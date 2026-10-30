"""Per-project profiles: settings/.mcp.json fragments plus plugins to install."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath

from . import paths
from .jsonio import get_dict, load_json
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
    done_when: list = field(default_factory=list)  # repo-relative paths: the commands are done here when any exists
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
        done_when=done_when(path, field_of("done_when", list, [])),
        notes=field_of("notes", str, ""),
        why=field_of("why", dict, {}),
    )


def done_when(path: Path, items: list) -> list:
    """The `done_when` paths, each a string inside the repo: relative, with no `..` part."""
    for item in items:
        if not isinstance(item, str):
            raise ValueError(f"profile {path}: done_when must be a list of strings")
        if PurePosixPath(item).is_absolute() or PureWindowsPath(item).anchor or ".." in re.split(r"[\\/]", item) \
                or PurePosixPath(item.replace("\\", "/")) == PurePosixPath("."):  # the repo itself always exists
            raise ValueError(f"profile {path}: done_when {item!r} must be a relative path inside the repo (no .., not the repo itself)")
    return items


def load_profile(name: str) -> Profile:
    if not NAME.fullmatch(name):
        raise ValueError(f"profile name {name!r}: use lowercase letters, digits, - and _")
    for d in _dirs():
        path = d / f"{name}.json"
        if path.exists():
            return read_profile(path, name)
    raise ValueError(f"unknown profile '{name}' (available: {', '.join(list_profiles())})")


def kit_marketplaces() -> dict[str, dict]:
    """Every marketplace the kit declares: settings.base.json's `extraKnownMarketplaces` and those of the kit's
    profiles (ADR 0037). The base wins on a name both declare."""
    out: dict[str, dict] = {}
    for path in sorted((paths.kit_root() / "profiles").glob("*.json")):
        out.update(get_dict(get_dict(load_json(path), "settings"), "extraKnownMarketplaces"))
    out.update(get_dict(load_json(paths.kit_root() / "settings.base.json"), "extraKnownMarketplaces"))
    return out


def marketplace_adds(profile: Profile) -> tuple[list[tuple[str, list[str]]], list[str]]:
    """(name, `claude plugin marketplace add` command) for each marketplace a profile needs before its installs: one for each marketplace
    its settings declare that a plugin in its `install` comes from and Claude Code has not added (ADR 0037). When
    Claude Code's list fails, each is added anyway: the install needs it. Also the lines for a source that names
    no usable repo or url. Output names the marketplace by its name only: an origin URL can carry a token."""
    declared = get_dict(profile.settings, "extraKnownMarketplaces")
    used = []
    for pid in profile.install:
        market = pid.rpartition("@")[2] if isinstance(pid, str) and PLUGIN_ID.match(pid) else None
        if market in declared and market not in used:
            used.append(market)
    if not used:
        return [], []
    from . import bootstrap
    listed = bootstrap.listed_marketplaces()
    cmds, bad = [], []
    for name in used:
        if listed is not None and name in listed:
            continue
        src = get_dict(declared[name], "source")
        origin = src.get("repo") or src.get("url")
        if not isinstance(origin, str) or not origin.strip() or origin.startswith("-"):
            bad.append(f"marketplace {name}: not added, profile {profile.name} names no usable repo or url for it")
            continue
        cmds.append((name, ["claude", "plugin", "marketplace", "add", origin]))
    return cmds, bad


CLAUDE_FILES = (("settings", Path(".claude/settings.json")), ("mcp", Path(".mcp.json")))  # Claude Code's repo files


def reason(profile: Profile, entry: str | None = None) -> str:
    """Why a change is made: `profile NAME`, plus the profile's reason for `entry` or, without an entry, its
    description."""
    text = profile.why.get(entry) if entry else None
    return f"profile {profile.name}" + (f": {text}" if isinstance(text, str) and text else
                                        f" ({profile.description})" if profile.description and entry is None else "")


def repo_off_notes(profile: Profile, project: Path, install: bool = False) -> list[str]:
    """When the repo is not for Claude Code: one line for the profile's Claude Code files and, with install, one
    naming the plugins that are not installed for it (ADR 0030)."""
    from . import repo_config
    if repo_config.agents(project)["claude"]:
        return []
    files = [rel.as_posix() for attr, rel in CLAUDE_FILES if getattr(profile, attr)]
    ids = [p for p in profile.install if install and isinstance(p, str) and PLUGIN_ID.match(p)]
    out = [f"skipped for this repo (not for Claude Code): {', '.join(f'plugin {p}' for p in ids)}"] if ids else []
    if not files:
        return out
    chosen = str(project) in repo_config._PENDING or repo_config.load(project).agents is not None
    why = ("this repo is for Codex only (.loadout.json; add Claude Code with loadout init --agents claude,codex)"
           if chosen else "Claude Code is off for you (turn it on and run loadout profile "
           f"{profile.name} again, or choose the repo's agents with loadout init --agents claude,codex)")
    return [f"{' and '.join(files)}: not written, {why}"] + out


def apply_profile(profile: Profile, project: Path, w=None, decide=None, notes: list | None = None) -> tuple[list[Path], list[str]]:
    """Merge the profile into the repo's settings and .mcp.json three-way against its record in .loadout.json
    (ADR 0031), when the repo is for Claude Code. A file is changed only in the layout it already has; any other
    file is left and its entries named. decide(lines) -> bool: whether to use the profile's values where a person
    changed an entry (None: keep theirs). notes collects the plan's lines about updated, kept and removed entries.
    With a collector `w` the changes are only planned. Returns (changed, skipped)."""
    import json as _json
    from . import repo_config, repo_merge
    from .jsonio import dumps_like, json_style
    from .repo_writes import RepoWrites, _flat
    changed, skipped = [], []
    notes = notes if notes is not None else []
    if not repo_config.agents(project)["claude"]:
        return changed, skipped  # repo_off_notes says what was not written
    writes = w if w is not None else RepoWrites(project, now=True)
    every = repo_config.records(project, writes)
    mine = every.get(profile.name, {})
    files = []
    for attr, rel in CLAUDE_FILES:
        overlay, key = getattr(profile, attr), rel.as_posix()
        if not overlay and not mine.get(key):
            continue
        target = project / rel
        if not paths.inside(target, project) or not paths.inside(target.parent, project):
            skipped.append(f"skipped {key}: it points outside the repo")
            continue
        planned = writes.planned(target)
        if planned is not None:  # an earlier profile in this plan already writes it: build on that
            before, old = _json.loads(planned), planned
        else:
            before = load_json(target)  # a file that does not parse raises InvalidJSON, as before
            old = target.read_bytes().decode("utf-8") if target.exists() else None
        if old is not None and not old.strip():
            old = None  # an empty file holds nothing of the user's: written like a new one
        others = tuple(r.get(key, {}) for n, r in every.items() if n != profile.name)
        files.append([attr, rel, target, before, old, overlay, others,
                      repo_merge.merge(before, overlay, mine.get(key, {}), others=others)])
    force = bool(getattr(decide, "take", False))  # --take-profile: also what was offered before and declined
    differs = [(f[1].as_posix(), d) for f in files for d in f[7].differs + (f[7].offered if force else [])]
    if differs and decide is not None:
        lines = [f"This repo differs from profile {profile.name} in {len(differs)} "
                 f"entr{'y' if len(differs) == 1 else 'ies'}:"]
        for rel, d in differs:
            k = repo_merge.unpointer(d.pointer)[-1]
            lines.append(redact(f"  {rel}  {d.pointer}: the repo has {repo_merge.show(d.theirs, k)}, "
                                f"the profile has {repo_merge.show(d.new, k)}"))
        if decide(lines):
            for f in files:
                f[7] = repo_merge.merge(f[3], f[5], mine.get(f[1].as_posix(), {}), take=True, others=f[6],
                                        take_offered=force)
    record = {}
    for attr, rel, target, before, old, overlay, others, m in files:
        key = rel.as_posix()
        skipped += [redact(f"{key}: {line}") for line in m.blocked]
        if not repo_merge.same(m.after, before) or old is None:
            style = json_style(old) if old is not None else None
            if old is not None and style is None:
                keys = ", ".join(_flat(overlay))  # key paths only: values can hold secrets
                skipped.append(redact(f"{key}: left as is (its layout is not one loadout rewrites); add by hand from "
                                      f"profile {profile.name}: {keys}"))
                continue  # nothing written, so the record for this file stays as it was
            if m.after or old is not None:
                keys = [f"{attr}.{k}" for k in overlay]
                why = next((reason(profile, k) for k in keys if k in profile.why), reason(profile))
                text = (_json.dumps(m.after, indent=2, ensure_ascii=False) + "\n" if old is None
                        else dumps_like(style, m.after))
                (writes.modify if target.exists() else writes.create)(target, text, why)
                changed.append(target)
        notes += _merge_notes(profile, key, m)
        record[key] = m.record
    if record and any(not repo_merge.same(record[k], mine.get(k, {})) for k in record):
        repo_config.plan_record(project, writes, profile.name, record, notes)
    return changed, skipped


class Kept(str):
    """A note that a person's change in a repo file stays (ADR 0031): said even when nothing else changes."""


