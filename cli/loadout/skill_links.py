"""Committed skill links a checkout turned into plain files (Git without symlinks, e.g. Windows without Developer
Mode): found and reported with the fix, never repaired (spec Part 3)."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from . import runner

FOLDERS = (".claude/skills", ".agents/skills")
AGENT = {".claude/skills": "Claude Code", ".agents/skills": "Codex"}
PREFIX = "skill links: "
SAFE = re.compile(r"[A-Za-z0-9._-]+")  # a link name loadout may put in a command you paste (names come from the repo)


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


def _same_blob(path: Path, oid: str) -> bool:
    """The file holds exactly the blob Git stores for the link (its target): what a checkout without symlinks writes.
    A file a person put there has other bytes."""
    try:
        data = path.read_bytes()
    except OSError:
        return False
    digest = hashlib.sha256 if len(oid) == 64 else hashlib.sha1  # a SHA-256 repository, or the usual SHA-1
    return digest(b"blob %d\0" % len(data) + data).hexdigest() == oid


def plain_files(project: Path) -> set[str]:
    """The candidates Git records as links (mode 120000) whose bytes are the link's target: a checkout without symlinks
    wrote them as files. git runs only when there is a candidate; without git, a repo or a readable index the answer is
    none."""
    candidates = _candidates(project)
    if not candidates or not (project / ".git").exists():
        return set()
    res = runner.run(["git", "-C", str(project), "ls-files", "-s", "-z", "--", *FOLDERS], timeout=20)
    if not res.ok:
        return set()
    linked = {}
    for record in res.stdout.split("\0"):
        meta, _, path = record.partition("\t")
        parts = meta.split(" ")
        if parts[0] == "120000" and len(parts) > 1:
            linked[path] = parts[1]
    return {c for c in candidates if c in linked and _same_blob(project / c, linked[c])}


def report(found: set[str]) -> list[str]:
    lines = []
    for folder in FOLDERS:
        n = sum(1 for p in found if p.startswith(folder + "/"))
        if not n:
            continue
        many = n != 1
        lines.append(f"{PREFIX}{n} skill link{'s' if many else ''} in {folder} {'are plain files' if many else 'is a plain file'} "
                     f"in this checkout (Git without symlinks), so {AGENT[folder]} does not see "
                     f"{'these skills' if many else 'this skill'}")
    if lines:
        safe = {p for p in found if SAFE.fullmatch(p.rsplit("/", 1)[-1])}
        restore = (f" and `git checkout -- {' '.join(_quoted(safe))}` (only these links, so your other changes in the "
                   "skill folders stay)" if safe else "")
        odd = (f"; {len(found - safe)} link name{'s' if len(found - safe) != 1 else ''} with unusual characters "
               "loadout does not put in a command: check those out by hand" if found - safe else "")
        lines.append(f"{PREFIX}fix: best, use Codex in WSL with the repo in the Linux home (docs/how-to/wsl.md); "
                     "otherwise turn on Windows Developer Mode, then in the repo run `git config core.symlinks true`"
                     f"{restore}{odd}. loadout runs none of these and never replaces the files")
    return lines


def _quoted(found: set[str]) -> list[str]:
    """The paths in folder order, each in double quotes (the same in PowerShell, cmd and Git Bash)."""
    order = {f: i for i, f in enumerate(FOLDERS)}
    return [f'"{p}"' for p in sorted(found, key=lambda p: (order.get(p.rsplit("/", 1)[0], 9), p))]
