"""One optional Codex CLI row instead of four warnings, and bootstrap says the CLI is optional (spec decisions 3, 8)."""
import pytest

from loadout import bootstrap, check, codex, out, paths, runner

GONE = ("--install", " /hooks", "loads none", "do not load", "for /hooks and plugins")


def test_extension_only_check_has_one_ok_cli_row_and_no_cli_warnings(codex_ext):
    rows = check.run_checks()
    cli = [r for r in rows if r.name == "Codex CLI"]
    assert [(r.ok, r.detail) for r in cli] == [(True, codex.CLI_OPTIONAL)]
    assert not any(r.name == "binary codex" for r in rows)
    bad = [(r.name, r.detail, r.fix) for r in rows if "odex" in r.name and any(g in r.detail + r.fix for g in GONE)]
    assert not bad, bad


def test_a_broken_cli_next_to_the_extension_warns_once(codex_ext, fake_runner):
    fake_runner.missing.discard("codex")
    fake_runner.responses[("codex", "--version")] = runner.Result(0, "codex-cli 0.150.0\n", "")
    rows = codex.checks()
    cli = [r for r in rows if r.name == "Codex CLI"]
    assert len(cli) == 1 and not cli[0].ok and cli[0].severity == "warn"
    assert "0.150.0" in cli[0].detail and "uses VS Code's Codex extension's codex instead" in cli[0].detail
    assert rows[0].name == "Codex" and rows[0].ok


def test_a_usable_cli_has_no_cli_row(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(codex, "enabled", lambda: True)
    fake_runner.responses[("codex", "--version")] = runner.Result(0, "codex-cli 0.162.1\n", "")
    assert not any(r.name == "Codex CLI" for r in codex.checks())


def test_the_extension_row_has_no_cli_gap(codex_ext):
    rows = [r for r in check._vscode_surfaces() if r.name.startswith("VS Code (Codex")]
    assert rows and all(r.ok for r in rows), [(r.name, r.detail) for r in rows]


def test_the_cli_offer_defaults_to_no(codex_ext):
    assert bootstrap.codex_cli_choice(True, lambda q: "", True, True) == (bootstrap.CODEX_CLI_DECLINED, True)
    assert bootstrap.codex_cli_choice(True, lambda q: "y", True, True) == (bootstrap.CODEX_CLI_WHY, False)
    assert "optional" in bootstrap.CODEX_CLI_QUESTION and "[y/N]" in bootstrap.CODEX_CLI_QUESTION
    assert "/hooks" not in bootstrap.RECOMMENDED_WHY["codex"] and "optional" in bootstrap.RECOMMENDED_WHY["codex"]


def test_bootstrap_next_line_names_the_hooks_icon(codex_ext, capsys, monkeypatch):
    (paths.home() / ".config/loadout/personal").mkdir(parents=True)
    monkeypatch.setattr(out, "VERBOSE", False)
    monkeypatch.setattr(codex, "hooks_status", lambda remember=False: "untrusted")
    bootstrap.bootstrap(install=False, yes=True, plugins=False, adopt_step=False, ask=lambda q: "", interactive=False,
                        agents="codex", codex_cli=False)
    assert ("Next: open VS Code's Codex extension (reload the window if it is open) and approve loadout's hooks: "
            "the hooks icon in the prompt bar, then Allow all.") in capsys.readouterr().out
