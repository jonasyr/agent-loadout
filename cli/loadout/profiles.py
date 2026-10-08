"""Per-project profiles: settings/.mcp.json fragments plus plugins to install."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import paths
from .jsonio import deep_merge, load_json, save_json


@dataclass
class Profile:
    name: str
    description: str
    settings: dict = field(default_factory=dict)
    mcp: dict = field(default_factory=dict)
    install: list = field(default_factory=list)
    commands: list = field(default_factory=list)
    notes: str = ""


def _dirs() -> list[Path]:
    return [paths.personal_root() / "profiles", paths.kit_root() / "profiles"]


def list_profiles() -> list[str]:
    names = set()
    for d in _dirs():
        names.update(p.stem for p in d.glob("*.json"))
    return sorted(names)


def load_profile(name: str) -> Profile:
    for d in _dirs():
        path = d / f"{name}.json"
        if path.exists():
            data = load_json(path)
            return Profile(
                name=name,
                description=data.get("description", ""),
                settings=data.get("settings", {}),
                mcp=data.get("mcp", {}),
                install=data.get("install", []),
                commands=data.get("commands", []),
                notes=data.get("notes", ""),
            )
    raise ValueError(f"unknown profile '{name}' (available: {', '.join(list_profiles())})")


def apply_profile(profile: Profile, project: Path) -> list[Path]:
    changed = []
    for rel, overlay in ((Path(".claude/settings.json"), profile.settings), (Path(".mcp.json"), profile.mcp)):
        if not overlay:
            continue
        target = project / rel
        before = load_json(target)
        after = deep_merge(before, overlay)
        if after != before:
            save_json(target, after)
            changed.append(target)
    return changed
