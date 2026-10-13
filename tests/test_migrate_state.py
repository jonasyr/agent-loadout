"""The one-time move of ~/.claude/.loadout and ~/.claude/backups to the XDG state folder (ADR 0025)."""
import errno
import json
import os

import pytest

from loadout import check, migrate, paths


def _legacy(fake_home):
    old = paths.legacy_state_dir()
    old.mkdir(parents=True)
    (old / "managed-settings.json").write_text('{"a": 1}')
    (old / "codex-config.json").write_text('{"tables": {}}')
    b = paths.legacy_backups_root() / "loadout-1"
    (b / "files").mkdir(parents=True)
    (b / "manifest.json").write_text('{"steps": []}')
    (b / "files" / "x").write_text("copy")
    return old


def test_nothing_to_do_is_silent(fake_home):
    assert migrate.migrate_state() == []
    assert not paths.state_dir().exists()


def test_moves_state_and_backups(fake_home):
    _legacy(fake_home)
    lines = migrate.migrate_state()
    assert (paths.state_dir() / "managed-settings.json").read_text() == '{"a": 1}'
    assert (paths.backups_root() / "loadout-1" / "files" / "x").read_text() == "copy"
    assert not paths.legacy_state_dir().exists() and not paths.legacy_backups_root().exists()
    assert any("moved its state and backups" in line for line in lines)
    assert migrate.migrate_state() == []  # a second run does nothing


def test_cross_device_copies_then_deletes(fake_home, monkeypatch):
    _legacy(fake_home)
    real = os.replace

    def replace(src, dst):
        if ".partial" not in str(src):
            raise OSError(errno.EXDEV, "cross-device link")
        return real(src, dst)
    monkeypatch.setattr(migrate.os, "replace", replace)
    migrate.migrate_state()
    assert (paths.backups_root() / "loadout-1" / "files" / "x").read_text() == "copy"
    assert (paths.state_dir() / "codex-config.json").exists()
    assert not paths.legacy_backups_root().exists()


def test_a_leftover_partial_copy_is_redone(fake_home, monkeypatch):
    _legacy(fake_home)
    partial = paths.state_dir() / "backups.partial"
    partial.mkdir(parents=True)
    (partial / "junk").write_text("half")
    real = os.replace
    monkeypatch.setattr(migrate.os, "replace", lambda s, d: real(s, d) if ".partial" in str(s)
                        else (_ for _ in ()).throw(OSError(errno.EXDEV, "x")))
    migrate.migrate_state()
    assert not partial.exists() and not (paths.backups_root() / "junk").exists()
    assert (paths.backups_root() / "loadout-1" / "manifest.json").exists()


def test_both_locations_keep_the_new_and_name_the_old(fake_home):
    _legacy(fake_home)
    paths.state_dir().mkdir(parents=True)
    (paths.state_dir() / "codex-config.json").write_text('{"new": true}')
    lines = migrate.migrate_state()
    assert json.loads((paths.state_dir() / "codex-config.json").read_text()) == {"new": True}
    assert (paths.state_dir() / "managed-settings.json").exists()  # the rest moved
    assert (paths.legacy_state_dir() / "codex-config.json").exists()  # kept, not lost
    assert any("codex-config.json" in line and "by hand" in line for line in lines)


def test_another_run_holding_the_lock_is_left_alone(fake_home):
    _legacy(fake_home)
    paths.state_dir().mkdir(parents=True)
    (paths.state_dir() / migrate.LOCK).write_text("")
    assert migrate.migrate_state() == []
    assert paths.legacy_state_dir().exists()


def test_empty_claude_folder_removed_only_with_claude_code_off(fake_home):
    _legacy(fake_home)
    (paths.personal_root()).mkdir(parents=True)
    (paths.personal_root() / "targets.json").write_text('{"claude": false, "codex": true}')
    migrate.migrate_state()
    assert not (fake_home / ".claude").exists()


def test_claude_folder_stays_with_claude_code_on_or_when_not_empty(fake_home):
    _legacy(fake_home)
    migrate.migrate_state()  # Claude Code on (no targets.json)
    assert (fake_home / ".claude").is_dir()
    (paths.personal_root()).mkdir(parents=True)
    (paths.personal_root() / "targets.json").write_text('{"claude": false, "codex": true}')
    (fake_home / ".claude" / "keep.txt").write_text("mine")
    _legacy(fake_home)
    migrate.migrate_state()
    assert (fake_home / ".claude" / "keep.txt").read_text() == "mine"


def test_damaged_targets_keeps_the_claude_folder(fake_home):
    _legacy(fake_home)
    paths.personal_root().mkdir(parents=True)
    (paths.personal_root() / "targets.json").write_text("{broken")
    migrate.migrate_state()
    assert (fake_home / ".claude").is_dir()


def test_main_runs_the_migration_and_reports_on_stderr(fake_home, capsys):
    from loadout.__main__ import main
    _legacy(fake_home)
    assert main(["kit-path"]) == 0
    captured = capsys.readouterr()
    assert "moved its state" in captured.err and "moved" not in captured.out
    assert (paths.state_dir() / "managed-settings.json").exists()


def test_check_warns_while_a_legacy_folder_remains(fake_home):
    assert check._legacy_state() == [check.CheckResult("loadout state", True)]
    paths.legacy_state_dir().mkdir(parents=True)
    (paths.legacy_state_dir() / "codex-config.json").write_text("{}")
    [row] = check._legacy_state()
    assert not row.ok and row.severity == "warn" and "codex-config.json" in row.detail
