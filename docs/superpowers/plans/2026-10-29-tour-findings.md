# Live tour 2026-10-28 fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One honest to-do list at the end of bootstrap and check, quieter and truer messages, and the Claude Code CLI decided like the Codex CLI next to its VS Code extension.

**Architecture:** Check rows become to-do items at render time (`steps.row_items` + `steps.todo_block`), never saved; the health block drops `fix:` lines in calm mode because every fix is in the list. Message fixes are local to the function that prints them. The Claude Code CLI choice copies `codex_cli_choice`.

**Tech Stack:** Python 3.11+ standard library (`cli/loadout/`), pytest with `fake_home` / `fake_runner`.

**Spec:** `docs/superpowers/specs/2026-10-29-tour-findings-design.md`

## Global Constraints

- Standard library only in `cli/loadout/`; external commands only through `runner.run` with argument lists.
- Tests use `fake_home` and `fake_runner` (`fake_runner.missing`, `fake_runner.responses[prefix] = runner.Result(code, stdout, stderr)`); never the real home, never real `claude`/`codex`/installers.
- Test command: `uv run --python 3.12 --with pytest pytest -q --deselect "tests/test_docs_links.py::test_links_resolve[docs/examples/Niklas_Serena_Config.md]"`.
- Conventional Commits `type(scope): subject`; no Co-Authored-By or AI attribution.
- No change to which checks run or their levels, except the Claude Code CLI row (Task 7). Exit codes unchanged.
- Code tools: codebase-memory (project `home-jonas-Documents-Code-agent-loadout`: `search_graph`, `trace_path`, `get_code_snippet`) and Serena `find_symbol` before grep.

## Review Focus

1. Codex on the Windows side of WSL (`here["codex"]` False, gate set): Codex check rows must not add Codex items to bootstrap's list that `bootstrap.ps1` owns — Task 6 test `test_windows_side_codex_rows_not_listed`.
2. `loadout check` with no saved steps and all rows ok: prints no "Now do this" at all (no empty title) — Task 6 test `test_check_all_ok_prints_no_list`.
3. `--verbose`: health block keeps `fix:` lines and the list still shows — Task 6 test `test_verbose_keeps_fix_lines`.
4. A git error with no `error:` line (only `fatal:`) or empty output still gives a readable line — Task 1 test `test_tail_fatal_only_and_empty`.
5. Claude Code chosen, extension present, `claude` already on PATH: no question, no "not installed" line, "Next" names both — Task 7 test `test_cli_present_no_question_next_names_extension`.

---

### Task 1: One readable line for a failed Codex command (C2)

**Files:**
- Modify: `cli/loadout/codex.py` (`_tail`, ~1277)
- Test: `tests/test_codex_tail.py`

**Interfaces:**
- Produces: `codex._tail(res: runner.Result) -> str` (same name, used at ~1669, 1719, 1729, 1771, 2019); `codex.NETWORK_HINT = "network error; loadout update retries"`.

- [ ] **Step 1: Write the failing tests**

```python
from loadout import codex, runner

GIT = ("Cloning into '/home/u/.codex/.tmp/marketplaces/.staging/marketplace-linux-uVGJ1X/checkout'...\n"
       "error: RPC failed; curl 56 Recv failure: Connection reset by peer\n"
       "error: 13993 bytes of body are still expected\n"
       "fetch-pack: unexpected disconnect while reading sideband packet\n"
       "fatal: early EOF\nfatal: fetch-pack: invalid index-pack output\n")

def test_tail_names_the_first_error_and_the_network():
    assert codex._tail(runner.Result(128, "", GIT)) == \
        "RPC failed; curl 56 Recv failure: Connection reset by peer (network error; loadout update retries)"

def test_tail_fatal_only_and_empty():
    assert codex._tail(runner.Result(1, "", "fatal: repository 'x' not found\n")) == "repository 'x' not found"
    assert codex._tail(runner.Result(1, "", "")) == "exit code 1"

def test_tail_keeps_a_plain_message_short():
    assert len(codex._tail(runner.Result(1, "x" * 900, ""))) <= 300
```

