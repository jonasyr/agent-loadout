"""bootstrap: the Codex CLI is recommended, not required, next to VS Code's Codex extension (spec Part 2)."""
import pytest

from loadout import bootstrap, codex


@pytest.fixture
def ext(fake_runner, monkeypatch):
    fake_runner.missing.add("codex")  # never this machine's real codex
    monkeypatch.setattr(codex, "extension_state", lambda: (object(), None))
    monkeypatch.setattr(bootstrap, "missing_binary", lambda name: name == "codex")


def test_question_text_is_the_specs():
    assert "Install the Codex CLI too (optional, for codex in a terminal)? [y/N]" in bootstrap.CODEX_CLI_QUESTION


@pytest.mark.parametrize("answer,skip", [("", True), ("y", False), ("yes", False), ("n", True), ("no", True)])
def test_in_a_terminal_it_asks_and_respects_the_answer(ext, answer, skip):
    asked = []
    result = bootstrap.codex_cli_choice(True, lambda q: asked.append(q) or answer, interactive=True, wanted=True)
    assert asked == [bootstrap.CODEX_CLI_QUESTION]
    assert result == ((bootstrap.CODEX_CLI_DECLINED, True) if skip else (bootstrap.CODEX_CLI_WHY, False))


def test_without_a_terminal_install_installs_and_says_why(ext):
    assert bootstrap.codex_cli_choice(True, lambda q: pytest.fail("asked"), interactive=False, wanted=True) == (
        bootstrap.CODEX_CLI_WHY, False)


def test_without_codex_cli_flag_skips_without_asking(ext):
    assert bootstrap.codex_cli_choice(True, lambda q: pytest.fail("asked"), interactive=True, wanted=False) == (
        bootstrap.CODEX_CLI_DECLINED, True)


def test_no_extension_or_a_cli_already_there_no_offer(fake_runner, monkeypatch):
    fake_runner.missing.add("codex")
    monkeypatch.setattr(codex, "extension_state", lambda: (None, None))
    monkeypatch.setattr(bootstrap, "missing_binary", lambda name: True)
    assert bootstrap.codex_cli_choice(True, lambda q: pytest.fail("asked"), True, True) == (None, False)
    fake_runner.missing.discard("codex")
    monkeypatch.setattr(codex, "extension_state", lambda: (object(), None))
    monkeypatch.setattr(bootstrap, "missing_binary", lambda name: False)
    assert bootstrap.codex_cli_choice(True, lambda q: pytest.fail("asked"), True, True) == (None, False)


def test_without_install_no_question_and_the_missing_line_says_optional(ext, fake_home, fake_runner, monkeypatch):
    from loadout import targets
    monkeypatch.setattr(targets, "OVERRIDE", {"claude": False, "codex": True})
    assert bootstrap.codex_cli_choice(False, lambda q: pytest.fail("asked"), True, True) == (None, False)
    notes = []
    bootstrap.check_prereqs(False, lambda q: "", notes=notes, recommended=frozenset({"codex"}))
    line = next(n for n in notes if "codex" in n)
    assert "(required)" not in line and "optional" in line


def test_the_flag_parses(fake_home):
    from loadout import commands  # noqa: F401
    from loadout.__main__ import build_parser
    assert build_parser().parse_args(["bootstrap", "--without-codex-cli"]).without_codex_cli is True


def test_extension_only_declined_is_a_clean_codex_setup(fake_home, fake_runner, monkeypatch, capsys):
    """The spec's promise: an extension-only user who says no gets Codex set up and the gaps listed, no failure."""
    from conftest import host_codex_bin
    from loadout import out, paths, runner
    (fake_home / ".config/loadout/personal").mkdir(parents=True)
    codex.set_enabled(True)
    fake_runner.missing.add("codex")
    binary = fake_home / ".vscode" / "extensions" / "openai.chatgpt-26.715.61943-linux-x64" / host_codex_bin()
    binary.parent.mkdir(parents=True)
    binary.write_text("bin")
    binary.chmod(0o755)
    fake_runner.responses[(str(binary), "--version")] = runner.Result(0, "codex-cli 0.162.1\n", "")
    monkeypatch.setattr(out, "VERBOSE", False)
    bootstrap.bootstrap(install=True, yes=True, plugins=False, adopt_step=False, ask=lambda q: pytest.fail("asked"),
                        interactive=False, agents="codex", codex_cli=False)
    text = capsys.readouterr().out
    assert bootstrap.CODEX_CLI_DECLINED in text
    assert "Codex step skipped" not in text and "codex not found on PATH" not in text
    assert codex.START in (paths.codex_home() / "AGENTS.md").read_text(encoding="utf-8")  # the rules block was written
    assert codex.HOOKS_EXTENSION in text  # Still to do names the extension's hooks icon
    assert not any(c[:1] == ["mise"] and "codex" in " ".join(c) for c in fake_runner.calls)  # the CLI was not installed
    assert "[FAIL] binary codex" not in text
