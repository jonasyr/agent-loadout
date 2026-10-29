# Tour leftovers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `bootstrap --no-plugins` run without plugin noise, plus the small output and doc leftovers from #72's reviews.

**Architecture:** Check rows that are not ok only because plugins or marketplaces are missing carry a flag (`CheckResult.plugins_missing`). In a `--no-plugins` run, bootstrap leaves those rows out of the health block, its counts, its exit code and the to-do list, and prints one info line instead. The other items are local edits in `recommend.py`, bootstrap's "Next" and adopt step, and the docs.

**Tech Stack:** Python 3.11+, standard library only (`cli/loadout/`); pytest with `fake_home` and `fake_runner`.

**Spec:** `docs/superpowers/specs/2026-10-29-tour-leftovers-design.md`

## Global Constraints

- Standard library only. External commands run only through `runner.run`. Tests use `fake_home` and `fake_runner` and never run real `claude`, `codex`, `loadout` or installers.
- Test command: `uv run --python 3.12 --with pytest pytest -q --deselect "tests/test_docs_links.py::test_links_resolve[docs/examples/Niklas_Serena_Config.md]"`.
- Conventional Commits; no AI attribution.
- Nothing about `--no-plugins` is remembered. A later `loadout check` or `update` is unchanged.
- Code tools: codebase-memory (project `home-jonas-Documents-Code-agent-loadout`) and Serena `find_symbol` before grep.

## Review Focus

1. `--no-plugins` with a real non-plugin FAIL (e.g. a binary missing): the exit stays 1 and the FAIL is listed (Task 1 test `test_other_fail_still_fails`).
2. `--no-plugins` with every plugin already installed: no info line (Task 1 test `test_no_line_when_nothing_hidden`).
3. `--no-plugins` with an undeclared marketplace in Claude Code's settings: the "plugins installed" row stays (Task 1 test `test_undeclared_marketplace_row_stays`).
4. A bootstrap run with plugins (no `--no-plugins`): plugin rows are reported exactly as before (Task 1 test `test_with_plugins_rows_unchanged`).
5. `--yes` adopt with secret findings only: the heading and the findings still print (Task 4 test `test_adopt_step_prints_when_secrets`).

---

### Task 1: `--no-plugins` hides only the rows it caused

**Files:**
- Modify: `cli/loadout/check.py` (`CheckResult` ~20, `_plugins` ~68), `cli/loadout/codex.py` (`checks`: "Codex plugin", "Codex plugins missing"; `open_steps`), `cli/loadout/bootstrap.py` (`still_to_do` ~100, health block and to-do list at the end of `_bootstrap`)
- Test: `tests/test_no_plugins.py`

**Interfaces:**
- Produces:
  - `CheckResult.plugins_missing: bool = False`. It is set to True on:
    - "plugins installed" when not ok and every missing marketplace is addable (not the `declare … in your personal settings.json` case, not invalid JSON);
    - "Codex plugin" when not ok and not the `no_plugin_command()` case;
    - "Codex plugins missing".
  - `bootstrap.PLUGINS_SKIPPED = "plugins skipped (--no-plugins): run loadout bootstrap without it to add them"`.
  - `codex.open_steps(plugins: bool = True)`.
  - `bootstrap.still_to_do(key, codex_here=True, plugins=True)`.
  - With `plugins=False`, neither adds the missing-plugins item.

- [ ] **Step 1: Write the failing tests.** Each runs `bootstrap.bootstrap(install=False, yes=True, plugins=False, adopt_step=False, ask=lambda q: "", interactive=False)` with `check.run_checks` patched, as in `tests/test_todo_list.py::_bootstrap`.

```python
R = check.CheckResult
P = lambda name, sev="error": R(name, False, "missing", "loadout update (retries them)", sev, plugins_missing=True)

def test_hidden_rows_do_not_fail_or_count(...):   # rows: [R("python", True), P("Codex plugin"), P("Codex plugins missing", "warn")]
    # exit 0; "Health check" line says "1 of 1 OK"; bootstrap.PLUGINS_SKIPPED printed once; no "Codex plugin" in the output
def test_other_fail_still_fails(...):              # + R("binary rtk", False, "not on PATH", "loadout bootstrap --install")
    # exit 1; "binary rtk: loadout bootstrap --install" in "Still to do"; PLUGINS_SKIPPED printed
def test_no_line_when_nothing_hidden(...):         # rows all ok -> PLUGINS_SKIPPED not printed
def test_with_plugins_rows_unchanged(...):         # plugins=True, same rows as the first test -> "Codex plugin" listed, exit 1, no PLUGINS_SKIPPED
def test_still_to_do_skips_missing_plugins_item(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(codex, "missing_routes", lambda *a, **k: (["x/y"], []))
    # (stub codex.enabled/has_codex/mode/hooks_status as tests/test_codex_plugins.py::_checks_on does)
    assert not any("loadout update" in s for s in codex.open_steps(plugins=False))
def test_undeclared_marketplace_row_stays(...):    # check._plugins() with an enabled plugin whose marketplace is declared nowhere -> plugins_missing False
def test_rows_are_marked(...):                     # check._plugins() missing with an addable marketplace -> True; codex "Codex plugin"/"Codex plugins missing" (reuse _checks_on/_codex_has) -> True; no_plugin_command case -> False
```

- [ ] **Step 2: Run** `uv run --python 3.12 --with pytest pytest -q tests/test_no_plugins.py`. Expected: FAIL (unknown keyword `plugins_missing`).

