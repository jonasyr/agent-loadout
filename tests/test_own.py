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


def _v(kind, name):
    return _by(_verdicts())[(kind, name)]


def _run_machine(rec):
    return rec.machine() if rec.machine else []


def test_global_plugin_records_plugin_and_marketplace(machine):
    (machine / ".claude/plugins/known_marketplaces.json").write_text(json.dumps({
        "somewhere": {"source": {"source": "github", "repo": "me/somewhere"}}}))
    bk = backup.Backup()
    rec = own.record_global(_v("plugin", "mystery@somewhere"), bk)
    assert rec.ok
    data = json.loads((paths.personal_root() / "settings.json").read_text())
    assert data["enabledPlugins"]["mystery@somewhere"] is True
    assert data["extraKnownMarketplaces"]["somewhere"] == {"source": {"source": "github", "repo": "me/somewhere"}}
    assert _v("plugin", "mystery@somewhere").action == "keep"


def test_global_plugin_marketplace_collision_skips(machine):
    (machine / ".claude/plugins/known_marketplaces.json").write_text(json.dumps({
        "somewhere": {"source": {"source": "github", "repo": "me/somewhere"}}}))
    _personal("settings.json", {"extraKnownMarketplaces": {"somewhere": {"source": {"source": "github", "repo": "other/x"}}}})
    rec = own.record_global(_v("plugin", "mystery@somewhere"), backup.Backup())
    assert not rec.ok and "skipped" in rec.lines[0]
    assert "enabledPlugins" not in json.loads((paths.personal_root() / "settings.json").read_text())


def test_global_mcp_plain_server_is_recorded_and_managed(machine, fake_runner):
    from loadout import personal_mcp
    rec = own.record_global(_v("mcp", "omarchy-kb"), backup.Backup())
    assert rec.ok
    _run_machine(rec)
    cfg = json.loads((machine / ".claude.json").read_text())["mcpServers"]["omarchy-kb"]
    assert json.loads((paths.personal_root() / "mcp.json").read_text())["mcpServers"]["omarchy-kb"] == cfg
    assert json.loads((paths.state_dir() / "managed-mcp.json").read_text())["mcpServers"]["omarchy-kb"] == cfg
    fake_runner.calls.clear()
    assert personal_mcp.apply_mcp() == []           # no "skipped, not managed" and no re-add
    assert fake_runner.calls == []


def test_global_mcp_secret_goes_to_secrets_env(machine, fake_runner):
    cfg = json.loads((machine / ".claude.json").read_text())
    cfg["mcpServers"]["mine"] = {"command": "x", "env": {"API_KEY": "k" * 20}}
    (machine / ".claude.json").write_text(json.dumps(cfg))
    rec = own.record_global(_v("mcp", "mine"), backup.Backup())
    _run_machine(rec)
    recorded = (paths.personal_root() / "mcp.json").read_text()
    assert "k" * 20 not in recorded and "${MINE_API_KEY}" in recorded
    assert "MINE_API_KEY=" in paths.secrets_file().read_text()
    add = [c for c in fake_runner.calls if c[:3] == ["claude", "mcp", "add-json"]][-1]
    assert "${MINE_API_KEY}" in add[-1]


def _as_own(kind, name):
    return inventory.Verdict(_v(kind, name).item, "own", "")


def _hook(detail):
    return inventory.Verdict(next(x.item for x in _verdicts() if x.item.kind == "hook" and x.item.detail == detail), "own", "")


def test_global_mcp_unfixable_secret_blocked(machine, fake_runner):
    rec = own.record_global(_as_own("mcp", "github-server"), backup.Backup())
    assert not rec.ok and "by hand" in rec.lines[0]
    assert not (paths.personal_root() / "mcp.json").exists()


def test_global_skill_dir_restore(machine):
    (machine / ".claude/skills/my-skill/SKILL.md").write_text("mine")
    bk = backup.Backup()
    rec = own.record_global(_v("skill", "my-skill"), bk)
    _run_machine(rec)
    from loadout import link
    link.link_all(bk)
    assert (paths.personal_root() / "skills/my-skill/SKILL.md").read_text() == "mine"
    assert (machine / ".claude/skills/my-skill").is_symlink()
    backup.restore(bk.root)
    restored = machine / ".claude/skills/my-skill"
    assert not restored.is_symlink() and (restored / "SKILL.md").read_text() == "mine"


def test_global_skill_symlink_becomes_pointer(machine):
    skills = machine / ".claude/skills"
    shared = machine / "shared/omarchy"
    shared.mkdir(parents=True)
    (skills / "omarchy").symlink_to(shared)
    rec = own.record_global(_v("skill", "omarchy"), backup.Backup())
    assert rec.ok and rec.machine is None
    assert json.loads((paths.personal_root() / "skills.json").read_text()) == {"omarchy": str(shared)}


def _settings():
    return json.loads((paths.claude_home() / "settings.json").read_text())


def test_global_hook_plain_command(machine):
    rec = own.record_global(_v("hook", "PreToolUse:Edit"), backup.Backup())
    _run_machine(rec)
    groups = json.loads((paths.personal_root() / "settings.json").read_text())["hooks"]["PreToolUse"]
    assert groups == [{"matcher": "Edit", "hooks": [{"type": "command", "command": "my-own-linter"}]}]


def test_global_hook_local_script_copied_and_rewritten(machine):
    script = machine / "bin/notify.sh"
    script.parent.mkdir()
    script.write_text("#!/bin/sh\necho hi\n")
    data = _settings()
    data["hooks"]["Notification"] = [{"hooks": [{"type": "command", "command": f"bash '{script}' --loud"}]}]
    (paths.claude_home() / "settings.json").write_text(json.dumps(data))
    rec = own.record_global(_v("hook", "Notification:"), backup.Backup())
    _run_machine(rec)
    assert (paths.personal_root() / "hooks/notify.sh").read_text() == script.read_text()
    assert script.exists()   # original stays
    want = 'bash "$HOME/.claude/hooks/personal/notify.sh" --loud'
    personal = json.loads((paths.personal_root() / "settings.json").read_text())["hooks"]["Notification"]
    assert personal[0]["hooks"][0]["command"] == want
    assert _settings()["hooks"]["Notification"][0]["hooks"][0]["command"] == want


def test_global_hook_exec_form_recorded_as_is(machine):
    data = _settings()
    data["hooks"]["Stop"] = [{"hooks": [{"type": "command", "command": "x", "args": ["/opt/x"]}]}]
    (paths.claude_home() / "settings.json").write_text(json.dumps(data))
    rec = own.record_global(_hook("x"), backup.Backup())
    assert rec.ok and any("exec form" in line for line in rec.lines)


def test_global_hook_no_duplicate_after_merge(machine):
    from loadout import settings_merge
    data = _settings()
    data["hooks"]["PreToolUse"][3]["hooks"].append({"type": "command", "command": "other"})  # the Edit group
    (paths.claude_home() / "settings.json").write_text(json.dumps(data))
    rec = own.record_global(_hook("my-own-linter"), backup.Backup())
    _run_machine(rec)
    settings_merge.apply_settings()
    commands = [h["command"] for g in _settings()["hooks"]["PreToolUse"] for h in g["hooks"]]
    assert commands.count("my-own-linter") == 1
