import json

import pytest

from loadout import backup, inventory, own, paths
from fixtures import author_machine


@pytest.fixture
def machine(fake_home, fake_runner):
    author_machine(fake_home)
    return fake_home


def _verdicts():
    return inventory.classify(inventory.collect(with_versions=False))


def _by(verdicts):
    return {(v.item.kind, v.item.name): v for v in verdicts}


def _personal(name, data):
    path = paths.personal_root() / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return path


def test_own_action_replaces_unknown(machine):
    v = _by(_verdicts())
    assert v[("plugin", "mystery@somewhere")].action == "own"
    assert all(x.action != "unknown" for x in v.values())


def test_personal_layer_items_are_keep(machine):
    _personal("settings.json", {"enabledPlugins": {"mystery@somewhere": True},
                                "hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [{"type": "command", "command": "my-own-linter"}]}]}})
    cfg = json.loads((machine / ".claude.json").read_text())["mcpServers"]["omarchy-kb"]
    _personal("mcp.json", {"mcpServers": {"omarchy-kb": cfg}})
    (paths.personal_root() / "skills/my-skill").mkdir(parents=True)
    v = _by(_verdicts())
    for key in [("plugin", "mystery@somewhere"), ("mcp", "omarchy-kb"), ("skill", "my-skill"), ("hook", "PreToolUse:Edit")]:
        assert v[key].action == "keep" and v[key].reason == own.PERSONAL_REASON, key


def test_kit_plugin_reason_is_kit_not_personal(machine):
    assert _by(_verdicts())[("plugin", "superpowers@claude-plugins-official")].reason == "Enabled by the kit."


def test_personal_profile_items_are_keep(machine):
    _personal("profiles/mine.json", {"install": ["mystery@somewhere"]})
    v = _by(_verdicts())[("plugin", "mystery@somewhere")]
    assert v.action == "keep" and "mine" in v.reason


def test_left_items_are_keep_and_listed_with_all(machine):
    item = _by(_verdicts())[("skill", "my-skill")].item
    own.remember_leave(item)
    v = _by(_verdicts())
    assert v[("skill", "my-skill")].action == "keep" and v[("skill", "my-skill")].reason == own.LEFT_REASON
    assert item not in [x.item for x in own.unmanaged(_verdicts())]
    assert item in [x.item for x in own.unmanaged(_verdicts(), include_left=True)]
    own.forget(item)
    assert _by(_verdicts())[("skill", "my-skill")].action == "own"


def test_hook_decision_key_includes_command(machine):
    hook = _by(_verdicts())[("hook", "PreToolUse:Edit")].item
    assert own.decision_key(hook) == "hook:PreToolUse:Edit:my-own-linter"
