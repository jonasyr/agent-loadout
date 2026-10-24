# Your own codebase-memory setups: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** loadout recognises a codebase-memory-mcp (cbm) you set up yourself in every variant: Codex servers by command, the files `codebase-memory-mcp install` writes, your own cbm hooks, several binaries and diverging cache folders. It names each, and offers removal only after a yes, with a backup.

**Architecture:**
- A command-based `is_cbm` next to `is_serena` drives Codex detection, `check`, `inventory`/`adopt` and the hook guard.
- A new module, `cli/loadout/cbm_installer.py`, finds the installer's files and removes one with a backup. `check` and `adopt` use it.
- The hook pointer (`cbm_project.py`) stays silent when your own cbm hook runs.
- Two new `check` rows compare binaries and cache folders.

**Tech stack:** Python 3.11+ standard library, pytest with `fake_home` and `fake_runner`. The conftest guard (#63) fails any real program run.

**Spec:** `docs/superpowers/specs/2026-10-24-own-codebase-memory-design.md`

## Global constraints

- **Stdlib only:** standard library only in `cli/loadout/`. `plugins/loadout/hooks/*.py` cannot import loadout (subprocess argv lists with timeouts, never `shell=True`).
- **User files:** loadout changes a file of yours only through `adopt` after a yes, with a backup first (`bk.save_copy`, `bk.move` or `bk.record_command`), so `loadout restore` reverts it. `check` only reads. A removal without a backup is P1.
- **Agent isolation:** with an agent off (`targets`), none of that agent's files is read or changed.
- **External commands:** only through `runner.run`, as argv lists with timeouts. Tests use `fake_runner`.
- **No `install`:** never run `codebase-memory-mcp install`, `update` or `uninstall`.
- **Content:** never print a file's content in output beyond names and paths.
- **The installer's names** (cbm 0.12.1):
  - wrapper scripts `codebase-memory-session.sh` and `codebase-memory-coverage.sh` in `~/.claude/hooks/`;
  - the agent file `~/.claude/agents/codebase-memory.md`;
  - the AGENTS.md markers `<!-- codebase-memory-mcp:start -->` and `<!-- codebase-memory-mcp:end -->`;
  - the old names stay in `duplicates.LEGACY_SCRIPTS` (`cbm-code-discovery-gate`, `cbm-session-reminder`, `cbm-subagent-reminder`).
- **The new script names never join `LEGACY_SCRIPTS`.** `loadout update` must not remove them.
- **Commits:** Conventional Commits, with no AI attribution.
- **Code tools:** implementers use Serena (`find_symbol`, `find_referencing_symbols`) and codebase-memory (`search_graph`, `trace_path`, `get_code_snippet`, project `home-jonas-Documents-Code-agent-loadout`) before grep.

## Review focus

1. **A Codex table with settings of its own:** a cbm table under another name with `env` (for example `CBM_CACHE_DIR`), extra `args` or a pinned path is named by `check`, but `adopt` must not offer removal. (Task 1: `test_a_cbm_table_with_its_own_settings_is_only_named`.)
2. **AGENTS.md text outside the markers:** removing the installer's block must leave every byte before and after it unchanged. A file with a start marker but no end marker is not touched. (Task 2: `test_the_agents_block_is_removed_exactly_between_markers`, `test_an_unclosed_block_is_left_alone`.)
3. **The plugin off in Codex:** with `[plugins."loadout@agent-loadout"] enabled = false` and a user's cbm table enabled, the Codex guard still counts cbm as available. With the plugin on and the user's table `enabled = false`, it counts as available too. (Task 1: `test_codex_cbm_availability`.)
4. **`loadout update` never removes the new scripts:** a settings hook that runs `~/.claude/hooks/codebase-memory-session.sh` survives `maintenance.undo_reregistered` and `_stray_hook_scripts`. (Task 2: `test_update_leaves_the_installers_new_scripts_alone`.)
5. **An `echo` hook does not silence the pointer:** a Codex `SessionStart` `echo "… codebase-memory-mcp …"` hook leaves loadout's pointer on. A hook that runs `codebase-memory-mcp` or a wrapper script silences it. (Task 3: `test_an_echo_hook_does_not_silence_the_pointer`.)

---

### Task 1: cbm recognised by command, in Codex, check, adopt and the guard

**Files:**
- Modify:
  - `cli/loadout/codex.py`: add `is_cbm`; `servers_twice` counts a user's cbm table under another name; the `Codex MCP` rows;
  - `cli/loadout/inventory.py` (`_codex_items`, `classify`);
  - `cli/loadout/check.py`: reuse `codex.is_cbm` in `_is_cbm_server`, so there is one home;
  - `catalog.json` (`mcp-codebase-memory` gains a command match);
  - `cli/loadout/catalog.py`, only if `match` needs to read a command;
  - `plugins/loadout/hooks/mcp_guard.py` (`available`/`codex_server_enabled` for cbm).
- Test: `tests/test_codex*.py`, `tests/test_inventory*.py` / `tests/test_adopt*.py`, `tests/test_mcp_guard.py`, `tests/test_check*.py`.

**Interfaces:**
- Produces:
  - `codex.is_cbm(table: dict) -> bool`: the command's basename (lowercased, `.exe` stripped, either slash) is `codebase-memory-mcp`; or the command is `npx`, `bunx`, `uvx` or `uv` with an arg naming `codebase-memory-mcp`;
  - `codex.user_cbm() -> dict[str, dict]`: the user's Codex tables for which `is_cbm` holds, by name;
  - `codex.cbm_has_own_settings(table: dict) -> bool`: true when the table has `env` or `env_vars`, `args` other than the server's own (`[]`, or `["mcp"]` as in the plugin's `.codex-mcp.json`; read that file for the exact form), or a command that is a path (contains a slash).

