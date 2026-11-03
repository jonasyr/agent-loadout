"""The first-install snapshot: what goes in, what stays out, and a restore that trusts nothing in the archive."""
from __future__ import annotations

import io
import json
import os
import stat
import sys
import tarfile
from pathlib import Path

import pytest

from loadout import paths, snapshot

BOTH = {"claude": True, "codex": True}
POSIX = pytest.mark.skipif(os.name == "nt", reason="POSIX file modes and symlinks")


def write(path: Path, text: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def names(archive: Path) -> list[str]:
    with tarfile.open(archive) as tar:
        return tar.getnames()


def forged(tmp_path: Path, members: list, roots=(".claude",), agents=None) -> Path:
    """An archive built by hand: members are (TarInfo, bytes | None); snapshot.json lists `roots`."""
    archive = tmp_path / "forged.tar.gz"
    meta = json.dumps({"roots": list(roots), "agents": agents or BOTH, "created": 1, "version": "0"}).encode()
    with tarfile.open(archive, "w:gz") as tar:
        info = tarfile.TarInfo("snapshot.json")
        info.size = len(meta)
        tar.addfile(info, io.BytesIO(meta))
        for info, data in members:
            tar.addfile(info, io.BytesIO(data) if data is not None else None)
    return archive


def member(name: str, data: bytes = b"evil", type=tarfile.REGTYPE, link: str = "") -> tuple:
    info = tarfile.TarInfo(name)
    info.type = type
    info.linkname = link
    info.size = len(data) if type == tarfile.REGTYPE else 0
    info.mode = 0o644
    return info, (data if type == tarfile.REGTYPE else None)


def test_roots_follow_agents_and_include_shell_files(fake_home):
    write(fake_home / ".claude" / "settings.json")
    write(fake_home / ".claude.json")
    write(fake_home / ".codex" / "config.toml")
    write(fake_home / ".bashrc")
    write(fake_home / ".zshrc")
    write(fake_home / ".config" / "fish" / "conf.d" / "a.fish")
    write(fake_home / ".config" / "Code" / "User" / "settings.json")
    both = {p.relative_to(fake_home).as_posix() for p in snapshot.roots(BOTH)}
    assert {".claude", ".claude.json", ".codex", ".bashrc", ".zshrc", ".config/fish/conf.d",
            ".config/Code/User/settings.json"} <= both
    claude_only = {p.relative_to(fake_home).as_posix() for p in snapshot.roots({"claude": True, "codex": False})}
    assert ".codex" not in claude_only and ".claude" in claude_only and ".bashrc" in claude_only
    codex_only = {p.relative_to(fake_home).as_posix() for p in snapshot.roots({"claude": False, "codex": True})}
    assert ".claude" not in codex_only and ".claude.json" not in codex_only and ".codex" in codex_only
    assert snapshot.roots({"claude": False, "codex": False}) == [fake_home / p for p in
                                                                 (".bashrc", ".zshrc", ".config/fish/conf.d",
                                                                  ".config/Code/User/settings.json")]


def test_roots_skip_what_does_not_exist(fake_home):
    assert snapshot.roots(BOTH) == []


def test_excluded_folders_are_not_walked(fake_home, monkeypatch):
    write(fake_home / ".claude" / "settings.json", "keep")
    for skipped in ("projects", "cache", "plugins/cache", "plugins/marketplaces", "shell-snapshots", "todos",
                    "statsig", "telemetry", "debug", "file-history", "ide", "session-env", "local", "downloads",
                    "backups"):
        write(fake_home / ".claude" / skipped / "deep" / "f.jsonl", "big")
    write(fake_home / ".claude" / "plugins" / "installed.json", "keep")
    for skipped in ("sessions", "archived_sessions", "log", "logs", "cache", ".tmp", "tmp", "plugins/cache"):
        write(fake_home / ".codex" / skipped / "f", "big")
    write(fake_home / ".codex" / "auth.json", "login")
    scanned = []
    real = os.scandir

    def counting(path):
        scanned.append(Path(path))
        return real(path)
    monkeypatch.setattr(os, "scandir", counting)
    roots = snapshot.roots(BOTH)
    snapshot.estimate(roots)
    archive = snapshot.create(roots, BOTH)
    for folder in scanned:
        rel = folder.relative_to(fake_home).as_posix()
        assert not any(rel == f".claude/{s}" or rel.startswith(f".claude/{s}/") for s in
                       ("projects", "cache", "plugins/cache", "plugins/marketplaces", "shell-snapshots", "todos",
                        "statsig", "telemetry", "debug", "file-history", "ide", "session-env", "local", "downloads",
                        "backups")), rel
        assert not rel.startswith((".codex/sessions", ".codex/logs", ".codex/plugins/cache", ".codex/tmp",
                                   ".codex/.tmp", ".codex/cache", ".codex/log", ".codex/archived_sessions")), rel
    listed = names(archive)
    assert ".claude/settings.json" in listed and ".claude/plugins/installed.json" in listed
    assert ".codex/auth.json" in listed
    assert not any("deep" in n or n.startswith((".claude/projects", ".codex/sessions")) for n in listed)


def test_estimate_counts_bytes_without_the_excluded(fake_home):
    write(fake_home / ".claude" / "settings.json", "12345")
    write(fake_home / ".claude" / "projects" / "t.jsonl", "x" * 1000)
    assert snapshot.estimate(snapshot.roots(BOTH)) == 5


def test_create_is_private_and_lists_roots(fake_home):
    write(fake_home / ".claude.json", '{"token": "secret"}')
    write(fake_home / ".claude" / "settings.json")
    archive = snapshot.create(snapshot.roots(BOTH), BOTH)
    assert archive.parent == paths.backups_root()
    assert archive.name.startswith("first-install-") and archive.name.endswith(".tar.gz")
    if os.name != "nt":
        assert stat.S_IMODE(archive.stat().st_mode) == 0o600
        assert stat.S_IMODE(archive.parent.stat().st_mode) == 0o700
    with tarfile.open(archive) as tar:
        meta = json.load(tar.extractfile("snapshot.json"))
    assert set(meta["roots"]) == {".claude", ".claude.json"}
    assert meta["agents"] == BOTH and meta["created"] and "version" in meta
    assert snapshot.latest() == archive


def test_latest_is_the_newest_and_none_without(fake_home):
    assert snapshot.latest() is None
    root = paths.backups_root()
    root.mkdir(parents=True)
    old, new = root / "first-install-20260101-000000.tar.gz", root / "first-install-20260202-000000.tar.gz"
    old.write_bytes(b"")
    new.write_bytes(b"")
    (root / "loadout-20260303-000000").mkdir()
    assert snapshot.latest() == new


@POSIX
def test_symlinks_stored_as_links(fake_home):
    outside = fake_home / "dotfiles" / "skills"
    write(outside / "a.md", "secret outside the roots")
    write(fake_home / ".claude" / "settings.json")
    os.symlink(outside, fake_home / ".claude" / "skills")
    archive = snapshot.create(snapshot.roots(BOTH), BOTH)
    with tarfile.open(archive) as tar:
        link = tar.getmember(".claude/skills")
        assert link.issym() and link.linkname == str(outside)
    assert not any(n.startswith(".claude/skills/") for n in names(archive))


@POSIX
def test_sockets_and_fifos_are_skipped(fake_home):
    write(fake_home / ".claude" / "settings.json")
    os.mkfifo(fake_home / ".claude" / "pipe")
    assert ".claude/pipe" not in names(snapshot.create(snapshot.roots(BOTH), BOTH))


def test_big_file_skipped_with_a_line(fake_home, monkeypatch):
    monkeypatch.setattr(snapshot, "MAX_FILE", 10)
    write(fake_home / ".claude" / "settings.json", "small")
    write(fake_home / ".claude" / "huge.bin", "x" * 50)
    archive = snapshot.create(snapshot.roots(BOTH), BOTH)
    assert ".claude/huge.bin" not in names(archive) and ".claude/settings.json" in names(archive)
    assert any("huge.bin" in line for line in snapshot.skipped(archive))
    assert snapshot.estimate(snapshot.roots(BOTH)) == 5


def test_member_names_are_posix(fake_home):
    write(fake_home / ".claude" / "skills" / "a" / "SKILL.md")
    for name in names(snapshot.create(snapshot.roots(BOTH), BOTH)):
        assert "\\" not in name and not name.startswith("/") and ".." not in name.split("/")


def test_create_failure_removes_the_partial_archive(fake_home, monkeypatch):
    write(fake_home / ".claude" / "settings.json")

    def boom(*a, **k):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(tarfile.TarFile, "add", boom)
    with pytest.raises(OSError):
        snapshot.create(snapshot.roots(BOTH), BOTH)
    assert list(paths.backups_root().glob("first-install-*")) == []


def test_restore_puts_files_back_and_moves_current_aside(fake_home):
    settings = write(fake_home / ".claude" / "settings.json", "original")
    login = write(fake_home / ".claude.json", '{"login": 1}')
    bashrc = write(fake_home / ".bashrc", "export A=1\n")
    projects = write(fake_home / ".claude" / "projects" / "p" / "t.jsonl", "transcript")
    archive = snapshot.create(snapshot.roots(BOTH), BOTH)
    settings.write_text("changed by loadout")
    login.write_text('{"login": 2}')
    bashrc.write_text("export A=1\n# loadout\n")
    new = write(fake_home / ".claude" / "added-later.md", "kept")
    lines, ok, pre = snapshot.restore(archive)
    assert ok, lines
    assert settings.read_text() == "original" and login.read_text() == '{"login": 1}'
    assert bashrc.read_text() == "export A=1\n"
    assert projects.read_text() == "transcript"  # excluded folders are never touched
    assert not new.exists()  # added since the snapshot: moved aside, not deleted
    assert pre is not None and pre.parent == paths.backups_root()
    moved = {p.read_text() for p in (pre / "files").iterdir()}
    assert {"changed by loadout", '{"login": 2}', "export A=1\n# loadout\n"} <= moved


def test_restore_is_itself_undoable(fake_home):
    from loadout import backup
    settings = write(fake_home / ".claude" / "settings.json", "original")
    archive = snapshot.create(snapshot.roots(BOTH), BOTH)
    settings.write_text("changed")
    _, ok, pre = snapshot.restore(archive)
    assert ok and settings.read_text() == "original"
    lines, ok2, _ = backup.restore(pre)
    assert ok2, lines
    assert settings.read_text() == "changed"


def test_restore_without_current_files_creates_them(fake_home):
    write(fake_home / ".claude" / "skills" / "a" / "SKILL.md", "s")
    archive = snapshot.create(snapshot.roots(BOTH), BOTH)
    import shutil
    shutil.rmtree(fake_home / ".claude")
    lines, ok, pre = snapshot.restore(archive)
    assert ok, lines
    assert (fake_home / ".claude" / "skills" / "a" / "SKILL.md").read_text() == "s"


@POSIX
def test_restore_keeps_modes_and_symlinks(fake_home):
    secret = write(fake_home / ".claude.json", "login")
    secret.chmod(0o600)
    write(fake_home / ".claude" / "settings.json")
    os.symlink("/some/where", fake_home / ".claude" / "link")
    archive = snapshot.create(snapshot.roots(BOTH), BOTH)
    secret.unlink()
    (fake_home / ".claude" / "link").unlink()
    _, ok, _ = snapshot.restore(archive)
    assert ok and stat.S_IMODE(secret.stat().st_mode) == 0o600
    assert os.readlink(fake_home / ".claude" / "link") == "/some/where"


def test_contents_lists_what_would_be_restored(fake_home):
    write(fake_home / ".claude" / "a" / "settings.json")
    write(fake_home / ".claude.json")
    got = snapshot.contents(snapshot.create(snapshot.roots(BOTH), BOTH))
    assert ".claude/a/settings.json" in got and ".claude.json" in got and "snapshot.json" not in got


@POSIX
@pytest.mark.parametrize("use_filter", [True, False])
def test_restore_refuses_members_outside_home(fake_home, tmp_path, monkeypatch, use_filter):
    if not use_filter:
        monkeypatch.delattr(tarfile, "data_filter", raising=False)  # Python 3.11 has no extraction filter
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    victim = write(tmp_path / "victim.txt", "mine")
    members = [
        member(".claude/ok.md", b"fine"),
        member(".claude/../../victim.txt", b"pwned"),
        member("../victim.txt", b"pwned"),
        member(f"{elsewhere}/x", b"pwned"),
        member("/etc/loadout-test-x", b"pwned"),
        member(".claude/hard", type=tarfile.LNKTYPE, link="/etc/passwd"),
        member(".claude/hard2", type=tarfile.LNKTYPE, link=".claude/ok.md"),
        member(".claude/dev", type=tarfile.CHRTYPE),
        member(".claude/blk", type=tarfile.BLKTYPE),
        member(".claude/fifo", type=tarfile.FIFOTYPE),
        member(".claude\\win", b"pwned"),
        member(".bashrc-not-a-root", b"pwned"),
        member(".claude/sneaky", type=tarfile.SYMTYPE, link=str(elsewhere)),
        member(".claude/sneaky/escaped.txt", b"pwned"),
    ]
    archive = forged(tmp_path, members)
    lines, ok, _ = snapshot.restore(archive)
    assert not ok
    assert (fake_home / ".claude" / "ok.md").read_text() == "fine"
    assert victim.read_text() == "mine"
    assert not (elsewhere / "escaped.txt").exists() and not (elsewhere / "x").exists()
    assert not Path("/etc/loadout-test-x").exists()
    for bad in ("hard", "hard2", "dev", "blk", "fifo", "win", "not-a-root"):
        assert not (fake_home / ".claude" / bad).exists()
    assert not (fake_home / ".bashrc-not-a-root").exists()
    assert sum(1 for line in lines if line.startswith("refused")) >= 10
    assert snapshot.contents(archive) == [".claude/ok.md"]  # a link is listed apart (links_in), not as put back


def test_restore_refuses_a_root_it_would_not_have_chosen(fake_home, tmp_path):
    victim = fake_home / ".ssh" / "authorized_keys"
    archive = forged(tmp_path, [member(".ssh/authorized_keys", b"attacker key")], roots=(".ssh", ".", "..", "/etc"))
    lines, ok, _ = snapshot.restore(archive)
    assert not ok and not victim.exists()
    assert any("refused" in line for line in lines)


def test_restore_never_reaches_an_agent_that_was_off(fake_home, tmp_path):
    archive = forged(tmp_path, [member(".codex/config.toml", b"x")], roots=(".claude",), agents={"claude": True, "codex": False})
    lines, ok, _ = snapshot.restore(archive)
    assert not ok and not (fake_home / ".codex").exists()


def test_restore_of_a_missing_or_corrupt_archive_says_so(fake_home, tmp_path):
    lines, ok, pre = snapshot.restore(tmp_path / "nope.tar.gz")
    assert not ok and pre is None and "nope.tar.gz" in " ".join(lines)
    junk = tmp_path / "junk.tar.gz"
    junk.write_bytes(b"this is not an archive")
    lines, ok, pre = snapshot.restore(junk)
    assert not ok and pre is None and lines
    assert snapshot.contents(junk) == []


def test_restore_of_a_truncated_archive_changes_nothing(fake_home):
    settings = write(fake_home / ".claude" / "settings.json", "original")
    write(fake_home / ".claude" / "big.txt", "".join(chr(65 + i % 26) * 7 for i in range(40000)))
    archive = snapshot.create(snapshot.roots(BOTH), BOTH)
    data = archive.read_bytes()
    archive.write_bytes(data[: len(data) // 2])
    settings.write_text("changed")
    lines, ok, pre = snapshot.restore(archive)
    assert not ok and pre is None and settings.read_text() == "changed"


def test_archive_without_snapshot_json_is_refused(fake_home, tmp_path):
    archive = tmp_path / "plain.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        info = tarfile.TarInfo(".claude/x")
        info.size = 1
        tar.addfile(info, io.BytesIO(b"x"))
    lines, ok, pre = snapshot.restore(archive)
    assert not ok and pre is None and not (fake_home / ".claude" / "x").exists()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX")
def test_hard_links_in_the_source_are_stored_as_files(fake_home):
    a = write(fake_home / ".claude" / "a.md", "same")
    os.link(a, fake_home / ".claude" / "b.md")
    with tarfile.open(snapshot.create(snapshot.roots(BOTH), BOTH)) as tar:
        assert tar.getmember(".claude/b.md").isreg()


def test_restore_moves_aside_what_the_install_added(fake_home):
    write(fake_home / ".claude" / "settings.json", "original")
    write(fake_home / ".claude" / "projects" / "p" / "t.jsonl", "transcript")
    write(fake_home / ".claude" / "plugins" / "cache" / "c.json", "cache")
    archive = snapshot.create(snapshot.roots(BOTH), BOTH)
    rule = write(fake_home / ".claude" / "rules" / "loadout.md", "rule")  # a whole folder added since
    plugins = write(fake_home / ".claude" / "plugins" / "known.json", "m")  # inside a folder with excluded parts
    zshrc = write(fake_home / ".zshrc", "# loadout")  # a root that did not exist
    codex = write(fake_home / ".codex" / "config.toml", "x")  # Codex was on but had no folder
    write(fake_home / ".codex" / "sessions" / "s.jsonl", "session")
    assert set(snapshot.moved_aside(archive)) == {".claude/rules", ".claude/plugins/known.json", ".zshrc",
                                                  ".codex/config.toml"}
    lines, ok, pre = snapshot.restore(archive)
    assert ok, lines
    for gone in (rule, plugins, zshrc, codex):
        assert not gone.exists()
    assert (fake_home / ".claude" / "projects" / "p" / "t.jsonl").read_text() == "transcript"
    assert (fake_home / ".claude" / "plugins" / "cache" / "c.json").read_text() == "cache"
    assert (fake_home / ".codex" / "sessions" / "s.jsonl").read_text() == "session"
    assert (fake_home / ".claude" / "settings.json").read_text() == "original"
    kept = {p.name.split("-", 1)[1] for p in (pre / "files").iterdir()}
    assert {"rules", "known.json", ".zshrc", "config.toml"} <= kept


def test_added_since_is_undone_with_the_pre_restore_backup(fake_home):
    from loadout import backup
    write(fake_home / ".claude" / "settings.json", "original")
    archive = snapshot.create(snapshot.roots(BOTH), BOTH)
    rule = write(fake_home / ".claude" / "rules" / "r.md", "rule")
    _, ok, pre = snapshot.restore(archive)
    assert ok and not rule.exists()
    lines, ok2, _ = backup.restore(pre)
    assert ok2, lines
    assert rule.read_text() == "rule"


def test_codex_off_its_folder_is_not_touched_by_restore(fake_home):
    write(fake_home / ".claude" / "settings.json", "original")
    off = {"claude": True, "codex": False}
    archive = snapshot.create(snapshot.roots(off), off)
    mine = write(fake_home / ".codex" / "config.toml", "mine")
    lines, ok, _ = snapshot.restore(archive)
    assert ok, lines
    assert mine.read_text() == "mine"


def test_big_file_skipped_at_snapshot_is_not_moved_aside(fake_home, monkeypatch):
    monkeypatch.setattr(snapshot, "MAX_FILE", 10)
    write(fake_home / ".claude" / "settings.json", "small")
    huge = write(fake_home / ".claude" / "huge.bin", "x" * 50)
    archive = snapshot.create(snapshot.roots(BOTH), BOTH)
    _, ok, _ = snapshot.restore(archive)
    assert ok and huge.exists()


@POSIX
@pytest.mark.parametrize("use_filter", [True, False])
def test_restore_through_a_symlinked_config_folder(fake_home, tmp_path, monkeypatch, use_filter):
    if not use_filter:
        monkeypatch.delattr(tarfile, "data_filter", raising=False)
    dotfiles = tmp_path / "dotfiles" / "config"
    fish = write(dotfiles / "fish" / "config.fish", "original")
    os.symlink(dotfiles, fake_home / ".config")
    archive = snapshot.create(snapshot.roots(BOTH), BOTH)
    fish.write_text("changed")
    lines, ok, pre = snapshot.restore(archive)
    assert ok, lines
    assert fish.read_text() == "original"
    assert pre is not None


@POSIX
def test_a_failed_extract_leaves_the_current_file_in_place(fake_home, monkeypatch):
    settings = write(fake_home / ".claude" / "settings.json", "original")
    archive = snapshot.create(snapshot.roots(BOTH), BOTH)
    settings.write_text("current")

    def boom(*a, **k):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(snapshot, "_extract", boom)
    lines, ok, _ = snapshot.restore(archive)
    assert not ok and settings.read_text() == "current"
    assert not [p for p in settings.parent.iterdir() if p.name.startswith(".loadout-restore-")]


@POSIX
def test_a_refused_member_leaves_the_current_file_in_place(fake_home, tmp_path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    os.symlink(elsewhere, fake_home / ".claude")  # the root itself is a link out of HOME
    target = write(elsewhere / "f.txt", "mine")
    archive = forged(tmp_path, [member(".claude/f.txt", b"new")])
    lines, ok, _ = snapshot.restore(archive)
    assert not ok and target.read_text() == "mine"
