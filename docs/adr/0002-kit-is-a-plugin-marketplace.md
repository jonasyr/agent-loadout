# 0002. The kit is a plugin marketplace

- Status: Accepted
- Date: 2026-10-08
- Source: [Design spec, decision D2](../superpowers/specs/2026-10-08-agent-loadout-design.md#2-decisions)

## Context
The kit has to deliver hooks, MCP server configuration and skills to every machine, on Linux, macOS and Windows, and keep them current. Claude Code already has a mechanism for that.

## Decision
The kit repo is also a Claude Code plugin marketplace named `agent-loadout`. It lists one plugin, `loadout`, which carries the hooks, the MCP config (Serena, codebase-memory-mcp) and the skills. The plugin has no `version` field, so every commit counts as an update.

## Alternatives considered
- Copy hooks and skills into `~/.claude` with our own installer: we would have to build update and cross-platform delivery ourselves.
- Ship only a CLI and no plugin: skills and hooks would not be discoverable the normal way and would not auto-update.

## Consequences
- Claude Code installs, enables and updates the plugin through marketplace auto-update. No custom delivery code.
- The plugin is the only thing that needs the marketplace layout. Rules, settings and the CLI come through git and `loadout`.
- Changes reach users on every commit to the kit, so a broken commit reaches them too. CI validates the plugin.

## In the code
- `.claude-plugin/marketplace.json` (plugin `loadout`)
- `plugins/loadout/hooks/hooks.json`, `plugins/loadout/.mcp.json`, `plugins/loadout/skills/`
- `settings.base.json` (`extraKnownMarketplaces`, `enabledPlugins`: `loadout@agent-loadout`)