**Behaviour:**
- **`check`:** for each `name` in `user_cbm()` with `name != "codebase-memory-mcp"`, when the plugin is installed and not switched off, add a warn row:
  - name: `Codex MCP <name>`;
  - detail: `runs codebase-memory-mcp next to the loadout plugin's; Codex starts two`;
  - fix: `remove your [mcp_servers.<toml_key(name)>] from <config> (the plugin provides it), or turn the loadout plugin off in Codex`.

  The same-name case keeps its existing row.
- **`inventory._codex_items`:** it skips a cbm table like `is_serena`, so it is never offered for Claude Code. Instead, `classify` gives it its own verdict:
  - `migrate` with the reason `Provided by loadout's Codex plugin; this table starts a second codebase-memory server.` and the id `mcp-codebase-memory`;
  - or, when `cbm_has_own_settings`, `keep` with the reason `It starts codebase-memory with settings of its own (env, args or a fixed path); remove it yourself if loadout's plugin should serve it.`

  `adopt`'s existing `_apply_mcp` Codex branch (`codex.remove_server`) does the removal. Make the item reach that branch: `own.is_codex(item)` must hold for it.
- **The Claude-side catalog match:** `mcp-codebase-memory` matches a server whose command is cbm (as `mcp-serena` matches `start-mcp-server`), so an own server named `cbm` gets `migrate`.
- **`mcp_guard`, `--agent codex`, server `codebase-memory-mcp`:** available when `binary_on_path` and either condition holds:
  - (the plugin is not switched off in `config.toml` and `[mcp_servers.codebase-memory-mcp].enabled` is not False);
  - or a table under any name with a cbm command is not `enabled = false`.

  The cbm test is inlined there (hooks cannot import loadout); a test keeps it equal to `codex.is_cbm` on a shared set of tables. Serena keeps today's rule.

