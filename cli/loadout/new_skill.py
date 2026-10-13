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
    """The description is a double-quoted YAML scalar (a JSON string is one), so `Use when: ...`, `#`, `[` or
    `yes` keep the frontmatter valid and the text unchanged."""
    import json
    return (f"---\nname: {name}\ndescription: {json.dumps(description, ensure_ascii=False)}\n---\n\n"
            f"# {name}\n\nTODO: the instructions.\n")


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
    from .jsonio import load_json
    try:
        pointers = load_json(paths.personal_root() / "skills.json")
    except Exception as exc:  # without the pointers, a name clash cannot be ruled out
        raise Refused(f"{paths.personal_root() / 'skills.json'} does not parse ({exc}); fix it, then run this "
                      "again") from None
    if isinstance(pointers, dict) and any(str(k).lower() == name.lower() for k in pointers):
        raise Refused(f"skill {name}: already a pointer in {paths.personal_root() / 'skills.json'}; nothing written")
    skill_md = _write(root, name, description, bk)
    out = [f"skill {name}: created {skill_md}"]
    out += [_link(dest / name, skill_md.parent, name, bk) for dest in dests]
    return out


def create(name: str, to: str = "global", description: str | None = None, cwd: Path | None = None,
           bk: Backup | None = None) -> list[str]:
    """Write the stub where `to` says (global, project:<profile>, repo) and link it for the agents that are on."""
    if not NAME.fullmatch(name or ""):  # fullmatch: `$` alone would let a trailing newline through
        raise BadInput(f"skill name '{name}': use lowercase letters, digits and -, starting with a letter or "
                       "digit, at most 64 characters")
    text = DEFAULT_DESCRIPTION if description is None else description.strip()
    if not text:
        raise Refused("--description is empty; say in one line when an agent should use the skill")
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
    from . import own
    from .jsonio import load_json
    if not own.PROFILE_NAME.match(profile):
        raise BadInput(f"profile name '{profile}': use lowercase letters, digits, - and _")
    path = paths.personal_root() / "profiles" / f"{profile}.json"
    if path.exists():
        try:
            data = load_json(path)
        except Exception as exc:
            raise Refused(f"{path} does not parse ({exc}); fix it, then run this again") from None
        if not isinstance(data, dict) or not isinstance(data.get("skills", []), list):
            raise Refused(f"{path}: skills is not a list; fix it, then run this again")
    root = paths.personal_root() / "profiles" / "skills"
    _refuse_taken(name, [root])
    skill_md = _write(root, name, description, bk)
    note = own.profile_note(profile)
    own._edit_profile(profile, bk, lambda d: own._append_once(own.ensure(d, "skills", list), name))
    return [*([note] if note else []), f"skill {name}: created {skill_md}; listed in profile {profile} "
            f"(apply it to a repo with `loadout profile {profile}`)"]


def _repo(name: str, description: str, cwd: Path, bk: Backup) -> list[str]:
    import os
    root = repo_root(Path(os.path.abspath(cwd)))
    if root is None:
        raise Refused(f"--to repo: {cwd} is not inside a git repo")
    src_root = root / ".claude" / "skills"
    dest_root = root / ".agents" / "skills" if targets.codex_enabled() else None
    if Path(os.path.realpath(root)) == Path(os.path.realpath(paths.home())):
        raise Refused(f"--to repo: the repo found is your home folder ({root}, a dotfiles repo?), where "
                      ".claude/skills is Claude Code's own folder; run it inside a project repo")
    for folder in (src_root, dest_root):
        if folder is not None and not (paths.inside(folder.parent, root) and paths.inside(folder, root)):
            raise Refused(f"--to repo: {folder} points outside {root} (a symlinked folder); nothing written")
        if folder is not None and (folder.exists() or folder.is_symlink()) and not folder.is_dir():
            raise Refused(f"--to repo: {folder} is not a folder; nothing written")
    _refuse_taken(name, [f for f in (src_root, dest_root) if f is not None])
    skill_md = _write(src_root, name, description, bk)
    out = [f"skill {name}: created {skill_md} (commit it to share it with this repo)"]
    if dest_root is not None:
        dest = dest_root / name
        dest_root.mkdir(parents=True, exist_ok=True)
        try:
            os.symlink(f"../../.claude/skills/{name}", dest, target_is_directory=True)
        except OSError as exc:  # e.g. Windows without symlink rights
            return out + [f"skill {name}: not linked for Codex ({exc.strerror or exc})"]
        bk.record_created(dest, f"Codex link for skill {name}")
        out.append(f"linked {dest} -> ../../.claude/skills/{name}")
    return out


def repo_root(start: Path) -> Path | None:
    for folder in (start, *start.parents):
        if (folder / ".git").exists():
            return folder
    return None
