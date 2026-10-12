"""adopt: record globally, leave or remove a Codex-only server or skill."""
import json

import pytest

from loadout import adopt, backup, codex, own, paths, runner, targets
from loadout.inventory import Item, Verdict
from loadout.jsonio import load_json


@pytest.fixture
def codex_on(fake_home, monkeypatch):
    monkeypatch.setattr(targets, "codex_enabled", lambda: True)
    monkeypatch.setattr(targets, "claude_enabled", lambda: False)
    monkeypatch.setattr(codex, "apply_config", lambda bk, dry_run=False: [])
    monkeypatch.setattr(codex, "apply_skills", lambda bk: [])
    cfg = paths.codex_home() / "config.toml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text('[mcp_servers.mine]\ncommand = "m"\n')


def _mcp(cfg=None, problem=""):
    return Verdict(Item("mcp", "mine", "m", codex.CONFIG_LOCATION, {"config": cfg, "problem": problem}), "own", "")


def test_record_global_writes_personal_mcp_and_hands_the_table_to_loadout(codex_on, fake_runner):
    bk = backup.Backup(description="t")
    rec = own.record_global(_mcp({"type": "stdio", "command": "m"}), bk)
    assert load_json(paths.personal_root() / "mcp.json")["mcpServers"]["mine"] == {"type": "stdio", "command": "m"}
    rec.machine()
    assert ["codex", "mcp", "remove", "mine"] in fake_runner.calls
    assert any("config.toml" in s.get("label", "") for s in bk.steps)  # saved before the removal


def test_record_global_refuses_with_the_reason(codex_on):
    rec = own.record_global(_mcp(None, "mcp mine: startup_timeout_sec has no Claude Code equivalent"),
                            backup.Backup(description="t"))
    assert not rec.ok and "startup_timeout_sec" in rec.lines[0]
    assert not (paths.personal_root() / "mcp.json").exists()


def test_remove_saves_config_then_runs_codex_mcp_remove(codex_on, fake_runner):
    bk = backup.Backup(description="t")
    v = _mcp({"type": "stdio", "command": "m"})
    v.action = "remove"
    out = adopt.apply([v], bk, confirm_cmds=False)
    assert ["codex", "mcp", "remove", "mine"] in fake_runner.calls
    assert any("mine" in l for l in out)


def test_failed_removal_is_reported(codex_on, fake_runner):
    fake_runner.responses[("codex", "mcp", "remove")] = runner.Result(1, "", "boom")
    assert "failed" in codex.remove_server("mine", backup.Backup(description="t"))


def test_record_global_skill_copies_and_relinks(codex_on):
    src = paths.agents_skills() / "solo"
    src.mkdir(parents=True)
    (src / "SKILL.md").write_text("---\nname: solo\ndescription: d\n---\n")
    v = Verdict(Item("skill", "solo", str(src), str(src), {}), "own", "")
    rec = own.record_global(v, backup.Backup(description="t"))
    assert (paths.personal_root() / "skills" / "solo" / "SKILL.md").exists()
    lines = rec.machine()
    assert not src.exists() or src.is_symlink()
    assert any("~/.agents/skills/solo" in l for l in lines)


def test_drift_points_codex_only_items_to_adopt(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(targets, "claude_enabled", lambda: True)
    fake_runner.responses[("codex", "mcp", "list")] = runner.Result(0, json.dumps([{"name": "solo"}]), "")
    monkeypatch.setattr(codex, "_plugin_servers", lambda: set())
    lines = codex.drift()
    assert lines == ['MCP server "solo" only in Codex (record it with loadout adopt, then both get it)']
