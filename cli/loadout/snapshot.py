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
import uuid
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
                    skipped.append(_rel(path) or str(path))
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


def create(roots: list[Path], agents: dict[str, bool], first: bool = True) -> Path:
    """Write the archive into the backups folder and return it (`first`: the first-install one, else a later `snapshot-`). Any failure removes the partial file and raises
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
            candidate = folder / f"{'first-install' if first else 'snapshot'}-{stamp}{'' if n == 1 else f'-{n}'}.tar.gz"
            try:
                fd = os.open(candidate, flags, backup.PRIVATE_FILE)
            except FileExistsError:
                n += 1
                continue
            archive = candidate
            break
        chosen = {_rel(r) for r in roots}
        absent = [name for agent, path in _candidates() for name in [_rel(path)]
                  if name and name not in chosen and (agent is None or agents.get(agent)) and not _exists(path)]
        lines = [f"skipped (over {MAX_FILE // (1024 * 1024)} MB): {name}" for name in skipped]
        meta = json.dumps({"roots": [name for name in (_rel(r) for r in roots) if name], "absent": absent,
                           "agents": dict(agents), "created": time.time(), "version": _version(),
                           "skipped": lines, "skipped_names": skipped}, indent=2).encode("utf-8")
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


def first() -> Path | None:
    """The oldest first-install snapshot: the state before loadout's first install (later snapshots are `snapshot-*`)."""
    found = [p for p in paths.backups_root().glob(PATTERN) if p.is_file() and not p.is_symlink()]
    return min(found, key=lambda p: p.name, default=None)


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
    roots: list[tuple[str, ...]]  # the places the snapshot covered and found
    absent: list[tuple[str, ...]]  # the places it covered that did not exist yet
    skipped: set[tuple[str, ...]]  # files left out for size: not "added since"


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

    def valid(listed) -> list[tuple[str, ...]]:
        out = []
        for root in listed if isinstance(listed, list) else []:
            parts = _parts(root)
            if parts is None or root not in allowed or (allowed[root] is not None and not agents.get(allowed[root])):
                refused.append(f"refused: root {printable(str(root))!r} is not a place a snapshot covers")
            else:
                out.append(parts)
        return out
    root_parts, absent_parts = valid(meta["roots"]), valid(meta.get("absent"))
    names = meta.get("skipped_names")
    skipped_parts = {p for p in (_parts(n) for n in names if isinstance(n, str)) if p} if isinstance(names, list) else set()
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
    return _Plan(meta, safe, refused, root_parts, absent_parts, skipped_parts)


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


def _extract(tar: tarfile.TarFile, info: tarfile.TarInfo, tmp: Path) -> None:
    """One regular file or folder, already checked, written to the temporary path `tmp`. The data filter does the
    work where Python has it; the same rules are applied by hand otherwise."""
    if hasattr(tarfile, "data_filter"):  # judged against tmp's own folder, so the user's symlinked ~/.config is fine
        tar.extract(info.replace(name=tmp.name), path=tmp.parent, set_attrs=True, filter="data")
        return
    if info.isdir():
        tmp.mkdir()
    else:
        with tar.extractfile(info) as src, open(tmp, "xb") as out:
            shutil.copyfileobj(src, out)
        os.utime(tmp, (info.mtime, info.mtime))
    if os.name != "nt":
        os.chmod(tmp, _mode(info))


def _extras(plan: _Plan) -> list[Path]:
    """What exists now inside a place the snapshot covered but is not in the archive (added since): the top-most
    paths only. Excluded folders are never entered, and files left out for size stay."""
    home = paths.home()
    covered = {parts[:i] for _, parts, _ in plan.safe for i in range(1, len(parts) + 1)}
    members = {parts for info, parts, _ in plan.safe if not info.isdir()}
    out: list[Path] = []

    def visit(path: Path, parts: tuple[str, ...], rel: str, excluded: frozenset[str], root: bool) -> None:
        try:
            st = os.lstat(path)
        except OSError:
            return
        isdir = stat.S_ISDIR(st.st_mode)
        if not isdir:
            if parts not in members and parts not in plan.skipped and (stat.S_ISREG(st.st_mode)
                                                                       or stat.S_ISLNK(st.st_mode)):
                out.append(path)
            return
        nested = any(e.startswith(f"{rel}/") for e in excluded) if rel else bool(excluded)
        if not root and parts not in covered and not nested:
            out.append(path)  # a folder added since, nothing excluded inside: one move
            return
        try:
            with os.scandir(path) as it:
                children = sorted(e.name for e in it)
        except OSError:
            return
        for name in children:
            child = f"{rel}/{name}" if rel else name
            if child not in excluded:
                visit(path / name, (*parts, name), child, excluded, False)

    for parts in plan.roots + plan.absent:
        path = home.joinpath(*parts)
        visit(path, parts, "", _excluded(path), parts in plan.absent)
    return list(dict.fromkeys(out))


def moved_aside(archive: Path) -> list[str]:
    """HOME-relative names a restore would move into the pre-restore backup because they were added since."""
    try:
        with _open(archive) as tar:
            return [_rel(p) or str(p) for p in _extras(_plan(tar))]
    except _Damaged:
        return []


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
            tmp = dest.parent / f".loadout-restore-{uuid.uuid4().hex}"
            try:
                link = _parent_link(home, parts, under)
                if link is not None:
                    lines.append(f"refused: {name}: {printable(str(link))} is a symlink")
                    failed += 1
                    continue
                keep_dir = info.isdir() and dest.is_dir() and not dest.is_symlink()
                if keep_dir:
                    done += 1
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                # everything that can fail happens on a temporary file next to the target; the current file is
                # moved aside only once the new one is ready, so a failure never leaves the target missing
                if info.issym():
                    os.symlink(info.linkname, tmp)
                else:
                    _extract(tar, info, tmp)
                moved = pre.move(dest, f"{dest} before restore", replace=True) if _exists(dest) else None
                try:
                    os.rename(tmp, dest)
                except OSError:
                    if moved is not None:
                        shutil.move(str(moved), str(dest))
                    raise
                label = f"{dest} (from the snapshot)"
                (pre.record_created_dir if info.isdir() else pre.record_created)(dest, label)
                done += 1
            except (tarfile.TarError, OSError) as exc:
                lines.append(f"failed: {name}: {printable(str(exc))}")
                failed += 1
            finally:
                if os.path.lexists(tmp):
                    shutil.rmtree(tmp) if tmp.is_dir() and not tmp.is_symlink() else tmp.unlink()
        extra = 0
        for path in _extras(plan):
            try:
                pre.move(path, f"{path} (added since the snapshot)", replace=True)
                extra += 1
            except OSError as exc:
                lines.append(f"failed: {printable(str(path))}: {printable(str(exc))}")
                failed += 1
        if extra:
            lines.append(f"moved {extra} item(s) added since the snapshot into the pre-restore backup")
        lines.append(f"restored {done} item(s) from {archive}")
        if not pre.empty:
            lines.append("what was there before is in the pre-restore backup")
        return lines, failed == 0, (None if pre.empty else pre.root)
