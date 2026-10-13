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


def _install_with_codex(fake_runner, monkeypatch, pid):
    """loadout installs pid itself; like the real `codex plugin add`, the fake writes enabled = true."""
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: {
        "enabledPlugins": {pid: True},
        "extraKnownMarketplaces": {"m": {"source": {"source": "github", "repo": "o/m"}}}})
    fake_runner.responses[("codex", "plugin", "marketplace", "add")] = runner.Result(
        0, json.dumps({"marketplaceName": "m", "alreadyAdded": True}), "")
    fake_runner.responses[("codex", "plugin", "list")] = runner.Result(
        0, json.dumps({"installed": [], "available": []}), "")

    def run(cmd, cwd=None, timeout=300, env=None):
        if cmd[:4] == ["codex", "plugin", "add", pid]:
            path = paths.codex_home() / "config.toml"
            path.parent.mkdir(parents=True, exist_ok=True)
            text = path.read_text(encoding="utf-8") if path.exists() else ""
            table = f'[plugins."{pid}"]'
            if table in text:
                text = text.replace(f"{table}\nenabled = false", f"{table}\nenabled = true")
            else:
                text += f"\n{table}\nenabled = true\n"
            path.write_text(text, encoding="utf-8")
        return fake_runner(cmd, cwd=cwd, timeout=timeout, env=env)
    monkeypatch.setattr(runner, "run", run)
    codex.apply_plugins(backup.Backup(description="install"))
    monkeypatch.setattr(runner, "run", fake_runner)


def test_an_enabled_true_line_loadout_did_not_cause_stays_yours(fake_home, fake_runner, monkeypatch):
    """Nothing proves `codex plugin add` wrote it rather than you: without that proof the line is yours."""
    path = paths.codex_home() / "config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('[plugins."x@m"]\nenabled = true\n', encoding="utf-8")
    _setup(fake_runner, monkeypatch, {"x@m": False}, ["x@m"])
    lines = _apply()
    assert "enabled = true" in _config() and "enabled = false" not in _config()
    assert any("your value" in line for line in lines)


def test_the_line_loadout_s_own_install_wrote_is_switched_off_later(fake_home, fake_runner, monkeypatch):
    _install_with_codex(fake_runner, monkeypatch, "x@m")
    _setup(fake_runner, monkeypatch, {"x@m": False}, ["x@m"])
    lines = _apply()
    assert "enabled = false" in _config() and not any("your value" in line for line in lines)
    assert 'plugins."x@m".enabled' in codex.read_record()["keys"]


def test_a_reinstall_by_loadout_after_an_uninstall_is_loadout_s_line_again(fake_home, fake_runner, monkeypatch):
    _install_with_codex(fake_runner, monkeypatch, "x@m")
    _setup(fake_runner, monkeypatch, {"x@m": False}, ["x@m"])
    _apply()  # owned enabled = false
    _install_with_codex(fake_runner, monkeypatch, "x@m")  # uninstalled meanwhile, switched on, loadout reinstalls
    _setup(fake_runner, monkeypatch, {"x@m": False}, ["x@m"])
    lines = _apply()
    assert "enabled = false" in _config() and not any("your value" in line for line in lines)


def test_the_install_record_expires_once_the_plugin_is_seen_uninstalled(fake_home, fake_runner, monkeypatch):
    _install_with_codex(fake_runner, monkeypatch, "x@m")
    path = paths.codex_home() / "config.toml"
    path.write_text(_config().replace('[plugins."x@m"]\nenabled = true\n', ""), encoding="utf-8")  # you uninstall
    _setup(fake_runner, monkeypatch, {"x@m": True}, [])
    _apply()  # a run sees it gone
    path.write_text(_config() + '\n[plugins."x@m"]\nenabled = true\n', encoding="utf-8")  # you reinstall it
    _setup(fake_runner, monkeypatch, {"x@m": False}, ["x@m"])
    lines = _apply()
    assert "enabled = true" in _config() and "enabled = false" not in _config()
    assert any("your value" in line for line in lines)


def test_the_install_record_does_not_hide_loadout_s_first_change_backup(fake_home, fake_runner, monkeypatch):
    path = paths.codex_home() / "config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# mine\n", encoding="utf-8")
    _install_with_codex(fake_runner, monkeypatch, "x@m")
    _setup(fake_runner, monkeypatch, {"x@m": True}, ["x@m"])
    bk = backup.Backup(description="first")
    codex.apply_config(bk)
    assert any("restore-file" in s["undo"] for s in bk.steps)


def test_every_switch_change_is_in_a_backup(fake_home, fake_runner, monkeypatch):
    _install_with_codex(fake_runner, monkeypatch, "x@m")
    _setup(fake_runner, monkeypatch, {"x@m": True}, ["x@m"])
    _apply()  # loadout's first write: effort and notifications
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
