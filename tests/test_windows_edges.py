"""Windows edge cases: paired restore steps, managed tracking, background notices, manual-commands format."""
import json
import shutil
from pathlib import Path

import pytest

from loadout import backup, maintenance, paths, personal_mcp, runner

SECRET = "ghp_" + "z" * 30


@pytest.fixture
def windows_cmd(monkeypatch):
    monkeypatch.setattr(runner, "_is_windows", lambda: True)
    monkeypatch.setattr(shutil, "which", lambda name: r"C:\npm\claude.CMD")


def _setup_personal(servers):
    root = paths.personal_root()
    root.mkdir(parents=True, exist_ok=True)
    (root / "mcp.json").write_text(json.dumps({"mcpServers": servers}))


def test_manual_commands_have_shell_form_and_windows_json_block(tmp_path):
    cfg = {"env": {"T": "a&b|c"}, "url": "https://x/?a=1&b=2"}
    cmds = [["claude", "mcp", "remove", "-s", "user", "srv"],
            ["claude", "mcp", "add-json", "-s", "user", "srv", json.dumps(cfg)]]
    text = Path(runner.write_manual_commands(tmp_path, "mcp srv", cmds)).read_text(encoding="utf-8")
    assert "# mcp srv" in text
    shell, windows = text.split("# macOS / Linux shell:")[1].split("# Windows")
    assert "claude mcp remove -s user srv" in shell and "claude mcp add-json -s user srv '{" in shell
    assert "--%" not in text and "claude mcp add-json" not in windows  # no claude.cmd + JSON invocation
    assert "close Claude Code" in windows and "%USERPROFILE%\\.claude.json" in windows
    block = windows.split("):\n", 1)[1]
    assert json.loads("{" + block + "}") == {"srv": cfg}  # the block is valid JSON under mcpServers


def test_manual_commands_windows_standalone_remove(tmp_path):
    text = Path(runner.write_manual_commands(tmp_path, "t", [["claude", "mcp", "remove", "-s", "user", "x"]])).read_text()
    assert 'delete the "x" entry under "mcpServers"' in text


def test_manual_commands_not_reappended_when_identical(tmp_path):
    cmd = ["claude", "mcp", "add-json", "-s", "user", "srv", '{"a": 1}']
    runner.write_manual_commands(tmp_path, "mcp srv", [cmd])
    first = (tmp_path / "manual-commands.txt").read_text(encoding="utf-8")
    runner.write_manual_commands(tmp_path, "mcp srv", [cmd])
    assert (tmp_path / "manual-commands.txt").read_text(encoding="utf-8") == first
    runner.write_manual_commands(tmp_path, "mcp srv", [cmd[:-1] + ['{"a": 2}']])
    assert (tmp_path / "manual-commands.txt").read_text(encoding="utf-8").count("# mcp srv") == 2


def test_restore_does_not_remove_when_paired_add_would_be_refused(fake_home, fake_runner, windows_cmd):
    bk = backup.Backup()
    # as fix_secrets records them: original add first, then remove of the rewritten server
    bk.record_command("secrets s (original)", ["claude", "mcp", "add-json", "-s", "user", "s", '{"env": {"T": "%s"}}' % SECRET])
    bk.record_command("secrets s (remove rewritten)", ["claude", "mcp", "remove", "-s", "user", "s"])
    lines, ok, _ = backup.restore(bk.root)
    assert not ok
    assert fake_runner.calls == []  # neither the remove nor the add reached claude
    text = (bk.root / "manual-commands.txt").read_text(encoding="utf-8")
    assert "mcp remove -s user s" in text and SECRET in text
    assert text.count("mcp add-json") == 1 and text.count("# restore") == 1  # one block, not repeated by the add step
    assert SECRET not in "\n".join(lines)


def test_restore_still_runs_unpaired_remove(fake_home, fake_runner, windows_cmd):
    bk = backup.Backup()
    bk.record_command("plugin x", ["claude", "mcp", "remove", "-s", "user", "other"])
    lines, ok, _ = backup.restore(bk.root)
    assert ok and fake_runner.calls == [["claude", "mcp", "remove", "-s", "user", "other"]]


def test_personal_mcp_keeps_managed_tracking_after_refusal(fake_home, fake_runner, windows_cmd):
    old, new = {"command": "old"}, {"command": "new", "env": {"T": SECRET}}
    paths.claude_json().write_text(json.dumps({"mcpServers": {"srv": old}}))
    _setup_personal({"srv": new})
    snap = paths.state_dir() / "managed-mcp.json"
    snap.parent.mkdir(parents=True, exist_ok=True)
    snap.write_text(json.dumps({"mcpServers": {"srv": old}}))
    personal_mcp.apply_mcp()
    assert json.loads(snap.read_text())["mcpServers"] == {"srv": old}
    out = personal_mcp.apply_mcp()  # second run: still managed, not "exists and is not managed"
    assert "not managed" not in "\n".join(out) and "manual-commands" in "\n".join(out)
    text = (paths.state_dir() / "manual-commands.txt").read_text(encoding="utf-8")
    assert text.count("# mcp srv") == 1


def test_background_apply_mcp_output_becomes_session_notice(fake_home, fake_runner, monkeypatch, tmp_path):
    kit = tmp_path / "kit"
    (kit / ".git").mkdir(parents=True)
    monkeypatch.setenv("LOADOUT_ROOT", str(kit))
    monkeypatch.setattr(maintenance, "pull_if_clean", lambda root: True)
    monkeypatch.setattr(maintenance, "find_outdated", lambda: [])
    import loadout.settings_merge as sm
    monkeypatch.setattr(sm, "apply_settings", lambda: ({}, {}))
    monkeypatch.setattr(personal_mcp, "apply_mcp", lambda: ["mcp srv: added"])
    maintenance.maintain(100.0)
    out = maintenance.session_start(100.0)
    assert "mcp srv: added" in json.loads(out)["systemMessage"]


def test_two_notices_are_both_kept(fake_home, monkeypatch):
    monkeypatch.setattr(maintenance, "_spawn_background", lambda: None)
    maintenance.notify("first")
    maintenance.notify("second")
    msg = json.loads(maintenance.session_start(0.0))["systemMessage"]
    assert "first" in msg and "second" in msg