- [ ] **Step 2: Run** `uv run --python 3.12 --with pytest pytest -q tests/test_codex_tail.py` — Expected: FAIL (old `[-300:]` cut).

- [ ] **Step 3: Implement `_tail`**: non-empty lines of stderr (else stdout); pick the first line starting with `error:`, else the last line starting with `fatal:`, else the last line; strip that prefix; cut to 300 characters; when the whole output matches `RPC failed|Connection reset|Could not resolve host|Temporary failure in name resolution|timed out|early EOF|unable to access` (case-insensitive) append ` (network error; loadout update retries)`; empty output → `f"exit code {res.code}"` (check `runner.Result`'s field name).

- [ ] **Step 4: Run** the test file — Expected: PASS; then the full suite — Expected: green (update any test that pinned the old cut text).

- [ ] **Step 5: Commit** `fix(codex): show one readable line for a failed command`

### Task 2: Bootstrap messages that say something new (B3, A1, duplicate status lines)

**Files:**
- Modify: `cli/loadout/bootstrap.py` (`check_prereqs` ~277-334, `_this_machine` ~929-954, `_report` ~55)
- Test: `tests/test_bootstrap_messages.py`

**Interfaces:**
- Produces: `bootstrap.INSTALL_FAILED_HINT = "the install failed (see above); fix that, then run loadout bootstrap --install again"`; `_report` skips a problem line that only repeats the summary.

- [ ] **Step 1: Write the failing tests**

```python
def test_failed_install_does_not_say_rerun_with_install(fake_home, fake_runner, monkeypatch):
    # make one catalog binary missing, its install command fail (fake_runner.responses on its install cmd prefix)
    notes = []
    bootstrap.check_prereqs(True, lambda q: "", notes=notes)
    line = next(n for n in notes if n.startswith("missing") and "<id>" in n)
    assert "re-run with --install" not in line and ("by hand" in line or "fix that" in line)

def test_missing_without_install_still_says_rerun(fake_home, fake_runner):
    notes = []; bootstrap.check_prereqs(False, lambda q: "", notes=notes)
    assert any("re-run with --install" in n for n in notes if n.startswith("missing"))

def test_this_machine_does_not_repeat_missing(calm, capsys, fake_runner):  # reuse test_bootstrap_this_machine's fixture/_block
    fake_runner.missing.add("serena")
    _run()
    assert "missing and no --install" not in _block(capsys.readouterr().out)

def test_report_prints_a_problem_once(capsys):
    bootstrap._report("codebase-memory", "could not read auto_index (config get failed)",
                      ["codebase-memory: could not read auto_index (config get failed)"])
    assert capsys.readouterr().out.count("could not read auto_index") == 1
```

(The implementer picks a catalog binary with an install command and sets `fake_runner.missing` and a failing `responses` entry for it; `<id>` is that binary.)

- [ ] **Step 2: Run** — Expected: 3 FAIL (`test_missing_without_install_still_says_rerun` passes already).

- [ ] **Step 3: Implement**
  - `check_prereqs`: remember the names whose install ran this call (`tried`); for a still-missing tried name the hint is `install it by hand: {manual}` when the entry has `manual`, else `INSTALL_FAILED_HINT`; the WSL Windows-first suffix logic stays.
  - `_this_machine`: pass `[]` as `missing` to `recommend.differences` (Prerequisites in the same run names missing tools); remove the now-unused `missing_tools` call there. Update `tests/test_bootstrap_this_machine.py::test_block_names_differences` and `test_without_codex_cli_does_not_hide_a_required_codex` / `test_optional_codex_cli_is_not_missing` to assert on the Prerequisites output instead of the block (their intent: a required Codex is reported missing, an optional one is not). `recommend.differences` keeps its `missing` rule (unit tests in `tests/test_recommend.py` stay).
  - `_report`: skip a line whose text without the leading `f"{name}: "` equals `summary`.

- [ ] **Step 4: Run** the new file and `tests/test_bootstrap_this_machine.py` — PASS; full suite — green.

- [ ] **Step 5: Commit** `fix(bootstrap): say what to do after a failed install and stop repeating lines`

### Task 3: codebase-memory says why once (A2)

**Files:**
- Modify: `cli/loadout/check.py` (`_cbm_auto_index` ~254, `_cbm_conflict` ~520), `cli/loadout/cbm.py` (`apply_auto_index` ~81)
- Test: `tests/test_cbm_unreadable.py`

**Interfaces:**
- Produces: `check.cbm_conflict_detail() -> str | None` (the daemon row's detail, or None; `_cbm_conflict` builds its row from it); `check.CBM_UNREADABLE_FIX`.

- [ ] **Step 1: Write the failing tests**

```python
def test_conflict_replaces_the_auto_index_row(fake_home, monkeypatch):
    monkeypatch.setattr(cbm, "query", lambda: cbm.UNREADABLE)
    monkeypatch.setattr(check, "cbm_conflict_detail", lambda: "a codebase-memory-mcp session with a different cache folder could not start (another one already runs for your account)")
    assert check._cbm_auto_index() == []

def test_unreadable_without_conflict_says_where_to_look(fake_home, monkeypatch):
    monkeypatch.setattr(cbm, "query", lambda: cbm.UNREADABLE)
    monkeypatch.setattr(check, "cbm_conflict_detail", lambda: None)
    [row] = check._cbm_auto_index()
    assert row.fix == check.CBM_UNREADABLE_FIX and "to see why" not in row.fix

def test_bootstrap_line_names_the_conflict(fake_home, monkeypatch):
    monkeypatch.setattr(cbm, "answer", lambda: "on"); monkeypatch.setattr(cbm, "query", lambda: cbm.UNREADABLE)
    monkeypatch.setattr(check, "cbm_conflict_detail", lambda: "X already runs")
    assert cbm.apply_auto_index(object()) == ["codebase-memory: could not read auto_index: X already runs (see loadout check)"]
```

- [ ] **Step 2: Run** — Expected: FAIL (`cbm_conflict_detail` missing).

- [ ] **Step 3: Implement**: extract the record lookup and detail text of `_cbm_conflict` into `cbm_conflict_detail()` (fix text stays in `_cbm_conflict`); `_cbm_auto_index` returns `[]` for UNREADABLE when a detail exists, else its row with `CBM_UNREADABLE_FIX = "run codebase-memory-mcp config get auto_index in a terminal: its error says why (often another codebase-memory-mcp session holds the daemon)"`; `cbm.apply_auto_index` (import `check` inside the function) appends `f": {detail} (see loadout check)"` instead of ` (config get failed)` when a detail exists.

- [ ] **Step 4: Run** the file and existing cbm/check tests — PASS; full suite — green.

- [ ] **Step 5: Commit** `fix(cbm): name the daemon conflict once instead of a bare config get failure`

### Task 4: Adopt inside bootstrap with --yes prints one line (C3)

**Files:**
- Modify: `cli/loadout/adopt.py` (`run` ~505-552, `render_calm` ~171)
- Test: `tests/test_adopt_yes_embedded.py`

**Interfaces:**
- Produces: `adopt.yes_line(verdicts: list[Verdict], findings: list) -> str | None`.

- [ ] **Step 1: Write the failing tests** — build verdicts the way existing adopt tests do (find one with `search_graph` on `test_adopt`):

```python
def test_embedded_yes_prints_one_line_and_no_nothing_selected(...):
    # verdicts: two in "update", one in "install"; no findings
    adopt.run(apply_changes=True, groups=None, skip=set(), yes=True, ask=..., interactive=True, embedded=True)
    text = capsys.readouterr().out
    assert "nothing selected" not in text and "suggestion" not in text
    assert text.strip().splitlines() == ["Your existing setup: 2 tool updates (loadout update), 1 tool to install (loadout adopt)"]

def test_embedded_yes_all_fine_prints_nothing(...):
    assert capsys.readouterr().out.strip() == ""

def test_not_embedded_yes_unchanged(...):  # `loadout adopt --apply --yes` keeps render_calm and "nothing selected"
```

- [ ] **Step 2: Run** — FAIL.

- [ ] **Step 3: Implement**: when `embedded and yes and calm`, print `yes_line(...)` (skip when None) instead of `render_calm`, and return 0 instead of printing "nothing selected". `yes_line` counts the groups `--yes` does not apply (`update` → "N tool update(s) (loadout update)", `install` → "N tool(s) to install (loadout adopt)", `review`/`own` → "N to review (loadout adopt)"), joined by ", ", prefixed "Your existing setup: "; None when all are zero. Groups in `DEFAULT_ALL` still apply and print what they do as today.

- [ ] **Step 4: Run** — PASS; full suite — green.

- [ ] **Step 5: Commit** `fix(adopt): one line inside bootstrap --yes instead of an unselected list`

### Task 5: A missing loadout marketplace is named, with one fix (C1)

**Files:**
- Modify: `cli/loadout/codex.py` (`missing_routes` ~1786, `checks` ~2283)
- Test: `tests/test_codex_own_marketplace.py`

**Interfaces:**
- Produces: `missing_routes` lists loadout's own marketplace source in its first list when Codex lacks it (the plugin entry still left to the `Codex plugin` row); the `Codex plugin` row's fix is `MISSING_FIX` when loadout's marketplace is in that list, else `"loadout bootstrap"`.

- [ ] **Step 1: Write the failing tests** (set up desired settings and a Codex listing the way existing `missing_routes` tests do; find them with `search_graph` name_pattern `test.*missing_routes`):

```python
def test_own_marketplace_missing_is_named(...):
    lacks_m, lacks_p = codex.missing_routes(installed=set(), listed={})
    assert "jonasyr/agent-loadout" in lacks_m and not any(p.startswith("loadout") for p in lacks_p)

def test_codex_plugin_row_points_to_update_when_its_marketplace_is_missing(...):
    row = next(r for r in codex.checks() if r.name == "Codex plugin")
    assert row.fix == codex.MISSING_FIX

def test_own_marketplace_present_plugin_missing_keeps_bootstrap_fix(...):
    row = next(r for r in codex.checks() if r.name == "Codex plugin")
    assert row.fix == "loadout bootstrap"
```

- [ ] **Step 2: Run** — FAIL.

- [ ] **Step 3: Implement**: in `missing_routes`, when a route's names become empty only because loadout's own plugin was removed, still resolve its market and append `src` to `lacks_m` when it is missing (no plugin entry); in `checks`, compute `lacks` before the `Codex plugin` row and pick its fix as above.

- [ ] **Step 4: Run** — PASS; full suite — green.

- [ ] **Step 5: Commit** `fix(codex): name a missing loadout marketplace and give one fix`

### Task 6: One to-do list from check rows (G1)

**Files:**
- Modify: `cli/loadout/steps.py`, `cli/loadout/check.py` (`format_results`, `format_summary`), `cli/loadout/bootstrap.py` (end of `bootstrap`, ~1121-1150), `cli/loadout/commands.py` (`run_check` ~66)
- Test: `tests/test_todo_list.py`; update tests that pin `fix:` lines in calm output or the "Still to do" / "Now do this" layout.

**Interfaces:**
- Consumes: Task 5's `Codex plugin` fix.
- Produces:
  - `check.format_results(results, fixes: bool = True)`, `check.format_summary(results, fixes: bool = True)` — `fixes=False` leaves out the `fix:` lines.
  - `steps.STILL_TO_DO_ROWS = {"gh auth", "Codex hooks", "Codex plugins missing", "Codex logins"}` — rows `bootstrap.still_to_do` already says.
  - `steps.row_items(results: list, skip_rows: set[str], after_bootstrap: bool = False) -> tuple[list[str], list[str]]` — (FAIL items, warn items) for rows that are not ok, have a fix and are not in `skip_rows` (a row name matches when it equals or starts with an entry); text `f"{name}: {fix}"`; rows with the same fix merge into one item (`"a, b: fix"`); an item whose fix already appears inside a `skip`-covered item is dropped by the caller passing those names; with `after_bootstrap` a bare `loadout bootstrap` fix becomes `re-run loadout bootstrap --verbose to see why {name} failed`.
  - `steps.open_items(claude_on: bool, codex_on: bool, skip: set[str] = frozenset(), show_codex: bool | None = None) -> list[Step]` — what `print_pending` shows today (settle, then pending, filtered); `print_pending` uses it.
  - `steps.todo_block(title: str, fails: list[str], plain: list[str], saved: list[Step], warns: list[str], claude_on: bool, codex_on: bool) -> list[str]` — `title` then numbered lines `  1. text` in the order fails, plain, saved (rendered `Claude Code: text` as `render` does), warns, and last every item starting with `optional:`; `[]` when there are no items.

- [ ] **Step 1: Write the failing tests**

```python
R = check.CheckResult
def test_fails_first_then_plain_saved_warns_optional_last():
    lines = steps.todo_block("Still to do:", ["binary playwright-cli: loadout bootstrap --install"],
                             ["log in to GitHub: x", "optional: keep your personal layer ..."], [],
                             ["gh auth: y"], True, False)
    assert lines == ["Still to do:", "  1. binary playwright-cli: loadout bootstrap --install",
                     "  2. log in to GitHub: x", "  3. gh auth: y", "  4. optional: keep your personal layer ..."]

def test_row_items_skip_merge_and_rewrite():
    rows = [R("gh auth", False, "not logged in", "run gh auth login", "warn"),
            R("binary playwright-cli", False, "not on PATH", "loadout bootstrap --install"),
            R("Codex plugin", False, "loadout plugin not installed in Codex", "loadout bootstrap"),
            R("x", False, "no fix here", "", "warn"), R("ok", True)]
    fails, warns = steps.row_items(rows, steps.STILL_TO_DO_ROWS, after_bootstrap=True)
    assert fails == ["binary playwright-cli: loadout bootstrap --install",
                     "Codex plugin: re-run loadout bootstrap --verbose to see why Codex plugin failed"]
    assert warns == []

def test_same_fix_merges():
    rows = [R("Codex plugin", False, "", codex.MISSING_FIX), R("Codex plugins missing", False, "", codex.MISSING_FIX, "warn")]
    assert steps.row_items(rows, set()) == ([f"Codex plugin, Codex plugins missing: {codex.MISSING_FIX}"], [])

def test_calm_summary_has_no_fix_lines():
    text, code = check.format_summary([R("binary playwright-cli", False, "not on PATH", "loadout bootstrap --install")], fixes=False)
    assert "fix:" not in text and code == 1

def test_check_lists_its_rows(fake_home, fake_runner, monkeypatch, capsys):  # via the registered command, as tests/test_check_parallel.py::_check_cmd does
    monkeypatch.setattr(check, "run_checks", lambda **k: [R("binary playwright-cli", False, "not on PATH", "loadout bootstrap --install")])
    ...; out = capsys.readouterr().out
    assert "Now do this" in out and "1. binary playwright-cli: loadout bootstrap --install" in out and "fix:" not in out

def test_check_all_ok_prints_no_list(...):   # Review Focus 2
def test_verbose_keeps_fix_lines(...):       # Review Focus 3: --verbose: "fix:" in output and the list printed
def test_bootstrap_lists_a_fail_row(calm, capsys, monkeypatch):  # bootstrap with check.run_checks patched to one FAIL row
    # "Still to do" contains "binary playwright-cli: loadout bootstrap --install" and the health block has no "fix:"
def test_windows_side_codex_rows_not_listed(...):  # Review Focus 1: gate set (here["codex"] False): no "Codex ..." row item
```

- [ ] **Step 2: Run** — FAIL (missing functions / old layout).

- [ ] **Step 3: Implement**
  - `check.format_results`/`format_summary`: the `fixes` parameter.
  - `steps`: the four names above; `print_pending` becomes `open_items` + `block` (unchanged output for its other callers: find them with `trace_path` inbound on `print_pending`).
  - `bootstrap`: calm health block uses `format_results(bad, fixes=False)`; one list from `todo_block(title, fails, still_to_do(...), open_items(here["claude"], chosen["codex"], skip={"codex/hooks"}, show_codex=here["codex"]), warns, ...)` where `fails, warns = row_items(results, STILL_TO_DO_ROWS | <Codex row names when not here["codex"]>, after_bootstrap=True)`; title stays "Still to do (in a new terminal):" / "Still to do:"; the separate `print_pending` call goes. Items are printed as numbered lines (no more "- ").
  - `run_check`: calm mode uses `format_summary(results, fixes=False)`; then `todo_block("Now do this", fails, [], open_items(...), warns, ...)` with `skip_rows` = `{"Codex hooks"}` when a `codex/hooks` step is open, plus `BOOTSTRAP_ROWS` when a `*/bootstrap` step is open; `--verbose` prints `format_results(results)` (with fixes) and the same list.

- [ ] **Step 4: Run** `tests/test_todo_list.py` and the suite; update every test that pinned the old layout (`- ` items, a separate "Now do this" after "Still to do", calm `fix:` lines) so it asserts the new layout — Expected: green.

- [ ] **Step 5: Commit** `feat(check): one to-do list with every problem that has a fix`

### Task 7: Claude Code CLI next to its VS Code extension, decided like Codex's (G3, E1/E2)

**Files:**
- Modify: `cli/loadout/bootstrap.py` (constants near `CODEX_CLI_QUESTION` ~805, new `claude_cli_choice`, `bootstrap()`/`_bootstrap` signatures ~960/972, Prerequisites ~1040-1056, "Next" ~1152-1178), `cli/loadout/commands.py` (`--without-claude-cli` ~185), `cli/loadout/recommend.py` (`differences`), `cli/loadout/check.py` (`_binaries` claude branch ~241)
- Test: `tests/test_claude_cli_optional.py`; update tests pinning `CLAUDE_BUNDLED`'s warn status or the `binary claude` warn row.

**Interfaces:**
- Produces:
  - `CLAUDE_CLI_QUESTION = "\nVS Code's Claude Code extension runs its own claude, and loadout sets it up fully. Install the Claude Code CLI too (optional, for claude in a terminal)? [y/N] "`
  - `CLAUDE_CLI_WHY = "installed alongside VS Code's Claude Code extension (optional, for claude in a terminal)"`
  - `CLAUDE_CLI_DECLINED = "not installed (optional): VS Code's Claude Code extension runs its own, and loadout set Claude Code up for it"`
  - `claude_cli_choice(install: bool, ask: Ask, interactive: bool, wanted: bool, bundled: Path | None) -> tuple[str | None, bool]` — same rules as `codex_cli_choice`, with "has a CLI" = `runner.have("claude")` and "extension can run it" = `bundled is not None`.
  - `bootstrap(..., claude_cli: bool = True)`; flag `--without-claude-cli` (help parallel to `--without-codex-cli`).
  - `recommend.differences(..., claude_cli: bool = True)` adds `"--without-claude-cli given while a Claude Code CLI is on PATH"` when Claude Code is chosen, `claude_cli` is False and `runner.have("claude")`.

- [ ] **Step 1: Write the failing tests**

```python
def test_terminal_without_yes_asks_default_no(...):   # bundled found, claude missing, install=True, interactive, ask -> ""
    # claude not installed (no install command in fake_runner.calls), status "Claude Code CLI" with CLAUDE_CLI_DECLINED
def test_yes_installs_like_codex(...):                 # yes=True: claude's install command runs, status CLAUDE_CLI_WHY
def test_no_terminal_installs_like_codex(...):         # interactive=False, yes=False: installs
def test_without_claude_cli_skips(...):                # claude_cli=False: no install, CLAUDE_CLI_DECLINED
def test_without_claude_cli_no_effect_warns(...):      # claude on PATH: problem line "--without-claude-cli: not used; ..."
def test_check_row_ok_optional(...):                   # check._binaries(): no "binary claude" row; a "Claude Code CLI" ok row whose detail is CLAUDE_CLI_DECLINED's optional wording
def test_next_names_extension_when_cli_skipped(...):   # "Next: open VS Code's Claude Code extension"
def test_cli_present_no_question_next_names_extension(...):  # Review Focus 5: ask never called; Next contains "run `claude`" and "Claude Code extension"
```

(Use the patterns of `tests/test_bootstrap_this_machine.py` and the existing Codex CLI tests — find them with `search_graph` on `codex_cli_choice`; patch `vscode.bundled_claude`/`use_bundled_claude` to return a fake path.)

- [ ] **Step 2: Run** — FAIL.

- [ ] **Step 3: Implement**: the choice before `check_prereqs`; its skip adds `"claude"` to `check_prereqs`' `skip`; status lines like Codex's (`warn` when skipped, `ok` when installed); replace the old `CLAUDE_BUNDLED` warn status where the choice already printed a line (keep `CLAUDE_BUNDLED` for the no-`--install` case); "Next": the Claude Code extension is named whenever `claude_bundled` was found (with `claude` on PATH: "run `claude` in a new terminal, or open VS Code's Claude Code extension (reload the window if it is open)"); same for Codex when its CLI and its extension are both there (`codex.extension_state()[0] is not None` and `mode() != "extension"`); `check._binaries`: a bundled claude gives `CheckResult("Claude Code CLI", True, <CLAUDE_CLI_DECLINED's text>)` instead of the warn row.

- [ ] **Step 4: Run** — PASS; full suite — green.

- [ ] **Step 5: Commit** `feat(bootstrap): decide the Claude Code CLI next to its VS Code extension like Codex's`

### Task 8: Docs and backlog

**Files:**
- Modify: `docs/reference/cli.md` (bootstrap flags incl. `--without-claude-cli`; check output: no `fix:` in calm mode, "Now do this" includes rows), `docs/reference/setup-matrix.md` (Claude Code × VS Code extension cell: CLI optional, question, flag — keep the `--install --agents claude` code span so `recommend.FLAGS` stays pinned), `docs/how-to/vscode.md` (Claude Code extension without the CLI), `docs/how-to/troubleshooting.md` (quotes of changed lines), `docs/how-to/install-with-an-agent.md` and `plugins/loadout/skills/configure/SKILL.md` (mention `--without-claude-cli` where `--without-codex-cli` is), `.superpowers/handoff/2026-10-13-hardening-backlog.md` (mark the tour entry's FIX PR part done).
- Test: `tests/test_recommend.py` (matrix pin), `tests/test_docs_links.py`.

- [ ] **Step 1:** Edit the docs (grep each changed message string and `--without-codex-cli` under `docs/` and `plugins/` to find every quote).
- [ ] **Step 2: Run** the full suite — Expected: green.
- [ ] **Step 3: Commit** `docs: tour fixes (to-do list, Claude Code CLI next to the extension)`
