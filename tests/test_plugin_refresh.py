"""loadout update refreshes loadout's plugins in both agents; the kit's marketplaces auto-update."""
import json

from loadout import bootstrap, check, maintenance, paths, runner, settings_merge, targets, update

SETTINGS = {"enabledPlugins": {"a@m": True, "b@m": True, "off@m": False, "proj@m": True, "gone@m": True}}


def _setup(fake_home, monkeypatch, claude=True, codex=False):
    targets.set_agents({"claude": claude, "codex": codex})
    from loadout import codex as codex_mod
    monkeypatch.setattr(codex_mod, "unavailable", lambda: None)  # a usable codex (fake_runner has no version)
    monkeypatch.setattr(maintenance, "find_outdated", lambda: [])
    monkeypatch.setattr(bootstrap, "missing_tools", lambda *a, **k: [])
    monkeypatch.setattr(bootstrap, "plugins_plan", lambda: ([], [], []))  # no new plugin to install here
    monkeypatch.setattr(check, "run_checks", lambda *a, **k: [])
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: SETTINGS)
    f = paths.claude_home() / "plugins" / "installed_plugins.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"plugins": {
        "a@m": [{"scope": "user"}], "b@m": [{"scope": "user"}], "off@m": [{"scope": "user"}],
        "proj@m": [{"scope": "project"}]}}))


def _run(yes):
    return update.run(yes, lambda q: "", argv=["--yes"] if yes else [])


def _updates(fake_runner):
    return [c for c in fake_runner.calls if c[:3] == ["claude", "plugin", "update"]]


def test_base_marketplaces_all_auto_update(kit_root):
    base = json.loads((kit_root / "settings.base.json").read_text())
    assert all(m.get("autoUpdate") is True for m in base["extraKnownMarketplaces"].values())
    desired = settings_merge.desired_settings()
    assert all(m.get("autoUpdate") is True for m in desired["extraKnownMarketplaces"].values())


def test_updates_enabled_user_scope_plugins_after_the_marketplace(fake_home, fake_runner, monkeypatch, capsys):
    _setup(fake_home, monkeypatch)
    fake_runner.responses[("claude", "plugin", "update", "a@m")] = runner.Result(0, "Updated a to 2.0", "")
    fake_runner.responses[("claude", "plugin", "update", "b@m")] = runner.Result(0, "b is already at the latest version", "")
    _run(True)
    first = fake_runner.calls.index(["claude", "plugin", "update", "a@m", "--scope", "user"])
    assert ["claude", "plugin", "marketplace", "update"] in fake_runner.calls[:first]  # the marketplaces first
    assert _updates(fake_runner) == [["claude", "plugin", "update", "a@m", "--scope", "user"],
                                     ["claude", "plugin", "update", "b@m", "--scope", "user"]]
    out = capsys.readouterr().out
    assert "plugin a@m: updated" in out and "plugin b@m: updated" not in out
    assert "/reload-plugins" in out


def test_no_hint_when_nothing_changed(fake_home, fake_runner, monkeypatch, capsys):
    _setup(fake_home, monkeypatch)
    fake_runner.responses[("claude", "plugin", "update")] = runner.Result(0, "already at the latest version", "")
    _run(True)
    assert "/reload-plugins" not in capsys.readouterr().out


def test_a_failing_update_is_one_line_and_the_loop_continues(fake_home, fake_runner, monkeypatch, capsys):
    _setup(fake_home, monkeypatch)
    fake_runner.responses[("claude", "plugin", "update", "a@m")] = runner.Result(1, "", "boom")
    _run(True)
    assert len(_updates(fake_runner)) == 2
    out = capsys.readouterr().out
    assert len([l for l in out.splitlines() if "a@m" in l and "failed:" in l and "boom" in l]) == 1


def test_claude_off_makes_no_claude_call(fake_home, fake_runner, monkeypatch):
    _setup(fake_home, monkeypatch, claude=False, codex=True)
    seen = []
    from loadout import codex
    monkeypatch.setattr(codex, "apply_plugins", lambda bk, refresh=False, say=None, **kw: seen.append(refresh) or [])
    _run(True)
    assert not any(c[0] == "claude" for c in fake_runner.calls)
    assert seen == [True]  # Codex is still refreshed


