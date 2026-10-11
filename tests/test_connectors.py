import json

from loadout import check, paths, settings_merge


def _settings(home, enabled):
    p = home / ".claude/settings.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"enabledPlugins": enabled}))


def _claude_json(home, data):
    (home / ".claude.json").write_text(data if isinstance(data, str) else json.dumps(data))


def _dupes():
    return [r for r in check.run_checks() if r.name.startswith("duplicate ")]


def test_enabled_plugin_and_connected_connector_warn(fake_home, fake_runner):
    _settings(fake_home, {"context7@claude-plugins-official": True})
    _claude_json(fake_home, {"claudeAiMcpEverConnected": ["claude.ai Context7", "claude.ai Gmail"]})
    [r] = _dupes()
    assert r.name == "duplicate context7@claude-plugins-official"
    assert not r.ok and r.severity == "warn"
    assert "claude.ai Context7" in r.detail and "still connected" in r.detail
    assert '"enabledPlugins": {"context7@claude-plugins-official": false}' in r.fix
    assert "loadout apply-settings" in r.fix


def test_disabled_plugin_or_unconnected_connector_is_quiet(fake_home, fake_runner):
    _settings(fake_home, {"context7@claude-plugins-official": False, "wiley-scholar-gateway@life-sciences": True})
    _claude_json(fake_home, {"claudeAiMcpEverConnected": ["claude.ai Context7"]})
    assert _dupes() == []


def test_wiley_duplicate(fake_home, fake_runner):
    _settings(fake_home, {"wiley-scholar-gateway@life-sciences": True})
    _claude_json(fake_home, {"claudeAiMcpEverConnected": ["claude.ai Wiley Scholar Gateway"]})
    assert [r.name for r in _dupes()] == ["duplicate wiley-scholar-gateway@life-sciences"]


def test_missing_or_malformed_claude_json_is_quiet(fake_home, fake_runner):
    _settings(fake_home, {"context7@claude-plugins-official": True})
    assert _dupes() == []  # no ~/.claude.json
    for bad in ("{ broken", json.dumps({"claudeAiMcpEverConnected": "claude.ai Context7"}),
                json.dumps({"claudeAiMcpEverConnected": [1, None]}), json.dumps([1, 2])):
        _claude_json(fake_home, bad)
        assert _dupes() == []


def test_invalid_settings_json_is_quiet_here(fake_home, fake_runner):
    p = fake_home / ".claude/settings.json"
    p.parent.mkdir(parents=True)
    p.write_text("{ nope")
    _claude_json(fake_home, {"claudeAiMcpEverConnected": ["claude.ai Context7"]})
    assert _dupes() == []  # the settings.json check reports the syntax error


def test_personal_false_overrides_kit_true(fake_home, fake_runner):
    pers = paths.personal_root()
    pers.mkdir(parents=True)
    (pers / "settings.json").write_text(json.dumps({"enabledPlugins": {"context7@claude-plugins-official": False}}))
    assert settings_merge.desired_settings()["enabledPlugins"]["context7@claude-plugins-official"] is False
    settings_merge.apply_settings()
    data = json.loads((fake_home / ".claude/settings.json").read_text())
    assert data["enabledPlugins"]["context7@claude-plugins-official"] is False
