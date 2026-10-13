"""A backup taken before ADR 0025 restores after the move, and never recreates ~/.claude/.loadout."""
import json

from loadout import backup, migrate, paths


def _old_backup(fake_home):
    """A manifest exactly as an old run wrote it: absolute paths under ~/.claude/backups and ~/.claude/.loadout."""
    root = paths.legacy_backups_root() / "loadout-old"
    files = root / "files"
    files.mkdir(parents=True)
    (files / "codex-config.json").write_text('{"old": true}')
    (files / "settings.json").write_text('{"moved": true}')
    state = paths.legacy_state_dir()
    state.mkdir(parents=True)
    (state / "codex-config.json").write_text('{"current": true}')
    (state / "made.json").write_text("{}")
    target = fake_home / ".claude" / "settings.json"
    steps = [
        {"label": "codex-config", "undo": {"restore-file": [str(files / "codex-config.json"), str(state / "codex-config.json")]}},
        {"label": "made", "undo": {"created": str(state / "made.json")}},
        {"label": "settings", "undo": {"move": [str(files / "settings.json"), str(target)]}},
    ]
    (root / "manifest.json").write_text(json.dumps({"description": "old", "created_at": 1, "steps": steps}))
    return root


def test_old_backup_restores_into_the_new_state_dir(fake_home):
    old_root = _old_backup(fake_home)
    migrate.migrate_state()
    lines, ok, _ = backup.restore(paths.backups_root() / old_root.name)
    assert ok, lines
    assert json.loads((paths.state_dir() / "codex-config.json").read_text()) == {"old": True}
    assert not (paths.state_dir() / "made.json").exists()  # created file moved aside
    assert json.loads((fake_home / ".claude" / "settings.json").read_text()) == {"moved": True}
    assert not paths.legacy_state_dir().exists() and not paths.legacy_backups_root().exists()


def test_old_printed_restore_path_still_works(fake_home):
    old_root = _old_backup(fake_home)
    migrate.migrate_state()
    lines, ok, _ = backup.restore(old_root)  # ~/.claude/backups/loadout-old, as an old message printed it
    assert ok, lines


def test_paths_outside_both_roots_are_not_mapped(fake_home):
    other = str(fake_home / "elsewhere" / "x")
    assert backup._map_legacy(other) == other
    legacy = str(paths.legacy_backups_root() / "b" / "files" / "y")
    assert backup._map_legacy(legacy) == str(paths.backups_root() / "b" / "files" / "y")


def test_a_mapped_source_outside_files_is_still_refused(fake_home):
    root = paths.backups_root() / "b"
    (root / "files").mkdir(parents=True)
    escape = str(paths.legacy_backups_root() / "b" / "manifest.json")  # maps inside the backup, not inside files/
    (root / "manifest.json").write_text(json.dumps({"steps": [
        {"label": "x", "undo": {"move": [escape, str(fake_home / "t")]}}]}))
    lines, ok, _ = backup.restore(root)
    assert not ok and any("not inside" in line for line in lines)
