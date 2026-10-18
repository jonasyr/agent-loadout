"""Final-review findings for VS Code PR 2 (extension mode), each pinned by a test that failed first."""
import pytest

from conftest import host_codex_bin

from loadout import bootstrap, check, codex, maintenance, out, paths, runner, targets, wsl


@pytest.fixture
def ext_only(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(targets, "OVERRIDE", {"claude": False, "codex": True})
    fake_runner.missing.add("codex")
    binary = fake_home / ".vscode" / "extensions" / "openai.chatgpt-26.715.61943-linux-x64" / host_codex_bin()
    binary.parent.mkdir(parents=True)
    binary.write_text("bin")
    binary.chmod(0o755)
    fake_runner.responses[(str(binary), "--version")] = runner.Result(0, "codex-cli 0.162.1\n", "")
    return binary


def test_check_has_no_failure_in_extension_mode(ext_only):
    from loadout.backup import Backup
    codex.apply_instructions(Backup(description="test"))  # what bootstrap writes; a missing block fails for anyone
    rows = codex.checks()
    assert not [r for r in rows if not r.ok and r.severity == "error"], [r.name for r in rows if not r.ok]


def test_extension_only_bootstrap_has_no_codex_failure(ext_only, capsys, monkeypatch):
    (paths.home() / ".config/loadout/personal").mkdir(parents=True)
    monkeypatch.setattr(out, "VERBOSE", False)
    bootstrap.bootstrap(install=True, yes=True, plugins=False, adopt_step=False, ask=lambda q: "", interactive=False,
                        agents="codex", codex_cli=False)
    text = capsys.readouterr().out
    assert "[FAIL] Codex" not in text and "Next: open VS Code's Codex extension" in text


def test_a_windows_shim_in_wsl_gets_no_cli_offer(ext_only, fake_runner, monkeypatch):
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)
    fake_runner.missing.discard("codex")
    fake_runner.paths["codex"] = "/mnt/c/Users/a/AppData/Roaming/npm/codex"
    assert bootstrap.codex_cli_choice(True, lambda q: pytest.fail("asked"), True, False) == (None, False)
    assert bootstrap.codex_recommended({"codex": True}, None) == frozenset()


def test_extension_mode_keeps_the_shared_codex_home_guard(ext_only, monkeypatch):
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)
    monkeypatch.setenv("CODEX_HOME", "/mnt/c/Users/a/.codex")
    assert "CODEX_HOME points into Windows" in codex.unavailable()


def test_no_extension_lookup_when_the_cli_is_there(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(codex, "extension_state", lambda: pytest.fail("looked for the extension"))
    assert bootstrap.codex_recommended({"codex": True}, None) == frozenset()


def test_the_bundled_version_is_asked_once_per_process(ext_only, fake_runner):
    codex.extension_state()
    codex.extension_state()
    codex.program()
    assert sum(1 for c in fake_runner.calls if c == [str(ext_only), "--version"]) == 1


def test_update_does_not_offer_a_plugin_refresh_in_extension_mode(ext_only, capsys):
    maintenance._update_plugins(False, True, False, lambda q: pytest.fail("asked"))
    assert codex.PLUGINS_EXTENSION in capsys.readouterr().out


def test_hints_name_the_extension_not_a_bare_codex(ext_only, monkeypatch):
    monkeypatch.setattr(codex, "hooks_status", lambda remember=False: "untrusted")
    monkeypatch.setattr(codex, "logins_needed", lambda: ["notion"])
    rows = {r.name: r for r in codex.checks()}
    assert "Codex CLI" in rows["Codex hooks"].fix and "start codex" not in rows["Codex hooks"].fix
    assert "VS Code" in rows["Codex logins"].fix


def test_an_extension_codex_without_a_version_names_the_extension(ext_only, fake_runner):
    fake_runner.responses[(str(ext_only), "--version")] = runner.Result(1, "", "boom")
    assert "VS Code's Codex extension" in codex.unavailable()


def test_without_codex_cli_says_when_it_was_not_used(fake_home, fake_runner, capsys, monkeypatch):
    (fake_home / ".config/loadout/personal").mkdir(parents=True)
    monkeypatch.setattr(out, "VERBOSE", False)
    bootstrap.bootstrap(install=False, yes=True, plugins=False, adopt_step=False, ask=lambda q: "", interactive=False,
                        agents="claude", codex_cli=False)
    assert "--without-codex-cli: not used" in capsys.readouterr().out
