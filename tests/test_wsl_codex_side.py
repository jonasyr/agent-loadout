"""Which side the user's Codex runs on, seen from WSL (spec PR B)."""
import os
import time

import pytest

from loadout import backup, runner, wsl


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


def test_the_setting_is_flipped_by_a_text_edit(win):
    text = '{\n  // keep me\n  "editor.tabSize": 2,\n  "chatgpt.runCodexInWindowsSubsystemForLinux": false,\n}\n'
    _vscode(win, text)
    bk = backup.Backup(description="t")
    line = wsl.set_vscode_wsl_mode(bk, win)
    assert wsl.vscode_settings(win).read_text() == text.replace(": false,", ": true,")
    assert "VS Code" in line and bk.steps


def test_the_setting_is_added_when_missing(win):
    _vscode(win, '{\n  "editor.tabSize": 2\n}\n')
    wsl.set_vscode_wsl_mode(backup.Backup(description="t"), win)
    text = wsl.vscode_settings(win).read_text()
    assert wsl.vscode_wsl_mode(win) is True and '"editor.tabSize": 2' in text


def test_no_settings_file_gives_the_manual_step(win):
    line = wsl.set_vscode_wsl_mode(backup.Backup(description="t"), win)
    assert "Settings" in line and not wsl.vscode_settings(win).exists()


def test_crlf_and_every_other_byte_stay(win):
    raw = b'\xef\xbb\xbf{\r\n  "a": 1,\r\n  "chatgpt.runCodexInWindowsSubsystemForLinux": false\r\n}\r\n'
    p = wsl.vscode_settings(win)
    p.parent.mkdir(parents=True)
    p.write_bytes(raw)
    wsl.set_vscode_wsl_mode(backup.Backup(description="t"), win)
    assert p.read_bytes() == raw.replace(b": false", b": true")


def test_an_added_line_uses_the_files_line_ending(win):
    p = wsl.vscode_settings(win)
    p.parent.mkdir(parents=True)
    p.write_bytes(b'{\r\n  "a": 1\r\n}\r\n')
    wsl.set_vscode_wsl_mode(backup.Backup(description="t"), win)
    assert p.read_bytes() == b'{\r\n  "chatgpt.runCodexInWindowsSubsystemForLinux": true,\r\n  "a": 1\r\n}\r\n'


def test_an_empty_object_gets_no_trailing_comma(win):
    _vscode(win, "{}")
    wsl.set_vscode_wsl_mode(backup.Backup(description="t"), win)
    assert wsl.vscode_settings(win).read_text() == '{\n  "chatgpt.runCodexInWindowsSubsystemForLinux": true\n}'


def test_a_commented_out_setting_is_neither_read_nor_edited(win):
    text = ('// { "chatgpt.runCodexInWindowsSubsystemForLinux": true }\n{\n'
            '  /* "chatgpt.runCodexInWindowsSubsystemForLinux": true */\n'
            '  "chatgpt.runCodexInWindowsSubsystemForLinux": false\n}\n')
    _vscode(win, text)
    assert wsl.vscode_wsl_mode(win) is False
    wsl.set_vscode_wsl_mode(backup.Backup(description="t"), win)
    assert wsl.vscode_settings(win).read_text() == text[: text.rindex("false")] + "true\n}\n"


def test_restore_puts_the_old_settings_back(win):
    text = '{"chatgpt.runCodexInWindowsSubsystemForLinux": false}'
    _vscode(win, text)
    bk = backup.Backup(description="t")
    wsl.set_vscode_wsl_mode(bk, win)
    backup.restore(bk.root)
    assert wsl.vscode_settings(win).read_text() == text


def test_already_on_changes_nothing(win):
    _vscode(win, '{"chatgpt.runCodexInWindowsSubsystemForLinux": true}')
    bk = backup.Backup(description="t")
    assert "already" in wsl.set_vscode_wsl_mode(bk, win) and not bk.steps


K = '"chatgpt.runCodexInWindowsSubsystemForLinux"'


def test_a_failed_write_falls_back_to_the_manual_step(win, monkeypatch):
    from loadout import jsonio
    text = '{%s: false}' % K
    _vscode(win, text)

    def refuse(*a, **k):
        raise PermissionError("in use by Code.exe")
    monkeypatch.setattr(jsonio, "write_atomic_bytes", refuse)
    line = wsl.set_vscode_wsl_mode(backup.Backup(description="t"), win)
    assert "could not change" in line and wsl.MANUAL in line and wsl.vscode_settings(win).read_text() == text


def test_the_last_top_level_copy_wins_as_in_vscode(win):
    _vscode(win, '{%s: true, %s: false}' % (K, K))
    assert wsl.vscode_wsl_mode(win) is False
    wsl.set_vscode_wsl_mode(backup.Backup(description="t"), win)
    assert wsl.vscode_settings(win).read_text() == '{%s: true, %s: true}' % (K, K)


def test_a_nested_copy_is_neither_read_nor_edited(win):
    text = '{"[python]": {%s: false}, "a": [{%s: false}]}' % (K, K)
    _vscode(win, text)
    assert wsl.vscode_wsl_mode(win) is None
    wsl.set_vscode_wsl_mode(backup.Backup(description="t"), win)
    assert wsl.vscode_settings(win).read_text() == '{\n  %s: true,%s' % (K, text[1:])


def test_a_value_that_is_not_true_or_false_is_left_to_the_user(win):
    text = '{%s: null}' % K
    _vscode(win, text)
    line = wsl.set_vscode_wsl_mode(backup.Backup(description="t"), win)
    assert wsl.MANUAL in line and wsl.vscode_settings(win).read_text() == text
