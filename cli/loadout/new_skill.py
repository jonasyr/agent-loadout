"""`loadout configure new skill`: a SKILL.md stub in one of the three places a skill of yours can live
(docs/how-to/your-own-tools.md#where-a-tool-of-yours-can-live)."""
from __future__ import annotations

import re
from pathlib import Path

from . import paths, secrets, targets
from .backup import Backup

NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
DEFAULT_DESCRIPTION = "TODO: say when an agent should use this skill."


class BadInput(ValueError):
    """Wrong name or target (exit 2); nothing was written."""


class Refused(ValueError):
    """The skill cannot be created there (exit 1); nothing was written."""


def stub(name: str, description: str) -> str:
    return f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n\nTODO: the instructions.\n"


def _taken(folder: Path, name: str) -> Path | None:
    """The entry in folder that has this name, also in another case (macOS and Windows ignore case) or as a
    dangling link."""
    try:
        entries = list(folder.iterdir()) if folder.is_dir() else []
    except OSError:
        return None
    return next((e for e in entries if e.name.lower() == name.lower()), None)


def _refuse_taken(name: str, folders: list[Path]) -> None:
    for folder in folders:
        hit = _taken(folder, name)
        if hit is not None:
            raise Refused(f"skill {name}: {hit} already exists; nothing written")


def _write(folder: Path, name: str, description: str, bk: Backup) -> Path:
    skill = folder / name
    folder.mkdir(parents=True, exist_ok=True)
    skill.mkdir()
    bk.record_created(skill, f"skill {name} (created by configure new skill)")
    (skill / "SKILL.md").write_text(stub(name, description), encoding="utf-8", newline="\n")
    return skill / "SKILL.md"


def _link(dest: Path, src: Path, name: str, bk: Backup) -> str:
    from . import link
    line = link._link_one(dest, src, bk)
    bk.record_created(dest, f"link for skill {name}")
    return line or f"linked {dest} -> {src}"


def _global(name: str, description: str, bk: Backup) -> list[str]:
    root = paths.personal_root() / "skills"
    dests = ([paths.claude_home() / "skills"] if targets.claude_enabled() else []) + \
            ([paths.agents_skills()] if targets.codex_enabled() else [])
    _refuse_taken(name, [root, *dests])
    skill_md = _write(root, name, description, bk)
    out = [f"skill {name}: created {skill_md}"]
    out += [_link(dest / name, skill_md.parent, name, bk) for dest in dests]
    return out


def create(name: str, to: str = "global", description: str | None = None, cwd: Path | None = None,
           bk: Backup | None = None) -> list[str]:
    """Write the stub where `to` says (global, project:<profile>, repo) and link it for the agents that are on."""
    if not NAME.match(name or ""):
        raise BadInput(f"skill name '{name}': use lowercase letters, digits and -, starting with a letter or "
                       "digit, at most 64 characters")
    text = DEFAULT_DESCRIPTION if description is None else description.strip()
    if "\n" in text or "\r" in text:
        raise Refused("--description: one line only")
    if secrets.redact(text) != text:
        raise Refused("--description looks like it contains a secret; secrets never belong in a skill")
    bk = bk or Backup(description=f"configure new skill {name}")
    if to == "global":
        return _global(name, text, bk)
    if to.startswith("project:"):
        return _project(name, to.split(":", 1)[1], text, bk)
    if to == "repo":
        return _repo(name, text, cwd or Path.cwd(), bk)
    raise BadInput(f"--to {to}: use global, project:<profile> or repo")


def _project(name: str, profile: str, description: str, bk: Backup) -> list[str]:
    raise BadInput("--to project: not available yet")


def _repo(name: str, description: str, cwd: Path, bk: Backup) -> list[str]:
    raise BadInput("--to repo: not available yet")


def repo_root(start: Path) -> Path | None:
    for folder in (start, *start.parents):
        if (folder / ".git").exists():
            return folder
    return None
