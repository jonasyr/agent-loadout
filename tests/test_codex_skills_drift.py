"""Personal skills linked for Codex; MCP servers and skills present in only one agent are reported."""
import json
import os

import pytest

from loadout import backup, codex, paths, runner


def _personal_skill(name):
    d = paths.personal_root() / "skills" / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: x\n---\n", encoding="utf-8")
    return d


@pytest.mark.skipif(os.name == "nt", reason="symlinks need Developer Mode on Windows; copy mode is covered by link tests")
def test_personal_skills_are_linked_for_codex(fake_home):
    src = _personal_skill("my-skill")
    lines = codex.apply_skills(backup.Backup(description="t"))
    dest = paths.agents_skills() / "my-skill"
    assert dest.is_symlink() and dest.resolve() == src.resolve() and lines


def _codex_mcp(fake_runner, names):
    fake_runner.responses[("codex", "mcp", "list")] = runner.Result(0, json.dumps([{"name": n} for n in names]), "")


def test_drift_names_servers_and_skills_in_only_one_agent(fake_home, fake_runner):
    paths.claude_json().write_text(json.dumps({"mcpServers": {"only-claude": {}, "both": {}}}), encoding="utf-8")
    _codex_mcp(fake_runner, ["both", "only-codex", "serena"])
    (paths.claude_home() / "skills" / "claude-skill").mkdir(parents=True)
    (paths.agents_skills() / "codex-skill").mkdir(parents=True)
    (paths.agents_skills() / ".system").mkdir()
    codex.record_path().parent.mkdir(parents=True, exist_ok=True)
    codex.record_path().write_text(json.dumps({"tables": {"serena": "x"}, "keys": {}}))
    lines = codex.drift()
    assert any('"only-claude" only in Claude Code' in l for l in lines)
    assert any('"only-codex" only in Codex' in l for l in lines)
    assert any('"claude-skill" only in Claude Code' in l for l in lines)
    assert any('"codex-skill" only in Codex' in l for l in lines)
    assert not any('"both"' in l or "serena" in l or ".system" in l for l in lines)


def test_drift_ignores_personal_layer_and_left_items(fake_home, fake_runner):
    paths.claude_json().write_text(json.dumps({"mcpServers": {"mine": {}, "left": {}}}), encoding="utf-8")
    (paths.personal_root()).mkdir(parents=True)
    (paths.personal_root() / "mcp.json").write_text(json.dumps({"mcpServers": {"mine": {"command": "x"}}}))
    paths.state_dir().mkdir(parents=True, exist_ok=True)
    (paths.state_dir() / "own-decisions.json").write_text(json.dumps({"mcp:left": "leave"}))
    _codex_mcp(fake_runner, [])
    assert codex.drift() == []


def test_drift_without_codex_answer_is_empty(fake_home, fake_runner):
    fake_runner.responses[("codex", "mcp", "list")] = runner.Result(1, "", "boom")
    paths.claude_json().write_text(json.dumps({"mcpServers": {"x": {}}}), encoding="utf-8")
    assert codex.drift() == []
