"""One Codex mode decides which codex runs: the CLI, else VS Code's Codex extension's own (spec decision 8)."""
from loadout import backup, codex, runner

OLD_CLI = runner.Result(0, "codex-cli 0.150.0\n", "")


def test_a_usable_cli_is_cli_mode(fake_home, fake_runner):
    fake_runner.responses[("codex", "--version")] = runner.Result(0, "codex-cli 0.162.1\n", "")
    assert codex.mode() == "cli" and codex.program() == "codex" and codex.cli_problem() is None


def test_the_extension_alone_is_extension_mode(codex_ext):
    assert codex.mode() == "extension" and codex.program() == str(codex_ext)
    assert codex.cli_problem() is None


def test_a_too_old_cli_next_to_a_usable_extension_uses_the_extension(codex_ext, fake_runner):
    fake_runner.missing.discard("codex")
    fake_runner.responses[("codex", "--version")] = OLD_CLI
    assert codex.mode() == "extension" and codex.program() == str(codex_ext)
    assert codex.unavailable() is None
    assert "0.150.0" in codex.cli_problem()


def test_a_broken_cli_without_an_extension_keeps_todays_reason(fake_home, fake_runner):
    fake_runner.responses[("codex", "--version")] = OLD_CLI
    assert codex.mode() is None
    assert codex.unavailable() == "codex 0.150.0 is too old; loadout needs 0.161 or newer (update it: mise upgrade codex)"


def test_neither_is_no_mode(fake_home, fake_runner):
    fake_runner.missing.add("codex")
    assert codex.mode() is None and codex.unavailable() == codex.NOT_FOUND


def test_plugin_commands_run_with_the_extensions_codex(codex_ext, fake_runner):
    codex.installed_plugins()
    codex.marketplaces()
    assert [str(codex_ext), "plugin", "list", "--json"] in fake_runner.calls
    assert [str(codex_ext), "plugin", "marketplace", "list", "--json"] in fake_runner.calls
    assert not any(c[0] == "codex" for c in fake_runner.calls)


def test_undo_of_a_plugin_runs_with_the_current_modes_codex(codex_ext, fake_runner):
    bk = backup.Backup(description="test")
    bk.record_command("codex plugin x@m", ["codex", "plugin", "remove", "x@m"])
    lines, ok, _ = backup.restore(bk.root)
    assert [str(codex_ext), "plugin", "remove", "x@m"] in fake_runner.calls
    assert ["codex", "plugin", "remove", "x@m"] not in fake_runner.calls
    assert ok, lines


def test_undo_recorded_with_the_extension_runs_the_cli_once_it_is_installed(codex_ext, fake_runner):
    bk = backup.Backup(description="test")
    bk.record_command("codex plugin x@m", ["codex", "plugin", "remove", "x@m"])
    fake_runner.missing.discard("codex")
    fake_runner.responses[("codex", "--version")] = runner.Result(0, "codex-cli 0.163.0\n", "")
    backup.restore(bk.root)
    assert ["codex", "plugin", "remove", "x@m"] in fake_runner.calls


def test_no_mode_runs_plain_codex(fake_home, fake_runner):
    fake_runner.missing.add("codex")
    assert codex.program() == "codex"


def test_the_unusable_text_names_both(codex_ext):
    assert codex.CLI_UNUSABLE.format(why="codex 0.150.0 is too old") == (
        "codex 0.150.0 is too old; loadout uses VS Code's Codex extension's codex instead")


def test_one_install_run_asks_which_codex_once(fake_home, fake_runner):
    fake_runner.responses[("codex", "--version")] = runner.Result(0, "codex-cli 0.162.1\n", "")
    routes = {"o/a": ["p1", "p2"], "o/b": ["p3"]}
    codex._install_routes(routes, None, refresh=True, say=lambda line: None, listed=set())
    assert sum(1 for c in fake_runner.calls if c[1:] == ["--version"]) == 1


def test_a_windows_codex_in_wsl_next_to_a_usable_extension_is_extension_mode(codex_ext, fake_runner, monkeypatch):
    from loadout import wsl
    fake_runner.missing.discard("codex")
    fake_runner.paths["codex"] = "/mnt/c/Users/x/AppData/Roaming/npm/codex"
    monkeypatch.setattr(wsl, "detect", lambda: object())
    monkeypatch.setattr(wsl, "is_windows_program", lambda name: True)
    assert "Windows" in codex.cli_problem()
    assert codex.mode() == "extension" and codex.program() == str(codex_ext)
