"""Create missing project files from templates/project; never overwrite."""
from __future__ import annotations

from pathlib import Path

from . import paths

GITIGNORE_LINES = [".claude/settings.local.json", ".serena/cache/"]


def render(text: str, values: dict) -> str:
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def _writes(project: Path, w):
    from .repo_writes import RepoWrites
    return w if w is not None else RepoWrites(project, now=True)


WHY = {"AGENTS.md": "instructions every agent reads", "CLAUDE.md": "points Claude Code at AGENTS.md",
       "docs/README.md": "the docs map", "docs/adr/README.md": "the decisions index"}


def scaffold(project: Path, dry_run: bool = False, w=None) -> tuple[list[Path], list[str]]:
    """Create the missing template files in the repo; with a collector `w` they are only planned. Returns (created or
    planned files, notes)."""
    from . import repo_config
    templates = paths.kit_root() / "templates" / "project"
    skip = set() if repo_config.agents(project)["claude"] else {"CLAUDE.md"}  # Claude Code's file (ADR 0030)
    notes = []
    if (project / "CLAUDE.md").exists() and not (project / "AGENTS.md").exists():
        skip = {"AGENTS.md", "CLAUDE.md"}
        notes.append("CLAUDE.md exists without AGENTS.md: /loadout:onboard will offer to migrate it.")
    writes = None if dry_run else _writes(project, w)
    created = []
    for src in sorted(templates.rglob("*")):
        if src.is_dir():
            continue
        rel = src.relative_to(templates)
        dest = project / rel
        if rel.as_posix() in skip or dest.exists():
            continue
        if dest.is_symlink():  # dangling: never followed; named when it points out of the repo
            if not paths.inside(dest, project):
                notes.append(f"skipped {rel.as_posix()}: it points outside the repo")
            continue
        if not paths.inside(dest, project) or not paths.inside(dest.parent, project):
            notes.append(f"skipped {rel.as_posix()}: it points outside the repo")
            continue
        created.append(dest)
        if writes is not None:
            writes.create(dest, render(src.read_text(encoding="utf-8"), {"PROJECT_NAME": project.name}),
                          f"init: {WHY.get(rel.as_posix(), 'project scaffold')}")
    return created, notes


def ensure_gitignore(project: Path, dry_run: bool = False, w=None) -> list[str]:
    """Add the missing local-file lines to .gitignore under one `# loadout` header, in the file's line endings."""
    from . import repo_config
    path = project / ".gitignore"
    if not paths.inside(path, project):
        return []
    planned = w.planned(path) if w is not None and hasattr(w, "planned") else None
    text = planned if planned is not None else (path.read_bytes().decode("utf-8") if path.exists() else "")
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines(keepends=True)  # each of the user's lines keeps its own ending
    existing = {line.strip() for line in lines}
    wanted = [l for l in GITIGNORE_LINES if repo_config.agents(project)["claude"] or not l.startswith(".claude/")]
    missing = [line for line in wanted if line not in existing]
    if not missing or dry_run:
        return missing
    added = [line + nl for line in missing]
    if "# loadout" in existing:  # one header: new lines go under it
        at = next(i for i, l in enumerate(lines) if l.strip() == "# loadout") + 1
        while at < len(lines) and lines[at].strip() and not lines[at].startswith("#"):
            at += 1
        if at == len(lines) and lines and not lines[-1].endswith(("\n", "\r")):
            lines[-1] += nl
        lines[at:at] = added
    else:
        if lines and not lines[-1].endswith(("\n", "\r")):
            lines[-1] += nl
        lines += ["# loadout" + nl] + added
    new = "".join(lines)
    writes = _writes(project, w)
    (writes.modify if path.exists() else writes.create)(path, new, "init: keep local agent files out of git")
    return missing
