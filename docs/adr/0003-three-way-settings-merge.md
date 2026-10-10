# 0003. settings.json is merged three-way; the kit manages only its keys

- Status: Accepted
- Date: 2026-10-08
- Source: [Design spec, decision D3 and section 6.3](../superpowers/specs/2026-10-08-agent-loadout-design.md#63-settings-merge)

## Context
`~/.claude/settings.json` already has content on most machines: the user's permissions, hooks and plugins. The kit needs to set some keys and change or drop them later, without losing the user's own edits.

## Decision
The kit merges instead of overwriting. It compares three states: the desired settings (kit base plus the personal overlay), the current file, and a snapshot of what it applied last time (`managed-settings.json`). It writes only the keys it manages. A value the kit dropped is removed only if the user did not change it. Lists are unioned and an item is removed only if the kit added it.

## Alternatives considered
- Symlink `settings.json` to the kit: overwrites everything the user has and breaks as soon as Claude Code writes to it.
- Plain deep merge without a snapshot: cannot tell whether the user or the kit changed a value, so a dropped kit value stays for ever or a user value is lost.

## Consequences
- Existing settings survive. A hook the user deletes does not come back (see [0017](0017-hooks-merge-per-hook-with-tombstones.md)).
- The snapshot is state that must be backed up before it is rewritten. Restoring an old backup can make the next merge drop a restored value.
- `loadout check` reports drift only on the paths the kit manages.

## In the code
- `cli/loadout/settings_merge.py` (`merge_settings`, `apply_settings`, `drift`, `backup_snapshot`)
- `cli/loadout/jsonio.py` (`deep_merge`)
- Details: [Settings merge](../reference/settings-merge.md)
