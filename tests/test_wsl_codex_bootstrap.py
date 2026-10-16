"""Bootstrap in WSL never sets up a Codex home the active Codex does not read (spec PR B)."""
import pytest

from loadout import bootstrap, codex, wsl


def _side(monkeypatch, side, **kw):
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)
    monkeypatch.setattr(wsl, "codex_side", lambda **k: wsl.CodexSide(side, [f"reason {side}"], **kw))


def test_outside_wsl_the_gate_is_open(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: None)
    monkeypatch.setattr(wsl, "codex_side", lambda **k: pytest.fail("read the Codex side outside WSL"))
    assert bootstrap.codex_gate(None, ask=lambda q: "", interactive=False) is None


@pytest.mark.parametrize("side", ["wsl", "both", "none"])
def test_a_wsl_side_is_set_up(fake_home, fake_runner, monkeypatch, side):
    _side(monkeypatch, side)
    assert bootstrap.codex_gate(None, ask=lambda q: "", interactive=False) is None


def test_only_windows_without_a_terminal_stops_with_both_ways(fake_home, fake_runner, monkeypatch):
    _side(monkeypatch, "windows")
    line = bootstrap.codex_gate(None, ask=lambda q: "", interactive=False)
    assert "--codex-side wsl" in line and "bootstrap.ps1" in line and "reason windows" in line


def test_the_flag_decides(fake_home, fake_runner, monkeypatch):
    _side(monkeypatch, "windows")
    assert bootstrap.codex_gate("wsl", ask=lambda q: "", interactive=False) is None
    assert "bootstrap.ps1" in bootstrap.codex_gate("windows", ask=lambda q: "", interactive=False)


def test_the_question_decides(fake_home, fake_runner, monkeypatch):
    _side(monkeypatch, "windows")
    assert bootstrap.codex_gate(None, ask=lambda q: "1", interactive=True) is None
    assert "bootstrap.ps1" in bootstrap.codex_gate(None, ask=lambda q: "2", interactive=True)


def test_a_shared_codex_home_needs_the_flag(fake_home, fake_runner, monkeypatch):
    _side(monkeypatch, "wsl", shared_home=True)
    assert "CODEX_HOME" in bootstrap.codex_gate(None, ask=lambda q: "", interactive=True)
    assert bootstrap.codex_gate("wsl", ask=lambda q: "", interactive=True) is None


def test_a_windows_codex_on_path_still_gets_the_agent_question(fake_home, fake_runner, monkeypatch):
    bootstrap.paths.personal_root().mkdir(parents=True)  # an existing layer that never chose
    fake_runner.missing.add("codex")
    fake_runner.paths["codex.exe"] = "/mnt/c/Program Files/codex/codex.exe"
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)
    asked = []
    bootstrap._choose_agents(lambda q: asked.append(q) or "2", interactive=True, flag=None)
    assert asked


def test_codex_off_never_needs_the_gate(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)
    assert bootstrap.codex_gate_needed({"claude": True, "codex": False}) is False
    assert bootstrap.codex_gate_needed({"claude": False, "codex": True}) is True


def test_codex_off_bootstrap_never_reads_the_side(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)
    monkeypatch.setattr(wsl, "codex_side", lambda **k: pytest.fail("read the Codex side with Codex off"))
    bootstrap.bootstrap(False, True, False, False, ask=lambda q: "", interactive=False, agents="claude")


def test_windows_only_bootstrap_skips_the_codex_step_and_keeps_going(fake_home, fake_runner, monkeypatch, capsys):
    _side(monkeypatch, "windows")
    monkeypatch.setattr(codex, "apply_all", lambda *a, **k: pytest.fail("set up the WSL Codex home"))
    rc = bootstrap.bootstrap(False, True, False, False, ask=lambda q: "", interactive=False, agents="codex")
    out = capsys.readouterr().out
    assert "--codex-side wsl" in out and "bootstrap.ps1" in out
    assert rc == bootstrap.bootstrap(False, True, False, False, ask=lambda q: "", interactive=False,
                                     agents="codex", codex_side="windows")


def test_install_replaces_a_windows_shim_with_a_linux_codex(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)
    fake_runner.paths["codex"] = "/mnt/c/Users/u/AppData/Roaming/npm/codex"
    assert bootstrap.missing_binary("codex") is True
    fake_runner.paths["codex"] = "/home/u/.local/share/mise/shims/codex"
    assert bootstrap.missing_binary("codex") is False


def test_outside_wsl_a_codex_on_path_is_there(fake_home, fake_runner):
    fake_runner.paths["codex"] = "/mnt/c/Users/u/AppData/Roaming/npm/codex"
    assert bootstrap.missing_binary("codex") is False


def test_the_windows_side_installs_no_linux_codex(fake_home, fake_runner, monkeypatch, capsys):
    _side(monkeypatch, "windows")
    fake_runner.missing.add("codex")
    for flag in ("windows", None):
        bootstrap.bootstrap(True, True, False, False, ask=lambda q: "", interactive=False, agents="codex",
                            codex_side=flag)
    assert ["mise", "use", "-g", "codex"] not in fake_runner.calls
    assert "missing (required) codex" not in capsys.readouterr().out