def test_plugins_are_not_touched_without_a_yes(fake_home, fake_runner, monkeypatch, capsys):
    _setup(fake_home, monkeypatch, codex=True)
    from loadout import codex
    seen = []
    monkeypatch.setattr(codex, "apply_plugins", lambda bk, refresh=False, say=None, **kw: seen.append(1) or [])
    _run(False)  # no terminal: the question gets an empty answer
    assert _updates(fake_runner) == [] and seen == []
    assert "--yes" in capsys.readouterr().out


def _codex_versions(fake_runner, monkeypatch, before, after):
    """`codex plugin list` answers `before` until the plugins were applied, then `after`."""
    from loadout import codex
    applied = {"done": False}
    real = fake_runner.__call__

    def fake(cmd, cwd=None, timeout=300, env=None):
        if cmd[:3] == ["codex", "plugin", "list"]:
            data = after if applied["done"] else before
            return runner.Result(0, json.dumps({"installed": [{"pluginId": k, "version": v} for k, v in data.items()]}), "")
        return real(cmd, cwd=cwd, timeout=timeout, env=env)

    def apply_plugins(bk, refresh=False, say=None, **kw):
        applied["done"] = True
        return ["plugin y@url: no Codex route (its marketplace is not on GitHub)"]
    monkeypatch.setattr(codex, "apply_plugins", apply_plugins)
    return fake


def test_codex_hint_follows_real_version_changes_not_notes(fake_home, fake_runner, monkeypatch, capsys):
    from loadout import codex
    _setup(fake_home, monkeypatch, claude=False, codex=True)
    monkeypatch.setattr(codex, "hooks_status", lambda remember=False: "trusted")
    monkeypatch.setattr(runner, "run", _codex_versions(fake_runner, monkeypatch, {"x@m": "1"}, {"x@m": "1"}))
    _run(True)
    assert "Restart" not in capsys.readouterr().out
    monkeypatch.setattr(runner, "run", _codex_versions(fake_runner, monkeypatch, {"x@m": "1"}, {"x@m": "2"}))
    _run(True)
    out = capsys.readouterr().out
    assert "Codex: plugins updated" in out and "Now do this" in out
    assert "Codex: restart Codex (it loads plugins per session)" in out and "/hooks" not in out


def test_codex_plugin_update_names_the_hooks_when_not_approved(fake_home, fake_runner, monkeypatch, capsys):
    from loadout import codex
    _setup(fake_home, monkeypatch, claude=False, codex=True)
    monkeypatch.setattr(codex, "hooks_status", lambda remember=False: "untrusted")
    monkeypatch.setattr(runner, "run", _codex_versions(fake_runner, monkeypatch, {"x@m": "1"}, {"x@m": "2"}))
    _run(True)
    assert "Codex: restart Codex and approve the changed hooks in /hooks" in capsys.readouterr().out


def test_an_unusable_codex_gets_no_plugin_commands(fake_home, fake_runner, monkeypatch, capsys):
    _setup(fake_home, monkeypatch, claude=False, codex=True)
    from loadout import codex
    seen = []
    monkeypatch.setattr(codex, "unavailable", lambda: "codex is not installed")
    monkeypatch.setattr(codex, "apply_plugins", lambda bk, refresh=False, say=None, **kw: seen.append(1) or [])
    _run(True)
    assert seen == []
    assert "codex is not installed" in capsys.readouterr().out


def test_a_failed_marketplace_refresh_is_listed_and_plugins_are_not_called_current(fake_home, fake_runner, monkeypatch,
                                                                                   capsys):
    _setup(fake_home, monkeypatch)
    token = "ghp_" + "abcdefghijklmnopqrstuvwxyz0123456789"  # built, so the repo scan finds no literal token
    fake_runner.responses[("claude", "plugin", "marketplace", "update")] = runner.Result(
        1, "", f"fatal: unable to access 'https://jonas:{token}@github.com/x/y.git/': Could not resolve host\n")
    fake_runner.responses[("claude", "plugin", "update")] = runner.Result(0, "already at the latest version", "")
    _run(True)
    assert len(_updates(fake_runner)) == 2  # still tried, against the cached catalog
    out = capsys.readouterr().out
    assert "ghp_" not in out
    assert "already up to date" not in out
    changed = out.split("What changed", 1)[1]
    line = next(l for l in changed.splitlines() if "marketplaces: not refreshed" in l)
    assert "Could not resolve host" in line and "fix:" in line
    assert "cached catalog" in out
