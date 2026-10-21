# Live Tour Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the bugs the Linux live tour found: a fresh machine gets the whole kit, failures are named instead of looking like success, and Codex tool approvals no longer end loadout's ownership of a server.

**Architecture:** Small fixes in the existing modules (bootstrap, codex, check, steps, preferences, project, maintenance/pkgmgr, apply, inventory), each with a failing test first. Two new ADRs record the decisions (0036 Codex tool approvals and the Serena approval preference; 0037 marketplaces cloned only when a plugin uses them). The plan names functions, not line numbers (they move); find them with Serena `find_symbol` or codebase-memory `search_graph`.

**Tech Stack:** Python 3.11+ standard library (`cli/loadout/`), pytest via uv, JSON kit files (`settings.base.json`, `profiles/*.json`, `preferences.json`).

**Spec:** `docs/superpowers/specs/2026-10-21-live-tour-fixes-design.md`. Evidence (git-ignored): `.superpowers/handoff/2026-10-21-live-tour-findings.md`, `.superpowers/handoff/live-tour-logs/`.

## Global Constraints

- Python 3.11+, standard library only in `cli/loadout/`; hook scripts in `plugins/loadout/hooks/` stay standard library and never import `loadout`.
- Tests use `fake_home` and `fake_runner` (`tests/conftest.py`: `fake.responses[prefix] = runner.Result(code, out, err)`, `fake.missing`, `fake.paths`; default result `Result(0, "", "")`). Never touch the real `~/.claude`, `~/.claude.json`, `~/.codex`, `~/.config/loadout`. No real installers, no mutating `claude`/`codex`.
- loadout changes only what it recorded as its own; the user's text stays as written; exact-text record, parse guard, atomic write; a backup (or allowlisted undo) before every destructive change; a `run` step that cannot be undone says so in its plan.
- External commands only through `runner.run` with argument lists. No plaintext secret anywhere loadout writes.
- Conventional Commits `type(scope): subject`; no Co-Authored-By or any AI attribution.
- Out of scope: VS Code's Codex extension mode (spec "Out of scope"): do not change extension-mode messages, rows or `hooks_status`.
- Every implementer and reviewer uses codebase-memory (project `home-jonas-Documents-Code-agent-loadout`: `search_graph`, `trace_path`, `get_code_snippet`) for callers and impact and Serena (`find_symbol`, `find_referencing_symbols`) for definitions and references before grep; grep for JSON, docs and literals.
- Suite: `uv run --python 3.12 --with pytest pytest -q --deselect "tests/test_docs_links.py::test_links_resolve[docs/examples/Niklas_Serena_Config.md]"`. Never `git add docs/examples/Niklas_Serena_Config.md`.

## Review Focus

