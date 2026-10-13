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
    partial = paths.backups_root() / "loadout-1.partial"  # backups move entry by entry
    partial.mkdir(parents=True)
    (partial / "junk").write_text("half")
    real = os.replace
    monkeypatch.setattr(migrate.os, "replace", lambda s, d: real(s, d) if ".partial" in str(s)
                        else (_ for _ in ()).throw(OSError(errno.EXDEV, "x")))
    migrate.migrate_state()
    assert not partial.exists() and not (paths.backups_root() / "loadout-1" / "junk").exists()
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
    assert all("another loadout run" in line for line in migrate.migrate_state())
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


def test_an_old_session_s_hook_files_are_merged_quietly(fake_home):
    """A Claude Code session still running the old plugin keeps writing its session files to ~/.claude/.loadout."""
    paths.state_dir().mkdir(parents=True)
    (paths.state_dir() / "advisor-pending.json").write_text('{"plans": []}')
    old = paths.legacy_state_dir()
    old.mkdir(parents=True)
    (old / "advisor-pending.json").write_text('{"plans": [1]}')  # same name: disposable, not "kept"
    (old / "reload-notified.json").write_text("{}")  # new name: moved, but no notice for it
    assert migrate.migrate_state() == []  # session files never print the move notice
    assert (paths.state_dir() / "reload-notified.json").exists()
    assert json.loads((paths.state_dir() / "advisor-pending.json").read_text())["plans"] == []  # never rewritten
    assert check._legacy_state() == [check.CheckResult("loadout state", True)] and not migrate.pending()


def test_another_run_holding_the_lock_is_named(fake_home, monkeypatch):
    monkeypatch.setattr(migrate, "WAIT", 0)
    _legacy(fake_home)
    paths.state_dir().mkdir(parents=True)
    (paths.state_dir() / migrate.LOCK).write_text("")
    [line] = migrate.migrate_state()
    assert "another loadout run" in line


def test_the_session_hook_waits_only_briefly(fake_home, monkeypatch):
    from loadout.__main__ import main
    waits = []
    monkeypatch.setattr(migrate, "migrate_state", lambda wait=None: waits.append(wait) or [])
    main(["hook-session-start"])
    assert waits and waits[0] is not None and waits[0] <= 2


def test_restore_and_a_bare_loadout_are_not_blocked(fake_home, monkeypatch, capsys):
    from loadout.__main__ import EXEMPT
    assert {"restore", "kit-path", "check", None} <= EXEMPT


def test_a_symlinked_old_state_folder_is_moved_and_unlinked(fake_home, tmp_path):
    real = tmp_path / "dotfiles-state"
    real.mkdir()
    (real / "managed-settings.json").write_text('{"a": 1}')
    paths.claude_home().mkdir()
    paths.legacy_state_dir().symlink_to(real, target_is_directory=True)
    assert any("moved" in line for line in migrate.migrate_state())
    assert (paths.state_dir() / "managed-settings.json").exists()
    assert not paths.legacy_state_dir().is_symlink() and not paths.legacy_state_dir().exists()
    assert migrate.migrate_state() == []


def test_check_survives_an_unreadable_old_folder(fake_home, monkeypatch):
    paths.legacy_state_dir().mkdir(parents=True)
    real = type(paths.legacy_state_dir()).iterdir
    monkeypatch.setattr(type(paths.legacy_state_dir()), "iterdir",
                        lambda self: (_ for _ in ()).throw(PermissionError("denied")) if self.name == ".loadout" else real(self))
    [row] = check._legacy_state()
    assert not row.ok and "denied" in row.detail


def test_claude_code_s_own_files_in_its_backups_folder_stay(fake_home):
    """~/.claude/backups is shared: Claude Code keeps its .claude.json rotation copies there."""
    _legacy(fake_home)
    theirs = paths.legacy_backups_root() / ".claude.json.backup.1791900553516"
    theirs.write_text("{}")
    (paths.legacy_backups_root() / "pre-loadout-baseline-1").mkdir()  # a hand-made snapshot, no manifest
    (paths.legacy_backups_root() / "loadout-notes").write_text("a file, not one of loadout's backups")
    lines = migrate.migrate_state()
    assert theirs.read_text() == "{}", "Claude Code's file stays where Claude Code rotates it"
    assert not (paths.backups_root() / theirs.name).exists()
    assert (paths.backups_root() / "loadout-1").is_dir()
    assert (paths.legacy_backups_root() / "pre-loadout-baseline-1").is_dir()
    assert (paths.legacy_backups_root() / "loadout-notes").is_file()
    assert not migrate.pending() and check._legacy_state() == [check.CheckResult("loadout state", True)]
    assert migrate.migrate_state() == [] and lines  # nothing of loadout's left: later runs stay quiet


