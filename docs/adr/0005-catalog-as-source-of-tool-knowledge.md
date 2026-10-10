# 0005. catalog.json is the source of tool knowledge

- Status: Accepted
- Date: 2026-10-08
- Source: [Design spec, decision D5 and section 5](../superpowers/specs/2026-10-08-agent-loadout-design.md#5-catalog-catalogjson)

## Context
`adopt`, `check`, `update` and the installer all need to know what a tool is, whether it is core, optional, superseded or deprecated, why, and how to install or update it. Without one place, each command would carry its own list.

## Decision
The kit has one file, `catalog.json`. Each entry has an id, a kind, a status (core, profile, superseded, deprecated, recommended, alternative, system), a match rule, a reason, and optional version, install and update commands per platform. Items that match no entry count as the user's own.

## Alternatives considered
- Hard-code the lists in each command: they drift apart, and the research behind a verdict is lost.
- Fetch the knowledge from a server: needs a network and a service to run, and breaks offline.

## Consequences
- One file to edit to change what the kit recommends. The `reason` field keeps the research behind each verdict.
- The format is plain JSON, so the catalog can be validated by tests.
- Entries need maintenance: versions and commands go stale.

## In the code
- `catalog.json`
- `cli/loadout/catalog.py` (`load`, `match`, `by_id`, `binaries`, `platform_cmds`)
- `cli/loadout/inventory.py` (`classify`)
- Format: [Catalog format](../reference/catalog-format.md)
