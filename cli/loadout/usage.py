"""`loadout usage`: how often the agents used each tool family in local transcripts (counts only, read-only).
See docs/reference/cli.md#loadout-usage."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING

from . import paths, searches, targets

if TYPE_CHECKING:
    from .usage_sessions import Session

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
    return {"sessions": 0, "calls": 0, "symbol_searches": 0, "serena_denials": 0,
            "families": {n: {"calls": 0, "sessions": 0} for n in NAMES}}


DENIALS = ("Too many consecutive grep calls", "Too many consecutive read calls",
           "Too many consecutive non-symbolic tool calls")  # Serena 2.1.0's `remind` deny reasons (serena/hooks.py)


def _symbol_searches(text: str) -> int:
    return searches.count_symbol_searches(text or "")


def _symbol_pattern(pattern: object) -> bool:
    return searches.symbol(pattern) is not None


_HOOK_ERROR = re.compile(r"^PreToolUse:\S+ hook error: ")


def _denial(content: object) -> bool:
    """A tool result that is Serena's reminder (its PreToolUse deny reason, shown to the agent)."""
    if isinstance(content, list):
        content = " ".join(c.get("text", "") for c in content if isinstance(c, dict) and isinstance(c.get("text"), str))
    if not isinstance(content, str):
        return False
    text = _HOOK_ERROR.sub("", content.lstrip(), count=1)  # Claude Code: "PreToolUse:Grep hook error: <reason>"
    return text.startswith(DENIALS)


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
    if obj.get("type") == "session_meta":
        return True  # it classifies the session (main or subagent), however old; it holds no tool calls
    payload = obj.get("payload") if isinstance(obj.get("payload"), dict) else {}
    stamp = obj.get("timestamp") or payload.get("timestamp")
    if not isinstance(stamp, str):
        return True
    try:
        from datetime import datetime
        return datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp() >= cutoff
    except (ValueError, OverflowError, OSError):
        return True


def _add(group: dict, calls: dict[str, int], found: int, denied: bool = False) -> None:
    group["sessions"] += 1
    group["symbol_searches"] += found
    group["serena_denials"] += denied
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
        found, denied = 0, False
        for obj in _lines(path, skipped, cutoff):
            try:  # valid JSON of an unexpected shape is skipped and counted, never a crash
                message = obj.get("message") if obj.get("type") in ("assistant", "user") else None
                content = message.get("content") if isinstance(message, dict) else None
                for item in content if isinstance(content, list) else []:
                    if isinstance(item, dict) and item.get("type") == "tool_result" and not denied:
                        denied = _denial(item.get("content"))
                    if not isinstance(item, dict) or item.get("type") != "tool_use":
                        continue
                    name, inp = str(item.get("name", "")), item.get("input")
                    inp = inp if isinstance(inp, dict) else {}
                    fam = family(name)
                    calls[fam] = calls.get(fam, 0) + 1
                    if fam == "grep" and _symbol_pattern(inp.get("pattern")):
                        found += 1
                    elif fam == "shell":
                        found += _symbol_searches(_command_text(inp))
            except (AttributeError, TypeError, ValueError):
                skipped[0] += 1
        _add(out["subagent" if "subagents" in path.parts else "main"], calls, found, denied)
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
        found, sub, mcp_ids, denied = 0, False, set(), False  # an MCP call can be logged twice: function_call and its end event
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
                    if fam == "shell":
                        found += _symbol_searches(_command_text(args))
                elif kind in ("function_call_output", "custom_tool_call_output") and not denied:
                    out_ = p.get("output")
                    denied = _denial(out_.get("content") if isinstance(out_, dict) else out_)
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
        _add(out["subagent" if sub else "main"], calls, found, denied)
    out["skipped_lines"] = skipped[0]
    return out


def _hint_sessions(cutoff: float, until: float | None = None) -> int:
    """Sessions whose last docs hint was shown inside the window (`hint_at`, written by the hook). The
    hook keeps its state files for 7 days, so a longer window still counts only about the last week."""
    folder = paths.state_dir() / "tool-hint"
    n = 0
    for path in folder.glob("*.json") if folder.is_dir() else []:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        shown = data.get("hint_at") if isinstance(data, dict) else None
        if isinstance(shown, (int, float)) and not isinstance(shown, bool) and shown >= cutoff \
                and (until is None or shown < until):
            n += 1
    return n