def test_answering_windows_installs_no_linux_codex(fake_home, fake_runner, monkeypatch):
    _side(monkeypatch, "windows")
    fake_runner.missing.add("codex")
    bootstrap.bootstrap(True, False, False, False, ask=lambda q: "2" if "Windows" in q else "", interactive=True,
                        agents="codex")
    assert ["mise", "use", "-g", "codex"] not in fake_runner.calls


def test_the_windows_shim_is_named_when_the_gate_is_open(fake_home, fake_runner, monkeypatch, capsys):
    _side(monkeypatch, "windows")
    fake_runner.paths["codex"] = "/mnt/c/Users/u/AppData/Roaming/npm/codex"
    monkeypatch.setattr(codex, "apply_all", lambda *a, **k: pytest.fail("set up through the Windows codex"))
    bootstrap.bootstrap(False, True, False, False, ask=lambda q: "", interactive=False, agents="codex",
                        codex_side="wsl")
    assert "the codex on PATH is the Windows one" in capsys.readouterr().out


def test_yes_in_a_terminal_does_not_pick_a_side(fake_home, fake_runner, monkeypatch, capsys):
    _side(monkeypatch, "windows")
    monkeypatch.setattr(codex, "apply_all", lambda *a, **k: pytest.fail("--yes picked WSL"))
    bootstrap.bootstrap(False, True, False, False, ask=lambda q: pytest.fail(f"asked: {q}") if "Windows" in q else "",
                        interactive=True, agents="codex")
    assert "--codex-side wsl" in capsys.readouterr().out


def test_skipping_the_codex_step_keeps_the_exit_code(fake_home, fake_runner, monkeypatch):
    _side(monkeypatch, "windows")
    monkeypatch.setattr(codex, "unavailable", lambda: "codex is not usable here")
    skipped = bootstrap.bootstrap(False, True, False, False, ask=lambda q: "", interactive=False, agents="codex")
    open_gate = bootstrap.bootstrap(False, True, False, False, ask=lambda q: "", interactive=False, agents="codex",
                                    codex_side="wsl")
    assert skipped == open_gate


def _windows_with_vscode(monkeypatch, tmp_path, text):
    home = tmp_path / "winhome"
    p = wsl.vscode_settings(home)
    p.parent.mkdir(parents=True)
    p.write_text(text)
    _side(monkeypatch, "windows", windows_home=home)
    return home


def test_choosing_wsl_offers_the_vscode_switch_and_a_yes_makes_it(fake_home, fake_runner, monkeypatch, tmp_path):
    from loadout import backup
    home = _windows_with_vscode(monkeypatch, tmp_path, '{"chatgpt.runCodexInWindowsSubsystemForLinux": false}')
    asked, bk = [], backup.Backup(description="t")
    answers = iter(["1", "y"])
    assert bootstrap.codex_gate(None, ask=lambda q: asked.append(q) or next(answers), interactive=True, bk=bk) is None
    assert any("VS Code" in q for q in asked) and wsl.vscode_wsl_mode(home) is True and bk.steps


def test_a_no_leaves_vscode_alone(fake_home, fake_runner, monkeypatch, tmp_path):
    from loadout import backup
    home = _windows_with_vscode(monkeypatch, tmp_path, '{"chatgpt.runCodexInWindowsSubsystemForLinux": false}')
    answers = iter(["1", ""])
    assert bootstrap.codex_gate(None, ask=lambda q: next(answers), interactive=True,
                                bk=backup.Backup(description="t")) is None
    assert wsl.vscode_wsl_mode(home) is False


def test_without_a_backup_the_switch_is_the_manual_step(fake_home, fake_runner, monkeypatch, tmp_path, capsys):
    home = _windows_with_vscode(monkeypatch, tmp_path, '{"chatgpt.runCodexInWindowsSubsystemForLinux": false}')
    answers = iter(["1", "y"])
    bootstrap.codex_gate(None, ask=lambda q: next(answers), interactive=True)
    assert wsl.MANUAL in capsys.readouterr().out and wsl.vscode_wsl_mode(home) is False


def test_no_vscode_settings_means_no_question(fake_home, fake_runner, monkeypatch, tmp_path):
    _side(monkeypatch, "windows", windows_home=tmp_path / "winhome")
    asked = []
    assert bootstrap.codex_gate(None, ask=lambda q: asked.append(q) or "1", interactive=True) is None
    assert len(asked) == 1


def test_in_wsl_a_windows_codex_is_unavailable_for_every_caller(fake_home, fake_runner, monkeypatch):
    from loadout import runner
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)
    fake_runner.paths["codex"] = "/mnt/c/Users/u/AppData/Roaming/npm/codex"
    fake_runner.responses[("codex", "--version")] = runner.Result(0, "codex-cli 0.170.0\n", "")
    assert "the codex on PATH is the Windows one" in codex.unavailable()
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: None)
    assert codex.unavailable() is None
