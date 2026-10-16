"""Which side the user's Codex runs on, seen from WSL (spec PR B)."""
import os
import time

import pytest

from loadout import runner, wsl


@pytest.fixture
def win(tmp_path, fake_home, fake_runner, monkeypatch):
    home = tmp_path / "mnt" / "c" / "Users" / "u"
    home.mkdir(parents=True)
    monkeypatch.setattr(wsl, "windows_home", lambda: home)
    monkeypatch.delenv("CODEX_HOME", raising=False)
    return home


def _mount(home):
    return str(home.parents[2]) + "/"


def _sessions(home, age_days=1):
    f = home / ".codex" / "sessions" / "2026" / "10" / "15" / "rollout.jsonl"
    f.parent.mkdir(parents=True)
    f.write_text("{}")
    t = time.time() - age_days * 86400
    os.utime(f, (t, t))


def _vscode(home, text):
    p = wsl.vscode_settings(home)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def test_a_linux_codex_alone_is_the_wsl_side(win, fake_runner):
    fake_runner.paths["codex"] = "/home/u/.local/share/mise/shims/codex"
    assert wsl.codex_side(mount=_mount(win)).side == "wsl"


def test_only_a_windows_codex_is_the_windows_side(win, fake_runner):
    fake_runner.paths["codex"] = str(win / "AppData" / "Roaming" / "npm" / "codex")
    cs = wsl.codex_side(mount=_mount(win))
    assert cs.side == "windows" and any("Windows" in r for r in cs.reasons)


def test_recent_windows_sessions_next_to_a_linux_codex_is_both(win, fake_runner):
    fake_runner.paths["codex"] = "/usr/local/bin/codex"
    _sessions(win)
    cs = wsl.codex_side(mount=_mount(win))
    assert cs.side == "both" and cs.windows_used


def test_old_windows_sessions_do_not_count(win, fake_runner):
    fake_runner.paths["codex"] = "/usr/local/bin/codex"
    _sessions(win, age_days=90)
    assert wsl.codex_side(mount=_mount(win)).side == "wsl"


@pytest.mark.parametrize("text, mode", [
    ('{\n  // mine\n  "chatgpt.runCodexInWindowsSubsystemForLinux": true,\n}\n', True),
    ('{"chatgpt.runCodexInWindowsSubsystemForLinux": false}', False),
    ('{"editor.tabSize": 2}', None),
])
def test_the_vscode_setting_is_read_from_jsonc(win, text, mode):
    _vscode(win, text)
    assert wsl.vscode_wsl_mode(win) is mode


def test_vscode_in_windows_mode_without_a_linux_codex_is_windows(win, fake_runner):
    _vscode(win, '{"chatgpt.runCodexInWindowsSubsystemForLinux": false}')
    assert wsl.codex_side(mount=_mount(win)).side == "windows"


def test_codex_home_under_mnt_is_shared(win, fake_runner, monkeypatch):
    fake_runner.paths["codex"] = "/usr/local/bin/codex"
    monkeypatch.setenv("CODEX_HOME", str(win / ".codex"))
    assert wsl.codex_side(mount=_mount(win)).shared_home


def test_no_codex_anywhere_is_none(win):
    assert wsl.codex_side(mount=_mount(win)).side == "none"


def test_windows_home_survives_a_missing_cmd_exe(fake_home, fake_runner):
    fake_runner.responses[("cmd.exe",)] = runner.Result(127, "", "cmd.exe: not found")
    assert wsl.windows_home() is None


def test_windows_home_from_cmd_and_wslpath(tmp_path, fake_home, fake_runner):
    target = tmp_path / "c" / "Users" / "u"
    target.mkdir(parents=True)
    fake_runner.responses[("cmd.exe",)] = runner.Result(0, "C:\\Users\\u\r\n", "")
    fake_runner.responses[("wslpath",)] = runner.Result(0, f"{target}\n", "")
    assert wsl.windows_home() == target
