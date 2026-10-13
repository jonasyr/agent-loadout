"""Moving loadout's files out of ~/.claude (ADR 0025): copy first, retire the old copies in a later run."""
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


@pytest.fixture
def clock(monkeypatch):
    """Move time forward: `clock(seconds)`."""
    offset = [0.0]
    real = migrate.time.time
    monkeypatch.setattr(migrate.time, "time", lambda: real() + offset[0])

    def advance(seconds):
        offset[0] += seconds
    return advance


@pytest.fixture
def at_once(monkeypatch):
    monkeypatch.setattr(migrate, "RETIRE_AFTER", 0.0)


def test_nothing_to_do_is_silent(fake_home):
    assert migrate.migrate_state() == []
    assert not paths.state_dir().exists()


def test_copies_first_and_retires_later(fake_home, clock):
    _legacy(fake_home)
    lines = migrate.migrate_state()
    assert any("copied its state and backups" in line for line in lines)
    assert (paths.state_dir() / "managed-settings.json").read_text() == '{"a": 1}'
    assert (paths.backups_root() / "loadout-1" / "files" / "x").read_text() == "copy"
    assert (paths.legacy_state_dir() / "managed-settings.json").exists(), "nothing is deleted in the copying run"
    assert not migrate.pending()
    assert migrate.migrate_state() == []  # too early to retire: quiet
    clock(migrate.RETIRE_AFTER + 1)
    assert migrate.migrate_state() == []
    assert not paths.legacy_state_dir().exists() and not paths.legacy_backups_root().exists()
    assert (paths.state_dir() / "managed-settings.json").read_text() == '{"a": 1}'


def test_a_busy_old_maintenance_run_postpones_retiring(fake_home, clock):
    old = _legacy(fake_home)
    (old / "maintenance.lock").write_text("")
    migrate.migrate_state()
    assert not (paths.state_dir() / "maintenance.lock").exists(), "a lock belongs to its process: never copied"
    clock(migrate.RETIRE_AFTER + 1)
    os.utime(old / "maintenance.lock")  # still fresh
    migrate.migrate_state()
    assert (old / "managed-settings.json").exists()


def test_an_old_entry_changed_after_its_copy_replaces_the_untouched_copy(fake_home, clock):
    old = _legacy(fake_home)
    migrate.migrate_state()
    (old / "managed-settings.json").write_text('{"a": 2}')  # an old process wrote it after the copy
    clock(migrate.RETIRE_AFTER + 1)
    assert migrate.migrate_state() == []
    assert (paths.state_dir() / "managed-settings.json").read_text() == '{"a": 2}', "the newer old one wins"
    assert (old / "managed-settings.json").exists(), "retired only after another quiet period"
    clock(migrate.RETIRE_AFTER + 1)
    migrate.migrate_state()
    assert not (old / "managed-settings.json").exists()


def test_both_changed_keeps_both_and_names_it_once(fake_home, clock):
    old = _legacy(fake_home)
    migrate.migrate_state()
    (old / "codex-config.json").write_text('{"old": true}')
    (paths.state_dir() / "codex-config.json").write_text('{"new": true}')
    clock(migrate.RETIRE_AFTER + 1)
    lines = migrate.migrate_state()
    assert any("both places have it" in line and "codex-config.json" in line for line in lines)
    assert json.loads((paths.state_dir() / "codex-config.json").read_text()) == {"new": True}
    assert json.loads((old / "codex-config.json").read_text()) == {"old": True}
    assert migrate.leftovers() == [old / "codex-config.json"] and not migrate.pending()
    [row] = check._legacy_state()
    assert not row.ok and row.severity == "warn" and "codex-config.json" in row.detail
    clock(migrate.RETIRE_AFTER + 1)
    assert migrate.migrate_state() == [], "named once"


def test_retire_never_deletes_a_file_replaced_at_that_moment(fake_home, tmp_path):
    f = tmp_path / "state.json"
    f.write_text("old")
    recorded = migrate._sig(f)
    (tmp_path / "next").write_text("written by an old process")
    os.replace(tmp_path / "next", f)  # atomically replaced: another inode
    assert migrate._retire(f, recorded) == "changed"
    assert f.read_text() == "written by an old process"


def test_a_backup_an_old_run_was_still_filling_is_copied_again(fake_home, clock):
    _legacy(fake_home)
    migrate.migrate_state()
    (paths.legacy_backups_root() / "loadout-1" / "files" / "y").write_text("moved in late")  # old adopt finishing
    clock(migrate.RETIRE_AFTER + 1)
    migrate.migrate_state()
    assert (paths.backups_root() / "loadout-1" / "files" / "y").read_text() == "moved in late"
    clock(migrate.RETIRE_AFTER + 1)
    migrate.migrate_state()
    assert not paths.legacy_backups_root().exists()


