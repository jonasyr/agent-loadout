"""Bootstrap says what it is doing during the slow Claude plugin step; Codex is told its MCP tools load on demand."""
from loadout import bootstrap, codex, runner, settings_merge


def test_claude_plugin_step_announces_slow_work(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: {
        "extraKnownMarketplaces": {"impeccable": {"source": {"source": "github", "repo": "pbakaus/impeccable"}}},
        "enabledPlugins": {"impeccable@impeccable": True}})
    fake_runner.responses[("claude", "plugin", "marketplace", "list")] = runner.Result(0, "", "")
    said = []
    bootstrap.setup_plugins(say=said.append)
    assert any("pbakaus/impeccable" in s and "can take a few minutes" in s for s in said)
    assert any("impeccable@impeccable" in s for s in said)


def test_codex_block_says_mcp_tools_load_on_demand(fake_home):
    block = codex.render_instructions()
    assert "load on demand" in block and "Serena" in block and "codebase-memory" in block
