# Init and profile output Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `loadout init` and `loadout profile` show a short plan (one line per file), ask once, and end with a status line plus numbered to-dos. A profile that is already applied here says so and asks nothing.

**Architecture:**
- `RepoWrites.render(calm=True)` drops the key lines of new files and of `.loadout.json`, and groups init's scaffold files.
- Codex refusals that only mean "Codex can't express this" become planned skips (`codex.Unsupported`), and the plan shows each one once.
- Notes the user must act on are marked `Todo`, and `_report` numbers them.
- `add_profile` checks the repo record plus this machine (plugins, the paths a command creates) before it plans.

**Tech Stack:** Python 3.11+, standard library only (`cli/loadout/`); pytest with `fake_home` and `fake_runner`.

**Spec:** `docs/superpowers/specs/2026-10-29-init-output-design.md`

## Global Constraints

- Standard library only. External commands run only through `runner.run`. Tests use `fake_home` and `fake_runner` and never run real `claude`, `codex`, `loadout` or installers.
- Test command: `uv run --python 3.12 --with pytest pytest -q --deselect "tests/test_docs_links.py::test_links_resolve[docs/examples/Niklas_Serena_Config.md]"`.
- Conventional Commits; no AI attribution.
- Calm mode means `not out.VERBOSE` (`project._calm()`). `--verbose` keeps today's full plan lines and every note.
- A `change` line of an existing file keeps its per-key lines in calm mode. Only `.loadout.json` is exempt.
- A `run` line always says that restore can't undo it.
- Code tools: codebase-memory (project `home-jonas-Documents-Code-agent-loadout`: `search_graph`, `trace_path`, `get_code_snippet`) and Serena `find_symbol` / `find_referencing_symbols` before grep.

## Review Focus

1. **An existing `.mcp.json` that a profile changes:** calm mode still lists the `+`/`~` key lines (Task 1 `test_calm_keeps_change_keys`).
2. **A profile MCP server with a plaintext secret** (a real `Refused`, not `Unsupported`): still `!` and exit 1 (Task 2 `test_real_refusal_still_fails`).
3. **A teammate clone:** the profile is recorded and the files are unchanged, but the Claude plugin is not installed for this project. The plan lists only that install, and the command asks (Task 5 `test_missing_plugin_is_planned`).
4. **A Codex-only repo, or Claude Code off for the user:** the done-check ignores Claude plugins, so "already applied" can still print (Task 5 `test_codex_only_ignores_claude_plugins`).
5. **No terminal:** `profile db --yes` with only the dbhub skip exits 0, and `--dry-run` on an already-applied profile prints the one line and exits 0 (Task 2 `test_planned_skip_exit_0_yes`, Task 5 `test_dry_run_already_applied`).

---

### Task 1: Calm plan lines

**Files:**
- Modify: `cli/loadout/repo_writes.py` (`Change`, `RepoWrites.create`, `RepoWrites.render`), `cli/loadout/scaffold.py` (its `w.create` calls and `ensure_gitignore`), `cli/loadout/project.py` (`_show`)
- Test: `tests/test_repo_writes.py`, plus updates to `tests/test_project.py` where it pins today's key lines in calm mode (assert them under `out.VERBOSE = True` instead)

**Interfaces:**
- Produces:
  - `Change.group: str | None = None`;
  - `RepoWrites.create(path, text, why, group=None)`;
  - `RepoWrites.render(calm: bool = False) -> list[str]`. `calm=False` is byte-identical to today (`new_skill` keeps it).
  - `project._show(project, title, w, notes, skips=())`: the signature gains `skips` in Task 2; in this task, pass `calm=_calm()` to `render`.

**Calm rules:**
- **Grouped creates.** All `create` changes with the same `group` share one line: `  create  A, B, C  <group>`. Scaffold and `.gitignore` creates pass `group="init"`.
- **`.loadout.json`.** A create or modify is one line: `  create|change  .loadout.json  what loadout wrote here (commit it)`, with no key lines.
- **Other new JSON files.** One line, no key lines. The label is `MCP servers: a, b` when the text has a `mcpServers` object; otherwise it is the profile names found in `why`, as `profile web` or `profiles web, db` (match `profile (\S+?)[:( ;]` in the why text). It falls back to the why's first clause, cut at `(`.
- **Unchanged rules.** `change` lines (other files), `copy` and `link` keep today's form.
- **`run` lines.** `  run     <cmd>  (<profile label>; restore can't undo it)`. A `run` with `touches` keeps `(<profile label>)`.
- **Plan title.** In calm mode it uses `project.name` instead of the full path.

