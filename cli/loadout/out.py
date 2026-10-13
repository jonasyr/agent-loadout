"""Calm terminal output: one status line per step; details only with --verbose, problems always."""
from __future__ import annotations

import os
import re
import shutil
import sys

VERBOSE = False
WIDTH = 18
_FANCY = {"ok": "✓", "warn": "!", "fail": "✗", "bullet": "•", "arrow": "→"}
_PLAIN = {"ok": "ok", "warn": "!", "fail": "x", "bullet": "-", "arrow": "->"}
# result lines that report something the user must see even in calm mode
PROBLEM = re.compile(r"failed|skipped|not changed|not effective|could not|cannot|do not run|by hand|left as is|^warning:")
_COLOR = {"ok": "32", "warn": "33", "fail": "31", "accent": "35", "muted": "2"}


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


def progress(line: str) -> None:
    """A slow step's progress. On a terminal it replaces the previous progress line in place (the next status,
    detail or problem line clears it); off a terminal (logs, CI) and with --verbose it is a normal line."""
    global _shown
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


def status(name: str, summary: str, level: str = "ok") -> None:
    end_progress()
    print(f"{paint(sym(level), level)} {name.ljust(WIDTH)} {summary}".rstrip())


def detail(line: str) -> None:
    if VERBOSE:
        end_progress()
        print(f"  {line}")


def problem(line: str) -> None:
    end_progress()
    print(f"  {line}")
