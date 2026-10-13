# Hardening 2: robustness and correctness — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unexpected file contents never crash a command. Nothing reads or names a turned-off agent. Plugin updates reach both agents. Secrets in `adopt` get their own consent.

**Architecture:** One shared accessor (`jsonio.get_dict` / `get_list`) is used at every read of a known container key, plus normalisation at the few central entry points (`desired_settings`, `load_profile`, `codex._json`, `list_backups`, the settings merge). The target gating follows the pattern `maintenance` already uses (`targets.claude_enabled()`). Plugin refresh is one new function per agent, called by `update` and by the daily sync after a pull.

**Tech Stack:** Python 3.11+ standard library, pytest with `fake_home` / `fake_runner` (autouse `never_the_real_home`).

**Spec:** the design approved in conversation on 2026-10-13. Findings are in `.superpowers/handoff/2026-10-13-hardening-backlog.md`, sections "Shape-crash audit", "Target gating leftovers", "Undo notes" and "loadout update and plugins", plus the adopt secrets line.

## Global Constraints

- Standard library only in `cli/loadout/`; Python 3.11+.
- Tests never touch the real `~/.claude`, `~/.claude.json`, `~/.codex` or `~/.config/loadout`; never run real `claude`, `codex` or installers.
- Conventional Commits; no AI attribution.
- A wrongly shaped value is treated as missing, and a line names the file when the user must fix it. Never a traceback.
- Run tests with: `uv run --python 3.12 --with pytest pytest -q`.

## Review Focus

