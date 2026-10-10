# 0001. Kit repo plus a personal repo per user

- Status: Accepted
- Date: 2026-10-08
- Source: [Design spec, decision D1](../superpowers/specs/2026-10-08-agent-loadout-design.md#2-decisions)

## Context
The setup should work for the author and for other people. Shared parts (rules, catalog, hooks, skills) change often, and every user needs them. Personal parts (preferences, extra plugins, own MCP servers) must stay private and must not end up in a shared repo.

## Decision
The repo `jonasyr/agent-loadout` is a generic kit that anyone can install. Each user keeps their own settings in a separate personal layer, ideally a private git repo (for the author `jonasyr/loadout-personal`). The kit never contains personal data.

## Alternatives considered
- One repo per user, forked from the kit: every kit improvement needs a manual merge upstream.
- One shared repo with a personal folder: personal data would sit next to shared code and could be pushed by accident.

## Consequences
- Kit improvements reach everyone through updates, and nobody merges upstream.
- Personal data stays private. A user without git can still use a plain folder as the personal layer.
- There are two places to look when something is wrong, and two repos to keep in sync (see [the personal layer](../reference/personal-layer.md)).

## In the code
- `cli/loadout/paths.py` (`kit_root`, `personal_root`)
- `cli/loadout/link.py` (`LINKS`): kit rules and personal rules are linked separately
- `cli/loadout/maintenance.py` (`_maintain`): pulls both repos