def test_an_entry_changing_while_it_is_copied_waits_for_the_next_run(fake_home, monkeypatch):
    _legacy(fake_home)
    real = migrate.shutil.copytree

    def copy_while_old_adopt_writes(src, dst, *a, **kw):
        out = real(src, dst, *a, **kw)
        if src.name == "loadout-1" and not (src / "files" / "late").exists():
            (src / "files" / "late").write_text("late")
        return out
    monkeypatch.setattr(migrate.shutil, "copytree", copy_while_old_adopt_writes)
    migrate.migrate_state()
    assert not (paths.backups_root() / "loadout-1").exists() and migrate.pending()
    monkeypatch.setattr(migrate.shutil, "copytree", real)
    migrate.migrate_state()
    assert (paths.backups_root() / "loadout-1" / "files" / "late").exists() and not migrate.pending()


def test_a_file_that_appears_at_the_new_place_while_copying_wins(fake_home, monkeypatch):
    old = paths.legacy_state_dir()
    old.mkdir(parents=True)
    (old / "codex-hooks.json").write_text('{"old": true}')
    paths.state_dir().mkdir(parents=True)
    target = paths.state_dir() / "codex-hooks.json"
    monkeypatch.setattr(migrate.os, "link", lambda s, d, **kw: (_ for _ in ()).throw(OSError(errno.EXDEV, "x")))
    real = migrate.shutil.copy2

    def copy_then_writer(src, dst, **kw):
        out = real(src, dst, **kw)
        target.write_text('{"current": true}')
        return out
    monkeypatch.setattr(migrate.shutil, "copy2", copy_then_writer)
    migrate.migrate_state()
    monkeypatch.setattr(migrate.shutil, "copy2", real)
    migrate.migrate_state()
    assert json.loads(target.read_text()) == {"current": True}
    assert json.loads((old / "codex-hooks.json").read_text()) == {"old": True}
    assert migrate.leftovers() == [old / "codex-hooks.json"]
    assert not list(paths.state_dir().glob("*.partial"))


def test_cross_device_and_no_hard_links_copy_without_partials(fake_home, monkeypatch, at_once):
    _legacy(fake_home)
    monkeypatch.setattr(migrate.os, "link", lambda s, d, **kw: (_ for _ in ()).throw(NotImplementedError()))
    migrate.migrate_state()
    assert (paths.state_dir() / "managed-settings.json").read_text() == '{"a": 1}'
    assert not list(paths.state_dir().rglob("*.partial"))
    assert not paths.legacy_state_dir().exists()


def test_publish_without_hard_links_never_overwrites(fake_home, tmp_path, monkeypatch):
    monkeypatch.setattr(migrate.os, "link", lambda s, d, **kw: (_ for _ in ()).throw(NotImplementedError()))
    src, dst = tmp_path / "a.partial", tmp_path / "a"
    src.write_text("copy")
    dst.write_text("current")
    assert migrate._publish(src, dst) is False
    assert dst.read_text() == "current" and not src.exists()
    src.write_text("copy")
    dst.unlink()
    assert migrate._publish(src, dst) is True and dst.read_text() == "copy"


def test_session_files_are_copied_kept_while_recent_and_never_copied_back(fake_home, clock):
    paths.state_dir().mkdir(parents=True)
    live = paths.state_dir() / "advisor-pending.json"
    live.write_text('{"plans": ["new"]}')
    old = paths.legacy_state_dir()
    old.mkdir(parents=True)
    (old / "advisor-pending.json").write_text('{"plans": ["old"]}')
    (old / "advisor-done.json").write_text('{"evaluated": {}}')
    assert migrate.migrate_state() == [], "session files never print the notice"
    assert live.read_text() == '{"plans": ["new"]}', "the live file is never rewritten"
    assert (paths.state_dir() / "advisor-done.json").exists()
    clock(migrate.RETIRE_AFTER + 1)
    (old / "advisor-pending.json").write_text('{"plans": ["old", "more"]}')  # the old session keeps working
    migrate.migrate_state()
    assert live.read_text() == '{"plans": ["new"]}' and (old / "advisor-pending.json").exists()
    assert not migrate.pending() and check._legacy_state() == [check.CheckResult("loadout state", True)]
    clock(migrate.SESSION_IDLE + migrate.RETIRE_AFTER + 1)
    migrate.migrate_state()
    clock(migrate.RETIRE_AFTER + 1)
    migrate.migrate_state()
    assert not old.exists()


def test_claude_code_s_own_files_in_its_backups_folder_stay(fake_home, at_once):
    _legacy(fake_home)
    theirs = paths.legacy_backups_root() / ".claude.json.backup.1791900553516"
    theirs.write_text("{}")
    (paths.legacy_backups_root() / "pre-loadout-baseline-1").mkdir()
    migrate.migrate_state()
    assert theirs.read_text() == "{}" and (paths.legacy_backups_root() / "pre-loadout-baseline-1").is_dir()
    assert not (paths.backups_root() / theirs.name).exists()
    assert (paths.backups_root() / "loadout-1").is_dir() and not (paths.legacy_backups_root() / "loadout-1").exists()
    assert not migrate.pending()


