"""Follow-up fixes N1 (Windows .cmd guard vs remove-then-add), N2 (piped answers), N4 (restore state)."""
import json
import os
import shutil
import stat

import pytest

from loadout import adopt, backup, catalog, inventory, paths, personal_mcp, runner, secrets
from fixtures import FAKE_DEVIN, author_machine

SECRET = "ghp_" + "q" * 30


@pytest.fixture
def windows_cmd(monkeypatch):
    monkeypatch.setattr(runner, "_is_windows", lambda: True)
    monkeypatch.setattr(shutil, "which", lambda name: r"C:\npm\claude.CMD")


def _mutations(fake_runner):
    return [c for c in fake_runner.calls if c[:3] in (["claude", "mcp", "remove"], ["claude", "mcp", "add-json"])]


def _private_text(path):
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600 or os.name == "nt"
    return open(path, encoding="utf-8").read()


def test_would_refuse_matches_run_guard(windows_cmd):
    assert runner.would_refuse(["claude", "mcp", "add-json", "-s", "user", "s", '{"a": 1}'])
    assert not runner.would_refuse(["claude", "mcp", "remove", "-s", "user", "s"])


def test_would_refuse_false_off_windows(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/claude")
    assert not runner.would_refuse(["claude", "mcp", "add-json", "s", '{"a": 1}'])


def test_apply_mcp_replace_issues_no_remove_when_add_would_be_refused(fake_home, fake_runner, windows_cmd):
    old = {"command": "old"}
    new = {"command": "new", "env": {"API_TOKEN": SECRET}}
    paths.claude_json().write_text(json.dumps({"mcpServers": {"srv": old}}))
    root = paths.personal_root()
    root.mkdir(parents=True)
    (root / "mcp.json").write_text(json.dumps({"mcpServers": {"srv": new}}))
    snap = paths.state_dir() / "managed-mcp.json"
    snap.parent.mkdir(parents=True, exist_ok=True)
    snap.write_text(json.dumps({"mcpServers": {"srv": old}}))
    out = personal_mcp.apply_mcp()
    assert _mutations(fake_runner) == []
    text = _private_text(paths.state_dir() / "manual-commands.txt")
    assert SECRET in text and "add-json" in text and "mcp remove" in text
    assert SECRET not in "\n".join(out) and "manual-commands.txt" in "\n".join(out)
    assert json.loads(snap.read_text())["mcpServers"] == {"srv": old}  # still managed (old config), new not claimed


def test_fix_secrets_issues_no_remove_when_add_would_be_refused(fake_home, fake_runner, windows_cmd):
    author_machine(fake_home)
    found = [f for f in secrets.scan(json.loads(paths.claude_json().read_text())) if f.fixable]
    bk = backup.Backup()
    out = adopt.fix_secrets(found, bk)
    assert _mutations(fake_runner) == []
    text = _private_text(bk.root / "manual-commands.txt")
    assert "${MCP_DOCKER_DEVIN_API_KEY}" in text and "mcp remove" in text
    assert FAKE_DEVIN not in "\n".join(out) and "manual-commands.txt" in "\n".join(out)


def test_adopt_mcp_removal_skipped_when_undo_would_be_refused(fake_home, fake_runner, windows_cmd):
    author_machine(fake_home)
    chosen = [v for v in inventory.classify(inventory.collect(with_versions=False))
              if v.item.kind == "mcp" and v.action == "remove" and v.item.location != "~/.claude/.mcp.json"]
    assert chosen
    bk = backup.Backup()
    out = adopt.apply(chosen, bk)
    assert [c for c in fake_runner.calls if c[:3] == ["claude", "mcp", "remove"]] == []
    assert "not removed" in out[0]
    assert "mcp remove" in _private_text(bk.root / "manual-commands.txt")


def test_restore_run_step_refused_writes_full_command(fake_home, fake_runner, windows_cmd):
    bk = backup.Backup()
    bk.record_command("mcp g", ["claude", "mcp", "add-json", "-s", "user", "g", '{"env": {"T": "%s"}}' % SECRET])
    lines, ok, _ = backup.restore(bk.root)
    assert not ok and fake_runner.calls == []
    assert SECRET in _private_text(bk.root / "manual-commands.txt")
    assert SECRET not in "\n".join(lines)


def _outdated():
    entry = next(e for e in catalog.binaries() if e["id"] == "rtk")
    item = inventory.Item("binary", "rtk", "0.1.0 -> 0.2.0", "PATH", {"entry": entry, "state": "outdated"})
    return adopt.Verdict(item, "update", entry["reason"], entry["id"])


def test_piped_yes_does_not_answer_binary_command_confirmation(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(inventory, "classify", lambda items: [_outdated()])
    rc = adopt.run(True, {"update"}, set(), False, ask=lambda q: "y", with_versions=False, interactive=False)
    assert rc == 0
    assert [c for c in fake_runner.calls if c[:1] != ["claude"]] == []


def test_restore_exists_skip_is_a_failure_and_listed(fake_home):
    f = fake_home / "a.txt"
    f.write_text("backed up")
    bk = backup.Backup()
    bk.move(f, "move a")
    f.write_text("new")
    lines, ok, _ = backup.restore(bk.root)
    assert not ok
    assert any("skipped (exists)" in x for x in lines) and "NOT restored" in lines[-1] and "move a" in lines[-1]
    assert not json.loads((bk.root / "manifest.json").read_text()).get("restored_at")


def test_partial_restore_can_be_rerun_to_complete(fake_home, fake_runner):
    f = fake_home / "a.txt"
    f.write_text("a")
    bk = backup.Backup()
    bk.move(f, "move a")
    bk.record_command("mcp x", ["claude", "mcp", "add-json", "-s", "user", "x", "{}"])
    fake_runner.responses[("claude",)] = runner.Result(1, "", "boom")
    lines, ok, _ = backup.restore(bk.root)
    assert not ok and f.read_text() == "a"
    manifest = json.loads((bk.root / "manifest.json").read_text())
    assert "restored_at" not in manifest and [s.get("restored", False) for s in manifest["steps"]] == [True, False]
    fake_runner.responses.clear()
    fake_runner.calls.clear()
    lines, ok, _ = backup.restore(bk.root)
    assert ok
    assert fake_runner.calls == [["claude", "mcp", "add-json", "-s", "user", "x", "{}"]]  # only the failed step replayed
    assert json.loads((bk.root / "manifest.json").read_text())["restored_at"]
