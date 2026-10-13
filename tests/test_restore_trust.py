"""restore replays only loadout's own backups and only the undo commands loadout records."""
import json

import pytest

from loadout import backup, paths


def _manifest(root, steps):
    root.mkdir(parents=True)
    (root / "manifest.json").write_text(json.dumps({"steps": steps}))


def test_a_folder_outside_the_backup_directory_is_refused(fake_home, tmp_path):
    _manifest(tmp_path / "evil", [])
    lines, ok, _ = backup.restore(tmp_path / "evil")
    assert not ok and "only restores backups under" in lines[0]


@pytest.mark.parametrize("cmd", [
    ["claude", "mcp", "add-json", "-s", "user", "x", '{"command": "sh"}', "--extra"],
    ["claude", "mcp", "add-json", "-s", "user", "x", "[1]"],
    ["claude", "mcp", "add-json", "-s", "local", "x", '{"command": "sh"}'],
    ["claude", "config", "set", "x", "y"],
    ["claude", "plugin", "install", "-x"],
    ["codex", "plugin", "add", "x@y"],
])
def test_only_recorded_undo_shapes_run(fake_home, fake_runner, cmd):
    root = paths.backups_root() / "loadout-1"
    _manifest(root, [{"label": "x", "undo": {"run": cmd}}])
    lines, ok, _ = backup.restore(root)
    assert not ok and fake_runner.calls == []


@pytest.mark.parametrize("cmd", [
    ["claude", "mcp", "add-json", "-s", "user", "x", '{"command": "npx"}'],
    ["claude", "mcp", "remove", "-s", "user", "x"],
    ["claude", "plugin", "enable", "a@b", "--scope", "user"],
    ["claude", "plugin", "install", "a@b", "--scope", "user"],
    ["claude", "plugin", "marketplace", "add", "owner/repo"],
    ["codex", "plugin", "remove", "a@b"],
    ["codex", "plugin", "marketplace", "remove", "m"],
])
def test_recorded_undo_shapes_still_run(fake_home, fake_runner, cmd):
    root = paths.backups_root() / "loadout-2"
    _manifest(root, [{"label": "x", "undo": {"run": cmd}}])
    backup.restore(root)
    assert fake_runner.calls == [cmd]


def test_a_move_source_outside_the_backup_is_refused(fake_home, tmp_path):
    victim = tmp_path / "victim"
    victim.write_text("keep")
    root = paths.backups_root() / "loadout-3"
    _manifest(root, [{"label": "x", "undo": {"move": [str(victim), str(tmp_path / "dest")]}}])
    lines, ok, _ = backup.restore(root)
    assert not ok and victim.read_text() == "keep"


def test_a_real_backup_round_trips(fake_home):
    f = fake_home / "f.txt"
    f.write_text("old")
    bk = backup.Backup(description="t")
    bk.save_copy(f, "f")
    f.write_text("new")
    lines, ok, pre = backup.restore(bk.root)
    assert ok and f.read_text() == "old"
    assert backup.restore(pre)[1]  # a pre-restore backup is restorable too


def test_a_symlinked_backup_folder_is_refused(fake_home, tmp_path):
    outside = fake_home / "outside"
    _manifest(outside, [])
    paths.backups_root().mkdir(parents=True, exist_ok=True)
    (paths.backups_root() / "link").symlink_to(outside)
    lines, ok, _ = backup.restore(paths.backups_root() / "link")
    assert not ok and "only restores backups under" in lines[0]


@pytest.mark.parametrize("tail", ["..", "x/.."])
def test_dot_dot_backup_paths_are_refused(fake_home, tail):
    paths.backups_root().mkdir(parents=True, exist_ok=True)
    (paths.backups_root() / "x").mkdir(exist_ok=True)
    lines, ok, _ = backup.restore(paths.backups_root() / tail)
    assert not ok


def test_a_source_ending_in_dot_dot_is_refused(fake_home, tmp_path):
    root = paths.backups_root() / "loadout-4"
    _manifest(root, [{"label": "x", "undo": {"move": [str(root / "files" / ".."), str(tmp_path / "dest")]}}])
    (root / "files").mkdir()
    lines, ok, _ = backup.restore(root)
    assert not ok and root.exists()


def test_a_symlinked_restore_file_source_is_refused(fake_home):
    secret = fake_home / "secret.txt"
    secret.write_text("SECRET")
    root = paths.backups_root() / "loadout-5"
    _manifest(root, [{"label": "x", "undo": {"restore-file": [str(root / "files" / "001-x"), str(fake_home / "dest")]}}])
    (root / "files").mkdir()
    (root / "files" / "001-x").symlink_to(secret)
    lines, ok, _ = backup.restore(root)
    assert not ok and not (fake_home / "dest").exists()


@pytest.mark.parametrize("cmd", [
    ["claude", "plugin", "marketplace", "add", "--scope"],
    ["claude", "plugin", "enable", "--scope", "--scope", "user"],
    ["codex", "plugin", "remove", "-s"],
])
def test_options_never_fill_a_name_slot(cmd):
    assert backup._allowed_run(cmd) is False


def test_restore_list_hides_symlinked_entries(fake_home):
    outside = fake_home / "outside"
    _manifest(outside, [])
    paths.backups_root().mkdir(parents=True, exist_ok=True)
    (paths.backups_root() / "link").symlink_to(outside)
    assert not any("link" in row for row in backup.list_backups())


def test_an_empty_run_step_gets_the_clear_refusal():
    assert backup._allowed_run([]) is False
