#!/usr/bin/env python3
"""Execution-advisor hooks (stdlib only, no network; always exit 0, silent on error).

  advisor.py record   PostToolUse Write|Edit|MultiEdit: remember a finished implementation plan
                      ({path, session_id}) in ~/.claude/.loadout/advisor-pending.json.
  advisor.py stop     Stop: once per plan version, block the stop and ask the agent to run
                      /loadout:execution-advisor before the user picks an execution method.

`loadout advisor-mark <plan>` (cli/loadout/advisor.py) imports this file and calls mark(), so
the plan hash has exactly one definition. stdout carries nothing but the Stop block JSON.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

PLAN_GLOBS = ("*/docs/superpowers/plans/*.md", "*/plans/*.md")
HEADER_LINES = 15
KEEP_PENDING = 50
KEEP_DONE = 200
INSTRUCTION = ("A plan was just finished: {path}. Before the user picks an execution method, invoke "
               "/loadout:execution-advisor on it and present its recommendation (Inline / SDD / Hybrid "
               "with per-task table) as the recommended option.")


def state_dir() -> Path:
    home = os.environ.get("HOME") or os.environ.get("USERPROFILE") or str(Path.home())
    return Path(home) / ".claude" / ".loadout"


def _load(name: str) -> dict:
    try:
        data = json.loads((state_dir() / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(name: str, data: dict) -> None:
    d = state_dir()
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / f".{name}.{os.getpid()}.tmp"
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, d / name)


def is_plan_path(path: str) -> bool:
    p = path.replace("\\", "/")
    return any(fnmatch.fnmatchcase(p, g) for g in PLAN_GLOBS)


def looks_like_plan(text: str) -> bool:
    """A real plan: "Implementation Plan" in a header line near the top and at least one `- [ ]` task."""
    head = text.splitlines()[:HEADER_LINES]
    has_header = any(line.lstrip().startswith("#") and "Implementation Plan" in line for line in head)
    return has_header and re.search(r"^\s*- \[ \]", text, re.M) is not None


def plan_hash(text: str) -> str:
    """Hash of the plan's content. Ticking checkboxes while executing is not a change."""
    norm = re.sub(r"^(\s*- )\[[xX]\]", r"\1[ ]", text.replace("\r\n", "\n"), flags=re.M)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def _read(path: str) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def record(payload: dict) -> None:
    tool_input = payload.get("tool_input")
    session = payload.get("session_id")
    if not isinstance(tool_input, dict) or not isinstance(session, str):
        return
    path = tool_input.get("file_path")
    if not isinstance(path, str) or not is_plan_path(path):
        return
    text = _read(path)
    if text is None or not looks_like_plan(text):
        return
    data = _load("advisor-pending.json")
    plans = [e for e in data.get("plans", []) if isinstance(e, dict)]
    if any(e.get("path") == path and e.get("session_id") == session for e in plans):
        return
    plans.append({"path": path, "session_id": session, "recorded": int(time.time())})
    _save("advisor-pending.json", {"plans": plans[-KEEP_PENDING:]})


def stop(payload: dict) -> str | None:
    """The block JSON for the first pending plan of this session whose current version was
    neither evaluated nor already nudged about; None to allow the stop."""
    if payload.get("stop_hook_active"):  # never block twice in a row
        return None
    session = payload.get("session_id")
    if not isinstance(session, str):
        return None
    data = _load("advisor-pending.json")
    plans = data.get("plans")
    if not isinstance(plans, list):
        return None
    evaluated = _load("advisor-done.json").get("evaluated", {})
    for entry in plans:
        if not isinstance(entry, dict) or entry.get("session_id") != session:
            continue
        path = entry.get("path")
        text = _read(path) if isinstance(path, str) else None
        if text is None or not looks_like_plan(text):
            continue
        h = plan_hash(text)
        if h in evaluated or entry.get("nudged") == h:
            continue
        entry["nudged"] = h  # one nudge per plan version, even if the user declines the advisor
        _save("advisor-pending.json", data)
        return json.dumps({"decision": "block", "reason": INSTRUCTION.format(path=path)}, ensure_ascii=False)
    return None


def mark(path: str) -> str:
    """Record the plan's current version as evaluated; returns its hash. Raises OSError if unreadable."""
    text = Path(path).read_text(encoding="utf-8")
    h = plan_hash(text)
    data = _load("advisor-done.json")
    evaluated = data.get("evaluated") if isinstance(data.get("evaluated"), dict) else {}
    evaluated.pop(h, None)
    evaluated[h] = {"path": path, "evaluated": int(time.time())}
    _save("advisor-done.json", {"evaluated": dict(list(evaluated.items())[-KEEP_DONE:])})
    return h


def main(argv: list[str]) -> int:
    try:
        payload = json.loads(sys.stdin.read())
        if not isinstance(payload, dict):
            return 0
        if argv[1:] == ["record"]:
            record(payload)
        elif argv[1:] == ["stop"]:
            out = stop(payload)
            if out:
                sys.stdout.write(out + "\n")
    except Exception:  # a hook must never break a session
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
