# Smooth update Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `loadout update` brings a machine fully current with one plan and one question, shows live progress, and ends with "What changed" and a numbered "Now do this" per agent that also reaches each agent's next session.

**Architecture:** A waiting lock module and a live progress line come first; then the pull stops pausing on harmless local changes; bootstrap's apply steps move into a shared `apply.py` that both bootstrap and update call; Codex skips marketplaces and plugins whose upstream did not change; a new `update.py` builds the numbered plan, runs it after the pull and a restart into the pulled code, and derives "Now do this" steps that `steps.py` stores per agent for the session-start hook.

**Tech Stack:** Python 3.11+ standard library (`cli/loadout/`), pytest with the `fake_home` and `fake_runner` fixtures.

**Spec:** `docs/superpowers/specs/2026-10-19-smooth-update-design.md`. Code facts with line numbers were gathered on 2026-10-19 (base 7cf02eb); the executor re-reads each named function before changing it.

## Global Constraints

- Python 3.11+, standard library only in `cli/loadout/`; external commands only through `runner.run` with argument lists (the restart in Task 9 replaces the process like `bin/loadout`'s `continue_under`, never a shell).
- With an agent off (`targets.json`), nothing reads or changes that agent's files.
- loadout changes only what it recorded as its own; text the user wrote stays byte for byte; exact-text record, parse guard, atomic write; a backup step before every removal or overwrite.
- Every printed path or name that comes from a file or a command is escaped with `out.printable`.
- Tests use `fake_home` and `fake_runner`; nothing reaches the real `~/.claude`, `~/.claude.json`, `~/.codex` or `~/.config/loadout`, and no real `claude`, `codex` or installer runs.
- Windows CI: POSIX-only tests skip on `os.name == "nt"`; bundled binaries via `host_codex_bin()`/`host_claude_bin()`; byte comparisons for CRLF files.
- Conventional Commits, no AI attribution lines.
- Copy fixed by the spec: the prompt `Apply all? [Y/n, or the numbers to leave out, e.g. 3 5]`; the wait line `waiting for the other loadout run (<command>, started <HH:MM>)…`; the block headings `What changed` and `Now do this`.
- ADR 0011 stays intact: the plan shows each tool's exact command before it runs (Ruling: the spec's "raw commands behind --verbose" applies to run-time output only).

## Review Focus

