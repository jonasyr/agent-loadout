"""Codex set up for VS Code's Codex extension when no Codex CLI is installed (spec Part 2)."""
import pytest

from loadout import codex, runner, targets


@pytest.fixture
def ext_only(codex_ext):
    return codex_ext


def test_a_new_enough_extension_makes_codex_available(ext_only):
    ext, why = codex.extension_state()
    assert ext is not None and ext.binary == ext_only and why is None
    assert codex.unavailable() is None
    assert codex.program() == str(ext_only)


def test_an_old_extension_codex_is_not_used_and_says_update(ext_only, fake_runner):
    fake_runner.responses[(str(ext_only), "--version")] = runner.Result(0, "codex-cli 0.145.0-alpha.27\n", "")
    assert codex.extension_state()[0] is None
    assert "0.145.0" in codex.unavailable() and "update" in codex.unavailable()


def test_no_extension_keeps_todays_reason(fake_home, fake_runner):
    fake_runner.missing.add("codex")
    assert codex.unavailable() == "codex not found on PATH"


def test_a_cli_on_path_changes_nothing(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(codex, "extension_state", lambda: pytest.fail("looked for the extension"))
    fake_runner.responses[("codex", "--version")] = runner.Result(0, "codex-cli 0.162.1\n", "")
    assert codex.unavailable() is None and codex.program() == "codex"


def test_mcp_list_runs_the_extensions_codex(ext_only, fake_runner):
    codex.mcp_names()
    assert [str(ext_only), "mcp", "list", "--json"] in fake_runner.calls


def test_plugins_install_with_the_extensions_codex(ext_only, fake_runner):
    from loadout.backup import Backup
    codex.apply_plugins(Backup(description="test"))
    plugin_calls = [c for c in fake_runner.calls if c[1:2] == ["plugin"]]
    assert plugin_calls and all(c[0] == str(ext_only) for c in plugin_calls)


def test_still_to_do_names_the_extensions_hooks_icon(ext_only, monkeypatch):
    monkeypatch.setattr(codex, "hooks_status", lambda remember=False: "untrusted")
    steps = codex.open_steps()
    assert steps[0] == codex.HOOKS_EXTENSION and "Codex CLI" not in steps[0]



def test_a_missing_cli_next_to_the_extension_is_no_binary_row(ext_only):
    from loadout import check
    assert not [r for r in check._binaries() if r.name == "binary codex"]  # the `Codex CLI` row says it is optional


def test_check_still_fails_without_cli_and_extension(fake_home, fake_runner, monkeypatch):
    from loadout import check
    monkeypatch.setattr(targets, "OVERRIDE", {"claude": False, "codex": True})
    fake_runner.missing.add("codex")
    (row,) = [r for r in check._binaries() if r.name == "binary codex"]
    assert row.severity == "error"


@pytest.mark.parametrize("problem, wanted, unwanted", [
    ("codex not found on PATH", "loadout bootstrap --install", "mise use -g codex"),
    (codex.EXT_OLD.format(version="0.145.0"), "update VS Code's Codex extension", "mise use -g codex"),
    (codex.EXT_NOVERSION, "update VS Code's Codex extension", "mise use -g codex"),
    ("the codex on PATH is the Windows one (/mnt/c/x/codex.exe): run bootstrap with --install to install Codex in WSL, "
     "or set loadout up on Windows (docs/how-to/wsl.md#codex)", "installs Codex in WSL", "mise"),
    ("CODEX_HOME points into Windows (/mnt/c/h): both sides would read loadout's WSL commands; unset it in WSL, or "
     "run bootstrap with --codex-side wsl to set it up anyway (docs/how-to/wsl.md#codex)", "unset CODEX_HOME", "mise"),
    ("codex 0.100.0 is too old; loadout needs 0.161 or newer (update it: mise upgrade codex)", "mise upgrade codex",
     "mise use -g codex"),
    ("could not read codex --version", "mise upgrade codex", "mise use -g codex"),
    ("something new", "loadout configure set target codex off", "VS Code"),
])
def test_each_cause_of_the_codex_row_gets_its_own_fix(fake_home, fake_runner, monkeypatch, problem, wanted, unwanted):
    monkeypatch.setattr(codex, "enabled", lambda: True)
    monkeypatch.setattr(codex, "unavailable", lambda *a, **k: problem)
    (r,) = [r for r in codex.checks() if r.name == "Codex"]
    assert not r.ok and r.detail == problem and wanted in r.fix and unwanted not in r.fix, r.fix
