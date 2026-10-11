"""Calm terminal output: one status line per step; details only with --verbose, problems always."""
from __future__ import annotations

import os
import re
import sys

VERBOSE = False
WIDTH = 18
_FANCY = {"ok": "✓", "warn": "!", "fail": "✗", "bullet": "•", "arrow": "→"}
_PLAIN = {"ok": "ok", "warn": "!", "fail": "x", "bullet": "-", "arrow": "->"}
# result lines that report something the user must see even in calm mode
PROBLEM = re.compile(r"failed|skipped|not changed|could not|cannot|do not run|by hand|left as is|^warning:")
_COLOR = {"ok": "32", "warn": "33", "fail": "31", "accent": "35", "muted": "2"}


def sym(name: str) -> str:
    """The symbol, or its ASCII stand-in when stdout cannot encode it (e.g. a cp1252 console)."""
    try:
        "".join(_FANCY.values()).encode(getattr(sys.stdout, "encoding", None) or "ascii")
        return _FANCY[name]
    except (UnicodeEncodeError, LookupError):
        return _PLAIN[name]


def paint(text: str, kind: str) -> str:
    """ANSI colour only on a terminal, never with NO_COLOR (https://no-color.org) or TERM=dumb."""
    try:
        tty = sys.stdout.isatty()
    except (AttributeError, ValueError):
        tty = False
    if not tty or os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
        return text
    if os.name == "nt" and not (os.environ.get("WT_SESSION") or os.environ.get("TERM")):
        return text  # the legacy console shows escape codes literally
    return f"\033[{_COLOR[kind]}m{text}\033[0m"


def status(name: str, summary: str, level: str = "ok") -> None:
    print(f"{paint(sym(level), level)} {name.ljust(WIDTH)} {summary}".rstrip())


def detail(line: str) -> None:
    if VERBOSE:
        print(f"  {line}")


def problem(line: str) -> None:
    print(f"  {line}")
