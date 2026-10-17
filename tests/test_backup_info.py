"""Backups as data for the restore picker (spec Part 6)."""
import json

from loadout import backup, paths

NOW = 2_000_000_000.0


def make(desc, ago, repo=None, steps=()):
    bk = backup.Backup(description=desc, repo=repo)
    bk._created_at = NOW - ago
    for kind, arg in steps:
        if kind == "copy":
            bk.save_copy(arg, f"{arg.name} before")
        elif kind == "created":
            bk.record_created(arg, f"{arg.name} (created)")
        elif kind == "dir":
            bk.record_created_dir(arg, f"{arg.name}/")
        elif kind == "run":
            bk.record_command("plugin x", arg)
    if bk.empty:
        bk._ensure_root()  # its own folder: two backups in one second must not share one
        bk._save()
    return bk


def test_backups_are_newest_first_and_filtered_by_repo(fake_home, tmp_path):
    repo = tmp_path / "repo"
    make("old", 7200)
    make("new", 60, repo=repo)
    assert [b.description for b in backup.backups()] == ["new", "old"]
    assert [b.description for b in backup.backups(repo)] == ["new"]


def test_age_reads_like_a_person_says_it():
    assert backup.age(NOW - 5, NOW) == "just now"
    assert backup.age(NOW - 60, NOW) == "1 minute ago"
    assert backup.age(NOW - 7200, NOW) == "2 hours ago"
    assert backup.age(NOW - 3 * 86400, NOW) == "3 days ago"


def test_summary_and_where(fake_home, tmp_path):
    f = tmp_path / "a.json"
    f.write_text("{}")
    repo = tmp_path / "repo"
    make("x", 10, repo=repo, steps=[("copy", f), ("created", tmp_path / "b"), ("dir", tmp_path / "d"),
                                    ("run", ["claude", "plugin", "uninstall", "x"])])
    info = backup.backups()[0]
    assert backup.summary(info) == "2 files, 1 folder, 1 command"
    assert backup.where(info) == f"repo {repo}"
    make("y", 5)
    assert backup.where(backup.backups()[0]) == "home"


def test_contents_name_each_file_and_command_with_secrets_masked(fake_home, tmp_path):
    f = tmp_path / "a.json"
    f.write_text("{}")
    token = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
    make("x", 10, steps=[("copy", f), ("run", ["claude", "mcp", "add-json", "gh", '{"env":{"T":"' + token + '"}}'])])
    lines = backup.contents(backup.backups()[0])
    assert lines[0].startswith("run: claude mcp add-json gh") and token not in lines[0]
    assert lines[1].startswith(f"put back {f}")


def test_a_damaged_manifest_never_crashes(fake_home):
    root = paths.backups_root()
    for name, steps in (("loadout-1", "x"), ("loadout-2", [{"label": "odd", "undo": "x"}, {"label": "pair", "undo": {"restore-file": "x"}}])):
        (root / name).mkdir(parents=True)
        (root / name / "manifest.json").write_text(json.dumps({"description": name, "created_at": 1, "steps": steps}))
    infos = backup.backups()
    assert [b.description for b in infos] == ["loadout-2"]
    assert all(isinstance(l, str) for l in backup.contents(infos[0]))
    assert backup.summary(infos[0]) == "1 file"  # the damaged restore-file still counts; contents names it as unknown
