"""VS Code's Codex extension loads plugins installed with its own codex: loadout installs them (spec decision 1)."""
import pytest

from loadout import apply, backup, codex, runner

OWN = "loadout@agent-loadout"


@pytest.fixture
def spaced_ext(codex_ext, fake_home, fake_runner):
    """The extension starts a codex whose path holds a space (chatgpt.cliExecutable)."""
    import json
    import sys
    from loadout import vscode
    own = fake_home / "Application Support" / ("codex.exe" if sys.platform == "win32" else "codex")
    own.parent.mkdir(parents=True)
    own.write_text("x")
    own.chmod(0o755)
    user = vscode._user_dir(fake_home, sys.platform)
    user.mkdir(parents=True, exist_ok=True)
    (user / "settings.json").write_text(json.dumps({"chatgpt.cliExecutable": str(own)}))
    fake_runner.responses[(str(own), "--version")] = runner.Result(0, "codex-cli 0.162.1\n", "")
    return own


def _plugin_calls(fake_runner):
    return [c for c in fake_runner.calls if c[1:2] == ["plugin"]]


def test_extension_mode_adds_marketplaces_and_plugins_with_the_extensions_codex(codex_ext, fake_runner):
    exe = str(codex_ext)
    bk = backup.Backup(description="test")
    codex.apply_plugins(bk)
    calls = _plugin_calls(fake_runner)
    assert any(c[:4] == [exe, "plugin", "marketplace", "add"] for c in calls)
    assert all(c[0] == exe for c in calls)
    assert not any(c[0] == "codex" for c in fake_runner.calls)


def test_a_path_with_a_space_is_one_argument(spaced_ext, fake_runner):
    codex.apply_plugins(backup.Backup(description="test"))
    calls = _plugin_calls(fake_runner)
    assert calls and all(c[0] == str(spaced_ext) and " " in c[0] for c in calls)


def test_an_extension_codex_without_a_plugin_command_skips_plugins_once(codex_ext, fake_runner):
    fake_runner.responses[(str(codex_ext), "plugin")] = runner.Result(
        2, "", "error: unrecognized subcommand 'plugin'\n")
    lines = codex.apply_plugins(backup.Backup(description="test"))
    assert lines == [codex.PLUGINS_OLD]
    adds = [c for c in fake_runner.calls if c[1:4] == ["plugin", "marketplace", "add"]]
    assert len(adds) == 1 and not any(c[1:3] == ["plugin", "add"] for c in fake_runner.calls)


def test_the_codex_step_plans_plugins_in_extension_mode(codex_ext, fake_runner):
    step = apply.codex_step(object(), refresh_plugins=True, auto=False, keep=False, skip_unchanged=True,
                            dry=True, on=True)
    assert not any("loads none" in line for line in step.lines)
    assert any(line.startswith("marketplace ") and "to refresh" in line for line in step.lines)


def test_extension_summary_names_plugins_and_skills_only_when_linked(codex_ext):
    assert apply._codex_summary(["rules: ok"], plugins=True) == (
        "rules, plugins and MCP servers set up for VS Code's Codex extension")
    assert apply._codex_summary(["linked x"], plugins=True).startswith("rules, plugins, MCP servers and skills set up")


def test_check_lists_plugin_rows_in_extension_mode(codex_ext, fake_runner):
    exe = str(codex_ext)
    fake_runner.responses[(exe, "plugin", "marketplace", "list")] = runner.Result(0, '{"marketplaces": []}', "")
    fake_runner.responses[(exe, "plugin", "list")] = runner.Result(0, '{"installed": [], "available": []}', "")
    rows = {r.name: r for r in codex.checks()}
    assert rows["Codex plugin"].ok is False and rows["Codex plugin"].detail == "loadout plugin not installed in Codex"
    assert "Codex plugins missing" in rows
    assert not any("loads none" in (r.detail + r.fix) for r in rows.values())


def test_an_old_extension_codex_counts_as_a_problem_in_the_summary(codex_ext):
    assert apply._codex_summary(["rules: ok", codex.PLUGINS_OLD]).startswith("1 problem")


def test_the_loadout_plugin_is_installed_and_its_undo_recorded(codex_ext, fake_runner):
    import json
    exe = str(codex_ext)
    fake_runner.responses[(exe, "plugin", "list")] = runner.Result(0, '{"installed": [], "available": []}', "")
    fake_runner.responses[(exe, "plugin", "marketplace", "add", "jonasyr/agent-loadout")] = runner.Result(
        0, '{"marketplaceName": "agent-loadout"}', "")
    bk = backup.Backup(description="test")
    codex.apply_plugins(bk)
    assert [exe, "plugin", "add", OWN, "--json"] in fake_runner.calls
    undo = [e["undo"]["run"] for e in json.loads((bk.root / "manifest.json").read_text())["steps"]
            if "run" in e.get("undo", {})]
    assert ["codex", "plugin", "remove", OWN] in undo and ["codex", "plugin", "marketplace", "remove",
                                                           "agent-loadout"] in undo


def test_check_names_a_server_twice_in_extension_mode(codex_ext, monkeypatch):
    import test_codex_server_twice as twice
    from loadout import paths
    twice._plugin()
    (paths.codex_home() / "config.toml").write_text(twice.USER_TABLE)
    monkeypatch.setattr(codex, "installed_plugins", lambda: twice.INSTALLED)
    rows = {r.name: r for r in codex.checks()}
    assert rows["Codex MCP codebase-memory-mcp"].detail == twice.DETAIL


def test_a_profile_with_an_old_extension_codex_says_update_the_extension(codex_ext, fake_runner, monkeypatch):
    from loadout import codex_project, profiles
    fake_runner.responses[(str(codex_ext), "plugin")] = runner.Result(
        2, "", "error: unrecognized subcommand 'plugin'\n")
    prof = profiles.load_profile("thesis")
    lines = codex_project.plugins(prof, dry_run=False)
    assert codex.PLUGINS_OLD in lines and not any("run loadout profile again" in l for l in lines)
    assert codex_project.failed_plugins(prof, lines) == frozenset(codex_project._wanted(prof)[1])
