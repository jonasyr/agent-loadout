"""A folder's or a profile's settings that turn the Codex extension's WSL switch off win; loadout names them (spec Part 3.1)."""
import pytest

from loadout import backup, bootstrap, check, vscode, wsl

KEY = wsl.WIN_SETTING


def _win(tmp_path, user: str = '{"%s": true}' % KEY):
    home = tmp_path / "winhome"
    p = wsl.vscode_settings(home)
    p.parent.mkdir(parents=True)
    p.write_text(user)
    return home


def _profile(home, value="false"):
    p = wsl.vscode_settings(home).parent / "profiles" / "abc" / "settings.json"
    p.parent.mkdir(parents=True)
    p.write_text('{\n  // work\n  "%s": %s,\n}\n' % (KEY, value))
    return p


def _repo(tmp_path, monkeypatch, text):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / ".vscode").mkdir()
    (repo / ".vscode" / "settings.json").write_text(text)
    monkeypatch.chdir(repo)
    return repo / ".vscode" / "settings.json"


def test_folder_false_is_an_override(fake_home, tmp_path, monkeypatch):
    home = _win(tmp_path)
    folder = _repo(tmp_path, monkeypatch, '{"%s": false}' % KEY)
    assert vscode.wsl_switch_overrides(home) == [("folder", folder)]


def test_profile_false_is_an_override(fake_home, tmp_path, monkeypatch):
    home = _win(tmp_path)
    monkeypatch.chdir(tmp_path)
    p = _profile(home)
    assert vscode.wsl_switch_overrides(home) == [("profile", p)]


def test_true_or_unset_is_no_override(fake_home, tmp_path, monkeypatch):
    home = _win(tmp_path)
    _repo(tmp_path, monkeypatch, '{"%s": true}' % KEY)
    _profile(home, "true")
    assert vscode.wsl_switch_overrides(home) == []


def test_broken_folder_settings_give_no_override(fake_home, tmp_path, monkeypatch):
    home = _win(tmp_path)
    _repo(tmp_path, monkeypatch, '{"%s": false' % KEY)
    assert vscode.wsl_switch_overrides(home) == []


def test_check_names_the_folder_and_drops_the_ok_row(fake_home, tmp_path, monkeypatch):
    home = _win(tmp_path)
    folder = _repo(tmp_path, monkeypatch, '{"%s": false}' % KEY)
    rows = check._vscode(wsl.CodexSide("wsl", [], windows_home=home))
    assert not any(r.ok for r in rows)
    assert len(rows) == 1 and rows[0].name == "VS Code" and rows[0].severity == "warn"
    assert str(folder) in rows[0].detail and "win over" in rows[0].detail
    assert "does not edit" in rows[0].fix


def test_check_names_a_profile_next_to_the_ok_row(fake_home, tmp_path, monkeypatch):
    home = _win(tmp_path)
    monkeypatch.chdir(tmp_path)
    p = _profile(home)
    rows = check._vscode(wsl.CodexSide("wsl", [], windows_home=home))
    assert [r.ok for r in rows] == [True, False]
    assert str(p) in rows[1].detail and "which profile is active" in rows[1].detail


def test_folder_true_is_ok_even_when_the_user_setting_is_off(fake_home, tmp_path, monkeypatch):
    home = _win(tmp_path, '{"%s": false}' % KEY)
    _repo(tmp_path, monkeypatch, '{"%s": true}' % KEY)
    rows = check._vscode(wsl.CodexSide("wsl", [], windows_home=home, vscode_windows=True))
    assert len(rows) == 1 and rows[0].ok and "this folder" in rows[0].detail


def test_vscode_wsl_flag_names_the_override_and_leaves_it(fake_home, fake_runner, tmp_path, monkeypatch, capsys):
    home = _win(tmp_path, '{"%s": false}' % KEY)
    folder = _repo(tmp_path, monkeypatch, '{"%s": false}' % KEY)
    before = folder.read_bytes()
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)
    monkeypatch.setattr(wsl, "codex_side", lambda **k: wsl.CodexSide("wsl", ["r"], windows_home=home,
                                                                      vscode_windows=True))
    assert bootstrap.codex_gate("wsl", ask=lambda q: pytest.fail("asked"), interactive=False,
                                bk=backup.Backup(description="t"), vscode=True) is None
    text = capsys.readouterr().out
    assert wsl.vscode_wsl_mode(home) is True and str(folder) in text and folder.read_bytes() == before


def test_bootstrap_prints_the_override_path_escaped(fake_home, fake_runner, tmp_path, monkeypatch, capsys):
    home = _win(tmp_path)
    repo = tmp_path / "re\x1b[31mpo"
    (repo / ".git").mkdir(parents=True)
    (repo / ".vscode").mkdir()
    (repo / ".vscode" / "settings.json").write_text('{"%s": false}' % KEY)
    monkeypatch.chdir(repo)
    bootstrap._vscode_step(wsl.CodexSide("wsl", [], windows_home=home), lambda q: "", False, None, False)
    text = capsys.readouterr().out
    assert "settings.json" in text and "\x1b[31m" not in text
