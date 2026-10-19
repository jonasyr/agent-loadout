"""Run locks in the state folder (`maintenance.lock`, `codex.lock`): one run at a time. A foreground command
waits for the holder; the background job and the session start never wait. A lock not touched for `stale`
seconds is from a crashed run and is taken over (renamed aside first, so only one run gets it)."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from . import out, paths

FOREGROUND_LIMIT = 600.0  # seconds a foreground run waits when nobody can watch (no terminal)
POLL = 0.2
_sleep = time.sleep  # tests replace these two
_now = time.time


def foreground_wait() -> float | None:
    """How long a foreground command waits: until free on a terminal, FOREGROUND_LIMIT seconds without one."""
    try:
        tty = sys.stdout.isatty() and sys.stdin is not None and sys.stdin.isatty()
    except (AttributeError, ValueError, OSError):
        tty = False
    return None if tty else FOREGROUND_LIMIT


def _path(name: str) -> Path:
    return paths.state_dir() / name


def _read(path: Path) -> tuple[dict | None, float]:
    """(content as a dict or None for an old plain-pid file, mtime)."""
    mtime = path.stat().st_mtime
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, mtime
    return (data if isinstance(data, dict) else None), mtime


def holder(name: str) -> tuple[str, float] | None:
    """(command, started epoch) of the run holding the lock; None when there is no lock file."""
    try:
        data, mtime = _read(_path(name))
    except OSError:
        return None
    if data is None:
        return "loadout", mtime
    started = data.get("started")
    command = data.get("command")
    return (command if isinstance(command, str) and command else "loadout",
            float(started) if isinstance(started, (int, float)) else mtime)


def busy_message(name: str) -> str:
    command, started = holder(name) or ("loadout", _now())
    return (f"the other loadout run ({command}, started {time.strftime('%H:%M', time.localtime(started))}) "
            "is still running; run this again when it has finished")


class Lock:
    def __init__(self, path: Path, token: str) -> None:
        self.path, self.token = path, token

    def _ours(self) -> bool:
        try:
            data, _ = _read(self.path)
        except OSError:
            return False
        return bool(data) and data.get("token") == self.token

    def touch(self) -> None:
        """Long runs refresh the lock, so nobody takes it over as stale while we still work."""
        if self._ours():
            try:
                os.utime(self.path, None)
            except OSError:
                pass

    def release(self) -> None:
        """Only our own lock: if it was taken over as stale meanwhile, the new owner keeps it."""
        if not self._ours():
            return
        for attempt in range(5):
            try:
                self.path.unlink()
                return
            except PermissionError:  # Windows: a waiter has the file open for a moment
                if attempt < 4:
                    _sleep(0.05)
            except OSError:
                return


def _take_over_if_stale(path: Path, name: str, stale: float) -> str:
    """'gone' (retry at once), 'held' (a live holder, or another run is taking over) or 'stale-taken'.
    Takeovers are serialised by a short `<name>.takeover` guard, so two takers never rename each other's lock."""
    try:
        if _now() - path.stat().st_mtime < stale:
            return "held"
    except FileNotFoundError:
        return "gone"
    except OSError:
        return "held"
    guard = path.with_name(f"{name}.takeover")
    try:
        os.close(os.open(guard, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
    except FileExistsError:
        try:  # a guard left by a crashed taker
            if _now() - guard.stat().st_mtime > 60:
                guard.unlink()
        except OSError:
            pass
        return "held"
    except OSError:
        return "held"
    try:
        if _now() - path.stat().st_mtime < stale:  # re-check under the guard
            return "held"
        aside = path.with_name(f"{name}.stale-{os.getpid()}-{time.time_ns()}")
        os.rename(path, aside)
        fresh = _now() - aside.stat().st_mtime < stale
        if fresh:  # it was replaced just before our rename: give it back
            try:
                os.link(aside, path)
            except OSError:
                pass
        aside.unlink()
        return "held" if fresh else "stale-taken"
    except FileNotFoundError:
        return "gone"
    except OSError:
        return "held"
    finally:
        try:
            guard.unlink()
        except OSError:
            pass


def acquire(name: str, command: str, wait: float | None, *, stale: float = 3600.0, on_wait=None) -> Lock | None:
    """The lock `name`, or None. wait=0: one try; wait=None: until it is free; a number: that many seconds.
    on_wait is called at every poll while waiting (a run holding another lock touches it there)."""
    path = _path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    token = f"{os.getpid()}-{time.time_ns()}"
    body = json.dumps({"pid": os.getpid(), "token": token, "command": command, "started": _now()})
    began = time.monotonic()
    shown = False
    try:
        while True:
            try:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                if _take_over_if_stale(path, name, stale) != "held":
                    continue
            else:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(body)
                return Lock(path, token)
            if wait == 0:
                return None
            elapsed = time.monotonic() - began
            if wait is not None and elapsed >= wait:
                return None
            who = holder(name)
            if who:
                out.waiting(who[0], who[1], elapsed)
                shown = True
            if on_wait:
                on_wait()
            _sleep(POLL)
    finally:
        if shown:
            out.end_waiting()
