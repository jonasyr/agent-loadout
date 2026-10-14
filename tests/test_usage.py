"""loadout usage: tool families per agent from local transcripts, counts only."""
import json
import os
import time

from loadout import paths, targets, usage
from loadout.__main__ import main

SECRET = "my private prompt text"


def _claude(lines, sub=False, name="s1"):
    folder = paths.claude_home() / "projects" / "-repo"
    path = folder / (f"{name}/subagents/a.jsonl" if sub else f"{name}.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(l) if isinstance(l, dict) else l for l in lines) + "\n")
    return path


def _tool(name, **inp):
    return {"type": "assistant", "timestamp": "2026-10-14T10:00:00Z",
            "message": {"content": [{"type": "tool_use", "name": name, "input": inp}]}}


def _codex(lines, name="rollout-1"):
    path = paths.codex_home() / "sessions" / "2026" / "10" / "14" / f"{name}.jsonl"
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
    _codex([{"type": "session_meta", "payload": {"timestamp": "2026-10-14T10:00:00Z", "source": "cli"}},
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


def test_codex_symbol_searches_are_counted_in_every_command_shape(fake_home, monkeypatch):
    _on(monkeypatch, claude=False)
    _codex([{"type": "session_meta", "payload": {"timestamp": "2026-10-14T10:00:00Z", "source": "cli"}},
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
    _codex([{"type": "session_meta", "payload": {"timestamp": "2026-10-14T10:00:00Z"}}])
    report = usage.collect(14)
    assert "claude" not in report and report["codex"]["main"]["sessions"] == 1


def test_hint_sessions_come_from_the_hint_state(fake_home, monkeypatch):
    _on(monkeypatch, codex=False)
    state = paths.state_dir() / "tool-hint"
    state.mkdir(parents=True)
    (state / "a.json").write_text(json.dumps({"last_hint": 3, "calls": 7}))
    (state / "b.json").write_text(json.dumps({"calls": 2}))
    assert usage.collect(14)["hint_sessions"] == 1


def test_cli_prints_a_table_and_json(fake_home, monkeypatch, capsys):
    _on(monkeypatch, codex=False)
    _claude([_tool("mcp__plugin_loadout_serena__find_symbol")])
    assert main(["usage"]) == 0
    assert "Serena" in capsys.readouterr().out
    assert main(["usage", "--days", "7", "--json"]) == 0
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
