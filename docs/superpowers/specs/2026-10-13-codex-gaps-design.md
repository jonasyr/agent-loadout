# Hardening 4b: close the Codex code gaps

Status: approved design, 2026-10-13. Second of three hardening 4 PRs (4a state location #33, 4b Codex gaps, 4c own-tool scopes). Developed in the worktree `.claude/worktrees/codex-gaps` (branch `feat/codex-gaps`): the real launcher runs the main checkout.

## Goal

Six behaviours that the docs currently describe as "Claude Code only" or "a limit for Codex" work for Codex too. Each change gets a test that fails first; the docs lose the corresponding limit sentences.

## Constraints

- AGENTS.md "Code Review Rules": loadout changes only what it recorded as its own in `~/.codex/config.toml` and `~/.codex/AGENTS.md`; every destructive change is undoable; a turned-off agent's files are untouched; no secret value is printed or written; external commands only through `runner.run`; tests use `fake_home`/`fake_runner`.
- Standard library only; Python 3.11+.

## Design

### 1. Turning a plugin off reaches Codex (`cli/loadout/codex.py`)

A plugin that loadout manages and that is switched off for Claude Code (`"enabledPlugins": {"ID": false}` in the desired settings: kit `settings.base.json` merged with the personal `settings.json`, the same source `plugin_routes` reads) and that is installed in Codex gets `[plugins."ID"] enabled = false` in `~/.codex/config.toml`.

- `desired_keys()` adds `(("plugins", pid), "enabled", False, False)` for each such `pid` that `installed_plugins()` lists. When the list fails (`None`), no such keys are added this run (nothing is turned off on a guess).
- The key is an owned key like `model_reasoning_effort`: recorded in `codex-config.json`, backed up on first change, left alone once you edit it. Switching the plugin back on keeps the owned line and sets it to `enabled = true` (`desired_keys()` adds `(…, True, False)` for a plugin that is on and whose `enabled` key loadout owns); `apply_config` never removes owned keys, and `true` is Codex's normal state.
- A plugin you installed in Codex yourself and that is not in the desired settings is untouched. Project-only plugins (`project_plugins()`) keep their existing forced keys.
- Not uninstalled (`codex plugin remove`): switching off is undoable without a reinstall and matches project scoping.

### 2. `autoUpdate: false` also holds for Codex (`cli/loadout/codex.py`)

The automatic refresh after a pull (`apply_all(refresh=True)`, called by the daily sync) skips `codex plugin marketplace upgrade` and the re-`add` of installed plugins for a marketplace whose `extraKnownMarketplaces` entry has `autoUpdate: false`. `claude-plugins-official` counts as auto-updating unless it is set to `false` the same way.

- `_install_routes` and `apply_plugins` get a parameter `auto: bool` (default `False`); `apply_all` passes `auto=refresh`. `loadout update` calls `apply_plugins(refresh=True)` without `auto`, so an explicit update still updates every marketplace, as in Claude Code.
- A first install (plugin not yet in Codex) is never skipped.

### 3. Hand edits reach Codex at the next session (`cli/loadout/codex.py`, `cli/loadout/maintenance.py`)

`codex.refresh_instructions() -> str | None` rewrites loadout's marked block in `~/.codex/AGENTS.md` when Codex is on (`targets.codex_enabled()`), the file already holds a balanced block, and the block differs from `render_instructions()`. It never creates the file or a block (that stays bootstrap's and `configure`'s job), needs no `codex` binary and no network, and writes atomically. Returns a notice line when it rewrote, else `None`.

`maintenance.session_start` calls it (errors never break the session; a rewrite is not announced). The `loadout check` row "Codex instructions" stays the safety net.

### 4. The execution advisor sees Codex edits (`plugins/loadout/hooks/advisor.py`)

`record` collects candidate paths from `tool_input.file_path` (Claude Code) and, when `tool_input.command` is a string, from its `*** Add File: <path>` and `*** Update File: <path>` lines (Codex `apply_patch`), the same rule `hooks/typecheck.py` `changed_files` uses (the hook cannot import it; a test pins that both read the same headers). Relative paths resolve against `payload["cwd"]` when present. Each path then goes through the existing `is_plan_path` / `looks_like_plan` checks.

### 5. The plaintext-secret scan covers Codex (`cli/loadout/secrets.py`, `cli/loadout/adopt.py`)

`secrets.scan_codex() -> list[Finding]` reads the `[mcp_servers.*]` tables of `~/.codex/config.toml` (through `codex.user_servers()`, which leaves out loadout's own tables; a file that does not parse gives no findings), maps each server's `env`, `args`, `url` and `http_headers` to the shape `secrets.scan` reads, and returns its findings with `location="~/.codex/config.toml"` and `fixable=False` (report only: loadout does not own those sections; the fix is "move it to `secrets.env` and name it in `env_vars`").

`adopt` scans Claude Code's files when Claude Code is on and Codex's when Codex is on (so Codex-only users are covered). Reported values stay hidden, as today.

### 6. WSL checks `codex` too (`cli/loadout/wsl.py`)

The tools whose resolution under `/mnt/c` is checked are `LINUX_TOOLS` plus `codex` when Codex is on (`targets.codex_enabled()`).

### 7. Docs

Remove or rewrite the "limit" sentences added in hardening 3 for these six points: `docs/how-to/codex.md`, `docs/reference/personal-layer.md`, `docs/reference/included-tools.md`, `docs/explanation/security-and-trust.md`, `docs/how-to/troubleshooting.md`, `docs/how-to/wsl.md`, `docs/explanation/execution-advisor.md`, `docs/reference/hooks.md`, `docs/how-to/set-preferences.md`, `docs/how-to/your-own-tools.md`. ADR 0024 gets one consequence line each for points 1 and 2. The backlog entries for these six points are removed.

## Testing

One test per point that fails before the change:

1. Plugin off: desired settings with `"x@m": false`, `codex plugin list` listing `x@m` → `config.toml` gets `enabled = false` as an owned key; back on → the owned line reads `enabled = true`; your own edit of the line → left as is; list failure → no key; a plugin only you installed → untouched.
2. autoUpdate: refresh with a marketplace `autoUpdate: false` → no `marketplace upgrade`, no re-add for it; `loadout update` path (`auto=False`) → upgraded; a missing plugin of that marketplace is still installed.
3. Block refresh: a changed rule file → `session_start` rewrites the block, user text byte for byte unchanged; Codex off, no block, unbalanced markers → no write.
4. Advisor: an `apply_patch` payload adding `docs/superpowers/plans/x.md` with plan content → recorded; a relative path with `cwd`; headers identical to typecheck's.
5. Secrets: a `config.toml` server with a plaintext token in `env` → one finding, value never printed; Codex-only adopt reports it; a non-parsing file → no crash.
6. WSL: Codex on and `codex` resolving under `/mnt/c` → warning; Codex off → not checked.

## Out of scope

- Fixing plaintext secrets in `config.toml` automatically (needs a byte-for-byte TOML edit of sections loadout does not own).
- 4c (own-tool scopes).