- [ ] **Step 1: Write the failing tests** in `tests/test_repo_writes.py`:
  - `test_calm_new_json_one_line`: create `.mcp.json` with servers `chrome-devtools` and `dbhub`. The calm render is exactly one line, containing `.mcp.json` and `MCP servers: chrome-devtools, dbhub`. No line starts with `          +`.
  - `test_calm_groups_init_files`: three creates with `group="init"`. They give one line, with the paths comma-joined in plan order.
  - `test_calm_loadout_json_one_line`: create and modify of `.loadout.json` (with an existing file). Each gives one line, and no line contains `profiles.`.
  - `test_calm_keeps_change_keys`: modify an existing `.mcp.json` that adds one server. The `+ mcpServers.x.command` line is present in calm mode.
  - `test_calm_run_line`: `w.run(["playwright-cli","install","--skills"], "profile web (Web UI work: …)")` gives `run     playwright-cli install --skills  (profile web; restore can't undo it)`.
  - `test_verbose_render_unchanged`: `render()` and `render(calm=False)` for the same plan equal today's output (pin one create plus one run line, verbatim).
- [ ] **Step 2: Run** `uv run --python 3.12 --with pytest pytest -q tests/test_repo_writes.py`. Expected: the new tests FAIL (`render() got an unexpected keyword argument 'calm'`).
- [ ] **Step 3: Implement** the rules above. Then run `tests/test_project.py` and update the calm-mode assertions that pinned key lines.
- [ ] **Step 4: Run** the full suite. Expected: green.
- [ ] **Step 5: Commit** `fix(project): one line per file in the calm plan`

### Task 2: Planned skips

**Files:**
- Modify: `cli/loadout/codex.py` (the `Refused` raises at the "mixes text and a variable" (~404), "Codex mapping does not support" (~415), "does not expand ${…}" (~438) and "env … forwards a variable only under" (~467) checks), `cli/loadout/codex_project.py` (`_wanted`), `cli/loadout/project.py` (`_plan_profile`, `_after_apply`, `_profile_now`, `_show`, `init`, `add_profile`)
- Test: `tests/test_planned_skips.py` (new)

**Interfaces:**
- Produces:
  - `class codex.Unsupported(Refused)`: raised at exactly those four checks. Every other `Refused` stays as it is.
  - `codex_project.planned_skips(prof) -> list[str]`: the `skipped mcp …` lines that came from `Unsupported`, plus `codex.claude_only_line(pid)` lines, in `_wanted` order. `_wanted` keeps its return shape.
  - `project._show(..., skips: list[str] = ())` prints each as `  skip    <line with a leading "skipped " removed>`.
- Rule:
  - In a repo with Codex, `_plan_profile` returns planned skips separately: `(notes, failures, skips)`. Update both callers.
  - `_after_apply` and `_profile_now` drop any problem line equal to one of `planned_skips(prof)` (after the `skipped ` prefix).
  - A planned skip never sets `rc`/`ok` to a failure.

- [ ] **Step 1: Write the failing tests.** Each runs `project.add_profile` / `project.init` with `fake_home`, `fake_runner`, a Codex-on repo (`.loadout.json` agents claude, codex; `targets.codex_enabled` → True) and a test profile that copies `profiles/db.json`'s dbhub server:
  - `test_dbhub_skip_shown_once`: the plan has exactly one line starting `  skip    mcp dbhub: Codex does not expand`, and the whole output contains `Codex does not expand` exactly once.
  - `test_planned_skip_exit_0_yes`: `add_profile(..., approve=approver(True, ask, False))` returns 0, the status is `✓`, and the output has no "applied with problems".
  - `test_real_refusal_still_fails`: a profile server with `"env": {"API_KEY": "sk-live-abcdef0123456789"}` (a plaintext secret). It exits 1 and shows "applied with problems".
  - `test_claude_only_plugin_is_planned_skip`: a profile installing a plugin from `catalog.claude_only_plugins()` in a Codex repo gives one `skip` line and exit 0.
