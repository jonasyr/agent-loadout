"""Prompt helpers shared by the interactive commands."""
from __future__ import annotations

import sys
from typing import Callable

Ask = Callable[[str], str]
YES = {"y", "yes"}
GROUP_ANSWERS = {"a": "a", "all": "a", "y": "a", "yes": "a",
                 "n": "n", "none": "n", "no": "n",
                 "p": "p", "pick": "p"}


def is_interactive() -> bool:
    """True when a person can answer prompts. Piped or closed stdin is not interactive."""
    try:
        return sys.stdin is not None and sys.stdin.isatty()
    except (AttributeError, ValueError, OSError):
        return False


def confirm(ask: Ask, question: str) -> bool:
    """y/N question; empty answer or EOF (ask returns "") means no."""
    return ask(question).strip().lower() in YES


def choose_group(ask: Ask, question: str, default: str, tries: int = 3) -> str:
    """a/all/y/yes, n/none/no, p/pick (any case); empty = default; anything else is asked again."""
    for _ in range(tries):
        answer = ask(question).strip().lower()
        if not answer:
            return default
        if answer in GROUP_ANSWERS:
            return GROUP_ANSWERS[answer]
        print("  please answer a(ll), n(one) or p(ick)")
    return "n"
