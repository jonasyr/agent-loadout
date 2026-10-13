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


def test_another_run_holding_the_lock_is_left_alone(fake_home, monkeypatch):
    monkeypatch.setattr(migrate, "WAIT", 0)
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


def test_the_notice_is_printed_only_when_something_moved(fake_home):
    _legacy(fake_home)
    paths.state_dir().mkdir(parents=True)
    (paths.state_dir() / "codex-config.json").write_text("{}")
    first = migrate.migrate_state()
    assert any("moved" in line for line in first) and any("by hand" in line for line in first)
    assert migrate.migrate_state() == []  # only the kept entry is left: loadout check reminds, not every command
    assert not migrate.pending()


def test_no_partial_files_are_left_after_a_cross_device_move(fake_home, monkeypatch):
    _legacy(fake_home)
    real = os.replace
    monkeypatch.setattr(migrate.os, "replace", lambda s, d: real(s, d) if ".partial" in str(s)
                        else (_ for _ in ()).throw(OSError(errno.EXDEV, "x")))
    monkeypatch.setattr(migrate.os, "link", lambda s, d, **kw: (_ for _ in ()).throw(OSError(errno.EXDEV, "x")))
    migrate.migrate_state()
    assert not list(paths.state_dir().rglob("*.partial"))
    assert (paths.state_dir() / "managed-settings.json").read_text() == '{"a": 1}'


def test_a_failed_move_keeps_everything_and_blocks_writing_commands(fake_home, monkeypatch, capsys):
    from loadout.__main__ import main
    _legacy(fake_home)
    real = migrate._move
    monkeypatch.setattr(migrate, "_move", lambda old, new: (_ for _ in ()).throw(OSError("disk full")))
    assert main(["apply-settings"]) == 1
    err = capsys.readouterr().err
    assert "disk full" in err and "did not finish" in err
    assert not (paths.state_dir() / "managed-settings.json").exists()  # nothing written to the new place
    assert (paths.legacy_state_dir() / "managed-settings.json").read_text() == '{"a": 1}'
    assert main(["kit-path"]) == 0  # read-only commands still work
    assert main(["hook-session-start"]) == 0  # the session never fails over it
    assert not (paths.state_dir() / migrate.LOCK).exists()  # the lock was released
    monkeypatch.setattr(migrate, "_move", real)
    assert main(["apply-settings"]) == 0  # the next run finishes the move
    assert (paths.state_dir() / "managed-settings.json").exists() and not migrate.pending()


def test_ctrl_c_during_the_move_is_a_clean_exit(fake_home, monkeypatch, capsys):
    from loadout.__main__ import main
    _legacy(fake_home)
    monkeypatch.setattr(migrate, "_move", lambda old, new: (_ for _ in ()).throw(KeyboardInterrupt()))
    assert main(["kit-path"]) == 130
    assert "interrupted" in capsys.readouterr().err
    assert not (paths.state_dir() / migrate.LOCK).exists()


def test_a_platform_without_linkat_copies_instead(fake_home, monkeypatch):
    def no_linkat(s, d, **kw):
        raise NotImplementedError("follow_symlinks unavailable on this platform")
    monkeypatch.setattr(migrate.os, "link", no_linkat)
    _legacy(fake_home)
    migrate.migrate_state()
    assert (paths.state_dir() / "managed-settings.json").read_text() == '{"a": 1}'
    assert not paths.legacy_state_dir().exists()
