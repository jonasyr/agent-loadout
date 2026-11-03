"""The first-install snapshot: one private archive of the agent setup, and a restore that trusts nothing in it.

The archive holds config only (no transcripts or caches) and login data, so it is private (0600, in the backups
folder). Restore reads an archive that could be damaged or forged: it puts back only plain files, folders and
symlinks that stay inside one of the places a snapshot covers under HOME, and moves whatever it replaces into a
"pre-restore" backup first, so a restore can itself be undone.
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import stat
import sys
import tarfile
import time
import zlib
from dataclasses import dataclass
from pathlib import Path

from . import backup, paths, vscode
from .out import printable

MAX_FILE = 50 * 1024 * 1024  # a single file over this is left out (and named)
META = "snapshot.json"
PATTERN = "first-install-*.tar.gz"

# Folders left out, relative to the agent folder: caches, transcripts and logs, not setup.
CLAUDE_EXCLUDE = frozenset(
    ["projects", "cache", "plugins/cache", "plugins/marketplaces", "shell-snapshots", "todos", "statsig",
     "telemetry", "debug", "file-history", "ide", "session-env", "local", "downloads", "backups"])
CODEX_EXCLUDE = frozenset(
    ["sessions", "archived_sessions", "log", "logs", "cache", ".tmp", "tmp", "plugins/cache"])

_DRIVE = re.compile(r"^[A-Za-z]:")
_SHELL_FILES = (".bashrc", ".zshrc", ".profile", ".bash_profile", ".zprofile")


class _Damaged(Exception):
    """The archive cannot be read or is not one of loadout's snapshots."""


def _candidates() -> list[tuple[str | None, Path]]:
    """Every place a snapshot may cover, with the agent it belongs to (None: neither agent, always included)."""
    home = paths.home()
    xdg = os.environ.get("XDG_CONFIG_HOME", "")
    fish = (Path(xdg) if os.path.isabs(xdg) else home / ".config") / "fish"
    found: list[tuple[str | None, Path]] = [
        ("claude", paths.claude_home()), ("claude", paths.claude_json()), ("codex", paths.codex_home())]
    found += [(None, home / name) for name in _SHELL_FILES]
    found += [(None, fish / "config.fish"), (None, fish / "conf.d")]
    if sys.platform == "win32":
        for docs in (home / "Documents", home / "OneDrive" / "Documents"):
            for folder in ("PowerShell", "WindowsPowerShell"):
                found.append((None, docs / folder / "Microsoft.PowerShell_profile.ps1"))
    found.append((None, vscode._user_dir(home, sys.platform) / "settings.json"))
    return found


def _rel(path: Path) -> str | None:
    """The HOME-relative POSIX name of `path`, or None when it lies outside HOME."""
    try:
        return path.relative_to(paths.home()).as_posix()
    except ValueError:
        return None