1. A `config.toml` where Codex wrote `[mcp_servers.X.tools.Y]` right after loadout's `[mcp_servers.X]` (one blank line, as the real file shows), and one with a user comment just above the sub-table header: loadout keeps managing X, the sub-table and the comment survive unchanged (Task 4).
2. A user's own Serena table named `serena` (what `serena setup codex` writes since Serena 2.1) with the approval preference on `approve`: nothing is written into it (Task 5).
3. Existing machines that already know `claude-plugins-official`, or list a marketplace whose name contains it as a substring, or whose `claude plugin marketplace list` text has the "From claude.ai:" section: exact names, nothing added twice (Task 1).
4. Only superpowers updated (not loadout's plugin): the Stop hook must not clear "/reload-plugins" (Task 10).
5. A broken `loadout.json`, a broken plugin `.codex-mcp.json`, or a malformed conflict log: check and session start still run and say nothing wrong (Tasks 5, 8, 9).

---

### Task 1: The official marketplace on a fresh machine; marketplaces only when used

**Files:** `settings.base.json`; `cli/loadout/bootstrap.py` (`plugins_plan`, new `listed_marketplaces`); `cli/loadout/check.py` (`_plugins`); Test: `tests/test_bootstrap_plugins_official.py` (new), `tests/test_bootstrap.py` (its mocked list output), `tests/test_check.py`.

**Interfaces:**
- Produces: `bootstrap.listed_marketplaces() -> set[str] | None`: names from `claude plugin marketplace list --json` (`[{"name","source","repo","installLocation"}]`); if the JSON is unusable, from the text output's marketplace lines (a leading `❯ ` is stripped; bare lines are accepted), stopping at the line `From claude.ai:`; `None` only when the command exits non-zero. Empty output → `set()`. Task 6 calls it at plan time.
- `plugins_plan()` keeps its 3-tuple `(skip_lines, [(name, origin)], [plugin_ids])`.

- [ ] **Step 1: Failing tests** (unpack `_, markets, plugins = bootstrap.plugins_plan()`):
  - `test_fresh_home_adds_the_official_marketplace_before_its_plugins`: list --json `[]` → `("claude-plugins-official", <origin for anthropics/claude-plugins-official>)` in `markets`; `superpowers@claude-plugins-official` in `plugins`.
  - `test_a_known_official_marketplace_is_not_added_again`: list --json has `claude-plugins-official` → not planned.
  - `test_a_substring_name_does_not_count`: list --json has only `claude-plugins-official-mirror` → official planned.
  - `test_text_fallback_stops_at_claude_ai_section`: list --json exits 0 with non-JSON text containing `❯ impeccable` and, after `From claude.ai:`, `❯ claude-plugins-official (available from claude.ai, account — not added)` → official still planned, impeccable not.
  - `test_a_declared_marketplace_no_enabled_plugin_uses_is_not_cloned`: base declares `life-sciences`, no enabled plugin `@life-sciences` → not in `markets`; with `wiley-scholar-gateway@life-sciences` enabled in the merged settings → planned.
  - `test_plugins_row_names_a_missing_marketplace`: `superpowers@claude-plugins-official` enabled, not installed, `~/.claude/plugins/known_marketplaces.json` lacks it → row `plugins installed` detail names `claude-plugins-official`, fix `run loadout update (adds the marketplace, then installs them)`; no text `automatically`. A broken `known_marketplaces.json` keeps the existing InvalidJSON handling.
- [ ] **Step 2: Run; FAIL.**
- [ ] **Step 3: Implement**: add `claude-plugins-official` (github, `anthropics/claude-plugins-official`, same shape as its neighbours) to `settings.base.json` `extraKnownMarketplaces`; `listed_marketplaces()`; `plugins_plan` uses exact membership and plans a declared marketplace only when it is `agent-loadout` or some enabled plugin id ends with `@<name>`; `_plugins` reads `known_marketplaces.json` (keyed by name). Remove the "install automatically at the next Claude Code start" text and comment. Update `tests/test_bootstrap.py`'s mocked list output if it breaks.
- [ ] **Step 4: PASS**, plus `tests/test_bootstrap*.py tests/test_check.py tests/test_update_plan.py tests/test_apply*.py`.
- [ ] **Step 5: Commit** `fix(plugins): add Anthropic's official marketplace on a fresh machine, clone only used marketplaces`

### Task 2: `bootstrap --no-plugins` skips Codex plugins

**Files:** `cli/loadout/bootstrap.py` (the Codex step in `bootstrap`); Test: `tests/test_bootstrap_no_plugins.py` (new).

- [ ] **Step 1: Failing test** `test_no_plugins_skips_codex_marketplaces_and_plugins`: bootstrap with `plugins=False`, Codex on and present → no call starts with `["codex", "plugin"]`; Codex's rules block is still written (assert the AGENTS.md block or a config.toml write).
- [ ] **Step 2: FAIL. Step 3:** pass `plugins=plugins` to `apply.codex_step` in bootstrap's Codex step. **Step 4: PASS** plus `tests/test_bootstrap*.py`. **Step 5: Commit** `fix(bootstrap): --no-plugins skips Codex's marketplaces and plugins too`

### Task 3: A large Codex clone is honest

**Files:** `cli/loadout/codex.py` (`_install_routes`, `checks`, `open_steps`, new `missing_routes`); `cli/loadout/bootstrap.py` (Still to do only if `open_steps` does not already flow there); `tests/conftest.py` (FakeRunner records `timeout` in a new `self.timeouts` list, backward compatible); Test: `tests/test_codex_plugins.py`.

**Interfaces:**
- Produces: `codex.missing_routes(installed: set[str] | None = None, listed: set[str] | None = None) -> tuple[list[str], list[str]]`: (marketplace sources Codex lacks, plugin entries Codex lacks). Plugin entries compare by full `name@market` id; when the marketplace itself is missing, the entry is the plugin name plus its source (the id is unknowable until the marketplace exists). Excludes `loadout@agent-loadout` (the `Codex plugin` row covers it). Callers pass the `installed_plugins()` / marketplace sets they already fetched; with `None` it fetches once. Returns `([], [])` without the Codex CLI or when listing fails. Sources compare through the existing `_norm_source`/`_same_source`.

- [ ] **Step 1: Failing tests**
  - `test_marketplace_add_and_upgrade_get_1800_seconds` (via `fake.timeouts`); `plugin add` stays 600.
  - `test_progress_line_warns_about_large_clones`: `say` gets `adding marketplace pbakaus/impeccable, a git clone (1 of 2; large repositories can take several minutes)…`.
  - `test_check_names_what_codex_lacks`: routes want `pbakaus/impeccable` (`impeccable@impeccable`); Codex lists neither → a row named `Codex plugins missing`, `warn`, detail naming `pbakaus/impeccable` and `impeccable`, fix `loadout update (retries them)`.
  - `test_same_name_from_another_market_is_still_missing`: Codex has `superpowers@openai-curated-remote`, loadout wants `superpowers@claude-plugins-official` → reported.
  - `test_open_steps_names_them_once`, `test_nothing_missing_no_row_no_step`, `test_loadout_plugin_not_reported_twice`.
- [ ] **Step 2: FAIL. Step 3: Implement**: timeouts (marketplace add and upgrade 1800), the progress text, `missing_routes`, the row (CLI mode only), the open step; `checks()` passes its fetched sets to `missing_routes` so no extra slow call; `open_steps` callers (bootstrap's Still to do, `configure agent codex on`) get one fetch at most.
- [ ] **Step 4: PASS** plus `tests/test_codex*.py tests/test_bootstrap*.py`. **Step 5: Commit** `fix(codex): longer clone timeout, warn about large clones, name what Codex lacks`

### Task 4: Codex `tools.*` sub-tables stay the user's

**Files:** `cli/loadout/codex.py` (`_sections` consumers, `_ownership`, `apply_config`, `_without_owned`, `refresh_record`, `RELEASES`/`is_release`, `_TABLE_STATES`, `explain_config`); `cli/loadout/codex_project.py` (its `_without_owned` use, check only); Create `docs/adr/0036-codex-tool-approvals-and-serena-approval.md` + `docs/adr/README.md` row; Test: `tests/test_codex_config.py` (or `tests/test_codex_tool_approvals.py`, new).

**Interfaces:**
- Produces: `codex.is_tool_section(path: tuple, name: str) -> bool` (`path[:3] == ("mcp_servers", name, "tools") and len(path) > 3`). `_ownership` ignores such sections. Task 5 relies on serena staying owned with a `tools.serena_repl` section.

Rules:
- A parent section's trailing comment and blank lines that sit directly above a `tools.*` header belong to that sub-table, not to the parent: split them off before comparing the parent's text and before rewriting it.
- A changed owned table is replaced **in place** (today it is removed and appended at the end); keep the change marked so the backup still happens; the `tools.*` sections and their leading comments stay where they are with identical lines. Separators between sections stay as the writer already normalises them (one blank line); do not claim more.
- `_without_owned` pops an owned table's keys but keeps its `tools` sub-dict, so the parse guard proves the approvals survive (check codex_project's use).
- When loadout would remove an owned table that still has `tools.*` sections (trigger in tests: `context7`, dropped when `context7@claude-plugins-official` is not enabled), it keeps both, records the table as kept (like `released`, so the line is said once and `checks()` does not warn forever), line `mcp {name}: kept in config.toml: your tool approvals ([mcp_servers.{name}.tools.*]) need it`; `_TABLE_STATES` and `explain_config` get a label for it.
- Other sub-tables (`env`, anything not `tools`) keep today's release.

- [ ] **Step 1: Failing tests** (fixtures built like the real file: parent, one blank line, `[mcp_servers.serena.tools.serena_repl]` + `approval_mode = "approve"`, one blank line, next table):
  - `test_always_allow_subtable_keeps_loadout_managing_serena`: desired serena args change → parent updated in place, sub-table lines identical, still in `tables`, no "left as is".
  - `test_user_comment_above_the_subtable_stays_with_it`.
  - `test_refresh_record_keeps_ownership_with_tools_subtable`.
  - `test_env_subtable_still_releases`.
  - `test_dropping_a_table_with_tools_subtables_keeps_both_and_says_it_once` (context7; second run: no line, no check warning).
  - `test_released_for_tools_only_is_managed_again`.
  - `test_parse_guard_sees_the_approvals`: a writer bug that drops the sub-table is refused (simulate by asserting `_without_owned` keeps `tools`).
- [ ] **Step 2: FAIL. Step 3: Implement** (read `apply_config` in full with Serena first; re-check order assertions in existing tests). **Step 4: PASS** plus `tests/test_codex*.py`. **Step 5: Commit** `fix(codex): "Always allow" approvals stay yours inside tables loadout manages` (ADR 0036 + index, same commit).

### Task 5: Codex asks once about Serena's approvals

**Files:** `preferences.json`; `cli/loadout/preferences.py` (`_apply`, `detect`, `set_choice`, `ask_all`, `show_lines`, `without_owned_settings`); `cli/loadout/configure.py` (`_quick_defaults`); `cli/loadout/answers.py` (accepted ids); `cli/loadout/paths.py` (`personal_loadout_json()`); `cli/loadout/codex.py` (`desired_keys` entry; filtering and removal in `apply_config` and `refresh_record`); Test: `tests/test_preferences_loadout_target.py` (new), `tests/test_codex_serena_approval.py` (new).

**Interfaces:**
- Consumes: Task 4 (`is_tool_section`; serena stays owned with a tools sub-table).
- Produces: preference id `codex_serena_approval`, `"agents": ["codex"]`, options `ask` (default, "ask each time") and `approve` ("approve automatically"); question text contains `serena_repl` and `runs code`; target `{"loadout": "codex.serena_approval"}` stored in `<personal layer>/loadout.json` as `{"codex": {"serena_approval": "approve"}}`. Read like the other preferences: `state[pid].value or by_id(pid)["default"]`.

Rules:
- `loadout.json`: atomic write through the backup object; unknown keys preserved; missing → unset; `InvalidJSON` → counts as unset for reading (session start must not fail) and a write refuses with a message naming the file.
- A preference with `"agents": ["codex"]` is skipped by `ask_all`, `_quick_defaults`, `show_lines` and `--answers` when Codex is off. A personal layer cloned onto a new machine or Codex turned on later is not asked: the default `ask` applies and `loadout configure prefs` changes it (say so in the docs).
- `desired_keys` may emit `(("mcp_servers","serena","tools","serena_repl"), "approval_mode", "approve", False)` when the answer is `approve`; `apply_config` and `refresh_record` drop that key when serena is not loadout's (`user_serena(...)` found a user Serena, which is named `serena` since Serena 2.1): then config.toml is unchanged and one line, said once, reads `Serena is your own server in config.toml; to approve its tools, choose "Always allow" in Codex`.
- Switching to `ask`: remove only this recorded key line (not a generic owned-key removal); remove the `[mcp_servers.serena.tools.serena_repl]` header only if loadout added it and the section holds nothing else; mark the change so a backup is made. A user-written `approval_mode` (not in the record) stays.

- [ ] **Step 1: Failing tests**: loadout-target round trip with unknown keys; missing/broken file (read unset, write refused); Codex off → not asked (bootstrap path, `configure prefs`, `_quick_defaults`, `--answers`); approve writes the key and records it, serena stays owned; ask removes only the recorded key and the header loadout added; user-written key stays; own `serena` table + approve → config.toml byte-identical and the note once; question text.
- [ ] **Step 2: FAIL. Step 3: Implement. Step 4: PASS** plus `tests/test_preferences*.py tests/test_codex*.py tests/test_configure.py tests/test_answers*.py`. **Step 5: Commit** `feat(codex): ask once whether Codex approves Serena's tools automatically`

### Task 6: academic-research-skills comes with the thesis profile

**Files:** `settings.base.json` (remove `academic-research-skills`; `life-sciences` stays declared and is cloned only when used, Task 1); `profiles/thesis.json` (`settings.extraKnownMarketplaces.academic-research-skills`, same shape, with a `why` if the file's convention has one); `cli/loadout/project.py` (`_plan_profile`, `_install`); `cli/loadout/inventory.py` (`classify` only); `cli/loadout/profiles.py` (`kit_marketplaces()`); `tests/test_repo_static.py` if it pins thesis.json; Create `docs/adr/0037-marketplaces-only-when-a-plugin-uses-them.md` + index; Test: `tests/test_profile_marketplaces.py` (new), `tests/test_inventory.py`.

**Interfaces:**
- Consumes: `bootstrap.listed_marketplaces()` (Task 1).
- Produces: `profiles.kit_marketplaces() -> dict[str, dict]` (base `extraKnownMarketplaces` merged with every profile's), used only by `inventory.classify` (not by `own._kit_markets`, whose adopt path must keep declaring the marketplace of an adopted plugin).

- [ ] **Step 1: Failing tests**
  - `test_base_settings_no_longer_declare_academic_research_skills`.
  - `test_profile_plan_adds_a_missing_marketplace_before_installing`: applying `thesis` with Claude on, `listed_marketplaces()` lacking it → a run step `claude plugin marketplace add Imbad0202/academic-research-skills` (marked not undoable in the plan output) before `claude plugin install academic-research-skills@academic-research-skills --scope project`; listed → no add; Claude off (`.loadout.json` or targets) → neither step; only marketplaces of plugins in the profile's `install` are added.
  - `test_profile_marketplace_counts_as_kit_in_inventory`; `test_adopt_still_declares_an_adopted_plugins_marketplace`.
  - `test_codex_project_still_routes_the_thesis_plugin`.
- [ ] **Step 2: FAIL. Step 3: Implement** (existing users: `settings_merge` removes the unchanged base entry; the clone in `known_marketplaces.json` stays; assert nothing else). **Step 4: PASS** plus `tests/test_project*.py tests/test_profile*.py tests/test_inventory.py tests/test_adopt.py tests/test_codex_project.py tests/test_repo_static.py tests/test_connectors.py`. **Step 5: Commit** `refactor(profiles): academic-research-skills comes with the thesis profile`

### Task 7: No `X -> X` updates

**Files:** `cli/loadout/maintenance.py` (`find_outdated`); `cli/loadout/pkgmgr.py` (`mise_outdated` if needed); Test: `tests/test_pkgmgr.py`.

- [ ] **Step 1: Failing tests** (`mise_tool` needs `fake.paths["gh"]` under mise's installs folder and `mise` present):
  - `current: null` and `current: ""` with `gh --version` = latest → no gh.
  - Binary older than latest → reported `2.101.0 -> 2.102.0`.
  - `local_version` None and mise `current` empty → dropped (no `? -> X`).
  - Through `update.build_plan` too: equal versions never become a plan item.
- [ ] **Step 2: FAIL. Step 3: Implement** (empty mise current → compare the PATH binary's version; final guard drops equal or unknown-installed entries). Adopt's inventory already compares strictly; its different source of "latest" (finding 19) is not this task: add a backlog line in Task 12. **Step 4: PASS** plus `tests/test_maintenance.py tests/test_update*.py`. **Step 5: Commit** `fix(update): never report an update whose versions are equal`

### Task 8: codebase-memory's daemon conflict is named

**Files:** `cli/loadout/check.py` (new `_cbm_conflict()` registered in `run_checks`); Test: `tests/test_check_cbm_conflict.py` (new).

Facts (codebase-memory-mcp 0.12.1, verified on this machine): the failing client writes the log in **its own** cache folder: `$CBM_CACHE_DIR` if set, else `$HOME/.cache/codebase-memory-mcp` (no XDG rule); file `logs/daemon-conflicts.ndjson`, rotated to `.1`. A cache-folder record: `{"event":"daemon.version_conflict","timestamp_unix_s":N,"reason":"cache_root","active_cache":…,"requested_cache":…,"active_version":"0.12.1","requested_version":"0.12.1",…}`; a version record lacks the cache fields and has differing versions.

- [ ] **Step 1: Failing tests**: a record 10 minutes old (`reason: cache_root`) → row `codebase-memory-mcp daemon`, `warn`, detail `a codebase-memory-mcp session with a different cache folder could not start (another one already runs for your account)`, fix `close the other sessions (Codex, Claude Code, VS Code) or give them the same CBM_CACHE_DIR; codebase-memory-mcp daemon stop retires the daemon once no session uses it`; a version record → detail names both versions; older than 24 h → nothing; malformed lines skipped; only the last 64 KiB read; no file → nothing; on Windows (`os.name == "nt"`) → nothing; `CBM_CACHE_DIR` in check's environment is read too (and the detail says check reads the folder of its own environment).
- [ ] **Step 2: FAIL. Step 3: Implement** read-only; never run the binary. **Step 4: PASS** plus `tests/test_check.py`. **Step 5: Commit** `feat(check): name codebase-memory's daemon conflict instead of a silent failed server`

### Task 9: A user's own table named like a loadout plugin server

**Files:** `cli/loadout/codex.py` (`checks`; a helper reading **loadout's** plugin manifest `mcpServers` file from the installed plugin root, guarded against broken JSON; `user_servers()`); Test: `tests/test_codex_server_twice.py` (new).

- [ ] **Step 1: Failing tests**: user `[mcp_servers.codebase-memory-mcp]` (+ `tools.*`) and loadout's plugin installed and enabled with `.codex-mcp.json` naming it → row `Codex MCP codebase-memory-mcp`, `warn`, detail `defined in config.toml and by the loadout plugin; Codex starts one of them`, fix `remove your [mcp_servers.codebase-memory-mcp] from ~/.codex/config.toml (the plugin provides it), or turn the loadout plugin off in Codex`; plugin disabled (`[plugins."loadout@agent-loadout"] enabled = false`) or not installed → nothing; another plugin's server of the same name → nothing; broken manifest JSON → nothing, no crash.
- [ ] **Step 2: FAIL. Step 3: Implement. Step 4: PASS** plus `tests/test_codex*.py`. **Step 5: Commit** `feat(check): name a Codex server defined in config.toml and by the loadout plugin`

### Task 10: "Now do this" without repeats; /reload-plugins clears its step when it can tell

**Files:** `cli/loadout/steps.py` (`derive`, `settle`, `Step`); `plugins/loadout/hooks/reload_check.py`; Test: `tests/test_open_steps.py`, `tests/test_reload_check.py`.

Rules:
- Whenever a CLI `codex/hooks` step exists, drop `codex/restart` (the hooks step already makes the user restart Codex). `derive` dedupes by id (first wins). `settle` drops a saved `codex/restart` when a `codex/hooks` step is saved too (existing files hold both).
- `Step` gets an optional `loadout_plugin: bool` (saved only when true; old files load). `derive` sets it on `claude/reload-plugins` when loadout's own plugin was installed or updated in this run (the fact names it, or `_plugin_copy_differs()`; pick the one `derive` can see).
- `reload_check.py` (Stop and SessionStart already run it): its plugin root is `Path(__file__).parent.parent`. When that root is inside the plugin cache **and** equals an `installPath` in `installed_plugins.json`, and the saved `claude/reload-plugins` step has `loadout_plugin: true`, remove that step from `open-steps.json`: keep the format (`{agent: [{id, text, reason, since, ...}]}`, indent 2, drop an empty agent), write a pid-unique temp file then `os.replace`; do nothing when the step is absent; missing/broken file → silent, exit 0; no lock.

- [ ] **Step 1: Failing tests** (reload_check tests copy the script into a fake plugin cache, as the existing tests do): one Codex step when restart + hooks (both `HOOKS_TEXT` and the "restart Codex and approve" text); no duplicate ids; settle drops a saved duplicate; Stop clears a `loadout_plugin` step when root == installPath; keeps it while outdated; keeps a step without `loadout_plugin` (only superpowers updated); root outside the cache → keeps; missing/broken file → silent exit 0; other steps untouched.
- [ ] **Step 2: FAIL. Step 3: Implement. Step 4: PASS** plus `tests/test_open_steps.py tests/test_reload_check.py tests/test_update*.py tests/test_maintenance.py`. **Step 5: Commit** `fix(steps): one Codex restart step, and /reload-plugins clears its step when loadout's plugin is the new one`

### Task 11: Plain words

**Files:** `cli/loadout/apply.py` (`_codex_summary`, its caller passes `plugins`); `cli/loadout/bootstrap.py` (report line for a kept own Serena); `cli/loadout/inventory.py` (`_binary_items` or `classify`); Test: `tests/test_codex_plugins.py`, `tests/test_bootstrap*.py`, `tests/test_bundled_claude.py`.

- [ ] **Step 1: Failing tests**:
  - `_codex_summary`: no `linked `/`copied ` line → `rules, plugins and MCP servers set up`; with one → `rules, plugins, MCP servers and skills set up`; `plugins=False` → `rules and MCP servers set up`; extension mode keeps its wording except "skills" only when linked.
  - Bootstrap with the user's own Serena (`user_serena` found) prints once `Serena: your own server in config.toml kept`; `apply_config` itself adds no such line (it runs at every update and sync).
  - Bundled claude (`runner.FALLBACK["claude"]` set to a real temp file, claude not on PATH) → inventory does not classify claude as `install`; it is an optional item reading `a claude on PATH for the terminal (VS Code's Claude Code extension's claude runs loadout's commands now)`.
- [ ] **Step 2: FAIL. Step 3: Implement. Step 4: PASS** plus `tests/test_bootstrap*.py tests/test_adopt.py tests/test_inventory.py tests/test_codex*.py`. **Step 5: Commit** `fix: say what was set up, name a kept own Serena, no missing claude with the extension's`

### Task 12: Docs and backlog

**Files:** `docs/how-to/troubleshooting.md` (rows: plugins installed with a missing marketplace; Codex plugins missing; codebase-memory-mcp daemon; Codex MCP defined twice; a table kept for tool approvals); `docs/reference/state-and-sync.md` (personal `loadout.json`); the page listing preferences (grep `agent_push_notifications` in `docs/`): the new preference, when it is asked, how to change it; `docs/reference/included-tools.md` (marketplaces registered); profiles docs for thesis; `docs/reference/modules.md` if a role changed; `AGENTS.md` (`adr/` range 0001-0037); `.superpowers/handoff/2026-10-13-hardening-backlog.md` (git-ignored): DONE line; synced-plugin item with the spec's evidence; finding 19 (adopt's latest ignores mise's `minimum_release_age`); Codex's writer normalising blank lines between sections (pre-existing).

- [ ] **Step 1:** docs-sync by hand: `git diff --stat main...HEAD`, each changed fact's home, links. **Step 2:** `uv run --python 3.12 --with pytest pytest -q tests/test_docs_links.py tests/test_docs_commands.py tests/test_readme.py tests/test_repo_static.py --deselect "tests/test_docs_links.py::test_links_resolve[docs/examples/Niklas_Serena_Config.md]"` → PASS. **Step 3: Commit** `docs: live tour fixes (official marketplace, Codex approvals, marketplaces when used, new check rows)`

### Final

- [ ] Full suite (Global Constraints): all pass. `claude plugin validate .` and `claude plugin validate plugins/loadout` (read-only).