- [ ] **Step 1: Write the failing tests:**
  - `test_is_cbm_recognises_commands`: true for `codebase-memory-mcp`, `/home/u/.local/bin/codebase-memory-mcp`, `C:\x\codebase-memory-mcp.exe`, `npx` with `["-y","codebase-memory-mcp"]`. False for `serena`, `cbm-other`, `uvx` with `["serena"]`.
  - `test_a_cbm_table_under_another_name_is_named_twice`: `user_servers` = `{"cbm": {"command": "codebase-memory-mcp"}}`, with the plugin installed → a `Codex MCP cbm` warn row with the detail above.
  - `test_a_cbm_table_is_never_offered_for_claude_code`: `_codex_items` has no `cbm` item; `classify` gives `migrate`.
  - `test_a_cbm_table_with_its_own_settings_is_only_named`: the table has `env = {CBM_CACHE_DIR = "/x"}` → verdict `keep` with the reason above.
  - `test_adopt_removes_a_cbm_table_with_a_backup`: `adopt --apply` on that verdict calls `codex.remove_server`, and `loadout restore` brings it back.
  - `test_claude_server_named_cbm_migrates`: `~/.claude.json` `mcpServers.cbm` with command `codebase-memory-mcp` → `migrate` with `mcp-codebase-memory`.
  - `test_codex_cbm_availability` (guard subprocess tests): the plugin off plus a user table on → available; the plugin on plus a user table `enabled = false` → available; the plugin off plus no table → unavailable; the plugin on plus `[mcp_servers.codebase-memory-mcp] enabled = false` and no other table → unavailable.
  - `test_guard_cbm_rule_matches_codex_is_cbm`: the same tables give the same answers from both.
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement it** as above.
- [ ] **Step 4: Run** the touched test files, then the full suite. Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat(codex): codebase-memory is recognised by its command, under any name"`

### Task 2: The installer's files: found, named, removed on a yes

**Files:**
- Create: `cli/loadout/cbm_installer.py`
- Modify:
  - `cli/loadout/check.py` (rows);
  - `cli/loadout/inventory.py` (items of kind `installer`);
  - `cli/loadout/adopt.py` (`_apply_installer`, wired into `apply` with the other kinds, and into the group the plan prints);
  - `catalog.json` (`hook-codebase-memory` matches the two new script names);
  - `cli/loadout/maintenance.py` / `cli/loadout/duplicates.py`, only as needed to keep `undo_reregistered`'s "resembles a kit item … left alone" note quiet for the new names.
- Test: `tests/test_cbm_installer.py`, plus touched `tests/test_adopt*.py` and `tests/test_maintenance*.py`.

**Interfaces:**
- Produces in `cbm_installer.py`:
  - `NEW_SCRIPTS = ("codebase-memory-session.sh", "codebase-memory-coverage.sh")`;
  - `AGENTS_START = "<!-- codebase-memory-mcp:start -->"` and `AGENTS_END = "<!-- codebase-memory-mcp:end -->"`;
  - `@dataclass Artefact`: `kind: str` (one of `"claude-hook"`, `"claude-script"`, `"claude-agent"`, `"codex-agents-block"`, `"codex-hook"`, `"codex-inline-hook"`), `agent: str` (`"claude"`/`"codex"`), `path: Path`, `label: str` (for the row, no file content), `removable: bool`, `where: dict` (what `remove` needs, such as event/group/hook indices);
  - `find() -> list[Artefact]`: only for agents that are on;
  - `remove(a: Artefact, bk) -> str`: one line in the form `adopt` prints; raises `ValueError` when `a.removable` is false.

