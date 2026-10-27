"""The Setup row: this machine's cell and its setup-matrix section, always ok (spec 2026-10-27)."""
from loadout import check, recommend
from loadout.check import CheckResult


def test_setup_row_is_first_and_ok(fake_home, fake_runner):
    first = check.run_checks()[0]
    assert first.name == "Setup" and first.ok
    assert "·" in first.info and "docs/reference/setup-matrix.md#" in first.info


def test_results_show_setup_info():
    text, code = check.format_results([CheckResult("Setup", True, info="Linux · Claude Code · CLI — x.md#a")])
    assert text == "[ok  ] Setup: Linux · Claude Code · CLI — x.md#a" and code == 0


def test_summary_shows_setup_line():
    rows = [CheckResult("Setup", True, info="Linux · Claude Code · CLI — x.md#a"), CheckResult("python", True)]
    text, code = check.format_summary(rows)
    assert text.splitlines() == ["Health check: 2 of 2 OK", "Setup: Linux · Claude Code · CLI — x.md#a"]
    assert code == 0


def test_summary_keeps_problems_after_setup_line():
    rows = [CheckResult("Setup", True, info="cell"), CheckResult("x", False, "broken", "fix it", "warn")]
    lines = check.format_summary(rows)[0].splitlines()
    assert lines[:3] == ["Health check: 1 of 2 OK", "Setup: cell", "[warn] x: broken"]


def test_setup_row_never_fails(fake_home, fake_runner, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("no")
    monkeypatch.setattr(recommend, "detect", boom)
    first = check.run_checks()[0]
    assert first.name == "Setup" and first.ok and first.info == "unknown"


def test_extensions_are_read_once_per_check(fake_home, fake_runner, monkeypatch):
    # review #4: the Setup row and the VS Code rows share one lookup (each may probe Windows in WSL)
    from loadout import vscode
    calls = []
    real = vscode.extensions
    monkeypatch.setattr(vscode, "extensions", lambda *a, **k: calls.append(1) or real(*a, **k))
    check.run_checks()
    assert len(calls) == 1