1. A kit update that turns a settings key from an object into a scalar (or back) applies cleanly for a user whose `settings.json` and snapshot still hold the old shape (Task 2).
2. The session hook and the daily sync never crash or loop on a wrongly shaped file: they notify once and keep going (Tasks 1-2).
3. With Claude Code off, `configure`, `check`, `adopt` and the restart hints neither read nor name Claude Code (Task 3).
4. Kit plugins update without the user doing anything (Claude Code's own `autoUpdate` for the kit's marketplaces; the daily sync's existing Codex refresh), and `loadout update` updates both agents at once, only those that are on (Task 4).
5. `adopt --apply --groups update --yes` never moves secrets; `--groups secrets` (with `--yes`, or confirmed interactively) does; `adopt --yes` without groups behaves as before (Task 5).

---

### Task 1: The shape-safe accessor and the central entry points

**Files:** `cli/loadout/jsonio.py` (new `get_dict`, `get_list`), `cli/loadout/settings_merge.py` (`desired_settings` normalises `enabledPlugins`, `extraKnownMarketplaces` and each marketplace's `source` to dicts), `cli/loadout/profiles.py` (`load_profile` validates field types), `cli/loadout/own.py` (`personal_index` skips a broken profile), `cli/loadout/codex.py` (`_json` never raises; the list and `mcp list` parsers check element types; `record_path` contents `tables`/`keys` are dicts), `cli/loadout/backup.py` (`list_backups` and `restore` check `steps`, `created_at` and label types), `cli/loadout/personal_mcp.py`, `cli/loadout/check.py`, `cli/loadout/configure.py`, `cli/loadout/bootstrap.py`, `cli/loadout/codex_project.py`, `cli/loadout/project.py` (switch the reads the backlog lists to the accessor). Tests: `tests/test_shapes.py`.

- [ ] Step 1: Failing tests. Write one parametrised test per entry point that feeds the backlog's crash shapes and asserts no exception plus the documented result. The shapes:
  - `null`, `5`, `"x"` and `[...]` for each container key in personal `settings.json` (`enabledPlugins`, `extraKnownMarketplaces`, a marketplace's `source`, a hook group's `hooks`);
  - personal `mcp.json`, `~/.claude.json` and `managed-mcp.json` with `mcpServers: null` or `5`;
  - `codex-config.json` with `tables: null` or `["x"]`;
  - `installed_plugins.json` with `plugins: null`;
  - a profile with `install: null`, `["ok@m", 5]`, `commands: null`, `[["ok"], "x"]`, `skills: null` or `settings: null`;
  - a backup manifest with `steps: null`, `created_at: "x"` or a step whose label is `5`;
  - `codex plugin list --json` output with a leading `WARN [x]` line, `{"installed": null}`, `["a@b"]`, or an entry without `pluginId`;
  - `codex mcp list --json` with an entry without `name`, or with a list as `name`.

  The entry points to drive:
  - `check.run_all` (or whatever `loadout check` calls), `configure.show`/`addons`, `own.personal_index`, `inventory.classify(inventory.collect(False))`;
  - `personal_mcp.apply_mcp` with `fake_runner`, `codex.apply_all` with `fake_runner` and `codex.drift`;
  - `profiles.load_profile` (raises a ValueError naming the file, which `main` prints as one line);
  - `backup.list_backups` and `backup.restore`.

  Write each test so it names the reader it covers.
- [ ] Step 2: Run, expect several FAILs (TypeError/AttributeError/KeyError).
- [ ] Step 3: Implement:

```python
# jsonio.py
def get_dict(data, key) -> dict:
    """data[key] when it is a dict, else {} (a null, list or scalar written by hand or by another tool)."""
    value = data.get(key) if isinstance(data, dict) else None
    return value if isinstance(value, dict) else {}


def get_list(data, key) -> list:
    value = data.get(key) if isinstance(data, dict) else None
    return value if isinstance(value, list) else []
```

  Replace each `load_json(x).get(KEY, {})` / `.get(KEY) or {}` read of a container key with `get_dict`, and each list read with `get_list`, filtering elements by type where they are used (`isinstance(pid, str)`). `desired_settings` returns the merge with the known container keys normalised. `load_profile` raises `ValueError(f"profile {path}: {field} must be a {kind}")` for wrong field types. `own.personal_index` catches that ValueError and skips the file. `codex._json` tries each line that starts with `{` or `[` and returns `None` on `ValueError`. `list_backups` skips a manifest whose `steps` is not a list. `restore` reports "failed: the backup's manifest is damaged" for it, and `str()`s labels before printing.
- [ ] Step 4: Full suite green; commit `fix: wrongly shaped files never crash a command`.

### Task 2: The settings merge survives a key that changes shape

**Files:** `cli/loadout/settings_merge.py` (`_delete_path`, `_plan`), tests `tests/test_settings_shape_change.py`.

- [ ] Step 1: Failing tests. Drive `settings_merge.apply_settings()` in `fake_home` with: the snapshot and current settings holding `"env": {"A": "1"}` while the desired settings have `"env": "x"`; the reverse (scalar to object); and `"permissions": [...]` replacing an object. Assert no exception, the desired value wins, and the user's own unrelated keys stay.
- [ ] Step 2: Run, expect TypeError.
- [ ] Step 3: Implement. `_delete_path` returns quietly when a node on the path is not a dict. `_plan` prunes only when `get_path(result, path[:-1])` is a dict, and `_set_path` replaces a non-dict node on the way with `{}` only for keys the kit owns (the merge already decides ownership; keep that rule).
- [ ] Step 4: Full suite green; commit `fix(settings): the merge survives a setting that changes shape`.

### Task 3: Nothing reads or names a turned-off agent

**Files:** `cli/loadout/preferences.py` (`_blockers`, `detect`, the auto-mode draft: skip `~/.claude/settings.json` when Claude Code is off), `cli/loadout/adopt.py` (`RESTART_NOTE` built from the targets), `cli/loadout/configure.py` (the same hint), `cli/loadout/bootstrap.py` (`INTRO` names both agents), `cli/loadout/own.py` (the "next Claude Code start" line names the agents that are on), `cli/loadout/check.py` (`_own` filtered to Codex items when Claude Code is off; `_mcp_path` whenever either agent is on). Tests: `tests/test_target_wording.py`.

- [ ] Step 1: Failing tests, with `targets.claude_enabled` patched to False and `codex_enabled` to True:
  - `configure set pref-choice ai_attribution on` with `includeCoAuthoredBy: false` in `~/.claude/settings.json` does not report "not effective";
  - `adopt.restart_note()` and the configure hint do not contain "Claude Code";
  - `check` lists an own Codex skill and runs the MCP PATH check.

  With Claude Code on, the old texts stay.
- [ ] Step 2: Run, expect FAIL.
- [ ] Step 3: Implement. One helper, `targets.restart_hint()`, returns e.g. "Restart Claude Code (or run /reload-plugins) and Codex to load the changes", naming only the agents that are on. Use it everywhere the old `RESTART_NOTE` text was printed. Keep `RESTART_NOTE` as a name if tests import it, set to the Claude-only text.
- [ ] Step 4: Full suite green; commit `fix: with an agent off, loadout neither reads nor names it`.

### Task 4: Plugin updates reach both agents

Facts (official Claude Code docs, checked 2026-10-13): `claude plugin update <name@marketplace> [-s user|project|local|managed]` updates a plugin to the newest version its marketplace offers, from the cached catalog, so run `claude plugin marketplace update <name>` first. Claude Code updates plugins by itself when a marketplace has `"autoUpdate": true` in its `extraKnownMarketplaces` entry. That is on by default only for Anthropic's marketplaces, and it applies in a running session after a random delay, then needs `/reload-plugins`. Ruling: the daily sync does not run `claude plugin update` itself; the kit turns on `autoUpdate` for its own marketplaces instead (the built-in feature, no new automatic command). `loadout update` updates explicitly for an immediate effect.

**Files:** `settings.base.json` (`"autoUpdate": true` on the kit's `extraKnownMarketplaces` entries: `agent-loadout`, `impeccable`, `academic-research-skills`, `life-sciences`), `cli/loadout/maintenance.py` (`_update`), `cli/loadout/codex.py` (reuse `apply_plugins(refresh=True)`). Tests: `tests/test_plugin_refresh.py`. Docs: `docs/reference/cli.md` (update), `docs/explanation/architecture.md` (daily sync / plugin updates), `docs/reference/settings-merge.md` if it lists the base keys.

- [ ] Step 1: Failing tests:
  - Every `extraKnownMarketplaces` entry in `settings.base.json` has `autoUpdate: true`, and the settings merge carries it into `desired_settings()`.
  - `_update` with Claude Code on runs `claude plugin marketplace update`, then `claude plugin update <id> --scope user` for each plugin enabled in `desired_settings()` that `~/.claude/plugins/installed_plugins.json` lists with user scope (read with the Task 1 accessor).
  - With Codex on, `_update` calls `codex.apply_plugins(<backup>, refresh=True)` and prints its lines.
  - With Claude Code off, no `claude` call happens.
  - A failing `claude plugin update` produces one `failed:` line, and the next plugin still runs.
  - A test checks the summary line tells the user to run `/reload-plugins` (or restart) when a plugin changed.
- [ ] Step 2: Run, expect FAIL.
- [ ] Step 3: Implement. Print one calm line per plugin whose output does not say "already at the latest version".
- [ ] Step 4: Full suite green; commit `feat: loadout update refreshes loadout's plugins in both agents; kit marketplaces auto-update`, and docs as `docs: plugin updates`.

### Task 5: Secrets in adopt need their own consent; small fixes

**Files:** `cli/loadout/adopt.py` (`select` accepts a `secrets` group; `run` moves secrets only when `groups is None` or `"secrets" in groups`), `cli/loadout/commands.py` (`--groups` help lists `secrets`), `plugins/loadout/skills/configure/SKILL.md` (drop the workaround, use `--groups ...,secrets`), `tests/test_configure_assistant.py` (update), `cli/loadout/maintenance.py` and `cli/loadout/codex_project.py` (print the Codex backup folder when one was made), the test that leaks a fake `~/.local/bin` into `os.environ["PATH"]` (find it: grep for `os.environ["PATH"]` / `prepend_tool_dirs` in tests and wrap with `monkeypatch`). Docs: `docs/reference/cli.md` (adopt groups), `docs/how-to/your-own-tools.md` if it mentions secrets.

- [ ] Step 1: Failing tests:
  - `adopt.run(apply_changes=True, groups={"update"}, yes=True, ...)` with a fixable secret finding does not call `fix_secrets`.
  - `groups={"secrets"}`, `yes=True` does call it.
  - `groups=None`, `yes=True` does as before.
  - `select` rejects no `secrets` group and returns no verdicts for it.
  - The configure skill text contains `--groups` with `secrets` and no longer contains "also moves the plaintext secrets".
  - A daily-sync Codex refresh that wrote a backup notifies with its folder.
  - The PATH-leak test leaves `os.environ["PATH"]` unchanged (assert in a fixture teardown or a direct check).
- [ ] Step 2: Run, expect FAIL.
- [ ] Step 3: Implement as listed.
- [ ] Step 4: Full suite green; commit `fix(adopt): moving secrets needs its own consent (--groups secrets)` plus `fix: name the Codex backup folder; test PATH isolation`.
