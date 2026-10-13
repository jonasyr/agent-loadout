"""One-time move of loadout's own files out of ~/.claude into the XDG state folder (ADR 0025)."""
from __future__ import annotations

import errno
import os
import shutil
import time
from pathlib import Path

from . import paths

LOCK = "migrate.lock"
STALE = 3600.0


def _files(root: Path) -> dict[str, int]:
    """Every file and link below root with its size (0 for a link): what a complete copy must match."""
    return {p.relative_to(root).as_posix(): 0 if p.is_symlink() else p.stat().st_size
            for p in root.rglob("*") if p.is_symlink() or p.is_file()}


def _move(old: Path, new: Path) -> None:
    """Move old to new (new does not exist): a rename, else a verified copy, then the old one goes."""
    new.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.replace(old, new)
        return
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
    if old.is_symlink() or not old.is_dir():
        shutil.copy2(old, new, follow_symlinks=False)
        old.unlink()
        return
    partial = new.with_name(new.name + ".partial")
    if partial.exists():
        shutil.rmtree(partial)  # an interrupted copy: start again
    shutil.copytree(old, partial, symlinks=True)
    if _files(partial) != _files(old):
        shutil.rmtree(partial)
        raise OSError(f"the copy of {old} is incomplete; it stays where it is")
    os.replace(partial, new)
    shutil.rmtree(old)


def _merge(old: Path, new: Path) -> list[Path]:
    """Both folders exist: move what the new one lacks; the new one wins; return the old entries kept."""
    kept = []
    for entry in sorted(old.iterdir()):
        target = new / entry.name
        if target.exists() or target.is_symlink():
            kept.append(entry)
        else:
            _move(entry, target)
    if not kept:
        old.rmdir()
    return kept


def _lock(state: Path) -> Path | None:
    lock = state / LOCK
    try:
        os.close(os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
        return lock
    except FileExistsError:
        try:
            if time.time() - lock.stat().st_mtime < STALE:
                return None  # another run is moving the files right now
            lock.unlink()
            os.close(os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
            return lock
        except OSError:
            return None


def _claude_code_off() -> bool:
    from . import targets
    try:
        return not targets.claude_enabled()
    except Exception:  # a damaged targets.json: keep the folder
        return False


def migrate_state() -> list[str]:
    """Returns notice lines; empty when there was nothing to move."""
    old_state, old_backups = paths.legacy_state_dir(), paths.legacy_backups_root()
    if not (old_state.exists() or old_backups.exists()):
        return []
    state = paths.state_dir()
    state.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        state.chmod(0o700)
    lock = _lock(state)
    if lock is None:
        return []
    lines, kept = [], []
    try:
        for old, new in ((old_state, state), (old_backups, paths.backups_root())):
            if not old.exists():
                continue
            if new.exists():
                kept += _merge(old, new)
            else:
                _move(old, new)
        lines.append(f"loadout: moved its state and backups from ~/.claude to {state}")
        lines += [f"loadout: kept {p} (the new location already has it); compare and delete it by hand" for p in kept]
    except OSError as exc:
        lines.append(f"loadout: could not move its state from ~/.claude ({exc}); it tries again next time")
    finally:
        lock.unlink(missing_ok=True)
    claude = paths.claude_home()
    if claude.is_dir() and not any(claude.iterdir()) and _claude_code_off():
        claude.rmdir()  # only an empty folder; only when Claude Code is off
    return lines