def _merge_notes(profile: Profile, rel: str, m) -> list[str]:
    from . import repo_merge
    out = [f"{rel}: update {p} to profile {profile.name}'s value" for p in m.updated]
    out += [f"{rel}: remove {p} (no longer in profile {profile.name})" for p in m.removed]
    out += [Kept(f"{rel}: {line}") for line in m.kept + m.left]
    out += [Kept(f"{rel}: {line} was removed in this repo; kept removed") for line in m.kept_removed]
    for d in m.differs:
        if d.pointer not in m.updated:
            k = repo_merge.unpointer(d.pointer)[-1]
            out.append(Kept(f"{rel}: {d.pointer}: kept the repo's {repo_merge.show(d.theirs, k)} (profile {profile.name} "
                       f"has {repo_merge.show(d.new, k)}; loadout profile {profile.name} --take-profile uses it)"))
    for d in m.offered:
        if d.pointer not in m.updated:
            k = repo_merge.unpointer(d.pointer)[-1]
            out.append(Kept(f"{rel}: {d.pointer}: the repo's {repo_merge.show(d.theirs, k)} stays (changed in this repo; "
                       f"loadout profile {profile.name} --take-profile uses the profile's {repo_merge.show(d.new, k)})"))
    return [type(line)(redact(line)) for line in out]  # a Kept note stays one after redaction



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
    from . import skill_links
    return out + skill_links.report(skill_links.plain_files(project))


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
    out, broken = [], None
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
            if dest.is_file() and not dest.is_symlink():
                if broken is None:
                    from . import skill_links
                    broken = skill_links.plain_files(project)
                if f"{dest_rel}/{name}" in broken:
                    continue  # a committed link this checkout wrote as a file: link_skills reports it once
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
