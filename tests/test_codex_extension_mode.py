"""Codex set up for VS Code's Codex extension when no Codex CLI is installed (spec Part 2)."""
import pytest

from conftest import host_codex_bin

from loadout import codex, runner, targets


@pytest.fixture
def ext_only(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(targets, "OVERRIDE", {"claude": False, "codex": True})
    fake_runner.missing.add("codex")
    folder = fake_home / ".vscode" / "extensions" / "openai.chatgpt-26.715.61943-linux-x64"
    binary = folder / host_codex_bin()
    binary.parent.mkdir(parents=True)
    binary.write_text("bin")
    binary.chmod(0o755)
    fake_runner.responses[(str(binary), "--version")] = runner.Result(0, "codex-cli 0.162.1\n", "")
    return binary


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


def test_plugins_are_skipped_with_one_line(ext_only, fake_runner):
    lines = codex.apply_plugins(None)
    assert lines == [codex.PLUGINS_EXTENSION]
    assert not any(c[1:2] == ["plugin"] for c in fake_runner.calls)


def test_still_to_do_names_the_cli_for_hooks(ext_only, monkeypatch):
    monkeypatch.setattr(codex, "hooks_status", lambda remember=False: "untrusted")
    steps = codex.open_steps()
    assert steps[0] == codex.HOOKS_NO_CLI and "Codex CLI" in steps[0] and "loadout bootstrap --install" in steps[0]
