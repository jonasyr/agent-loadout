"""adopt: record globally, leave or remove a Codex-only server or skill."""
import json
import sys

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


def test_a_server_codex_could_not_take_back_is_not_recorded_or_removed(codex_on, fake_runner):
    v = _mcp({"type": "stdio", "command": "m", "env": {"API_KEY": "sk" + "-abcdefghijklmnopqrstuvwxyz0123456789"}})
    rec = own.record_global(v, backup.Backup(description="t"))
    assert not rec.ok and "API_KEY" in rec.lines[0]
    assert not (paths.personal_root() / "mcp.json").exists()
    assert not any(c[:3] == ["codex", "mcp", "remove"] for c in fake_runner.calls)


def test_restore_after_record_global_gives_the_server_back_to_the_user(fake_home, fake_runner, monkeypatch):
    from loadout import settings_merge
    monkeypatch.setattr(targets, "codex_enabled", lambda: True)
    monkeypatch.setattr(targets, "claude_enabled", lambda: False)
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: {"enabledPlugins": {}})
    cfg = paths.codex_home() / "config.toml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text('[mcp_servers.mine]\ncommand = "m"\n')
    codex.apply_config(backup.Backup(description="first"))  # loadout already manages other entries

    def fake_remove(cmd, cwd=None, timeout=300, env=None):
        if cmd[:3] == ["codex", "mcp", "remove"]:
            cfg.write_text(cfg.read_text().replace('[mcp_servers.mine]\ncommand = "m"\n', ""))
        return runner.Result(0, "", "")
    monkeypatch.setattr(runner, "run", fake_remove)
    bk = backup.Backup(description="adopt")
    rec = own.record_global(_mcp({"type": "stdio", "command": "m"}), bk)
    rec.machine()
    assert "mine" in json.loads(codex.record_path().read_text())["tables"]
    backup.restore(bk.root)
    (paths.personal_root() / "mcp.json").unlink(missing_ok=True)
    codex.apply_config(backup.Backup(description="sync"))
    assert '[mcp_servers.mine]\ncommand = "m"' in cfg.read_text()


def test_leave_silences_codex_items_in_drift(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(targets, "claude_enabled", lambda: True)
    fake_runner.responses[("codex", "mcp", "list")] = runner.Result(0, json.dumps([{"name": "solo"}]), "")
    monkeypatch.setattr(codex, "_plugin_servers", lambda: set())
    own.remember_leave(Item("mcp", "solo", "", codex.CONFIG_LOCATION, {}))
    assert codex.drift() == []


def test_update_never_removes_codex_servers_as_duplicates(fake_home, fake_runner, monkeypatch):
    from loadout import duplicates, inventory, maintenance
    item = Item("mcp", "codebase-memory-mcp", "codebase-memory-mcp", codex.CONFIG_LOCATION, {"config": {"command": "c"}})
    monkeypatch.setattr(inventory, "collect", lambda with_versions=False: [item])
    monkeypatch.setattr(duplicates, "plugin_enabled", lambda: True)
    monkeypatch.setattr(duplicates, "is_duplicate_mcp", lambda i: True)
    monkeypatch.setattr(duplicates, "would_refuse_undo", lambda i: False)
    removed, _ = maintenance.undo_reregistered(backup.Backup(description="t"))
    assert removed == []
    assert not any(c[:3] == ["codex", "mcp", "remove"] for c in fake_runner.calls)


def test_codex_mcp_remove_runs_from_home(fake_home, fake_runner):
    codex.remove_server("mine", backup.Backup(description="t"))
    i = next(i for i, c in enumerate(fake_runner.calls) if c[:3] == ["codex", "mcp", "remove"])
    assert fake_runner.cwds[i] == str(paths.home())


def test_a_failed_codex_handoff_is_reported_as_not_done(codex_on, fake_runner, monkeypatch):
    fake_runner.responses[("codex", "mcp", "remove")] = runner.Result(1, "", "boom")
    monkeypatch.setattr(codex, "desired_tables", lambda: ({"mine": "x"}, []))
    rec = own.record_global(_mcp({"type": "stdio", "command": "m"}), backup.Backup(description="t"))
    with pytest.raises(OSError, match="codex mcp remove mine"):
        rec.machine()


def test_codex_only_adoption_leaves_claude_code_alone(codex_on, fake_runner, monkeypatch):
    from loadout import link, settings_merge
    touched = []
    monkeypatch.setattr(link, "link_all", lambda bk, **k: touched.append("link") or [])
    monkeypatch.setattr(settings_merge, "apply_settings", lambda *a, **k: touched.append("settings"))
    monkeypatch.setattr(codex, "desired_tables", lambda: ({"mine": "x"}, []))
    adopt.apply_own([(_mcp({"type": "stdio", "command": "m"}), own.Choice("global"))], backup.Backup(description="t"))
    assert touched == []
    assert ["codex", "mcp", "remove", "mine"] in fake_runner.calls


def test_failed_handoff_hint_names_a_command_that_reapplies(codex_on, fake_runner, monkeypatch):
    fake_runner.responses[("codex", "mcp", "remove")] = runner.Result(1, "", "boom")
    monkeypatch.setattr(codex, "desired_tables", lambda: ({"mine": "x"}, []))
    rec = own.record_global(_mcp({"type": "stdio", "command": "m"}), backup.Backup(description="t"))
    with pytest.raises(OSError, match="loadout bootstrap"):
        rec.machine()




def test_adopt_backs_up_the_record_as_it_is_after_it_takes_the_lock(codex_on, fake_runner, monkeypatch):
    """Another run holds the Codex lock and changes the record meanwhile: adopt's copy is of that newer record, so
    restoring adopt's backup keeps the other run's entry."""
    from loadout import locks
    record = codex.record_path()
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps({"keys": {"old": "1"}}))
    bk = backup.Backup(description="t")
    rec = own.record_global(_mcp({"type": "stdio", "command": "m"}), bk)
    holder = codex._lock(0, "other")
    assert holder is not None

    def other_run_finishes(_s):
        record.write_text(json.dumps({"keys": {"old": "1", "theirs": "2"}}))
        holder.release()
    monkeypatch.setattr(locks, "_sleep", other_run_finishes)
    monkeypatch.setattr(locks, "foreground_wait", lambda: 5)
    rec.machine()
    copies = [s for s in bk.steps if "codex-config.json" in s.get("label", "")]
    assert len(copies) == 1
    saved = copies[0]["undo"]["restore-file"][0]
    assert "theirs" in open(saved).read()
