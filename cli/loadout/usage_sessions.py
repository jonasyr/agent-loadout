"""One record per transcript, counts only (never content). See docs/superpowers/specs/2026-10-24-usage-before-after-design.md."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime

from . import paths
from .usage import (CODEX_SHELL, MAX_LINE, _command_text, _denial, _read_record, _symbol_pattern, _symbol_searches,
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
    active: list[int] = field(default_factory=list)  # the seconds (int epoch) with an event, sorted


def active_between(s: Session, start: float, end: float) -> bool:
    """Whether the session had an event in [start, end), to the second."""
    return any(start <= t < end for t in s.active)


def lookup_family(name: str) -> str | None:
    tool = name.rsplit("__", 1)[-1]  # `mcp__serena__find_symbol`, Codex's `serena__find_symbol`, or a bare name
    for fam, tools in LOOKUP_TOOLS.items():
        if tool in tools and family(name) == fam:
            return fam
    return None


def _stamp(obj: dict) -> float | None:
    payload = obj.get("payload") if isinstance(obj.get("payload"), dict) else {}
    value = obj.get("timestamp") or payload.get("timestamp")  # Codex keeps some stamps in its payload
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
    act: set[int] = set()  # event seconds, kept as s.active at the end
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
                if t is not None:
                    act.add(int(t))
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
    s.active = sorted(act)  # a plain list, so the record stays JSON-serialisable
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


# Where a Codex subagent's task prompt lives (checked against one real session file, record types and payload
# key names only): there are user-input records, a `response_item` whose payload has `type: "message"` and
# `role: "user"`, with `content` a list of text parts (or an `event_msg` of `user_message`). Codex also logs
# injected context (AGENTS.md, environment, other `<tag>` blocks) as user messages; those are skipped. Checked on
# real subagent sessions (2026-10-24, record kinds and keys only): the parent's task arrives as a `response_item`
# of type `agent_message` (author and recipient differ) before the first tool call. That message decides
# `prompted`; without one, the first plain user text does; a subagent with neither keeps prompted=None.
_CODEX_CONTEXT = ("<environment_context", "# agents.md instructions", "<user_instructions", "<permissions")


def _context(text: str) -> bool:
    """Injected context, not a person's or a parent's task: a known prefix or any leading `<tag>`."""
    t = text.lstrip().lower()
    return t.startswith(_CODEX_CONTEXT) or t.startswith("<")


def _codex_agent_text(obj: dict, p: dict) -> str | None:
    """The text of an inter-agent message (a parent's task to this subagent)."""
    if obj.get("type") != "response_item" or p.get("type") != "agent_message" or p.get("author") == p.get("recipient"):
        return None
    parts = [i["text"] for i in p.get("content") or [] if isinstance(i, dict) and isinstance(i.get("text"), str)]
    return " ".join(parts) if parts else None


def _codex_user_text(obj: dict, p: dict) -> str | None:
    if obj.get("type") == "event_msg" and p.get("type") == "user_message":
        m = p.get("message")
        return m if isinstance(m, str) and not _context(m) else None
    if obj.get("type") == "response_item" and p.get("type") == "message" and p.get("role") == "user":
        parts = [i["text"] for i in p.get("content") or [] if isinstance(i, dict)
                 and i.get("type") in ("input_text", "text") and isinstance(i.get("text"), str)]
        text = " ".join(parts) if parts else None
        if text is not None and not _context(text):
            return text
    return None


def _codex_session(path, follow_within: int, skipped: list[int], mtime: float) -> Session:
    s = Session(path.stem, "codex", "main", mtime)
    first: float | None = None
    act: set[int] = set()  # event seconds, kept as s.active at the end
    open_denials: list[int] = []
    mcp_ids: set[str] = set()  # an MCP call can be logged twice (function_call and its end event), in either order
    end_ids: set[str] = set()
    need_prompt = False
    sub = False
    user_text: str | None = None  # the first plain user text: the fallback prompt
    agent_text: str | None = None  # the parent's task, an agent_message before the first tool call

    def call(name: str, fam: str, look: str | None) -> None:
        nonlocal open_denials
        s.calls[fam] = s.calls.get(fam, 0) + 1
        s.total_calls += 1
        if look:
            s.lookups[look] += 1
            s.followed += len(open_denials)
            open_denials = []
        else:
            open_denials = [n - 1 for n in open_denials if n > 1]

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
                if t is not None:
                    act.add(int(t))
                try:
                    p = obj.get("payload") if isinstance(obj.get("payload"), dict) else {}
                    if obj.get("type") == "session_meta":
                        sub = "subagent" in json.dumps(p.get("source", "")).lower()
                        if sub:
                            s.kind, need_prompt = "subagent", True
                    if need_prompt:
                        if user_text is None:
                            user_text = _codex_user_text(obj, p)
                        if agent_text is None and s.total_calls == 0:
                            agent_text = _codex_agent_text(obj, p)
                    kind = p.get("type")
                    if kind in ("function_call", "custom_tool_call"):
                        name = p.get("name")
                        if not isinstance(name, str):
                            raise TypeError("tool name")
                        args = p.get("arguments") or p.get("input") or ""
                        fam = "shell" if name in CODEX_SHELL else family(name)
                        if fam not in ("shell", "other") and isinstance(p.get("call_id"), str):
                            if p["call_id"] in end_ids:
                                continue  # its end event was already counted
                            mcp_ids.add(p["call_id"])
                        call(name, fam, lookup_family(name))
                        if fam == "shell":
                            s.symbol_searches += _symbol_searches(_command_text(args))
                    elif kind in ("function_call_output", "custom_tool_call_output"):
                        out_ = p.get("output")
                        if _denial(out_.get("content") if isinstance(out_, dict) else out_):
                            s.denials += 1
                            open_denials.append(follow_within)
                    elif kind == "mcp_tool_call_end":
                        invocation = p.get("invocation")
                        if not isinstance(invocation, dict):
                            raise TypeError("invocation")
                        if p.get("call_id") in mcp_ids:
                            continue
                        if isinstance(p.get("call_id"), str):
                            end_ids.add(p["call_id"])
                        server = str(invocation.get("server", ""))
                        fam = family(server)
                        if fam != "other":
                            tool = str(invocation.get("tool", ""))
                            look = fam if fam in LOOKUP_TOOLS and tool in LOOKUP_TOOLS[fam] else None
                            call(tool, fam, look)
                except (AttributeError, TypeError, ValueError):
                    skipped[0] += 1
    except OSError:
        skipped[0] += 1
    prompt = agent_text if agent_text is not None else user_text
    if need_prompt and prompt is not None:
        s.prompted = any(w in prompt.lower() for w in PROMPT_WORDS)
    s.start = first if first is not None else mtime
    s.active = sorted(act)  # a plain list, so the record stays JSON-serialisable
    return s


def codex_sessions(earliest: float, follow_within: int, skipped: list[int]) -> list[Session]:
    root = paths.codex_home() / "sessions"
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
        out.append(_codex_session(path, follow_within, skipped, mtime))
    return out
