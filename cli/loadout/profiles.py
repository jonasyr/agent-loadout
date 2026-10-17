"""Per-project profiles: settings/.mcp.json fragments plus plugins to install."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import paths
from .jsonio import deep_merge, load_json
from .secrets import redact


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
    why: dict = field(default_factory=dict)  # entry path like "settings.disabledMcpjsonServers" -> reason


def _dirs() -> list[Path]:
    return [paths.personal_root() / "profiles", paths.kit_root() / "profiles"]


def list_profiles() -> list[str]:
    names = set()
    for d in _dirs():
        names.update(p.stem for p in d.glob("*.json") if NAME.fullmatch(p.stem))  # others cannot be loaded by name
    return sorted(names)


def read_profile(path: Path, name: str) -> Profile:
    """The profile in `path`. A field of the wrong type raises a ValueError naming the file and the field."""
    data = load_json(path)

    def field_of(key, kind, default):
        value = data.get(key, default)
        if not isinstance(value, kind):
            word = {dict: "an object", list: "a list", str: "a string"}[kind]
            raise ValueError(f"profile {path}: {key} must be {word}")
        return value

    return Profile(
        name=name,
        description=field_of("description", str, ""),
        settings=field_of("settings", dict, {}),
        mcp=field_of("mcp", dict, {}),
        install=field_of("install", list, []),
        commands=field_of("commands", list, []),
        skills=field_of("skills", list, []),
        notes=field_of("notes", str, ""),
        why=field_of("why", dict, {}),
    )


def load_profile(name: str) -> Profile:
    if not NAME.fullmatch(name):
        raise ValueError(f"profile name {name!r}: use lowercase letters, digits, - and _")
    for d in _dirs():
        path = d / f"{name}.json"
        if path.exists():
            return read_profile(path, name)
    raise ValueError(f"unknown profile '{name}' (available: {', '.join(list_profiles())})")


CLAUDE_FILES = (("settings", Path(".claude/settings.json")), ("mcp", Path(".mcp.json")))  # Claude Code's repo files


def reason(profile: Profile, entry: str | None = None) -> str:
    """Why a change is made: `profile NAME`, plus the profile's reason for `entry` or, without an entry, its
    description."""
    text = profile.why.get(entry) if entry else None
    return f"profile {profile.name}" + (f": {text}" if isinstance(text, str) and text else
                                        f" ({profile.description})" if profile.description and entry is None else "")


def repo_off_notes(profile: Profile, project: Path) -> list[str]:
    """One line when the repo is not for Claude Code but the profile has Claude Code files (ADR 0030)."""
    from . import repo_config
    if repo_config.agents(project)["claude"]:
        return []
    files = [rel.as_posix() for attr, rel in CLAUDE_FILES if getattr(profile, attr)]
    if not files:
        return []
    chosen = str(project) in repo_config._PENDING or repo_config.load(project).agents is not None
    why = ("this repo is for Codex only (.loadout.json; add Claude Code with loadout init --agents claude,codex)"
           if chosen else "Claude Code is off for you (turn it on and run loadout profile "
           f"{profile.name} again, or choose the repo's agents with loadout init --agents claude,codex)")
    return [f"{' and '.join(files)}: not written, {why}"]


def apply_profile(profile: Profile, project: Path, w=None) -> tuple[list[Path], list[str]]:
    """Merge the profile into the repo's settings and .mcp.json when the repo is for Claude Code. A file is changed
    only in the layout it already has; any other file is left and its entries named. With a collector `w` the
    changes are only planned. Returns (changed, skipped)."""
    import json as _json
    from . import repo_config
    from .jsonio import dumps_like, json_style
    from .repo_writes import RepoWrites
    changed, skipped = [], []
    if not repo_config.agents(project)["claude"]:
        return changed, skipped  # repo_off_notes says what was not written
    writes = w if w is not None else RepoWrites(project, now=True)
    for attr, rel in CLAUDE_FILES:
        overlay = getattr(profile, attr)
        if not overlay:
            continue
        target = project / rel
        if not paths.inside(target, project) or not paths.inside(target.parent, project):
            skipped.append(f"skipped {rel.as_posix()}: it points outside the repo")
            continue
        planned = w.planned(target) if w is not None and hasattr(w, "planned") else None
        if planned is not None:  # an earlier profile in this plan already writes it: build on that
            before, old = _json.loads(planned), planned
        else:
            before = load_json(target)  # a file that does not parse raises InvalidJSON, as before
            old = target.read_bytes().decode("utf-8") if target.exists() else None
        if old is not None and not old.strip():
            old = None  # an empty file holds nothing of the user's: written like a new one
        after = deep_merge(before, overlay)
        if after == before and old is not None:
            continue  # nothing to change: quiet, whatever the layout
        style = json_style(old) if old is not None else None
        if old is not None and style is None:
            from .repo_writes import _flat
            keys = ", ".join(_flat(overlay))  # key paths only: values can hold secrets
            skipped.append(redact(f"{rel.as_posix()}: left as is (its layout is not one loadout rewrites); add by "
                                  f"hand from profile {profile.name}: {keys}"))
            continue
        keys = [f"{attr}.{k}" for k in overlay]
        why = next((reason(profile, k) for k in keys if k in profile.why), reason(profile))
        if old is None:
            (writes.modify if target.exists() else writes.create)(
                target, _json.dumps(after, indent=2, ensure_ascii=False) + "\n", why)
        else:
            writes.modify(target, dumps_like(style, after), why)
        changed.append(target)
    return changed, skipped


def _skill_source(name: str) -> Path | None:
    for d in _dirs():
        candidate = d / "skills" / name
        if candidate.is_dir():
            return candidate
    return None


REPO_SKILLS = (".claude/skills", ".agents/skills")  # Claude Code's and Codex's skill folder in a repo


def repo_skill_dirs(project: Path) -> tuple[Path, Path | None]:
    """(where a new repo skill's real folder goes, the other agent's folder that links to it, or None): Claude Code's
    .claude/skills whenever Claude Code is on, else Codex's .agents/skills (ADR 0027)."""
    from . import repo_config
    on = repo_config.agents(project)
    claude, agents = (project / rel for rel in REPO_SKILLS)
    if not on["claude"]:
        return agents, None
    return claude, agents if on["codex"] else None