# the transcript helpers usage_sessions shares (public names, so a rename here fails at import, not in a test)
read_record = _read_record
is_denial = _denial
symbol_pattern = _symbol_pattern
count_symbol_searches = _symbol_searches
command_text = _command_text


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
            lines.append(f"    sessions with a Serena reminder: {g['serena_denials']}")
        if report[agent]["skipped_lines"]:
            lines.append(f"  {title}: {report[agent]['skipped_lines']} unreadable lines skipped")
    lines.append(f"  sessions with a loadout tool hint: {report['hint_sessions']}")
    return "\n".join(lines)


SHARE_POINTS = 0.05
RATE_RATIO = 0.20
SHARE_FAMILIES = ("serena", "codebase-memory", "context7", "microsoft-learn")


def metrics(sessions: "list[Session]", min_calls: int) -> dict:
    """Sums over the counted sessions (those with at least `min_calls` calls); the rest are `tiny`."""
    counted = [s for s in sessions if s.total_calls >= min_calls]
    out = _group()
    out["tiny"] = len(sessions) - len(counted)
    out["sessions"] = len(counted)
    lookups = {"serena": 0, "codebase-memory": 0}
    denials = followed = 0
    for s in counted:
        out["calls"] += s.total_calls
        out["symbol_searches"] += s.symbol_searches
        out["serena_denials"] += 1 if s.denials else 0
        denials += s.denials
        followed += s.followed
        for k in lookups:
            lookups[k] += s.lookups.get(k, 0)
        for n in NAMES:
            if s.calls.get(n, 0):
                out["families"][n]["calls"] += s.calls[n]
                out["families"][n]["sessions"] += 1
    n = len(counted)
    found = sum(lookups.values())
    out["lookups"] = lookups
    out["code_tool_share"] = found / (found + out["symbol_searches"]) if found + out["symbol_searches"] else None
    out["denials"], out["followed"] = denials, followed
    out["follow_through"] = followed / denials if denials else None
    out["per_session"] = {"symbol_searches": out["symbol_searches"] / n if n else 0.0,
                          "calls": out["calls"] / n if n else 0.0}
    out["family_share"] = {k: (v["sessions"] / n if n else 0.0) for k, v in out["families"].items()}
    return out


def _arrow_share(b: float, a: float) -> str:
    d = round(a - b, 9)
    return "↑" if d >= SHARE_POINTS else "↓" if d <= -SHARE_POINTS else "="


def _arrow_rate(b: float, a: float) -> str:
    if b == 0:
        return "new" if a > 0 else "="
    r = round(a / b, 9)  # symmetric: a change of at least RATE_RATIO either way counts
    return "↑" if r >= 1 + RATE_RATIO else "↓" if r <= 1 - RATE_RATIO else "="


def change(before: dict, after: dict, min_sessions: int) -> dict:
    """One arrow per compared metric; every metric reads "too few sessions" when either side is small."""
    pairs = [("code_tool_share", before.get("code_tool_share"), after.get("code_tool_share"), _arrow_share),
             ("follow_through", before.get("follow_through"), after.get("follow_through"), _arrow_share)]
    for fam in SHARE_FAMILIES:
        pairs.append((f"family_share.{fam}", before.get("family_share", {}).get(fam, 0.0),
                      after.get("family_share", {}).get(fam, 0.0), _arrow_share))
    for key in ("symbol_searches", "calls"):
        pairs.append((f"per_session.{key}", before.get("per_session", {}).get(key, 0.0),
                      after.get("per_session", {}).get(key, 0.0), _arrow_rate))
    few = before.get("sessions", 0) < min_sessions or after.get("sessions", 0) < min_sessions
    out = {}
    for name, b, a, fn in pairs:
        out[name] = "too few sessions" if few else "—" if b is None or a is None else fn(b, a)
    return out


ROWS = ("main", "subagent", "subagent_prompted", "subagent_unprompted")


def _rows(sessions: "list[Session]", min_calls: int) -> tuple[dict, bool]:
    sub = [s for s in sessions if s.kind == "subagent"]
    groups = {"main": [s for s in sessions if s.kind == "main"], "subagent": sub,
              "subagent_prompted": [s for s in sub if s.prompted is True],
              "subagent_unprompted": [s for s in sub if s.prompted is False]}
    # True: every subagent's prompt was read; False: at least one was not; None: no subagents to split
    known = (all(s.prompted is not None for s in sub)) if sub else None
    return {k: metrics(v, min_calls) for k, v in groups.items()}, known


def _agent_block(after: "list[Session]", skipped: list[int], min_calls: int,
                 before: "list[Session] | None" = None, min_sessions: int = 20) -> dict:
    rows, known = _rows(after, min_calls)
    block: dict = dict(rows)
    states = [known]
    if before is not None:
        brows, bknown = _rows(before, min_calls)
        states.append(bknown)
        block["before"] = brows
        block["change"] = {k: change(brows[k], rows[k], min_sessions) for k in ROWS}
    block["prompted_known"] = True in states and False not in states  # split only when every subagent is classified
    block["skipped_lines"] = skipped[0]
    return block