- [ ] **Step 3: Implement.** In `_bootstrap`'s Check step, when `not plugins`, split the rows into `hidden = [r for r in results if not r.ok and r.plugins_missing]` and `shown = the rest`. The health block, its count, its level, `code`, `row_items` and `steps.settle` use `shown`. When `hidden` is non-empty, print `PLUGINS_SKIPPED` as an info line (`out.detail` is verbose-only, so use the same call that prints the `Setup` line's info in calm mode, or `out.status`'s info styling; check `format_summary`'s info lines). Pass `plugins` to `still_to_do`, and from there to `codex.open_steps`.

- [ ] **Step 4: Run** the file, then the full suite. Expected: PASS and green.

- [ ] **Step 5: Commit** `fix(bootstrap): --no-plugins leaves out the plugin rows it caused`

### Task 2: One line for an ignored CLI flag; the dead `missing` rule goes

**Files:**
- Modify: `cli/loadout/recommend.py` (`differences`), `cli/loadout/bootstrap.py` (`_this_machine` call)
- Test: `tests/test_recommend.py` and `tests/test_claude_cli_optional.py` (update the tests that pin the removed lines)

**Interfaces:**
- Produces: `recommend.differences(cell, chosen, vscode_wsl: bool) -> list[str]`. Only the Windows-window rule and the "a Codex CLI is on PATH but Codex is not chosen" rule are left. The `install`, `missing`, `codex_cli` and `claude_cli` parameters go. Update every caller (find them with `trace_path` inbound on `differences`).

- [ ] **Step 1: Change the tests.**
  - `test_differences_names_a_flag_with_a_cli_on_path` becomes `test_ignored_cli_flag_is_said_once`: bootstrap with `claude_cli=False`, a claude on PATH and the extension present; the output contains `--without-claude-cli: not used` once and not `given while a Claude Code CLI is on PATH`.
  - Add the same test for Codex.
  - Delete the recommend tests of the removed rules.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the full suite. Expected: green.
- [ ] **Step 5: Commit** `refactor(recommend): drop differences that Prerequisites already says`

### Task 3: "Next" in two short lines

**Files:**
- Modify: `cli/loadout/bootstrap.py` ("Next", ~1195-1215)
- Test: `tests/test_claude_cli_optional.py`, `tests/test_bundled_claude.py`

- [ ] **Step 1: Write the test.** `test_next_second_line_names_extensions_next_to_their_cli`: claude on PATH, the Claude Code extension present, Codex off. The output has a line `Next: run `claude` in a new terminal.` (or the restart variant), and the line right after it is `Or open VS Code's Claude Code extension (reload the window if it is open).`. Also `test_cli_present_no_question_next_names_extension` changes: "Claude Code extension" is now on the line after "Next:". The verbose variant: `Then start …` / `Restart …`, followed by the same second line.
- [ ] **Step 2: Run it.** Expected: FAIL.
- [ ] **Step 3: Implement.** The `too` list becomes its own line: `Or open VS Code's {' or '.join(too)} extension (reload the window if it is open).`, printed right after whichever first line prints. The `claude_ext` (extension without its CLI) suffix stays as is.
- [ ] **Step 4: Run** the full suite. Expected: green.
- [ ] **Step 5: Commit** `fix(bootstrap): name the extensions on their own line in Next`

### Task 4: No empty adopt step under `--yes`

**Files:**
- Modify: `cli/loadout/bootstrap.py` (the adopt step, ~1105)
- Test: `tests/test_adopt_yes_embedded.py`

- [ ] **Step 1: Write the tests.** Both use bootstrap with `yes=True`, `adopt_step=True` and Claude Code on.
  - `test_adopt_step_silent_when_nothing`: the inventory gives nothing to report; the output has no "Adopt existing setup" and no two blank lines in a row.
  - `test_adopt_step_prints_when_secrets`: one secret finding; the heading and the finding are printed.
- [ ] **Step 2: Run them.** Expected: the first FAILs.
- [ ] **Step 3: Implement.** With `yes`, run `adopt.run` inside `contextlib.redirect_stdout(io.StringIO())`, then print `_step("Adopt existing setup")`, the captured text and the blank lines only when the captured text is not blank. Keep its return code handling. The interactive path is unchanged.
- [ ] **Step 4: Run** the full suite. Expected: green.
- [ ] **Step 5: Commit** `fix(bootstrap): no empty adopt step under --yes`

### Task 5: Docs

**Files:**
- Modify:
  - `docs/how-to/vscode.md` (~line 10, the Claude Code CLI advice);
  - `docs/how-to/troubleshooting.md` (new entry: Serena "could not initialize" or "language server terminated" on first use);
  - `docs/reference/cli.md` (`--no-plugins` in the bootstrap flags table: the info line, the hidden rows, nothing remembered; the `--without-…-cli` rows name only the `not used` line);
  - `.superpowers/handoff/2026-10-13-hardening-backlog.md` (mark the leftovers done, PR pending).
- Test: `tests/test_docs_links.py`, `tests/test_docs_commands.py`

- [ ] **Step 1: Edit.**
  - vscode.md: in a terminal, answer y to get the CLI; without a terminal, `--install` installs it unless `--without-claude-cli` is given.
  - Troubleshooting: Serena downloads its Python language server (pyright) from PyPI on first use and doesn't use loadout's pyright; it needs the network once; retry when online.
- [ ] **Step 2: Run** the docs tests and the full suite. Expected: green.
- [ ] **Step 3: Commit** `docs: --no-plugins, Claude Code CLI advice, Serena's first-use download`
