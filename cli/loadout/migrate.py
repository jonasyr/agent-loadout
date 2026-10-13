"""One-time move of loadout's own files out of ~/.claude into the XDG state folder (ADR 0025)."""
from __future__ import annotations

import errno
import os
import shutil
import time
from pathlib import Path

from . import paths

LOCK = "migrate.lock"
STALE = 300.0  # the move is normally one rename: a lock this old is from a run that was killed
WAIT = 10.0  # seconds to wait for another run that is moving the files right now
# session files of the loadout hooks: an older plugin still running in an open Claude Code session keeps writing
# them to ~/.claude/.loadout until /reload-plugins; they are merged quietly, never "kept"
SESSION_FILES = {"advisor-pending.json", "advisor-done.json", "reload-notified.json"}


def _ours(entry: Path) -> bool:
    """~/.claude/backups is shared (Claude Code keeps its .claude.json rotation copies there): only a folder
    loadout made, `loadout-<timestamp>` with a manifest, belongs to loadout. ~/.claude/.loadout is all loadout's."""
    if entry.parent.name != "backups":
        return True
    return entry.name.startswith("loadout-") and entry.is_dir() and not entry.is_symlink() \
        and (entry / "manifest.json").is_file()


def _files(root: Path) -> dict[str, int]:
    """Every file and link below root with its size (0 for a link): what a complete copy must match."""
    return {p.relative_to(root).as_posix(): 0 if p.is_symlink() else p.stat().st_size
            for p in root.rglob("*") if p.is_symlink() or p.is_file()}


def _move_file(old: Path, new: Path) -> bool:
    """A file or link: hard link then unlink, so a file that appeared at new meanwhile is never overwritten
    (returns False then: the new one wins). Other filesystem: an atomic copy through new.partial."""
    try:
        os.link(old, new, follow_symlinks=False)
    except FileExistsError:
        return False
    except (OSError, NotImplementedError):  # another filesystem, no hard links there, or Windows (no linkat)
        if new.exists() or new.is_symlink():
            return False
        partial = new.with_name(new.name + ".partial")
        shutil.copy2(old, partial, follow_symlinks=False)
        os.replace(partial, new)
    old.unlink()
    return True


def _move(old: Path, new: Path) -> None:
    """Move old to new (new does not exist): a rename, else a verified copy, then the old one goes."""
    new.parent.mkdir(parents=True, exist_ok=True)
    if old.is_symlink() or not old.is_dir():
        if not _move_file(old, new):
            raise FileExistsError(f"{new} appeared while moving {old}; both are kept")
        return
    try:
        os.replace(old, new)
        return
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
    partial = new.with_name(new.name + ".partial")
    if partial.exists():
        shutil.rmtree(partial)  # an interrupted copy: start again
    shutil.copytree(old, partial, symlinks=True)
    if _files(partial) != _files(old):
        shutil.rmtree(partial)
        raise OSError(f"the copy of {old} is incomplete; it stays where it is")
    os.replace(partial, new)
    shutil.rmtree(old)


def _merge(old: Path, new: Path) -> tuple[list[Path], int]:
    """Both folders exist: move what the new one lacks; the new one wins.
    Returns (the old entries kept, how many moved)."""
    kept, moved = [], 0
    for entry in sorted(old.iterdir()):
        if not _ours(entry):
            continue  # not loadout's: it stays where its owner keeps it
        target = new / entry.name
        session = entry.name in SESSION_FILES
        if target.exists() or target.is_symlink():
            if session:
                entry.unlink()  # the new location's copy is the live one
            else:
                kept.append(entry)
            continue
        try:
            _move(entry, target)
            moved += 0 if session else 1
        except FileExistsError:  # it appeared meanwhile: the new one wins
            if session:
                entry.unlink()
            else:
                kept.append(entry)
    if not kept and not any(old.iterdir()):  # other owners' files keep the folder
        old.unlink() if old.is_symlink() else old.rmdir()  # a symlinked folder: remove the link, never its target
    return kept, moved


def _lock(state: Path, wait: float) -> Path | None:
    """The move lock; waits up to `wait` seconds for another run. A lock older than STALE is from a crashed run:
    it is renamed aside first, so only one run takes it over."""
    lock = state / LOCK
    deadline = time.time() + wait
    while True:
        try:
            os.close(os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
            return lock
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime >= STALE:
                    aside = lock.with_name(f"{LOCK}.stale-{os.getpid()}-{time.time_ns()}")
                    os.rename(lock, aside)
                    aside.unlink()
                    continue
            except OSError:
                pass  # another run took it over meanwhile: wait for it like for any other
        if time.time() >= deadline:
            return None
        time.sleep(0.2)


def _claude_code_off() -> bool:
    from . import targets
    try:
        return not targets.claude_enabled()
    except Exception:  # a damaged targets.json: keep the folder
        return False


def migrate_state(wait: float | None = None) -> list[str]:
    """Returns notice lines; empty when there was nothing to move. wait: seconds to wait for another run's lock
    (default WAIT; the session hook passes less, so it never runs into its own timeout)."""
    old_state, old_backups = paths.legacy_state_dir(), paths.legacy_backups_root()
    if not (old_state.is_dir() or old_backups.is_dir()):  # a plain file of that name is not loadout's
        return []
    state = paths.state_dir()
    state.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        state.chmod(0o700)
    lock = _lock(state, WAIT if wait is None else wait)
    if lock is None:
        return [f"loadout: another loadout run is moving its state out of ~/.claude right now ({state / LOCK}); "
                "run this again in a moment"]
    lines, kept, moved = [], [], 0
    try:
        # state first: the lock already lives in the new state folder, so state always merges entry by entry
        for old, new in ((old_state, state), (old_backups, paths.backups_root())):
            if not old.is_dir():
                continue
            if new.exists() or old == old_backups:  # the shared backups folder: entry by entry, never whole
                new.mkdir(parents=True, exist_ok=True)
                k, m = _merge(old, new)
                kept += k
                moved += m
            else:
                _move(old, new)
                moved += 1
    except OSError as exc:
        lines.append(f"loadout: could not move its state from ~/.claude ({exc}); it tries again next time")
    finally:
        lock.unlink(missing_ok=True)
    if moved:  # once: later runs that only find kept entries stay quiet (loadout check names them)
        lines.insert(0, f"loadout: moved its state and backups from ~/.claude to {state}")
        if kept:
            lines.append("loadout: kept in ~/.claude because the new location already has them: "
                         + ", ".join(str(p) for p in kept) + "; compare and delete them by hand")
    claude = paths.claude_home()
    try:
        if claude.is_dir() and not any(claude.iterdir()) and _claude_code_off():
            claude.rmdir()  # only an empty folder; only when Claude Code is off
    except OSError:
        pass  # something appeared in it meanwhile: it stays
    return lines


def pending() -> bool:
    """True while the old folders still hold something the new ones lack (a move that did not finish).
    Entries kept because the new location has the same name do not count."""
    try:
        for old, new in ((paths.legacy_state_dir(), paths.state_dir()),
                         (paths.legacy_backups_root(), paths.backups_root())):
            if old.is_dir() and any(_ours(e) and e.name not in SESSION_FILES
                                    and not ((new / e.name).exists() or (new / e.name).is_symlink())
                                    for e in old.iterdir()):
                return True
    except OSError:
        return False  # cannot tell: never block every command on it
    return False
