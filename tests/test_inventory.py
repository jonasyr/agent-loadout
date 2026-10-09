import pytest

from loadout import catalog, inventory, secrets, versions
from fixtures import FAKE_DEVIN, FAKE_PAT, author_machine


@pytest.fixture
def machine(fake_home, fake_runner):
    author_machine(fake_home)
    return fake_home


def _by_name(verdicts):
    return {(v.item.kind, v.item.name): v for v in verdicts}


def test_catalog_match_by_name_and_contains():
    assert catalog.match("mcp", "github-server", "npx x")["id"] == "mcp-github-reference"
    assert catalog.match("mcp", "gh2", "npx @modelcontextprotocol/server-github")["id"] == "mcp-github-reference"
    assert catalog.match("mcp", "unknown-thing", "foo") is None


def test_classification_of_author_machine(machine):
    v = _by_name(inventory.classify(inventory.collect(with_versions=False)))
    assert v[("mcp", "github-server")].action == "remove"
    assert v[("mcp", "MCP_DOCKER")].action == "review"
    assert v[("mcp", "omarchy-kb")].action == "unknown"
    assert v[("mcp", "serena")].action == "migrate"
    assert v[("mcp", "codebase-memory-mcp")].action == "migrate"
    assert v[("mcp", "sonarqube")].action == "scope-down"
    assert v[("plugin", "auto-memory@severity1-marketplace")].action == "remove"
    assert v[("plugin", "academic-research-skills@academic-research-skills")].action == "scope-down"
    assert v[("plugin", "superpowers@claude-plugins-official")].action == "keep"
    assert v[("plugin", "mystery@somewhere")].action == "unknown"
    assert v[("marketplace", "claude-code-templates")].action == "remove"
    assert v[("marketplace", "claude-plugins-official")].action == "keep"
    assert v[("skill", "gpt-taste")].action == "remove"
    assert v[("skill", "my-skill")].action == "unknown"
    assert v[("hook", "PreToolUse:Bash")].action == "migrate"
    assert v[("hook", "PreToolUse:")].action == "remove"
    assert v[("hook", "PreToolUse:Read")].action == "scope-down"
    assert v[("hook", "PreToolUse:Edit")].action == "unknown"
    assert v[("hook", "Stop:")].action == "remove"
    assert v[("claude-md", "CLAUDE.md")].action == "review"


def test_project_scoped_mcp_is_not_touched(machine):
    # The fixture has a project-scoped "serena" (no args) under projects; only the top-level one counts.
    serena = [i for i in inventory.collect(with_versions=False) if i.kind == "mcp" and i.name == "serena"]
    assert len(serena) == 1
    assert serena[0].extra["config"]["args"] == ["start-mcp-server", "--context=claude-code", "--project-from-cwd"]


def test_secret_scan_finds_env_and_args():
    claude_json = {"mcpServers": {
        "a": {"env": {"DEVIN_API_KEY": FAKE_DEVIN, "HARMLESS": "1"}},
        "b": {"args": [f"TOKEN={FAKE_PAT}"]},
        "c": {"headers": {"Authorization": "Bearer ${MY_TOKEN}"}},
    }}
    found = secrets.scan(claude_json)
    assert [(f.server, f.field, f.fixable) for f in found] == [("a", "env", True), ("b", "args", False)]
    assert found[0].key == "DEVIN_API_KEY"
    assert secrets.var_name("github-server", "x") == "GITHUB_SERVER_X"


def test_versions_parse_and_offline(monkeypatch):
    assert versions.parse_version("Serena 1.7.0") == (1, 7, 0)
    assert versions.parse_version("v0.11.0") == (0, 11, 0)
    assert versions.parse_version("nothing") is None

    def boom(url):
        raise OSError("offline")

    monkeypatch.setattr(versions, "_fetch_json", boom)
    assert versions.latest_version({"version": {"cmd": ["x"], "github": "o/r"}}) is None


def test_binary_outdated_and_missing(fake_home, fake_runner, monkeypatch):
    from loadout import runner
    fake_runner.responses[("serena", "--version")] = runner.Result(0, "Serena 1.7.0", "")
    fake_runner.missing.add("codebase-memory-mcp")
    monkeypatch.setattr(versions, "latest_version", lambda e: (1, 8, 0) if e["id"] == "serena" else None)
    v = {(x.item.kind, x.item.name): x for x in inventory.classify(inventory.collect(with_versions=True))}
    assert v[("binary", "serena")].action == "update"
    assert "1.7.0 -> 1.8.0" in v[("binary", "serena")].item.detail
    assert v[("binary", "codebase-memory-mcp")].action == "install"


def test_malformed_mcp_config_does_not_crash(fake_home, fake_runner):
    from fixtures import _w
    bad = {"mcpServers": {
        "weird-args": {"command": "x", "args": None},
        "mixed-args": {"command": "y", "args": ["a", 3]},
        "weird-env": {"command": "z", "args": ["k=v"], "env": "x"},
    }}
    _w(fake_home / ".claude.json", bad)
    names = {i.name for i in inventory.collect(with_versions=False) if i.kind == "mcp"}
    assert names == {"weird-args", "mixed-args", "weird-env"}
    assert secrets.scan(bad) == []


def test_collect_survives_non_dict_entries(fake_home, fake_runner):
    import json as _json
    from loadout import inventory as inv
    (fake_home / ".claude").mkdir(exist_ok=True)
    (fake_home / ".claude.json").write_text(_json.dumps({"mcpServers": {"odd": "x", "ok": {"command": "y"}}}))
    (fake_home / ".claude/settings.json").write_text(_json.dumps({"hooks": {"Stop": ["bad", {"hooks": ["bad", {"command": "c"}]}], "X": "bad"}}))
    items = inv.collect(with_versions=False)
    assert [i.name for i in items if i.kind == "mcp"] == ["ok"]
    assert [i.detail for i in items if i.kind == "hook"] == ["c"]