def _exists(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def roots(agents: dict[str, bool]) -> list[Path]:
    """The existing places to snapshot: the chosen agents' config, shell startup files and VS Code user settings."""
    out: list[Path] = []
    for agent, path in _candidates():
        if agent is not None and not agents.get(agent):
            continue  # an agent that is off is never read
        if _rel(path) in (None, "") or not _exists(path) or path in out:
            continue
        out.append(path)
    return out


def _excluded(root: Path) -> frozenset[str]:
    if root == paths.claude_home():
        return CLAUDE_EXCLUDE
    if root == paths.codex_home():
        return CODEX_EXCLUDE
    return frozenset()


def _entries(root: Path, skipped: list[str], strict: bool = True):
    """(path, lstat) of the root and everything below it that goes into the archive. Excluded folders are never
    entered; a symlink is one entry, never followed; sockets, devices and fifos are left out."""
    excluded = _excluded(root)

    def visit(path: Path, rel: str):
        try:
            st = os.lstat(path)
            if stat.S_ISLNK(st.st_mode):
                yield path, st
            elif stat.S_ISDIR(st.st_mode):
                yield path, st
                with os.scandir(path) as it:
                    children = sorted(e.name for e in it)
                for name in children:
                    child = f"{rel}/{name}" if rel else name
                    if child not in excluded:
                        yield from visit(path / name, child)
            elif stat.S_ISREG(st.st_mode):
                if st.st_size > MAX_FILE:
                    skipped.append(f"skipped (over {MAX_FILE // (1024 * 1024)} MB): {_rel(path) or path}")
                else:
                    yield path, st
        except FileNotFoundError:
            return  # gone while walking
        except OSError:
            if strict:
                raise

    yield from visit(root, "")


def estimate(roots: list[Path]) -> int:
    """Bytes that would be archived (file sizes, before compression)."""
    total = 0
    for root in roots:
        for _, st in _entries(root, [], strict=False):
            if stat.S_ISREG(st.st_mode):
                total += st.st_size
    return total


def _version() -> str:
    try:
        text = (paths.kit_root() / "pyproject.toml").read_text(encoding="utf-8")
        return re.search(r'^version = "([^"]+)"', text, re.M).group(1)
    except (OSError, AttributeError):
        return "unknown"


def _anonymous(info: tarfile.TarInfo) -> tarfile.TarInfo:
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    return info


def create(roots: list[Path], agents: dict[str, bool]) -> Path:
    """Write the archive into the backups folder and return it. Any failure removes the partial file and raises
    OSError."""
    folder = paths.backups_root()
    skipped: list[str] = []
    archive: Path | None = None
    try:
        entries = [(path, _rel(path)) for root in roots for path, _ in _entries(root, skipped)]
        entries = [(p, name) for p, name in entries if name]
        folder.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            os.chmod(folder, backup.PRIVATE_DIR)  # the archive holds login data
        stamp = time.strftime("%Y%m%d-%H%M%S")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        n = 1
        while True:
            candidate = folder / f"first-install-{stamp}{'' if n == 1 else f'-{n}'}.tar.gz"
            try:
                fd = os.open(candidate, flags, backup.PRIVATE_FILE)
            except FileExistsError:
                n += 1
                continue
            archive = candidate
            break
        meta = json.dumps({"roots": [name for name in (_rel(r) for r in roots) if name], "agents": dict(agents),
                           "created": time.time(), "version": _version(), "skipped": skipped},
                          indent=2).encode("utf-8")
        with os.fdopen(fd, "wb") as raw, tarfile.open(fileobj=raw, mode="w:gz") as tar:
            info = tarfile.TarInfo(META)
            info.size, info.mode, info.mtime = len(meta), 0o600, int(time.time())
            tar.addfile(info, io.BytesIO(meta))
            for path, name in entries:
                tar.inodes.clear()  # a second link to one file is stored as a file, never as a hard-link member
                tar.add(path, arcname=name, recursive=False, filter=_anonymous)
        if os.name != "nt":
            os.chmod(archive, backup.PRIVATE_FILE)
        return archive
    except BaseException as exc:
        if archive is not None:
            try:
                archive.unlink()
            except OSError:
                pass
        if isinstance(exc, (tarfile.TarError, zlib.error, ValueError)):
            raise OSError(str(exc)) from exc
        raise


def latest() -> Path | None:
    """The newest first-install snapshot in the backups folder."""
    found = [p for p in paths.backups_root().glob(PATTERN) if p.is_file() and not p.is_symlink()]
    return max(found, key=lambda p: p.name, default=None)


# --- reading an archive that may be damaged or forged -------------------------------------------------------

@dataclass
class _Plan:
    meta: dict
    safe: list[tuple[tarfile.TarInfo, tuple[str, ...], int]]  # member, its name parts, length of the root it is under
    refused: list[str]


def _parts(name) -> tuple[str, ...] | None:
    """The path parts of a member name, or None when the name is not a plain relative POSIX path."""
    if not isinstance(name, str) or not name or "\x00" in name or "\\" in name or name.startswith("/") \
            or _DRIVE.match(name):
        return None
    parts = tuple(name.split("/"))
    return None if any(p in ("", ".", "..") for p in parts) else parts


def _plan(tar: tarfile.TarFile) -> _Plan:
    try:
        members = tar.getmembers()  # reads the whole listing: a truncated archive fails here, before any change
    except (tarfile.TarError, OSError, EOFError, zlib.error, ValueError) as exc:
        raise _Damaged(f"is damaged ({exc})") from exc
    meta_info = next((m for m in members if m.name == META and m.isreg()), None)
    if meta_info is None or meta_info.size > 1_000_000:
        raise _Damaged(f"is not one of loadout's snapshots ({META} is missing)")
    try:
        meta = json.loads(tar.extractfile(meta_info).read().decode("utf-8"))
    except (tarfile.TarError, OSError, EOFError, zlib.error, ValueError) as exc:
        raise _Damaged(f"is damaged ({META}: {exc})") from exc
    if not isinstance(meta, dict) or not isinstance(meta.get("roots"), list):
        raise _Damaged(f"is not one of loadout's snapshots ({META} has no roots)")
    agents = meta.get("agents") if isinstance(meta.get("agents"), dict) else {}
    allowed = {_rel(path): agent for agent, path in _candidates() if _rel(path)}
    refused: list[str] = []
    root_parts: list[tuple[str, ...]] = []
    for root in meta["roots"]:
        parts = _parts(root)
        if parts is None or root not in allowed or (allowed[root] is not None and not agents.get(allowed[root])):
            refused.append(f"refused: root {printable(str(root))!r} is not a place a snapshot covers")
        else:
            root_parts.append(parts)
    safe, links = [], set()
    for info in members:
        if info.name == META:
            continue
        parts = _parts(info.name)
        reason = None
        if parts is None:
            reason = "not a plain relative path"
        elif info.islnk():
            reason = "a hard link"
        elif not (info.isreg() or info.isdir() or info.issym()):
            reason = "not a plain file, folder or symlink"
        elif info.issym() and (not info.linkname or "\x00" in info.linkname):
            reason = "a symlink without a target"
        else:
            under = next((len(r) for r in root_parts if parts[:len(r)] == r), None)
            if under is None:
                reason = "outside the places this snapshot covers"
            elif any(parts[:i] in links for i in range(1, len(parts))):
                reason = "inside a symlink"
        if reason:
            refused.append(f"refused: {printable(info.name)}: {reason}")
            continue
        if info.issym():
            links.add(parts)
        safe.append((info, parts, under))
    return _Plan(meta, safe, refused)


def _open(archive: Path) -> tarfile.TarFile:
    if not archive.is_file():
        raise _Damaged("is missing" if not _exists(archive) else "is not a file")
    try:
        return tarfile.open(archive, "r:gz")
    except (tarfile.TarError, OSError, EOFError, zlib.error) as exc:
        raise _Damaged(f"is damaged or not an archive ({exc})") from exc


def contents(archive: Path) -> list[str]:
    """The HOME-relative names a restore would put back (files and symlinks), after the safety checks."""
    try:
        with _open(archive) as tar:
            return ["/".join(parts) for info, parts, _ in _plan(tar).safe if not info.isdir()]
    except _Damaged:
        return []


def skipped(archive: Path) -> list[str]:
    """The lines about files left out of this snapshot (too big)."""
    try:
        with _open(archive) as tar:
            lines = _plan(tar).meta.get("skipped")
    except _Damaged:
        return []
    return [printable(str(x)) for x in lines] if isinstance(lines, list) else []


def _mode(info: tarfile.TarInfo) -> int:
    mode = (info.mode & 0o777) & ~0o022 | 0o600
    if info.isdir():
        return mode | 0o700
    return mode if mode & 0o100 else mode & ~0o111


def _extract(tar: tarfile.TarFile, info: tarfile.TarInfo, dest: Path) -> None:
    """One regular file or folder, already checked. The data filter does the work where Python has it (3.12+);
    the same rules are applied by hand otherwise."""
    if hasattr(tarfile, "data_filter"):
        tar.extract(info, path=paths.home(), set_attrs=True, filter="data")
        return
    if info.isdir():
        dest.mkdir(exist_ok=True)
    else:
        with tar.extractfile(info) as src, open(dest, "xb") as out:
            shutil.copyfileobj(src, out)
        os.utime(dest, (info.mtime, info.mtime))
    if os.name != "nt":
        os.chmod(dest, _mode(info))


def _parent_link(home: Path, parts: tuple[str, ...], under: int) -> Path | None:
    """A symlink on disk between the snapshot's root (included) and the member: writing through it could leave HOME."""
    for i in range(under, len(parts)):
        folder = home.joinpath(*parts[:i])
        if folder.is_symlink():
            return folder
    return None


def restore(archive: Path) -> tuple[list[str], bool, Path | None]:
    """Put the snapshot back. Returns (messages, all_ok, pre-restore backup root), like backup.restore.

    Nothing changes unless the whole archive reads cleanly. Each file or link it covers that exists now is first
    moved into a pre-restore backup; files the archive does not hold stay where they are."""
    try:
        tar = _open(archive)
    except _Damaged as exc:
        return [f"failed: the snapshot {archive} {exc}"], False, None
    with tar:
        try:
            plan = _plan(tar)
            for info, _, _ in plan.safe:  # read every file once: damage shows now, not after files were moved
                if info.isreg():
                    with tar.extractfile(info) as src:
                        while src.read(1 << 20):
                            pass
        except (tarfile.TarError, OSError, EOFError, zlib.error, ValueError) as exc:
            return [f"failed: the snapshot {archive} is damaged ({exc}); nothing was changed"], False, None
        except _Damaged as exc:
            return [f"failed: the snapshot {archive} {exc}"], False, None
        home, pre = paths.home(), backup.Backup(description="pre-restore first-install")
        lines, failed, done = list(plan.refused), len(plan.refused), 0
        for info, parts, under in plan.safe:
            dest, name = home.joinpath(*parts), printable("/".join(parts))
            try:
                link = _parent_link(home, parts, under)
                if link is not None:
                    lines.append(f"refused: {name}: {printable(str(link))} is a symlink")
                    failed += 1
                    continue
                if _exists(dest) and not (info.isdir() and dest.is_dir() and not dest.is_symlink()):
                    pre.move(dest, f"{dest} before restore", replace=True)
                dest.parent.mkdir(parents=True, exist_ok=True)
                if info.issym():
                    os.symlink(info.linkname, dest)
                    pre.record_created(dest, f"{dest} (from the snapshot)")
                elif info.isdir():
                    if not dest.is_dir():
                        _extract(tar, info, dest)
                        pre.record_created_dir(dest, f"{dest} (from the snapshot)")
                else:
                    _extract(tar, info, dest)
                    pre.record_created(dest, f"{dest} (from the snapshot)")
                done += 1
            except (tarfile.TarError, OSError) as exc:
                lines.append(f"failed: {name}: {printable(str(exc))}")
                failed += 1
        lines.append(f"restored {done} item(s) from {archive}")
        if not pre.empty:
            lines.append("what was there before is in the pre-restore backup")
        return lines, failed == 0, (None if pre.empty else pre.root)
