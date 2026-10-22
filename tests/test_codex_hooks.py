"""The plugin's Codex hooks: every Claude hook has a Codex counterpart or a stated reason; the type check."""
import io
import json
import os
import sys

import pytest
from pathlib import Path

from loadout import paths

PLUGIN = paths.kit_root() / "plugins" / "loadout"
sys.path.insert(0, str(PLUGIN / "hooks"))
import typecheck  # noqa: E402

# Claude hooks with no Codex counterpart, and why
OMITTED = {
    "codebase-memory-mcp hook-augment": "Codex has no Grep/Glob tools to augment",
    "tool_hint.sh": "Codex has its own entries with other matchers (shell only), checked in test_tool_hint_wiring.py",
    "reload_check.py":"compares Claude's installed_plugins.json; Codex loads plugins per session",
    "serena-hooks": "Codex gets Serena's documented hooks in ~/.codex/hooks.json (ADR 0028), never from the plugin",
}
# Claude events with no Codex counterpart, and why
OMITTED_EVENTS = {"SubagentStop": "Codex refreshes codebase-memory at Stop only; a subagent's edits wait for the "
                                  "parent's Stop (or the 20-file limit)"}
CODEX_ARGS = {"--client=claude-code": "--client=codex", "rtk hook claude": "rtk hook codex",
              "--agent claude": "--agent codex", 'subagent-context.sh" claude': 'subagent-context.sh" codex',
              "mcp__plugin_loadout_serena__": "mcp__serena__", "Write|Edit|MultiEdit": "Edit|Write"}


def _commands(path):
    hooks = json.loads(path.read_text(encoding="utf-8"))["hooks"]
    return {(event, g.get("matcher", ""), h["command"]) for event, groups in hooks.items() for g in groups for h in g["hooks"]}


def _codexify(text):
    for a, b in CODEX_ARGS.items():
        text = text.replace(a, b)
    return text


def test_manifest_points_codex_to_its_hooks():
    manifest = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "loadout" and manifest["hooks"] == "./hooks/codex.json"


def test_every_claude_hook_has_a_codex_counterpart_or_a_reason():
    codex_hooks = _commands(PLUGIN / "hooks" / "codex.json")
    for event, matcher, command in _commands(PLUGIN / "hooks" / "hooks.json"):
        if any(key in command for key in OMITTED) or event in OMITTED_EVENTS:
            continue
        assert (event, _codexify(matcher), _codexify(command)) in codex_hooks, (event, matcher, command)
    assert not any("--client=claude-code" in c or "rtk hook claude" in c for _, _, c in codex_hooks)


def test_codex_hooks_add_the_type_check_after_edits():
    assert any(e == "PostToolUse" and m == "Edit|Write" and "typecheck.py" in c
               for e, m, c in _commands(PLUGIN / "hooks" / "codex.json"))


def test_changed_files_from_apply_patch_and_claude_edits(tmp_path):
    patch = "*** Begin Patch\n*** Update File: src/a.py\n@@\n-x\n+y\n*** Add File: b.ts\n+z\n*** End Patch\n"
    event = {"cwd": str(tmp_path), "tool_name": "apply_patch", "tool_input": {"command": patch}}
    assert typecheck.changed_files(event) == [tmp_path / "src/a.py", tmp_path / "b.ts"]
    absolute = tmp_path / "abs" / "c.rs"
    assert typecheck.changed_files({"cwd": "/elsewhere", "tool_input": {"file_path": str(absolute)}}) == [absolute]


def _fake_tool(bin_dir, name, exit_code, output):
    script = bin_dir / name
    script.write_text(f"#!/bin/sh\necho '{output}'\nexit {exit_code}\n", encoding="utf-8")
    script.chmod(0o755)


@pytest.mark.skipif(os.name == "nt", reason="fake checkers are shell scripts")
def test_errors_are_reported_and_clean_files_are_silent(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    (tmp_path / "a.py").write_text("x: int = 'no'\n")
    event = {"cwd": str(tmp_path), "tool_input": {"command": "*** Update File: a.py\n"}}
    _fake_tool(bin_dir, "pyright", 1, "a.py:1:10 - error: str is not int")
    out = io.StringIO()
    typecheck.main(io.StringIO(json.dumps(event)), out)
    reply = json.loads(out.getvalue())
    assert reply["decision"] == "block" and "str is not int" in reply["reason"]
    _fake_tool(bin_dir, "pyright", 0, "0 errors")
    out = io.StringIO()
    typecheck.main(io.StringIO(json.dumps(event)), out)
    assert out.getvalue() == ""


@pytest.mark.skipif(os.name == "nt", reason="fake checkers are shell scripts")
def test_slow_checker_is_reported_as_skipped(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    (bin_dir / "pyright").write_text("#!/bin/sh\nsleep 5\n", encoding="utf-8")
    (bin_dir / "pyright").chmod(0o755)
    monkeypatch.setattr(typecheck, "LIMIT", 0.5)
    (tmp_path / "a.py").write_text("x = 1\n")
    out = io.StringIO()
    typecheck.main(io.StringIO(json.dumps({"cwd": str(tmp_path), "tool_input": {"command": "*** Update File: a.py\n"}})), out)
    reply = json.loads(out.getvalue())
    assert "decision" not in reply and "skipped (timeout" in reply["hookSpecificOutput"]["additionalContext"]


def test_missing_checker_and_bad_input_are_silent(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))  # no checkers at all
    (tmp_path / "a.py").write_text("x = 1\n")
    out = io.StringIO()
    typecheck.main(io.StringIO(json.dumps({"cwd": str(tmp_path), "tool_input": {"command": "*** Update File: a.py\n"}})), out)
    typecheck.main(io.StringIO("not json"), out)
    assert out.getvalue() == ""


def test_checks_pick_the_project_folder(tmp_path, monkeypatch):
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "tsconfig.json").write_text("{}")
    (tmp_path / "crate" / "src").mkdir(parents=True)
    (tmp_path / "crate" / "Cargo.toml").write_text("")
    monkeypatch.setattr(typecheck, "_which", lambda name: f"/usr/bin/{name}")
    found = typecheck.checks([tmp_path / "web" / "x.ts", tmp_path / "crate" / "src" / "lib.rs"])
    assert (["/usr/bin/tsc", "--noEmit", "-p", str(tmp_path / "web")], tmp_path / "web") in found
    assert (["/usr/bin/cargo", "check", "--quiet", "--message-format=short"], tmp_path / "crate") in found


def test_codex_gets_no_serena_from_the_plugin():
    # Codex starts an active plugin's MCP servers by bare name; with the user's Serena under another name the
    # plugin's `serena` (context claude-code) would run as a second one
    manifest = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    servers = json.loads((PLUGIN / manifest["mcpServers"]).read_text(encoding="utf-8"))["mcpServers"]
    assert "serena" not in servers and "codebase-memory-mcp" in servers
    assert "serena-hooks" not in (PLUGIN / "hooks" / "codex.json").read_text(encoding="utf-8")


def test_codex_session_start_passes_its_agent():
    commands = [c for e, _, c in _commands(PLUGIN / "hooks" / "codex.json") if e == "SessionStart"]
    assert any("hook-session-start --agent codex" in c for c in commands)
