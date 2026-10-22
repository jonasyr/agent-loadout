"""mcp_guard.py: runs Serena's (or another MCP tool's) hook command only when that tool is there for the agent and
the user does not already run the same hook. The script runs as a subprocess with a temporary HOME and PATH."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[1] / "plugins" / "loadout"
GUARD = PLUGIN / "hooks" / "mcp_guard.py"
pytestmark = pytest.mark.skipif(os.name == "nt", reason="stub executables are shell scripts")


@pytest.fixture
def env(tmp_path):
    home, bindir, repo = tmp_path / "home", tmp_path / "bin", tmp_path / "repo"
    for d in (home / ".claude", bindir, repo):
        d.mkdir(parents=True)
    stub = bindir / "serena-hooks"  # echoes what it got, so a test sees that it ran and with which input
    stub.write_text('#!/bin/sh\nprintf \'{"ran":"%s","stdin":%s}\' "$*" "$(cat)"\n')
    stub.chmod(0o755)
    return {"home": home, "bin": bindir, "repo": repo}


def _payload(env, event="PreToolUse", tool="Bash"):
    return {"session_id": "s1", "hook_event_name": event, "tool_name": tool, "tool_input": {"command": "rg x"},
            "cwd": str(env["repo"])}


def _run(env, payload, raw=None, command=("serena-hooks", "remind", "--client=claude-code"), server="serena"):
    e = {"HOME": str(env["home"]), "PATH": f"{env['bin']}{os.pathsep}/usr/bin:/bin"}
    res = subprocess.run([sys.executable, str(GUARD), server, *command],
                         input=raw if raw is not None else json.dumps(payload), env=e, capture_output=True,
                         text=True, timeout=20)
    assert res.returncode == 0 and res.stderr == ""
    return json.loads(res.stdout) if res.stdout.strip() else None


def _settings(path, event, command, matcher=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"hooks": {event: [{"matcher": matcher, "hooks": [
        {"type": "command", "command": command}]}]}}))


def test_guard_runs_command_and_passes_output(env):
    out = _run(env, _payload(env))
    assert out["ran"] == "remind --client=claude-code" and out["stdin"]["tool_name"] == "Bash"


def test_guard_silent_when_binary_missing(env):
    (env["bin"] / "serena-hooks").unlink()
    assert _run(env, _payload(env)) is None


@pytest.mark.parametrize("name", ["plugin:loadout:serena", "serena"])
def test_guard_silent_when_server_disabled_for_folder(env, name):
    (env["home"] / ".claude.json").write_text(json.dumps(
        {"projects": {str(env["repo"]): {"disabledMcpServers": [name]}}}))
    assert _run(env, _payload(env)) is None


def test_guard_runs_when_another_folder_disabled_the_server(env):
    (env["home"] / ".claude.json").write_text(json.dumps(
        {"projects": {"/elsewhere": {"disabledMcpServers": ["plugin:loadout:serena"]}}}))
    assert _run(env, _payload(env))


def test_guard_runs_when_plugin_server_off_but_users_own_serena_is_on(env):
    (env["home"] / ".claude.json").write_text(json.dumps(
        {"mcpServers": {"serena": {"command": "serena", "args": ["start-mcp-server"]}},
         "projects": {str(env["repo"]): {"disabledMcpServers": ["plugin:loadout:serena"]}}}))
    assert _run(env, _payload(env))


@pytest.mark.parametrize("where", [".claude/settings.json", "repo/.claude/settings.json",
                                   "repo/.claude/settings.local.json"])
def test_guard_silent_when_user_runs_equivalent_hook(env, where):
    base = env["home"] if where.startswith(".claude") else env["repo"].parent
    _settings(base / where, "PreToolUse", "serena-hooks remind --client=claude-code")
    assert _run(env, _payload(env)) is None


def test_guard_sees_equivalent_hook_behind_a_wrapper_or_with_other_flags(env):
    _settings(env["home"] / ".claude" / "settings.json", "PreToolUse",
              "/home/u/.local/bin/serena-hooks remind", matcher="Bash")
    assert _run(env, _payload(env)) is None


def test_guard_runs_when_user_hook_is_other_event(env):
    _settings(env["home"] / ".claude" / "settings.json", "SessionStart", "serena-hooks remind --client=claude-code")
    assert _run(env, _payload(env))


def test_guard_runs_when_user_hook_is_other_subcommand(env):
    _settings(env["home"] / ".claude" / "settings.json", "PreToolUse", "serena-hooks auto-approve --client=claude-code")
    assert _run(env, _payload(env))


def test_guard_ignores_unreadable_settings(env):
    (env["home"] / ".claude" / "settings.json").write_text("{broken")
    (env["home"] / ".claude.json").write_text("[]")
    assert _run(env, _payload(env))


def test_guard_never_fails_the_tool_call(env):
    assert _run(env, None, raw="\x00 not json") is None
    assert _run(env, None, raw="[]") is None


def test_guard_passes_a_failing_command_through_silently(env):
    (env["bin"] / "serena-hooks").write_text("#!/bin/sh\necho boom >&2\nexit 3\n")
    assert _run(env, _payload(env)) is None


def test_guard_silent_when_server_disabled_for_a_parent_folder(env):
    sub = env["repo"] / "src" / "pkg"
    sub.mkdir(parents=True)
    (env["home"] / ".claude.json").write_text(json.dumps(
        {"projects": {str(env["repo"]): {"disabledMcpServers": ["plugin:loadout:serena"]}}}))
    payload = _payload(env)
    payload["cwd"] = str(sub)
    assert _run(env, payload) is None


def test_inner_command_is_stopped_before_the_hook_timeout(env):
    (env["bin"] / "serena-hooks").write_text("#!/bin/sh\nsleep 30\n")
    import time
    start = time.monotonic()
    assert _run(env, _payload(env)) is None
    assert time.monotonic() - start < 5.5  # remind's hook timeout is 5 s; the guard ends first, silently


def test_a_hook_that_only_mentions_the_command_is_not_equivalent(env):
    _settings(env["home"] / ".claude" / "settings.json", "PreToolUse", "echo serena-hooks remind")
    assert _run(env, _payload(env))


def test_flags_before_the_subcommand_still_match(env):
    _settings(env["home"] / ".claude" / "settings.json", "PreToolUse", "serena-hooks --client=claude-code remind")
    assert _run(env, _payload(env)) is None


def test_own_mcp_json_serena_off_by_disabled_mcpjson_servers(env):
    (env["repo"] / ".mcp.json").write_text(json.dumps({"mcpServers": {"serena": {"command": "serena"}}}))
    _settings(env["repo"] / ".claude" / "settings.local.json", "SessionStart", "x")
    data = json.loads((env["repo"] / ".claude" / "settings.local.json").read_text())
    data["disabledMcpjsonServers"] = ["serena"]
    (env["repo"] / ".claude" / "settings.local.json").write_text(json.dumps(data))
    (env["home"] / ".claude.json").write_text(json.dumps(
        {"projects": {str(env["repo"]): {"disabledMcpServers": ["plugin:loadout:serena"]}}}))
    assert _run(env, _payload(env)) is None


def _guard_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("mcp_guard_t", GUARD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_codex_availability_reads_codex_config_not_claudes(env, monkeypatch):
    mod = _guard_module()
    monkeypatch.setenv("PATH", f"{env['bin']}{os.pathsep}/usr/bin:/bin")
    (env["bin"] / "codebase-memory-mcp").write_text("#!/bin/sh\n")
    (env["bin"] / "codebase-memory-mcp").chmod(0o755)
    # Claude Code has it off here: that must not matter for Codex
    (env["home"] / ".claude.json").write_text(json.dumps(
        {"projects": {str(env["repo"]): {"disabledMcpServers": ["plugin:loadout:codebase-memory-mcp"]}}}))
    monkeypatch.setenv("CODEX_HOME", str(env["home"] / ".codex"))
    assert mod.available("codebase-memory-mcp", "codex", str(env["repo"]), env["home"])
    assert not mod.available("codebase-memory-mcp", "claude", str(env["repo"]), env["home"])
    (env["home"] / ".codex").mkdir()
    (env["home"] / ".codex" / "config.toml").write_text('[mcp_servers.codebase-memory-mcp]\nenabled = false\n')
    assert not mod.available("codebase-memory-mcp", "codex", str(env["repo"]), env["home"])
