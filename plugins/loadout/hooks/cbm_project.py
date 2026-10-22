#!/usr/bin/env python3
"""SessionStart and SubagentStart hook: tell the agent which codebase-memory project its folder is indexed as,
so it can call search_graph(project=...) at once (stdlib only; always exit 0; silent on any error).

Usage: cbm_project.py session-start|subagent-start, the hook payload (cwd) on stdin.
The index lives in codebase-memory's cache folder ($CBM_CACHE_DIR, else ~/.cache/codebase-memory-mcp; its
README documents no other default, also not on Windows). The default project name is the folder's absolute
path without the leading slash and with every slash turned into a dash; a project indexed under another
name is found by the root_path in the projects table of the *.db files.
"""
from __future__ import annotations

import json
import re
import os
import sqlite3
import sys
from pathlib import Path

EVENTS = {"session-start": "SessionStart", "subagent-start": "SubagentStart"}
SKIP = {"_config.db", "activity.db"}
MAX_DBS = 64


def cache_dir() -> Path:
    custom = os.environ.get("CBM_CACHE_DIR")
    if custom:
        return Path(custom)
    home = os.environ.get("HOME") or os.environ.get("USERPROFILE") or str(Path.home())
    return Path(home) / ".cache" / "codebase-memory-mcp"


def default_name(cwd: str) -> str:
    """codebase-memory's name for a project indexed without a name override: `/` becomes `-`, and a run of `-`
    becomes one (cbm 0.12.1: /tmp/claude-1000/-home-x is `tmp-claude-1000-home-x`)."""
    return re.sub(r"-{2,}", "-", cwd.lstrip("/").replace("/", "-"))


def project_for(cwd: str, max_dbs: int = MAX_DBS) -> str | None:
    try:
        cache = cache_dir()
        default = default_name(cwd)
        if (cache / f"{default}.db").is_file():
            return default
        for db in [d for d in sorted(cache.glob("*.db")) if d.name not in SKIP][:max_dbs]:
            if db.name in SKIP:
                continue
            try:
                con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=0.2)
                try:
                    row = con.execute("select name from projects where root_path = ?", (cwd,)).fetchone()
                finally:
                    con.close()
            except sqlite3.Error:
                continue
            if row and row[0]:
                return str(row[0])
    except Exception:
        return None
    return None


def _available(agent: str, cwd: str) -> bool:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import mcp_guard
    return mcp_guard.available("codebase-memory-mcp", agent, cwd, mcp_guard._home())


def main(argv: list[str]) -> None:
    event = EVENTS.get(argv[1]) if len(argv) > 1 else None
    if not event:
        return
    try:
        cwd = json.loads(sys.stdin.read()).get("cwd")
    except Exception:
        return
    agent = argv[argv.index("--agent") + 1] if "--agent" in argv[:-1] else "claude"
    if not isinstance(cwd, str) or not cwd or not _available(agent, cwd):
        return  # never point to a tool the agent does not have
    name = project_for(cwd)
    if not name:
        return
    text = (f"codebase-memory: this folder is indexed as project {name}; "
            f'pass project="{name}" to search_graph, trace_path and get_code_snippet.')
    print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}))


if __name__ == "__main__":
    try:
        main(sys.argv)
    except Exception:
        pass
    sys.exit(0)
