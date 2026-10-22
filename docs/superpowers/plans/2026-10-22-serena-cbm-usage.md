# Serena and codebase-memory get used: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agents and subagents in Claude Code and Codex call Serena and codebase-memory directly, get Serena's own `remind` when they drift into grep/Read, and never query a stale graph, in every setup loadout supports.

**Architecture:**
- The plugin's hook files carry Serena's and codebase-memory's documented hooks. They run through one stdlib guard script (`hooks/mcp_guard.py`), which stays silent when the tool is not available or the user already runs an equivalent hook.
- `alwaysLoad` in the plugin's `.mcp.json` removes the ToolSearch step.
- A stdlib refresh hook (`hooks/refresh.py`) re-indexes codebase-memory in the background at change points.
- loadout's CLI gets:
  - a search parser module that `loadout usage` uses;
  - a `cbm_auto_index` preference applied as an undoable command;
  - check rows for the new states.

**Tech Stack:** Python 3.11+ stdlib (`cli/loadout/`, `plugins/loadout/hooks/*.py`), bash wrappers, JSON hook files, pytest with `fake_home`/`fake_runner`.

**Spec:** `docs/superpowers/specs/2026-10-22-serena-cbm-usage-design.md`

## Global Constraints

- Python 3.11+, standard library only in `cli/loadout/` and in hook scripts.
- Tests use `fake_home` and `fake_runner`. They never touch the real `~/.claude`, `~/.claude.json`, `~/.codex`, `~/.config/loadout`, `~/.serena` or `~/.cache/codebase-memory-mcp`, and never run real `serena`, `serena-hooks`, `codebase-memory-mcp`, `claude` or `codex`. Hook-script tests pipe JSON into the script with a fake `PATH` holding stub executables.
- External commands in `cli/loadout/` go only through `runner.run` / `runner.spawn_detached`, as argument lists. Hook scripts use `subprocess` with argument lists, never `shell=True`.
- User files: loadout changes only what it recorded as its own; a backup or a recorded undo comes before every change; `loadout restore` reverts it (AGENTS.md "User files").
- Never unpickle Serena's hook state (`~/.serena/hook_data/*/tool_use_counter.pkl`): a pickle runs code. Serena's denials are counted from transcripts.
- Serena hook commands exactly as Serena documents them: `serena-hooks <sub> --client=claude-code` (Claude Code), `--client=codex` (Codex).
- Conventional Commits (`type(scope): subject`), no `Co-Authored-By` or AI attribution.
- Test command: `uv run --python 3.12 --with pytest pytest -q --deselect "tests/test_docs_links.py::test_links_resolve[docs/examples/Niklas_Serena_Config.md]"`. Abbreviated below as `PYTEST`.
- Refresh thresholds (spec decision 7): end of a turn with changed code files; a tree-rewriting git command (`checkout`, `switch`, `pull`, `merge`, `rebase`, `reset`, `stash pop`, `stash apply`, `cherry-pick`, `revert`); 20 changed code files within a turn.

## Rulings already made (from the spec's builder calls)

- **No `alwaysLoad` preference.** The plugin's `.mcp.json` is the kit's file, the same for every user, and Claude Code offers no per-user override for a plugin server's `alwaysLoad`. So `alwaysLoad` is always on. The docs say this, and point to `ENABLE_TOOL_SEARCH` for anyone who wants deferral back. Spec decision 2 allows this.
- **The refresh logic lives in the hook script `hooks/refresh.py`, not in a `loadout` subcommand.** It runs on every edit and shell call, where the CLI's start-up (launcher, uv) is too slow. Both agents' hook files call the same script, so the rule still lives in one place, which is the spec's intent.

## Review Focus

