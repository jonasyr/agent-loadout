"""Bootstrap in WSL never sets up a Codex home the active Codex does not read (spec PR B)."""
import pytest

from loadout import bootstrap, catalog, codex, paths, wsl


def _win_shim(monkeypatch, tmp_path):
    """A Windows npm codex shim under a fake /mnt (as_posix: the Windows CI job resolves paths too)."""
    monkeypatch.setattr(wsl, "MOUNT", (tmp_path / "mnt").as_posix() + "/")
    return (tmp_path / "mnt" / "c" / "Users" / "u" / "AppData" / "Roaming" / "npm" / "codex").as_posix()


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


def test_install_replaces_a_windows_shim_with_a_linux_codex(fake_home, fake_runner, monkeypatch, tmp_path):
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)
    fake_runner.paths["codex"] = _win_shim(monkeypatch, tmp_path)
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


def test_the_windows_shim_is_named_when_the_gate_is_open(fake_home, fake_runner, monkeypatch, capsys, tmp_path):
    _side(monkeypatch, "windows")
    fake_runner.paths["codex"] = _win_shim(monkeypatch, tmp_path)
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
    monkeypatch.setattr(codex, "unavailable", lambda **k: "codex is not usable here")
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


def test_in_wsl_a_windows_codex_is_unavailable_for_every_caller(fake_home, fake_runner, monkeypatch, tmp_path):
    from loadout import runner
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)
    fake_runner.paths["codex"] = _win_shim(monkeypatch, tmp_path)
    fake_runner.responses[("codex", "--version")] = runner.Result(0, "codex-cli 0.170.0\n", "")
    assert "the codex on PATH is the Windows one" in codex.unavailable()
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: None)
    assert codex.unavailable() is None


def test_a_typo_in_the_side_question_stops_instead_of_choosing(fake_home, fake_runner, monkeypatch):
    _side(monkeypatch, "windows")
    line = bootstrap.codex_gate(None, ask=lambda q: "wsl", interactive=True)
    assert "no such choice" in line and "--codex-side wsl" in line


def test_a_shared_codex_home_is_unavailable_unless_bootstrap_was_told(fake_home, fake_runner, monkeypatch, tmp_path):
    from loadout import runner
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)
    monkeypatch.setattr(wsl, "MOUNT", (tmp_path / "mnt").as_posix() + "/")
    shared = tmp_path / "mnt" / "c" / "Users" / "u" / ".codex"
    shared.mkdir(parents=True)
    monkeypatch.setenv("CODEX_HOME", str(shared))
    fake_runner.paths["codex"] = "/usr/local/bin/codex"
    fake_runner.responses[("codex", "--version")] = runner.Result(0, "codex-cli 0.170.0\n", "")
    assert "CODEX_HOME points into Windows" in codex.unavailable()
    assert codex.unavailable(allow_shared_home=True) is None


def test_bootstrap_with_codex_side_wsl_sets_up_a_shared_home(fake_home, fake_runner, monkeypatch, tmp_path):
    _side(monkeypatch, "wsl", shared_home=True)
    seen = []
    monkeypatch.setattr(codex, "unavailable", lambda allow_shared_home=False: seen.append(allow_shared_home))
    monkeypatch.setattr(codex, "apply_all", lambda *a, **k: [])
    bootstrap.bootstrap(False, True, False, False, ask=lambda q: "", interactive=False, agents="codex",
                        codex_side="wsl")
    assert seen[0] is True  # the Codex step; the final check still warns about the shared home


def test_both_sides_with_the_extension_on_windows_offers_the_switch(fake_home, fake_runner, monkeypatch, tmp_path):
    from loadout import backup
    home = tmp_path / "winhome"
    p = wsl.vscode_settings(home)
    p.parent.mkdir(parents=True)
    p.write_text('{"editor.tabSize": 2}')
    _side(monkeypatch, "both", windows_home=home, vscode_windows=True)
    asked = []
    assert bootstrap.codex_gate(None, ask=lambda q: asked.append(q) or "y", interactive=True,
                                bk=backup.Backup(description="t")) is None
    assert len(asked) == 1 and "VS Code" in asked[0] and wsl.vscode_wsl_mode(home) is True


