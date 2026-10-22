import json
import os
import re
import subprocess

import pytest

from loadout import paths

PLUGIN = paths.kit_root() / "plugins" / "loadout"
pytestmark = pytest.mark.skipif(os.name == "nt", reason="hook scripts run under bash")


def _commands():
    hooks = json.loads((PLUGIN / "hooks/hooks.json").read_text())["hooks"]
    return [h["command"] for groups in hooks.values() for g in groups for h in g["hooks"]]


def test_every_hook_uses_plugin_root_and_has_timeout():
    hooks = json.loads((PLUGIN / "hooks/hooks.json").read_text())["hooks"]
    for groups in hooks.values():
        for g in groups:
            for h in g["hooks"]:
                assert "${CLAUDE_PLUGIN_ROOT}" in h["command"]
                assert h.get("timeout")


def test_claude_session_start_passes_its_agent():
    assert any("loadout hook-session-start --agent claude" in c for c in _commands())


@pytest.mark.parametrize("args", [
    ["serena-hooks", "activate", "--client=claude-code"],
    ["rtk", "hook", "claude"],
    ["loadout", "hook-session-start"],
    ["--soft", "codebase-memory-mcp", "hook-augment"],
])
def test_run_sh_is_silent_noop_when_binary_missing(tmp_path, args):
    env = {"PATH": str(tmp_path), "HOME": str(tmp_path)}
    proc = subprocess.run(["/bin/bash", str(PLUGIN / "hooks/run.sh"), *args], env=env, capture_output=True, text=True, input="{}")
    assert proc.returncode == 0
    assert proc.stdout == "" and proc.stderr == ""


def test_soft_mode_swallows_failures(tmp_path):
    fake = tmp_path / "failing-tool"
    fake.write_text("#!/bin/sh\necho oops >&2\nexit 3\n")
    fake.chmod(0o755)
    env = {"PATH": f"{tmp_path}:/usr/bin:/bin"}
    proc = subprocess.run(["/bin/bash", str(PLUGIN / "hooks/run.sh"), "--soft", "failing-tool"], env=env, capture_output=True, text=True)
    assert proc.returncode == 0 and proc.stderr == ""


def test_subagent_context_is_valid_json(tmp_path):
    proc = subprocess.run(["/bin/bash", str(PLUGIN / "hooks/subagent-context.sh")], env={"PATH": str(tmp_path)}, capture_output=True, text=True)
    data = json.loads(proc.stdout)
    assert data["hookSpecificOutput"]["hookEventName"] == "SubagentStart"
    assert "codebase-memory" in data["hookSpecificOutput"]["additionalContext"]


def test_subagent_context_names_exact_tools(tmp_path):
    proc = subprocess.run(["/bin/bash", str(PLUGIN / "hooks/subagent-context.sh")], env={"PATH": str(tmp_path)}, capture_output=True, text=True)
    card = json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"]
    for name in ("mcp__plugin_loadout_codebase-memory-mcp__search_graph", "mcp__plugin_loadout_serena__find_symbol", "already active"):
        assert name in card


def test_tooling_rule_says_name_tools_when_delegating():
    assert "When you delegate code work" in (paths.kit_root() / "rules/tooling.md").read_text(encoding="utf-8")


def test_codex_reviewer_can_use_serena_and_graph():
    text = (paths.kit_root() / ".claude/agents/codex-reviewer.md").read_text(encoding="utf-8")
    tools = [t.strip() for t in re.search(r"^tools: (.*)$", text, re.M).group(1).split(",")]
    serena, cbm = "mcp__plugin_loadout_serena__", "mcp__plugin_loadout_codebase-memory-mcp__"
    for t in ("Read", "Grep", "Glob", "Bash", serena + "find_symbol", serena + "find_referencing_symbols",
              serena + "get_symbols_overview", cbm + "search_graph", cbm + "trace_path", cbm + "get_code_snippet", cbm + "query_graph"):
        assert t in tools, t
    assert not {"Edit", "Write", "MultiEdit"} & set(tools) and not any("replace_" in t or "insert_" in t for t in tools)


def test_marketplace_lists_kit_core_without_version():
    market = json.loads((paths.kit_root() / ".claude-plugin/marketplace.json").read_text())
    assert market["name"] == "agent-loadout"
    assert market["plugins"][0]["source"] == "./plugins/loadout"
    plugin = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text())
    assert "version" not in plugin and "version" not in market["plugins"][0]


GUARD = '"${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" --soft --python "${CLAUDE_PLUGIN_ROOT}/hooks/mcp_guard.py" serena '


def _groups(event):
    return json.loads((PLUGIN / "hooks/hooks.json").read_text())["hooks"].get(event, [])


def _guarded(event, inner):
    return [(g["matcher"], h) for g in _groups(event) for h in g["hooks"] if h["command"] == GUARD + inner]


def test_claude_hooks_match_serena_docs():
    # Serena's documented Claude Code hooks (oraios.github.io/serena/02-usage/030_clients.html), each once, guarded
    serena = "mcp__plugin_loadout_serena__.*|mcp__serena__.*"
    assert [m for m, _ in _guarded("SessionStart", "serena-hooks activate --client=claude-code")] == [""]
    assert [m for m, _ in _guarded("SessionEnd", "serena-hooks cleanup --client=claude-code")] == [""]
    assert [m for m, _ in _guarded("PreToolUse", "serena-hooks auto-approve --client=claude-code")] == [serena]
    assert [m for m, _ in _guarded("PreToolUse", "serena-hooks remind --client=claude-code")] == \
        ["Bash|Read|Grep|Glob|" + serena]
    assert not [c for c in _commands() if "serena-hooks" in c and not c.startswith(GUARD)]
    timeouts = {inner: h["timeout"] for ev, inner in (("SessionStart", "serena-hooks activate --client=claude-code"),
                                                      ("SessionEnd", "serena-hooks cleanup --client=claude-code"),
                                                      ("PreToolUse", "serena-hooks remind --client=claude-code"))
                for _, h in _guarded(ev, inner)}
    assert list(timeouts.values()) == [15, 10, 5]


def test_remind_matcher_covers_windows_tools():
    import re
    (matcher, _), = _guarded("PreToolUse", "serena-hooks remind --client=claude-code")
    for tool in ("Grep", "Glob", "Read", "Bash", "mcp__serena__find_symbol", "mcp__plugin_loadout_serena__find_symbol"):
        assert re.fullmatch(matcher, tool), tool
    for tool in ("Edit", "WebSearch", "mcp__plugin_loadout_codebase-memory-mcp__search_graph"):
        assert not re.fullmatch(matcher, tool), tool


def test_cbm_hook_augment_is_not_wired():
    # codebase-memory 0.12.1's hook-augment exceeds its own 2 s deadline and prints nothing (upstream #2683, #2441)
    for name in ("hooks.json", "codex.json"):
        assert "hook-augment" not in (PLUGIN / "hooks" / name).read_text()


def test_plugin_servers_always_load():
    servers = json.loads((PLUGIN / ".mcp.json").read_text())["mcpServers"]
    assert servers["serena"]["alwaysLoad"] is True and servers["codebase-memory-mcp"]["alwaysLoad"] is True
