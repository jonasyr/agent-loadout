"""Profile plugins stay project-only in Codex: loadout keeps their user-level entry switched off."""
import json
import sys

import pytest

from loadout import backup, codex, paths, runner, settings_merge



def _settings(monkeypatch, enabled=None):
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: {"enabledPlugins": enabled or {}})


def test_project_plugin_is_switched_off_at_user_level(fake_home, fake_runner, monkeypatch):
    _settings(monkeypatch)
    cfg = paths.codex_home() / "config.toml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text('[plugins."deepeval@claude-plugins-official"]\nenabled = true\n')
    codex.add_project_plugin("deepeval@claude-plugins-official")
    codex.apply_config(backup.Backup(description="t"))
    text = cfg.read_text()
    assert '[plugins."deepeval@claude-plugins-official"]\nenabled = false' in text
    assert text.count("deepeval") == 1


def test_codex_plugin_add_turning_it_back_on_is_undone(fake_home, fake_runner, monkeypatch):
    _settings(monkeypatch)
    codex.add_project_plugin("deepeval@claude-plugins-official")
    bk = backup.Backup(description="t")
    codex.apply_config(bk)
    cfg = paths.codex_home() / "config.toml"
    cfg.write_text(cfg.read_text().replace("enabled = false", "enabled = true"))  # what `codex plugin add` does
    lines = codex.apply_config(bk)
    assert "enabled = false" in cfg.read_text()
    assert not any("your value" in l for l in lines)


def test_a_project_plugin_enabled_globally_is_switched_on(fake_home, fake_runner, monkeypatch):
    codex.add_project_plugin("deepeval@claude-plugins-official")
    _settings(monkeypatch)
    codex.apply_config(backup.Backup(description="t"))
    _settings(monkeypatch, {"deepeval@claude-plugins-official": True})
    codex.apply_config(backup.Backup(description="t"))
    assert '[plugins."deepeval@claude-plugins-official"]\nenabled = true' in (paths.codex_home() / "config.toml").read_text()


def test_existing_key_records_keep_working(fake_home, fake_runner, monkeypatch):
    _settings(monkeypatch)
    codex.apply_config(backup.Backup(description="t"))
    keys = json.loads(codex.record_path().read_text())["keys"]
    assert "model_reasoning_effort" in keys and "tui.notifications" in keys


def test_add_project_plugin_is_idempotent(fake_home):
    codex.add_project_plugin("a@m")
    codex.add_project_plugin("a@m")
    assert codex.project_plugins() == ["a@m"]


def test_mcp_list_runs_from_home_so_repo_servers_do_not_count(fake_home, fake_runner):
    fake_runner.responses[("codex", "mcp", "list")] = runner.Result(0, "[]", "")
    codex.mcp_names()
    i = next(i for i, c in enumerate(fake_runner.calls) if c[:3] == ["codex", "mcp", "list"])
    assert fake_runner.cwds[i] == str(paths.home())


def test_first_change_backup_still_happens_after_a_project_plugin_was_recorded(fake_home, fake_runner, monkeypatch):
    _settings(monkeypatch)
    cfg = paths.codex_home() / "config.toml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text('model = "x"\n')
    codex.add_project_plugin("deepeval@claude-plugins-official")
    bk = backup.Backup(description="t")
    codex.apply_config(bk)
    assert any("before loadout's first change" in s["label"] for s in bk.steps)


def test_a_broken_key_record_is_ignored(fake_home, fake_runner, monkeypatch):
    _settings(monkeypatch)
    codex.record_path().parent.mkdir(parents=True, exist_ok=True)
    codex.record_path().write_text(json.dumps({"tables": {}, "keys": {"not a [key": "x = 1"}}))
    codex.apply_config(backup.Backup(description="t"))  # does not raise
