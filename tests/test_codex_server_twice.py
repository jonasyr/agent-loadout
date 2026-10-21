"""loadout check names a Codex MCP server the user defined in config.toml that the loadout plugin also provides."""
import json

import pytest

from loadout import codex, paths

USER_TABLE = ('[mcp_servers.codebase-memory-mcp]\ncommand = "codebase-memory-mcp"\n\n'
              '[mcp_servers.codebase-memory-mcp.tools.search_graph]\napproval_mode = "approve"\n')
DETAIL = "defined in config.toml and by the loadout plugin; Codex starts one of them"
FIX = ("remove your [mcp_servers.codebase-memory-mcp] from ~/.codex/config.toml (the plugin provides it), "
       "or turn the loadout plugin off in Codex")


def _plugin(market="agent-loadout", name="loadout", servers=("codebase-memory-mcp",), manifest=None):
    root = paths.codex_home() / "plugins" / "cache" / market / name / "local"
    (root / ".codex-plugin").mkdir(parents=True)
    (root / ".codex-plugin" / "plugin.json").write_text(
        manifest if manifest is not None else json.dumps({"mcpServers": "./.codex-mcp.json"}))
    (root / ".codex-mcp.json").write_text(json.dumps({"mcpServers": {s: {"command": s} for s in servers}}))
    return root


@pytest.fixture
def check(fake_home, fake_runner, monkeypatch):
    for name, value in (("enabled", lambda: True), ("unavailable", lambda: None), ("hooks_status", lambda: "trusted"),
                        ("logins_needed", lambda: []), ("drift", lambda: []),
                        ("installed_plugins", lambda: {"loadout@agent-loadout"}),
                        ("missing_routes", lambda installed=None: ([], [])),
                        ("apply_config", lambda bk, dry_run=False: [])):
        monkeypatch.setattr(codex, name, value)
    monkeypatch.setattr(codex.runner, "have", lambda b: b == "codex")
    cfg = paths.codex_home() / "config.toml"
    cfg.parent.mkdir(parents=True, exist_ok=True)

    def rows(text=USER_TABLE):
        cfg.write_text(text)
        return [r for r in codex.checks() if r.name == "Codex MCP codebase-memory-mcp"]
    return rows


def test_a_user_table_next_to_the_plugins_server_is_named(check):
    _plugin()
    (row,) = check()
    assert not row.ok and row.severity == "warn"
    assert row.detail == DETAIL and row.fix == FIX


def test_a_disabled_plugin_gives_nothing(check):
    _plugin()
    assert check(USER_TABLE + '\n[plugins."loadout@agent-loadout"]\nenabled = false\n') == []


def test_an_enabled_plugin_line_still_names_it(check):
    _plugin()
    assert len(check(USER_TABLE + '\n[plugins."loadout@agent-loadout"]\nenabled = true\n')) == 1


def test_no_installed_plugin_gives_nothing(check, monkeypatch):
    assert check() == []
    _plugin()
    monkeypatch.setattr(codex, "installed_plugins", lambda: set())  # left in the cache, not installed
    assert check() == []


def test_another_plugins_server_of_that_name_gives_nothing(check):
    _plugin(market="other", name="plug")
    assert check() == []


def test_a_broken_manifest_gives_nothing_and_no_crash(check):
    _plugin(manifest="{not json")
    assert check() == []


def test_a_broken_server_file_gives_nothing_and_no_crash(check):
    root = _plugin()
    (root / ".codex-mcp.json").write_text("{not json")
    assert check() == []


def test_no_user_table_gives_nothing(check):
    _plugin()
    assert check('[mcp_servers.other]\ncommand = "x"\n') == []
