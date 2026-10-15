# 0028. Serena's Codex hooks as owned entries in hooks.json

- Status: Accepted
- Date: 2026-10-15
- Source: [Design: Codex anywhere](../superpowers/specs/2026-10-15-codex-anywhere-design.md), section "PR A"

## Context

Serena documents its Codex setup ([Serena: clients](https://oraios.github.io/serena/02-usage/030_clients.html), `serena setup codex`): a `[mcp_servers.serena]` table in `~/.codex/config.toml` and six `serena-hooks … --client=codex` entries in `~/.codex/hooks.json`. loadout's plugin carried three Serena hooks of its own (`activate`, `cleanup` and an `auto-approve` that Serena does not document for Codex) and declared a `serena` server in the plugin's `.mcp.json`. Codex combines hooks from every layer and starts an active plugin's MCP servers by their bare name, so a user who had followed Serena's docs got `activate` and `cleanup` twice, and a user whose Serena server had another name got a second Serena in the wrong context (`claude-code`). A plugin's hooks are fixed: they cannot step aside when the user has the same ones.

## Decision

- loadout writes Serena's server exactly as Serena documents it, and none when the user's `config.toml` already has a table that starts Serena's MCP server, whatever its name.
- Serena's six hooks are loadout-owned entries in `~/.codex/hooks.json`, with the `config.toml` contract: loadout records each entry it wrote by its exact text, adds only the ones that are missing (an entry counts as present when any hook of that event runs `serena-hooks <same subcommand> --client=codex`; `cleanup` under `SessionEnd` or `Stop`), never touches the user's entries, saves a copy before its first change, and removes only its own entries when `serena-hooks` and `serena` are gone.
- It rewrites `hooks.json` only when the file is already in its own format (two-space JSON, LF line endings); any other file is left byte for byte and loadout names the entries to add by hand.
- The plugin no longer runs Serena in Codex: its `codex.json` has no `serena-hooks`, and its Codex manifest points at `.codex-mcp.json`, which has codebase-memory only. Claude Code is unchanged.

## Alternatives considered

- Keep the hooks in the plugin: they would run twice for every user who followed Serena's docs, with no way to step aside.
- Write the hooks inline as `[hooks]` in `config.toml`: Codex warns when one layer has both forms, and a user who ran `serena setup codex` has `hooks.json`.
- Rewrite any `hooks.json`: reformatting changes the user's bytes (indentation, CRLF).

## Consequences

- Codex runs the entries only after the user reviews them in `/hooks`; `loadout check` counts them as part of "Codex hooks" (their keys are `<absolute path of hooks.json>:<event>:<group>:<hook>`).
- Codex loses the auto-approve for Serena's tools; Codex asks before a Serena tool call as for any MCP tool.
- Only the first change to `hooks.json` has a backup copy, as for `config.toml`.

## In the code

- `cli/loadout/codex_hooks.py` (the entries, presence, ownership, trust keys)
- `cli/loadout/codex.py` (`SERENA`, `is_serena`, `user_serena`, `apply_all`, `checks`, `hooks_status`)
- `plugins/loadout/hooks/codex.json`, `plugins/loadout/.codex-mcp.json`, `plugins/loadout/.codex-plugin/plugin.json`
