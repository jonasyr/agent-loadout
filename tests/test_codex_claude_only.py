"""Catalog plugins with target "claude" (codex-reviewer) never reach Codex; the add-on is off by default."""
import json
from types import SimpleNamespace

from loadout import backup, catalog, codex, codex_project, inventory, paths, settings_merge

PID = "codex-reviewer@agent-loadout"
MARKET = {"agent-loadout": {"source": {"source": "github", "repo": "jonasyr/agent-loadout"}}}


def _desired(monkeypatch, enabled):
    monkeypatch.setattr(settings_merge, "desired_settings",
                        lambda: {"enabledPlugins": enabled, "extraKnownMarketplaces": MARKET})


def test_claude_only_plugin_has_no_codex_route():
    routes, missing = codex.plugin_routes({"enabledPlugins": {PID: True, "loadout@agent-loadout": True},
                                           "extraKnownMarketplaces": MARKET})
    names = sum(routes.values(), [])
    assert "codex-reviewer" not in names and "loadout" in names and missing == []


def test_apply_plugins_says_claude_only_once(fake_home, fake_runner, monkeypatch):
    _desired(monkeypatch, {PID: True})
    lines = codex.apply_plugins(backup.Backup(description="t"))
    assert lines.count(f"plugin {PID}: Claude Code only, not added to Codex") == 1
    assert not any("codex-reviewer" in " ".join(map(str, c)) for c in fake_runner.calls)


def test_profile_mirror_skips_claude_only():
    prof = SimpleNamespace(mcp={}, settings={}, install=[PID, "deepeval@claude-plugins-official"])
    _, plugins, skipped = codex_project._wanted(prof)
    assert plugins == ["deepeval@claude-plugins-official"]
    assert f"plugin {PID}: Claude Code only, not added to Codex" in skipped


def test_catalog_offers_codex_reviewer_off_by_default():
    entry = catalog.by_id("addon-codex-reviewer")
    assert entry["offer"]["plugin"] == PID and entry["target"] == "claude"
    assert PID in catalog.claude_only_plugins()
    kit = json.loads((paths.kit_root() / "settings.base.json").read_text())
    assert PID not in kit["enabledPlugins"]


def test_enabled_addon_is_not_an_own_tool(fake_home):
    [verdict] = inventory.classify([inventory.Item("plugin", PID, "", "user")])
    assert verdict.action != "own"


def test_codex_dry_run_names_claude_only_plugin(fake_home, fake_runner, monkeypatch):
    from loadout import apply
    _desired(monkeypatch, {PID: True})
    res = apply._codex_dry(True, False, True)
    assert f"plugin {PID}: Claude Code only, not added to Codex" in res.lines


def test_update_plan_names_claude_only_plugin(fake_home, fake_runner, monkeypatch):
    from loadout import update
    _desired(monkeypatch, {PID: True, "loadout@agent-loadout": True})
    monkeypatch.setattr(codex, "unavailable", lambda: None)
    monkeypatch.setattr(codex, "program", lambda: "codex")
    monkeypatch.setattr(codex, "installed_plugins", lambda: set())
    monkeypatch.setattr(codex, "unchanged_routes", lambda routes, installed: (set(), set()))
    monkeypatch.setattr(codex, "marketplaces", lambda: {})
    items = []
    update._codex_item(items)
    groups = items[0][-1]
    assert (f"plugin {PID}: Claude Code only, not added to Codex", []) in groups
    assert not any("codex-reviewer" in " ".join(c) for _, cmds in groups for c in cmds)
