"""A user's own codebase-memory table in Codex's config.toml, under any name: named by check, offered to adopt."""
import pytest

from loadout import adopt, backup, codex, inventory, paths, targets
from loadout.inventory import Item, Verdict

from test_codex_server_twice import INSTALLED, _plugin  # noqa: F401  (the plugin cache helper)

DETAIL = "runs codebase-memory-mcp next to the loadout plugin's; Codex starts two"
PLAIN = '[mcp_servers.cbm]\ncommand = "codebase-memory-mcp"\n'
OWN = PLAIN + 'env = { CBM_CACHE_DIR = "/x" }\n'
REASON_MIGRATE = "Provided by loadout's Codex plugin; this table starts a second codebase-memory server."
REASON_KEEP = ("It starts codebase-memory with settings of its own (env, args or a fixed path); remove it yourself "
               "if loadout's plugin should serve it.")


@pytest.fixture
def cfg(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(targets, "codex_enabled", lambda: True)
    monkeypatch.setattr(targets, "claude_enabled", lambda: False)
    path = paths.codex_home() / "config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)

    def write(text):
        path.write_text(text)
    return write


def test_is_cbm_recognises_commands():
    for table in ({"command": "codebase-memory-mcp"}, {"command": "/home/u/.local/bin/codebase-memory-mcp"},
                  {"command": "C:\\x\\codebase-memory-mcp.exe"},
                  {"command": "npx", "args": ["-y", "codebase-memory-mcp"]}):
        assert codex.is_cbm(table), table
    for table in ({"command": "serena"}, {"command": "cbm-other"}, {"command": "uvx", "args": ["serena"]}):
        assert not codex.is_cbm(table), table


def test_own_settings():
    assert not codex.cbm_has_own_settings({"command": "codebase-memory-mcp"})
    assert not codex.cbm_has_own_settings({"command": "codebase-memory-mcp", "args": ["mcp"]})
    assert codex.cbm_has_own_settings({"command": "codebase-memory-mcp", "env": {"A": "b"}})
    assert codex.cbm_has_own_settings({"command": "codebase-memory-mcp", "env_vars": ["A"]})
    assert codex.cbm_has_own_settings({"command": "codebase-memory-mcp", "args": ["--x"]})
    assert codex.cbm_has_own_settings({"command": "/opt/codebase-memory-mcp"})


def test_a_cbm_table_under_another_name_is_named_twice(cfg, monkeypatch):
    for name, value in (("enabled", lambda: True), ("unavailable", lambda: None), ("hooks_status", lambda: "trusted"),
                        ("logins_needed", lambda: []), ("drift", lambda: []),
                        ("installed_plugins", lambda: INSTALLED),
                        ("missing_routes", lambda installed=None: ([], [])),
                        ("apply_config", lambda bk, dry_run=False: [])):
        monkeypatch.setattr(codex, name, value)
    monkeypatch.setattr(codex.runner, "have", lambda b: b == "codex")
    _plugin()
    cfg(PLAIN)
    (row,) = [r for r in codex.checks() if r.name == "Codex MCP cbm"]
    assert not row.ok and row.severity == "warn" and row.detail == DETAIL
    assert row.fix.startswith("remove your [mcp_servers.cbm] from ") and row.fix.endswith(
        "(the plugin provides it), or turn the loadout plugin off in Codex")
    cfg(PLAIN + '\n[plugins."loadout@agent-loadout"]\nenabled = false\n')
    assert not [r for r in codex.checks() if r.name == "Codex MCP cbm"]


def test_a_cbm_table_is_never_offered_for_claude_code(cfg):
    _plugin()  # the plugin serves codebase-memory, so the table is a second server
    cfg(PLAIN)
    assert [i for i in inventory._codex_items() if i.name == "cbm"] == []
    (v,) = [v for v in inventory.classify([]) if v.item.name == "cbm"]
    assert (v.action, v.reason, v.entry_id) == ("migrate", REASON_MIGRATE, "mcp-codebase-memory")


def test_a_cbm_table_with_its_own_settings_is_only_named(cfg):
    _plugin()
    cfg(OWN)
    (v,) = [v for v in inventory.classify([]) if v.item.name == "cbm"]
    assert (v.action, v.reason) == ("keep", REASON_KEEP)


def test_adopt_removes_a_cbm_table_with_a_backup(cfg, fake_runner):
    _plugin()
    cfg(PLAIN)
    (v,) = [v for v in inventory.classify([]) if v.item.name == "cbm"]
    bk = backup.Backup(description="t")
    out = adopt.apply([v], bk, confirm_cmds=False)
    assert ["codex", "mcp", "remove", "cbm"] in fake_runner.calls
    assert any("cbm" in line for line in out)
    assert any("config.toml" in s.get("label", "") for s in bk.steps)  # saved first: restore brings it back


def test_claude_server_named_cbm_migrates(fake_home):
    from loadout.jsonio import save_json
    save_json(paths.claude_json(), {"mcpServers": {"cbm": {"command": "codebase-memory-mcp"}}})
    (v,) = [v for v in inventory.classify(inventory.collect(with_versions=False)) if v.item.name == "cbm"]
    assert (v.action, v.entry_id) == ("migrate", "mcp-codebase-memory")


# --- fix round 1 ---------------------------------------------------------------------------------------------------

SAME = '[mcp_servers.codebase-memory-mcp]\ncommand = "codebase-memory-mcp"\n'


def test_the_same_name_table_keeps_todays_handling_without_the_plugin(cfg):
    cfg(SAME)
    assert [i.name for i in inventory._codex_items()] == ["codebase-memory-mcp"]
    (item,) = inventory._codex_items()
    assert item.extra["config"] == {"type": "stdio", "command": "codebase-memory-mcp"}
    (v,) = [v for v in inventory.classify([item]) if v.item.name == "codebase-memory-mcp"]
    assert v.action == "own"  # as before: no new verdict, no cbm reason
    assert v.reason != REASON_MIGRATE


def test_a_name_in_claude_json_gets_no_codex_verdict(cfg, monkeypatch):
    from loadout.jsonio import save_json
    monkeypatch.setattr(targets, "claude_enabled", lambda: True)
    save_json(paths.claude_json(), {"mcpServers": {"cbm": {"command": "codebase-memory-mcp"}}})
    cfg(PLAIN)
    assert [v for v in inventory.classify([]) if v.item.location == codex.CONFIG_LOCATION] == []


def test_drift_does_not_offer_a_cbm_table_under_another_name(cfg, monkeypatch):
    monkeypatch.setattr(targets, "claude_enabled", lambda: True)
    cfg(PLAIN)
    monkeypatch.setattr(codex, "mcp_names", lambda: {"cbm"})
    assert not [line for line in codex.drift() if '"cbm"' in line]


def test_other_table_keys_count_as_own_settings():
    base = {"command": "codebase-memory-mcp"}
    for key, value in (("startup_timeout_sec", 30), ("cwd", "/x"), ("tool_timeout_sec", 5),
                       ("enabled_tools", ["a"]), ("disabled_tools", ["b"])):
        assert codex.cbm_has_own_settings({**base, key: value}), key
    assert not codex.cbm_has_own_settings({**base, "enabled": True, "type": "stdio"})


def test_a_leave_decision_keeps_the_cbm_table(cfg):
    from loadout import own
    cfg(PLAIN)
    (v,) = [v for v in inventory.classify([]) if v.item.name == "cbm"]
    left = {own.decision_key(v.item): "leave"}
    (w,) = inventory._codex_cbm_verdicts(left)
    assert (w.action, w.reason) == ("keep", own.LEFT_REASON)


def test_with_codex_off_there_are_no_cbm_verdicts_and_nothing_is_read(cfg, monkeypatch):
    cfg(PLAIN)
    monkeypatch.setattr(targets, "codex_enabled", lambda: False)
    monkeypatch.setattr(codex, "user_servers", lambda *a, **k: pytest.fail("read ~/.codex"))
    assert inventory.classify([]) == []


REASON_ONLY = ("Codex's only codebase-memory server here: loadout's plugin does not serve it (not installed, or "
               "switched off); keep it, or turn the plugin on first.")


@pytest.mark.parametrize("extra, plugin", [("", False),
                                           ('\n[plugins."loadout@agent-loadout"]\nenabled = false\n', True),
                                           ('\n[mcp_servers.codebase-memory-mcp]\nenabled = false\n', True)])
def test_no_removal_offer_when_the_plugin_does_not_serve_cbm(cfg, extra, plugin):
    if plugin:
        _plugin()
    cfg(PLAIN + extra)
    (v,) = [v for v in inventory.classify([]) if v.item.name == "cbm"]
    assert (v.action, v.reason) == ("keep", REASON_ONLY)


def test_a_switched_off_table_is_neither_named_twice_nor_offered(cfg):
    _plugin()
    cfg(PLAIN + "enabled = false\n")
    assert [v for v in inventory.classify([]) if v.item.name == "cbm"] == []
    assert codex.cbm_twice(INSTALLED) == []


def test_cbm_twice_needs_the_plugins_server_on(cfg):
    _plugin()
    cfg(PLAIN + '\n[mcp_servers.codebase-memory-mcp]\nenabled = false\n')
    assert codex.cbm_twice(INSTALLED) == []
