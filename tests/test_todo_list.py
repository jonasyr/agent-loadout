"""One to-do list: every not-ok check row with a fix, once, FAILs first; the health block keeps no fix: lines in calm
mode (spec 2026-10-29 G1)."""
import argparse

from loadout import check, codex, out, steps
from loadout.check import CheckResult as R


def test_fails_first_then_plain_saved_warns_optional_last():
    lines = steps.todo_block("Still to do:", ["binary playwright-cli: loadout bootstrap --install"],
                             ["log in to GitHub: x", "optional: keep your personal layer ..."], [],
                             ["gh auth: y"], True, False)
    assert lines == ["Still to do:", "  1. binary playwright-cli: loadout bootstrap --install",
                     "  2. log in to GitHub: x", "  3. gh auth: y", "  4. optional: keep your personal layer ..."]


def test_saved_steps_render_with_their_agent():
    saved = [steps.Step("codex/hooks", "codex", "trust the hooks", "why")]
    assert steps.todo_block("Now do this", [], [], saved, [], True, True) == ["Now do this", "  1. Codex: trust the hooks"]


def test_empty_block_is_empty():
    assert steps.todo_block("Now do this", [], [], [], [], True, True) == []


def test_row_items_skip_and_rewrite_after_bootstrap():
    rows = [R("gh auth", False, "not logged in", "run gh auth login", "warn"),
            R("binary playwright-cli", False, "not on PATH", "loadout bootstrap --install"),
            R("Codex plugin", False, "loadout plugin not installed in Codex", "loadout bootstrap"),
            R("x", False, "no fix here", "", "warn"), R("ok", True)]
    fails, warns = steps.row_items(rows, steps.STILL_TO_DO_ROWS, after_bootstrap=True)
    assert fails == ["binary playwright-cli: loadout bootstrap --install",
                     "Codex plugin: re-run loadout bootstrap --verbose to see why Codex plugin failed"]
    assert warns == []


def test_row_items_keep_bare_bootstrap_outside_bootstrap():
    fails, _ = steps.row_items([R("Codex plugin", False, "", "loadout bootstrap")], set())
    assert fails == ["Codex plugin: loadout bootstrap"]


def test_same_fix_merges():
    rows = [R("Codex plugin", False, "", codex.MISSING_FIX),
            R("Codex plugins missing", False, "", codex.MISSING_FIX, "warn")]
    assert steps.row_items(rows, set()) == ([f"Codex plugin, Codex plugins missing: {codex.MISSING_FIX}"], [])


def test_skip_matches_a_name_prefix():
    rows = [R("Codex MCP serena", False, "twice", "remove it", "warn")]
    assert steps.row_items(rows, {"Codex"}) == ([], [])


def test_calm_summary_has_no_fix_lines():
    text, code = check.format_summary([R("binary playwright-cli", False, "not on PATH",
                                         "loadout bootstrap --install")], fixes=False)
    assert "fix:" not in text and "binary playwright-cli: not on PATH" in text and code == 1


def test_results_keep_fix_lines_by_default():
    text, _ = check.format_results([R("x", False, "broken", "fix it", "warn")])
    assert "fix: fix it" in text


def _check_cmd(monkeypatch, rows, verbose=False):
    from loadout import commands
    parser = argparse.ArgumentParser()
    commands._register_check(parser.add_subparsers())
    monkeypatch.setattr(out, "VERBOSE", False)
    monkeypatch.setattr(out, "_tty", lambda: False)
    monkeypatch.setattr(check, "run_checks", lambda **k: rows)
    a = parser.parse_args(["check"] + (["--verbose"] if verbose else []))
    return a.func(a)


def test_check_lists_its_rows(fake_home, fake_runner, monkeypatch, capsys):
    code = _check_cmd(monkeypatch, [R("binary playwright-cli", False, "not on PATH", "loadout bootstrap --install")])
    text = capsys.readouterr().out
    assert "Now do this" in text and "1. binary playwright-cli: loadout bootstrap --install" in text
    assert "fix:" not in text and code == 1


def test_check_all_ok_prints_no_list(fake_home, fake_runner, monkeypatch, capsys):
    _check_cmd(monkeypatch, [R("python", True)])
    assert "Now do this" not in capsys.readouterr().out


def test_verbose_keeps_fix_lines(fake_home, fake_runner, monkeypatch, capsys):
    _check_cmd(monkeypatch, [R("x", False, "broken", "fix it", "warn")], verbose=True)
    text = capsys.readouterr().out
    assert "fix: fix it" in text and "1. x: fix it" in text


def test_check_skips_rows_a_saved_step_says(fake_home, fake_runner, monkeypatch, capsys):
    saved = [steps.Step("codex/hooks", "codex", "trust the hooks", "why")]
    from loadout import targets
    monkeypatch.setattr(steps, "open_items", lambda *a, **k: saved)
    monkeypatch.setattr(targets, "codex_enabled", lambda: True)
    _check_cmd(monkeypatch, [R("Codex hooks", False, "not approved", "start codex and trust them", "warn")])
    text = capsys.readouterr().out
    assert "1. Codex: trust the hooks" in text and "start codex and trust them" not in text


def _bootstrap(fake_home, monkeypatch, rows, **kw):
    from loadout import bootstrap
    monkeypatch.setattr(out, "VERBOSE", False)
    (fake_home / ".config/loadout/personal").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(check, "run_checks", lambda **k: rows)
    args = dict(install=False, yes=True, plugins=False, adopt_step=False, ask=lambda q: "", interactive=False)
    args.update(kw)
    return bootstrap.bootstrap(**args)


def test_bootstrap_lists_a_fail_row(fake_home, fake_runner, monkeypatch, capsys):
    _bootstrap(fake_home, monkeypatch, [R("binary playwright-cli", False, "not on PATH", "loadout bootstrap --install")])
    text = capsys.readouterr().out
    tail = text[text.index("Still to do"):]
    assert "1. binary playwright-cli: loadout bootstrap --install" in tail
    assert "fix:" not in text[text.index("Health check"):]


def test_windows_side_codex_rows_not_listed(fake_home, fake_runner, monkeypatch, capsys):
    # Codex set up by bootstrap.ps1 on Windows (the gate): its rows are that side's to fix
    from loadout import bootstrap
    monkeypatch.setattr(bootstrap, "codex_gate_needed", lambda chosen: True)
    monkeypatch.setattr(bootstrap, "codex_gate", lambda *a, **k: f"Codex runs on Windows: {bootstrap.WINDOWS_WAY}")
    _bootstrap(fake_home, monkeypatch, [R("Codex config", False, "differs", "loadout bootstrap", "warn"),
                                        R("binary rtk", False, "not on PATH", "loadout bootstrap --install", "warn")],
               agents="claude,codex")
    text = capsys.readouterr().out
    assert "Codex config" not in text[text.index("Still to do"):] and "binary rtk" in text
