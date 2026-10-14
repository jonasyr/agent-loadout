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


def _hint_rules():
    """The hook's own parser (plugins/loadout/hooks/tool_hint.py), so this metric and the hint use one definition
    of a symbol search. Loaded like advisor.py's hook; None when the kit has no hook script."""
    global _RULES
    if _RULES is None:
        import importlib.util
        path = paths.kit_root() / "plugins" / "loadout" / "hooks" / "tool_hint.py"
        if not path.is_file():
            _RULES = False
        else:
            spec = importlib.util.spec_from_file_location("loadout_tool_hint_hook", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            _RULES = module
    return _RULES or None


_RULES = None


def _symbol_search(text: str) -> bool:
    rules = _hint_rules()
    if rules is None:
        return False
    is_search, name, _ = rules.shell_search(text or "")
    return is_search and name is not None


def _symbol_pattern(pattern: object) -> bool:
    rules = _hint_rules()
    return rules is not None and rules.symbol(pattern) is not None


SHELLS = frozenset({"bash", "sh", "zsh", "dash", "fish", "pwsh", "powershell"})


def _command_text(args: object) -> str:
    """The shell text of a tool call: Claude Code's {"command": "..."}, Codex's JSON arguments with `cmd` or
    `command` (a string or an argv list), and `bash -lc "<script>"` unwrapped one level."""
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            return args
    if isinstance(args, dict):
        args = args.get("command") if args.get("command") is not None else args.get("cmd")
    if isinstance(args, list):
        words = [w for w in args if isinstance(w, str)]
        if len(words) >= 3 and words[0].rsplit("/", 1)[-1] in SHELLS and words[1] in ("-c", "-lc", "-ic"):
            return words[2]
        return " ".join(words)
    return args if isinstance(args, str) else ""


def _read_record(fh) -> str:
    """The next line, read in chunks of at most MAX_LINE + 1 characters. An oversized line comes back as its first
    chunk (longer than MAX_LINE, so the caller skips it); the rest is drained chunk by chunk, never held whole."""
    line = fh.readline(MAX_LINE + 1)
    if len(line) > MAX_LINE and not line.endswith("\n"):
        while True:
            chunk = fh.readline(MAX_LINE + 1)
            if not chunk or chunk.endswith("\n"):
                break
    return line


def _lines(path: Path, skipped: list[int], cutoff: float):
    """JSON objects of a transcript whose own timestamp is inside the window (a resumed old session keeps its old
    calls out). Lines without a readable timestamp count, since the file itself was changed in the window."""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            while True:
                line = _read_record(fh)
                if not line:
                    break
                if len(line) > MAX_LINE:
                    skipped[0] += 1
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    skipped[0] += 1
                    continue
                if isinstance(obj, dict) and _in_window(obj, cutoff):
                    yield obj
    except OSError:
        skipped[0] += 1


def _in_window(obj: dict, cutoff: float) -> bool:
    payload = obj.get("payload") if isinstance(obj.get("payload"), dict) else {}
    stamp = obj.get("timestamp") or payload.get("timestamp")
    if not isinstance(stamp, str):
        return True
    try:
        from datetime import datetime
        return datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp() >= cutoff
    except (ValueError, OverflowError, OSError):
        return True


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
        for obj in _lines(path, skipped, cutoff):
            try:  # valid JSON of an unexpected shape is skipped and counted, never a crash
                message = obj.get("message") if obj.get("type") == "assistant" else None
                content = message.get("content") if isinstance(message, dict) else None
                for item in content if isinstance(content, list) else []:
                    if not isinstance(item, dict) or item.get("type") != "tool_use":
                        continue
                    name, inp = str(item.get("name", "")), item.get("input")
                    inp = inp if isinstance(inp, dict) else {}
                    fam = family(name)
                    calls[fam] = calls.get(fam, 0) + 1
                    if fam == "grep" and _symbol_pattern(inp.get("pattern")):
                        searches += 1
                    elif fam == "shell" and _symbol_search(_command_text(inp)):
                        searches += 1
            except (AttributeError, TypeError, ValueError):
                skipped[0] += 1
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
        searches, sub, mcp_ids = 0, False, set()  # an MCP call can be logged twice: function_call and its end event
        for obj in _lines(path, skipped, cutoff):
            try:  # valid JSON of an unexpected shape is skipped and counted, never a crash
                p = obj.get("payload") if isinstance(obj.get("payload"), dict) else {}
                if obj.get("type") == "session_meta":
                    sub = "subagent" in json.dumps(p.get("source", "")).lower()
                kind = p.get("type")
                if kind in ("function_call", "custom_tool_call"):
                    name = p.get("name")
                    if not isinstance(name, str):
                        raise TypeError("tool name")
                    args = p.get("arguments") or p.get("input") or ""
                    fam = "shell" if name in CODEX_SHELL else family(name)
                    calls[fam] = calls.get(fam, 0) + 1
                    if fam not in ("shell", "other") and isinstance(p.get("call_id"), str):
                        mcp_ids.add(p["call_id"])
                    if fam == "shell" and _symbol_search(_command_text(args)):
                        searches += 1
                elif kind == "mcp_tool_call_end":
                    invocation = p.get("invocation")
                    if not isinstance(invocation, dict):
                        raise TypeError("invocation")
                    if p.get("call_id") in mcp_ids:
                        continue  # already counted from its function_call
                    fam = family(str(invocation.get("server", "")))
                    if fam != "other":
                        calls[fam] = calls.get(fam, 0) + 1
            except (AttributeError, TypeError, ValueError):
                skipped[0] += 1
        _add(out["subagent" if sub else "main"], calls, searches)
    out["skipped_lines"] = skipped[0]
    return out


def _hint_sessions(cutoff: float) -> int:
    """Sessions in the window that got a search or a docs hint. The hook keeps its state files for 7 days, so a
    longer window still counts only about the last week."""
    folder = paths.state_dir() / "tool-hint"
    n = 0
    for path in folder.glob("*.json") if folder.is_dir() else []:
        try:
            if path.stat().st_mtime < cutoff:
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and any(isinstance(data.get(k), int) and data[k] > 0
                                          for k in ("last_hint", "last_docs")):
            n += 1
    return n


def collect(days: int, now: float | None = None) -> dict:
    cutoff = (now or time.time()) - days * 86400
    report: dict = {"days": days}
    if targets.claude_enabled() and (c := _claude(cutoff)) is not None:
        report["claude"] = c
    if targets.codex_enabled() and (c := _codex(cutoff)) is not None:
        report["codex"] = c
    report["hint_sessions"] = _hint_sessions(cutoff)
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
