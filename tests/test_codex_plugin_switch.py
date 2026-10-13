"""A plugin switched off for Claude Code is switched off in Codex too (owned `enabled` key)."""
import json

from loadout import backup, codex, paths, runner, settings_merge


def _setup(fake_runner, monkeypatch, enabled, installed):
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: {"enabledPlugins": enabled})
    fake_runner.responses[("codex", "plugin", "list")] = runner.Result(
        0, json.dumps({"installed": [{"pluginId": p} for p in installed], "available": []}), "")


def _config():
    p = paths.codex_home() / "config.toml"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _apply():
    return codex.apply_config(backup.Backup(description="t"))


def test_switched_off_and_installed_is_switched_off_in_codex(fake_home, fake_runner, monkeypatch):
    _setup(fake_runner, monkeypatch, {"x@m": False}, ["x@m"])
    _apply()
    assert '[plugins."x@m"]' in _config() and "enabled = false" in _config()
    assert 'plugins."x@m".enabled' in codex.read_record()["keys"]


def test_switched_on_again_the_owned_line_reads_true(fake_home, fake_runner, monkeypatch):
    _setup(fake_runner, monkeypatch, {"x@m": False}, ["x@m"])
    _apply()
    _setup(fake_runner, monkeypatch, {"x@m": True}, ["x@m"])
    _apply()
    assert "enabled = true" in _config() and "enabled = false" not in _config()


def test_your_own_edit_of_the_line_is_left_alone(fake_home, fake_runner, monkeypatch):
    _setup(fake_runner, monkeypatch, {"x@m": False}, ["x@m"])
    _apply()
    path = paths.codex_home() / "config.toml"
    path.write_text(_config().replace("enabled = false", "enabled = true # mine"), encoding="utf-8")
    lines = _apply()
    assert "enabled = true # mine" in _config()
    assert any("your value" in line for line in lines)


def test_not_installed_or_unknown_list_writes_nothing(fake_home, fake_runner, monkeypatch):
    _setup(fake_runner, monkeypatch, {"x@m": False}, [])
    _apply()
    assert "plugins" not in _config()
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: {"enabledPlugins": {"x@m": False}})
    fake_runner.responses[("codex", "plugin", "list")] = runner.Result(1, "", "boom")
    _apply()
    assert "plugins" not in _config()


def test_a_plugin_you_installed_yourself_is_untouched(fake_home, fake_runner, monkeypatch):
    _setup(fake_runner, monkeypatch, {"x@m": False}, ["x@m", "mine@else"])
    _apply()
    assert "mine@else" not in _config()
