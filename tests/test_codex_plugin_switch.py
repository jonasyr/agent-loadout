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


def test_turning_it_back_on_by_hand_with_exactly_enabled_true_stays_yours(fake_home, fake_runner, monkeypatch):
    _setup(fake_runner, monkeypatch, {"x@m": False}, ["x@m"])
    _apply()
    path = paths.codex_home() / "config.toml"
    path.write_text(_config().replace("enabled = false", "enabled = true"), encoding="utf-8")  # your edit
    for _ in range(2):  # released once, never taken over again
        lines = _apply()
        assert "enabled = true" in _config() and "enabled = false" not in _config()
    assert any("your value" in line for line in lines)
    assert 'plugins."x@m".enabled' not in codex.read_record()["keys"]


def test_a_plugin_you_installed_yourself_is_untouched(fake_home, fake_runner, monkeypatch):
    _setup(fake_runner, monkeypatch, {"x@m": False}, ["x@m", "mine@else"])
    _apply()
    assert "mine@else" not in _config()


def test_codex_s_own_install_line_is_taken_over_and_switched_off(fake_home, fake_runner, monkeypatch):
    """`codex plugin add` writes [plugins."ID"] enabled = true itself: that default is not your choice."""
    path = paths.codex_home() / "config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('[plugins."x@m"]\nenabled = true\n', encoding="utf-8")
    _setup(fake_runner, monkeypatch, {"x@m": False}, ["x@m"])
    lines = _apply()
    assert "enabled = false" in _config() and not any("your value" in line for line in lines)
    assert 'plugins."x@m".enabled' in codex.read_record()["keys"]


def test_every_switch_change_is_in_a_backup(fake_home, fake_runner, monkeypatch):
    _setup(fake_runner, monkeypatch, {"x@m": True}, ["x@m"])
    _apply()  # loadout's first write: effort and notifications
    path = paths.codex_home() / "config.toml"
    path.write_text(_config() + '\n[plugins."x@m"]\nenabled = true\n', encoding="utf-8")  # codex plugin add
    _setup(fake_runner, monkeypatch, {"x@m": False}, ["x@m"])
    bk = backup.Backup(description="switch off")
    codex.apply_config(bk)
    assert "enabled = false" in _config()
    assert any("restore-file" in s["undo"] for s in bk.steps), "switching a plugin off is undoable on its own"


def test_switching_on_again_does_not_recreate_a_removed_plugin_s_table(fake_home, fake_runner, monkeypatch):
    _setup(fake_runner, monkeypatch, {"x@m": False}, ["x@m"])
    _apply()
    path = paths.codex_home() / "config.toml"
    path.write_text(_config().replace('[plugins."x@m"]\nenabled = false\n', ""), encoding="utf-8")  # removed
    _setup(fake_runner, monkeypatch, {"x@m": True}, [])
    _apply()
    assert "x@m" not in _config()
