"""`.loadout.json` in a repo: which agents the repo is for, and whether loadout may write there (ADR 0030)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import paths
from .jsonio import dumps_like, json_style

FILE = ".loadout.json"
AGENTS = ("claude", "codex")


class Invalid(ValueError):
    """The repo's .loadout.json cannot be used; the message starts with `.loadout.json: `."""


@dataclass
class RepoConfig:
    agents: frozenset | None = None
    manage: bool = True
    data: dict = field(default_factory=dict)
    exists: bool = False


def _path(project: Path) -> Path:
    return project / FILE


def load(project: Path) -> RepoConfig:
    path = _path(project)
    if not (path.exists() or path.is_symlink()):
        return RepoConfig()
    if not paths.inside(path, project):
        raise Invalid(f"{FILE}: it is a link that leads outside the repo; make it a plain file")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise Invalid(f"{FILE}: cannot read it ({exc.strerror or exc})") from None
    except (UnicodeDecodeError, ValueError) as exc:
        raise Invalid(f"{FILE}: does not parse ({exc}); fix it, then run this again") from None
    if not isinstance(data, dict):
        raise Invalid(f"{FILE}: must be a JSON object")
    agents = data.get("agents")
    if agents is not None:
        if (not isinstance(agents, list) or not agents or not all(isinstance(a, str) for a in agents)
                or len(set(agents)) != len(agents)
                or not all(a in AGENTS for a in agents)):
            raise Invalid(f'{FILE}: agents must be a list of "claude" and "codex" (each once)')
        agents = frozenset(agents)
    manage = data.get("manage", True)
    if not isinstance(manage, bool):
        raise Invalid(f"{FILE}: manage must be true or false")
    return RepoConfig(agents, manage, data, True)


def user_agents() -> dict:
    from . import targets
    return {"claude": targets.claude_enabled(), "codex": targets.codex_enabled()}


_PENDING: dict = {}


class pending:
    """While planning, the agents about to be written to .loadout.json count as the repo's."""

    def __init__(self, project: Path, chosen: frozenset | None):
        self.key, self.chosen = str(project), chosen

    def __enter__(self):
        if self.chosen is not None:
            _PENDING[self.key] = frozenset(self.chosen)
        return self

    def __exit__(self, *exc):
        _PENDING.pop(self.key, None)


def agents(project: Path) -> dict:
    """The repo's agents from .loadout.json, else the user's (a repo nobody chose for)."""
    if str(project) in _PENDING:
        return {a: a in _PENDING[str(project)] for a in AGENTS}
    chosen = load(project).agents
    if chosen is None:
        return user_agents()
    return {a: a in chosen for a in AGENTS}


def parse_agents(value: str) -> frozenset:
    parts = [p.strip().lower() for p in (value or "").split(",")]
    if not parts or any(p not in AGENTS for p in parts):
        raise ValueError("--agents: give claude, codex or claude,codex")
    return frozenset(parts)


def new_text(project: Path, chosen: frozenset) -> str | None:
    """The file's text with `agents` set to `chosen` (its other keys kept), or None when nothing changes."""
    cfg = load(project)
    ordered = [a for a in AGENTS if a in chosen]
    if cfg.exists and cfg.agents == frozenset(chosen):
        return None
    if not cfg.exists:
        return json.dumps({"agents": ordered}, indent=2) + "\n"
    with open(_path(project), encoding="utf-8", newline="") as fh:  # newline="": keep CRLF so json_style sees it
        style = json_style(fh.read())
    if style is None:
        raise Invalid(f'{FILE}: its layout is not one loadout rewrites; set "agents": {json.dumps(ordered)} by hand')
    return dumps_like(style, {**cfg.data, "agents": ordered})
