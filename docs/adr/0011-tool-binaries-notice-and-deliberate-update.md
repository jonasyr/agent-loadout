# 0011. Tool binaries: a weekly notice and a deliberate loadout update

- Status: Accepted
- Date: 2026-10-08
- Source: [Design spec, decision D11 and section 6.5](../superpowers/specs/2026-10-08-agent-loadout-design.md#65-updates)

## Context
The kit depends on binaries such as Serena, codebase-memory-mcp, rtk and playwright-cli. Their releases have broken things before. Updating them silently in the background could break a session without a trace.

## Decision
Maintenance checks the catalog versions at most once a week and writes a notice, shown at the next session start. Nothing is updated by itself. The user runs `loadout update`, which shows each command before it runs and, around it, watches `settings.json` for changes a tool's installer made.

## Alternatives considered
- Update automatically: convenient, but a bad upstream release lands on every machine at once.
- Never notify: users stay on old and possibly broken versions.

## Consequences
- The user decides when to take an update, at the price of one command.
- `curl | sh` installers run only with `--install` or after a confirmation that shows the exact command.
- A user who ignores the notice runs old binaries. Plugins are different: they update through the marketplace ([0002](0002-kit-is-a-plugin-marketplace.md)).

## In the code
- `cli/loadout/maintenance.py` (`_maintain`, `find_outdated`, `worth_notifying`, `update`, `WEEK`)
- `cli/loadout/versions.py`
- `catalog.json` (`version`, `install`, `update` per entry)
