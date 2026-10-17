"""Committed skill links a checkout turned into plain files (Git without symlinks, e.g. Windows without Developer
Mode): found and reported with the fix, never repaired (spec Part 3)."""
from __future__ import annotations

from pathlib import Path

from . import runner

FOLDERS = (".claude/skills", ".agents/skills")
AGENT = {".claude/skills": "Claude Code", ".agents/skills": "Codex"}
PREFIX = "skill links: "


def _candidates(project: Path) -> set[str]:
    """Regular files where a skill folder or link belongs."""
    out = set()
    for folder in FOLDERS:
        root = project / folder
        try:
            entries = list(root.iterdir()) if root.is_dir() and not root.is_symlink() else []
        except OSError:
            continue
        out.update(f"{folder}/{e.name}" for e in entries if e.is_file() and not e.is_symlink())
    return out


def plain_files(project: Path) -> set[str]:
    """The candidates Git records as links (mode 120000): a checkout without symlinks wrote them as files. git runs
    only when there is a candidate; without git, a repo or a readable index the answer is none."""
    candidates = _candidates(project)
    if not candidates or not (project / ".git").exists():
        return set()
    res = runner.run(["git", "-C", str(project), "ls-files", "-s", "-z", "--", *FOLDERS], timeout=20)
    if not res.ok:
        return set()
    linked = set()
    for record in res.stdout.split("\0"):
        meta, _, path = record.partition("\t")
        if meta.split(" ")[0] == "120000":
            linked.add(path)
    return candidates & linked


def report(found: set[str]) -> list[str]:
    lines, folders = [], []
    for folder in FOLDERS:
        n = sum(1 for p in found if p.startswith(folder + "/"))
        if not n:
            continue
        folders.append(folder)
        many = n != 1
        lines.append(f"{PREFIX}{n} skill link{'s' if many else ''} in {folder} {'are plain files' if many else 'is a plain file'} "
                     f"in this checkout (Git without symlinks), so {AGENT[folder]} does not see "
                     f"{'these skills' if many else 'this skill'}")
    if lines:
        lines.append(f"{PREFIX}fix: best, use Codex in WSL with the repo in the Linux home (docs/how-to/wsl.md); "
                     "otherwise turn on Windows Developer Mode, then in the repo run `git config core.symlinks true` "
                     f"and `git checkout -- {' '.join(folders)}`. loadout runs none of these and never replaces the files")
    return lines
