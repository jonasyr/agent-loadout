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


def _cwrite(lines, name="c1"):
    path = paths.codex_home() / "sessions" / "2026" / "10" / "14" / f"{name}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(l) for l in lines) + "\n")
    return path


def _fcall(name, call_id, **extra):
    return {"type": "response_item", "payload": {"type": "function_call", "name": name, "call_id": call_id,
                                                 "arguments": "{}", **extra}}


def _crun(follow=5):
    return us.codex_sessions(0, follow, [0])


def _meta(source="cli"):
    return {"type": "session_meta", "timestamp": "2026-10-14T10:00:00Z", "payload": {"source": source}}


def _cuser(text):
    return {"type": "response_item", "payload": {"type": "message", "role": "user",
                                                 "content": [{"type": "input_text", "text": text}]}}


def test_codex_lookups_and_calls(fake_home):
    _cwrite([_meta(),
             {"type": "event_msg", "payload": {"type": "mcp_tool_call_end", "call_id": "a",
                                               "invocation": {"server": "serena", "tool": "find_symbol"}}},
             _fcall("mcp__serena__find_symbol", "a")])
    (s,) = _crun()
    assert s.agent == "codex" and s.lookups["serena"] == 1 and s.calls["serena"] == 1 and s.total_calls == 1


def test_codex_mcp_end_alone_counts_and_non_lookup_does_not(fake_home):
    end = lambda tool, cid: {"type": "event_msg", "payload": {"type": "mcp_tool_call_end", "call_id": cid,
                                                              "invocation": {"server": "serena", "tool": tool}}}
    _cwrite([_meta(), end("find_symbol", "a"), end("initial_instructions", "b")])
    (s,) = _crun()
    assert s.calls["serena"] == 2 and s.lookups["serena"] == 1


def test_codex_denial_followed(fake_home):
    out = {"type": "response_item", "payload": {"type": "function_call_output", "output": DENY}}
    _cwrite([_meta(), out, _fcall("exec_command", "x"), _fcall("mcp__serena__find_symbol", "y")])
    (s,) = _crun()
    assert s.denials == 1 and s.followed == 1
    _cwrite([_meta(), out, _fcall("exec_command", "x")])
    assert [x.followed for x in _crun() if x.id == "c1"] == [0]


def test_codex_subagent_kind(fake_home):
    _cwrite([_meta({"subagent": {"thread_spawn": {}}})])
    (s,) = _crun()
    assert s.kind == "subagent"
    _cwrite([_meta("cli")], name="c2")
    assert {x.id: x.kind for x in _crun()} == {"c1": "subagent", "c2": "main"}


def test_codex_prompted(fake_home):
    # Real Codex files hold user-input records (response_item, role user), so prompted is a bool.
    _cwrite([_meta({"subagent": {}}), _cuser("<environment_context>serena</environment_context>"),
             _cuser("Use find_symbol to look.")])
    _cwrite([_meta({"subagent": {}}), _cuser("fix the bug")], name="c2")
    _cwrite([_meta("cli"), _cuser("serena")], name="c3")
    got = {x.id: x.prompted for x in _crun()}
    assert got == {"c1": True, "c2": False, "c3": None}


def _cagent(text, author="parent", recipient="child"):
    return {"type": "response_item", "payload": {"type": "agent_message", "author": author, "recipient": recipient,
                                                 "content": [{"type": "text", "text": text}]}}


def test_codex_subagent_prompt_is_the_parents_agent_message(fake_home):
    # the real shape (2026-10, keys only): injected `<...>` context as user messages, then the parent's task as
    # an agent_message before any tool call
    _cwrite([_meta({"subagent": {}}), _cuser("<other_tag>context</other_tag>"),
             _cuser("<environment_context>x</environment_context>"), _cagent("Use find_symbol for X")])
    _cwrite([_meta({"subagent": {}}), _cuser("<other_tag>serena</other_tag>"), _cagent("fix the README")],
            name="c2")
    _cwrite([_meta({"subagent": {}}), _cuser("<tag>x</tag>"), _fcall("exec_command", "k1"),
             _cagent("now use serena")], name="c3")  # an agent_message after work began is no task prompt
    got = {x.id: x.prompted for x in _crun()}
    assert got == {"c1": True, "c2": False, "c3": None}


def test_consecutive_denials_share_the_next_lookup(fake_home):
    _write([_deny(), _deny(), _tool(SERENA)])
    s = _run()[0]
    assert (s.denials, s.followed) == (2, 2)


def test_a_lookup_as_the_very_next_call_follows(fake_home):
    _write([_deny(), _tool(CBM)])
    s = _run(follow=1)[0]
    assert s.followed == 1


def test_a_lookup_named_tool_of_another_server_is_no_lookup(fake_home):
    _write([_tool("mcp__plugin_context7_context7__search_code"), _tool("mcp__other__find_symbol")])
    assert _run()[0].lookups == {"serena": 0, "codebase-memory": 0}
