"""apply.rtk_step runs wherever cbm_step runs (bootstrap, update, configure, the daily sync), also Codex only."""
from loadout import apply, backup, bootstrap, codex, maintenance as m, rtk_config, update
from loadout.apply import StepResult

from test_rtk_config import LINE, _cfg, _put, _wanted
from test_update_plan import _plan_world
from test_update_run import _world


def test_rtk_step_is_empty_when_nothing_to_do(fake_home, fake_runner, monkeypatch):
    _wanted(monkeypatch, fake_runner, on=False)
    res = apply.rtk_step(backup.Backup(description="t"))
    assert isinstance(res, StepResult) and res.name == "rtk" and not res.lines and not res.summary


def test_rtk_step_writes_and_dry_run_does_not(fake_home, fake_runner, monkeypatch):
    _wanted(monkeypatch, fake_runner)
    dry = apply.rtk_step(object(), dry=True)
    assert dry.lines and not _cfg(fake_home).exists()
    res = apply.rtk_step(backup.Backup(description="t"))
    assert res.lines and LINE in _cfg(fake_home).read_text()


def test_update_plan_names_rtk_part(fake_home, fake_runner, monkeypatch):
    _plan_world(monkeypatch)
    _wanted(monkeypatch, fake_runner)
    first = update.build_plan(True, False)[0].label
    assert "rtk (config)" in first
    _put(fake_home, f"[hooks]\n{LINE}\n")
    assert "rtk (config)" not in update.build_plan(True, False)[0].label


def test_update_reapply_writes_rtk_config(fake_home, fake_runner, monkeypatch, capsys):
    _world(monkeypatch)
    _wanted(monkeypatch, fake_runner)
    assert update.run(True, lambda q: "", argv=["--yes"]) == 0
    assert LINE in _cfg(fake_home).read_text()


def test_codex_only_update_removes_key(fake_home, fake_runner, monkeypatch):
    _world(monkeypatch, claude=True)
    _wanted(monkeypatch, fake_runner)
    rtk_config.apply(backup.Backup(description="t"))
    assert LINE in _cfg(fake_home).read_text()
    _world(monkeypatch, claude=False, codex_on=True)
    _wanted(monkeypatch, fake_runner, on=False)
    assert update.run(True, lambda q: "", argv=["--yes"]) == 0
    assert not _cfg(fake_home).exists()


def test_daily_sync_runs_rtk_step(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(m, "pull_if_clean", lambda root: True)
    monkeypatch.setattr(m, "find_outdated", lambda: [])
    monkeypatch.setattr(m, "apply_settings", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(codex, "enabled", lambda: False)
    _wanted(monkeypatch, fake_runner)
    notes = []
    monkeypatch.setattr(m, "notify", notes.append)
    m.maintain(100.0)
    assert LINE in _cfg(fake_home).read_text()
    assert any("rtk config.toml" in n for n in notes)
    assert any("rtk config" in n and "loadout restore" in n for n in notes)


def test_bootstrap_runs_rtk_step(fake_home, fake_runner, monkeypatch):
    (fake_home / ".config/loadout/personal").mkdir(parents=True)
    _wanted(monkeypatch, fake_runner)
    bootstrap.bootstrap(install=False, yes=True, plugins=False, adopt_step=False, ask=lambda q: "", interactive=False)
    assert LINE in _cfg(fake_home).read_text()


def test_daily_sync_is_silent_when_only_the_record_changed(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(m, "pull_if_clean", lambda root: True)
    monkeypatch.setattr(m, "find_outdated", lambda: [])
    monkeypatch.setattr(m, "apply_settings", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(codex, "enabled", lambda: False)
    _wanted(monkeypatch, fake_runner, on=False)
    rtk_config.record_path().parent.mkdir(parents=True, exist_ok=True)
    rtk_config.record_path().write_text('{"line": "suppress_hook_warning = true", "created": true}\n')
    notes = []
    monkeypatch.setattr(m, "notify", notes.append)
    m.maintain(100.0)
    assert not any("rtk config" in n for n in notes), notes


def test_configure_apply_all_writes_rtk_config(fake_home, fake_runner, monkeypatch, capsys):
    from loadout import configure, paths
    paths.personal_root().mkdir(parents=True)
    _wanted(monkeypatch, fake_runner)
    configure.apply_all(lambda q: "n")
    assert LINE in _cfg(fake_home).read_text()
    out = capsys.readouterr().out
    assert "rtk config.toml" in out and "loadout restore" in out


def test_update_configures_rtk_installed_in_the_same_run(fake_home, fake_runner, monkeypatch):
    """rtk missing at first, its install item chosen: the config line is written after the install, not a run later."""
    _world(monkeypatch)
    _wanted(monkeypatch, fake_runner)
    fake_runner.missing = {"rtk"}
    monkeypatch.setattr(bootstrap, "missing_tools", lambda: [({"id": "rtk"}, [["install-rtk"]], False)])

    def installed(item, summary, failed):
        fake_runner.missing = set()
        summary.changed.append("rtk: installed")
        summary.upgraded.append("rtk")
    monkeypatch.setattr(update, "_install_tool", installed)
    assert update.run(True, lambda q: "", argv=["--yes"]) == 0
    assert LINE in _cfg(fake_home).read_text()
