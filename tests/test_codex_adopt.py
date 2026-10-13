"""adopt sees MCP servers and skills that only Codex has."""
import sys

import pytest

from loadout import codex, inventory, own, paths, targets
from loadout.jsonio import save_json



@pytest.fixture
def codex_on(fake_home, monkeypatch):
    monkeypatch.setattr(targets, "codex_enabled", lambda: True)
    monkeypatch.setattr(codex, "_plugin_servers", lambda: {"codebase-memory-mcp"})


def _config(text):
    cfg = paths.codex_home() / "config.toml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(text)


def test_to_claude_maps_codex_keys():
    assert codex.to_claude("a", {"command": "x", "args": ["-y"], "env": {"K": "v"}, "env_vars": ["TOKEN"]}) == {
        "type": "stdio", "command": "x", "args": ["-y"], "env": {"K": "v", "TOKEN": "${TOKEN}"}}
    assert codex.to_claude("b", {"url": "https://h/mcp", "bearer_token_env_var": "T",
                                 "env_http_headers": {"X-Key": "XK"}, "http_headers": {"X-A": "1"}}) == {
        "type": "http", "url": "https://h/mcp",
        "headers": {"X-A": "1", "Authorization": "Bearer ${T}", "X-Key": "${XK}"}}


def test_to_claude_refuses_what_claude_cannot_express():
    with pytest.raises(codex.Refused, match="startup_timeout_sec"):
        codex.to_claude("a", {"command": "x", "startup_timeout_sec": 30})
    with pytest.raises(codex.Refused, match="tools"):
        codex.to_claude("a", {"command": "x", "tools": {"y": {"approval_mode": "approve"}}})


def test_codex_only_servers_are_items(codex_on):
    _config('[mcp_servers.mine]\ncommand = "m"\n\n[mcp_servers.codebase-memory-mcp]\ncommand = "c"\n\n'
            '[mcp_servers.both]\ncommand = "b"\n\n[mcp_servers.odd]\ncommand = "o"\nstartup_timeout_sec = 9\n')
    save_json(paths.claude_json(), {"mcpServers": {"both": {"command": "b"}}})
    items = {i.name: i for i in inventory.collect(with_versions=False) if i.location == codex.CONFIG_LOCATION}
    assert set(items) == {"mine", "odd"}  # plugin servers and servers Claude Code also has are not Codex-only
    assert items["mine"].extra["config"] == {"type": "stdio", "command": "m"}
    assert items["odd"].extra["config"] is None and "startup_timeout_sec" in items["odd"].extra["problem"]


def test_servers_loadout_wrote_are_not_items(codex_on):
    _config('[mcp_servers.serena]\ncommand = "serena"\n')
    save_json(codex.record_path(), {"tables": {"serena": '[mcp_servers.serena]\ncommand = "serena"\n'}, "keys": {}})
    assert not [i for i in inventory.collect(with_versions=False) if i.location == codex.CONFIG_LOCATION]


def test_codex_only_skills_are_items(codex_on):
    (paths.agents_skills() / "solo").mkdir(parents=True)
    (paths.agents_skills() / "shared").mkdir()
    (paths.claude_home() / "skills" / "shared").mkdir(parents=True)
    names = {i.name for i in inventory.collect(with_versions=False)
             if i.kind == "skill" and own.is_codex(i)}
    assert names == {"solo"}


def test_nothing_from_codex_when_it_is_off(fake_home, monkeypatch):
    monkeypatch.setattr(targets, "codex_enabled", lambda: False)
    (paths.agents_skills() / "solo").mkdir(parents=True)
    assert not [i for i in inventory.collect(with_versions=False) if own.is_codex(i)]


def test_codex_items_have_their_own_keys_and_choices(codex_on):
    mcp = inventory.Item("mcp", "mine", "m", codex.CONFIG_LOCATION, {"config": {"command": "m"}})
    skill = inventory.Item("skill", "solo", "x", str(paths.agents_skills() / "solo"), {})
    assert own.decision_key(mcp) == "mcp:codex:mine"
    assert own.decision_key(skill) == "skill:codex:solo"
    assert own.options(mcp) == ["global", "leave", "remove"]
    assert own.options(skill) == ["global", "leave", "remove"]


def test_codex_items_are_own_tools_not_catalog_matches(codex_on):
    item = inventory.Item("mcp", "serena", "serena", codex.CONFIG_LOCATION, {"config": {"command": "serena"}})
    (verdict,) = inventory.classify([item])
    assert verdict.action == "own"


@pytest.mark.parametrize("table", [{"command": "x", "env": ["x"]}, {"command": "x", "env_vars": "T"},
                                   {"command": "x", "args": "-y"}, {"url": "u", "http_headers": ["a"]},
                                   {"command": ["x"]}, {"url": 3}])
def test_to_claude_refuses_odd_shapes(table):
    with pytest.raises(codex.Refused):
        codex.to_claude("a", table)


def test_a_server_with_odd_args_is_listed_not_a_crash(codex_on):
    _config('[mcp_servers.odd]\ncommand = "o"\nargs = 1\n')
    (item,) = [i for i in inventory.collect(with_versions=False) if i.location == codex.CONFIG_LOCATION]
    assert item.extra["config"] is None and "args" in item.extra["problem"]


def test_a_non_table_mcp_servers_value_is_not_a_crash(codex_on):
    _config("mcp_servers = 1\n")
    assert codex.user_servers() == {}
