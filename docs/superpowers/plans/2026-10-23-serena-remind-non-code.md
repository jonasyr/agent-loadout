# Serena's reminder skips harmless searches: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** loadout's guard stops passing harmless searches and reads to Serena's `remind` hook in Claude Code and Codex. Harmless means a pipe filter, config, docs or text files, or files outside the project.

**Architecture:**
- A new stdlib-only hook module, `plugins/loadout/hooks/harmless.py`, mirrors Serena 2.1.0's shell parsing and decides whether a hook payload is harmless.
- `mcp_guard.py` asks it before it runs `serena-hooks remind`. A new `--agent codex` mode lets the guard serve Codex: it decides availability and equivalent hooks from Codex's files.
- For Codex, `remind` moves from `~/.codex/hooks.json` into the plugin's `codex.json`. `codex_hooks.apply` removes loadout's own entry, but only once the installed plugin copy carries the guarded hook.

**Tech stack:** Python 3.11+ standard library, pytest with `fake_home` and `fake_runner`, subprocess tests for the hook scripts (as in `tests/test_mcp_guard.py`).

**Spec:** `docs/superpowers/specs/2026-10-23-serena-remind-non-code-design.md`

## Global constraints

- **Stdlib only:** hook scripts in `plugins/loadout/hooks/` use the standard library only and cannot import `loadout`. Siblings are imported via `sys.path.insert(0, str(Path(__file__).resolve().parent))`, as `refresh.py` does.
- **External commands:** never `shell=True`. The guard keeps its argv-list subprocess call and its timeouts.
- **No extra process:** the filter adds no process start. It runs in the guard's Python process, before `serena-hooks` starts.
- **When in doubt, Serena:** anything not provably harmless goes to `remind`. That covers a mixed line, a pipe fed by a code-file read, a folder operand, no operand, an unparseable line, and an unknown suffix.
- **Agent isolation:** with `--agent codex`, the guard reads only Codex's files (`$CODEX_HOME` or `~/.codex`, plus `<cwd>/.codex/hooks.json`). Without it, the guard reads only Claude Code's files, as today.
- **User files:** a user's own Serena hook stays byte for byte. loadout removes only its recorded `remind` entry from `hooks.json`, after `bk.save_copy`.
- **Tests:** they use `fake_home` and `fake_runner`, or a temporary HOME as in `tests/test_mcp_guard.py`. They never touch the real `~/.claude`, `~/.codex` or `~/.config/loadout`.
- **Commits:** Conventional Commits, with no AI attribution.
- **Code tools:** implementers use Serena (`find_symbol`, `get_symbols_overview`) and codebase-memory (`search_graph`, `get_code_snippet`, project `home-jonas-Documents-Code-agent-loadout`) before grep.

## Review focus

1. **Variable and quoted operands:** `grep x "$f"`, `grep x $(git ls-files)`, `rg foo -- -weird.md`. A variable or command substitution as an operand is not provably harmless and must go to Serena. A `--` ends the options. (Task 1: `test_variable_operand_goes_to_serena`.)
2. **Relative paths that climb out:** `grep x ../other/a.py` from the repo root is outside the project and harmless. `grep x ./../repo/a.py` resolves back inside and is code. (Task 1: `test_relative_paths_resolve_against_cwd`.)
3. **Codex anchored matchers:** a user's `^Bash$` or `Bash` matcher in `~/.codex/hooks.json` must count as equivalent. A `^mcp__serena__` matcher must not match `Bash`. (Task 2: `test_codex_equivalence_uses_regex_search`.)
4. **Background sync:** `keep=True` must never migrate, even when the gate is true. A removal shifts the positions Codex keys its hook approvals on, and the background sync cannot ask. (Task 3: `test_background_sync_keeps_remind`.)
5. **No reminder during an upgrade:** while the copy is old (no guarded remind) or the plugin is switched off, `remind` must stay in `hooks.json`. (Task 3: `test_old_plugin_copy_keeps_remind_in_hooks_json`.)

---

### Task 1: The classifier (`harmless.py`)

**Files:**
- Create: `plugins/loadout/hooks/harmless.py`
- Test: `tests/test_harmless.py` (imports the module via `sys.path`, like the existing hook tests that import `mcp_guard`)

**Interfaces:**
- Produces:
  - `skips_remind(payload: dict) -> bool`: true when the payload is a call Serena's `remind` should not see;
  - `harmless_path(path: str, cwd: str) -> bool`;
  - the constants `NON_CODE: tuple[str, ...]`, `CONFIG_NAMES: frozenset[str]`, `GREP_CMDS: frozenset[str]` and `READ_CMDS: frozenset[str]`.

