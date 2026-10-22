"""The hint hook is wired for both agents, and the subagent card leads with triggers."""
import json
import os
import subprocess
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[1] / "plugins" / "loadout"
HINT = '"${CLAUDE_PLUGIN_ROOT}/hooks/tool_hint.sh"'


def _entries(name, event):
    hooks = json.loads((PLUGIN / "hooks" / name).read_text())["hooks"]
    return [(g["matcher"], h) for g in hooks.get(event, []) for h in g["hooks"]]


def _matchers_for(name, event):
    return [m for m, h in _entries(name, event) if h["command"] == HINT]


def test_claude_code_runs_the_hint_on_web_lookups_only():
    assert _matchers_for("hooks.json", "PreToolUse") == ["WebSearch|WebFetch"]
    assert _matchers_for("hooks.json", "PostToolUse") == []
    assert all(h["timeout"] == 5 for m, h in _entries("hooks.json", "PreToolUse") if h["command"] == HINT)


def test_codex_has_no_hint():
    # Codex gives hooks no web tools, and Serena's remind covers shell searches there
    assert _matchers_for("codex.json", "PreToolUse") == [] and _matchers_for("codex.json", "PostToolUse") == []


@pytest.mark.skipif(os.name == "nt", reason="bash")
def test_the_subagent_card_leads_with_triggers_and_stays_short():
    out = subprocess.run(["bash", str(PLUGIN / "hooks" / "subagent-context.sh")], capture_output=True, text=True)
    card = json.loads(out.stdout)["hookSpecificOutput"]["additionalContext"]
    assert len(card) < 700
    for word in ("search_graph", "Serena", "Context7", "Microsoft Learn", "planning", "paths and symbols"):
        assert word in card
