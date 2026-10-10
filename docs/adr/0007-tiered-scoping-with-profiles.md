# 0007. Tiered scoping: core tools global, domain tools per project

- Status: Accepted
- Date: 2026-10-08
- Source: [Design spec, decision D7 and section 4.2](../superpowers/specs/2026-10-08-agent-loadout-design.md#2-decisions)

## Context
Every globally enabled skill puts its description into the context of every session. A tool for databases or academic writing costs tokens in repos that never use it.

## Decision
Only core tools are enabled globally. Domain tools belong to profiles (`thesis`, `sonar`, `db`, `web`, `android`) that `loadout profile <name>` applies to one repo: plugins are installed with `--scope project`, and settings and MCP servers are merged into the repo's `.claude/settings.json` and `.mcp.json`. Catalog entries with status `profile` are proposed for scoping down by `adopt`.

## Alternatives considered
- Enable everything globally: simple, but costs context everywhere.
- Let users enable per project by hand: works, but nobody remembers the exact plugin and server names.

## Consequences
- Lower idle overhead in sessions. A repo carries its own tool list, so a clone on another machine gets the same tools.
- A profile is copied when applied. Later edits to a profile do not reach repos until it is applied again.
- The user has to know a profile exists. `loadout init` and `/loadout:onboard` suggest them.

## In the code
- `profiles/*.json` (`thesis`, `sonar`, `db`, `web`, `android`)
- `cli/loadout/profiles.py` (`load_profile`, `apply_profile`, `copy_skills`)
- `cli/loadout/inventory.py` (`classify`: action `scope-down`)
- Format: [Profile format](../reference/profile-format.md)
