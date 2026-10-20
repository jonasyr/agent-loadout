"""Final-review fix pass A: Windows entry script, PATH, helpers, catalog and CI details."""
import json
import re

from loadout import paths

PS1 = paths.kit_root() / "bootstrap.ps1"


def test_ps1_warning_names_the_full_wsl_url():
    assert ("Write-Warning 'Native Windows is experimental and not recommended. WSL 2 is the recommended setup on "
            "Windows: https://github.com/jonasyr/agent-loadout/blob/main/docs/how-to/wsl.md'") in PS1.read_text()


def test_ps1_never_exits_when_run_as_a_scriptblock():
    """The one-liner runs the script as a scriptblock: `exit` there closes the user's PowerShell window."""
    text = PS1.read_text()
    assert "$asFile = [bool]$PSCommandPath" in text
    code = [l for l in text.splitlines() if not l.lstrip().startswith("#")]
    for line in code:
        if re.search(r"\bexit\b", line):
            assert "if ($asFile)" in line, line
    assert not any("Write-Error" in l for l in code)  # under 'Stop' it throws instead of returning
    assert "$global:LASTEXITCODE = $code" in text
    assert "Set-Location" not in text  # Push/Pop-Location: the user's folder is left as it was


def _bootstrap_end(monkeypatch, fake_runner, path_changed, todo):
    from loadout import bootstrap as b
    monkeypatch.setattr(b.check, "run_checks", lambda: [])
    monkeypatch.setattr(b, "setup_path", lambda bk=None: ((["added x to PATH"], True) if path_changed else ([], False)))
    monkeypatch.setattr(b, "still_to_do", lambda key, **kw: todo)
    b.bootstrap(False, True, False, False, lambda q: "", interactive=False)


def test_new_terminal_hint_comes_before_the_still_to_do_list(fake_home, fake_runner, monkeypatch, capsys):
    _bootstrap_end(monkeypatch, fake_runner, True, ["log in to Claude Code: claude"])
    out = capsys.readouterr().out
    hint = out.index("Open a new terminal so the new PATH applies.")
    assert hint < out.index("Still to do (in a new terminal):") < out.index("log in to Claude Code")
    assert "\nStill to do:" not in out


def test_new_terminal_hint_without_a_list(fake_home, fake_runner, monkeypatch, capsys):
    _bootstrap_end(monkeypatch, fake_runner, True, [])
    out = capsys.readouterr().out
    assert "Open a new terminal so the new PATH applies." in out and "Still to do" not in out


def test_unchanged_path_keeps_the_plain_list_and_restart_line(fake_home, fake_runner, monkeypatch, capsys):
    _bootstrap_end(monkeypatch, fake_runner, False, ["log in to Claude Code: claude"])
    out = capsys.readouterr().out
    assert "\nStill to do:\n" in out and "new terminal" not in out
    assert out.index("Still to do:") < out.index("Restart Claude Code to load plugins and rules.")


def test_dependant_of_a_failed_install_gets_exactly_one_line(fake_home, fake_runner, monkeypatch, capsys):
    from loadout import bootstrap as b, catalog, runner
    entries = [{"id": "node", "kind": "binary", "status": "core", "required": True, "needs": ["mise"],
                "install": {"posix": [["install-node"]], "windows": [["install-node"]]}},
               {"id": "mise", "kind": "binary", "status": "core", "helper": True, "needs": [],
                "install": {"posix": [["install-mise"]], "windows": [["install-mise"]]}}]
    monkeypatch.setattr(catalog, "binaries", lambda: entries)
    fake_runner.missing.update({"node", "mise", "gh"})
    fake_runner.responses[("install-mise",)] = runner.Result(1, "", "boom")
    assert b.check_prereqs(True, lambda q: "") == ["node"]
    node_lines = [l for l in capsys.readouterr().out.splitlines() if "node" in l]
    assert node_lines == ["missing node: not installed because mise failed to install"]


def test_uv_installers_never_edit_shell_profiles():
    uv = next(e for e in json.loads((paths.kit_root() / "catalog.json").read_text())["entries"] if e["id"] == "uv")
    assert uv["install"]["posix"] == [["sh", "-c", "curl -LsSf https://astral.sh/uv/install.sh | UV_NO_MODIFY_PATH=1 sh"]]
    assert uv["install"]["windows"][0][-1] == "$env:UV_NO_MODIFY_PATH='1'; irm https://astral.sh/uv/install.ps1 | iex"


def test_helpers_are_not_offered_as_updates(fake_home, fake_runner, monkeypatch, capsys):
    from loadout import catalog, maintenance, versions
    entries = [{"id": "mise", "kind": "binary", "helper": True, "version": {"cmd": ["mise", "--version"]}},
               {"id": "uv", "kind": "binary", "version": {"cmd": ["uv", "--version"]}}]
    monkeypatch.setattr(catalog, "binaries", lambda: entries)
    monkeypatch.setattr(versions, "local_version", lambda e: (1, 0))
    monkeypatch.setattr(versions, "latest_version", lambda e: (2, 0))
    assert [e["id"] for e, _, _ in maintenance.find_outdated()] == ["uv"]
    from loadout import bootstrap
    monkeypatch.setattr(bootstrap, "missing_tools", lambda *a, **k: [])
    maintenance.update(False, lambda q: "n")
    out = capsys.readouterr().out
    assert "uv: 1.0 -> 2.0" in out and "mise:" not in out


def test_fresh_machine_workflow_fails_on_fail_lines_and_never_interpolates_the_branch():
    text = (paths.kit_root() / ".github/workflows/fresh-machine.yml").read_text()
    assert "! printf" not in text  # `! cmd` never fails a bash -e step
    assert text.count("""if printf '%s\\n' "$out" | grep -qF '[FAIL]'; then exit 1; fi""") == 2
    for path in ("bin/loadout", "cli/loadout/**", "settings.base.json", "plugins/loadout/hooks/**"):
        assert f'"{path}"' in text, path
    for module in sorted((paths.kit_root() / "cli/loadout").glob("*.py")):
        assert '"cli/loadout/**"' in text or f'"cli/loadout/{module.name}"' in text, module.name
    assert "su -w LOADOUT_REPO_URL,LOADOUT_REF - oneliner -c '" in text
    assert "LOADOUT_REF=$REF" not in text
    fork_guard = "if: github.event_name != 'pull_request' || github.event.pull_request.head.repo.full_name == github.repository"
    assert text.count(fork_guard) == 2
