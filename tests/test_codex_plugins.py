"""Every plugin enabled for Claude Code goes into Codex through the same marketplace source."""
import json

from loadout import backup, codex, runner

SETTINGS = {
    "enabledPlugins": {"loadout@agent-loadout": True, "superpowers@claude-plugins-official": True,
                       "impeccable@impeccable": True, "hookify@claude-plugins-official": False,
                       "local-thing@my-dir": True},
    "extraKnownMarketplaces": {"agent-loadout": {"source": {"source": "github", "repo": "jonasyr/agent-loadout"}},
                               "impeccable": {"source": {"source": "github", "repo": "pbakaus/impeccable"}},
                               "my-dir": {"source": {"source": "directory", "path": "/x"}}},
}


def test_routes_follow_the_marketplace_source():
    routes, missing = codex.plugin_routes(SETTINGS)
    assert routes == {"jonasyr/agent-loadout": ["loadout"], codex.OFFICIAL: ["superpowers"],
                      "pbakaus/impeccable": ["impeccable"]}
    assert missing == ["local-thing@my-dir"]


def _fake(fake_runner, installed=()):
    def add(src, name, already=False):
        fake_runner.responses[("codex", "plugin", "marketplace", "add", src)] = runner.Result(
            0, json.dumps({"marketplaceName": name, "alreadyAdded": already}), "")
    add("jonasyr/agent-loadout", "agent-loadout")
    add(codex.OFFICIAL, "claude-plugins-official", already=True)
    add("pbakaus/impeccable", "impeccable")
    fake_runner.responses[("codex", "plugin", "list")] = runner.Result(
        0, json.dumps({"installed": [{"pluginId": p} for p in installed], "available": []}), "")


def test_installs_what_is_missing_and_records_undo(fake_home, fake_runner, monkeypatch):
    from loadout import settings_merge
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: SETTINGS)
    _fake(fake_runner, installed=["superpowers@claude-plugins-official"])
    bk = backup.Backup(description="t")
    lines = codex.apply_plugins(bk)
    adds = [c[3] for c in fake_runner.calls if c[:3] == ["codex", "plugin", "add"]]
    assert adds == ["loadout@agent-loadout", "impeccable@impeccable"]
    undo = [s["undo"]["run"] for s in bk.steps]
    assert ["codex", "plugin", "marketplace", "remove", "agent-loadout"] in undo
    assert ["codex", "plugin", "remove", "loadout@agent-loadout"] in undo
    assert ["codex", "plugin", "marketplace", "remove", "claude-plugins-official"] not in undo  # already there
    assert any("local-thing@my-dir" in l and "no Codex route" in l for l in lines)


def test_refresh_upgrades_marketplaces_and_reinstalls(fake_home, fake_runner, monkeypatch):
    from loadout import settings_merge
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: {"enabledPlugins": {"loadout@agent-loadout": True},
                                                                     "extraKnownMarketplaces": SETTINGS["extraKnownMarketplaces"]})
    _fake(fake_runner, installed=["loadout@agent-loadout"])
    fake_runner.responses[("codex", "plugin", "marketplace", "add", "jonasyr/agent-loadout")] = runner.Result(
        0, json.dumps({"marketplaceName": "agent-loadout", "alreadyAdded": True}), "")
    codex.apply_plugins(backup.Backup(description="t"), refresh=True)
    assert ["codex", "plugin", "marketplace", "upgrade", "agent-loadout"] in fake_runner.calls
    assert ["codex", "plugin", "add", "loadout@agent-loadout", "--json"] in fake_runner.calls


def test_failed_marketplace_is_reported_and_others_continue(fake_home, fake_runner, monkeypatch):
    from loadout import settings_merge
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: SETTINGS)
    _fake(fake_runner)
    fake_runner.responses[("codex", "plugin", "marketplace", "add", "pbakaus/impeccable")] = runner.Result(1, "", "network down")
    lines = codex.apply_plugins(backup.Backup(description="t"))
    assert any("pbakaus/impeccable" in l and "failed" in l for l in lines)
    assert ["codex", "plugin", "add", "loadout@agent-loadout", "--json"] in fake_runner.calls


def _frozen_settings():
    markets = json.loads(json.dumps(SETTINGS["extraKnownMarketplaces"]))
    markets["agent-loadout"]["autoUpdate"] = False
    return {"enabledPlugins": {"loadout@agent-loadout": True, "fresh@agent-loadout": True},
            "extraKnownMarketplaces": markets}


def test_the_automatic_refresh_skips_a_marketplace_set_to_no_auto_update(fake_home, fake_runner, monkeypatch):
    from loadout import settings_merge
    monkeypatch.setattr(settings_merge, "desired_settings", _frozen_settings)
    _fake(fake_runner, installed=["loadout@agent-loadout"])
    fake_runner.responses[("codex", "plugin", "marketplace", "add", "jonasyr/agent-loadout")] = runner.Result(
        0, json.dumps({"marketplaceName": "agent-loadout", "alreadyAdded": True}), "")
    codex.apply_plugins(backup.Backup(description="t"), refresh=True, auto=True)
    assert ["codex", "plugin", "marketplace", "upgrade", "agent-loadout"] not in fake_runner.calls
    assert ["codex", "plugin", "add", "loadout@agent-loadout", "--json"] not in fake_runner.calls
    assert ["codex", "plugin", "add", "fresh@agent-loadout", "--json"] in fake_runner.calls, "a first install still happens"


def test_an_explicit_update_still_updates_it(fake_home, fake_runner, monkeypatch):
    from loadout import settings_merge
    monkeypatch.setattr(settings_merge, "desired_settings", _frozen_settings)
    _fake(fake_runner, installed=["loadout@agent-loadout"])
    fake_runner.responses[("codex", "plugin", "marketplace", "add", "jonasyr/agent-loadout")] = runner.Result(
        0, json.dumps({"marketplaceName": "agent-loadout", "alreadyAdded": True}), "")
    codex.apply_plugins(backup.Backup(description="t"), refresh=True)
    assert ["codex", "plugin", "marketplace", "upgrade", "agent-loadout"] in fake_runner.calls


def test_apply_all_refresh_honours_auto_update(fake_home, fake_runner, monkeypatch):
    seen = []
    monkeypatch.setattr(codex, "apply_plugins", lambda bk, refresh=False, say=None, auto=False: seen.append((refresh, auto)) or [])
    monkeypatch.setattr(codex, "apply_instructions", lambda bk: "ok")
    monkeypatch.setattr(codex, "apply_config", lambda bk: [])
    monkeypatch.setattr(codex, "apply_skills", lambda bk: [])
    codex.apply_all(backup.Backup(description="t"), refresh=True)
    assert seen == [(True, True)]
