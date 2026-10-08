---
name: configure
description: Conversationally adjust the user's loadout setup — preferences, global add-ons (plugins, MCP servers) and opt-outs of kit defaults — stored in their personal layer. Use when the user wants to add, remove or change tools or preferences globally.
---

# Configure loadout

The kit's defaults stay untouched; every choice goes into the user's personal layer through the `loadout configure` engine.

1. Run `loadout configure show` to see the current state: each add-on on/off, whether that is the kit default or a personal override, and the preferences.
2. Ask what the user wants in their own words ("I do a lot of frontend debugging", "I never use Rust", "I want database access everywhere"). Ask one question at a time.
3. Map the answers to concrete changes, using the reasons in `catalog.json` (in the kit repo, `loadout` resolves it). Prefer the kit's scoping: suggest a project profile (`loadout profile <name>`) when something is only needed in some repos, and global only when it is needed almost everywhere. Mention context cost for heavy add-ons (e.g. chrome-devtools, many-skill plugins).
4. Present the planned changes as a short list and get a yes.
5. Apply each with `loadout configure set plugin <id> on|off`, `loadout configure set mcp <catalog-id> on|off` or `loadout configure set pref <key> <json>`. Relay any notes, e.g. missing environment variables and where to put them.
6. Tell the user to restart Claude Code or run `/reload-plugins`. If their personal layer is a git repo, offer to commit and push it.

Never edit `~/.claude/settings.json` or `~/.claude.json` directly; the engine keeps kit-managed and personal values apart.
