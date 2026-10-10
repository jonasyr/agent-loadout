"""Per-project profiles: settings/.mcp.json fragments plus plugins to install."""
from __future__ import annotations

import shutil
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
    skills: list = field(default_factory=list)
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
                skills=data.get("skills", []),
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


def _skill_source(name: str) -> Path | None:
    for d in _dirs():
        candidate = d / "skills" / name
        if candidate.is_dir():
            return candidate
    return None


def copy_skills(profile: Profile, project: Path, dry_run: bool = False) -> list[str]:
    """Copy the profile's skills into the repo. An existing skill folder is never overwritten."""
    out = []
    for name in profile.skills:
        src, dest = _skill_source(name), project / ".claude" / "skills" / name
        if src is None:
            out.append(f"skill {name}: not found in profiles/skills/ (personal layer or kit)")
        elif dest.exists() or dest.is_symlink():
            out.append(f"skill {name}: {dest} exists, left as is")
        elif dry_run:
            out.append(f"would copy skill {name} -> {dest}")
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(src, dest, symlinks=True)
            out.append(f"copied skill {name} -> {dest}")
    return out
