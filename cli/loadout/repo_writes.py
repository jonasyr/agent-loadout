"""Repo writes as a plan: collected, shown, then applied with a backup (spec Part 0)."""
from __future__ import annotations

import difflib
import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from . import paths, runner, secrets
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
    absent: tuple = ()        # paths that must still be absent when a `run` step starts (git init and .git)
    pre: object = None        # what the path held when the plan was made (see _snapshot)
    group: str | None = None  # creates in one group share one line in the calm plan (e.g. init's scaffold)


def _snapshot(path: Path):
    """What a path holds now: its bytes, a link's target, "dir", or None when it is absent."""
    if path.is_symlink():
        return ("link", os.readlink(path))
    if path.is_file():
        return path.read_bytes()
    return "dir" if path.exists() else None


def _flat(value, prefix=""):
    if value == {} and not prefix:  # an empty file or object holds no entries
        return {}
    if isinstance(value, dict) and value:
        out = {}
        for k, v in value.items():
            seg = str(k).replace("\\", "\\\\").replace(".", "\\.")  # a literal dot stays distinct from nesting
            out.update(_flat(v, f"{prefix}.{seg}" if prefix else seg))
        return out
    return {prefix: value}


def _json_diff(old: str, new: str) -> list[str] | None:
    try:
        a, b = _flat(json.loads(old or "{}")), _flat(json.loads(new))
    except ValueError:
        return None
    secret = secrets.secret_value

    def masked(key, value):
        if isinstance(value, dict):  # nested objects: each value under its own key
            return {k: masked(str(k), v) for k, v in value.items()}
        if isinstance(value, list):  # args lists: the value after a key-like flag, and any secret-looking item
            out, prev = [], None
            for item in value:
                flag = isinstance(prev, str) and prev.startswith("-") and secrets.SECRET_KEY.search(prev)
                if isinstance(item, str):
                    out.append(secrets.MASK if flag or secret(key, item) else item)
                else:
                    out.append(masked(key, item))
                prev = item
            return out
        return secrets.MASK if secret(key, value) else value

    def shown(key, value):
        last = re.split(r"(?<!\\)\.", key)[-1].replace("\\.", ".")
        return json.dumps(masked(last, value), ensure_ascii=False)

    lines = []
    for key in b:
        if key not in a:
            lines.append(f"+ {key}: {shown(key, b[key])}")
        elif a[key] != b[key]:
            lines.append(f"~ {key}: {shown(key, a[key])} -> {shown(key, b[key])}")
    lines += [f"- {key}" for key in a if key not in b]
    return lines


def _text_diff(old: str, new: str) -> list[str]:
    lines = [l[0] + redact(l[1:]) for l in difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=0)
             if not l.startswith(("---", "+++", "@@"))]
    if not lines and old != new:
        lines = ["~ line endings or whitespace change"]
    return lines


RECORD_FILE = ".loadout.json"
RECORD_LABEL = "what loadout wrote here (commit it)"


def _who(why: str) -> str:
    """The profiles a reason names ("profile web", "profiles web, db"), else its first clause."""
    names = list(dict.fromkeys(re.findall(r"profile (\S+?)[:( ;]", why + " ")))
    if names:
        return ("profile " if len(names) == 1 else "profiles ") + ", ".join(names)
    return why.split("(")[0].split(";")[0].strip().rstrip(":")


def _label(c: Change) -> str:
    """A new file in a few words: its MCP servers when it has them, else who adds it."""
    if c.path.suffix == ".json":
        try:
            servers = json.loads(c.text).get("mcpServers")
        except (ValueError, AttributeError):
            servers = None
        if isinstance(servers, dict) and servers:
            return "MCP servers: " + ", ".join(str(k) for k in servers)
    return _who(c.why)


