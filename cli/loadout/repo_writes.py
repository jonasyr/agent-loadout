"""Repo writes as a plan: collected, shown, then applied with a backup (spec Part 0)."""
from __future__ import annotations

import difflib
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from . import runner
from .jsonio import write_atomic
from .secrets import redact


@dataclass
class Change:
    kind: str                 # create | modify | copy | link | run
    path: Path | None
    why: str
    text: str | None = None
    src: Path | None = None
    target: str | None = None
    cmd: list | None = None
    touches: tuple = ()


def _top_missing(path: Path, project: Path) -> Path:
    """The highest folder (or the path itself) that does not exist yet: what restore has to take away again."""
    top = path
    for parent in path.parents:
        if parent == project or parent.exists() or parent.is_symlink():
            break
        top = parent
    return top


def _flat(value, prefix=""):
    if isinstance(value, dict) and value:
        out = {}
        for k, v in value.items():
            out.update(_flat(v, f"{prefix}.{k}" if prefix else str(k)))
        return out
    return {prefix: value}


def _json_diff(old: str, new: str) -> list[str] | None:
    try:
        a, b = _flat(json.loads(old or "{}")), _flat(json.loads(new))
    except ValueError:
        return None
    lines = []
    for key in b:
        if key not in a:
            lines.append(f"+ {key}: {json.dumps(b[key], ensure_ascii=False)}")
        elif a[key] != b[key]:
            lines.append(f"~ {key}: {json.dumps(a[key], ensure_ascii=False)} -> {json.dumps(b[key], ensure_ascii=False)}")
    lines += [f"- {key}" for key in a if key not in b]
    return lines


def _text_diff(old: str, new: str) -> list[str]:
    return [l for l in difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=0)
            if not l.startswith(("---", "+++", "@@"))]


class RepoWrites:
    def __init__(self, project: Path, now: bool = False, bk=None):
        self.project, self.now, self.bk = project, now, bk
        self._changes: list[Change] = []

    @property
    def changes(self) -> list[Change]:
        return list(self._changes)

    def _add(self, change: Change) -> None:
        if self.now:
            problem = self._do(change, self.bk)
            if problem:
                raise OSError(problem)
        else:
            self._changes.append(change)

    def create(self, path: Path, text: str, why: str) -> None:
        self._add(Change("create", path, why, text=text))

    def modify(self, path: Path, text: str, why: str) -> None:
        self._add(Change("modify", path, why, text=text))

    def copytree(self, src: Path, dest: Path, why: str) -> None:
        self._add(Change("copy", dest, why, src=src))

    def link(self, dest: Path, target: str, why: str) -> None:
        self._add(Change("link", dest, why, target=target))

    def run(self, cmd: list, why: str, touches: tuple = ()) -> None:
        self._add(Change("run", None, why, cmd=list(cmd), touches=tuple(touches)))

    def _rel(self, path: Path) -> str:
        try:
            return path.relative_to(self.project).as_posix()
        except ValueError:
            return str(path)

    def render(self) -> list[str]:
        out = []
        for c in self._changes:
            if c.kind == "create":
                n = len(c.text.splitlines())
                out.append(f"  create  {self._rel(c.path)} ({n} line{'s' if n != 1 else ''})  {c.why}")
                if c.path.suffix == ".json":
                    out += [f"          {l}" for l in (_json_diff("", c.text) or [])]
            elif c.kind == "modify":
                out.append(f"  change  {self._rel(c.path)}  {c.why}")
                old = c.path.read_bytes().decode("utf-8", "replace") if c.path.exists() else ""
                diff = _json_diff(old, c.text) if c.path.suffix == ".json" else None
                out += [f"          {l}" for l in (diff if diff is not None else _text_diff(old, c.text))]
            elif c.kind == "copy":
                files = sum(1 for p in c.src.rglob("*") if p.is_file())
                out.append(f"  copy    {self._rel(c.path)} ({files} file{'s' if files != 1 else ''})  {c.why}")
            elif c.kind == "link":
                out.append(f"  link    {self._rel(c.path)} -> {c.target}  {c.why}")
            else:
                out.append(f"  run     {' '.join(c.cmd)}  {c.why}; what it changes is its own, restore cannot undo it"
                           if not c.touches else f"  run     {' '.join(c.cmd)}  {c.why}")
        return [redact(l) for l in out]

    def apply(self, bk) -> list[str]:
        """Apply every collected change in order; each is recorded in `bk` before or as it happens."""
        problems = []
        for c in self._changes:
            problem = self._do(c, bk)
            if problem:
                problems.append(redact(problem))
        return problems

    def _do(self, c: Change, bk) -> str | None:
        if c.kind == "run":
            for path in c.touches:
                if bk is not None:
                    if path.exists():
                        bk.save_copy(path, f"{self._rel(path)} before {c.cmd[0]}")
                    else:
                        bk.record_created(_top_missing(path, self.project), f"{self._rel(path)} (created by {c.cmd[0]})")
            res = runner.run(c.cmd, cwd=str(self.project))
            return None if res.ok else f"{c.cmd[0]}: failed: {res.stderr.strip()}"
        if c.kind == "modify":
            if bk is not None:
                bk.save_copy(c.path, f"{self._rel(c.path)} before loadout changed it")
            write_atomic(c.path, c.text)
            return None
        top = _top_missing(c.path, self.project)
        c.path.parent.mkdir(parents=True, exist_ok=True)
        if c.kind == "create":
            write_atomic(c.path, c.text)
        elif c.kind == "copy":
            shutil.copytree(c.src, c.path, symlinks=True)
        else:
            try:
                os.symlink(c.target, c.path, target_is_directory=True)
            except OSError as exc:  # e.g. Windows without symlink rights
                return f"{self._rel(c.path)}: not linked ({exc.strerror or exc})"
        if bk is not None:
            bk.record_created(top, f"{self._rel(top)} (created by loadout)")
        return None