- [ ] **Step 2: Run** `uv run --python 3.12 --with pytest pytest -q tests/test_planned_skips.py`. Expected: FAIL (the skip is printed 3 times; exit 1).
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the full suite. Expected: green.
- [ ] **Step 5: Commit** `fix(project): a skip Codex can't express is planned, said once, not a problem`

### Task 3: Result as status + numbered to-dos; skill links without a second question

**Files:**
- Modify: `cli/loadout/project.py` (`_report`, `_after_apply`, `_plan_profile`, `init`, `add_profile`, `_profile_now`), `cli/loadout/wsl.py` only if `repo_note` needs to return a `Todo` (prefer wrapping at the call site)
- Test: `tests/test_project_result.py` (new); update the `tests/test_project.py` assertions on the "next:" line, the second link plan, and the note lines

**Interfaces:**
- Produces:
  - `class project.Todo(str)`: a note the user must act on.
  - `_report(title, bk, notes, problems, done: str = "applied", todos_after: list[str] = ()) -> int`.
  - `STILL_TO_DO = "Still to do:"`.
- Wrap these notes in `Todo(...)` where they are appended:
  - `codex_project.TRUST_NOTE`;
  - `note ({name}): {prof.notes}`;
  - the WSL repo note;
  - `plugin {pid}: {CLAUDE_OFF}`;
  - "Codex plugins of profile … off for you";
  - "no longer needed for this repo's agents (yours to remove)";
  - `skill_links.PREFIX` lines.
- **`_report` in calm mode** prints, in order:
  - the status line: `applied` or `applied (web, db)` (init passes `done`); `!` only when there are problems;
  - each problem;
  - each `backup: …` note, as is;
  - `Still to do:` with `  1. …` per unique `Todo`, in order, with the "next" item appended last via `todos_after`;
  - the `undo:` line.
- Other notes are hidden in calm mode.
- **`_report` in verbose mode** prints today's lines, then the same numbered list.
- `init`'s `next: …` text becomes the last to-do: `Start Claude Code here and run /loadout:onboard` / `Start Codex here and ask it to use the loadout:onboard skill`.
- `_after_apply` applies the follow-up skill links without `approve`. The `approve` parameter goes. It still stops on `later.stale`. In verbose mode it prints `later.render()` under `linked for the repo's other agent:`.

- [ ] **Step 1: Write the failing tests** (init with profiles `web` and `db` copied as test profiles, Codex on, `out.VERBOSE = False`, approve yes):
  - `test_init_result_lists_todos_once`: after `Still to do:`, there is one line containing `codex` and `trust`, one containing `DATABASE_URL`, and the last numbered line contains `/loadout:onboard`. The trust note appears once in the whole output.
  - `test_record_later_note_hidden_in_calm`: `RECORD_LATER`'s text is absent in calm mode and present with `out.VERBOSE = True`.
  - `test_skill_links_no_second_question`: a profile command (`fake_runner` side effect) creates `.claude/skills/x/SKILL.md` in a claude+codex repo. `ask` is called exactly once, and `.agents/skills/x` is a link afterwards.
  - `test_codex_backup_line_kept`: when `codex_project.plugins` returns a `backup: …` line, it is printed in calm mode.
- [ ] **Step 2: Run** `uv run --python 3.12 --with pytest pytest -q tests/test_project_result.py`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the full suite. Expected: green.
- [ ] **Step 5: Commit** `fix(project): end with a status line and numbered to-dos; link skills without asking again`

### Task 4: Profile `done_when`

**Files:**
- Modify: `cli/loadout/profiles.py` (`Profile`, `load_profile` validation), `profiles/web.json`, `docs/reference/profile-format.md`
- Test: `tests/test_profile_done_when.py` (new)

**Interfaces:**
- Produces: `Profile.done_when: list[str]`, made of repo-relative paths. A profile's commands count as done here when **any** of them exists in the repo. With no `done_when`, a recorded profile's commands count as done.
- `load_profile` refuses a non-list, a non-string item, an absolute path, or `..` (same error style as the other fields).
- `profiles/web.json`: `"done_when": [".claude/skills/playwright-cli", ".agents/skills/playwright-cli"]`.