1. **The user and the plugin both run `serena-hooks remind`** with a different matcher or wrapper. The plugin's copy must stay silent, or the shared counter denies after half the calls. Test: `test_guard_silent_when_user_runs_equivalent_hook` (Task 2).
2. **Serena's server disabled for this folder** in Claude Code (`disabledMcpServers` in `~/.claude.json` `projects[cwd]`). `remind` must not deny. Test: `test_guard_silent_when_server_disabled_for_folder` (Task 2).
3. **A refresh while cbm is already indexing that repo,** or two triggers at once. At most one runs, a refusal is silent, and the agent is never blocked. Test: `test_refresh_runs_once_under_lock` (Task 6).
4. **A non-repo folder, or a repo cbm never indexed.** The refresh does nothing; a new repo is `auto_index`'s job. Test: `test_refresh_skips_unindexed_repo` (Task 6).
5. **The user turned cbm's `auto_index` off after loadout turned it on.** loadout keeps their value and does not flip it back on the next run. Test: `test_auto_index_respects_users_own_value` (Task 5).

---

### Task 1: Search parser module, `loadout usage` counts Serena's denials, the search hint goes

**Files:**
- Create: `cli/loadout/searches.py` (moved from `plugins/loadout/hooks/tool_hint.py`: `symbol`, `_words`, `shell_search`, `_search_args`, `non_code`, `doc_filter`, `code_repo` and their constants)
- Modify: `cli/loadout/usage.py` (drop `_hint_rules`; import `searches`; add Serena-denial counting)
- Modify: `plugins/loadout/hooks/tool_hint.py` (keep only the docs hint: `docs_event`, `DOCS_*`, state/spacing for docs; drop `SEARCH_*`, search counting and the PostToolUse reset)
- Modify: `plugins/loadout/hooks/tool_hint.sh` (the bash pre-filter passes only web tools)
- Modify: `plugins/loadout/hooks/hooks.json`:
  - the tool_hint PreToolUse matcher becomes `WebSearch|WebFetch`;
  - remove the tool_hint PostToolUse group.
