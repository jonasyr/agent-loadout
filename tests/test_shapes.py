"""Wrongly shaped but valid JSON never crashes a command (hardening 2, task 1).

Each test names the reader it covers. A wrong shape is treated as missing; when the user must fix a file, one line
names it.
"""
import json

import pytest

from loadout import backup, check, codex, configure, inventory, jsonio, own, paths, personal_mcp, profiles, runner
from loadout import settings_merge

WRONG = [None, 5, "x", ["a"]]
IDS = ["null", "5", "str", "list"]


def _w(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _personal(name, data):
    _w(paths.personal_root() / name, data)


def _codex_on():
    _personal("targets.json", {"claude": True, "codex": True})


def test_get_dict_and_get_list():
    assert jsonio.get_dict({"a": {"b": 1}}, "a") == {"b": 1}
    assert jsonio.get_dict({"a": None}, "a") == {}
    assert jsonio.get_dict(None, "a") == {}
    assert jsonio.get_dict({"a": [1]}, "a") == {}
    assert jsonio.get_list({"a": [1]}, "a") == [1]
    assert jsonio.get_list({"a": "x"}, "a") == []
    assert jsonio.get_list([], "a") == []


# --- settings_merge.desired_settings (consumers: check, configure, bootstrap, codex, codex_project) ---------------

@pytest.mark.parametrize("bad", WRONG, ids=IDS)
@pytest.mark.parametrize("key", ["enabledPlugins", "extraKnownMarketplaces"])
def test_desired_settings_keeps_the_kit_dicts_when_personal_has_a_wrong_container(fake_home, key, bad):
    _personal("settings.json", {key: bad})
    desired = settings_merge.desired_settings()
    assert isinstance(desired[key], dict) and desired[key], key


@pytest.mark.parametrize("bad", WRONG, ids=IDS)
def test_desired_settings_marketplace_source_is_a_dict(fake_home, bad):
    _personal("settings.json", {"extraKnownMarketplaces": {"mine": {"source": bad}, "other": bad}})
    desired = settings_merge.desired_settings()
    assert isinstance(desired["extraKnownMarketplaces"]["mine"]["source"], dict)
    assert all(isinstance(m, dict) and isinstance(m.get("source"), dict)
               for m in desired["extraKnownMarketplaces"].values())


@pytest.mark.parametrize("bad", WRONG, ids=IDS)
def test_apply_settings_with_a_wrong_personal_hooks_value(fake_home, bad):
    _personal("settings.json", {"hooks": bad})
    settings_merge.apply_settings()  # reader: settings_merge.effective_desired / _plan
    settings_merge.drift()


@pytest.mark.parametrize("bad", WRONG, ids=IDS)
def test_check_with_wrong_personal_settings(fake_home, fake_runner, bad):
    """Reader: check._plugins and check._settings through desired_settings."""
    _personal("settings.json", {"enabledPlugins": bad, "extraKnownMarketplaces": bad, "hooks": bad})
    check.run_checks()


@pytest.mark.parametrize("bad", WRONG, ids=IDS)
def test_configure_show_and_addons_with_wrong_personal_settings(fake_home, bad):
    """Reader: configure.addons / is_on / show."""
    _personal("settings.json", {"enabledPlugins": bad, "extraKnownMarketplaces": bad})
    _personal("mcp.json", {"mcpServers": bad})
    configure.addons()
    configure.show()


@pytest.mark.parametrize("bad", WRONG, ids=IDS)
def test_configure_set_plugin_and_mcp_over_a_wrong_container(fake_home, bad):
    """Reader: configure.set_plugin / set_mcp write into a container the user's file holds in a wrong shape."""
    _personal("settings.json", {"enabledPlugins": bad})
    configure.set_plugin("x@y", True)
    assert jsonio.load_json(paths.personal_root() / "settings.json")["enabledPlugins"] == {"x@y": True}
    _personal("mcp.json", {"mcpServers": bad})
    configure.set_mcp("addon-dbhub-global", True)


@pytest.mark.parametrize("bad", WRONG, ids=IDS)
def test_personal_index_with_wrong_personal_files(fake_home, bad):
    """Reader: own.personal_index (settings.json, mcp.json, profiles), also with the settings of the machine."""
    _personal("settings.json", {"enabledPlugins": bad, "extraKnownMarketplaces": bad, "hooks": bad})
    _personal("mcp.json", {"mcpServers": bad})
    _w(fake_home / ".claude/settings.json", {"enabledPlugins": bad})
    assert own.personal_index()["plugin"] == {} or isinstance(own.personal_index()["plugin"], dict)


@pytest.mark.parametrize("hooks", WRONG + [{"Stop": None}, {"Stop": [{"hooks": 5}]}, {"Stop": [{"hooks": None}]}])
def test_personal_index_hook_shapes(fake_home, hooks):
    """Reader: own._hook_commands."""
    _personal("settings.json", {"hooks": hooks})
    own.personal_index()


@pytest.mark.parametrize("prof", [
    {"install": None}, {"install": ["ok@m", 5]}, {"install": "x"}, {"mcp": None}, {"mcp": {"mcpServers": None}},
    {"mcp": []}, {"skills": None}, {"skills": [["a"], 5]}, {"settings": None}, {"settings": {"hooks": 5}},
    {"settings": []}, {"commands": None}, {"commands": [["ok"], "x"]}])
def test_personal_index_skips_a_broken_profile(fake_home, prof):
    """Reader: own.personal_index over ~/personal/profiles/*.json; a broken profile is skipped, a good one counts."""
    _personal("profiles/bad.json", {"description": "d", **prof})
    _personal("profiles/good.json", {"description": "d", "install": ["p@m"]})
    index = own.personal_index()
    assert index["_profile"]["plugin"].get("p@m")


# --- inventory ---------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("bad", WRONG, ids=IDS)
def test_inventory_with_wrong_files(fake_home, fake_runner, bad):
    """Reader: inventory.collect / classify (mcp servers, installed plugins, marketplaces, hooks, settings)."""
    _w(fake_home / ".claude.json", {"mcpServers": bad})
    _w(fake_home / ".claude/.mcp.json", {"mcpServers": bad})
    _w(fake_home / ".claude/plugins/installed_plugins.json", {"plugins": bad})
    _w(fake_home / ".claude/settings.json", {"hooks": bad, "enabledPlugins": bad})
    _w(fake_home / ".claude/plugins/known_marketplaces.json", {"m": bad})
    _personal("settings.json", {"enabledPlugins": bad, "extraKnownMarketplaces": bad})
    inventory.classify(inventory.collect(False))


# --- check, bootstrap -----------------------------------------------------------------------------------------

@pytest.mark.parametrize("bad", WRONG, ids=IDS)
def test_check_with_wrong_installed_plugins_and_settings(fake_home, fake_runner, bad):
    """Reader: check._plugins (installed_plugins.json) and check._connectors (settings.json enabledPlugins)."""
    _w(fake_home / ".claude/plugins/installed_plugins.json", {"plugins": bad})
    _w(fake_home / ".claude/settings.json", {"enabledPlugins": bad})
    _w(fake_home / ".claude.json", {"claudeAiMcpEverConnected": bad, "mcpServers": bad})
    check.run_checks()


@pytest.mark.parametrize("bad", WRONG, ids=IDS)
def test_bootstrap_setup_plugins_with_wrong_files(fake_home, fake_runner, bad):
    """Reader: bootstrap.setup_plugins (extraKnownMarketplaces, enabledPlugins, installed_plugins.json)."""
    from loadout import bootstrap
    _personal("settings.json", {"extraKnownMarketplaces": {"m": {"source": bad}, "n": bad}, "enabledPlugins": bad})
    _w(fake_home / ".claude/plugins/installed_plugins.json", {"plugins": bad})
    bootstrap.setup_plugins()


# --- personal_mcp ---------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("bad", WRONG, ids=IDS)
@pytest.mark.parametrize("which", ["personal", "claude", "managed"])
def test_apply_mcp_with_wrong_mcpservers(fake_home, fake_runner, which, bad):
    """Reader: personal_mcp.apply_mcp over personal mcp.json, ~/.claude.json and managed-mcp.json."""
    _personal("mcp.json", {"mcpServers": bad if which == "personal" else {"a": {"command": "x"}}})
    _w(fake_home / ".claude.json", {"mcpServers": bad if which == "claude" else {}})
    _w(paths.state_dir() / "managed-mcp.json", {"mcpServers": bad if which == "managed" else {}})
    assert isinstance(personal_mcp.apply_mcp(), list)


# --- codex ----------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("bad", [None, ["x"], 5, "x"], ids=["null", "list", "5", "str"])
@pytest.mark.parametrize("key", ["tables", "keys"])
def test_codex_record_with_wrong_tables(fake_home, fake_runner, key, bad):
    """Reader: codex.apply_config / user_servers / drift / checks over codex-config.json."""
    _codex_on()
    _personal("mcp.json", {"mcpServers": {"a": {"command": "x"}}})
    _w(codex.record_path(), {key: bad})
    codex.apply_config(backup.Backup(description="t"))
    codex.user_servers()
    codex.drift()
    codex.checks()


@pytest.mark.parametrize("bad", WRONG, ids=IDS)
def test_codex_with_wrong_settings_and_mcp(fake_home, fake_runner, bad):
    """Reader: codex.desired_tables / desired_keys / plugin_routes / drift (personal files, ~/.claude.json)."""
    _codex_on()
    _personal("settings.json", {"enabledPlugins": bad, "extraKnownMarketplaces": bad})
    _personal("mcp.json", {"mcpServers": bad})
    _w(fake_home / ".claude.json", {"mcpServers": bad})
    fake_runner.responses[("codex", "mcp", "list")] = runner.Result(0, "[]", "")
    codex.apply_all(backup.Backup(description="t"))
    codex.drift()


@pytest.mark.parametrize("bad", WRONG, ids=IDS)
def test_codex_plugin_routes_with_wrong_marketplaces(bad):
    """Reader: codex.plugin_routes."""
    codex.plugin_routes({"enabledPlugins": {"a@m": True, "b@n": True}, "extraKnownMarketplaces": {"m": bad, "n": {"source": bad}}})
    codex.plugin_routes({"enabledPlugins": bad, "extraKnownMarketplaces": bad})


@pytest.mark.parametrize("bad", WRONG, ids=IDS)
def test_codex_plugin_servers_with_wrong_plugin_mcp(fake_home, fake_runner, bad):
    """Reader: codex._plugin_servers (a cached plugin's .mcp.json)."""
    _codex_on()
    _w(paths.codex_home() / "plugins/cache/a/b/c/.mcp.json", {"mcpServers": bad})
    fake_runner.responses[("codex", "mcp", "list")] = runner.Result(0, json.dumps([{"name": "z"}]), "")
    codex.drift()


@pytest.mark.parametrize("out,expected", [
    ('WARN [x] something\n{"installed": [{"pluginId": "a@b"}]}', {"a@b"}),
    ('{"installed": null}', set()),
    ('["a@b"]', None),
    ('{"installed": [{"x": 1}, "a@b", {"pluginId": ["l"]}, {"pluginId": "c@d"}]}', {"c@d"}),
    ('{"installed": 5}', set()),
    ("WARN [x] only a warning", None),
    ("{broken", None),
])
def test_codex_installed_plugins_parser(fake_runner, out, expected):
    """Reader: codex.installed_plugins / codex._json."""
    fake_runner.responses[("codex", "plugin", "list")] = runner.Result(0, out, "")
    assert codex.installed_plugins() == expected


@pytest.mark.parametrize("out,expected", [
    ('[{"name": "a"}, {"x": 1}, {"name": ["l"]}, {"name": "b"}, "c"]', {"a", "b"}),
    ('WARN [x] hi\n[{"name": "a"}]', {"a"}),
    ('{"name": "a"}', None),
    ("[broken", None),
])
def test_codex_mcp_names_parser(fake_runner, out, expected):
    """Reader: codex.mcp_names / codex._json."""
    fake_runner.responses[("codex", "mcp", "list")] = runner.Result(0, out, "")
    assert codex.mcp_names() == expected


def test_codex_json_never_raises():
    for text in ["", "{", "[", "WARN [x]\n{bad", "5", "null", "}{", "[1,"]:
        codex._json(text)


# --- profiles -------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("field,value", [
    ("install", None), ("install", "x"), ("commands", None), ("commands", "x"),
    ("skills", None), ("skills", "x"), ("settings", None), ("settings", []), ("mcp", None), ("mcp", "x"),
    ("description", 5), ("notes", None)])
