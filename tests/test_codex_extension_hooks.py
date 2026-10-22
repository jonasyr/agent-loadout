"""Hooks approved in VS Code's Codex extension (hooks icon, Allow all) count, and its steps say where (spec decision 2)."""
import pytest

from loadout import codex, codex_hooks, paths, runner, steps



@pytest.fixture
def serena(fake_home, monkeypatch):
    monkeypatch.setattr(codex_hooks, "serena_items", lambda: {_serena_key(): "activate"})


def _serena_key():
    return f"{codex_hooks.path()}:session_start:0:0"


def _trust(keys, plugin_on=True):
    lines = (['[plugins."loadout@agent-loadout"]', "enabled = true", ""] if plugin_on else []) + ["[hooks.state]"] + [f'"{k}" = {{ trusted_hash = "h{i}" }}' for i, k in enumerate(keys)]
    path = paths.codex_home() / "config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def test_allow_all_in_the_extension_clears_the_hooks(codex_ext, fake_runner, serena):
    _trust([_serena_key(), *sorted(codex.hook_keys())])
    assert codex.hooks_status() == "trusted"
    assert not any("hooks" in s for s in codex.open_steps())
    rows = {r.name: r for r in codex.checks()}
    assert rows["Codex hooks"].ok


def test_without_the_loadout_plugin_only_serenas_hooks_count(codex_ext, fake_runner, serena):
    _trust([_serena_key()], plugin_on=False)
    assert codex.hooks_status() == "trusted"


def test_with_the_loadout_plugin_its_hooks_must_be_approved(codex_ext, fake_runner, serena):
    _trust([_serena_key()])
    assert codex.hooks_status() == "untrusted"


def test_the_status_runs_no_codex(codex_ext, fake_runner, serena):
    _trust([_serena_key()])
    fake_runner.calls.clear()
    codex.hooks_status()
    assert fake_runner.calls == []


def test_extension_hooks_step_names_the_hooks_icon(codex_ext, monkeypatch):
    monkeypatch.setattr(codex, "hooks_status", lambda remember=False: "untrusted")
    assert codex.open_steps()[0] == codex.HOOKS_EXTENSION
    found = steps.derive({"codex_plugins_installed"}, [], False, True)
    assert [(s.id, s.text) for s in found] == [("codex/hooks", codex.HOOKS_EXTENSION)]
    rows = {r.name: r for r in codex.checks()}
    assert rows["Codex hooks"].fix == codex.HOOKS_EXTENSION
    every = " ".join(codex.open_steps() + [s.text for s in found] + [rows["Codex hooks"].fix])
    assert "Codex CLI" not in every and "--install" not in every


def test_changed_hooks_in_the_extension(codex_ext, monkeypatch):
    monkeypatch.setattr(codex, "hooks_status", lambda remember=False: "changed")
    assert codex.open_steps()[0] == codex.HOOKS_EXTENSION_CHANGED


def test_extension_restart_step_reloads_the_window(codex_ext, monkeypatch):
    monkeypatch.setattr(codex, "hooks_status", lambda remember=False: "trusted")
    found = steps.derive({"codex_plugins_installed"}, [], False, True)
    assert [(s.id, s.text) for s in found] == [("codex/restart", codex.RESTART_EXTENSION)]
    steps.save(found)
    steps.settle(False, True)
    assert "codex/restart" in [s.id for s in steps.pending("codex")]
