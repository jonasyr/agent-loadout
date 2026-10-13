"""loadout's own files live in $XDG_STATE_HOME/loadout (ADR 0025), never under ~/.claude."""
import importlib.util
import os

from loadout import paths

HOOKS = paths.kit_root() / "plugins" / "loadout" / "hooks"


def _hook(name):
    spec = importlib.util.spec_from_file_location(name, HOOKS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_default_location_is_xdg_state_under_home(fake_home):
    assert paths.state_dir() == fake_home / ".local" / "state" / "loadout"
    assert paths.backups_root() == paths.state_dir() / "backups"
    assert paths.legacy_state_dir() == fake_home / ".claude" / ".loadout"
    assert paths.legacy_backups_root() == fake_home / ".claude" / "backups"


def test_absolute_xdg_state_home_wins(fake_home, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "st"))
    assert paths.state_dir() == tmp_path / "st" / "loadout"


def test_relative_or_empty_xdg_state_home_is_ignored(fake_home, monkeypatch):
    for value in ("rel/state", ""):
        monkeypatch.setenv("XDG_STATE_HOME", value)
        assert paths.state_dir() == fake_home / ".local" / "state" / "loadout"


def test_tests_never_see_the_real_state_folder(fake_home):
    assert "XDG_STATE_HOME" not in os.environ
    assert paths.state_dir().is_relative_to(fake_home)


def test_hooks_use_the_same_folder(fake_home, tmp_path, monkeypatch):
    advisor = _hook("advisor")
    assert advisor.state_dir() == paths.state_dir()
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "st"))
    assert advisor.state_dir() == paths.state_dir()
    reload_check = _hook("reload_check")
    assert reload_check.state_dir(fake_home) == paths.state_dir()
