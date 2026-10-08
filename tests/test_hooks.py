import json
import os
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


def test_marketplace_lists_kit_core_without_version():
    market = json.loads((paths.kit_root() / ".claude-plugin/marketplace.json").read_text())
    assert market["name"] == "agent-loadout"
    assert market["plugins"][0]["source"] == "./plugins/loadout"
    plugin = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text())
    assert "version" not in plugin and "version" not in market["plugins"][0]