1. A kit checkout on a feature branch with local edits (the developer's own clone): the pull must refuse cleanly through git and never touch the work; pinned in Task 5 (`test_a_refused_pull_names_the_files_and_changes_nothing`).
2. Ctrl+C while waiting for a lock or during the live progress line: the terminal line is cleared and the usual interrupt message and exit 130 follow; pinned in Task 3 and Task 4.
3. Piped output and CI logs (no terminal): no ticker thread, no carriage returns, one line per item; pinned in Task 4 (`test_no_tty_prints_plain_lines_without_a_thread`).
4. An update interrupted after the pull but before the restart, run again: it must not pull twice into a half state, and the plan is built from the pulled code; pinned in Task 9 (`test_a_second_run_after_an_interrupted_one_starts_cleanly`).
5. An agent that is off: update's plan, steps and notices name nothing of it; pinned in Task 8 and Task 10.

---

### Task 1: Bug 22, a user's own Serena in config.toml is not an own tool

**Files:**
- Modify: `cli/loadout/inventory.py` (`_codex_items`)
- Test: `tests/test_codex_adopt.py`

**Interfaces:**
- Consumes: `codex.is_serena(table: dict) -> bool` (existing).
- Produces: nothing new.

- [ ] **Step 1: Write the failing test** `test_a_users_own_serena_is_not_an_own_tool` in `tests/test_codex_adopt.py` (fixture `codex_on`, helper `_config`): write `[mcp_servers.serena]\ncommand = "serena"\nargs = ["start-mcp-server", "--project-from-cwd", "--context=codex"]\n` plus `[mcp_servers.my-serena]` with `command = "uvx"`, `args = ["--from", "git+https://github.com/oraios/serena", "serena", "start-mcp-server"]`, no record; assert `[i for i in inventory.items() if i.location == codex.CONFIG_LOCATION] == []` (use the item accessor the neighbouring tests use).
- [ ] **Step 2: Run** `uv run --python 3.12 --with pytest pytest -q tests/test_codex_adopt.py -k own_serena` — Expected: FAIL, two items found.
- [ ] **Step 3: Skip** tables where `codex.is_serena(table)` in `inventory._codex_items`.
- [ ] **Step 4: Run** the test file — Expected: PASS.
- [ ] **Step 5: Commit** `fix(adopt): a Serena set up with serena setup codex is the kit's tool, not an own tool`

### Task 2: Keep a hooks.json's own format when adding Serena's hooks

**Files:**
- Modify: `cli/loadout/jsonio.py` (`JsonStyle`, `json_style`, `dumps_like`), `cli/loadout/codex_hooks.py` (`apply`, the `canonical` closure and the "another format" branch)
- Modify docs: `docs/reference/hooks.md` (section "Serena's hooks in Codex"), `docs/how-to/troubleshooting.md` (rows on `Codex Serena hooks: … add these yourself`)
- Test: `tests/test_json_style.py`, `tests/test_codex_serena_hooks.py`

**Interfaces:**
- Produces: `JsonStyle(indent, newline, final_newline, ensure_ascii: bool = False)`; `json_style(text: str) -> JsonStyle | None` tries `ensure_ascii` False then True for each indent; `dumps_like(style: JsonStyle, data) -> str` honours `ensure_ascii`.

- [ ] **Step 1: Tests.** In `tests/test_json_style.py`: `test_style_detects_ensure_ascii` (a 4-space file with `"\\u00e9"` round-trips with `ensure_ascii=True`). In `tests/test_codex_serena_hooks.py`: `test_a_four_space_file_gets_the_hooks_in_its_own_format` (write the user's file as `json.dumps(data, indent=4) + "\n"`; after `apply`, the file is `json.dumps(new, indent=4) + "\n"`, all six commands present, user entries unchanged, `backup.restore` gives the original bytes), `test_a_crlf_four_space_file_keeps_crlf`, and change `test_a_file_in_another_format_is_not_rewritten` to a layout `json_style` cannot reproduce (3-space indent) so it still asserts the file is untouched and the "add these yourself" line.
- [ ] **Step 2: Run** both files — Expected: the new tests FAIL.
- [ ] **Step 3: Implement.** `codex_hooks.apply` writes with `dumps_like(json_style(old), data)` when `old` is non-empty and `json_style(old)` is not None and `dumps_like(style, json.loads(old)) == old`; an empty or missing file keeps today's indent-2 LF form; only when the style is None does it return today's "add these yourself" line. Backup and ownership record unchanged.
- [ ] **Step 4: Run** `tests/test_json_style.py tests/test_codex_serena_hooks.py tests/test_profile_three_way.py tests/test_repo_config*.py` — Expected: PASS (the other `json_style` users unchanged).
- [ ] **Step 5: Docs.** hooks.md: loadout adds the entries in the file's own format (indent, line endings, ASCII escapes), backup first; it lists them only when it cannot reproduce the file. Troubleshooting rows say the same.
- [ ] **Step 6: Commit** `feat(codex): add Serena's hooks to a hooks.json in its own format, with a backup`

### Task 3: Locks that wait for the other run

**Files:**
- Create: `cli/loadout/locks.py`
- Modify: `cli/loadout/maintenance.py` (`_acquire_lock`, `_own_lock`, `_touch_lock`, `_release_lock`, `update`, `_update_plugins` message at the Codex lock), `cli/loadout/codex.py` (`_lock`, `apply_all` message), `cli/loadout/out.py` (a `waiting` line)
- Modify docs: `docs/reference/state-and-sync.md` (lock paragraph), `docs/reference/personal-layer.md` (lock rows), `docs/reference/cli.md` (`loadout update` exit codes), `docs/how-to/troubleshooting.md` (new row for the wait line)
- Test: create `tests/test_locks.py`; update `tests/test_codex_progress.py::test_a_second_run_waits_its_turn`

**Interfaces:**
- Produces:
  - `locks.acquire(name: str, command: str, wait: float | None, *, stale: float = 3600.0) -> Lock | None` — `wait=0`: one try; `wait=None`: wait until free; a number: seconds. Content JSON `{"pid", "token", "command", "started"}`; a plain-pid file from an older loadout is read as held by `"loadout"` since its mtime. Stale takeover renames the file aside first (today's maintenance pattern).
  - `Lock.touch() -> None`, `Lock.release() -> None` (releases only its own token).
  - `locks.holder(name: str) -> tuple[str, float] | None` (command, started epoch).
  - `out.waiting(command: str, started: float, elapsed: float) -> None` — on a terminal one in-place line `waiting for the other loadout run (<command>, started <HH:MM>)… <n>s`; off a terminal printed once.
- Lock names stay `maintenance.lock` and `codex.lock` (migrate.TRANSIENT and personal-layer.md list them). Order stays maintenance then codex.
- Waits: foreground commands (`update`, `bootstrap`, `configure`, `configure set target codex on`) wait with `None` on a terminal and `600` seconds without one; `maintain` (background) and `codex.refresh_instructions` (session start) use `0` and stay silent.
- After the limit without a terminal: `the other loadout run (<command>, started <HH:MM>) is still running; run this again when it has finished`, exit 1 (`update`) or a problem line (`apply_all`).

- [ ] **Step 1: Tests** in `tests/test_locks.py`: `test_acquire_writes_who_holds_it` (holder returns `("update", started)`), `test_a_second_acquire_waits_then_gets_it` (a thread releases after 0.3 s; `acquire(..., wait=5)` returns a Lock; `time.monotonic` delta >= 0.3), `test_wait_zero_gives_up_at_once`, `test_a_stale_lock_is_taken_over`, `test_an_old_plain_pid_lock_counts_as_held`, `test_release_leaves_someone_elses_lock`, `test_ctrl_c_while_waiting_clears_the_line` (monkeypatch the sleep to raise `KeyboardInterrupt`; capsys shows the line ended; the exception propagates). Update `test_a_second_run_waits_its_turn` to expect the wait and then success when the holder releases, and the limit message when it does not (monkeypatch the limit to 0.1 s).
- [ ] **Step 2: Run** `tests/test_locks.py tests/test_codex_progress.py` — Expected: FAIL (module missing).
- [ ] **Step 3: Implement** `locks.py` and route the two existing locks through it; replace the three "another loadout run … run this again" messages with the wait.
- [ ] **Step 4: Run** `tests/test_locks.py tests/test_codex_progress.py tests/test_maintenance.py tests/test_migrate_state.py` — Expected: PASS.
- [ ] **Step 5: Docs** as listed; troubleshooting row: symptom = the wait line, fix = nothing to do (it continues by itself); Ctrl+C stops it.
- [ ] **Step 6: Commit** `feat: a second loadout run waits for the first instead of skipping`

### Task 4: A live progress line with elapsed time

**Files:**
- Modify: `cli/loadout/out.py`
- Test: create `tests/test_out_progress.py`

**Interfaces:**
- Produces: `out.step(label: str, total: int | None = None, slow: str | None = None) -> Step` context manager; `Step.item(text: str) -> None` (sets the current item, n of total); on a terminal and not `VERBOSE` a daemon ticker thread rewrites `<label>: <item> (<n> of <total>) <s>s` once a second under a `threading.Lock`; `slow` is printed once as a plain line when the step starts; leaving the context (normally or by exception, including `KeyboardInterrupt`) stops the thread and clears the line. Off a terminal or with `VERBOSE`: no thread, one plain line per `item`. `progress`/`end_progress` keep their behaviour; `say` callbacks used by `codex.apply_plugins` and `bootstrap.setup_plugins` can be `step.item`.
- Prompts: `update.py` (Task 8) leaves every `Step` before calling `ask`.

- [ ] **Step 1: Tests:** `test_tty_step_shows_elapsed_seconds` (monkeypatch `out._tty` True, `VERBOSE` False, a fake clock; after two ticks the written text contains `(2 of 3)` and `2s`), `test_no_tty_prints_plain_lines_without_a_thread` (`threading.active_count()` unchanged; output has no `\r`), `test_slow_note_is_printed_once`, `test_an_exception_inside_the_step_clears_the_line_and_stops_the_thread`.
- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement** `out.step`; inject the clock and the tick interval as module-level names so tests can set them.
- [ ] **Step 4: Run** `tests/test_out_progress.py tests/test_codex_progress.py tests/test_progress_and_codex_hint.py` — Expected: PASS.
- [ ] **Step 5: Commit** `feat(out): a live progress line with the item count and elapsed seconds`

### Task 5: The pull pauses only when git refuses, and names the files

**Files:**
- Modify: `cli/loadout/maintenance.py` (`pull_if_clean` becomes a wrapper of `pull`), `cli/loadout/check.py` (`_repos`)
- Modify docs: `docs/reference/state-and-sync.md` (the daily pull), `docs/explanation/architecture.md` (the daily sync sentence and the diagram alt text), `docs/diagrams/architecture-daily-sync.mmd` and its SVGs (use the `diagrams` skill), `docs/reference/cli.md` (`kit repo clean`/`personal repo clean` rows), `docs/how-to/troubleshooting.md` (the paused-sync row), `docs/reference/personal-layer.md` (state file)
- Test: `tests/test_maintenance.py`, a check test next to the existing `_repos` tests

**Interfaces:**
- Produces: `maintenance.PullResult(pulled: bool, paused: str | None, files: list[str])`; `maintenance.pull(root: Path) -> PullResult`; `maintenance.paused() -> dict[str, dict]` reading `paths.state_dir() / "sync-paused.json"` (`{str(root): {"reason": str, "files": [...], "at": epoch}}`), written on a refusal, removed on the next successful or no-op pull.
- `pull` runs no `status --porcelain` gate. It skips with its own reason when HEAD is detached (`git symbolic-ref -q HEAD` fails) or there is no upstream (`git rev-parse --abbrev-ref @{u}` fails); these are not "paused". Then `git -c core.quotePath=false -C <root> pull --ff-only -q` with env `GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=never`, `LC_ALL=C`. A refusal whose stderr lists files (tab-indented lines after "would be overwritten by merge:") records `reason` "local changes the pull would overwrite" with those files; a non-fast-forward records "your branch and its upstream have diverged"; any other failure records the first stderr line (escaped).
- The notice (queued once per new refusal): `loadout: the daily sync of <root> paused: <reason>: <files>; commit or stash them, then run loadout update`.
- `check._repos`: dirty alone is no longer a warning; a recorded pause is a warning with that detail and fix.

- [ ] **Step 1: Tests:** `test_untracked_files_do_not_pause_the_pull` (status shows `?? x`; pull is called; `paused()` empty), `test_a_refused_pull_names_the_files_and_changes_nothing` (pull returns the code-1 stderr with `\t.serena/project.yml`; result `paused` set, `files == [".serena/project.yml"]`; record written; notice text exact; no other git command after the refusal), `test_the_pull_env_forces_english_and_no_prompts` (LC_ALL=C plus the two existing vars), `test_no_upstream_is_skipped_not_paused`, `test_a_later_good_pull_clears_the_pause`, `test_check_names_the_paused_files` (escaped control characters in a file name).
- [ ] **Step 2: Run** `tests/test_maintenance.py` and the check test — Expected: FAIL.
- [ ] **Step 3: Implement** `pull` and the record; `_maintain` uses `pull(...).pulled`.
- [ ] **Step 4: Run** `tests/test_maintenance.py tests/test_check*.py` — Expected: PASS.
- [ ] **Step 5: Docs** as listed; architecture.md: the pull is fast-forward only and git refuses on its own when a local change would be overwritten, so it never overwrites your work; untracked files and unrelated edits no longer pause it. Re-render the daily-sync diagram and run `tests/test_diagrams.py`.
- [ ] **Step 6: Commit** `feat(sync): pull past untracked files and unrelated edits; a refusal names the files`

### Task 6: Shared apply steps for bootstrap and update

**Files:**
- Create: `cli/loadout/apply.py`
- Modify: `cli/loadout/bootstrap.py` (`_bootstrap` Links, Settings, Marketplaces and plugins, Codex steps; `check_prereqs` split), `cli/loadout/configure.py` (`apply_all`), `cli/loadout/codex.py` (`apply_all` gets `apply_parts`; split flags)
- Test: create `tests/test_apply_steps.py`; existing bootstrap and configure tests must stay green unchanged

**Interfaces:**
- Produces:
  - `apply.StepResult(name: str, summary: str, lines: list[str], facts: set[str], level: str = "ok")`.
  - `apply.link_step(bk: Backup, claude_on: bool, retry_symlinks: bool = False) -> StepResult` (`link.link_all` when Claude Code is on, `link.link_bin`).
  - `apply.settings_step(bk: Backup) -> StepResult` (the `would_change`/`save_copy`, `backup_snapshot`, `apply_settings`, `personal_mcp.apply_mcp` sequence).
  - `apply.claude_plugins_step(say=None, dry: bool = False) -> StepResult` (`bootstrap.setup_plugins`; `dry=True` returns the marketplaces to add and plugins to install as `lines` without running anything).
  - `apply.codex_step(bk: Backup, *, refresh_plugins: bool, auto: bool, keep: bool, say=None, skip_unchanged: bool = False, dry: bool = False) -> StepResult`.
  - `codex.apply_parts(bk, *, refresh: bool, auto: bool, keep: bool, say=None, skip_unchanged: bool = False) -> dict[str, list[str]]` with keys `instructions`, `config`, `hooks`, `skills`, `plugins`, under the Codex lock; `codex.apply_all(bk, refresh=False, say=None)` keeps its list return and today's flag coupling (`auto=refresh`, `keep=refresh`) for its callers.
  - `bootstrap.missing_tools(skip: set[str], recommended: set[str]) -> list[tuple[dict, list[list[str]], bool]]` (entry, install commands, optional) and `bootstrap.install_tool(entry: dict, cmds: list[list[str]]) -> tuple[bool, list[str]]`; `check_prereqs` uses both with no behaviour change.
  - Fact names (strings): `settings_changed`, `mcp_changed`, `claude_plugins_installed`, `claude_marketplace_added`, `codex_block_written`, `codex_config_changed`, `serena_hooks_added`, `codex_hooks_removed`, `codex_skills_linked`, `codex_plugins_installed`, `codex_plugins_updated`, and `failed:<step>`.
- `bootstrap._bootstrap` and `configure.apply_all` print exactly what they print today (their tests are the guard).

- [ ] **Step 1: Tests** in `tests/test_apply_steps.py`: each step's facts from fake_runner outputs (for example `codex_step` with an `instructions written to …` line gives `codex_block_written`; `claude_plugins_step(dry=True)` runs no `claude plugin install`; an agent that is off yields an empty `StepResult` and no file reads of that agent).
- [ ] **Step 2: Run** — Expected: FAIL (module missing).
- [ ] **Step 3: Implement** `apply.py`, `codex.apply_parts`, the `check_prereqs` split; switch bootstrap and configure to the shared steps.
- [ ] **Step 4: Run** the whole suite `uv run --python 3.12 --with pytest pytest -q` — Expected: PASS, bootstrap and configure output unchanged.
- [ ] **Step 5: Commit** `refactor: bootstrap's apply steps as shared functions with the facts they changed`

### Task 7: Codex refreshes only marketplaces and plugins that changed upstream

**Files:**
- Modify: `cli/loadout/codex.py` (`_install_routes`, `apply_plugins`/`apply_parts` `skip_unchanged`, new helpers)
- Modify docs: `docs/reference/cli.md` (`loadout update`), `docs/reference/personal-layer.md` (state file)
- Test: `tests/test_codex_plugins.py`

**Interfaces:**
- Produces: `codex.marketplaces() -> dict[str, dict] | None` from `codex plugin marketplace list --json` (name → root, source URL); `codex.remote_head(url: str, ref: str | None) -> str | None` via `runner.run(["git", "ls-remote", url, ref or "HEAD"], timeout=30)` with the no-prompt env (None when it fails); the record `paths.state_dir() / "codex-marketplaces.json"`: `{"<owner/repo>": {"name": str, "url": str, "head": str, "at": epoch, "plugins": {"<pid>": {"url": str, "ref": str | None, "head": str}}}}`, written only after a successful add/upgrade or plugin add; `codex.unchanged_routes(routes) -> tuple[set[str], set[str]]` (marketplaces and plugin ids that can be skipped).
- Rules: a marketplace is skipped when its remote head equals the recorded head, it appears in `marketplaces()`, and every wanted plugin of it is installed. A plugin whose `marketplace.json` source is a dict without `sha` is compared by its own remote head; in-repo paths and dicts with `sha` are covered by the marketplace head. Anything that cannot be compared (ls-remote fails, no record, unparsable list) is refreshed as today. `skip_unchanged` is False for bootstrap and the daily sync (no behaviour change there) and True for update.

- [ ] **Step 1: Tests:** `test_an_unchanged_marketplace_is_not_upgraded_or_re_added` (responses for `("git","ls-remote")` returning the recorded head and `("codex","plugin","marketplace","list")`; assert no `marketplace upgrade` and no `plugin add` calls), `test_a_changed_plugin_source_is_re_added_alone`, `test_ls_remote_failure_refreshes_as_today`, `test_the_record_is_written_only_after_success`.
- [ ] **Step 2: Run** `tests/test_codex_plugins.py` — Expected: FAIL.
- [ ] **Step 3: Implement** the helpers and the skip in `_install_routes`.
- [ ] **Step 4: Run** `tests/test_codex_plugins.py tests/test_codex_progress.py tests/test_plugin_refresh.py` — Expected: PASS.
- [ ] **Step 5: Commit** `feat(codex): refresh only marketplaces and plugins whose upstream changed`

### Task 8: The update plan and its one question

**Files:**
- Create: `cli/loadout/update.py`
- Modify: `cli/loadout/maintenance.py` (`_remember_refused`, `worth_notifying`), `cli/loadout/commands.py` (`update` gets `--verbose`)
- Test: create `tests/test_update_plan.py`

**Interfaces:**
- Consumes: Task 6 `apply.*_step(dry=True)`, `bootstrap.missing_tools`; Task 7 `codex.unchanged_routes`; `maintenance.find_outdated`, `pkgmgr.update_plan`.
- Produces:
  - `update.PlanItem(n: int, kind: str, label: str, commands: list[list[str]], optional: bool = False, key: str = "")` (kinds: `reapply`, `claude-plugin-install`, `claude-plugins-refresh`, `codex-plugins`, `tool-update`, `tool-install`).
  - `update.build_plan(claude_on: bool, codex_on: bool) -> list[PlanItem]`; re-apply is always item 1; Codex marketplaces show "refresh N, skip M (unchanged since <date>)"; each tool item shows `id: a -> b (via how)` and its exact command lines (ADR 0011); new recommended tools are `optional=True` and left out by default.
  - `update.render(plan) -> list[str]`.
  - `update.choose(plan, answer: str) -> list[PlanItem] | None` — `""`/`y`/`yes` → all non-optional plus optional ones named; `n`/`no` → none; space- or comma-separated numbers → all non-optional except those numbers (an optional item's number keeps it); anything else → None (ask again, as `restore_cmd` does).
  - `maintenance.decline(tool_id: str, version: tuple) -> None` writing `paths.state_dir() / "declined-updates.json"` (`{id: "x.y.z"}`); `worth_notifying` drops an entry when declined[id] >= the offered latest, for mise tools too; an update that installs the version removes the entry.
- Prompt: exactly `Apply all? [Y/n, or the numbers to leave out, e.g. 3 5] `; `--yes` takes all non-optional items; no terminal and no `--yes`: print the plan and `nothing changed (run loadout update --yes to apply)`, return 0.

- [ ] **Step 1: Tests:** `test_plan_numbers_items_and_shows_each_tool_command`, `test_answer_numbers_leave_items_out`, `test_a_bad_answer_asks_again`, `test_n_declines_and_the_weekly_notice_goes_quiet_until_newer` (decline 1.0.1; `worth_notifying` with latest 1.0.1 drops it, with 1.0.2 keeps it, also for a mise entry), `test_without_a_terminal_the_plan_is_shown_and_nothing_runs`, `test_an_agent_that_is_off_is_not_in_the_plan`.
- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement** `update.py` plan, render, choose; `decline`; `--verbose` on the `update` parser setting `out.VERBOSE`.
- [ ] **Step 4: Run** `tests/test_update_plan.py tests/test_maintenance.py` — Expected: PASS.
- [ ] **Step 5: Commit** `feat(update): one numbered plan and one question, numbers leave items out`

### Task 9: The update run: pull, restart, apply, summary

**Files:**
- Modify: `cli/loadout/update.py` (`run`), `cli/loadout/maintenance.py` (`update` delegates to `update.run`; `_update`/`_update_plugins` move into or are called from `update.py`), `cli/loadout/commands.py`
- Modify docs: `docs/reference/cli.md` (`loadout update` section rewritten; `LOADOUT_UPDATE_PULLED` next to `LOADOUT_REEXEC`), `docs/how-to/troubleshooting.md` (`Codex instructions` row fix becomes `loadout update`)
- Test: create `tests/test_update_run.py`

**Interfaces:**
- Consumes: Tasks 3-8.
- Produces: `update.run(yes: bool, ask, *, argv: list[str]) -> int`; `update.Summary(changed: list[str], failed: list[tuple[str, str]], steps: dict[str, list[str]])`; module-level `update._exec(argv: list[str]) -> NoReturn` (POSIX `os.execv(sys.executable, [sys.executable, <kit>/bin/loadout, *argv])`, Windows `sys.exit(subprocess.call(...))`), injectable in tests.
- Order: maintenance lock (wait) → unless `LOADOUT_UPDATE_PULLED=1`: `pull` kit and personal layer (Task 5); if the kit HEAD moved: release the lock, set `LOADOUT_UPDATE_PULLED=1`, `_exec(["update", *flags])` → plan and question (Task 8) → `apply.link_step`, `settings_step`, `claude_plugins_step`, `codex_step(refresh_plugins=True, auto=False, keep=False, skip_unchanged=True)` inside `out.step` lines → Claude Code `claude plugin marketplace update` and `claude plugin update` for chosen plugins → chosen tool updates and installs (today's refused bookkeeping plus `decline` for left-out items) → settings guard and `undo_reregistered` (today's code) → `check.run_checks()` one-line health summary → "What changed" (one plain line per fact and per updated tool, failed items with their fix, each backup with `loadout restore <path>`) → "Now do this" from Task 10 → return 0 (1 only when the lock wait hits its limit).
- Never re-exec when `LOADOUT_UPDATE_PULLED=1` is already set; the variable is not `LOADOUT_REEXEC` (that one is set in every test and after the old-Python restart).

- [ ] **Step 1: Tests:** `test_update_reapplies_the_codex_block` (stale block; after `run(True, …)` the block is current and "What changed" names it — today's scenario), `test_a_kit_pull_restarts_into_the_new_code_once` (fake `_exec` records argv and env; second call with the variable set does not pull), `test_a_personal_only_pull_does_not_restart`, `test_a_second_run_after_an_interrupted_one_starts_cleanly` (lock left by a dead pid is taken over; no double pull), `test_what_changed_names_each_backup_with_its_undo`, `test_a_failed_step_is_listed_as_failed_with_its_fix`, `test_codex_only_touches_no_claude_files`.
- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement** `update.run`; `maintenance.update` calls it; keep `_update`'s settings guard and dedupe as they are.
- [ ] **Step 4: Run** the whole suite — Expected: PASS; `tests/test_plugin_refresh.py` and `tests/test_update_dedupe.py` adapted only where they asserted the old per-group prompts.
- [ ] **Step 5: Docs** as listed.
- [ ] **Step 6: Commit** `feat(update): one command that pulls, restarts into the new code, re-applies and reports`

### Task 10: "Now do this", per agent, until done

**Files:**
- Create: `cli/loadout/steps.py`
- Modify: `cli/loadout/maintenance.py` (`session_start(now, agent)`), `cli/loadout/commands.py` (`hook-session-start --agent`), `plugins/loadout/hooks/hooks.json` and `plugins/loadout/hooks/codex.json` (pass `--agent claude` / `--agent codex`), `cli/loadout/bootstrap.py` (its "Still to do" uses the same steps), `cli/loadout/update.py` (prints them)
- Modify docs: `docs/reference/hooks.md` (the session-start row), `docs/reference/state-and-sync.md` (session start), `docs/reference/personal-layer.md` (`open-steps.json`), `docs/reference/cli.md`
- Test: create `tests/test_open_steps.py`; update `tests/test_hooks.py`, `tests/test_codex_hooks.py` manifest assertions

**Interfaces:**
- Consumes: Task 9 `Summary` facts and the tool loop's upgraded binaries.
- Produces:
  - `steps.Step(id: str, agent: str, text: str, reason: str)`.
  - `steps.derive(facts: set[str], upgraded: list[str], claude_on: bool, codex_on: bool) -> list[Step]`: Claude Code plugins installed or updated, or the loadout plugin copy differs from the kit afterwards → `claude/reload-plugins` "run /reload-plugins (or restart Claude Code)"; an upgraded binary that starts an MCP server → `claude/mcp:<name>` "run /mcp and reconnect <name> (it was upgraded)" and `codex/restart` "restart Codex"; Codex plugins or hooks changed, Serena's hooks added, or `codex.hooks_status()` in `("untrusted", "changed")` → `codex/hooks` "start codex and approve the changed hooks in /hooks"; a bootstrap-only need seen in the health check (PATH, secrets, VS Code PATH rows failing) → `<agent>/bootstrap` "run loadout bootstrap".
  - `steps.mcp_servers_started_by(binary_id: str) -> dict[str, list[str]]` comparing the command basename (minus `.exe`, and `uv`/`uvx` args as in `codex.is_serena`) across the loadout plugin's `.mcp.json`, `~/.claude.json` (Claude Code on), personal `mcp.json`, Codex `config.toml` (Codex on) and Codex plugin servers.
  - `steps.save(new: list[Step]) -> None` merging by id into `paths.state_dir() / "open-steps.json"` (`{"claude": [...], "codex": [...]}`); `steps.pending(agent: str) -> list[Step]`; `steps.clear(agent: str, ids: set[str]) -> None`.
  - `maintenance.session_start(now, agent: str | None = None)`: with an agent, appends that agent's pending steps to the `systemMessage`; Claude Code steps clear only when the hook's stdin JSON has `"source": "startup"` (not resume, clear or compact); Codex: `codex/restart` clears at a Codex session start, `codex/hooks` clears when `hooks_status()` is `"trusted"`. Without an agent (an older plugin copy), today's behaviour.
  - Output block (update and bootstrap): `Now do this` then `  1. Claude Code: …`, `  2. Codex: …`, numbered across agents, only steps of agents that are on.
- The `codex.json` change makes Codex ask for one `/hooks` re-approval; `derive` names it through `hooks_status() == "changed"`.

- [ ] **Step 1: Tests:** `test_an_upgraded_mcp_binary_gives_a_reconnect_step`, `test_claude_steps_clear_only_at_a_fresh_start` (stdin source `resume` keeps them, `startup` clears), `test_codex_hooks_step_clears_when_trusted`, `test_a_codex_session_does_not_see_or_clear_claude_steps`, `test_steps_of_an_agent_that_is_off_are_never_shown`, `test_an_old_hook_without_agent_keeps_todays_behaviour`, manifest tests: hooks.json passes `--agent claude`, codex.json passes `--agent codex`.
- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement** `steps.py`, the `--agent` argument (optional), the manifests, `session_start`, and the printing in update and bootstrap.
- [ ] **Step 4: Run** the whole suite and `claude plugin validate plugins/loadout` — Expected: PASS.
- [ ] **Step 5: Docs** as listed.
- [ ] **Step 6: Commit** `feat: "Now do this" steps per agent, shown at its next session until done`

### Task 11: ADR and the remaining docs

**Files:**
- Create: `docs/adr/0035-loadout-update-brings-a-machine-current.md`
- Modify: `docs/adr/0015-claude-code-installs-synced-plugins.md` and `docs/adr/0024-codex-parity-update-model.md` (status line only: "amended by 0035"), `docs/adr/README.md` (index), `docs/explanation/architecture.md` (update's place), `docs/how-to/vscode.md` / `docs/tutorials/getting-started.md` where they name "run loadout bootstrap" after an update, `AGENTS.md` only if the module map link needs `update.py`, `apply.py`, `locks.py`, `steps.py` (they go into `docs/reference/modules.md`)
- Test: `tests/test_docs_links.py`, `tests/test_docs_commands.py`

**Interfaces:**
- ADR 0035 Decision: `loadout update` is the one deliberate command that brings a machine current: it pulls (asking nothing, as the daily sync), restarts into the pulled code, shows one numbered plan with each command (ADR 0011), and after one yes re-applies the setup, installs new kit plugins and required tools and refreshes the rest; the daily sync still installs nothing; the pull pauses only when git refuses. Amends 0015 (loadout installs new kit plugins on update) and 0024 (update covers more than refresh).

- [ ] **Step 1:** Write the ADR (Status, Context with today's five-command scenario, Decision, Consequences including the one `/hooks` re-approval and the dirty-checkout change); status lines on 0015 and 0024; index row.
- [ ] **Step 2:** `docs/reference/modules.md`: rows for `apply.py`, `locks.py`, `steps.py`, `update.py`.
- [ ] **Step 3:** Run `uv run --python 3.12 --with pytest pytest -q tests/test_docs_links.py tests/test_docs_commands.py tests/test_docs_vscode.py tests/test_diagrams.py` — Expected: PASS.
- [ ] **Step 4:** Run the `loadout:docs-sync` skill over the branch and fix what it finds.
- [ ] **Step 5: Commit** `docs: ADR 0035, loadout update brings a machine current`
