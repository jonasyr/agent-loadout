"""One record per transcript, counts only (never content). See docs/superpowers/specs/2026-10-24-usage-before-after-design.md."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime

from . import paths
from .usage import (MAX_LINE, _command_text, _denial, _read_record, _symbol_pattern, _symbol_searches,
                    family)

LOOKUP_TOOLS: dict[str, frozenset[str]] = {
    "serena": frozenset({"find_symbol", "get_symbols_overview", "find_referencing_symbols", "find_declaration",
                         "find_implementations"}),
    "codebase-memory": frozenset({"search_graph", "trace_path", "get_code_snippet", "query_graph", "search_code",
                                  "get_file_outline", "get_architecture"}),
}
PROMPT_WORDS = ("serena", "codebase-memory", "find_symbol", "search_graph", "trace_path", "get_code_snippet")


@dataclass
class Session:
    id: str
    agent: str
    kind: str
    start: float
    calls: dict[str, int] = field(default_factory=dict)
    total_calls: int = 0
    lookups: dict[str, int] = field(default_factory=lambda: {"serena": 0, "codebase-memory": 0})
    symbol_searches: int = 0
    denials: int = 0
    followed: int = 0
    prompted: bool | None = None


def lookup_family(name: str) -> str | None:
    tool = name.rsplit("__", 1)[-1] if name.startswith("mcp__") else name
    for fam, tools in LOOKUP_TOOLS.items():
        if tool in tools and family(name) == fam:
            return fam
    return None


def _stamp(obj: dict) -> float | None:
    value = obj.get("timestamp")
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (ValueError, OverflowError, OSError):
        return None


def _prompt_text(message: object) -> str | None:
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [i["text"] for i in content if isinstance(i, dict) and i.get("type") == "text"
                 and isinstance(i.get("text"), str)]
        return " ".join(parts) if parts else None
    return None


def _claude_session(path, follow_within: int, skipped: list[int], mtime: float) -> Session:
    sub = "subagents" in path.parts
    s = Session(path.stem, "claude", "subagent" if sub else "main", mtime)
    first: float | None = None
    open_denials: list[int] = []  # calls still allowed for each unfollowed denial
    need_prompt = sub
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
                if not isinstance(obj, dict):
                    continue
                t = _stamp(obj)
                if t is not None and (first is None or t < first):
                    first = t
                try:
                    kind = obj.get("type")
                    message = obj.get("message") if kind in ("assistant", "user") else None
                    if need_prompt and kind == "user":
                        text = _prompt_text(message)
                        if text is not None:
                            low = text.lower()
                            s.prompted = any(w in low for w in PROMPT_WORDS)
                            need_prompt = False
                    content = message.get("content") if isinstance(message, dict) else None
                    for item in content if isinstance(content, list) else []:
                        if not isinstance(item, dict):
                            continue
                        if item.get("type") == "tool_result" and _denial(item.get("content")):
                            s.denials += 1
                            open_denials.append(follow_within)
                        if item.get("type") != "tool_use":
                            continue
                        name, inp = str(item.get("name", "")), item.get("input")
                        inp = inp if isinstance(inp, dict) else {}
                        fam = family(name)
                        s.calls[fam] = s.calls.get(fam, 0) + 1
                        s.total_calls += 1
                        look = lookup_family(name)
                        if look:
                            s.lookups[look] += 1
                            s.followed += len(open_denials)
                            open_denials.clear()
                        else:
                            open_denials = [n - 1 for n in open_denials if n > 1]
                        if fam == "grep" and _symbol_pattern(inp.get("pattern")):
                            s.symbol_searches += 1
                        elif fam == "shell":
                            s.symbol_searches += _symbol_searches(_command_text(inp))
                except (AttributeError, TypeError, ValueError):
                    skipped[0] += 1
    except OSError:
        skipped[0] += 1
    s.start = first if first is not None else mtime
    return s


def claude_sessions(earliest: float, follow_within: int, skipped: list[int]) -> list[Session]:
    root = paths.claude_home() / "projects"
    out: list[Session] = []
    if not root.is_dir():
        return out
    for path in sorted(root.rglob("*.jsonl")):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime < earliest:
            continue
        out.append(_claude_session(path, follow_within, skipped, mtime))
    return out
