"""Which coding agents loadout sets up, stored in the personal layer so it follows the user (docs/how-to/codex.md)."""
from __future__ import annotations

from pathlib import Path

from . import paths
from .jsonio import load_json, save_json

AGENTS = ("claude", "codex")
OVERRIDE: dict | None = None  # bootstrap's choice while it runs, before the personal layer exists to store it


def path() -> Path:
    return paths.personal_root() / "targets.json"


def from_file() -> dict | None:
    """The stored choice, or None when the personal layer has not chosen."""
    data = load_json(path())
    if "claude" not in data and "codex" not in data:
        return None
    return {"claude": data.get("claude", True) is not False, "codex": data.get("codex") is True}


def claude_enabled() -> bool:
    if OVERRIDE is not None:
        return OVERRIDE["claude"]
    return load_json(path()).get("claude", True) is not False  # missing: every machine from before the choice


def codex_enabled() -> bool:
    if OVERRIDE is not None:
        return OVERRIDE["codex"]
    return load_json(path()).get("codex") is True


def restart_hint() -> str:
    """The restart line, naming only the agents that are on."""
    claude, codex = claude_enabled(), codex_enabled()
    if claude and codex:
        return "Restart Claude Code (or run /reload-plugins) and Codex to load the changes."
    if codex:
        return "Restart Codex to load the changes."
    return "Restart Claude Code (or run /reload-plugins) to load the changes."


def decided() -> bool:
    data = load_json(path())
    return "claude" in data or "codex" in data


def set_agents(choice: dict) -> None:
    if not any(choice.get(a) for a in AGENTS):
        raise ValueError("choose at least one coding agent (claude, codex)")
    data = load_json(path())
    data.update({a: bool(choice.get(a)) for a in AGENTS})
    path().parent.mkdir(parents=True, exist_ok=True)
    save_json(path(), data)


def set_target(name: str, on: bool) -> str:
    if name not in AGENTS:
        raise ValueError(f"unknown agent {name}; use claude or codex")
    choice = {"claude": claude_enabled(), "codex": codex_enabled(), name: on}
    if not any(choice.values()):
        raise ValueError("at least one coding agent must stay on; turn the other one on first")
    set_agents(choice)
    return f"{name}: {'on' if on else 'off'}"


def parse_agents(text: str) -> dict:
    names = [part.strip() for part in text.split(",")]
    if not names or any(n not in AGENTS for n in names):
        raise ValueError(f"--agents takes claude, codex or claude,codex (got '{text}')")
    return {a: a in names for a in AGENTS}
