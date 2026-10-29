"""loadout usage: tool families per agent from local transcripts, counts only."""
import json
import os
from pathlib import Path
import time

import pytest

from loadout import paths, targets, usage
from loadout.__main__ import main

SECRET = "my private prompt text"


def _claude(lines, sub=False, name="s1"):
    folder = paths.claude_home() / "projects" / "-repo"
    path = folder / (f"{name}/subagents/a.jsonl" if sub else f"{name}.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(l) if isinstance(l, dict) else l for l in lines) + "\n")
    return path


# a recent day, so the 14-day window always holds it (a fixed date aged out on 2026-10-29)
RECENT = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 86400))


def _tool(name, **inp):
    return {"type": "assistant", "timestamp": RECENT,
            "message": {"content": [{"type": "tool_use", "name": name, "input": inp}]}}


def _codex(lines, name="rollout-1"):
    path = paths.codex_home() / "sessions" / Path(*RECENT[:10].split("-")) / f"{name}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(l) for l in lines) + "\n")
    return path


def _on(monkeypatch, claude=True, codex=True):
    monkeypatch.setattr(targets, "claude_enabled", lambda: claude)
    monkeypatch.setattr(targets, "codex_enabled", lambda: codex)


def test_claude_main_and_subagent_counts(fake_home, monkeypatch):
    _on(monkeypatch, codex=False)
    _claude([{"type": "user", "message": {"content": SECRET}},
             _tool("mcp__plugin_loadout_serena__find_symbol"), _tool("Bash", command="rg -n record_project src"),
             _tool("Grep", pattern="record_project"), _tool("Read", file_path="x")])
    _claude([_tool("mcp__plugin_loadout_codebase-memory-mcp__search_graph")], sub=True)
    report = usage.collect(14)
    main_ = report["claude"]["main"]
    assert main_["sessions"] == 1 and main_["families"]["serena"]["calls"] == 1
    assert main_["families"]["shell"]["calls"] == 1 and main_["symbol_searches"] == 2
    assert report["claude"]["subagent"]["families"]["codebase-memory"]["sessions"] == 1
    assert SECRET not in json.dumps(report) and SECRET not in usage.render(report)


def test_codex_counts_function_calls_and_mcp_events(fake_home, monkeypatch):
    _on(monkeypatch, claude=False)
    _codex([{"type": "session_meta", "payload": {"timestamp": RECENT, "source": "cli"}},
            {"type": "response_item", "payload": {"type": "function_call", "name": "exec_command",
                                                  "arguments": json.dumps({"cmd": "rg record_project"})}},
            {"type": "event_msg", "payload": {"type": "mcp_tool_call_end",
                                              "invocation": {"server": "serena", "tool": "find_symbol"}}},
            {"type": "response_item", "payload": {"type": "function_call", "name": "mcp__context7__query-docs",
                                                  "arguments": "{}"}}])
    fam = usage.collect(14)["codex"]["main"]["families"]
    assert fam["serena"]["calls"] == 1 and fam["context7"]["calls"] == 1 and fam["shell"]["calls"] == 1


def test_old_sessions_are_outside_the_window(fake_home, monkeypatch):
    _on(monkeypatch, codex=False)
    old = _claude([_tool("mcp__plugin_loadout_serena__find_symbol")], name="old")
    os.utime(old, (time.time() - 30 * 86400,) * 2)
    assert usage.collect(14)["claude"]["main"]["sessions"] == 0


def test_malformed_and_oversized_lines_are_skipped_and_counted(fake_home, monkeypatch):
    _on(monkeypatch, codex=False)
    _claude(["{broken", "x" * 3_000_000, json.dumps(_tool("Read", file_path="a"))])
    report = usage.collect(14)
    assert report["claude"]["skipped_lines"] == 2 and report["claude"]["main"]["families"]["read"]["calls"] == 1