class RepoWrites:
    def __init__(self, project: Path, now: bool = False, bk=None):
        self.project, self.now, self.bk = project, now, bk
        self._changes: list[Change] = []
        self._watched: dict = {}
        self.stale = False  # set by apply when a watched path changed: nothing was written, nothing may follow

    def watch(self, path: Path) -> None:
        """The plan depends on `path` (e.g. .loadout.json): if it changes before apply, nothing is applied."""
        self._watched[path] = _snapshot(path)

    @property
    def changes(self) -> list[Change]:
        return list(self._changes)

    def _add(self, change: Change) -> None:
        if self.now:
            problem = self._do(change, self.bk)
            if problem:
                raise OSError(redact(problem))
            return
        if change.path is not None:
            change.pre = _snapshot(change.path)
        if change.kind in ("create", "modify"):  # a second write to one file: one change with the final text
            for earlier in self._changes:
                if earlier.kind in ("create", "modify") and earlier.path == change.path:
                    earlier.text = change.text
                    if change.why not in earlier.why:
                        earlier.why = f"{earlier.why}; {change.why}"
                    return
        self._changes.append(change)

    def keep(self, wanted) -> None:
        """Keep only the changes `wanted(change)` is true for (e.g. the installs this machine still lacks)."""
        self._changes = [c for c in self._changes if wanted(c)]

    def planned(self, path: Path) -> str | None:
        """The text already planned for `path`, so a later planner builds on it instead of on the disk."""
        return next((c.text for c in self._changes if c.kind in ("create", "modify") and c.path == path), None)

    def _ordered(self) -> list[Change]:
        """File changes first, commands after them, so a command's own edits are not overwritten by the plan."""
        return [c for c in self._changes if c.kind != "run"] + [c for c in self._changes if c.kind == "run"]

    def create(self, path: Path, text: str, why: str, group: str | None = None) -> None:
        self._add(Change("create", path, why, text=text, group=group))

    def modify(self, path: Path, text: str, why: str) -> None:
        self._add(Change("modify", path, why, text=text))

    def copytree(self, src: Path, dest: Path, why: str) -> None:
        self._add(Change("copy", dest, why, src=src))

    def link(self, dest: Path, target: str, why: str) -> None:
        self._add(Change("link", dest, why, target=target))

    def run(self, cmd: list, why: str, touches: tuple = (), absent: tuple = ()) -> None:
        self._add(Change("run", None, why, cmd=list(cmd), touches=tuple(touches), absent=tuple(absent)))

    def _rel(self, path: Path) -> str:
        try:
            return path.relative_to(self.project).as_posix()
        except ValueError:
            return str(path)

    def render(self, calm: bool = False) -> list[str]:
        """The plan's lines. calm: one line per new file (no keys), init's files on one line, .loadout.json without
        its record; a changed file keeps its key lines."""
        if calm:
            return [redact(l) for l in self._render_calm()]
        out = []
        for c in self._ordered():
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

    def _render_calm(self) -> list[str]:
        out, grouped = [], {}
        for c in self._ordered():
            if c.kind == "create" and c.group:
                if c.group not in grouped:
                    grouped[c.group] = len(out)
                    out.append([c.group])
                out[grouped[c.group]].append(self._rel(c.path))
                continue
            if c.kind in ("create", "modify") and c.path.name == RECORD_FILE and c.path.parent == self.project:
                verb = "create" if c.kind == "create" else "change"
                out.append(f"  {verb}  {RECORD_FILE}  {RECORD_LABEL}")
            elif c.kind == "create":
                out.append(f"  create  {self._rel(c.path)}  {_label(c)}")
            elif c.kind == "run":
                undo = "" if c.touches else "; restore can't undo it"
                out.append(f"  run     {' '.join(c.cmd)}  ({_who(c.why)}{undo})")
            else:
                out += self._render_one(c)
        return [f"  create  {', '.join(l[1:])}  {l[0]}" if isinstance(l, list) else l for l in out]

    def _render_one(self, c: Change) -> list[str]:
        keep, self._changes = self._changes, [c]
        try:
            return self.render()
        finally:
            self._changes = keep

    def apply(self, bk, hold: frozenset = frozenset()) -> list[str]:
        """Apply every collected change in order; each is recorded in `bk` before it acts. One failing change is a
        problem line; the rest still run. A file that changed since the plan is left as is (the user approved the
        plan, not that version). hold: paths the caller writes itself later (e.g. after installs)."""
        for path, seen in self._watched.items():
            if _snapshot(path) != seen:
                self.stale = True
                return [f"{self._rel(path)}: changed since the plan, so the plan no longer fits; nothing written "
                        "(run the command again for a new plan)"]
        problems = []
        for c in self._ordered():
            if c.path is not None and c.path in hold:
                continue
            if c.kind in ("create", "modify") and _snapshot(c.path) != c.pre:
                problems.append(f"{self._rel(c.path)}: changed since the plan, left as is (run the command again "
                                "for a new plan)")
                continue
            try:
                problem = self._do(c, bk)
            except OSError as exc:
                problem = f"{self._rel(c.path) if c.path else c.cmd[0]}: {exc.strerror or exc}"
            if problem:
                problems.append(redact(problem))
                if c.path in self._watched:  # e.g. .loadout.json could not be written: the rest was planned for it
                    self.stale = True
                    problems.append(f"{self._rel(c.path)} was not written, so the rest of the plan was not applied")
                    return problems
        return problems

    def _outside(self, path: Path, follow: bool) -> bool:
        """True when writing `path` would land outside the repo: through a linked parent folder, or (follow) through
        the path itself when it is a link."""
        if not paths.inside(path.parent, self.project):
            return True
        return follow and path.is_symlink() and not paths.inside(path, self.project)

    def _record_parents(self, path: Path, bk) -> None:
        """Record each folder that does not exist yet, top down, before it is made."""
        missing = []
        for parent in path.parents:
            if parent == self.project or parent.exists() or parent.is_symlink():
                break
            missing.append(parent)
        for folder in reversed(missing):
            if bk is not None:
                bk.record_created_dir(folder, f"{self._rel(folder)}/ (created by loadout)")

    def _record_touch(self, path: Path, who: str, bk) -> None:
        """Before a command changes `path`: save it, or record it (and its new folders) as created."""
        if path.exists():
            bk.save_copy(path, f"{self._rel(path)} before {who}")
        else:
            self._record_parents(path, bk)
            bk.record_created(path, f"{self._rel(path)} (created by {who})")

    def _do(self, c: Change, bk) -> str | None:
        if c.kind == "run":
            here = [p for p in c.absent if p.exists() or p.is_symlink()]
            if here:  # e.g. .git appeared since the plan: git init would follow it
                return f"{c.cmd[0]}: not run, {self._rel(here[0])} exists now (run the command again for a new plan)"
            for path in c.touches:
                if bk is not None:
                    self._record_touch(path, c.cmd[0], bk)
            res = runner.run(c.cmd, cwd=str(self.project))
            return None if res.ok else f"{c.cmd[0]}: failed: {res.stderr.strip()}"
        if self._outside(c.path, follow=c.kind in ("create", "modify")) or (c.kind == "create" and c.path.is_symlink()):
            return f"{self._rel(c.path)}: not written, it leads outside the repo (a link)"
        if c.kind in ("create", "modify"):
            if c.path.exists():  # a create whose file appeared since the plan is a change: its bytes are saved first
                if bk is not None:
                    bk.save_copy(c.path, f"{self._rel(c.path)} before loadout changed it")
            else:
                self._record_parents(c.path, bk)
                if bk is not None:
                    bk.record_created(c.path, f"{self._rel(c.path)} (created by loadout)")
            c.path.parent.mkdir(parents=True, exist_ok=True)
            write_atomic(c.path, c.text)
            return None
        if c.path.exists() or c.path.is_symlink():
            return f"{self._rel(c.path)}: exists now, left as is"
        self._record_parents(c.path, bk)
        if c.kind == "copy":
            if bk is not None:
                bk.record_created_dir(c.path, f"{self._rel(c.path)}/ (created by loadout)")
                for item in sorted(c.src.rglob("*")):
                    dest = c.path / item.relative_to(c.src)
                    if item.is_dir() and not item.is_symlink():
                        bk.record_created_dir(dest, f"{self._rel(dest)}/ (created by loadout)")
                    else:
                        bk.record_created(dest, f"{self._rel(dest)} (created by loadout)")
            c.path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(c.src, c.path, symlinks=True)
            return None
        if bk is not None:
            bk.record_created(c.path, f"{self._rel(c.path)} (created by loadout)")
        c.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.symlink(c.target, c.path, target_is_directory=True)
        except OSError as exc:  # e.g. Windows without symlink rights
            return f"{self._rel(c.path)}: not linked ({exc.strerror or exc})"
        return None
