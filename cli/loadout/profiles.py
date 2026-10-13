"""Per-project profiles: settings/.mcp.json fragments plus plugins to install."""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from . import paths
from .jsonio import deep_merge, load_json, save_json


NAME = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
PLUGIN_ID = re.compile(r"^[A-Za-z0-9][\w.-]*@[A-Za-z0-9][\w.-]*$")


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
        names.update(p.stem for p in d.glob("*.json") if NAME.match(p.stem))  # others cannot be loaded by name
    return sorted(names)


def load_profile(name: str) -> Profile:
    if not NAME.match(name):
        raise ValueError(f"profile name {name!r}: use lowercase letters, digits, - and _")
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


def apply_profile(profile: Profile, project: Path) -> tuple[list[Path], list[str]]:
    """Merge the profile into the repo's settings and .mcp.json. Returns (changed files, skipped lines)."""
    changed, skipped = [], []
    for rel, overlay in ((Path(".claude/settings.json"), profile.settings), (Path(".mcp.json"), profile.mcp)):
        if not overlay:
            continue
        target = project / rel
        if not paths.inside(target, project) or not paths.inside(target.parent, project):
            skipped.append(f"skipped {rel.as_posix()}: it points outside the repo")
            continue
        before = load_json(target)
        after = deep_merge(before, overlay)
        if after != before:
            save_json(target, after)
            changed.append(target)
    return changed, skipped


def _skill_source(name: str) -> Path | None:
    for d in _dirs():
        candidate = d / "skills" / name
        if candidate.is_dir():
            return candidate
    return None


def copy_skills(profile: Profile, project: Path, dry_run: bool = False) -> list[str]:
    """Copy the profile's skills into the repo. An existing skill folder is never overwritten."""
    out = []
    skills_dir = project / ".claude" / "skills"
    if not paths.inside(skills_dir, project):
        return [f"skills not copied: {skills_dir} points outside {project} (a symlinked .claude or .claude/skills)"]
    for name in profile.skills:
        if not isinstance(name, str) or not name or Path(name).name != name or name in (".", ".."):
            out.append(f"skill {name}: not a plain name, skipped")
            continue
        src, dest = _skill_source(name), skills_dir / name
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