def test_valid_json_with_an_odd_shape_is_skipped_not_a_crash(fake_home, monkeypatch):
    _on(monkeypatch)
    _claude([{"type": "assistant", "message": "oops"},
             {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": "abc"}]}},
             {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Grep", "input": ["x"]}]}},
             json.dumps(_tool("Read", file_path="a"))])
    _codex([{"type": "event_msg", "payload": {"type": "mcp_tool_call_end", "invocation": "s"}},
            {"type": "response_item", "payload": {"type": "function_call", "name": 7, "arguments": ["x"]}}])
    report = usage.collect(14)
    assert report["claude"]["main"]["families"]["read"]["calls"] == 1  # odd fields are tolerated
    assert report["codex"]["skipped_lines"] == 2  # an invocation or a name that cannot be read


def test_a_resumed_session_counts_only_calls_inside_the_window(fake_home, monkeypatch):
    _on(monkeypatch, codex=False)
    old = dict(_tool("mcp__plugin_loadout_serena__find_symbol"), timestamp="2025-01-01T10:00:00Z")
    new = dict(_tool("Read", file_path="a"), timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    _claude([old, new])  # the file was touched today, but one call is from last year
    fam = usage.collect(14)["claude"]["main"]["families"]
    assert fam["serena"]["calls"] == 0 and fam["read"]["calls"] == 1


def test_a_resumed_codex_session_counts_only_calls_inside_the_window(fake_home, monkeypatch):
    _on(monkeypatch, claude=False)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _codex([{"timestamp": "2025-01-01T10:00:00Z", "type": "response_item",
             "payload": {"type": "function_call", "name": "mcp__serena__find_symbol", "arguments": "{}"}},
            {"timestamp": now, "type": "response_item",
             "payload": {"type": "function_call", "name": "mcp__context7__query-docs", "arguments": "{}"}}])
    fam = usage.collect(14)["codex"]["main"]["families"]
    assert fam["serena"]["calls"] == 0 and fam["context7"]["calls"] == 1


@pytest.mark.parametrize("command", ["rg -g '*.py' record_project", "rg -t py record_project",
                                     "grep -A 3 record_project src", "rtk rg -n record_project src"])
def test_searches_with_option_values_count_like_the_hook_counts_them(fake_home, monkeypatch, command):
    _on(monkeypatch, codex=False)
    _claude([_tool("Bash", command=command)])
    assert usage.collect(14)["claude"]["main"]["symbol_searches"] == 1


def test_common_words_are_no_symbol_search_here_either(fake_home, monkeypatch):
    _on(monkeypatch, codex=False)
    _claude([_tool("Bash", command="rg -n error logs"), _tool("Grep", pattern="TODO")])
    assert usage.collect(14)["claude"]["main"]["symbol_searches"] == 0


def test_an_oversized_line_is_skipped_without_reading_it_whole(fake_home, monkeypatch):
    _on(monkeypatch, codex=False)
    path = _claude([json.dumps(_tool("Read", file_path="a"))])
    with path.open("a", encoding="utf-8") as fh:
        fh.write("x" * (usage.MAX_LINE * 3) + "\n")
        fh.write(json.dumps(_tool("Read", file_path="b")) + "\n")
    reads = []
    real = usage._read_record

    def spy(fh):
        line = real(fh)
        reads.append(len(line or ""))
        return line
    monkeypatch.setattr(usage, "_read_record", spy)
    report = usage.collect(14)
    assert report["claude"]["main"]["families"]["read"]["calls"] == 2 and report["claude"]["skipped_lines"] == 1
    assert max(reads) <= usage.MAX_LINE + 1  # never more than one bounded chunk at a time


def test_an_old_codex_subagent_session_with_new_calls_stays_a_subagent(fake_home, monkeypatch):
    _on(monkeypatch, claude=False)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _codex([{"timestamp": "2025-01-01T10:00:00Z", "type": "session_meta",
             "payload": {"timestamp": "2025-01-01T10:00:00Z", "source": {"subagent": "x"}}},
            {"timestamp": now, "type": "response_item",
             "payload": {"type": "function_call", "name": "mcp__serena__find_symbol", "arguments": "{}"}}])
    report = usage.collect(14)["codex"]
    assert report["subagent"]["families"]["serena"]["calls"] == 1 and report["main"]["sessions"] == 0


def test_a_codex_mcp_call_logged_twice_counts_once(fake_home, monkeypatch):
    _on(monkeypatch, claude=False)
    _codex([{"type": "session_meta", "payload": {"timestamp": RECENT}},
            {"type": "response_item", "payload": {"type": "function_call", "name": "mcp__serena__find_symbol",
                                                  "arguments": "{}", "call_id": "c1"}},
            {"type": "event_msg", "payload": {"type": "mcp_tool_call_end", "call_id": "c1",
                                              "invocation": {"server": "serena", "tool": "find_symbol"}}},
            {"type": "event_msg", "payload": {"type": "mcp_tool_call_end", "call_id": "c2",
                                              "invocation": {"server": "serena", "tool": "find_symbol"}}}])
    assert usage.collect(14)["codex"]["main"]["families"]["serena"]["calls"] == 2  # c1 once, c2 once


def test_hint_sessions_follow_the_window_and_include_docs_hints(fake_home, monkeypatch):
    _on(monkeypatch, codex=False)
    state = paths.state_dir() / "tool-hint"
    state.mkdir(parents=True)
    now = time.time()
    (state / "search.json").write_text(json.dumps({"last_hint": 3, "hint_at": now}))
    (state / "docs.json").write_text(json.dumps({"last_docs": 1, "hint_at": now}))
    # a hint three days ago in a session that is still active today (its file was just rewritten)
    (state / "old.json").write_text(json.dumps({"last_hint": 5, "hint_at": now - 3 * 86400}))
    assert usage.collect(14)["hint_sessions"] == 3
    assert usage.collect(1)["hint_sessions"] == 2


def test_codex_symbol_searches_are_counted_in_every_command_shape(fake_home, monkeypatch):
    _on(monkeypatch, claude=False)
    _codex([{"type": "session_meta", "payload": {"timestamp": RECENT, "source": "cli"}},
            {"type": "response_item", "payload": {"type": "function_call", "name": "exec_command",
                                                  "arguments": json.dumps({"cmd": "rg record_project"})}},
            {"type": "response_item", "payload": {"type": "function_call", "name": "shell",
                                                  "arguments": json.dumps({"command": ["bash", "-lc",
                                                                                       "rg -n record_project src"]})}},
            {"type": "response_item", "payload": {"type": "function_call", "name": "shell",
                                                  "arguments": json.dumps({"command": ["ls", "-la"]})}}])
    assert usage.collect(14)["codex"]["main"]["symbol_searches"] == 2


def test_an_agent_that_is_off_is_not_read(fake_home, monkeypatch):
    _on(monkeypatch, claude=False, codex=True)
    _claude([_tool("Read", file_path="a")])
    _codex([{"type": "session_meta", "payload": {"timestamp": RECENT}}])
    report = usage.collect(14)
    assert "claude" not in report and report["codex"]["main"]["sessions"] == 1


def test_hint_sessions_come_from_the_hint_state(fake_home, monkeypatch):
    _on(monkeypatch, codex=False)
    state = paths.state_dir() / "tool-hint"
    state.mkdir(parents=True)
    (state / "a.json").write_text(json.dumps({"last_hint": 3, "calls": 7, "hint_at": time.time()}))
    (state / "b.json").write_text(json.dumps({"calls": 2}))
    assert usage.collect(14)["hint_sessions"] == 1


def test_cli_legacy_prints_a_table_and_json(fake_home, monkeypatch, capsys):
    _on(monkeypatch, codex=False)
    _claude([_tool("mcp__plugin_loadout_serena__find_symbol")])
    assert main(["usage", "--legacy"]) == 0
    assert "Serena" in capsys.readouterr().out
    assert main(["usage", "--legacy", "--days", "7", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["days"] == 7


def test_cli_exits_1_without_any_history(fake_home, monkeypatch, capsys):
    _on(monkeypatch)
    assert main(["usage"]) == 1
    assert "no session history" in capsys.readouterr().err


def test_usage_is_read_only_and_never_migrates_or_creates_state(fake_home, monkeypatch):
    from loadout import __main__ as entry
    assert "usage" in entry.READ_ONLY and "usage" in entry.EXEMPT
    _on(monkeypatch, codex=False)
    _claude([_tool("Read", file_path="a")])
    main(["usage"])
    assert not paths.state_dir().exists()


def _denial(text):
    return {"type": "user", "timestamp": RECENT,
            "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "is_error": True, "content": text}]}}


def test_usage_counts_serena_denials_per_group(fake_home, monkeypatch):
    _on(monkeypatch, codex=False)
    deny = "Too many consecutive grep calls without using symbolic tools. You can continue using grep now"
    _claude([_tool("Bash", command="rg -n record_project src"), _denial(deny), _denial(deny)])
    _claude([_tool("Read", file_path="a.py"), _denial("Too many consecutive read calls of files without using")],
            sub=True)
    _claude([_tool("Bash", command="ls"), _denial("some other error")], name="s2")
    report = usage.collect(14)
    assert report["claude"]["main"]["serena_denials"] == 1
    assert report["claude"]["subagent"]["serena_denials"] == 1
    assert "sessions with a Serena reminder: 1" in usage.render(report)


def test_serena_denial_in_claude_codes_real_format_counts(fake_home, monkeypatch):
    # what Claude Code 2.1.305 records for a PreToolUse deny (seen live with this branch's remind hook)
    _on(monkeypatch, codex=False)
    real = ("PreToolUse:Grep hook error: Too many consecutive non-symbolic tool calls (mixed grep and read). "
            "You can continue using these tools now if needed, the counter was reset.")
    _claude([_tool("Grep", pattern="record_project"), _denial(real)], sub=True)
    _claude([_tool("Bash", command="echo"), _denial("grep found: Too many consecutive grep calls? no")], name="s3")
    report = usage.collect(14)
    assert report["claude"]["subagent"]["serena_denials"] == 1
    assert report["claude"]["main"]["serena_denials"] == 0


def test_chained_symbol_searches_count_one_each(fake_home, monkeypatch):
    _on(monkeypatch, codex=False)
    _claude([_tool("Bash", command="rg alpha_fn src; rg beta_fn src")])
    assert usage.collect(14)["claude"]["main"]["symbol_searches"] == 2