def test_load_profile_names_the_file_for_a_wrong_field(fake_home, field, value):
    """Reader: profiles.load_profile; main prints a ValueError as one line."""
    _personal("profiles/bad.json", {"description": "d", field: value})
    with pytest.raises(ValueError) as exc:
        profiles.load_profile("bad")
    msg = str(exc.value)
    assert "bad.json" in msg and field in msg and "\n" not in msg


def test_load_profile_accepts_a_good_profile(fake_home):
    _personal("profiles/ok.json", {"description": "d", "install": ["a@b"], "commands": [["x"]], "skills": ["s"],
                                   "settings": {}, "mcp": {}, "notes": "n"})
    assert profiles.load_profile("ok").install == ["a@b"]


def test_cli_prints_a_bad_profile_as_one_line(fake_home, tmp_path, monkeypatch, capsys):
    """Reader: __main__.main prints the ValueError of load_profile as one line, no traceback."""
    from loadout.__main__ import main
    monkeypatch.chdir(tmp_path)
    _personal("profiles/bad.json", {"install": None})
    assert main(["profile", "bad", "--no-install"]) != 0
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err + captured.out
    assert "bad.json" in captured.err + captured.out


# --- backups --------------------------------------------------------------------------------------------------------

def _backup_dir(name, manifest):
    d = paths.backups_root() / name
    _w(d / "manifest.json", manifest)
    return d