def copy_skills(profile: Profile, project: Path, dry_run: bool = False, w=None) -> list[str]:
    """Copy the profile's skills into the repo's real skill folder (repo_skill_dirs). A skill of that name in either
    agent's folder is never overwritten."""
    out = []
    skills_dir, _ = repo_skill_dirs(project)
    if not paths.inside(skills_dir, project):
        top = skills_dir.parent.name
        return [f"skills not copied: {skills_dir} points outside {project} (a symlinked {top} or {top}/skills)"]
    for part in (skills_dir.parent, skills_dir):
        if profile.skills and (part.exists() or part.is_symlink()) and not part.is_dir():
            return [f"skills not copied: {part} is not a folder"]
    for name in profile.skills:
        if not isinstance(name, str) or not name or Path(name).name != name or name in (".", ".."):
            out.append(f"skill {name}: not a plain name, skipped")
            continue
        src, dest = _skill_source(name), skills_dir / name
        found = next((project / rel / name for rel in REPO_SKILLS
                      if (project / rel / name).exists() or (project / rel / name).is_symlink()), None)
        if src is None:
            out.append(f"skill {name}: not found in profiles/skills/ (personal layer or kit)")
        elif found is not None:
            out.append(f"skill {name}: {found} exists, left as is")
        elif dry_run:
            out.append(f"would copy skill {name} -> {dest}")
        else:
            from .repo_writes import RepoWrites
            writes = w if w is not None else RepoWrites(project, now=True)
            writes.copytree(src, dest, f"{reason(profile)}: skill {name}")
            out.append(f"copied skill {name} -> {dest}")
    return out


AGENT_OF = {".claude/skills": "Claude Code", ".agents/skills": "Codex"}


def link_skills(project: Path, dry_run: bool, w=None) -> list[str]:
    """Link each repo skill into the skill folder of every other agent that is on (relative, so the link works in
    every clone): .claude/skills/NAME into .agents/skills for Codex, .agents/skills/NAME into .claude/skills for
    Claude Code (ADR 0027)."""
    from . import repo_config
    on = repo_config.agents(project)
    claude, agents = REPO_SKILLS
    out, codex = [], on["codex"]
    if codex:
        out += _link_into(project, claude, agents, dry_run, report=True, w=w)
    if on["claude"]:  # two real folders: reported once, by the Codex direction when it ran
        out += _link_into(project, agents, claude, dry_run, report=not codex, w=w)
    return out


def _link_into(project: Path, src_rel: str, dest_rel: str, dry_run: bool, report: bool, w=None) -> list[str]:
    src_root, dest_root, agent = project / src_rel, project / dest_rel, AGENT_OF[dest_rel]
    if not src_root.is_dir():
        return []
    for root in (src_root, dest_root):  # a skill from outside the repo would be dangling in every other clone
        if not paths.inside(root.parent, project) or not paths.inside(root, project):
            top = root.parent.name
            return [f"skills not linked: {root} points outside {project} (a symlinked {top} or {top}/skills)"]
    for part in (dest_root.parent, dest_root):
        if part.is_symlink():  # ../../SRC/NAME would resolve from the link's real folder and dangle
            return [f"skills not linked: {part} is a link; make it a plain folder, then run this again"]
        if part.exists() and not part.is_dir():
            return [f"skills not linked: {part} is not a folder"]
    out = []
    for entry in sorted(src_root.iterdir()):
        if entry.name.startswith(".") or not entry.is_dir():
            continue
        name, dest = entry.name, dest_root / entry.name
        if not paths.inside(entry, project):  # a link to a skill elsewhere: dangling in every other clone
            out.append(f"skill {name}: {src_rel}/{name} leads outside {project}, not linked for {agent}")
            continue
        want = os.path.join("..", "..", *src_rel.split("/"), name)  # Windows resolves only its own separator
        if dest.exists() or dest.is_symlink():
            ours = dest.is_symlink() and Path(os.readlink(dest)) == Path(want)
            reverse = not dest.is_symlink() and os.path.realpath(dest) == os.path.realpath(entry)
            if ours or reverse:
                continue  # our link, or the entry is the other agent's link to this real folder
            if report:
                out.append(f"skill {name}: {dest_rel}/{name} is not a link to {src_rel}/{name}, "
                           f"left as is ({agent} uses that one)")
            continue
        if dry_run:
            out.append(f"would link skill {name} for {agent} -> {dest_rel}/{name}")
            continue
        if w is not None:
            try:
                w.link(dest, want, f"skill {name} for {agent}")
            except OSError as exc:  # a collector in now mode: e.g. Windows without symlink rights
                out.append(f"skill {name}: not linked for {agent} ({exc.strerror or exc})")
                continue
            out.append(f"linked skill {name} for {agent} -> {dest_rel}/{name}")
            continue
        dest_root.mkdir(parents=True, exist_ok=True)
        try:
            os.symlink(want, dest, target_is_directory=True)
        except OSError as exc:  # e.g. Windows without symlink rights
            out.append(f"skill {name}: not linked for {agent} ({exc.strerror or exc})")
            continue
        out.append(f"linked skill {name} for {agent} -> {dest_rel}/{name}")
    return out