def test_both_sides_without_a_terminal_names_the_manual_switch(fake_home, fake_runner, monkeypatch, tmp_path, capsys):
    _side(monkeypatch, "both", windows_home=tmp_path, vscode_windows=True)
    assert bootstrap.codex_gate(None, ask=lambda q: pytest.fail(q), interactive=False) is None
    assert wsl.MANUAL in capsys.readouterr().out


def test_the_windows_side_gets_no_wsl_codex_follow_ups(fake_home, fake_runner, monkeypatch, capsys):
    _side(monkeypatch, "windows")
    monkeypatch.setattr(codex, "open_steps", lambda: ["approve them in Codex: /hooks"])
    bootstrap.bootstrap(False, True, False, False, ask=lambda q: "", interactive=False, agents="codex",
                        codex_side="windows")
    out = capsys.readouterr().out
    assert "/hooks" not in out and "Restart Codex" not in out and "bootstrap.ps1" in out.strip().splitlines()[-1]


def test_both_agents_with_the_windows_side_name_only_claude_next(fake_home, fake_runner, monkeypatch, capsys):
    _side(monkeypatch, "windows")
    monkeypatch.setattr(codex, "open_steps", lambda: ["approve them in Codex: /hooks"])
    bootstrap.bootstrap(False, True, False, False, ask=lambda q: "", interactive=False, agents="claude,codex",
                        codex_side="windows")
    last = capsys.readouterr().out.strip().splitlines()[-1]
    assert "Claude Code" in last and "Codex" not in last


def test_choosing_windows_against_the_detection_reaches_the_final_check(fake_home, fake_runner, monkeypatch, capsys):
    _side(monkeypatch, "none")
    fake_runner.missing.add("codex")
    bootstrap.bootstrap(False, True, False, False, ask=lambda q: "", interactive=False, agents="codex",
                        codex_side="windows")
    out = capsys.readouterr().out
    assert not [line for line in out.splitlines() if "binary codex" in line]
    assert any(line.startswith("[ok  ] Codex") for line in out.splitlines())


def test_codex_set_up_on_the_windows_side_keeps_its_open_steps(fake_home, fake_runner, monkeypatch):
    from loadout import steps
    _side(monkeypatch, "windows")
    monkeypatch.setattr(codex, "apply_all", lambda *a, **k: pytest.fail("set up the WSL Codex home"))
    monkeypatch.setattr(codex, "hooks_status", lambda remember=False: "changed")
    steps.save([steps.Step("codex/hooks", "codex", "approve the changed hooks in /hooks", "x")])
    bootstrap.bootstrap(False, True, False, False, ask=lambda q: "", interactive=False, agents="codex")
    assert [s.id for s in steps.pending("codex")] == ["codex/hooks"]  # Codex is on, only not set up from here


@pytest.fixture
def in_wsl(monkeypatch, tmp_path):
    """WSL 2 on Linux (also on the Windows CI runner) with a fake /mnt; returns the Windows npm folder."""
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)
    monkeypatch.setattr(paths, "platform_key", lambda: "posix")
    return _win_shim(monkeypatch, tmp_path).rsplit("/", 1)[0]


@pytest.mark.parametrize("name", ["claude", "uv", "npm", "git", "node", "playwright-cli"])
def test_in_wsl_a_windows_tool_on_path_counts_as_missing(fake_home, fake_runner, in_wsl, name):
    fake_runner.paths[name] = in_wsl + "/" + name
    assert bootstrap.missing_binary(name) is True
    assert wsl.is_windows_program(name) is True
    fake_runner.paths[name] = "/home/u/.local/bin/" + name
    assert bootstrap.missing_binary(name) is False


def test_in_wsl_node_is_missing_when_its_npm_is_the_windows_one(fake_home, fake_runner, in_wsl):
    fake_runner.paths["node"] = "/home/u/.local/bin/node"
    fake_runner.paths["npm"] = in_wsl + "/npm"
    assert bootstrap.missing_binary("node") is True


def test_outside_wsl_a_windows_looking_claude_is_there(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: None)
    fake_runner.paths["claude"] = "/mnt/c/Users/u/AppData/Roaming/npm/claude"
    assert bootstrap.missing_binary("claude") is False


