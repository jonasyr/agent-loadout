"""loadout check in WSL: VS Code's Codex extension must run the WSL Codex (spec Part 4)."""
from loadout import check, wsl


def _home(tmp_path, text):
    home = tmp_path / "winhome"
    p = wsl.vscode_settings(home)
    p.parent.mkdir(parents=True)
    p.write_text(text)
    return home


def test_a_warning_when_the_extension_runs_the_windows_codex(tmp_path):
    home = _home(tmp_path, '{"chatgpt.runCodexInWindowsSubsystemForLinux": false}')
    rows = check._vscode(wsl.CodexSide("wsl", [], windows_home=home, vscode_windows=True))
    assert len(rows) == 1 and rows[0].name == "VS Code" and not rows[0].ok and rows[0].severity == "warn"
    assert "--vscode-wsl" in rows[0].fix and wsl.MANUAL in rows[0].fix


def test_ok_when_it_runs_in_wsl(tmp_path):
    home = _home(tmp_path, '{"chatgpt.runCodexInWindowsSubsystemForLinux": true}')
    rows = check._vscode(wsl.CodexSide("both", [], windows_home=home))
    assert len(rows) == 1 and rows[0].ok


def test_no_row_without_codex_in_wsl_or_vscode(tmp_path):
    home = _home(tmp_path, "{}")
    assert check._vscode(None) == []
    assert check._vscode(wsl.CodexSide("windows", [], windows_home=home, vscode_windows=True)) == []
    assert check._vscode(wsl.CodexSide("wsl", [], windows_home=home)) == []  # no extension, no setting
    assert check._vscode(wsl.CodexSide("wsl", [])) == []


def test_run_checks_includes_the_row(fake_home, fake_runner, monkeypatch, tmp_path):
    home = _home(tmp_path, '{"chatgpt.runCodexInWindowsSubsystemForLinux": false}')
    monkeypatch.setattr(check, "_wsl_codex_side", lambda: wsl.CodexSide("wsl", [], windows_home=home, vscode_windows=True))
    assert any(r.name == "VS Code" and not r.ok for r in check.run_checks())
