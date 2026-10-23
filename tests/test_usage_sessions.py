"""usage_sessions: one counts-only Session per transcript."""
import dataclasses
import json
import os
from datetime import datetime

from loadout import paths, targets, usage, usage_sessions as us

SERENA = "mcp__plugin_loadout_serena__find_symbol"
CBM = "mcp__plugin_loadout_codebase-memory-mcp__search_graph"
DENY = "PreToolUse:Grep hook error: Too many consecutive grep calls (3)"


def _write(lines, sub=False, name="s1"):
    folder = paths.claude_home() / "projects" / "-repo"
    path = folder / (f"{name}/subagents/a.jsonl" if sub else f"{name}.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(l) for l in lines) + "\n")
    return path


def _tool(name, ts="2026-10-14T10:00:00Z", **inp):
    rec = {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name, "input": inp}]}}
    if ts:
        rec["timestamp"] = ts
    return rec


def _deny():
    return {"type": "user", "timestamp": "2026-10-14T10:00:00Z",
            "message": {"content": [{"type": "tool_result", "content": DENY}]}}


def _user(text):
    return {"type": "user", "timestamp": "2026-10-14T10:00:00Z", "message": {"content": text}}


def _run(follow=5):
    skipped = [0]
    return us.claude_sessions(0, follow, skipped)


def test_lookups_count_only_lookup_tools(fake_home):
    _write([_tool(SERENA), _tool(SERENA), _tool("mcp__serena__initial_instructions"), _tool(CBM),
            _tool("mcp__plugin_loadout_codebase-memory-mcp__index_status")])
    (s,) = _run()
    assert s.lookups == {"serena": 2, "codebase-memory": 1} and s.calls["serena"] == 3 and s.total_calls == 5


def test_denial_followed_within_n(fake_home):
    _write([_deny(), _tool("Bash", command="ls"), _tool("Read", file_path="x"), _tool(SERENA)])
    (s,) = _run()
    assert s.denials == 1 and s.followed == 1
    (s,) = _run(follow=2)
    assert s.denials == 1 and s.followed == 0


def test_denial_at_the_end_is_not_followed(fake_home):
    _write([_deny(), _tool("Bash", command="ls")])
    (s,) = _run()
    assert s.denials == 1 and s.followed == 0


def test_prompted_subagent(fake_home):
    _write([_user("use Serena find_symbol")], sub=True, name="a")
    _write([_user("fix the README")], sub=True, name="b")
    _write([_user("use Serena")], name="m")
    by_kind = {}
    for s in _run():
        by_kind.setdefault(s.kind, []).append(s.prompted)
    assert sorted(by_kind["subagent"]) == [False, True] and by_kind["main"] == [None]


def test_subagent_context_attachment_is_not_the_prompt(fake_home):
    _write([{"type": "attachment", "attachment": {"type": "hook_additional_context", "content": [SERENA]}},
            _user("fix the README")], sub=True)
    (s,) = _run()
    assert s.prompted is False


def test_start_is_the_earliest_timestamp(fake_home):
    _write([_tool("Read", ts="2026-10-14T12:00:00Z"), _tool("Read", ts="2026-10-14T09:00:00Z")])
    (s,) = _run()
    assert s.start == datetime.fromisoformat("2026-10-14T09:00:00+00:00").timestamp()


def test_a_session_without_timestamps_starts_at_file_mtime(fake_home):
    path = _write([_tool("Read", ts=None)])
    os.utime(path, (1_700_000_000, 1_700_000_000))
    (s,) = _run()
    assert s.start == 1_700_000_000


def test_symbol_searches_match_todays_counter(fake_home, monkeypatch):
    monkeypatch.setattr(targets, "claude_enabled", lambda: True)
    monkeypatch.setattr(targets, "codex_enabled", lambda: False)
    _write([_tool("Bash", command="rg -n record_project src"), _tool("Grep", pattern="record_project"),
            _tool("Read", file_path="x")])
    (s,) = _run()
    assert s.symbol_searches == usage.collect(14)["claude"]["main"]["symbol_searches"] == 2


def test_no_content_is_kept(fake_home):
    _write([_user("SECRET-PROMPT"), _tool("Bash", command="echo SECRET-PROMPT")], sub=True)
    (s,) = _run()
    assert "SECRET-PROMPT" not in json.dumps(dataclasses.asdict(s))
