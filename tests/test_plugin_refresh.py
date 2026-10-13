"""loadout update refreshes loadout's plugins in both agents; the kit's marketplaces auto-update."""
import json

from loadout import maintenance, paths, runner, settings_merge, targets

SETTINGS = {"enabledPlugins": {"a@m": True, "b@m": True, "off@m": False, "proj@m": True, "gone@m": True}}


def _setup(fake_home, monkeypatch, claude=True, codex=False):
    targets.set_agents({"claude": claude, "codex": codex})
    monkeypatch.setattr(maintenance, "find_outdated", lambda: [])
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: SETTINGS)
    f = paths.claude_home() / "plugins" / "installed_plugins.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"plugins": {
        "a@m": [{"scope": "user"}], "b@m": [{"scope": "user"}], "off@m": [{"scope": "user"}],
        "proj@m": [{"scope": "project"}]}}))


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
    maintenance._update(True, lambda q: "")
    assert fake_runner.calls[0] == ["claude", "plugin", "marketplace", "update"]
    assert _updates(fake_runner) == [["claude", "plugin", "update", "a@m", "--scope", "user"],
                                     ["claude", "plugin", "update", "b@m", "--scope", "user"]]
    out = capsys.readouterr().out
    assert "a@m" in out and "b@m" not in out
    assert "/reload-plugins" in out


def test_no_hint_when_nothing_changed(fake_home, fake_runner, monkeypatch, capsys):
    _setup(fake_home, monkeypatch)
    fake_runner.responses[("claude", "plugin", "update")] = runner.Result(0, "already at the latest version", "")
    maintenance._update(True, lambda q: "")
    assert "/reload-plugins" not in capsys.readouterr().out


def test_a_failing_update_is_one_line_and_the_loop_continues(fake_home, fake_runner, monkeypatch, capsys):
    _setup(fake_home, monkeypatch)
    fake_runner.responses[("claude", "plugin", "update", "a@m")] = runner.Result(1, "", "boom")
    maintenance._update(True, lambda q: "")
    assert len(_updates(fake_runner)) == 2
    out = capsys.readouterr().out
    assert [l for l in out.splitlines() if "a@m" in l and "failed:" in l and "boom" in l].__len__() == 1


def test_claude_off_makes_no_claude_call(fake_home, fake_runner, monkeypatch):
    _setup(fake_home, monkeypatch, claude=False, codex=True)
    maintenance._update(True, lambda q: "")
    assert not any(c[0] == "claude" for c in fake_runner.calls)


def test_codex_on_refreshes_codex_plugins(fake_home, fake_runner, monkeypatch, capsys):
    _setup(fake_home, monkeypatch, codex=True)
    seen = []
    from loadout import codex
    monkeypatch.setattr(codex, "apply_plugins", lambda bk, refresh=False, say=None: seen.append(refresh) or ["plugin x: updated"])
    maintenance._update(True, lambda q: "")
    assert seen == [True]
    assert "plugin x: updated" in capsys.readouterr().out