def test_an_unreadable_old_folder_counts_as_pending(fake_home, monkeypatch):
    real = migrate.os.stat
    legacy = str(paths.legacy_state_dir())
    monkeypatch.setattr(migrate.os, "stat", lambda p, **kw: (_ for _ in ()).throw(PermissionError("denied"))
                        if str(p) == legacy else real(p, **kw))
    assert migrate.pending()


def test_a_failed_copy_keeps_everything_and_blocks_writing_commands(fake_home, monkeypatch, capsys):
    from loadout.__main__ import main
    _legacy(fake_home)
    real = migrate._copy
    monkeypatch.setattr(migrate, "_copy", lambda old, new: (_ for _ in ()).throw(OSError("disk full")))
    assert main(["apply-settings"]) == 1
    err = capsys.readouterr().err
    assert "disk full" in err and "did not finish" in err
    assert not (paths.state_dir() / "managed-settings.json").exists()
    assert main(["kit-path"]) == 0 and main(["hook-session-start"]) == 0
    assert not (paths.state_dir() / migrate.LOCK).exists()
    monkeypatch.setattr(migrate, "_copy", real)
    assert main(["apply-settings"]) == 0
    assert not migrate.pending()


def test_ctrl_c_during_the_copy_is_a_clean_exit(fake_home, monkeypatch, capsys):
    from loadout.__main__ import main
    _legacy(fake_home)
    monkeypatch.setattr(migrate, "_copy", lambda old, new: (_ for _ in ()).throw(KeyboardInterrupt()))
    assert main(["kit-path"]) == 130
    assert "interrupted" in capsys.readouterr().err
    assert not (paths.state_dir() / migrate.LOCK).exists()


def test_main_reports_on_stderr_only(fake_home, capsys):
    from loadout.__main__ import main
    _legacy(fake_home)
    assert main(["kit-path"]) == 0
    captured = capsys.readouterr()
    assert "copied its state" in captured.err and "copied" not in captured.out


def test_another_run_holding_the_lock_is_named(fake_home, monkeypatch):
    monkeypatch.setattr(migrate, "WAIT", 0)
    _legacy(fake_home)
    paths.state_dir().mkdir(parents=True)
    (paths.state_dir() / migrate.LOCK).write_text("")
    [line] = migrate.migrate_state()
    assert "another loadout run" in line and paths.legacy_state_dir().exists()


def test_the_session_hook_waits_only_briefly(fake_home, monkeypatch):
    from loadout.__main__ import main
    waits = []
    monkeypatch.setattr(migrate, "migrate_state", lambda wait=None: waits.append(wait) or [])
    main(["hook-session-start"])
    assert waits and waits[0] is not None and waits[0] <= 2


def test_restore_check_and_a_bare_loadout_are_not_blocked():
    from loadout.__main__ import EXEMPT
    assert {"restore", "kit-path", "check", None} <= EXEMPT


def test_empty_claude_folder_removed_only_with_claude_code_off(fake_home, at_once):
    _legacy(fake_home)
    paths.personal_root().mkdir(parents=True)
    (paths.personal_root() / "targets.json").write_text('{"claude": false, "codex": true}')
    migrate.migrate_state()
    assert not (fake_home / ".claude").exists()


def test_claude_folder_stays_with_claude_code_on_or_damaged_targets(fake_home, at_once):
    _legacy(fake_home)
    migrate.migrate_state()  # Claude Code on (no targets.json)
    assert (fake_home / ".claude").is_dir()
    paths.personal_root().mkdir(parents=True)
    (paths.personal_root() / "targets.json").write_text("{broken")
    migrate.migrate_state()
    assert (fake_home / ".claude").is_dir()


def test_a_symlinked_old_state_folder_is_copied_and_unlinked(fake_home, tmp_path, at_once):
    real = tmp_path / "dotfiles-state"
    real.mkdir()
    (real / "managed-settings.json").write_text('{"a": 1}')
    paths.claude_home().mkdir()
    paths.legacy_state_dir().symlink_to(real, target_is_directory=True)
    migrate.migrate_state()
    assert (paths.state_dir() / "managed-settings.json").exists()
    assert not paths.legacy_state_dir().is_symlink() and not paths.legacy_state_dir().exists()


def test_check_survives_an_unreadable_old_folder(fake_home, monkeypatch):
    monkeypatch.setattr(migrate, "pending", lambda: (_ for _ in ()).throw(PermissionError("denied")))
    [row] = check._legacy_state()
    assert not row.ok and "denied" in row.detail


def test_check_warns_while_something_is_not_copied(fake_home, monkeypatch):
    assert check._legacy_state() == [check.CheckResult("loadout state", True)]
    monkeypatch.setattr(migrate, "pending", lambda: True)
    [row] = check._legacy_state()
    assert not row.ok and "not everything was copied" in row.detail


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions")
def test_the_state_folder_is_private_from_the_start(fake_home):
    from loadout.__main__ import main
    assert main(["kit-path"]) == 0
    assert paths.state_dir().stat().st_mode & 0o777 == 0o700
