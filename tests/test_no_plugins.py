"""bootstrap --no-plugins leaves out the check rows that only say plugins are missing (spec 2026-10-29 tour
leftovers G1): not shown, not counted, no exit 1, no to-do item; one info line instead. Nothing is remembered."""
import json

from loadout import bootstrap, check, codex, out, runner
from loadout.check import CheckResult as R


def P(name, sev="error"):
    return R(name, False, "missing", "loadout update (retries them)", sev, plugins_missing=True)


def _bootstrap(fake_home, monkeypatch, rows, plugins=False):
    monkeypatch.setattr(out, "VERBOSE", False)
    (fake_home / ".config/loadout/personal").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(check, "run_checks", lambda **k: rows)
    return bootstrap.bootstrap(install=False, yes=True, plugins=plugins, adopt_step=False, ask=lambda q: "",
                               interactive=False)


def test_hidden_rows_do_not_fail_or_count(fake_home, fake_runner, monkeypatch, capsys):
    code = _bootstrap(fake_home, monkeypatch, [R("python", True), P("Codex plugin"), P("Codex plugins missing", "warn")])
    text = capsys.readouterr().out
    assert code == 0
    assert "1 of 1 OK" in text and text.count(bootstrap.PLUGINS_SKIPPED) == 1
    assert "Codex plugin" not in text


def test_other_fail_still_fails(fake_home, fake_runner, monkeypatch, capsys):
    code = _bootstrap(fake_home, monkeypatch, [P("Codex plugin"),
                                               R("binary rtk", False, "not on PATH", "loadout bootstrap --install")])
    text = capsys.readouterr().out
    assert code == 1 and "binary rtk: loadout bootstrap --install" in text[text.index("Still to do"):]
    assert bootstrap.PLUGINS_SKIPPED in text


def test_no_line_when_nothing_hidden(fake_home, fake_runner, monkeypatch, capsys):
    _bootstrap(fake_home, monkeypatch, [R("python", True)])
    assert bootstrap.PLUGINS_SKIPPED not in capsys.readouterr().out


def test_with_plugins_rows_unchanged(fake_home, fake_runner, monkeypatch, capsys):
    code = _bootstrap(fake_home, monkeypatch, [R("python", True), P("Codex plugin")], plugins=True)
    text = capsys.readouterr().out
    assert code == 1 and "Codex plugin" in text and bootstrap.PLUGINS_SKIPPED not in text


def _codex_on(monkeypatch, settings):
    from loadout import settings_merge
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: settings)
    for name, value in (("enabled", lambda: True), ("unavailable", lambda *a, **k: None),
                        ("hooks_status", lambda remember=False: "trusted"), ("logins_needed", lambda: []),
                        ("logins_optional", lambda: []), ("drift", lambda: [])):
        monkeypatch.setattr(codex, name, value)


def test_open_steps_leave_out_missing_plugins(fake_home, fake_runner, monkeypatch):
    _codex_on(monkeypatch, {})
    monkeypatch.setattr(codex, "missing_routes", lambda *a, **k: (["x/y"], []))
    assert any("loadout update" in s for s in codex.open_steps())
    assert not any("loadout update" in s for s in codex.open_steps(plugins=False))


IMPECCABLE = {"enabledPlugins": {"impeccable@impeccable": True},
              "extraKnownMarketplaces": {"impeccable": {"source": {"source": "github", "repo": "pbakaus/impeccable"}}}}


def _claude_plugins(fake_home, monkeypatch, settings):
    from loadout import settings_merge
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: settings)
    d = fake_home / ".claude/plugins"
    d.mkdir(parents=True, exist_ok=True)
    (d / "installed_plugins.json").write_text(json.dumps({"plugins": {}}))
    (d / "known_marketplaces.json").write_text("{}")


def test_undeclared_marketplace_row_stays(fake_home, fake_runner, monkeypatch):
    _claude_plugins(fake_home, monkeypatch, {"enabledPlugins": {"x@nowhere": True}})
    (row,) = check._plugins()
    assert not row.ok and not row.plugins_missing


def test_rows_are_marked(fake_home, fake_runner, monkeypatch):
    _claude_plugins(fake_home, monkeypatch, IMPECCABLE)
    (row,) = check._plugins()
    assert not row.ok and row.plugins_missing
    _codex_on(monkeypatch, IMPECCABLE)
    fake_runner.responses[("codex", "plugin", "marketplace", "list")] = runner.Result(0, json.dumps({"marketplaces": []}), "")
    fake_runner.responses[("codex", "plugin", "list")] = runner.Result(0, json.dumps({"installed": [], "available": []}), "")
    rows = {r.name: r for r in codex.checks()}
    assert rows["Codex plugin"].plugins_missing and rows["Codex plugins missing"].plugins_missing


def test_too_old_codex_row_stays(fake_home, fake_runner, monkeypatch):
    _codex_on(monkeypatch, IMPECCABLE)
    monkeypatch.setattr(codex, "installed_plugins", lambda: None)
    monkeypatch.setattr(codex, "no_plugin_command", lambda: True)
    (row,) = [r for r in codex.checks() if r.name == "Codex plugin"]
    assert not row.ok and not row.plugins_missing


def test_failed_codex_listing_is_not_hidden(fake_home, fake_runner, monkeypatch):
    # review: a listing that times out or does not parse is Codex failing to answer, not a skipped plugin
    _codex_on(monkeypatch, IMPECCABLE)
    monkeypatch.setattr(codex, "installed_plugins", lambda: None)
    monkeypatch.setattr(codex, "no_plugin_command", lambda: False)
    (row,) = [r for r in codex.checks() if r.name == "Codex plugin"]
    assert not row.ok and not row.plugins_missing