- [ ] **Step 1: Write the failing tests:**
  - `test_done_when_loaded` (web has both paths);
  - `test_done_when_rejects_absolute_and_dotdot`.
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement**, and document the field in `profile-format.md`: the any-of rule, and what a profile without it means.
- [ ] **Step 4: Run** the full suite. Expected: green.
- [ ] **Step 5: Commit** `feat(profiles): done_when names what a profile's commands leave behind`

### Task 5: Already applied here

**Files:**
- Modify: `cli/loadout/project.py` (`add_profile`; new `missing_here`), `cli/loadout/__main__.py` (`profile --refresh`), `cli/loadout/commands.py` if it passes the flag through
- Test: `tests/test_profile_already_applied.py` (new)

**Interfaces:**
- Consumes: `Profile.done_when` (Task 4); `Todo` / `_report` (Task 3).
- Produces:
  - `project.missing_here(prof, project) -> list[str]`: the ids or commands this machine still lacks;
  - `ALREADY = "profile {name}: already applied here (nothing to change)"`;
  - `add_profile(..., refresh: bool = False)`.
- `missing_here` checks, each only when it applies:
  - Claude plugins: only when the repo has Claude Code and `targets.claude_enabled()`. Each valid `prof.install` id has an entry in `~/.claude/plugins/installed_plugins.json` with `scope` `project` or `local` and `projectPath` equal to the resolved project.
  - Codex plugins: only when the repo has Codex and `targets.codex_enabled()`. `codex_project._wanted(prof)[1]` minus `codex.installed_plugins()`. If that returns None, count them as missing.
  - Commands: when `prof.commands` and `done_when` are set and none of the paths exists, the commands are missing.
- **Flow in `add_profile`,** when `not refresh` and the name is in `repo_config.records(project)`, after `_plan_profile`:
  - if `w` has no `create`/`modify`/`copy`/`link` change and `missing_here` is empty: print `ALREADY` and return 0, before `_show`. This also applies to `dry_run`.
  - if there are no file changes but something is missing: drop the `run` changes whose result is present, then continue with `_show` and the question as usual.
- `--refresh` skips the check.
- `init` is unchanged; it always plans.

- [ ] **Step 1: Write the failing tests:**
  - `test_already_applied_no_question`: record web in `.loadout.json`, apply its files, create `.claude/skills/playwright-cli/`. Exit 0, the output is exactly the `ALREADY` line, `ask` is never called, and `fake_runner` ran nothing.
  - `test_dry_run_already_applied`: same, with `dry_run=True`.
  - `test_missing_plugin_is_planned`: android recorded, files present, `installed_plugins.json` without kotlin-lsp for this project. The plan has one `run` line `claude plugin install kotlin-lsp@claude-plugins-official --scope project`, and `ask` is called once.
  - `test_commands_rerun_when_done_when_missing`: web recorded, no skill folder. The plan has the `playwright-cli` run line.
  - `test_codex_only_ignores_claude_plugins`: a Codex-only repo with android recorded and the Codex plugin installed (`fake_runner` `codex plugin list` JSON). Prints `ALREADY`.
  - `test_refresh_runs_anyway`: `refresh=True` shows the plan with the run line.
- [ ] **Step 2: Run** `uv run --python 3.12 --with pytest pytest -q tests/test_profile_already_applied.py`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the full suite. Expected: green.
- [ ] **Step 5: Commit** `feat(profile): say "already applied" when the repo and this machine have it all; --refresh`

### Task 6: Docs

**Files:**
- Modify:
  - `docs/reference/cli.md` (`init` and `profile`: the calm plan shape, `skip` lines and exit 0 for them, the "Still to do" list, `profile --refresh`, "already applied");
  - `docs/tutorials/getting-started.md` and `docs/how-to/write-a-profile.md` (any pasted plan or result output);
  - `docs/how-to/troubleshooting.md` (the "run `loadout profile NAME` again" entry now names `--refresh` for a full re-run);
  - `docs/how-to/install-with-an-agent.md` and `plugins/loadout/skills/configure/SKILL.md`, only if they state the old exit code for skips or the second link question.
- Test: `tests/test_docs_links.py`, `tests/test_docs_commands.py`

- [ ] **Step 1: Edit** the pages. Find the pasted output with `grep -rn "Apply these changes\|applied with problems\|next: start" docs plugins/loadout/skills`.
- [ ] **Step 2: Run** the docs tests and the full suite. Expected: green.
- [ ] **Step 3: Commit** `docs: short init and profile output, --refresh, already applied`
