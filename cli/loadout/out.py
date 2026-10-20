"""Calm terminal output: one status line per step; details only with --verbose, problems always."""
from __future__ import annotations

import os
import re
import shutil
import sys
import threading
import time

VERBOSE = False
WIDTH = 18
_FANCY = {"ok": "✓", "warn": "!", "fail": "✗", "bullet": "•", "arrow": "→"}
_PLAIN = {"ok": "ok", "warn": "!", "fail": "x", "bullet": "-", "arrow": "->"}
# result lines that report something the user must see even in calm mode
PROBLEM = re.compile(r"failed|skipped|not changed|not effective|could not|cannot|do not run|by hand|left as is|^warning:")
_COLOR = {"ok": "32", "warn": "33", "fail": "31", "accent": "35", "muted": "2"}


_CONTROL = re.compile(r"[\x00-\x08\x0a-\x1f\x7f-\x9f]")  # tab stays; a newline would fake a line


def printable(text: str, lines: bool = False) -> str:
    """Text from a repo or another person's file, safe to print: control characters (a terminal escape sequence, a
    bell) become visible \\xNN, so a cloned repo cannot drive the terminal. lines: keep line breaks (a message of
    several lines, such as a failed command's stderr); otherwise a newline is escaped too, so it cannot fake a line."""
    return _CONTROL.sub(lambda m: m.group() if lines and m.group() == "\n" else f"\\x{ord(m.group()):02x}", text)


def sym(name: str) -> str:
    """The symbol, or its ASCII stand-in when stdout cannot encode it (e.g. a cp1252 console)."""
    try:
        "".join(_FANCY.values()).encode(getattr(sys.stdout, "encoding", None) or "ascii")
        return _FANCY[name]
    except (UnicodeEncodeError, LookupError):
        return _PLAIN[name]


def _tty() -> bool:
    try:
        return sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


def paint(text: str, kind: str) -> str:
    """ANSI colour only on a terminal, never with NO_COLOR (https://no-color.org) or TERM=dumb."""
    if not _tty() or os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
        return text
    if os.name == "nt" and not (os.environ.get("WT_SESSION") or os.environ.get("TERM")):
        return text  # the legacy console shows escape codes literally
    return f"\033[{_COLOR[kind]}m{text}\033[0m"


_shown = 0  # width of the progress line on screen, 0 when none


def _safe(text: str) -> str:
    """Progress text from any caller, safe to show: redacted (a clone URL can carry a token) and escaped."""
    from .secrets import redact  # lazily: secrets must stay importable without out
    return printable(redact(text))


def progress(line: str) -> None:
    """A slow step's progress. On a terminal it replaces the previous progress line in place (the next status,
    detail or problem line clears it); off a terminal (logs, CI) and with --verbose it is a normal line."""
    global _shown
    line = _safe(line)
    if VERBOSE or not _tty():
        print(line, flush=True)
        return
    width = max(shutil.get_terminal_size().columns - 1, 20)
    text = line.rstrip()[:width]
    # spaces instead of an erase-line escape: the legacy Windows console has no escape codes
    sys.stdout.write("\r" + text.ljust(_shown) + ("\b" * max(_shown - len(text), 0)))
    sys.stdout.flush()
    _shown = len(text)


def end_progress() -> None:
    """Clear a progress line before anything else is printed."""
    global _shown
    if _shown:
        sys.stdout.write("\r" + " " * _shown + "\r")
        sys.stdout.flush()
        _shown = 0


_waiting_key: tuple | None = None


def waiting(command: str, started: float, elapsed: float) -> None:
    """A run is waiting for another loadout run. One in-place line with the seconds on a terminal; once elsewhere."""
    global _waiting_key
    line = (f"waiting for the other loadout run ({command}, started "
            f"{time.strftime('%H:%M', time.localtime(started))})…")
    if VERBOSE or not _tty():
        if _waiting_key != (command, started):
            _waiting_key = (command, started)
            print(_safe(line), flush=True)  # the command comes from the lock file
        return
    _waiting_key = (command, started)
    progress(f"{line} {int(elapsed)}s")


def end_waiting() -> None:
    """The wait is over (or interrupted): end the line."""
    global _waiting_key
    _waiting_key = None
    end_progress()


_clock = time.monotonic  # tests replace these two
_TICK = 1.0


class Step:
    """One slow step. On a terminal (not --verbose) a daemon thread rewrites `label: item (n of total) Ns` once a
    second; otherwise each item is one plain line. Use it through `step()`, which stops the thread on any exit."""

    def __init__(self, label: str, total: int | None = None, slow: str | None = None) -> None:
        self.label, self.total, self.slow = label, total, slow
        self._current, self._n, self._start = "", 0, _clock()
        self._live = False
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _line(self, elapsed: bool) -> str:
        text = f"{self.label}: {self._current}" if self._current else self.label
        if self._n and self.total:
            text += f" ({self._n} of {self.total})"
        if elapsed:
            text += f" {int(_clock() - self._start)}s"
        return text

    def item(self, text: str) -> None:
        with self._lock:
            self._current, self._n = _safe(text), self._n + 1
            if self._live:
                progress(self._line(True))
            else:
                print(self._line(False), flush=True)

    def tick(self) -> None:
        with self._lock:
            if self._live and not self._stop.is_set():
                progress(self._line(True))

    def _run(self) -> None:
        while not self._stop.wait(_TICK):
            self.tick()

    def __enter__(self) -> "Step":
        if self.slow:
            print(self.slow, flush=True)
        self._start = _clock()
        self._live = not VERBOSE and _tty()
        if self._live:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join()
        with self._lock:
            end_progress()


def step(label: str, total: int | None = None, slow: str | None = None) -> Step:
    return Step(label, total, slow)


def status(name: str, summary: str, level: str = "ok") -> None:
    end_progress()
    print(f"{paint(sym(level), level)} {name.ljust(WIDTH)} {summary}".rstrip())


def detail(line: str) -> None:
    if VERBOSE:
        end_progress()
        print(f"  {line}")


def problem(line: str) -> None:
    end_progress()
    print(f"  {printable(line, lines=True)}")