def report(after_start: float, after_end: float, before_start: "float | None", *, min_calls: int = 5,
           follow_within: int = 5, min_sessions: int = 20, now: "float | None" = None, days: "int | None" = None,
           keep: "list | None" = None) -> dict:
    """Before/after windows over per-session records; each transcript is read once. A session belongs to the
    window holding its start: after is [after_start, min(after_end, now)), before is [before_start, after_start).
    `keep`, when given, receives every session read (one read per run, also for `--sessions`)."""
    from . import usage_sessions
    now = time.time() if now is None else now
    end = max(after_start, min(after_end, now))  # a start in the future is an empty window, never a negative one
    windows: dict = {"after": {"start": after_start, "end": end, "days": round((end - after_start) / 86400, 2),
                               "partial": end < after_end}}
    if before_start is not None:
        windows["before"] = {"start": before_start, "end": after_start, "partial": False,
                             "days": round((after_start - before_start) / 86400, 2)}
    span = max(0.0, round((after_end - after_start) / 86400, 2))
    out: dict = {"days": days if days is not None else (int(span) if span == int(span) else span), "windows": windows,
                 "thresholds": {"min_calls": min_calls, "follow_within": follow_within,
                                "min_sessions": min_sessions},
                 }
    earliest = before_start if before_start is not None else after_start
    readers = (("claude", targets.claude_enabled, usage_sessions.claude_sessions, paths.claude_home() / "projects"),
               ("codex", targets.codex_enabled, usage_sessions.codex_sessions, paths.codex_home() / "sessions"))
    for name, enabled, read, root in readers:
        if not enabled() or not root.is_dir():
            continue
        skipped = [0]
        found = read(earliest, follow_within, skipped)
        if keep is not None:
            keep.extend(found)
        aft = [s for s in found if after_start <= s.start < end]
        bef = [s for s in found if before_start <= s.start < after_start] if before_start is not None else None
        out[name] = _agent_block(aft, skipped, min_calls, bef, min_sessions)
        first = earliest  # sessions that started before the first window but ran in it: not counted, but named
        out[name]["started_earlier"] = {k: sum(1 for s in found if s.start < first and s.kind == k
                                               and usage_sessions.active_between(s, first, end))
                                        for k in ("main", "subagent")}
    out["hint_sessions"] = _hint_sessions(after_start, end)  # [after_start, end): the after window only
    return out


MOMENT_FORMS = ("%Y-%m-%d", "%Y-%m-%dT%H:%M")


def parse_moment(text: str) -> float:
    """`YYYY-MM-DD` is local midnight, `YYYY-MM-DDTHH:MM` local time."""
    from datetime import datetime
    for form in MOMENT_FORMS:
        try:
            return datetime.strptime(text, form).timestamp()
        except ValueError:
            continue
    raise ValueError("use YYYY-MM-DD or YYYY-MM-DDTHH:MM")


def _shift(moment: float, days: int) -> float:
    """MOMENT moved by whole local calendar days: the same wall-clock time, also across a DST switch."""
    from datetime import datetime, timedelta
    return (datetime.fromtimestamp(moment) + timedelta(days=days)).timestamp()


def plan_windows(days: int, around: "float | None", since: "float | None", now: float) -> tuple:
    """(after_start, after_end, before_start) for the flags; --around has a before window, the rest do not."""
    if around is not None:
        return around, _shift(around, days), _shift(around, -days)
    if since is not None:
        return since, now, None
    return _shift(now, -days), now, None


def _moment(t: float) -> str:
    from datetime import datetime
    d = datetime.fromtimestamp(t)
    return d.strftime("%Y-%m-%d") if (d.hour, d.minute) == (0, 0) else d.strftime("%Y-%m-%d %H:%M")


def _days(n: float) -> str:
    return f"{n:g} day" + ("" if n == 1 else "s")


def _pct(v: "float | None") -> str:
    return "—" if v is None else f"{round(v * 100)}%"


def _cell(g: dict, metric: str) -> str:
    if metric == "code":
        found = sum(g["lookups"].values())
        return f"{_pct(g['code_tool_share'])} ({found}/{found + g['symbol_searches']})"
    if metric == "follow":
        return f"{_pct(g['follow_through'])} ({g['followed']}/{g['denials']})"
    if not g["sessions"]:  # nothing counted: no share and no rate
        return "—" if metric == "symbol" else "— (0/0)"
    if metric == "symbol":
        return f"{g['per_session']['symbol_searches']:.1f}"
    fam = metric
    return f"{_pct(g['family_share'][fam])} ({g['families'][fam]['sessions']}/{g['sessions']})"