def _install_cmds(name):
    entry = next(e for e in catalog.binaries() if e["id"] == name)
    return catalog.platform_cmds(entry, "install")


def test_in_wsl_the_report_lists_a_windows_claude_and_runs_nothing(fake_home, fake_runner, in_wsl):
    fake_runner.paths["claude"] = in_wsl + "/claude"
    assert "claude" in [e["id"] for e, _c, _o in bootstrap.missing_tools()]
    notes: list[str] = []
    bootstrap.check_prereqs(False, lambda q: "", notes=notes)
    assert any("claude" in n and "--install" in n for n in notes)
    assert not any(c in fake_runner.calls for c in _install_cmds("claude"))
    assert not any(c[0] in ("curl", "mise") for c in fake_runner.calls)


def test_in_wsl_install_runs_the_linux_install_for_a_windows_claude(fake_home, fake_runner, in_wsl):
    fake_runner.paths["claude"] = in_wsl + "/claude"
    bootstrap.check_prereqs(True, lambda q: "")
    assert all(c in fake_runner.calls for c in _install_cmds("claude")) and _install_cmds("claude")
    assert not any(wsl.MOUNT in " ".join(c) for c in fake_runner.calls)


def test_in_wsl_a_windows_claude_that_stays_first_names_the_folder_to_put_first(fake_home, fake_runner, in_wsl):
    fake_runner.paths["claude"] = in_wsl + "/claude"
    notes: list[str] = []
    bootstrap.check_prereqs(False, lambda q: "", notes=notes)
    assert any("claude" in n and ".local/bin" in n and "PATH" in n for n in notes)
    notes.clear()
    bootstrap.check_prereqs(True, lambda q: "", notes=notes)  # fake PATH order is not changed by the install
    line = next(n for n in notes if "still" in n)
    assert ".local/bin" in line and "first in PATH" in line and "appendWindowsPath" in line
    assert "fixed" not in line


def test_in_wsl_a_windows_git_says_to_use_the_package_manager(fake_home, fake_runner, in_wsl):
    fake_runner.paths["git"] = in_wsl + "/git"
    notes: list[str] = []
    bootstrap.check_prereqs(True, lambda q: "", notes=notes)
    assert any("missing" in n and "git" in n and "inside WSL with your package manager (sudo apt install git)" in n
               for n in notes)


def test_in_wsl_problems_cover_a_windows_only_catalog_tool(fake_home, fake_runner, in_wsl):
    fake_runner.paths["playwright-cli"] = in_wsl + "/playwright-cli"
    found = wsl.problems(2, None)
    assert any("playwright-cli" in p and "Windows program" in p for p, _f in found)
    fixes = " ".join(f for p, f in found if "playwright-cli" in p)
    assert "loadout bootstrap --install" in fixes and "loadout update" in fixes and "first in PATH" in fixes


def test_in_wsl_windows_first_after_install_is_one_note_and_blocks_nothing(fake_home, fake_runner, in_wsl):
    fake_runner.paths["node"] = in_wsl + "/node"
    fake_runner.paths["npm"] = in_wsl + "/npm"
    notes: list[str] = []
    missing = bootstrap.check_prereqs(True, lambda q: "", notes=notes)
    text = "\n".join(notes)
    assert "re-run with --install" not in text
    assert "node" not in missing
    assert sum("node still resolves to the Windows program" in n for n in notes) == 1
    assert "missing (required) node" not in text
    assert not any("because node failed" in n for n in notes)


def test_in_wsl_linux_folder_of_a_mise_tool_is_mises_shims_before_the_install(fake_home, fake_runner, in_wsl):
    assert bootstrap._linux_folder("node") == "~/.local/share/mise/shims"
    assert bootstrap._linux_folder("claude") == "~/.local/bin"


def test_in_wsl_a_windows_only_git_is_told_to_use_the_package_manager(fake_home, fake_runner, in_wsl):
    """git has no install command: check must not send the person to --install or update, which cannot help."""
    fake_runner.paths["git"] = in_wsl + "/git"
    found = wsl.problems(2, None)
    fixes = " ".join(f for p, f in found if p.startswith("git "))
    assert "package manager" in fixes and "sudo apt install git" in fixes
    assert "loadout bootstrap --install" not in fixes and "loadout update" not in fixes