**Detection** (each only when loadout's plugin is on for that agent):
- **`claude-hook`:** a settings hook whose command runs `codebase-memory-mcp hook…` or `~/.claude/hooks/<NEW_SCRIPTS>`. These are removable through the existing hook path, because the catalog's `hook-codebase-memory` now matches them, so `inventory`/`adopt` already offer `migrate`. `find` lists them for `check` only.
- **`claude-script`:** a `NEW_SCRIPTS` file in `~/.claude/hooks/` that no settings hook references. Removable: `bk.move`.
- **`claude-agent`:** `~/.claude/agents/codebase-memory.md`. Removable: `bk.move`.
- **`codex-agents-block`:** `~/.codex/AGENTS.md` (`$CODEX_HOME`) holding exactly one `AGENTS_START` before exactly one `AGENTS_END`. Removable: `bk.save_copy`, then rewrite with the span `[start, end + len(END)]` removed, plus one following newline if there is one. Bytes outside stay identical. An unclosed or repeated marker: not removable.
- **`codex-hook`:** an entry in `~/.codex/hooks.json` whose command runs `codebase-memory-mcp` or a `NEW_SCRIPTS` script, or is an `echo`/`printf` whose text contains `codebase-memory-mcp`. It must not be a loadout-recorded entry (`codex.read_record()["hooks"]`). Removable: `bk.save_copy`, then drop that hook (and its group when it is empty, and its event when empty). Rewrite in the file's own style (`jsonio.json_style` / `dumps_like`, as `codex_hooks.apply` does). When the style cannot be reproduced byte for byte: not removable.
- **`codex-inline-hook`:** the same match under `[hooks]` in `config.toml`. Not removable ("when unsure": the inline TOML rewrite is out of scope); it is named with the fix "remove it from config.toml by hand".

**`check`:** one warn row per artefact:
- name: `codebase-memory installer`;
- detail: `<label> (<path>): doubles loadout's <routing | project pointer | hooks>`;
- fix: `loadout adopt` when removable, else the manual fix.

**`inventory`/`adopt`:** every removable artefact except `claude-hook` (already covered) becomes an `Item(kind="installer", name=<label>, detail=<kind>, location=<path>, extra={"artefact": a})`. `classify` gives it `migrate` with the id `mcp-codebase-memory` and the reason `Written by codebase-memory-mcp install; loadout's plugin provides the same.` `_apply_installer(v, bk)` calls `cbm_installer.remove`.

- [ ] **Step 1: Write the failing tests** in `tests/test_cbm_installer.py`:
  - `test_find_lists_each_artefact` (one of each in `fake_home`; Codex and Claude on, the plugin on);
  - `test_the_agents_block_is_removed_exactly_between_markers` (before and after text with CRLF and no trailing newline both stay byte for byte; `restore` brings the block back);
  - `test_an_unclosed_block_is_left_alone`;
  - `test_a_codex_echo_hook_is_found_and_removed_with_a_backup` (the maintainer's shape: a `SessionStart` group with an `echo "...codebase-memory-mcp..."` command);
  - `test_loadouts_own_codex_hooks_are_never_artefacts`;
  - `test_an_inline_config_hook_is_named_not_removable`;
  - `test_an_agent_that_is_off_is_not_read`;
  - `test_check_names_each_artefact_without_content` (the row text holds the path and label, not the file text);
  - `test_adopt_offers_and_removes_with_a_yes_only` (a dry run changes nothing; `--apply --groups migrate` removes them);
  - `test_update_leaves_the_installers_new_scripts_alone` (`undo_reregistered` plus `_stray_hook_scripts` keep both the hook and the script, and print nothing about them).
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement it.**
- [ ] **Step 4: Run** the touched files, then the full suite. Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat(cbm): the installer's files are named and removed on a yes"`

### Task 3: Your own cbm hooks silence loadout's project pointer

**Files:**
- Modify: `plugins/loadout/hooks/cbm_project.py` (session-start and subagent-start).
- Test: `tests/test_cbm_project*.py`

**Interfaces:**
- Consumes: the `mcp_guard` helpers (`users_hook_runs`, `codex_users_hook_runs`, `_words`, `_program`, `NOT_A_RUN`). It imports the sibling via `sys.path`, as `refresh.py` does.

**Behaviour:** before printing the pointer, `cbm_project.py` stays silent when the agent's hooks (Claude Code: the settings files `users_hook_runs` reads; Codex: the files `codex_users_hook_runs` reads) hold, for the same event (`SessionStart` or `SubagentStart`), a hook that *runs*:
- the program `codebase-memory-mcp` (any subcommand);
- or a `NEW_SCRIPTS` wrapper script (by basename).

`echo`, `printf` and `#` forms do not count (the existing `NOT_A_RUN`). Add a small helper in `mcp_guard.py`: `runs_program(event, programs: set[str], cwd, home, agent) -> bool`, reusing the matcher and word logic.

- [ ] **Step 1: Write the failing tests:**
  - `test_own_cbm_session_hook_silences_the_pointer` (Claude Code settings `SessionStart` running `codebase-memory-mcp hook-augment` → no output);
  - `test_own_wrapper_script_silences_the_subagent_pointer` (Codex `hooks.json` `SubagentStart` running `~/.claude/hooks/codebase-memory-session.sh` → no output);
  - `test_an_echo_hook_does_not_silence_the_pointer`.
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement it.**
- [ ] **Step 4: Run** `tests/test_cbm_project*.py` and `tests/test_mcp_guard.py`. Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat(hooks): your own codebase-memory hooks silence loadout's project pointer"`

### Task 4: Binaries and cache folders

**Files:**
- Modify: `cli/loadout/check.py` (two rows, in the tool-setup group, only when cbm is in the kit for an agent that is on).
- Test: `tests/test_check*.py`

**Behaviour:**
- **`codebase-memory-mcp binaries`:**
  - **Finding them:** every distinct (realpath) executable named `codebase-memory-mcp` (`.exe` on Windows) in the `PATH` entries, in order;
  - **Their versions:** `runner.run([path, "--version"], timeout=10)`, parsing the first `\d+\.\d+\.\d+`;
  - **OK** with one, or when all versions are equal: detail `<n> on PATH, version <v>`;
  - **Warn** when the versions differ: detail `<path> <version>; <path> <version> …`, fix `the first one runs (<path>); remove the others or make them the same version`;
  - **Unknown version:** a failed `--version` counts as an unknown version and is shown as `?`.
- **`codebase-memory cache folders`:**
  - **Claude Code's folder:** a user's own Claude Code cbm server's `env.CBM_CACHE_DIR`, else `os.environ.get("CBM_CACHE_DIR")`;
  - **Codex's folder:** the plugin's server gets `None` (Codex passes no exported variables). A user's cbm table: its `env.CBM_CACHE_DIR`, or the process value when `env_vars` names it;
  - **Resolving:** `None` resolves to the default `~/.cache/codebase-memory-mcp` (use the same default as `cbm_project.cache_dir`; keep one home);
  - **When it shows:** only with both agents on;
  - **OK** when equal;
  - **Warn** when not: detail `two cache folders: <claude> (Claude Code) and <codex> (Codex); the servers and the project pointer see different indexes`, fix `leave CBM_CACHE_DIR unset everywhere, or set the same folder for both (Codex: env in your [mcp_servers] table)`.

- [ ] **Step 1: Write the failing tests:**
  - `test_one_binary_is_ok`;
  - `test_two_binaries_with_different_versions_warn` (two stubs in `tmp_path` dirs on `PATH`; `fake_runner` responses per path);
  - `test_cache_folders_equal_by_default`;
  - `test_an_exported_cache_dir_splits_claude_from_codex` (`CBM_CACHE_DIR` set → warn, since Codex does not pass it);
  - `test_a_codex_table_env_matching_the_export_is_ok`;
  - `test_rows_absent_with_codex_off`.
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement it.**
- [ ] **Step 4: Run** the touched files and the full suite. Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat(check): codebase-memory binaries and cache folders are compared"`

### Task 5: Docs, ADR and the live check

**Files:**
- Create: `docs/adr/0041-own-codebase-memory-by-command.md`. Format as ADR 0040; it amends ADR 0028 and ADR 0039's pointer.
- Modify:
  - `docs/adr/README.md`;
  - `docs/how-to/codex.md`: add "codebase-memory already set up?" next to "Serena already set up?";
  - `docs/how-to/your-own-tools.md` (if it lists Serena variants);
  - `docs/how-to/troubleshooting.md` (one row per new check row);
  - `docs/reference/hooks.md` (the pointer's silencing rule);
  - `docs/reference/setup-matrix.md` / `docs/reference/own-tools.md` (if they list Serena variants);
  - `docs/reference/modules.md` (`cbm_installer.py`);
  - `AGENTS.md` (decisions 0001–0041).
- **Real-machine step, inline:** run `bin/loadout check` on this machine and show the maintainer the new rows only. Expected: the `codebase-memory installer` rows for the `~/.codex/AGENTS.md` block and the `hooks.json` `echo` hook. Then run `bin/loadout adopt` (a dry run, which changes nothing) and show that both are offered under `migrate`. Do not apply without the maintainer's yes.

- [ ] **Step 1: Write the docs and the ADR.**
- [ ] **Step 2: Run** `tests/test_docs_links.py` (with the usual deselect) and the full suite. Expected: PASS.
- [ ] **Step 3: Commit.** `git commit -m "docs: your own codebase-memory setups (ADR 0041)"`
- [ ] **Step 4: Run the live check** and show its new rows.
