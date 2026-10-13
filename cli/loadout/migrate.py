"""Move of loadout's own files out of ~/.claude into the XDG state folder (ADR 0025): copy, then retire later.

Older loadout processes (a daily sync that just pulled the update, an old `adopt`, the hooks of a Claude Code
session that has not reloaded its plugins) can still write the old place while a new run migrates, and nothing
can stop them. So nothing is deleted in the run that copies it:

1. copy: every entry of loadout's in the old place is copied to the new one without overwriting anything there,
   and recorded with a signature of the old entry and of the new copy (`migrated.json`);
2. retire: in a later run, once no old process can still be busy (RETIRE_AFTER, and no fresh old maintenance
   lock), an old entry that is unchanged since its copy is renamed aside, checked again and only then deleted.
   An old entry that changed after its copy (an old process wrote it) replaces the copy when the copy is
   untouched; when both changed, both are kept and named (`loadout check` warns).
"""
from __future__ import annotations

import errno
import filecmp
import os
import shutil
import stat
import time
from pathlib import Path

from . import paths
from .jsonio import InvalidJSON, load_json, save_json

LOCK = "migrate.lock"
RECORD = "migrated.json"
STALE = 300.0  # a migration lock this old is from a run that was killed
WAIT = 10.0  # seconds to wait for another run that is migrating right now
RETIRE_AFTER = 600.0  # an old copy is retired only this long after it was copied: old processes have finished
OLD_LOCK_FRESH = 3600.0  # an old version's maintenance lock younger than this: it may still be writing
# session files of the loadout hooks: an older plugin in an open Claude Code session keeps reading and writing
# them in ~/.claude/.loadout until /reload-plugins; the new place's copy is never replaced from the old one
SESSION_FILES = {"advisor-pending.json", "advisor-done.json", "reload-notified.json"}
SESSION_IDLE = 86400.0  # an old session file untouched this long belongs to no running session any more
TRANSIENT = {"maintenance.lock", LOCK}  # locks are never copied: they belong to the process holding them
_held: Path | None = None  # this run's lock, renewed while copying (_beat)
CHUNK = 1 << 20  # copy in pieces of this size, renewing the lock after each


def _ours(entry: Path) -> bool:
    """~/.claude/backups is shared (Claude Code keeps its .claude.json rotation copies there): only a folder
    loadout made, `loadout-<timestamp>` with a manifest, belongs to loadout. ~/.claude/.loadout is loadout's,
    except locks and this module's own temporary names."""
    name = entry.name
    if entry.parent.name == "backups":
        return name.startswith("loadout-") and entry.is_dir() and not entry.is_symlink() \
            and (entry / "manifest.json").is_file()
    return name not in TRANSIENT and ".stale-" not in name and not name.startswith(".") \
        and not name.endswith((".partial", ".tmp"))


def _sig(path: Path) -> list:
    """What an entry looks like now: inode, size and time of a file; names, sizes and times of a folder's files."""
    st = os.stat(path, follow_symlinks=False)
    if stat.S_ISDIR(st.st_mode):
        files = []
        for p in sorted(path.rglob("*")):
            s = os.stat(p, follow_symlinks=False)
            rel = p.relative_to(path).as_posix()
            # folders count too: an empty one an old run moved in later must make the copy look stale
            files.append([rel, "dir"] if stat.S_ISDIR(s.st_mode) else [rel, s.st_size, s.st_mtime_ns])
        return ["dir", files]
    return ["file", st.st_ino, st.st_size, st.st_mtime_ns]


def _gone(path: Path) -> bool:
    try:
        os.stat(path, follow_symlinks=False)
        return False
    except FileNotFoundError:
        return True


def _remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


