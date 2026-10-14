"""`loadout usage`: how often the agents used each tool family in local transcripts (counts only, read-only).
See docs/reference/cli.md#loadout-usage."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from . import paths, targets

MAX_LINE = 1_000_000
FAMILIES = (("serena", re.compile(r"serena", re.I)),
            ("codebase-memory", re.compile(r"codebase[-_]memory", re.I)),
            ("context7", re.compile(r"context7", re.I)),
            ("microsoft-learn", re.compile(r"microsoft[-_](learn|docs|code)|microsoft_docs", re.I)))
BUILTIN = {"Grep": "grep", "Glob": "glob", "Read": "read", "Bash": "shell"}
CODEX_SHELL = {"exec_command", "shell", "shell_command", "local_shell", "exec"}
SEARCH = re.compile(r"(?:^|[\s|;&(])(?:rg|grep|egrep|git\s+grep)\s+(?:-\S+\s+)*(?:\"([^\"]+)\"|'([^']+)'|(\S+))")
IDENT = re.compile(r"^(?:(?:def|class|function|fn|func|struct|interface|type)\s+)?[A-Za-z_][A-Za-z0-9_]{2,63}\(?$")
NAMES = ("serena", "codebase-memory", "context7", "microsoft-learn", "grep", "glob", "read", "shell", "other")
LABELS = {"serena": "Serena", "codebase-memory": "codebase-memory", "context7": "Context7",
          "microsoft-learn": "Microsoft Learn", "grep": "Grep", "glob": "Glob", "read": "Read", "shell": "shell",
          "other": "other"}


def family(name: str) -> str:
    for fam, rx in FAMILIES:
        if rx.search(name):
            return fam
    return BUILTIN.get(name, "other")


def _group() -> dict:
    return {"sessions": 0, "calls": 0, "symbol_searches": 0,
            "families": {n: {"calls": 0, "sessions": 0} for n in NAMES}}


def _symbol_search(text: str) -> bool:
    m = SEARCH.search(text or "")
    pattern = next((g for g in m.groups() if g), "") if m else ""
    return bool(IDENT.match(pattern.strip()))


def _lines(path: Path, skipped: list[int]):
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if len(line) > MAX_LINE:
                    skipped[0] += 1
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    skipped[0] += 1
                    continue
                if isinstance(obj, dict):
                    yield obj
    except OSError:
        skipped[0] += 1


def _add(group: dict, calls: dict[str, int], searches: int) -> None:
    group["sessions"] += 1
    group["symbol_searches"] += searches
    for fam, n in calls.items():
        group["calls"] += n
        group["families"][fam]["calls"] += n
        group["families"][fam]["sessions"] += 1


def _claude(cutoff: float) -> dict | None:
    root = paths.claude_home() / "projects"
    if not root.is_dir():
        return None
    out, skipped = {"main": _group(), "subagent": _group()}, [0]
    for path in root.rglob("*.jsonl"):
        try:
            if path.stat().st_mtime < cutoff:
                continue
        except OSError:
            continue
        calls: dict[str, int] = {}
        searches = 0
        for obj in _lines(path, skipped):
            content = (obj.get("message") or {}).get("content") if obj.get("type") == "assistant" else None
            for item in content if isinstance(content, list) else []:
                if not isinstance(item, dict) or item.get("type") != "tool_use":
                    continue
                name, inp = str(item.get("name", "")), item.get("input") or {}
                fam = family(name)
                calls[fam] = calls.get(fam, 0) + 1
                if fam == "grep" and IDENT.match(str(inp.get("pattern", "")).strip()):
                    searches += 1
                elif fam == "shell" and _symbol_search(str(inp.get("command", ""))):
                    searches += 1
        _add(out["subagent" if "subagents" in path.parts else "main"], calls, searches)
    out["skipped_lines"] = skipped[0]
    return out


def _codex(cutoff: float) -> dict | None:
    root = paths.codex_home() / "sessions"
    if not root.is_dir():
        return None
    out, skipped = {"main": _group(), "subagent": _group()}, [0]
    for path in root.rglob("*.jsonl"):
        try:
            if path.stat().st_mtime < cutoff:
                continue
        except OSError:
            continue
        calls: dict[str, int] = {}
        searches, sub = 0, False
        for obj in _lines(path, skipped):
            p = obj.get("payload") if isinstance(obj.get("payload"), dict) else {}
            if obj.get("type") == "session_meta":
                sub = "subagent" in json.dumps(p.get("source", "")).lower()
            kind = p.get("type")
            if kind in ("function_call", "custom_tool_call"):
                name = str(p.get("name", ""))
                args = p.get("arguments") or p.get("input") or ""
                args = args if isinstance(args, str) else json.dumps(args)
                fam = "shell" if name in CODEX_SHELL else family(name)
                calls[fam] = calls.get(fam, 0) + 1
                if fam == "shell" and _symbol_search(args):
                    searches += 1
            elif kind == "mcp_tool_call_end":
                fam = family(str((p.get("invocation") or {}).get("server", "")))
                if fam != "other":
                    calls[fam] = calls.get(fam, 0) + 1
        _add(out["subagent" if sub else "main"], calls, searches)
    out["skipped_lines"] = skipped[0]
    return out


def _hint_sessions() -> int:
    folder = paths.state_dir() / "tool-hint"
    n = 0
    for path in folder.glob("*.json") if folder.is_dir() else []:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and isinstance(data.get("last_hint"), int) and data["last_hint"] > 0:
            n += 1
    return n


def collect(days: int, now: float | None = None) -> dict:
    cutoff = (now or time.time()) - days * 86400
    report: dict = {"days": days}
    if targets.claude_enabled() and (c := _claude(cutoff)) is not None:
        report["claude"] = c
    if targets.codex_enabled() and (c := _codex(cutoff)) is not None:
        report["codex"] = c
    report["hint_sessions"] = _hint_sessions()
    return report


def render(report: dict) -> str:
    lines = [f"Tool use in the last {report['days']} days (counts only):"]
    for agent, title in (("claude", "Claude Code"), ("codex", "Codex")):
        if agent not in report:
            continue
        for kind in ("main", "subagent"):
            g = report[agent][kind]
            if not g["sessions"]:
                continue
            fams = ", ".join(f"{LABELS[n]} {g['families'][n]['calls']} calls in {g['families'][n]['sessions']}"
                             for n in NAMES if g["families"][n]["calls"])
            lines.append(f"  {title} {kind}: {g['sessions']} sessions, {g['calls']} tool calls; {fams or 'no tools'}")
            lines.append(f"    symbol-like searches with grep/rg: {g['symbol_searches']}")
        if report[agent]["skipped_lines"]:
            lines.append(f"  {title}: {report[agent]['skipped_lines']} unreadable lines skipped")
    lines.append(f"  sessions with a loadout tool hint: {report['hint_sessions']}")
    return "\n".join(lines)
