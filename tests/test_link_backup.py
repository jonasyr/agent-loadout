import os

import pytest

from loadout import backup, link, paths


def test_backup_move_and_restore_roundtrip(fake_home):
    f = fake_home / "a.txt"
    f.write_text("hi")
    bk = backup.Backup()
    assert bk.empty
    bk.move(f, "move a")
    assert not f.exists()
    backup.restore(bk.root)
    assert f.read_text() == "hi"


def test_backup_save_copy_restores_original_content(fake_home):
    f = fake_home / "s.json"
    f.write_text("old")
    bk = backup.Backup()
    bk.save_copy(f, "settings")
    f.write_text("new")
    backup.restore(bk.root)
    assert f.read_text() == "old"


def test_restore_runs_undo_commands_in_reverse(fake_home, fake_runner):
    bk = backup.Backup()
    bk.record_command("one", ["echo", "1"])
    bk.record_command("two", ["echo", "2"])
    backup.restore(bk.root)
    assert fake_runner.calls == [["echo", "2"], ["echo", "1"]]


def _personal(fake_home):
    p = paths.personal_root() / "rules"
    p.mkdir(parents=True)
    (p / "me.md").write_text("me")


def test_link_all_creates_symlinks_and_is_idempotent(fake_home):
    _personal(fake_home)
    bk = backup.Backup()
    actions = link.link_all(bk)
    assert (fake_home / ".claude/rules/loadout/tooling.md").exists()
    assert (fake_home / ".claude/rules/personal/me.md").read_text() == "me"
    assert any("linked" in a for a in actions)
    assert link.link_all(backup.Backup()) == []
    assert bk.empty


def test_link_all_backs_up_existing_real_dir(fake_home):
    _personal(fake_home)
    existing = fake_home / ".claude/rules/loadout"
    existing.mkdir(parents=True)
    (existing / "old.md").write_text("old")
    bk = backup.Backup()
    link.link_all(bk)
    assert not bk.empty
    assert (fake_home / ".claude/rules/loadout").is_symlink()


def test_copy_fallback_when_symlinks_unavailable(fake_home, monkeypatch):
    _personal(fake_home)

    def no_symlink(*a, **k):
        raise OSError("symlinks not permitted")

    monkeypatch.setattr(os, "symlink", no_symlink)
    link.link_all(backup.Backup())
    assert link.is_copy_mode()
    assert (fake_home / ".claude/rules/loadout/tooling.md").exists()
    assert not (fake_home / ".claude/rules/loadout").is_symlink()
    # re-running in copy mode refreshes without creating backups
    bk = backup.Backup()
    link.link_all(bk)
    assert bk.empty


def test_link_bin_posix_symlink(fake_home):
    if os.name == "nt":
        pytest.skip("posix only")
    link.link_bin(backup.Backup())
    target = fake_home / ".local/bin/loadout"
    assert target.is_symlink()
    assert target.resolve() == (paths.kit_root() / "bin/loadout").resolve()


def test_windows_shims_quote_paths_with_spaces(fake_home, monkeypatch, tmp_path):
    kit = tmp_path / "Max Mustermann" / "loadout"
    (kit / "bin").mkdir(parents=True)
    (kit / "bin/loadout").write_text("")
    monkeypatch.setenv("LOADOUT_ROOT", str(kit))
    link.write_windows_shims(fake_home / ".local/bin")
    cmd = (fake_home / ".local/bin/loadout.cmd").read_text()
    sh = (fake_home / ".local/bin/loadout").read_text()
    assert f'"{kit / "bin" / "loadout"}"' in cmd
    assert f'"{(kit / "bin" / "loadout").as_posix()}"' in sh
