"""bootstrap --vscode-wsl and the VS Code switch with --codex-side wsl (spec Part 4)."""
import pytest

from loadout import __main__ as cli, backup, bootstrap, wsl

OFF = '{\n  // mine\n  "chatgpt.runCodexInWindowsSubsystemForLinux": false\n}\n'


def _vscode(monkeypatch, tmp_path, text=OFF, side="wsl", vscode_windows=True):
    home = tmp_path / "winhome"
    p = wsl.vscode_settings(home)
    p.parent.mkdir(parents=True)
    p.write_text(text)
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)
    monkeypatch.setattr(wsl, "codex_side", lambda **k: wsl.CodexSide(side, ["r"], windows_home=home,
                                                                      vscode_windows=vscode_windows))
    return home


def test_codex_side_wsl_in_a_terminal_offers_the_switch(fake_home, fake_runner, monkeypatch, tmp_path):
    home = _vscode(monkeypatch, tmp_path)
    asked, bk = [], backup.Backup(description="t")
    assert bootstrap.codex_gate("wsl", ask=lambda q: asked.append(q) or "y", interactive=True, bk=bk) is None
    assert asked == [bootstrap.VSCODE_QUESTION] and wsl.vscode_wsl_mode(home) is True


def test_the_flag_switches_without_asking_and_restore_undoes_it(fake_home, fake_runner, monkeypatch, tmp_path):
    home = _vscode(monkeypatch, tmp_path)
    bk = backup.Backup(description="t")
    assert bootstrap.codex_gate("wsl", ask=lambda q: pytest.fail("asked"), interactive=False, bk=bk, vscode=True) is None
    assert wsl.vscode_wsl_mode(home) is True and "// mine" in wsl.vscode_settings(home).read_text()
    _, ok, _ = backup.restore(bk.root)
    assert ok and wsl.vscode_settings(home).read_text() == OFF


def test_the_flag_works_when_both_sides_were_found(fake_home, fake_runner, monkeypatch, tmp_path):
    home = _vscode(monkeypatch, tmp_path, side="both")
    assert bootstrap.codex_gate(None, ask=lambda q: pytest.fail("asked"), interactive=False,
                                bk=backup.Backup(description="t"), vscode=True) is None
    assert wsl.vscode_wsl_mode(home) is True


def test_without_a_terminal_and_flag_the_manual_step_is_printed(fake_home, fake_runner, monkeypatch, tmp_path, capsys):
    home = _vscode(monkeypatch, tmp_path)
    assert bootstrap.codex_gate("wsl", ask=lambda q: pytest.fail("asked"), interactive=False) is None
    printed = capsys.readouterr().out
    assert wsl.MANUAL in printed and "--vscode-wsl" in printed and wsl.vscode_wsl_mode(home) is False


def test_the_flag_without_settings_names_the_manual_step(fake_home, fake_runner, monkeypatch, tmp_path, capsys):
    home = tmp_path / "winhome"
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)
    monkeypatch.setattr(wsl, "codex_side", lambda **k: wsl.CodexSide("wsl", ["r"], windows_home=home))
    bootstrap.codex_gate("wsl", ask=lambda q: "", interactive=False, bk=backup.Backup(description="t"), vscode=True)
    assert wsl.MANUAL in capsys.readouterr().out and not wsl.vscode_settings(home).exists()


def test_the_flag_without_a_windows_home_names_the_manual_step(fake_home, fake_runner, monkeypatch, capsys):
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)
    monkeypatch.setattr(wsl, "codex_side", lambda **k: wsl.CodexSide("wsl", ["r"]))
    bootstrap.codex_gate("wsl", ask=lambda q: "", interactive=False, bk=backup.Backup(description="t"), vscode=True)
    assert wsl.MANUAL in capsys.readouterr().out


def test_the_cli_passes_the_flag(fake_home, monkeypatch):
    got = {}
    monkeypatch.setattr(bootstrap, "bootstrap", lambda *a, **k: got.update(k) or 0)
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)
    assert cli.main(["bootstrap", "--codex-side", "wsl", "--vscode-wsl"]) == 0
    assert got["vscode_wsl"] is True and got["codex_side"] == "wsl"


def test_the_flag_outside_wsl_says_it_changed_nothing(fake_home, monkeypatch, capsys):
    monkeypatch.setattr(bootstrap, "bootstrap", lambda *a, **k: 0)
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: None)
    cli.main(["bootstrap", "--vscode-wsl"])
    assert "--vscode-wsl" in capsys.readouterr().out


def test_the_flag_outside_wsl_gets_no_second_warning_from_bootstrap(fake_home, fake_runner, monkeypatch):
    """The CLI says "applies to loadout in WSL only"; bootstrap must not add "Codex is not set up in WSL"."""
    from loadout import codex, out
    seen = []
    monkeypatch.setattr(out, "status", lambda label, text, *a, **k: seen.append(text))
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: None)
    monkeypatch.setattr(codex, "unavailable", lambda *a, **k: None)
    monkeypatch.setattr(codex, "apply_all", lambda bk, refresh=False, **kw: [])
    monkeypatch.setattr(codex, "open_steps", lambda: [])
    bootstrap.bootstrap(False, True, False, False, ask=lambda q: "", interactive=False, vscode_wsl=True,
                        agents="claude,codex")
    assert not any("not set up in WSL in this run" in t for t in seen), seen
