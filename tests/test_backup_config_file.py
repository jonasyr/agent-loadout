"""A config-file undo step: the MCP server config lives in a private file in the backup, never in the manifest."""
import json
import os
import stat

import pytest

from loadout import backup, paths, runner

SECRET = "ghp_" + "s" * 30
CFG = {"command": "x", "env": {"TOKEN": SECRET}}
ADD = ["claude", "mcp", "add-json", "-s", "user", "srv"]


@pytest.fixture
def windows_cmd(monkeypatch):
    monkeypatch.setattr(runner, "_is_windows", lambda: True)
    monkeypatch.setattr(runner, "_resolve", lambda name: "/winnpm/claude.CMD")


def _made(name="srv", cfg=None):
    bk = backup.Backup(description="t")
    return bk, bk.record_mcp_add(f"{name} (original)", name, CFG if cfg is None else cfg)


def _edit(bk, fn):
    path = bk.root / "manifest.json"
    data = json.loads(path.read_text())
    fn(data["steps"][0]["undo"])
    path.write_text(json.dumps(data))


def _refused(bk, fake_runner):
    lines, ok, _ = backup.restore(bk.root)
    assert ok is False and any(x.startswith("failed: ") for x in lines)
    assert fake_runner.calls == []


def test_record_mcp_add_keeps_secret_out_of_manifest(fake_home):
    bk, file = _made()
    assert SECRET not in (bk.root / "manifest.json").read_text()
    assert SECRET in file.read_text()
    if os.name != "nt":
        assert stat.S_IMODE(file.stat().st_mode) == 0o600


def test_restore_runs_add_json_with_exact_config(fake_home, fake_runner):
    bk, _ = _made()
    lines, ok, _ = backup.restore(bk.root)
    assert ok
    assert fake_runner.calls == [[*ADD, fake_runner.calls[0][6]]]
    assert json.loads(fake_runner.calls[0][6]) == CFG


def test_config_file_outside_files_refused(fake_home, fake_runner):
    bk, _ = _made()
    other = bk.root / "elsewhere.json"
    other.write_text(json.dumps(CFG))
    _edit(bk, lambda u: u.update({"config-file": str(other)}))
    _refused(bk, fake_runner)


@pytest.mark.skipif(os.name == "nt", reason="symlinks need privileges on Windows")
def test_config_file_symlink_refused(fake_home, fake_runner):
    bk, file = _made()
    target = fake_home / "outside.json"
    target.write_text(json.dumps(CFG))
    file.unlink()
    file.symlink_to(target)
    _refused(bk, fake_runner)


def test_config_file_missing_refused(fake_home, fake_runner):
    bk, file = _made()
    file.unlink()
    _refused(bk, fake_runner)


def test_config_file_not_object_refused(fake_home, fake_runner):
    bk, file = _made()
    file.write_text("[1]")
    _refused(bk, fake_runner)


def test_config_file_with_other_command_refused(fake_home, fake_runner):
    bk, _ = _made()
    _edit(bk, lambda u: u.update({"run": ["claude", "mcp", "add-json", "-s", "user", "srv", "{}"]}))
    _refused(bk, fake_runner)
    _edit(bk, lambda u: u.update({"run": ["rm", "-rf", "x"]}))
    _refused(bk, fake_runner)


def test_config_file_name_is_sanitised(fake_home):
    bk, file = _made("../x/y")
    assert file.parent == bk.root / "files"


def test_config_file_path_is_mapped_for_legacy_backups(fake_home, fake_runner):
    bk, file = _made()
    legacy = paths.legacy_backups_root() / bk.root.name / "files" / file.name
    _edit(bk, lambda u: u.update({"config-file": str(legacy)}))
    lines, ok, _ = backup.restore(bk.root)
    assert ok and len(fake_runner.calls) == 1


def test_force_replay_reuses_config_file(fake_home, fake_runner):
    bk, file = _made()
    assert backup.restore(bk.root)[1]
    assert backup.restore(bk.root, force=True)[1]
    assert [c[:6] for c in fake_runner.calls] == [ADD, ADD] and file.is_file()


def test_inline_add_json_still_restores(fake_home, fake_runner):
    bk = backup.Backup(description="t")
    cmd = [*ADD, json.dumps(CFG)]
    bk.record_command("srv (original)", cmd)
    assert backup.restore(bk.root)[1]
    assert fake_runner.calls == [cmd]


def test_show_names_config_file_without_secret(fake_home):
    _made()
    text = "\n".join(backup.contents(backup.backups()[0]))
    assert "add-json -s user srv <config in " in text and SECRET not in text
