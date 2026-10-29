"""bootstrap: the Claude Code CLI next to VS Code's Claude Code extension is decided like the Codex CLI next to its
extension (spec 2026-10-29 G3, tour finding E1/E2)."""
import pytest

from conftest import host_claude_bin
from loadout import bootstrap, check, out, runner, vscode


def _ext(home, version="2.1.10"):
    exe = home / ".vscode" / "extensions" / f"anthropic.claude-code-{version}" / host_claude_bin()
    exe.parent.mkdir(parents=True)
    exe.write_text("#!/bin/sh\necho ran\n")
    exe.chmod(0o755)
    return exe


@pytest.fixture
def bundled(fake_home, fake_runner, monkeypatch):
    fake_runner.missing.add("claude")  # never this machine's real claude
    monkeypatch.setattr(runner, "FALLBACK", {})
    return _ext(fake_home)


def test_question_text():
    assert "Install the Claude Code CLI too (optional, for claude in a terminal)? [y/N]" in bootstrap.CLAUDE_CLI_QUESTION


@pytest.mark.parametrize("answer,skip", [("", True), ("y", False), ("yes", False), ("n", True)])
def test_in_a_terminal_it_asks_default_no(bundled, answer, skip):
    asked = []
    result = bootstrap.claude_cli_choice(True, lambda q: asked.append(q) or answer, True, True, bundled)
    assert asked == [bootstrap.CLAUDE_CLI_QUESTION]
    assert result == ((bootstrap.CLAUDE_CLI_DECLINED, True) if skip else (bootstrap.CLAUDE_CLI_WHY, False))


def test_yes_or_no_terminal_installs_like_codex(bundled):
    assert bootstrap.claude_cli_choice(True, lambda q: pytest.fail("asked"), False, True, bundled) == (
        bootstrap.CLAUDE_CLI_WHY, False)


def test_without_claude_cli_skips_without_asking(bundled):
    assert bootstrap.claude_cli_choice(True, lambda q: pytest.fail("asked"), True, False, bundled) == (
        bootstrap.CLAUDE_CLI_DECLINED, True)


def test_no_extension_no_install_or_a_cli_there_no_offer(fake_runner, bundled):
    assert bootstrap.claude_cli_choice(True, lambda q: pytest.fail("asked"), True, True, None) == (None, False)
    assert bootstrap.claude_cli_choice(False, lambda q: pytest.fail("asked"), True, True, bundled) == (None, False)
    fake_runner.missing.discard("claude")
    assert bootstrap.claude_cli_choice(True, lambda q: pytest.fail("asked"), True, True, bundled) == (None, False)


def _run(**kw):
    args = dict(install=True, yes=True, plugins=False, adopt_step=False, ask=lambda q: "", interactive=False,
                agents="claude", personal="new")
    args.update(kw)
    return bootstrap.bootstrap(**args)


def _claude_installs(fake_runner):
    return [c for c in fake_runner.calls if "claude.ai/install" in " ".join(c)]  # install.sh, or install.ps1 on Windows


def test_without_claude_cli_flag_skips_the_install(bundled, fake_runner, monkeypatch, capsys):
    monkeypatch.setattr(out, "VERBOSE", False)
    _run(claude_cli=False)
    text = capsys.readouterr().out
    assert not _claude_installs(fake_runner)
    assert bootstrap.CLAUDE_CLI_DECLINED in text
    assert "open VS Code's Claude Code extension" in text and "run `claude`" not in text


def test_terminal_answer_no_skips_the_install(bundled, fake_runner, monkeypatch, capsys):
    monkeypatch.setattr(out, "VERBOSE", False)
    _run(yes=False, interactive=True, ask=lambda q: "")
    assert not _claude_installs(fake_runner)


def test_no_terminal_installs(bundled, fake_runner, monkeypatch):
    monkeypatch.setattr(out, "VERBOSE", False)
    _run()
    assert _claude_installs(fake_runner)


def test_without_claude_cli_no_effect_says_so(fake_home, fake_runner, monkeypatch, capsys):
    monkeypatch.setattr(out, "VERBOSE", False)
    _run(claude_cli=False, install=False)
    assert "--without-claude-cli: not used" in capsys.readouterr().out


def _after_next(text, start="Next:"):
    lines = text.splitlines()
    i = next(i for i, line in enumerate(lines) if line.startswith(start))
    return lines[i], lines[i + 1]


EXT_LINE = "Or open VS Code's Claude Code extension (reload the window if it is open)."


def test_cli_present_no_question_next_names_extension(fake_home, fake_runner, monkeypatch, capsys):
    monkeypatch.setattr(out, "VERBOSE", False)
    _ext(fake_home)
    _run(ask=lambda q: pytest.fail(f"asked: {q}"))  # claude on PATH: no Claude Code CLI question
    first, second = _after_next(capsys.readouterr().out)
    assert "`claude`" in first and "extension" not in first
    assert second == EXT_LINE


def test_next_second_line_names_extensions_next_to_their_cli(fake_home, fake_runner, monkeypatch, capsys):
    monkeypatch.setattr(out, "VERBOSE", False)
    _ext(fake_home)
    _run(install=False)
    first, second = _after_next(capsys.readouterr().out)
    assert first.startswith("Next: run `claude` ") and second == EXT_LINE


def test_next_second_line_verbose_variants(fake_home, fake_runner, monkeypatch, capsys):
    monkeypatch.setattr(out, "VERBOSE", True)
    _ext(fake_home)
    _run(install=False)
    first, second = _after_next(capsys.readouterr().out, start=("Then start ", "Restart "))
    assert first in ("Then start Claude Code.", "Restart Claude Code to load plugins and rules.")
    assert second == EXT_LINE


def test_check_row_is_ok_and_optional(bundled):
    rows = check._binaries()
    assert not any(r.name == "binary claude" for r in rows)
    (row,) = [r for r in rows if r.name == "Claude Code CLI"]
    assert row.ok and "optional" in row.detail


def test_the_flag_parses(fake_home):
    from loadout import commands  # noqa: F401
    from loadout.__main__ import build_parser
    assert build_parser().parse_args(["bootstrap", "--without-claude-cli"]).without_claude_cli is True


def test_ignored_cli_flag_is_said_once(bundled, fake_runner, monkeypatch, capsys):
    monkeypatch.setattr(out, "VERBOSE", False)
    fake_runner.missing.discard("claude")  # a claude on PATH next to the extension
    _run(claude_cli=False, install=False)
    text = capsys.readouterr().out
    assert text.count("--without-claude-cli: not used") == 1
    assert "given while a Claude Code CLI is on PATH" not in text


def test_ignored_codex_cli_flag_is_said_once(bundled, fake_runner, monkeypatch, capsys):
    monkeypatch.setattr(out, "VERBOSE", False)
    fake_runner.missing.discard("claude")
    _run(codex_cli=False, install=False, agents="claude,codex")
    text = capsys.readouterr().out
    assert text.count("--without-codex-cli: not used") == 1
    assert "given while a Codex CLI is on PATH" not in text