**Rules:** the spec's "Goals" 1–3 and its "Edge rules".
- **Tokenizing:** as Serena 2.1.0's `ShellCommandLine`. That is `shlex.shlex(posix=True, punctuation_chars=True, whitespace_split=True)`. Control operators are `&& || ; ;; | |& & ( )`. A redirection operator `> >> >| >& &> &>> < << <<< <& <>` drops its target token. Leading `VAR=x` words and the prefixes `command`, `env` and `exec` (with their flags) are skipped. The program is the basename, lowercased. On a `ValueError`, the line is not harmless.
- **Pipes:** a segment that follows `|` or `|&` belongs to the pipeline of the segment before it.
- **The command lists:**
  - `GREP_CMDS = {"grep","rg","ag","ack","fgrep","egrep","ugrep","ug"}`;
  - `READ_CMDS = {"cat","head","tail","sed","awk","less","more","bat","get-content","gc"}` (Serena's lists). A `sed` with `-i`, `--in-place` or `--in-place=…` is not a read.
- **`NON_CODE`:** equal to `cli/loadout/searches.py`'s `NON_CODE`.
- **`CONFIG_NAMES`:** `.gitignore`, `.gitattributes`, `.editorconfig`, `.npmrc`, `.dockerignore`, `.prettierrc`, `.eslintignore`, `Makefile`, `Dockerfile`, `LICENSE`, `CODEOWNERS`, `README`. Every name starting with `.env` is also non-code.
- **`harmless_path(p, cwd)`:**
  - true when the basename is in `CONFIG_NAMES` or starts with `.env`;
  - true when the lowercased suffix is in `NON_CODE`;
  - true when the path lies outside `cwd`, after `os.path.expanduser` and `os.path.normpath(os.path.join(cwd, p))`. Outside means not equal to `cwd` and not under `cwd + os.sep`;
  - false for an empty path, for a `$` in it (a variable or a command substitution), and for a backtick.
- **A grep segment:**
  - **Pattern and paths:** the pattern is the first non-option word, unless `-e`/`--regexp`/`-f`/`--file` gave it. The options in `searches.TAKES_VALUE` swallow their value. `--` ends the options. The remaining words are paths.
  - **Harmless when:**
    - (a) it is in a pipeline after an earlier segment, and no earlier segment of that pipeline has an operand that is a code path. A code path is any operand with a suffix that is not harmless, and that is inside `cwd`;
    - (b) a filter (`-t`, `--type`, `-g`, `--glob`, `--include`, `--iglob`, also in `=` form) passes `searches.doc_filter`;
    - (c) there is at least one path, and every path passes `harmless_path`.
- **A read segment** (in `READ_CMDS`, not `sed -i`): it blocks harmlessness when any operand of it has a suffix and is not `harmless_path`. This means a code file inside the project.
- **`skips_remind(payload)`:**
  - `tool_name == "Bash"`: the command is `tool_input.command`, else `tool_input.cmd`. A list is joined with `shlex.join`; a `["bash","-lc",script]` list uses its script. The result is true only when the line has at least one grep or read segment, every grep segment is harmless and no read segment blocks;
  - `tool_name == "Read"`: true when `harmless_path(file_path)`;
  - `tool_name == "Grep"`: true when `glob` or `type` passes `doc_filter`, or `path` is given and passes `harmless_path`;
  - anything else: false. A missing or non-string `cwd` gives false.

- [ ] **Step 1: Write the failing tests** in `tests/test_harmless.py`. Use a helper `bash(cmd, cwd="/r") = harmless.skips_remind({"tool_name":"Bash","tool_input":{"command":cmd},"cwd":cwd})`.
  - `test_pipe_filter_is_harmless`: `gh pr view 59 | grep -i codex`, `bin/loadout check --verbose 2>&1 | grep -E "auto_index"` → True.
  - `test_pipe_from_code_read_goes_to_serena`: `cat a.py | grep foo`, `sed -n 1,80p src/a.ts | grep bar` → False. `cat notes.md | grep x` → True.
  - `test_config_and_doc_files_are_harmless`: `grep -n x .gitignore`, `grep -n '^#' docs/a.md | tail -3`, `rg x pyproject.toml config.yaml`, `grep x .env.local` → True.
  - `test_doc_filter_is_harmless`: `rg foo -t md`, `grep -rn x --include='*.yml' .` → True.
  - `test_outside_project_is_harmless`: `grep -n x ~/.codex/config.toml`, `rg foo /tmp/x/a.rs`, `grep x ../other/a.py` → True.
  - `test_relative_paths_resolve_against_cwd`: `grep x ./../r/a.py` (cwd `/r`) → False.
  - `test_code_searches_go_to_serena`: `grep -n "class FakeRunner" tests/conftest.py`, `rg foo src/`, `grep -r x .`, `rg foo` (no path), `grep x a.vue` → False.
  - `test_mixed_line_goes_to_serena`: `grep x a.md; grep y b.py` → False. `sed -n 1,80p a.py; grep -n x notes.md` → False.
  - `test_variable_operand_goes_to_serena`: `grep x "$f"`, `grep x $(git ls-files)` → False. `rg foo -- -weird.md` → True.
  - `test_unparseable_line_goes_to_serena`: `grep "x a.md` → False.
  - `test_line_without_search_is_not_skipped`: `ls -la`, `git status` → False.
  - `test_read_tool`: `Read` of `/tmp/x/a.rs` (cwd `/r`) → True. `/r/a.py` → False. `/r/a.md` → True.
  - `test_grep_tool`: `{"pattern":"x","glob":"*.md"}` → True. `{"pattern":"x","path":"/r/src"}` → False. `{"pattern":"x","path":"/home/u/.codex"}` → True.
  - `test_codex_argv_and_cmd_forms`: `{"cmd": "gh x | grep y"}` → True. `{"command": ["bash","-lc","grep x a.md"]}` → True.
  - `test_non_code_matches_loadout_usage`: `harmless.NON_CODE == loadout.searches.NON_CODE`. The test may import `loadout`.
- [ ] **Step 2: Run them and see them fail.** Run `uv run --python 3.12 --with pytest pytest -q tests/test_harmless.py`. Expected: FAIL, because the module does not exist.
- [ ] **Step 3: Implement `plugins/loadout/hooks/harmless.py`** per the rules above. Give it a module docstring that names Serena 2.1.0 `PreToolUseRemindAboutSymbolicToolsHook` as the parsing it mirrors, and `docs/reference/hooks.md`.
- [ ] **Step 4: Run the tests and see them pass.** Expected: all PASS.
- [ ] **Step 5: Commit.** `git add plugins/loadout/hooks/harmless.py tests/test_harmless.py && git commit -m "feat(hooks): classify searches Serena's reminder cannot help with"`

### Task 2: The guard skips harmless calls and serves Codex

**Files:**
- Modify: `plugins/loadout/hooks/mcp_guard.py` (`should_run`, `main`, plus new Codex equivalence helpers)
- Modify: `plugins/loadout/hooks/codex.json` (a new `PreToolUse` group)
- Test: `tests/test_mcp_guard.py`, and the existing hook-file tests (`tests/test_hooks*.py` or wherever `codex.json`'s shape is asserted; find them with `search_code`)

**Interfaces:**
- Consumes: `harmless.skips_remind(payload) -> bool` (Task 1).
- Produces:
  - **The CLI form** `mcp_guard.py [--agent codex] <server> <command...>`: without `--agent` it behaves exactly as today, with `--agent claude` the same;
  - `should_run(server, argv, payload, home, agent="claude") -> bool`;
  - `codex_users_hook_runs(argv, cwd, home, tool) -> bool`;
  - **the plugin hook** in `codex.json`: `PreToolUse`, matcher `Bash`, command `"${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" --soft --python "${CLAUDE_PLUGIN_ROOT}/hooks/mcp_guard.py" --agent codex serena serena-hooks remind --client=codex`, timeout 5.

**Behaviour:**
- **The new first check:** for `argv[1] == "remind"`, `harmless.skips_remind(payload)` → silent (exit 0, no output, `serena-hooks` not started). Import `harmless` lazily, only for `remind`, inside the existing `try`: an import error must leave the guard silent, as it is today.
- **`agent == "codex"`:**
  - **Availability:** `binary_on_path(argv[0]) and codex_server_enabled(server, home)`. Never read `~/.claude.json` or Claude's settings.
  - **Equivalence:** `codex_users_hook_runs` looks for a hook running the same program and subcommand (the existing `_words`, `_program` and `NOT_A_RUN` logic) for `PreToolUse`, whose group matcher matches `tool` with `re.search` (None, `""` or `"*"` match everything). It looks in `<CODEX_HOME or home/.codex>/hooks.json` (`{"hooks":{event:[groups]}}`), in `config.toml`'s `[hooks]` tables (via `tomllib`; on a parse error, nothing found) and in `<cwd>/.codex/hooks.json`. loadout's own `serena-hooks remind --client=codex` entry in `hooks.json` counts as equivalent, so there is no double reminder during the migration (spec, Codex step 4).
- **`--available`:** the mode stays as it is.

- [ ] **Step 1: Write the failing tests** in `tests/test_mcp_guard.py`, reusing `env`, `_payload` and `_run`. Extend `_run` with an `agent=None` parameter that prepends `--agent <agent>`.
  - `test_guard_skips_harmless_search`: payload command `gh pr view 1 | grep x` → `_run` returns None. The stub's output is absent, so `serena-hooks` did not run.
  - `test_guard_runs_remind_for_code_search`: command `rg Foo src/` → `out["ran"] == "remind --client=claude-code"`.
  - `test_guard_skips_only_for_remind`: a harmless payload with command `("serena-hooks","auto-approve","--client=claude-code")` → it runs.
  - `test_codex_mode_reads_codex_config`: `.codex/config.toml` with `[mcp_servers.serena]\nenabled = false` → None. Without it → it runs. A `~/.claude.json` that disables serena changes nothing in Codex mode.
  - `test_codex_equivalence_uses_regex_search`: `~/.codex/hooks.json` with group matcher `^Bash$` running `serena-hooks remind --client=codex` → None. Matcher `^mcp__serena__` → it runs.
  - `test_codex_equivalence_in_project_and_inline`: the same remind in `<repo>/.codex/hooks.json` → None. In `~/.codex/config.toml` as `[[hooks.PreToolUse]]\nmatcher = "Bash"\n[[hooks.PreToolUse.hooks]]\ntype = "command"\ncommand = "serena-hooks remind --client=codex"` → None.
  - `test_codex_json_runs_guarded_remind`: load `plugins/loadout/hooks/codex.json` and assert the `PreToolUse` group with matcher `Bash` and the exact command and timeout from Interfaces.
- [ ] **Step 2: Run them and see them fail.** Run `uv run --python 3.12 --with pytest pytest -q tests/test_mcp_guard.py`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement it** in `mcp_guard.py`, and add the group to `codex.json`. Keep the existing rtk group on `Bash` as its own group, in the same order. Update the module docstring to cover the harmless skip and the Codex mode.
- [ ] **Step 4: Run** `tests/test_mcp_guard.py` plus every test file that asserts the hook files. Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat(hooks): the guard skips harmless searches and runs Serena's reminder for Codex"`

### Task 3: Codex's `remind` moves from `hooks.json` into the plugin

**Files:**
- Modify: `cli/loadout/codex.py`. Add `loadout_copy() -> Path | None`, `plugin_runs_remind() -> bool` and the re-run in `apply_parts`. Make `check._codex_copies` use `loadout_copy()`.
- Modify: `cli/loadout/codex_hooks.py` (the `wanted` computation in `apply`)
- Modify: `cli/loadout/check.py` (`_codex_copies` delegates)
- Test: `tests/test_codex_hooks.py`, plus `tests/test_codex*.py` for `apply_parts`

**Interfaces:**
- Consumes: the exact command from Task 2's Interfaces.
- Produces:
  - `codex.loadout_copy() -> Path | None`: the folder `check._codex_copies` finds today (`plugins/cache/agent-loadout/loadout/local`, else the newest subfolder);
  - `codex.plugin_runs_remind() -> bool`: true when `loadout_copy()/hooks/codex.json` parses and has a `PreToolUse` hook whose command contains both `mcp_guard.py` and `serena-hooks remind`, **and** `_plugin_hooks_on(config.toml data)` is true.

**Behaviour:**
- **The gate:** in `codex_hooks.apply`, when `wanted` would be `SERENA_HOOKS` and `not keep and codex.plugin_runs_remind()`, `wanted` is `SERENA_HOOKS` without the `remind` row. The existing loop then removes loadout's recorded `remind` group, with `bk.save_copy` as today. A user's own remind entry is never in the record, so it stays.
- **Ruling (the spec said "not switched off"):** the gate requires `enabled = true`, which `codex plugin add` writes. A missing entry keeps `remind` in `hooks.json`. That is the safe direction, because a wrong yes would leave Codex without any reminder.
- **The re-run:** in `apply_parts`, record `before = codex_hooks wanted the remind` (that is, `not codex.plugin_runs_remind()`) before the hooks part. After the plugins part, if `"hooks" in run`, `not keep` and `plugin_runs_remind()` changed, run `parts["hooks"] += codex_hooks.apply(bk, keep=keep)` once.
- **Self-healing:** with the gate false (plugin removed, switched off, or an old copy), `remind` is wanted again and is added back by the existing code.

- [ ] **Step 1: Write the failing tests.**
  - In `tests/test_codex_hooks.py`, using a helper that writes a fake plugin copy under `fake_home/.codex/plugins/cache/agent-loadout/loadout/local/hooks/codex.json` and `[plugins."loadout@agent-loadout"]\nenabled = true` in `config.toml`:
    - `test_remind_leaves_hooks_json_when_the_plugin_runs_it`: hooks.json holds loadout's six recorded entries, and the plugin copy has the guarded remind. `apply` removes only the remind group. The other five stay. `bk` has a saved copy.
    - `test_old_plugin_copy_keeps_remind_in_hooks_json`: the copy's `codex.json` has no remind → no change.
    - `test_switched_off_plugin_keeps_remind`: `enabled = false` → no change. With the remind already removed earlier, it is added back.
    - `test_background_sync_keeps_remind`: `keep=True` with the gate true → no change.
    - `test_users_own_remind_stays`: an unrecorded `serena-hooks remind --client=codex` group in `hooks.json`, with the gate true → byte for byte unchanged.
  - In the `apply_parts` tests, `test_migration_finishes_in_one_run`: the plugin part (stubbed) creates the copy with the guarded remind during the run. After `apply_parts`, hooks.json has no loadout remind.
- [ ] **Step 2: Run them and see them fail.** Expected: FAIL (no gate).
- [ ] **Step 3: Implement it** as above. `check._codex_copies` returns `[("Codex", codex.loadout_copy(), fix)]` when it is not None.
- [ ] **Step 4: Run** `uv run --python 3.12 --with pytest pytest -q tests/test_codex_hooks.py tests/test_check*.py tests/test_codex*.py`. Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat(codex): Serena's reminder runs from the plugin once its copy carries it"`

### Task 4: Docs, ADR and the upstream issue draft

**Files:**
- Create: `docs/adr/0040-serena-remind-skips-harmless.md`. It uses the ADR format of `docs/adr/0039-…` (Status, Date, Source pointing to the spec, Amends 0039 and 0028; Context with the measurement table from the spec; Decision; Alternatives; Consequences; In the code).
- Modify:
  - `docs/adr/README.md` (the index row);
  - `docs/adr/0039-….md` and `docs/adr/0028-….md` (an "Amended by: 0040" line only; never edit an accepted decision);
  - `docs/reference/hooks.md` (the guard's harmless rule; Codex's Serena hook table: `remind` comes from the plugin once its copy carries it);
  - `docs/reference/modules.md` (`harmless.py`);
  - `rules/tooling.md` (the reminder sentence);
  - `AGENTS.md` ("decisions 0001-0039" → "0001-0040");
  - `docs/how-to/codex.md` and `docs/how-to/troubleshooting.md` only where they state that `remind` lives in `hooks.json`.
- Create, uncommitted: `<scratchpad>/serena-issue.md`, the upstream issue draft.

**Copy fixed by the spec:**
- `rules/tooling.md`: "Serena's reminder hook denies a code search once when Serena's symbolic tools fit better (the next call goes through); loadout lets searches in config, docs, piped output and files outside the project through without it." Keep the existing docs-hint clause after it.
- **The issue draft:** the counting rule (greps are path-blind, pipes are counted), four anonymised example commands (one per class), and the two proposals from the spec's "Upstream issue" section. Also the question whether config greps should count, since `_CODE_FILE_EXTENSIONS` holds `.json`, `.yaml`, `.toml` and `.html`.

- [ ] **Step 1: Write the ADR and update the pages** listed above. Find the statements to change with `search_code` for `remind` in `docs/` and `rules/`.
- [ ] **Step 2: Run the docs tests.** Run `uv run --python 3.12 --with pytest pytest -q tests/test_docs_links.py --deselect "tests/test_docs_links.py::test_links_resolve[docs/examples/Niklas_Serena_Config.md]"` and the whole suite. Expected: PASS.
- [ ] **Step 3: Commit.** `git commit -m "docs: Serena's reminder skips harmless searches (ADR 0040)"`
- [ ] **Step 4: Write the issue draft** to the scratchpad and show it to the maintainer. It is not posted without their yes.
