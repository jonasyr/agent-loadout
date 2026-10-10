# 0015. Claude Code, not loadout, installs plugins synced through the personal layer

- Status: Accepted
- Date: 2026-10-10
- Source: [Adopt design, gap G1](../superpowers/specs/2026-10-10-adopt-own-tools-design.md#1-problem)

## Context
A plugin recorded in the personal layer on one machine has to reach the others. It looked like a gap: `bootstrap.setup_plugins` runs only from `bootstrap` and `configure`, not after the daily pull. The Claude Code documentation says that for user settings, a marketplace that settings declare but `known_marketplaces.json` lacks is cloned, and enabled plugins that are not cached yet are downloaded, when plugins are loaded.

## Decision
No code change. After the daily pull merges the personal layer into `~/.claude/settings.json`, Claude Code installs new plugins at its next start, in the background. They are active after `/reload-plugins` or a new session. loadout documents this and does not add an install step to maintenance.

## Alternatives considered
- Run `setup_plugins` after every pull: duplicates what Claude Code already does, and runs `claude` commands from a background process.
- Make users run `loadout bootstrap` on each machine after a change: easy to forget.

## Consequences
- Less code and no background `claude` mutations.
- The new plugin is not usable in the first session after the pull. `LOADOUT_NO_AUTO_PULL=1` stops the pull, and with it this path.
- The behaviour is Claude Code's, so a change there changes ours. The statement is listed as a known limit.

## In the code
- `cli/loadout/maintenance.py` (`_maintain`: pull, then `apply_settings`, `apply_mcp`, `link_all`; no plugin step)
- `cli/loadout/bootstrap.py` (`setup_plugins`, called only from `bootstrap`)
- `cli/loadout/own.py` (`record_global`: writes `enabledPlugins` and `extraKnownMarketplaces` to the personal `settings.json`)