def test_an_unreadable_old_folder_counts_as_pending(fake_home, monkeypatch):
    paths.legacy_state_dir().mkdir(parents=True)
    real = type(paths.legacy_state_dir()).iterdir
    monkeypatch.setattr(type(paths.legacy_state_dir()), "iterdir",
                        lambda self: (_ for _ in ()).throw(PermissionError("denied")) if self.name == ".loadout" else real(self))
    assert migrate.pending(), "writing commands must not run on an empty snapshot while the old one is unreadable"


def test_an_old_session_keeps_its_file_and_the_new_one_is_never_rewritten(fake_home):
    """Hooks write without the migration lock: rewriting the new file could undo a plan a hook just recorded.
    The old session keeps reading its own file, so it stays until no session can still use it."""
    import time as _time
    paths.state_dir().mkdir(parents=True)
    new_pending = paths.state_dir() / "advisor-pending.json"
    new_pending.write_text(json.dumps({"plans": [{"path": "new.md"}]}))
    before = new_pending.stat().st_mtime_ns
    old = paths.legacy_state_dir()
    old.mkdir(parents=True)
    (old / "advisor-pending.json").write_text(json.dumps({"plans": [{"path": "old.md"}]}))
    (old / "advisor-done.json").write_text(json.dumps({"evaluated": {"a": "1"}}))  # the new place has none yet
    (old / "reload-notified.json").write_text("{}")
    stale = _time.time() - 3 * 86400
    os.utime(old / "reload-notified.json", (stale, stale))
    (paths.state_dir() / "reload-notified.json").write_text('{"sessions": ["s"]}')
    assert migrate.migrate_state() == []
    assert new_pending.stat().st_mtime_ns == before, "the live file is never rewritten"
    assert (old / "advisor-pending.json").exists(), "a recent old file stays for the session still using it"
    assert json.loads((paths.state_dir() / "advisor-done.json").read_text()) == {"evaluated": {"a": "1"}}  # moved in
    assert not (old / "reload-notified.json").exists(), "an idle old copy goes"
    assert json.loads((paths.state_dir() / "reload-notified.json").read_text()) == {"sessions": ["s"]}
    assert not migrate.pending() and check._legacy_state() == [check.CheckResult("loadout state", True)]


def test_a_cross_device_copy_never_overwrites_a_file_that_appeared(fake_home, monkeypatch):
    old = paths.legacy_state_dir()
    old.mkdir(parents=True)
    (old / "codex-hooks.json").write_text('{"old": true}')
    paths.state_dir().mkdir(parents=True)
    target = paths.state_dir() / "codex-hooks.json"
    monkeypatch.setattr(migrate.os, "link", lambda s, d, **kw: (_ for _ in ()).throw(OSError(errno.EXDEV, "x")))
    real_copy = migrate.shutil.copy2

    def copy_then_hook_writes(src, dst, **kw):
        out = real_copy(src, dst, **kw)
        target.write_text('{"hook": true}')  # a hook (no lock) writes the new place during the copy
        return out
    monkeypatch.setattr(migrate.shutil, "copy2", copy_then_hook_writes)
    migrate.migrate_state()
    assert json.loads(target.read_text()) == {"hook": True}, "the file that appeared wins"
    assert json.loads((old / "codex-hooks.json").read_text()) == {"old": True}, "the old one is kept, not lost"
    assert not list(paths.state_dir().glob("*.partial"))


def test_a_recent_session_file_is_copied_and_kept_for_its_session(fake_home):
    import time as _time
    old = paths.legacy_state_dir()
    old.mkdir(parents=True)
    (old / "advisor-pending.json").write_text('{"plans": [1]}')  # just written by a running old session
    (old / "advisor-done.json").write_text('{"evaluated": {}}')
    stale = _time.time() - 3 * 86400
    os.utime(old / "advisor-done.json", (stale, stale))
    migrate.migrate_state()
    assert (paths.state_dir() / "advisor-pending.json").read_text() == '{"plans": [1]}'
    assert (old / "advisor-pending.json").read_text() == '{"plans": [1]}', "its session still reads it there"
    assert (paths.state_dir() / "advisor-done.json").exists() and not (old / "advisor-done.json").exists()


def test_publish_without_hard_links_never_overwrites(fake_home, tmp_path, monkeypatch):
    monkeypatch.setattr(migrate.os, "link", lambda s, d, **kw: (_ for _ in ()).throw(NotImplementedError()))
    src, dst = tmp_path / "a.partial", tmp_path / "a"
    src.write_text("copy")
    dst.write_text("hook")
    assert migrate._publish(src, dst) is False
    assert dst.read_text() == "hook" and not src.exists()
    src.write_text("copy")
    dst.unlink()
    assert migrate._publish(src, dst) is True
    assert dst.read_text() == "copy" and not src.exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions")
def test_the_state_folder_is_private_from_the_start(fake_home):
    from loadout.__main__ import main
    assert main(["kit-path"]) == 0
    assert paths.state_dir().stat().st_mode & 0o777 == 0o700
