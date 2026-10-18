"""No claude on PATH: loadout runs the Claude Code extension's bundled binary for its own commands (spec Part 3.3)."""
import os
import sys

import pytest

from conftest import host_claude_bin
from loadout import __main__ as cli, bootstrap, check, runner, vscode


def _ext(home, version):
    exe = home / ".vscode" / "extensions" / f"anthropic.claude-code-{version}" / host_claude_bin()
    exe.parent.mkdir(parents=True)
    exe.write_text("#!/bin/sh\necho ran\n")
    exe.chmod(0o755)
    return exe


def test_newest_bundled_claude_wins(fake_home, fake_runner):
    _ext(fake_home, "2.1.9")
    new = _ext(fake_home, "2.1.10")
    assert vscode.bundled_claude() == new


def test_use_bundled_claude_only_without_a_claude_on_path(fake_home, fake_runner):
    exe = _ext(fake_home, "2.1.10")
    assert vscode.use_bundled_claude(on=True) is None and "claude" not in runner.FALLBACK
    fake_runner.missing.add("claude")
    assert vscode.use_bundled_claude(on=True) == exe and runner.FALLBACK["claude"] == str(exe)
    assert vscode.use_bundled_claude(on=False) is None and "claude" not in runner.FALLBACK


def test_claude_off_reads_no_extension(fake_home, fake_runner, monkeypatch):
    fake_runner.missing.add("claude")
    monkeypatch.setattr(vscode, "extensions", lambda *a, **k: pytest.fail("read"))
    assert vscode.use_bundled_claude(on=False) is None


@pytest.mark.skipif(os.name == "nt", reason="a POSIX script stands in for the binary")
def test_run_uses_the_fallback(tmp_path, monkeypatch):
    exe = tmp_path / "bundled"
    exe.write_text("#!/bin/sh\necho ran \"$@\"\n")
    exe.chmod(0o755)
    monkeypatch.setattr(runner, "FALLBACK", {"loadout-test-claude": str(exe)})
    res = runner.run(["loadout-test-claude", "plugin", "list"])
    assert res.ok and res.stdout.strip() == "ran plugin list"
    assert not runner.have("loadout-test-claude")  # PATH answers stay PATH answers


def test_fallback_that_vanished_is_not_found(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "FALLBACK", {"loadout-test-claude": str(tmp_path / "gone")})
    assert runner.run(["loadout-test-claude", "--version"]).returncode == 127


def test_main_fills_the_fallback(fake_home, fake_runner, monkeypatch):
    seen = []
    monkeypatch.setattr(vscode, "use_bundled_claude", lambda on=None: seen.append(on))
    cli.main(["kit-path"])
    assert seen == [None]


def test_check_row_warns_and_names_the_binary(fake_home, fake_runner):
    exe = _ext(fake_home, "2.1.10")
    fake_runner.missing.add("claude")
    row = next(r for r in check._binaries() if r.name == "binary claude")
    assert not row.ok and row.severity == "warn" and str(exe) in row.detail


def test_missing_claude_with_a_bundled_one_is_not_a_failure(fake_home, fake_runner):
    fake_runner.missing.add("claude")
    _, level = bootstrap._prereq_summary(["claude"], [], frozenset({"claude"}))
    assert level == "warn"
    _, level = bootstrap._prereq_summary(["claude"], [], frozenset())
    assert level == "fail"


def test_prereq_note_says_why(fake_home, fake_runner):
    fake_runner.missing.add("claude")
    notes = []
    bootstrap.check_prereqs(False, ask=lambda q: "", notes=notes, recommended=frozenset({"claude"}))
    line = next(n for n in notes if "claude" in n)
    assert bootstrap.RECOMMENDED_WHY["claude"] in line and "(required)" not in line


def test_bootstrap_with_only_the_extension_runs_its_binary(fake_home, fake_runner, monkeypatch, capsys):
    exe = _ext(fake_home, "2.1.10")
    fake_runner.missing.add("claude")
    code = bootstrap.bootstrap(install=False, yes=True, plugins=True, adopt_step=False, ask=lambda q: "",
                               interactive=False, agents="claude", personal="new")
    text = capsys.readouterr().out
    assert str(exe) in text and "Next: open VS Code's Claude Code extension" in text
    assert code == 0 or "Health check" in text


def test_bundled_path_is_printed_escaped(fake_home, fake_runner, capsys):
    from loadout import out
    out.status("Claude Code CLI", bootstrap._claude_bundled_line(fake_home / "a\x1b[31mb"), "warn")
    assert "\x1b[31m" not in capsys.readouterr().out


def test_next_line_names_the_claude_extension_next_to_a_codex_cli(fake_home, fake_runner, monkeypatch, capsys):
    _ext(fake_home, "2.1.10")
    fake_runner.missing.add("claude")
    from loadout import codex
    monkeypatch.setattr(codex, "unavailable", lambda **k: "skip")
    bootstrap.bootstrap(install=False, yes=True, plugins=True, adopt_step=False, ask=lambda q: "",
                        interactive=False, agents="claude,codex", personal="new")
    text = capsys.readouterr().out
    assert "open VS Code's Claude Code extension" in text
