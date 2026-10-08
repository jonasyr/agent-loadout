import json

from loadout import backup, check, link, paths, settings_merge


def _setup_ok(fake_home):
    (paths.personal_root() / "rules").mkdir(parents=True)
    link.link_all(backup.Backup())
    settings_merge.apply_settings()
    installed = {pid: [{"scope": "user"}] for pid, on in settings_merge.desired_settings()["enabledPlugins"].items() if on}
    p = fake_home / ".claude/plugins/installed_plugins.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"version": 2, "plugins": installed}))


def _by(results):
    return {r.name: r for r in results}


def test_check_passes_on_good_setup(fake_home, fake_runner):
    _setup_ok(fake_home)
    text, code = check.format_results(check.run_checks())
    assert code == 0, text


def test_check_reports_drift_with_personal_hint(fake_home, fake_runner):
    _setup_ok(fake_home)
    s = fake_home / ".claude/settings.json"
    data = json.loads(s.read_text())
    data["enabledPlugins"]["superpowers@claude-plugins-official"] = False
    s.write_text(json.dumps(data))
    r = _by(check.run_checks())["settings drift"]
    assert not r.ok
    assert "superpowers" in r.detail
    assert "personal" in r.fix


def test_check_missing_link_and_binary(fake_home, fake_runner):
    fake_runner.missing.add("serena")
    results = _by(check.run_checks())
    assert not results["link rules/loadout"].ok
    assert not results["binary serena"].ok
    assert results["binary serena"].severity == "error"
    text, code = check.format_results(list(results.values()))
    assert code == 1
    assert "loadout bootstrap" in text


def test_check_invalid_settings_json(fake_home, fake_runner):
    s = fake_home / ".claude/settings.json"
    s.parent.mkdir(parents=True)
    s.write_text("{ nope")
    r = _by(check.run_checks())["settings.json"]
    assert not r.ok and "invalid JSON" in r.detail