- Modify: `plugins/loadout/hooks/codex.json`: remove both tool_hint entries (Codex has no web tools for hooks, and Serena's `remind` covers shell searches)
- Test: `tests/test_searches.py` (new), `tests/test_usage.py`, `tests/test_tool_hint.py`, `tests/test_tool_hint_wiring.py`

**Interfaces:**
- Produces: `searches.shell_search(command: object) -> tuple[bool, str | None, list[str]]`. It keeps today's contract, but `is a search` is now true for the first search whose pattern yields a symbol, scanning **every** search in the line.
- Produces: `searches.symbol(pattern: object) -> str | None`. It now also returns the first identifier-like alternative of an alternation (`foo\|bar`, `-E 'foo|bar'`, `(foo|bar)`).
- Produces: `usage` report key `serena_denials` (sessions with at least one Serena `remind` denial), per group main/subagent, beside `hint_sessions`.

- [ ] **Step 1: Write the failing tests** in `tests/test_searches.py`:

```python
from loadout import searches

def test_alternation_counts_as_symbol_search():
    assert searches.shell_search(r'rg -n "hooks_status\|plugin_hook_commands" cli')[1] == "hooks_status"
    assert searches.shell_search("grep -nE 'alpha|beta' src")[1] == "alpha"

def test_every_search_in_a_compound_line_is_seen():
    hit, name, _ = searches.shell_search("sed -n 1,40p a.py; grep -n 'TEXT\\|abstract' x.cls; rg -n build_parser cli")
    assert hit and name == "build_parser"

def test_common_words_and_doc_filters_still_do_not_count():
    assert searches.shell_search("rg -n error src")[1] is None
    assert searches.shell_search("rg -n build_parser -t md docs")[0] is False
```

  In `tests/test_usage.py`, add `test_usage_counts_serena_denials_per_group`. It writes one main transcript and one subagent transcript (the existing `_claude` helper). Each has a `tool_result` with `is_error: true` and content `"Too many consecutive grep calls without using symbolic tools. ..."`. The test asserts `report["main"]["serena_denials"] == 1` and `report["subagent"]["serena_denials"] == 1`, using the group key names usage already uses.

  In `tests/test_tool_hint.py`, replace the search-hint tests with `test_no_search_hint_any_more`: three `_grep` calls emit nothing. Keep the docs-hint tests as they are.

- [ ] **Step 2: Run them, verify they fail**

  Run: `PYTEST tests/test_searches.py tests/test_usage.py tests/test_tool_hint.py tests/test_tool_hint_wiring.py`
  Expected: FAIL. `searches` is not found, `serena_denials` is missing, and a search hint is still emitted.

- [ ] **Step 3: Implement.**
  - Move the parser into `cli/loadout/searches.py`.
  - `symbol()`: for a pattern containing an unescaped `|` or a `\|`, split on it, strip `(`, `)`, `\b`, `^`, `$`, and return the first alternative that passes today's rules.
  - `shell_search()`: walk all command words, not only the first search. Return the first search with a symbol, else the first search, else `(False, None, [])`.
  - `usage`: count a session once when any `tool_result` text starts with one of Serena's three deny reasons:
    - `"Too many consecutive grep calls"`
    - `"Too many consecutive read calls"`
    - `"Too many consecutive non-symbolic tool calls"`

    Use these exact prefixes from Serena 2.1.0's `hooks.py`. Render them as `  sessions with a Serena reminder: N`.
  - Update the tool_hint wiring tests to the new matchers.

- [ ] **Step 4: Run the tests, verify they pass**

  Run: `PYTEST`
  Expected: all pass.

- [ ] **Step 5: Record the "before" numbers.** Run `bin/loadout usage --days 14 --json` from the checkout. It reads only transcripts. Save the main/subagent table to the ledger as `Before:`; the PR description uses it.

- [ ] **Step 6: Commit**

```bash
git add cli/loadout/searches.py cli/loadout/usage.py plugins/loadout/hooks/ tests/
git commit -m "refactor(usage): search parser of its own, counts Serena reminders; the search hint goes"
```

### Task 2: The guard, Serena's documented Claude Code hooks, cbm's hooks, `alwaysLoad`

**Files:**
- Create: `plugins/loadout/hooks/mcp_guard.py`
- Modify: `plugins/loadout/hooks/hooks.json`, `plugins/loadout/hooks/codex.json`, `plugins/loadout/.mcp.json`
- Modify: `cli/loadout/duplicates.py` (`plugin_hook_commands` strips the guard prefix too)
- Test: `tests/test_mcp_guard.py` (new), `tests/test_hooks.py`, `tests/test_duplicates*.py` (whichever file tests `plugin_hook_commands`)

**Interfaces:**
- Produces: hook command form `"${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" --soft --python "${CLAUDE_PLUGIN_ROOT}/hooks/mcp_guard.py" --agent claude|codex <server> <command...>`.
  - `<server>` is `serena` or `codebase-memory-mcp`.
  - The guard runs `<command...>` with the hook's stdin, passes its stdout and exit code through, and exits 0 silently when it skips.
- Produces: `mcp_guard.should_run(agent: str, server: str, argv: list[str], payload: dict, home: Path) -> bool`. It is False when any of these holds:
  - (a) `argv[0]` is not on `PATH`;
  - (b) Claude Code has the server disabled for `payload["cwd"]`: `~/.claude.json` `projects[<cwd>].disabledMcpServers` contains `serena`, `plugin:loadout:serena` or the cbm equivalents. The builder confirms the plugin form from the Claude Code docs; a project or user settings `disabledMcpjsonServers` that names the server counts too;
  - (c) a user or project settings file (`~/.claude/settings.json`, `<cwd>/.claude/settings.json`, `<cwd>/.claude/settings.local.json`) has a hook under the same event (`payload["hook_event_name"]`) whose command runs the same program and subcommand (`serena-hooks remind`, `codebase-memory-mcp hook-augment`), whatever its flags, matcher or wrapper. For `--agent codex`, rule (b) does not apply, and rule (c) reads `~/.codex/hooks.json` and `[hooks]` in `~/.codex/config.toml` instead; loadout's own Serena entries there are not "the user's" (they are recorded in loadout's state, as `codex_hooks.py` keeps them).
- Produces: `duplicates.plugin_hook_commands()` returns the inner command after the guard prefix (`serena-hooks remind --client=claude-code`), so ADR 0035's exact-duplicate removal still works.

- [ ] **Step 1: Write the failing tests** in `tests/test_mcp_guard.py`. Load the script like the other hook tests do, with a stub `serena-hooks` on a temp `PATH` that echoes its stdin.
  - `test_guard_runs_command_and_passes_output`
  - `test_guard_silent_when_binary_missing`
  - `test_guard_silent_when_server_disabled_for_folder`: `~/.claude.json` has `{"projects": {"<cwd>": {"disabledMcpServers": ["plugin:loadout:serena"]}}}`.
  - `test_guard_silent_when_user_runs_equivalent_hook`: `~/.claude/settings.json` has a PreToolUse hook `serena-hooks remind --client=claude-code` with matcher `""`.
  - `test_guard_runs_when_user_hook_is_other_event`
  - `test_guard_never_fails_the_tool_call`: malformed stdin gives exit 0 and no output.
  - `test_codex_guard_reads_codex_hooks_json`: a user's own cbm `SessionStart` hook in `~/.codex/hooks.json` keeps the plugin's copy silent.
  - `test_remind_matcher_covers_windows_tools`: the `remind` matcher regex matches `Grep`, `Glob`, `Read` and `Bash`, since native Windows Claude Code has Grep and Glob.

  In `tests/test_hooks.py`:
  - `test_claude_hooks_match_serena_docs`: `hooks.json` has, each once and each through the guard:
    - `SessionStart` with `serena-hooks activate --client=claude-code`;
    - `SessionEnd` with `serena-hooks cleanup --client=claude-code`;
    - `PreToolUse` matcher `mcp__plugin_loadout_serena__.*|mcp__serena__.*` with `serena-hooks auto-approve --client=claude-code`;
    - `PreToolUse` matcher `Bash|Read|Grep|Glob|mcp__plugin_loadout_serena__.*|mcp__serena__.*` with `serena-hooks remind --client=claude-code`.
  - `test_cbm_hooks_match_its_installer`: `hooks.json` has cbm's commands for `SessionStart`, `SubagentStart`, `PreToolUse` `Grep|Glob|Bash` and `PostToolUse` `Read`. `codex.json` has cbm's `SessionStart` and `SubagentStart`. Use the exact commands found in Step 3.
  - `test_plugin_servers_always_load`: both servers in `.mcp.json` have `"alwaysLoad": true`.

  In the duplicates test file: `test_guarded_plugin_hook_counts_as_duplicate`. A user hook `serena-hooks remind --client=claude-code` is `is_duplicate_hook`.

- [ ] **Step 2: Run them, verify they fail**

  Run: `PYTEST tests/test_mcp_guard.py tests/test_hooks.py`
  Expected: FAIL. There is no guard script and no `remind` entry.

- [ ] **Step 3: Find cbm's exact hook commands.** Read cbm 0.12.1's installer output for Claude Code and Codex without touching the real home. Either run `codebase-memory-mcp install -y --clients=claude,codex` with `HOME` and `CODEX_HOME` pointing into a fresh temp folder (the dry run prints no hook bodies), then read the written `settings.json`/`hooks.json` and delete the folder; or read DeusData/codebase-memory-mcp's source. Run each command once with a real payload on this repo and note its output in the ledger (a quick earlier try of `hook-augment --event SessionStart` printed nothing). Wire only commands that produce output or are documented as context-only, and ledger what each does.

- [ ] **Step 4: Implement** `mcp_guard.py` (stdlib; read at most 200 000 bytes of stdin like `tool_hint.py`; 4 s inner timeout below the hook's 5 s), the hook entries, `alwaysLoad`, and the `duplicates.py` prefix. Timeouts: `remind` 5 s, `activate` 15 s, `cleanup` 10 s, `auto-approve` 10 s, cbm as its installer sets them, else 5 s. Matchers are regexes in Claude Code; `mcp__serena__.*` covers a user's own server named `serena`.

- [ ] **Step 5: Codex `alwaysLoad` equivalent.** Check Codex's docs through Context7, falling back to developers.openai.com/codex: is there a per-server or global switch that loads MCP tools upfront?
  - If there is one, add it to the Codex server tables loadout writes (`codex.py`), using the exact-text record and a test.
  - If there is none, ledger `Ruling: Codex has no alwaysLoad; the instruction block's "search first" line stays`.
  - Either way, check that `codex_hooks.SERENA_HOOKS` still equals Serena's documented six (event, matcher, subcommand, timeout), as listed in the spec's source page. Ledger the result.

- [ ] **Step 6: Run the tests, verify they pass**

  Run: `PYTEST`
  Expected: all pass, including the existing Codex hook-digest tests. Update digests only where a test pins `codex.json`'s content.

- [ ] **Step 7: Commit**

```bash
git add plugins/loadout/ cli/loadout/duplicates.py cli/loadout/codex.py tests/
git commit -m "feat(hooks): Serena's and codebase-memory's documented hooks, guarded, and their tools load upfront"
```

### Task 3: Subagent context, delegation rule, codex-reviewer tools

**Files:**
- Modify: `plugins/loadout/hooks/subagent-context.sh`, `rules/tooling.md`, `.claude/agents/codex-reviewer.md`
- Test: `tests/test_hooks.py` (subagent text), `tests/test_rules.py` or the file that pins `rules/tooling.md`

**Interfaces:** none consumed beyond Task 2's tool names.

- [ ] **Step 1: Write the failing tests.**
  - `test_subagent_context_names_exact_tools` asserts the SubagentStart `additionalContext` contains `mcp__plugin_loadout_codebase-memory-mcp__search_graph`, `mcp__plugin_loadout_serena__find_symbol` and `already active`.
  - `test_tooling_rule_says_name_tools_when_delegating` asserts `rules/tooling.md` contains `When you delegate code work`.
  - `test_codex_reviewer_can_use_serena_and_graph` parses the agent's frontmatter `tools:`. It asserts the list includes `mcp__plugin_loadout_serena__find_symbol`, `mcp__plugin_loadout_serena__find_referencing_symbols`, `mcp__plugin_loadout_serena__get_symbols_overview`, `mcp__plugin_loadout_codebase-memory-mcp__search_graph`, `mcp__plugin_loadout_codebase-memory-mcp__trace_path`, `mcp__plugin_loadout_codebase-memory-mcp__get_code_snippet` and `mcp__plugin_loadout_codebase-memory-mcp__query_graph`, and still `Read, Grep, Glob, Bash`. No editing tool is in the list.

- [ ] **Step 2: Run them, verify they fail** (`PYTEST tests/test_hooks.py`; expected: FAIL on the missing names).

- [ ] **Step 3: Implement.** Write the subagent text, exactly:

  `Tool routing (loadout): code structure, callers, impact -> codebase-memory (mcp__plugin_loadout_codebase-memory-mcp__search_graph, trace_path, get_code_snippet) before grep; a definition, references or an edit -> Serena (mcp__plugin_loadout_serena__find_symbol, find_referencing_symbols, replace_symbol_body); both are loaded and Serena's project is already active, so call them directly. A user's own servers may be named mcp__serena__* / mcp__codebase-memory-mcp__*. Library docs, also while planning -> Context7; Microsoft APIs -> Microsoft Learn; text and config -> Grep/Read. Use the paths and symbols the parent gave you.`

  Add this line under the table in `rules/tooling.md`:

  `When you delegate code work to a subagent, name the tools in its prompt (the codebase-memory project, search_graph/trace_path, Serena find_symbol): subagents use what their prompt names.`

  In `codex-reviewer.md`, add the tools and a short paragraph: use codebase-memory for callers and the impact of each changed function, and Serena to read definitions, before grep.

- [ ] **Step 4: Run** `PYTEST`; expected: all pass.

- [ ] **Step 5: Commit** `feat(routing): subagents get exact tool names, delegation names the tools, codex-reviewer reads with Serena and the graph`.

### Task 4: Check rows for the setup variations

**Files:**
- Modify: `cli/loadout/check.py`
- Possibly modify: `catalog.json` (Serena minimum)
- Test: `tests/test_check_serena_cbm_setups.py` (new)

**Interfaces:**
- Consumes: `mcp_guard`'s equivalence rule. Re-implement it in `cli/loadout/` as `duplicates.equivalent_user_hooks() -> list[tuple[str, str, str]]`, returning (event, command, file). The hook script cannot import loadout; one test feeds both the same fixture to keep them in step.
- Produces these rows:
  - `Serena hooks`: OK with detail `yours in <file>; the plugin's copy stays silent` when equivalent user hooks exist; the fix is `loadout configure own`.
  - `Serena servers`: warn when a user-scope or project server whose command is `serena` exists next to the plugin's and is not an exact duplicate. Detail `two Serena servers: the plugin's and yours (<name> in <file>)`; fix `loadout configure own`.
  - The same pair for codebase-memory (`codebase-memory servers`).

- [ ] **Step 1: Write the failing tests:**
  - `test_row_names_users_equivalent_serena_hook`
  - `test_row_warns_on_second_serena_server`
  - `test_exact_duplicate_server_is_not_a_second_server` (ADR 0035 removes it on update)
  - `test_rows_absent_in_default_setup`
  - `test_cbm_second_server_row`

  Each one builds its files under `fake_home`.

- [ ] **Step 2: Run them, verify they fail.**

- [ ] **Step 3: Implement.** Serena minimum: if the catalog has a minimum-version field for binaries, set Serena's to `2.1.0` and add a test that an older `serena --version` makes the existing version row warn. If it has none, ledger `Ruling: no minimum-version mechanism; Serena 2.1.0 named in docs only`.

- [ ] **Step 4: Run** `PYTEST`; expected: all pass.

- [ ] **Step 5: Commit** `feat(check): name a second Serena or codebase-memory and hooks you run yourself`.

### Task 5: `cbm_auto_index` preference

**Files:**
- Modify: `preferences.json`, `cli/loadout/preferences.py` (if a `loadout` target needs registering)
- Create: `cli/loadout/cbm.py`
- Modify: `cli/loadout/apply.py` (a `cbm_step`, wired into bootstrap, update and the daily sync wherever `codex_step` runs; the sync runs it too, since it installs nothing)
- Modify: `cli/loadout/backup.py` (`_allowed_run` allows `["codebase-memory-mcp", "config", "set", "auto_index", "true"|"false"]`)
- Modify: `cli/loadout/check.py` (row)
- Test: `tests/test_cbm_auto_index.py` (new), `tests/test_backup*.py` (allowlist)

**Interfaces:**
- Produces a preference: `{"id": "cbm_auto_index", "agents": ["claude", "codex"], "question": "Should codebase-memory index a new git repo by itself the first time a session opens it? (up to 50 000 files; afterwards its watcher keeps it current)", "options": [{"value": "on", "label": "yes"}, {"value": "off", "label": "no, I index repos myself"}], "default": "on", "target": {"loadout": "cbm.auto_index"}}`.
- Produces `cbm.apply_auto_index(bk: Backup, dry: bool = False) -> list[str]`. It reads `codebase-memory-mcp config get auto_index` via `runner.run`, then acts:
  - The value already equals the answer: nothing.
  - The answer is `on`, the value is `false`, and loadout has no record: run `config set auto_index true`, record the undo `["codebase-memory-mcp", "config", "set", "auto_index", "false"]` in `bk`, and save `state_dir()/cbm-auto-index.json` `{"set": "true"}`. Line: `codebase-memory: auto_index on (new git repos are indexed at their first session)`.
  - The record says loadout set `true` and the value is now `false`: the user's own value. Nothing changes. Line: `codebase-memory: auto_index off (yours)`.
  - The answer is `off` and loadout's record says it set `true`: set `false` and drop the record.
  - Binary missing: no line.
- Produces the check row `codebase-memory auto_index`: OK `on`; OK `off (yours)` or `off (your answer)`; no row without the binary.

- [ ] **Step 1: Write the failing tests:**
  - `test_auto_index_turned_on_with_undo`: `fake_runner` answers `config get auto_index` with `false`. Assert the `set` call happens, and that the backup manifest holds the undo.
  - `test_auto_index_respects_users_own_value`: record present, value `false`; assert no `set`.
  - `test_auto_index_off_answer_reverts_only_ours`
  - `test_auto_index_dry_run_changes_nothing`
  - `test_restore_replays_auto_index_undo` (allowlist)
  - `test_check_row_auto_index`

  Use `fake_runner.responses[("codebase-memory-mcp", "config", "get", "auto_index")]` for the value. The builder checks the real output format of `config get` with `--help`/`config get auto_index` (read-only) and ledgers it.

- [ ] **Step 2: Run them, verify they fail.**

- [ ] **Step 3: Implement**, following how `codex_serena_approval` is stored and read (`preferences.detect()`, `by_id`).

- [ ] **Step 4: Run** `PYTEST`; expected: all pass.

- [ ] **Step 5: Commit** `feat(cbm): new git repos get their first index from codebase-memory itself (preference, undoable)`.

### Task 6: Refresh at change points

**Files:**
- Create: `plugins/loadout/hooks/refresh.py`
- Modify: `plugins/loadout/hooks/hooks.json`:
  - PostToolUse `Write|Edit|MultiEdit|Bash`;
  - `Stop`;
  - `SubagentStop`.
- Modify: `plugins/loadout/hooks/codex.json`:
  - PostToolUse `Edit|Write|Bash` (Codex's edits arrive as `apply_patch` under `Edit|Write`, as `advisor.py` reads them);
  - `Stop`.
- Modify: `cli/loadout/check.py` (row only on a failed last refresh)
- Test: `tests/test_refresh.py` (new)

**Interfaces:**
- Produces the state file `<state_dir>/cbm-refresh/<repo-hash>.json` with `{"changed": [paths], "head": sha, "status": porcelain-hash, "last": {"at": ts, "ok": bool, "error": str}}`, and a lock `<repo-hash>.lock` (O_EXCL create, stale after 10 minutes).
- Hook behaviour:
  - PostToolUse on an edit tool adds the edited code file (a `CODE_EXT` file under the repo root; the repo root comes from `git rev-parse --show-toplevel`, with a 2 s timeout).
  - PostToolUse on Bash: when the command is a tree-rewriting git command (the Global Constraints list), trigger now. Otherwise, note it so the next Stop compares HEAD and the `git status --porcelain` hash.
  - Stop/SubagentStop: trigger when `changed` is non-empty or HEAD/porcelain moved.
  - 20 entries in `changed` trigger at once.
- Trigger: spawn detached (`start_new_session`; on Windows `DETACHED_PROCESS | CREATE_NO_WINDOW`) `python refresh.py --run <repo_root>`. The `--run` child does the following, all with argument lists and timeouts:
  1. takes the lock (none free: exit);
  2. runs `codebase-memory-mcp cli --quiet index_status {"repo_path": <root>}`; "not indexed" (or a non-zero exit) means exit without recording a failure;
  3. runs `codebase-memory-mcp cli --quiet index_repository {"repo_path": <root>, <the mode/options index_status reports>}`;
  4. on exit 0 resets `changed` and stores `head`/`status`;
  5. treats a stderr/stdout containing `another index operation` as silent, not a failure;
  6. records any other failure in `last`.
- Never blocks: the hook process itself returns within 2 s and prints nothing.
- Skips when the guard rule (a) or (b) says cbm is not available. Import the guard's functions from `mcp_guard.py` (same folder, `sys.path` insert), so the rule has one home in the hook folder.

- [ ] **Step 1: Write the failing tests** (stub `git` and `codebase-memory-mcp` executables on a temp `PATH`, recording their argv to a file; `--run` invoked in-process for determinism):
  - `test_edit_then_stop_triggers_one_refresh`
  - `test_no_change_no_refresh`
  - `test_git_checkout_triggers_now`: `git checkout -b x` and `git switch main` trigger; `git status` and `git log` do not.
  - `test_twenty_files_trigger_mid_turn`
  - `test_refresh_skips_unindexed_repo`
  - `test_refresh_runs_once_under_lock`: a held lock means a second `--run` exits without calling `index_repository`.
  - `test_busy_index_is_silent`
  - `test_failure_is_recorded_and_check_shows_it`
  - `test_hook_returns_fast_and_prints_nothing`: the parent never waits for `--run`.
  - `test_non_repo_folder_does_nothing`
  - `test_codex_apply_patch_paths_are_recorded`: use the `apply_patch` payload shape the advisor tests use.

- [ ] **Step 2: Run them, verify they fail.**

- [ ] **Step 3: Implement.** Read the options `index_status` returns for a real indexed repo (this repo, read-only) and ledger the fields used.

- [ ] **Step 4: Run** `PYTEST`; expected: all pass.

- [ ] **Step 5: Commit** `feat(cbm): re-index at the end of a turn, after git rewrites and after 20 changed files`.

### Task 7: Docs, ADR 0039, live checks

**Files:**
- Create: `docs/adr/0039-serena-remind-always-load-and-refresh.md` (supersedes ADR 0008's "remind is dropped" sentence and ADR 0026 for code searches; mark both "Superseded in part by 0039")
- Modify:
  - `docs/adr/README.md` (index) and `AGENTS.md` (range `0001-0039`);
  - `docs/reference/hooks.md` (both tables, the guard, refresh, alwaysLoad);
  - `docs/explanation/the-toolset.md`;
  - `docs/how-to/codex.md` (the "Tool hints" and "MCP tools load on demand" bullets);
  - `docs/how-to/troubleshooting.md`: a row for "Too many consecutive grep calls…": Serena's reminder; the next call goes through;
  - `docs/reference/cli.md` (`loadout usage`: the Serena reminder line);
  - `docs/reference/preferences-format.md` (`cbm_auto_index`);
  - `docs/reference/state-and-sync.md` (`cbm-refresh/`, `cbm-auto-index.json`);
  - `docs/reference/modules.md` (`searches.py`, `cbm.py`, hook scripts);
  - `plugins/loadout/skills/configure/SKILL.md` (routing row for "Serena/graph not used", if it names the hint);
  - `.serena/memories/` entries that name the tool hint;
  - `docs/how-to/vscode.md`: one line that VS Code's Claude Code extension runs the same plugin hooks. The builder checks the Claude Code docs for differences first.
- Test: `tests/test_docs_links.py` (existing)

- [ ] **Step 1: Serena freshness for TypeScript.** Repeat the spec's check (find_symbol after an outside edit, a new file, a deleted file) in a temp TypeScript repo, with Serena's MCP server over stdio in the scratchpad. Record the result in `docs/explanation/the-toolset.md`. If TypeScript goes stale, stop and report it to the user; do not add a refresh.
- [ ] **Step 2: Write the docs and the ADR.** In the ADR's Context, put the evidence numbers from the spec plus Task 1's "before" table.
- [ ] **Step 3: Run** `PYTEST` and `claude plugin validate plugins/loadout` (read-only validation; AGENTS.md lists it as a command). Expected: pass.
- [ ] **Step 4: Run the `loadout:docs-sync` skill** over the branch.
- [ ] **Step 5: Commit** `docs: Serena's reminder, tools that load upfront, codebase-memory refresh (ADR 0039)`.
