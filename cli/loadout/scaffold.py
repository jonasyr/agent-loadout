"""Create missing project files from templates/project; never overwrite."""
from __future__ import annotations

from pathlib import Path

from . import paths

GITIGNORE_LINES = [".claude/settings.local.json", ".serena/cache/"]


def render(text: str, values: dict) -> str:
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def scaffold(project: Path, dry_run: bool = False) -> tuple[list[Path], list[str]]:
    templates = paths.kit_root() / "templates" / "project"
    skip = set()
    notes = []
    if (project / "CLAUDE.md").exists() and not (project / "AGENTS.md").exists():
        skip = {"AGENTS.md", "CLAUDE.md"}
        notes.append("CLAUDE.md exists without AGENTS.md: /loadout:onboard will offer to migrate it.")
    created = []
    for src in sorted(templates.rglob("*")):
        if src.is_dir():
            continue
        rel = src.relative_to(templates)
        dest = project / rel
        if rel.as_posix() in skip or dest.exists():
            continue
        created.append(dest)
        if not dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(render(src.read_text(encoding="utf-8"), {"PROJECT_NAME": project.name}), encoding="utf-8")
    return created, notes


def ensure_gitignore(project: Path, dry_run: bool = False) -> list[str]:
    path = project / ".gitignore"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    existing = {line.strip() for line in text.splitlines()}
    missing = [line for line in GITIGNORE_LINES if line not in existing]
    if missing and not dry_run:
        if text and not text.endswith("\n"):
            text += "\n"
        text += "# loadout\n" + "\n".join(missing) + "\n"
        path.write_text(text, encoding="utf-8")
    return missing
