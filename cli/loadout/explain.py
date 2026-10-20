"""`loadout explain FILE`: the entries loadout wrote in a repo file, from which profile, and whether each still has
loadout's value; also Codex's own ~/.codex/config.toml and hooks.json (read-only; spec Part 0, ADR 0031)."""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import repo_config, repo_merge
from .secrets import redact

BROKEN = object()


def _say(text: str) -> None:
    from .out import printable
    print(printable(text))


def _current(path: Path, rel: str):
    if not path.is_file():
        return None
    try:
        if rel == ".codex/config.toml":
            from . import codex
            return codex._tomllib().loads(path.read_bytes().decode("utf-8"))
        return json.loads(path.read_text(encoding="utf-8-sig") or "{}")
    except Exception:
        return BROKEN


def _states(stored, data, ptr: str) -> list[str]:
    path = repo_merge.unpointer(ptr)
    key = path[-1]
    if data is BROKEN:
        return [f"{ptr}: {repo_merge.show(stored, key)}  cannot compare, the file does not parse"]
    now = repo_merge.get(data, path) if data is not None else repo_merge.MISSING
    if isinstance(stored, list):
        return [f"{ptr}: {repo_merge.show(s, key)}  "
                + ("loadout's value" if isinstance(now, list) and any(repo_merge.matches(s, x, key) for x in now)
                   else "removed in this repo") for s in stored]
    if repo_merge.matches(stored, now, key):
        state = "loadout's value"
    elif now is repo_merge.MISSING or now is repo_merge.SHAPE:
        state = "removed in this repo"
    else:
        state = f"changed in this repo (now {repo_merge.show(now, key)})"
    return [f"{ptr}: {repo_merge.show(stored, key)}  {state}"]


def _own(cfg) -> int:
    if not cfg.exists:
        _say(".loadout.json: not in this repo (loadout init or loadout profile adds it)")
        return 1
    agents = ", ".join(a for a in repo_config.AGENTS if a in (cfg.agents or ())) or "not set (each user's agents)"
    _say(f".loadout.json: loadout's file for this repo (commit it). agents: {agents}; "
          f"manage: {str(cfg.manage).lower()}")
    for name, files in sorted((cfg.data.get("profiles") or {}).items()):
        n = sum(len(e) for e in files.values())
        _say(f"  profile {name}: {n} recorded entr{'y' if n == 1 else 'ies'} in {', '.join(sorted(files))}")
    return 0


def _gitignore(path: Path) -> int:
    if not path.is_file():
        _say(".gitignore: no such file")
        return 1
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        _say(".gitignore: not UTF-8 text; loadout cannot read it")
        return 1
    except OSError as exc:
        _say(f".gitignore: cannot read it ({exc.strerror or exc})")
        return 1
    if "# loadout" not in [l.strip() for l in lines]:
        _say(".gitignore: no lines from loadout (it adds them under a '# loadout' line)")
        return 0
    at = next(i for i, l in enumerate(lines) if l.strip() == "# loadout") + 1
    ours = []
    while at < len(lines) and lines[at].strip() and not lines[at].startswith("#"):
        ours.append(lines[at].strip())
        at += 1
    _say(".gitignore: loadout added the lines under '# loadout': " + (", ".join(ours) or "(none)"))
    _say("  every other line is yours")
    return 0


def _codex_file(path: Path) -> str | None:
    """"config" or "hooks" when path is Codex's own config.toml or hooks.json (CODEX_HOME honoured), else None."""
    from . import paths
    home = paths.codex_home()
    same = lambda a, b: os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))  # noqa: E731
    return "config" if same(path, home / "config.toml") else "hooks" if same(path, home / "hooks.json") else None


def explain(target: str, cwd: Path | None = None) -> int:
    from .new_skill import repo_root
    if target == "~" or target.startswith(("~/", "~\\")):  # quoted, so the shell left it
        from . import paths
        target = str(paths.home() / target[2:])
    path = Path(os.path.abspath(Path(cwd or Path.cwd()) / target))
    which = _codex_file(path)
    if which is not None:  # Codex's user files: loadout's record of them is codex-config.json
        from . import codex
        for line in (codex.explain_config() if which == "config" else codex.explain_hooks()):
            _say(redact(line))
        return 0
    root = repo_root(path.parent)
    if root is None:
        _say(f"{target}: not inside a git repo; loadout records entries only in repos")
        return 1
    try:
        cfg = repo_config.load(root)
    except repo_config.Invalid as exc:
        _say(str(exc))
        return 1
    rel = path.relative_to(root).as_posix()
    from . import paths
    if (path.exists() or path.is_symlink()) and not (paths.inside(path, root) and paths.inside(path.parent, root)):
        _say(f"{rel}: it is a link that leads outside the repo; loadout does not read it")
        return 1
    if rel == repo_config.FILE:
        return _own(cfg)
    if rel == ".gitignore":
        return _gitignore(path)
    found = [(name, files[rel]) for name, files in sorted((cfg.data.get("profiles") or {}).items()) if rel in files]
    if not found:
        if not path.exists():
            _say(f"{rel}: no such file in {root}")
            return 1
        _say(f"{rel}: loadout recorded no entries in it. loadout records only what profiles write in "
              ".claude/settings.json, .mcp.json and .codex/config.toml; a file init created is yours once it exists")
        return 0
    data = _current(path, rel)
    _say(f"{rel} in {root}: entries loadout wrote (recorded in .loadout.json)")
    for name, entries in found:
        for ptr, stored in entries.items():
            for line in _states(stored, data, ptr):
                _say(redact(f"  profile {name}  {line}"))
    _say("  everything else in this file is yours; loadout does not change it")
    return 0
