"""loadout check runs its rows in parallel, keeps their order, and shows progress only on a terminal."""
import threading

import pytest

from loadout import check, out
from loadout.check import CheckResult


def test_slow_rows_run_at_the_same_time(fake_home, fake_runner, monkeypatch):
    # two rows that each wait for the other: serial execution breaks the barrier
    barrier = threading.Barrier(2, timeout=5)

    def row(name):
        def run(*a, **k):
            barrier.wait()
            return [CheckResult(name, True)]
        return run
    monkeypatch.setattr(check, "_gh", row("gh auth"))
    monkeypatch.setattr(check, "_cbm_auto_index", row("codebase-memory auto_index"))
    names = [r.name for r in check.run_checks()]
    assert names.index("codebase-memory auto_index") < names.index("gh auth")  # printed order unchanged


def test_order_is_the_serial_order(fake_home, fake_runner, monkeypatch):
    rows = [lambda i=i: [CheckResult(str(i), True)] for i in range(30)]
    assert [r.name for r in check._run_rows(rows)] == [str(i) for i in range(30)]


def test_a_failing_row_still_raises(fake_home, fake_runner, monkeypatch):
    def boom():
        raise RuntimeError("row broke")
    monkeypatch.setattr(check, "_gh", boom)
    with pytest.raises(RuntimeError, match="row broke"):
        check.run_checks()


def test_progress_counts_finished_rows():
    seen = []
    check._run_rows([lambda: [], lambda: [CheckResult("a", True)]], say=lambda done, total: seen.append((done, total)))
    assert sorted(seen) == [(1, 2), (2, 2)]


def _check_cmd(monkeypatch, tty, verbose=False):
    import argparse
    from loadout import commands
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers()
    commands._register_check(sub)
    lines = []
    monkeypatch.setattr(out, "VERBOSE", False)
    monkeypatch.setattr(out, "_tty", lambda: tty)
    monkeypatch.setattr(out, "progress", lambda line: lines.append(line))
    a = parser.parse_args(["check"] + (["--verbose"] if verbose else []))
    a.func(a)
    return lines


def test_check_shows_progress_on_a_terminal(fake_home, fake_runner, monkeypatch):
    lines = _check_cmd(monkeypatch, tty=True)
    assert lines and all(line.startswith("checking") for line in lines)


def test_check_shows_no_progress_off_a_terminal(fake_home, fake_runner, monkeypatch):
    assert _check_cmd(monkeypatch, tty=False) == []


def test_check_shows_no_progress_with_verbose(fake_home, fake_runner, monkeypatch):
    assert _check_cmd(monkeypatch, tty=True, verbose=True) == []


def test_serial_rows_run_alone_after_the_others():
    # _without_codex sets targets.OVERRIDE for its row: no other row may run meanwhile
    running, log = [], []

    def row(name):
        def run():
            running.append(name)
            log.append((name, list(running)))
            running.remove(name)
            return [CheckResult(name, True)]
        return run
    rows = [row("a"), check.Serial(row("s")), row("b"), row("c")]
    names = [r.name for r in check._run_rows(rows)]
    assert names == ["a", "s", "b", "c"]
    assert dict(log)["s"] == ["s"] and [n for n, _ in log][-1] == "s"


def test_windows_only_codex_rows_are_serial(fake_home, fake_runner, monkeypatch):
    from loadout import wsl
    monkeypatch.setattr(check, "_wsl_codex_side", lambda: wsl.CodexSide("windows"))
    seen = []
    monkeypatch.setattr(check, "_run_rows", lambda rows, say=None: seen.extend(rows) or [])
    check.run_checks()
    assert sum(isinstance(r, check.Serial) for r in seen) == 5


def test_codex_mcp_list_runs_once_inside_the_cache(fake_home, fake_runner, monkeypatch):
    from loadout import codex
    monkeypatch.setattr(codex, "program", lambda: "codex")
    with codex.mcp_list_cache():
        codex.mcp_names()
        codex.logins_needed()
    assert sum(c[1:3] == ["mcp", "list"] for c in fake_runner.calls) == 1
    codex.mcp_names()  # outside: asks again
    assert sum(c[1:3] == ["mcp", "list"] for c in fake_runner.calls) == 2


def test_check_codex_row_uses_the_cache(fake_home, fake_runner, monkeypatch):
    from loadout import codex
    monkeypatch.setattr(codex, "program", lambda: "codex")
    monkeypatch.setattr(codex, "checks", lambda: (codex.mcp_names(), codex.logins_needed()) and [])
    check._codex()
    assert sum(c[1:3] == ["mcp", "list"] for c in fake_runner.calls) == 1