def _exclusive_copy(src: Path, dst: Path) -> None:
    """Copy src to dst only if dst does not exist (FileExistsError otherwise): the name is claimed with O_EXCL,
    then filled. A process that writes dst meanwhile replaces it atomically, so its file wins."""
    if src.is_symlink():
        os.symlink(os.readlink(src), dst)  # fails when dst exists
        return
    fd = os.open(dst, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
    with os.fdopen(fd, "wb") as w, open(src, "rb") as r:
        shutil.copyfileobj(r, w)
    shutil.copystat(src, dst)


def _publish(src: Path, dst: Path) -> bool:
    """Rename src to dst unless dst exists: never overwrite. Returns False, with src removed, when dst exists."""
    try:
        if src.is_dir() and not src.is_symlink():
            os.mkdir(dst, 0o700)  # claims the name: a folder another run created meanwhile is never replaced
            for child in sorted(src.iterdir()):
                os.rename(child, dst / child.name)  # into our own fresh folder
            os.rmdir(src)
            return True
        if os.name == "nt":
            os.rename(src, dst)  # Windows: rename never replaces
            return True
        try:
            os.link(src, dst, follow_symlinks=False)  # a file: link is the no-replace primitive
        except FileExistsError:
            raise
        except (NotImplementedError, OSError):  # no hard links on this filesystem
            _exclusive_copy(src, dst)
        src.unlink()
        return True
    except OSError as exc:
        if not (isinstance(exc, FileExistsError) or exc.errno in (errno.EEXIST, errno.ENOTEMPTY)):
            raise
        _remove(src)
        return False


def _beat(lock: Path | None = None) -> None:
    """Renew the lock while copying, so a long copy never looks like a crashed run (STALE)."""
    lock = lock or _held
    if lock is not None:
        try:
            os.utime(lock)
        except OSError:
            pass


def _copy_file(src, dst, *, follow_symlinks: bool = True):
    """shutil.copy2 in pieces, renewing the lock after each, so even one huge file never lets the lock go stale."""
    src, dst = Path(src), Path(dst)
    _beat()
    if src.is_symlink() and not follow_symlinks:
        os.symlink(os.readlink(src), dst)
        return dst
    with open(src, "rb") as r, open(dst, "wb") as w:
        while True:
            block = r.read(CHUNK)
            if not block:
                break
            w.write(block)
            _beat()
    shutil.copystat(src, dst)
    return dst


def _stage(old: Path, new: Path) -> tuple[Path, list] | None:
    """A complete copy of old next to new (new.partial). Returns (partial, old's signature as copied), or None
    when old changed while it was copied (the next run tries again)."""
    before = _sig(old)
    partial = new.with_name(new.name + ".partial")
    if not _gone(partial):
        _remove(partial)  # an interrupted copy: start again
    if old.is_dir() and not old.is_symlink():
        shutil.copytree(old, partial, symlinks=True, copy_function=_copy_file)
    else:
        _copy_file(old, partial, follow_symlinks=False)
    if _sig(old) != before:  # an old process wrote it meanwhile
        _remove(partial)
        return None
    return partial, before


def _copy(old: Path, new: Path) -> list | None:
    """Copy old to new without overwriting. Returns old's signature as copied, or None (try again next run)."""
    staged = _stage(old, new)
    if staged is None:
        return None
    partial, sig = staged
    return sig if _publish(partial, new) else None


def _aside(path: Path) -> Path:
    return path.with_name(f".{path.name}.retire-{os.getpid()}-{time.time_ns()}")


def _put_back(aside: Path, path: Path) -> bool:
    """Undo a rename aside without overwriting what appeared at path meanwhile."""
    try:
        if _gone(path):
            os.rename(aside, path)
            return True
    except OSError:
        pass
    return False


def _retire(old: Path, recorded: list) -> str:
    """Delete old only if it is exactly what was copied: renamed aside first, so a file an old process writes at
    that moment survives under the old name. Returns "done", "changed" or "kept" (left aside, to be named)."""
    aside = _aside(old)
    os.rename(old, aside)
    if _sig(aside) == recorded:
        _remove(aside)
        return "done"
    return "changed" if _put_back(aside, old) else "kept"


def _readopt(old: Path, new: Path, new_sig: list) -> tuple[list, list] | None:
    """old changed after its copy and the copy is untouched: the old one is newer and replaces the copy.
    Returns the new (old, new) signatures, or None when this is a conflict to keep and name."""
    try:
        if _sig(new) != new_sig:
            return None
    except FileNotFoundError:
        return None
    staged = _stage(old, new)
    if staged is None:
        return None
    partial, before = staged
    stale = _aside(new)
    os.rename(new, stale)
    if _sig(stale) != new_sig:  # a current process wrote the copy at that moment: it wins
        if not _put_back(stale, new):
            _remove(stale)
        _remove(partial)
        return None
    if not _publish(partial, new):
        _remove(stale)
        return None
    _remove(stale)
    return before, _sig(new)


def _release(lock: Path, token: str) -> None:
    """Remove the lock only if it is still this run's (a run that took over a stale lock wrote its own token)."""
    try:
        if lock.read_text(encoding="utf-8") == token:
            lock.unlink()
    except OSError:
        pass


def _lock(state: Path, wait: float) -> tuple[Path, str] | None:
    """The migration lock, holding this run's token; waits up to `wait` seconds for another run. A lock not
    renewed for STALE is from a crashed run: it is renamed aside first, so only one run takes it over."""
    lock = state / LOCK
    token = f"{os.getpid()}-{time.time_ns()}"
    deadline = time.time() + wait
    while True:
        try:
            fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(token)
            return lock, token
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime >= STALE:
                    stale = lock.read_text(encoding="utf-8")
                    aside = lock.with_name(f"{LOCK}.stale-{os.getpid()}-{time.time_ns()}")
                    os.rename(lock, aside)
                    if aside.read_text(encoding="utf-8") == stale:
                        aside.unlink()
                        continue
                    # another run took the stale lock over between our check and our rename: give it back
                    if not _put_back(aside, lock):
                        aside.unlink(missing_ok=True)
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


def _legacy_roots() -> list[tuple[Path, Path]]:
    return [(paths.legacy_state_dir(), paths.state_dir()), (paths.legacy_backups_root(), paths.backups_root())]


def _holds_destination(old: Path) -> bool:
    """An old entry that is (or contains) the new state folder: XDG_STATE_HOME pointing inside ~/.claude."""
    state = paths.state_dir()
    try:
        return state == old or state.is_relative_to(old)
    except ValueError:
        return False


def _is_dir(path: Path) -> bool:
    """Like Path.is_dir, but a path that cannot be inspected raises instead of looking absent."""
    try:
        return stat.S_ISDIR(os.stat(path).st_mode)
    except (FileNotFoundError, NotADirectoryError):
        return False


def _valid(entry) -> bool:
    if not (isinstance(entry, dict) and isinstance(entry.get("sig"), list)
            and isinstance(entry.get("at"), (int, float)) and not isinstance(entry.get("at"), bool)):
        return False
    if "new" in entry:
        return isinstance(entry["new"], str) and isinstance(entry.get("new_sig"), list)
    return bool(entry.get("conflict")) or bool(entry.get("session"))


def _record() -> dict:
    """The migration record. Anything that cannot be trusted (a damaged file or entry) is left out, so the copy
    step looks at that old entry again: it fails closed."""
    try:
        data = load_json(paths.state_dir() / RECORD)
    except (InvalidJSON, OSError, UnicodeDecodeError):
        data = {}
    entries = data.get("entries") if isinstance(data, dict) else None
    entries = entries if isinstance(entries, dict) else {}
    return {"entries": {k: e for k, e in entries.items() if isinstance(k, str) and _valid(e)}}


def _identical(old: Path, new: Path) -> bool:
    """Same content (a copy made earlier whose record was lost)."""
    try:
        if old.is_dir() and not old.is_symlink():
            if not (new.is_dir() and not new.is_symlink()):
                return False
            a, b = _sig(old)[1], _sig(new)[1]
            if [x[:2] for x in a] != [x[:2] for x in b]:
                return False
            return all(filecmp.cmp(old / x[0], new / x[0], shallow=False) for x in a if len(x) == 3)
        if old.is_symlink() or new.is_symlink():
            return old.is_symlink() and new.is_symlink() and os.readlink(old) == os.readlink(new)
        return new.is_file() and filecmp.cmp(old, new, shallow=False)
    except OSError:
        return False


def _old_process_busy() -> bool:
    lock = paths.legacy_state_dir() / "maintenance.lock"
    try:
        return time.time() - lock.stat().st_mtime < OLD_LOCK_FRESH
    except OSError:
        return False


def _reconcile(entry: dict, old: Path, now: float) -> None:
    """An old entry changed after its copy (an older process wrote it): at once, not after the waiting period,
    the newer old one replaces the copy when that is untouched; otherwise both are kept and named."""
    again = _readopt(old, Path(entry["new"]), entry["new_sig"])
    if again is None:
        entry.update(conflict=True, named=False)
    else:
        entry.update(sig=again[0], new_sig=again[1], at=now)  # retired after RETIRE_AFTER from now


def _step(entries: dict, key: str, entry: dict, now: float, busy: bool) -> None:
    """Keep one recorded old entry in step with its copy, and retire it when it is due (module docstring)."""
    old = Path(key)
    if entry.get("conflict"):
        return
    if "new" in entry and _gone(Path(entry["new"])):
        del entries[key]  # its copy is gone: never delete the last one; the next run copies it again
        return
    if _sig(old) != entry["sig"]:
        if entry.get("session") or "new" not in entry:
            entry.update(sig=_sig(old), at=now)  # a session file is never copied back: wait until it is idle
        else:
            _reconcile(entry, old, now)
        return
    if busy or now - entry.get("at", now) < RETIRE_AFTER:
        return
    if entry.get("session") and now - old.stat().st_mtime < SESSION_IDLE:
        return  # an old session may still read and write it
    result = _retire(old, entry["sig"])
    if result == "done":
        del entries[key]
    elif result == "kept":
        entry.update(conflict=True, named=False)
    # "changed": reconciled on the next run


def migrate_state(wait: float | None = None) -> list[str]:
    """Copies what is new in the old place and retires old copies that are due. Returns notice lines; empty when
    there was nothing to tell. wait: seconds to wait for another run's lock (the session hook passes less)."""
    roots = [(old, new) for old, new in _legacy_roots() if _is_dir(old)]
    if not roots:
        return []
    state = paths.state_dir()
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        state.chmod(0o700)
    held = _lock(state, WAIT if wait is None else wait)
    if held is None:
        return [f"loadout: another loadout run is moving its state out of ~/.claude right now ({state / LOCK}); "
                "run this again in a moment"]
    global _held
    lock, token = held
    _held = lock
    lines, copied, conflicts = [], 0, []
    record = {"entries": {}}
    entries = record["entries"]
    try:
        record = _record()
        entries = record["entries"]
        now = time.time()
        for old_root, new_root in roots:
            new_root.mkdir(parents=True, exist_ok=True, mode=0o700)
            for old in sorted(old_root.iterdir()):
                key = str(old)
                if not _ours(old) or key in entries or _holds_destination(old):
                    continue
                new = new_root / old.name
                session = old.name in SESSION_FILES
                if not _gone(new):  # the new place already has one of that name
                    if _identical(old, new):  # copied earlier (its record was lost): a copy, not a conflict
                        entries[key] = {"sig": _sig(old), "new": str(new), "new_sig": _sig(new),
                                        "session": session, "at": now}
                    else:
                        entries[key] = {"sig": _sig(old), "session": session, "at": now, "conflict": not session}
                    continue
                sig = _copy(old, new)
                if sig is None:
                    continue  # it changed while copying, or appeared at the new place: the next run decides
                entries[key] = {"sig": sig, "new": str(new), "new_sig": _sig(new), "session": session, "at": now}
                copied += 0 if session else 1
        busy = _old_process_busy()
        for key, entry in list(entries.items()):
            if _gone(Path(key)):
                del entries[key]
                continue
            _step(entries, key, entry, now, busy)
    except OSError as exc:
        lines.append(f"loadout: could not move its state from ~/.claude ({exc}); it tries again next time")
    finally:
        for key, entry in entries.items():
            if entry.get("conflict") and not entry.get("named"):
                conflicts.append(key)
                entry["named"] = True
        try:
            save_json(state / RECORD, record, mode=0o600)
        except OSError:
            pass
        finally:
            _held = None
            _release(lock, token)
    if copied:
        lines.insert(0, f"loadout: copied its state and backups from ~/.claude to {state}; "
                        "the old copies there go by themselves once nothing uses them")
    if conflicts:
        lines.append("loadout: kept in ~/.claude because both places have it: " + ", ".join(conflicts)
                     + "; compare and delete the old ones by hand (loadout check lists them)")
    for old_root, _ in roots:
        try:
            if old_root.is_symlink() and not any(old_root.iterdir()):
                old_root.unlink()  # a symlinked folder: remove the link, never its target
            elif old_root.is_dir() and not any(old_root.iterdir()):
                old_root.rmdir()
        except OSError:
            pass
    claude = paths.claude_home()
    try:
        if claude.is_dir() and not any(claude.iterdir()) and _claude_code_off():
            claude.rmdir()  # only an empty folder; only when Claude Code is off
    except OSError:
        pass
    return lines


def copied_to(old: Path) -> Path | None:
    """Where an old entry was copied, while the old copy waits to be retired (None: not copied, or a conflict)."""
    entry = _record()["entries"].get(str(old))
    if isinstance(entry, dict) and "new" in entry and not entry.get("conflict"):
        return Path(entry["new"])
    return None


def leftovers() -> list[Path]:
    """Old entries kept because both places have them: for `loadout check`."""
    return [Path(k) for k, e in _record()["entries"].items() if e.get("conflict") and not _gone(Path(k))]


def pending() -> bool:
    """True while the old place holds something of loadout's that was not copied yet (or cannot be read): a
    writing command would start from an empty snapshot. Copies waiting to be retired do not count."""
    try:
        entries = _record()["entries"]
        for old_root, _ in _legacy_roots():
            if not _is_dir(old_root):
                continue
            for old in old_root.iterdir():
                if not _ours(old) or old.name in SESSION_FILES or _holds_destination(old):
                    continue
                entry = entries.get(str(old))
                if entry is None:
                    return True  # not copied yet
                if not entry.get("conflict") and "new" in entry and _sig(old) != entry["sig"]:
                    return True  # an older process changed it after the copy: not reconciled yet
    except OSError:
        return True
    return False