def _sessions_cell(g: dict) -> str:
    return f"{g['sessions']}" + (f" (+{g['tiny']} tiny)" if g["tiny"] else "")


ROW_TITLES = {"main": "main", "subagent": "subagent", "subagent_prompted": "subagent prompted",
              "subagent_unprompted": "subagent not prompted"}
METRIC_ROWS = (("sessions", "sessions counted", None),
               ("code", "code-tool share", "code_tool_share"),
               ("follow", "follow-through", "follow_through"),
               ("serena", "sessions with Serena", "family_share.serena"),
               ("codebase-memory", "sessions with cbm", "family_share.codebase-memory"),
               ("context7", "sessions with Context7", "family_share.context7"),
               ("microsoft-learn", "sessions with MS Learn", "family_share.microsoft-learn"),
               ("symbol", "symbol searches/session", "per_session.symbol_searches"))


def _has_subagents(block: dict) -> bool:
    """Whether an agent's block holds any subagent session (counted or tiny) in either window."""
    rows = [block.get("subagent"), (block.get("before") or {}).get("subagent")]
    return any(r and r["sessions"] + r["tiny"] for r in rows)


def render_report(rep: dict) -> str:
    w = rep["windows"]
    lines = []
    for key in ("before", "after"):
        if key in w:
            x = w[key]
            label = key if "before" in w else "window"  # a single window is not "after" anything
            lines.append(f"{label:<6} {_moment(x['start'])} to {_moment(x['end'])}  ({_days(x['days'])}"
                         + (", partial)" if x["partial"] else ")"))
    t = rep["thresholds"]
    lines.append(f"counted: sessions with at least {t['min_calls']} tool calls; arrows need {t['min_sessions']} "
                 f"sessions on each side")
    for agent, title in (("claude", "Claude Code"), ("codex", "Codex")):
        if agent not in rep:
            continue
        blk = rep[agent]
        for row in ROWS:
            if row in ("subagent_prompted", "subagent_unprompted") and not blk["prompted_known"]:
                continue
            after, before = blk[row], blk.get("before", {}).get(row)
            if not (after["sessions"] + after["tiny"] or (before and before["sessions"] + before["tiny"])):
                continue
            lines.append("")
            lines.append(f"{title} {ROW_TITLES[row]}")
            for metric, label, ckey in METRIC_ROWS:
                fn = _sessions_cell if metric == "sessions" else (lambda g, m=metric: _cell(g, m))
                text = fn(after)
                if before is not None:
                    text = f"{fn(before)} → {text}"
                    if ckey:
                        text += f"  {blk['change'][row][ckey]}"
                lines.append(f"  {label:<26}{text}")
    lines.append("")
    for agent, title in (("claude", "Claude Code"), ("codex", "Codex")):
        early = rep.get(agent, {}).get("started_earlier") or {}
        if any(early.values()):
            lines.append(f"{title}: {early['main']} main, {early['subagent']} subagent sessions started before "
                         "the window, not counted (see --sessions)")
    lines.append(f"sessions with a loadout tool hint (after window): {rep['hint_sessions']}")
    for agent, title in (("claude", "Claude Code"), ("codex", "Codex")):
        if agent in rep and rep[agent]["skipped_lines"]:
            lines.append(f"{title}: {rep[agent]['skipped_lines']} unreadable lines skipped")
    if "codex" in rep and not rep["codex"]["prompted_known"] and _has_subagents(rep["codex"]):
        lines.append("Codex subagents are not split: their prompt is not in the session file")
    return "\n".join(lines)


def render_sessions(sessions: "list[Session]", windows: dict, min_calls: int) -> str:
    def where(s) -> str:
        for key in ("before", "after"):
            x = windows.get(key)
            if x and x["start"] <= s.start < x["end"]:
                return key
        return "outside"
    lines = []
    for s in sorted(sessions, key=lambda s: (s.start, s.id)):
        found = sum(s.lookups.values())
        share = f"{round(100 * found / (found + s.symbol_searches))}%" if found + s.symbol_searches else "—"
        prompted = "—" if s.prompted is None else "yes" if s.prompted else "no"
        lines.append("  ".join([
            s.id, s.agent, s.kind, "counted" if s.total_calls >= min_calls else "tiny", where(s),
            f"lookups={s.lookups.get('serena', 0)}/{s.lookups.get('codebase-memory', 0)}",
            f"symbol={s.symbol_searches}", f"share={share}", f"denials={s.denials} followed={s.followed}",
            f"prompted={prompted}"]))
    return "\n".join(lines)