@pytest.mark.parametrize("manifest", [
    {"steps": None}, {"steps": "x"}, {"steps": 5}, {"created_at": "x", "steps": []}, {"created_at": None, "steps": []},
    {"steps": [{"label": 5}]}, {"steps": ["x", 5]}, {"description": 5, "steps": []}, {"restored_at": "x", "steps": []}])
def test_list_backups_tolerates_a_damaged_manifest(fake_home, manifest):
    """Reader: backup.list_backups."""
    _backup_dir("2026-01-01-bad", manifest)
    _backup_dir("2026-01-02-good", {"created_at": 1700000000, "description": "ok", "steps": []})
    lines = backup.list_backups()
    assert any("ok" in line for line in lines)


@pytest.mark.parametrize("manifest", [
    {"steps": None}, {"steps": "x"}, {"steps": [{"label": 5}]}, {"steps": ["x"]}, {"restored_at": "x", "steps": []},
    {"steps": [{"label": ["l"], "undo": 5}]}])
def test_restore_tolerates_a_damaged_manifest(fake_home, fake_runner, manifest):
    """Reader: backup.restore."""
    d = _backup_dir("2026-01-01-bad", manifest)
    lines, ok, _ = backup.restore(d, force=True)
    assert all(isinstance(line, str) for line in lines)
    if manifest.get("steps") is None or isinstance(manifest.get("steps"), (str, int)):
        assert not ok and any("damaged" in line for line in lines)
