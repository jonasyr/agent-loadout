# Codex extension mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** With only VS Code's Codex extension, loadout sets up everything the CLI user gets (plugins, skills, codebase-memory), hooks are approved in the extension, and `loadout check` turns green once they are.

**Architecture:** One decision point in `codex.py` (`mode()`: "cli", "extension" or None) replaces the scattered `runner.have("codex")` checks. Every codex command runs through `program()`, which returns the codex of that mode. The extension-mode skips and their texts go. Hooks, steps and check rows ask `mode()` only for wording (the CLI's `/hooks` vs the extension's hooks icon).

**Tech Stack:** Python 3.11+ standard library (`cli/loadout/`), pytest with the `fake_home` / `fake_runner` fixtures.

**Spec:** `docs/superpowers/specs/2026-10-22-codex-extension-mode-design.md`

## Global Constraints

- Python 3.11+, standard library only in `cli/loadout/`.
- Tests use `fake_home` and `fake_runner`. No test reaches the real `~/.claude`, `~/.claude.json`, `~/.codex` or `~/.config/loadout`, or runs a real `claude`/`codex`/installer.
- External commands only through `runner.run` with argument lists. The extension's codex path can hold spaces (macOS "Application Support", Windows user names).
- Undo records keep `["codex", ...]` (`backup._allowed_run` matches them). At replay, `codex` resolves to `codex.program()`.
- loadout never writes `[hooks.state]` trust.
- The 0.161 floor compares (major, minor) only: `0.161.0-alpha` passes. An extension codex under 0.161, with no usable CLI, means Codex is not set up (today's `EXT_OLD`).
- "Reads another home" covers only what loadout detects today: `vscode.reads_home`, a Windows window, Remote-WSL, and the WSL/Windows split.
- Conventional Commits, no `Co-Authored-By` or other AI attribution.
- Test command: `uv run --python 3.12 --with pytest pytest -q --deselect "tests/test_docs_links.py::test_links_resolve[docs/examples/Niklas_Serena_Config.md]"`. Never commit `docs/examples/Niklas_Serena_Config.md`.
- Before grep, use codebase-memory (`search_graph`, `trace_path`) and Serena (`find_symbol`, `find_referencing_symbols`).

Exact texts (used verbatim by the tasks):

- `HOOKS_EXTENSION = "approve loadout's hooks in VS Code's Codex extension: the hooks icon in the prompt bar, then Allow all (or Settings > Hooks)"`
- `HOOKS_EXTENSION_CHANGED = "approve the changed loadout hooks in VS Code's Codex extension: the hooks icon in the prompt bar, then Allow all (or Settings > Hooks)"`
- `PLUGINS_OLD = "plugins: not installed: VS Code's Codex extension's codex has no plugin command; update the extension in VS Code, then run loadout update"`
- `CLI_OPTIONAL = "not installed (optional: VS Code's Codex extension runs its own)"`
- `CLI_UNUSABLE = "{why}; loadout uses VS Code's Codex extension's codex instead"`
- `RESTART_EXTENSION = "reload the VS Code window (Command Palette: Developer: Reload Window) so the Codex extension loads the plugins"`

## Review Focus

1. **Plugin listing fails** (`installed_plugins()` is None) in extension mode. `hooks_status` must not stay "untrusted" forever after Allow all. Test in Task 4.
2. **An undo recorded in extension mode, replayed after the CLI was installed** (or the reverse). `codex plugin remove` runs with the codex of the current mode. Test in Task 2.
3. **The extension's codex path has a space.** Every plugin command is one argv element with that path, never a shell line. Test in Task 3.
4. **A broken CLI and no usable extension.** Today's reason and fix stay unchanged (no "uses the extension instead" text). Test in Task 2.
5. **A Remote-WSL window while Codex runs on Windows only** (`windows_only`). That gap row stays after `CODEX_GAP` goes. Test in Task 5.

---

### Task 1: Versions keep their prerelease

**Files:**
- Modify: `cli/loadout/versions.py:11-13` (`parse_version`) and `:44-45` (`fmt`)
- Test: `tests/test_version.py`

**Interfaces:**
- Produces: `versions.Version(tuple)`, which holds `(major, minor, patch)` and an attribute `pre: str` (`""` for a release). `parse_version(text) -> Version | None`. `fmt(v)` prints `1.2.3` or `1.2.3-alpha.2`.

- [ ] **Step 1: Write the failing tests** in `tests/test_version.py`:

```python
def test_a_prerelease_sorts_before_its_release():
    assert versions.parse_version("codex-cli 0.163.0-alpha.2") < versions.parse_version("0.163.0")
    assert versions.parse_version("0.163.0-alpha.2") > versions.parse_version("0.162.9")
    assert versions.parse_version("0.163.0-alpha.2") != versions.parse_version("0.163.0")

def test_a_release_still_equals_its_plain_tuple():
    assert versions.parse_version("v2.102.1") == (2, 102, 1)
    assert versions.parse_version("2.102.1 (abc)") == (2, 102, 1)

def test_fmt_shows_the_prerelease():
    assert versions.fmt(versions.parse_version("0.163.0-alpha.2")) == "0.163.0-alpha.2"
    assert versions.fmt(versions.parse_version("0.163.0")) == "0.163.0"
```

- [ ] **Step 2: Run them.** Run: `uv run --python 3.12 --with pytest pytest -q tests/test_version.py`. Expected: FAIL on the prerelease asserts.
- [ ] **Step 3: Implement `Version`.** It subclasses tuple with `__new__(cls, parts, pre="")`. Ordering and equality compare `(parts, 0 if pre else 1, pre)`. A release compares equal to the plain tuple; a prerelease never does. `__hash__` follows `__eq__`. The prerelease is the `-[0-9A-Za-z.]+` right after the three numbers. Build metadata (`+…`) is ignored.
- [ ] **Step 4: Run the whole suite.** `maintenance.py:297/301`, `pkgmgr.py:78` and `find_outdated` compare these values. Expected: all pass. Fix any test that asserted the old suffix-dropping behaviour (`0.163.0-alpha == 0.163.0`). Each changed test gets a ruling line in the ledger.
- [ ] **Step 5: Commit** `fix(versions): a prerelease sorts before its release`.

---

### Task 2: One Codex mode, one program

**Files:**
- Modify: `cli/loadout/codex.py`:
  - `:42-70` `unavailable`
  - `:101-127` `extension_state` / `program`
  - every `["codex", ...]` literal: `:64`, `:1167`, `:1182`, `:1197`, `:1382`, `:1392`, `:1406` (the undo records at `:1389`/`:1412` stay `"codex"`)
- Modify: `cli/loadout/update.py:82-96` (the printed plan commands use `codex.program()`)
- Modify: `cli/loadout/backup.py:270-282` (replay: `cmd[0] == "codex"` runs as `[codex.program(), *cmd[1:]]` after `_allowed_run(cmd)` passes on the recorded form)
- Test: `tests/test_codex_mode.py` (new); update `tests/test_codex_extension_mode.py`

**Interfaces:**
- Produces:
  - `codex.mode() -> str | None`: `"cli"` when a usable codex is on PATH, else `"extension"` when this side's extension runs a usable one, else None.
  - `codex.cli_problem() -> str | None`: why the codex on PATH is unusable (too old, no version, the Windows codex in WSL); None when it is usable or absent.
  - `codex.program() -> str`: `"codex"` in CLI mode, `str(ext.binary)` in extension mode, `"codex"` otherwise.
  - `codex.CLI_UNUSABLE` (text above).
- `unavailable()` keeps its signature. It returns None when `mode()` is not None and the `SHARED_HOME` rule passes. Otherwise it returns `cli_problem()` if a CLI is on PATH, then `extension_state()`'s reason, then `NOT_FOUND`.
- The extension is looked at only when the CLI is absent or unusable. `test_a_cli_on_path_changes_nothing` stays as it is.

- [ ] **Step 1: Write the failing tests** in `tests/test_codex_mode.py`. Reuse the `ext_only` setup from `test_codex_extension_mode.py` (move it to `conftest.py` as the fixture `codex_ext`, returning the binary path).

```python
def test_a_too_old_cli_next_to_a_usable_extension_uses_the_extension(codex_ext, fake_runner):
    fake_runner.missing.discard("codex")
    fake_runner.responses[("codex", "--version")] = runner.Result(0, "codex-cli 0.150.0\n", "")
    assert codex.mode() == "extension" and codex.program() == str(codex_ext)
    assert codex.unavailable() is None
    assert "0.150.0" in codex.cli_problem()

def test_a_broken_cli_without_an_extension_keeps_todays_reason(fake_home, fake_runner):
    fake_runner.responses[("codex", "--version")] = runner.Result(0, "codex-cli 0.150.0\n", "")
    assert codex.mode() is None
    assert codex.unavailable() == "codex 0.150.0 is too old; loadout needs 0.161 or newer (update it: mise upgrade codex)"

def test_undo_of_a_plugin_runs_with_the_current_modes_codex(codex_ext, fake_runner, fake_home):
    # record ["codex","plugin","remove","x@m"] in a backup, restore it: the call is [str(codex_ext),"plugin","remove","x@m"]
    ...
```

  The third test builds its backup the way `tests/test_restore*.py` does. Its assertion is the exact list above, plus `["codex", "plugin", "remove", "x@m"]` not in `fake_runner.calls`.
- [ ] **Step 2: Run them.** Expected: FAIL (`mode` not defined).
- [ ] **Step 3: Implement** `mode`, `cli_problem`, the new `unavailable`/`program`, the `program()` literals and the backup replay.
- [ ] **Step 4: Run** `tests/test_codex_mode.py tests/test_codex_extension_mode.py tests/test_wsl_codex_*.py tests/test_restore*.py`, then the whole suite. Expected: all pass, with no change to CLI-mode test expectations (`"codex"` stays argv[0] there).
- [ ] **Step 5: Commit** `feat(codex): one mode decides which codex runs, a broken CLI falls back to the extension`.

---

### Task 3: Plugins in extension mode

**Files:**
- Modify: `cli/loadout/codex.py`:
  - `:1431` `missing_routes`
  - `:1497` `apply_plugins` (drop the skip)
  - `:1776` (`plugin_versions` when `mode()` is not None)
  - `:1831-1847` `checks` (one branch for both modes: the `Codex plugin`, `Codex plugins missing` and `Codex MCP <name>` rows run when `mode()` is not None; delete the `else` branch)
  - delete `PLUGINS_EXTENSION`, add `PLUGINS_OLD`
- Modify: `cli/loadout/apply.py:150-161` (`_codex_summary`: "plugins" whenever plugins were handled; keep the suffix " for VS Code's Codex extension" when `mode() == "extension"`) and `:219` (drop the `PLUGINS_EXTENSION` branch)
- Modify: `cli/loadout/update.py:52` (`_codex_item` runs in both modes) and `:153` (drop the note)
- Modify: `cli/loadout/codex_project.py:137-150` (delete `PLUGINS_EXTENSION_NOTE` and its branch; `:215` follows)
- Modify: `cli/loadout/project.py:199-202`, `:245`, `:258`, `:336`, `:401`, `:517` (the extension-note branches go)
- Test: `tests/test_codex_extension_plugins.py` (new); change `test_codex_extension_mode.py::test_plugins_are_skipped_with_one_line`, `test_vscode_pr2_review.py::test_update_does_not_offer_a_plugin_refresh_in_extension_mode`, `test_codex_project.py:370-395` (the three extension-mode tests now assert installs)

**Interfaces:**
- Consumes: `codex.mode()`, `codex.program()` (Task 2).
- Produces: `codex.PLUGINS_OLD` (text above). When the first `[program(), "plugin", "marketplace", ...]` call fails with `unrecognized subcommand` in stderr, `apply_plugins` returns `[PLUGINS_OLD]` and runs no further plugin command.

- [ ] **Step 1: Write the failing tests:**
  - `test_extension_mode_adds_marketplaces_and_plugins_with_the_extensions_codex`: `apply_plugins(bk)` calls `[str(codex_ext), "plugin", "marketplace", "add", <src>, "--json"]` and `[str(codex_ext), "plugin", "add", "loadout@agent-loadout", "--json"]`. The recorded undo is `["codex", "plugin", "remove", "loadout@agent-loadout"]`.
  - `test_a_path_with_a_space_is_one_argument`: the extension folder sits under `fake_home / "Application Support"`. Every plugin call's argv[0] equals that full path.
  - `test_an_extension_codex_without_a_plugin_command_skips_plugins_once`: the response to `marketplace add` is `Result(2, "", "error: unrecognized subcommand 'plugin'")`. The result is `[codex.PLUGINS_OLD]` and there is exactly one plugin call.
  - `test_update_plans_the_plugin_refresh_in_extension_mode`: the update plan items hold the Codex refresh group, and the notes do not contain "loads none".
  - `test_profile_installs_its_codex_plugins_in_extension_mode`: `codex_project.plugins(prof, dry_run=False)` calls `[str(codex_ext), "plugin", "add", ...]`.
  - `test_check_lists_missing_plugins_and_servers_twice_in_extension_mode`: `codex.checks()` has rows named `Codex plugins missing` and `Codex MCP codebase-memory-mcp` with the same setup as `tests/test_codex_server_twice.py`, but `codex_ext` instead of a CLI.
  - `test_extension_summary_names_plugins_and_skills_only_when_linked` (finding 25): `_codex_summary(["rules: ok"], plugins=True)` in extension mode is `"rules, plugins and MCP servers set up for VS Code's Codex extension"`.
- [ ] **Step 2: Run them.** Expected: FAIL (plugins are skipped today).
- [ ] **Step 3: Implement** the changes listed under Files.
- [ ] **Step 4: Run** the new file, the changed tests, then the whole suite. Expected: all pass. `grep -rn "PLUGINS_EXTENSION" cli tests` is empty.
- [ ] **Step 5: Commit** `feat(codex): install loadout's plugins for VS Code's Codex extension too`.

---

### Task 4: Hooks that can clear in the extension

**Files:**
- Modify: `cli/loadout/codex.py:1916-1960` (`hooks_status`), `:1977-1999` (`open_steps`), `:1870-1875` (the `Codex hooks` row fix); replace `HOOKS_NO_CLI` with `HOOKS_EXTENSION` / `HOOKS_EXTENSION_CHANGED`
- Modify: `cli/loadout/steps.py:175-226` (`derive`) and `:284-292` (`settle`)
- Test: `tests/test_codex_extension_hooks.py` (new); change `tests/test_open_steps.py:246`, `tests/test_codex_extension_mode.py::test_still_to_do_names_the_cli_for_hooks`

**Interfaces:**
- Consumes: `codex.mode()` (Task 2), `codex.installed_plugins()`.
- `hooks_status(remember=False)` keeps its signature. Tests monkeypatch it as `lambda remember=False: ...`. The required keys are Serena's, plus `hook_keys()` when `"loadout@agent-loadout"` is in `installed_plugins()`. When `installed_plugins()` is None, it falls back to `hook_keys()` only when `[hooks.state]` already has a key starting with `HOOK_PLUGIN + ":"`.
- Text by mode:
  - CLI mode keeps every text it has today.
  - Extension mode: the hooks step and the row's fix are `HOOKS_EXTENSION` ("untrusted") or `HOOKS_EXTENSION_CHANGED` ("changed").
  - `codex/restart` in extension mode is `RESTART_EXTENSION`. It is derived when plugins changed or an upgraded binary starts a Codex server, as in CLI mode.
  - `settle` drops `codex/restart` only when `mode()` is None.
  - The rule "a hooks step replaces the restart step" stays.

- [ ] **Step 1: Write the failing tests:**
  - `test_allow_all_in_the_extension_clears_the_hooks`: `config.toml` `[hooks.state]` has trusted hashes for every `codex_hooks.serena_items()` key and every `hook_keys()` key, and `installed_plugins()` contains the loadout plugin. Then `hooks_status() == "trusted"`, `open_steps()` has no hooks line, and `codex.checks()` has `Codex hooks` ok.
  - `test_without_the_loadout_plugin_only_serenas_hooks_count`: Serena keys only, and the plugin is not installed. Result: `"trusted"`.
  - `test_a_failed_plugin_listing_does_not_block_the_approval`: `codex plugin list --json` fails, and the state has Serena keys only. Result: `"trusted"`. With one `HOOK_PLUGIN` key present and the others missing, the result is `"untrusted"`.
  - `test_extension_hooks_step_names_the_hooks_icon`: untrusted means `open_steps()[0] == codex.HOOKS_EXTENSION`. `derive(...)` gives a `codex/hooks` step with that text, and "Codex CLI" and "--install" are in no line.
  - `test_extension_restart_step_reloads_the_window`: plugins installed (fact `codex_plugins_installed`) and hooks trusted give a `codex/restart` step with `RESTART_EXTENSION`. `settle` keeps it in extension mode.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the new file, `tests/test_open_steps.py`, `tests/test_codex_hooks.py`, `tests/test_codex_serena_hooks.py`, then the whole suite. Expected: all pass. `grep -rn "HOOKS_NO_CLI" cli tests` is empty.
- [ ] **Step 5: Commit** `fix(codex): hooks approved in VS Code's Codex extension count, and its steps say where`.

---

### Task 5: Check rows and bootstrap wording

**Files:**
- Modify: `cli/loadout/codex.py:1822-1830` (`checks`). After the `Codex` row:
  - with `mode() == "extension"` and no codex on PATH, add `CheckResult("Codex CLI", True, CLI_OPTIONAL)`;
  - with a codex on PATH whose `cli_problem()` is set (and `mode() == "extension"`), add `CheckResult("Codex CLI", False, CLI_UNUSABLE.format(why=cli_problem()), unavailable_fix(cli_problem()), "warn")`.
- Modify: `cli/loadout/check.py:241-247` (the `binary codex` row: when `codex.mode() == "extension"`, `continue`; the `Codex CLI` row covers it)
- Modify: `cli/loadout/check.py:493-497` and `:547-548` (delete `CODEX_GAP`/`CODEX_GAP_FIX` and their branch). Keep the Remote-WSL `windows_only` gap and the version gaps. When a CLI is in use, the version gap's text reads `"its bundled Codex is {version}; it may not load what the Codex CLI set up (loadout needs 0.161 or newer)"`.
- Modify: `cli/loadout/bootstrap.py:805-834`:
  - `CODEX_CLI_QUESTION = "\nVS Code's Codex extension runs its own Codex, and loadout sets it up fully. Install the Codex CLI too (optional, for codex in a terminal)? [y/N] "`. The default is no: only `y`/`yes` installs.
  - `CODEX_CLI_WHY = "installed alongside VS Code's Codex extension (optional, for codex in a terminal)"`.
  - `CODEX_CLI_DECLINED = "not installed (optional): VS Code's Codex extension runs its own, and loadout set Codex up for it"`.
  - `:217-218` `RECOMMENDED_WHY` drops "for /hooks and plugins" and says "optional next to VS Code's Codex extension".
  - `--without-codex-cli` keeps working.
- Modify: `cli/loadout/bootstrap.py:1111-1125`. The `Next:` line in extension mode reads `"Next: open VS Code's Codex extension (reload the window if it is open) and approve loadout's hooks: the hooks icon in the prompt bar, then Allow all."` when hooks are untrusted; otherwise it keeps today's line.
- Test: `tests/test_check_codex_cli_row.py` (new); change `tests/test_bootstrap_codex_cli_offer.py`, `tests/test_vscode_pr2_review.py::test_check_has_no_failure_in_extension_mode`, `tests/test_check_vscode_surfaces.py` (gap rows), `tests/test_codex_extension_mode.py::test_check_warns_not_fails_for_a_missing_cli_next_to_the_extension`

**Interfaces:**
- Consumes: `mode()`, `cli_problem()`, `CLI_OPTIONAL`, `CLI_UNUSABLE` (Task 2), the hook texts (Task 4).

- [ ] **Step 1: Write the failing tests:**
  - `test_extension_only_check_has_one_ok_cli_row_and_no_cli_warnings`: `check.run_checks()` (or the function `check.py:754` builds the list with) gives exactly one row whose name contains "codex" (case-insensitive) and mentions the CLI: `Codex CLI`, ok, detail `CLI_OPTIONAL`. No row's detail or fix contains "--install", "/hooks", "loads none" or "do not load".
  - `test_a_broken_cli_next_to_the_extension_warns_once`: there is one `Codex CLI` warn row with "0.150.0" and "uses VS Code's Codex extension's codex instead", and the `Codex` row is ok.
  - `test_remote_wsl_window_with_codex_on_windows_keeps_its_gap` (Review Focus 5): it uses the `windows_only` setup from `tests/test_check_vscode_surfaces.py`, and the Remote-WSL gap text is still in the row.
  - `test_the_cli_offer_defaults_to_no`: `codex_cli_choice(install=True, ask=lambda q: "", interactive=True, wanted=True)` returns `(CODEX_CLI_DECLINED, True)`.
  - `test_bootstrap_next_line_names_the_hooks_icon`: an extension-only bootstrap with untrusted hooks prints the `Next:` line above.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the new file, the changed tests, then the whole suite. Expected: all pass. `grep -rn "CODEX_GAP\|for /hooks and plugins\|has no /hooks" cli tests` is empty.
- [ ] **Step 5: Commit** `fix(check): one optional Codex CLI row instead of four warnings, and bootstrap says the CLI is optional`.

---

### Task 6: ADR 0038 and the docs

**Files:**
- Create: `docs/adr/0038-codex-extension-loads-plugins-and-reviews-hooks.md` (Status: Accepted; supersedes ADR 0033's plugin and hooks parts). Its Decision covers spec decisions 1-8 and records the `[hooks.state]` evidence and the tour's version (26.1007, bundled 0.162.0-alpha).
- Modify: `docs/adr/0033-codex-for-the-vscode-extension-without-its-cli.md` (Status line: "Superseded in part by [0038](0038-…)"; the decision text stays), `docs/adr/README.md` (index), `AGENTS.md` (ADR range 0001-0038)
- Modify every page listed under the spec's "Docs", at the lines the code map found:
  - `docs/how-to/vscode.md:9,23,25,31,34-36,39,43`
  - `docs/how-to/setups.md:19,29`
  - `docs/how-to/codex.md:9,24`
  - `docs/how-to/troubleshooting.md:53,59,62,81,82,85,95`
  - `docs/reference/cli.md:301,311,318,319`
  - `docs/reference/hooks.md:63`
  - `docs/reference/state-and-sync.md:50,62`
  - `docs/reference/profile-format.md:88`
  - `docs/explanation/architecture.md:36,46`
  - `docs/explanation/security-and-trust.md:10,19`
  - `docs/explanation/the-toolset.md:18`
  - `docs/explanation/documentation-strategy.md:121`
  - `docs/reference/modules.md:82`
  - `docs/tutorials/getting-started.md:101`
  - `docs/how-to/install-with-an-agent.md:102`
  - `docs/how-to/wsl.md:30`
  - `plugins/loadout/skills/configure/SKILL.md:29`
- In `vscode.md` and the setups walkthrough, step 1 for the extension is VS Code's Restricted Mode: "Trust Folder & Continue" (finding 21). Then bootstrap, then the hooks icon and Allow all.
- `.serena/` in git (finding 27): read what Serena 2.1 writes into `.serena/.gitignore` (from its source or docs via Context7; never by running Serena on the real home). Then add one step to `plugins/loadout/skills/onboard/SKILL.md` and one paragraph to the Serena section of `docs/explanation/the-toolset.md`: commit `project.yml` and `memories/`, not what Serena's own `.gitignore` excludes. If Serena's `.gitignore` already excludes `cache/` and `project.local.yml`, `init` needs no change; otherwise add the missing line to `scaffold.GITIGNORE_LINES` with a test.
- Test: `tests/test_docs_vscode.py` follows the new wording (it asserts a phrase from `check.CODEX_GAP`, which is gone; assert instead that `vscode.md` names `codex.HOOKS_EXTENSION`'s "hooks icon" and "Allow all", and "Trust Folder & Continue"). `tests/test_docs_links.py` and `tests/test_docs_commands.py` pass.

- [ ] **Step 1:** Write the changed `test_docs_vscode.py` assertions and run them. Expected: FAIL.
- [ ] **Step 2:** Write the ADR and rewrite the pages. `grep -rn "loads none\|no /hooks\|has no \`/hooks\`\|plugins do not load\|loads no plugins" docs plugins README.md AGENTS.md` returns only ADR 0033's historical text.
- [ ] **Step 3:** Run the whole suite. Expected: all pass.
- [ ] **Step 4:** Run the `loadout:docs-sync` skill over the branch diff and fix what it finds.
- [ ] **Step 5: Commit** `docs: VS Code's Codex extension loads plugins and reviews hooks (ADR 0038)`.
