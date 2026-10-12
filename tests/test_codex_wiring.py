"""Codex in bootstrap, the daily sync and the health check; nothing changes for Claude-only users."""
import json

from loadout import bootstrap, check, codex, maintenance, out, paths, runner


def _run(**kw):
    args = dict(install=False, yes=True, plugins=False, adopt_step=False, ask=lambda q: "", interactive=False)
    args.update(kw)
    return bootstrap.bootstrap(**args)


def _personal(fake_home):
    (fake_home / ".config/loadout/personal").mkdir(parents=True)


def test_bootstrap_without_codex_is_unchanged(fake_home, fake_runner, capsys):
    _personal(fake_home)
    fake_runner.missing.add("codex")
    _run()
    text = capsys.readouterr().out
    assert "Codex" not in text and not any(c[0] == "codex" for c in fake_runner.calls)


def test_bootstrap_sets_up_codex_and_lists_the_hooks_step(fake_home, fake_runner, monkeypatch, capsys):
    _personal(fake_home)
    codex.set_enabled(True)
    monkeypatch.setattr(codex, "unavailable", lambda: None)
    monkeypatch.setattr(codex, "apply_all", lambda bk, refresh=False, **kw: ["instructions written"])
    monkeypatch.setattr(out, "VERBOSE", False)
    _run()
    text = capsys.readouterr().out
    assert any(line.lstrip("✓! ").startswith("Codex") for line in text.splitlines())
    assert codex.HOOKS_TODO in text


def test_apply_all_runs_every_part(fake_home, fake_runner, monkeypatch):
    calls = []
    for name in ("apply_instructions", "apply_config", "apply_skills", "apply_plugins"):
        monkeypatch.setattr(codex, name, lambda *a, n=name, **k: calls.append(n) or ([] if n != "apply_instructions" else "ok"))
    codex.apply_all(object())
    assert calls == ["apply_instructions", "apply_config", "apply_skills", "apply_plugins"]


def test_check_without_codex_has_no_codex_group(fake_home, fake_runner):
    assert not any(r.name.startswith("Codex") for r in check.run_checks())


def test_check_reports_codex_state(fake_home, fake_runner, monkeypatch):
    codex.set_enabled(True)
    monkeypatch.setattr(codex, "unavailable", lambda: None)
    monkeypatch.setattr(codex, "installed_plugins", lambda: set())
    monkeypatch.setattr(codex, "drift", lambda: ['MCP server "x" only in Claude Code (record it with loadout adopt, then both get it)'])
    names = {r.name: r for r in check.run_checks() if r.name.startswith("Codex")}
    assert not names["Codex plugin"].ok and "loadout bootstrap" in names["Codex plugin"].fix
    assert names["Codex drift"].severity == "warn" and "only in Claude Code" in names["Codex drift"].detail


def test_sync_reapplies_codex_after_a_pull(fake_home, fake_runner, monkeypatch):
    codex.set_enabled(True)
    monkeypatch.setattr(codex, "unavailable", lambda: None)
    seen = []
    monkeypatch.setattr(codex, "apply_all", lambda bk, refresh=False, **kw: seen.append(refresh) or ["skipped mcp x: no"])
    monkeypatch.setattr(codex, "drift", lambda: ["skill \"y\" only in Codex (…)"])
    monkeypatch.setattr(maintenance, "pull_if_clean", lambda root: True)
    monkeypatch.setattr(maintenance, "find_outdated", lambda: [])  # the weekly check would ask the network
    from loadout import link, personal_mcp, settings_merge
    monkeypatch.setattr(settings_merge, "apply_settings", lambda: (None, None))
    monkeypatch.setattr(personal_mcp, "apply_mcp", lambda: [])
    monkeypatch.setattr(link, "link_all", lambda bk, retry_symlinks=False: [])
    (paths.personal_root() / ".git").mkdir(parents=True)  # the kit is a real clone; pull_if_clean is faked for both
    maintenance._maintain(0)
    notice = (paths.state_dir() / "pending-notice").read_text(encoding="utf-8")
    assert seen == [True] and "skipped mcp x" in notice and 'skill "y" only in Codex' in notice
