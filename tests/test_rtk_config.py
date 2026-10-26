"""rtk's config.toml: where it lives, and loadout's one line that silences rtk's false "No hook installed" warning
where loadout's plugin provides the hook (ADR 0043). Never the real rtk config; rtk never runs."""
import sys

from loadout import paths


def test_rtk_config_path_per_os(fake_home, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    assert paths.rtk_config() == fake_home / ".config/rtk/config.toml"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(fake_home / "xdg"))
    assert paths.rtk_config() == fake_home / "xdg/rtk/config.toml"
    monkeypatch.setenv("XDG_CONFIG_HOME", "relative")  # not absolute: ignored, as rtk's dirs crate does
    assert paths.rtk_config() == fake_home / ".config/rtk/config.toml"
    monkeypatch.setattr(sys, "platform", "darwin")
    assert paths.rtk_config() == fake_home / "Library/Application Support/rtk/config.toml"
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(fake_home / "AD"))
    assert paths.rtk_config() == fake_home / "AD/rtk/config.toml"
    monkeypatch.delenv("APPDATA")
    assert paths.rtk_config() == fake_home / "AppData/Roaming/rtk/config.toml"
