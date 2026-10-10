# 0017. Hooks merge per hook (event, matcher, command) with tombstones

- Status: Accepted
- Date: 2026-10-10
- Source: [Adopt design, section 6](../superpowers/specs/2026-10-10-adopt-own-tools-design.md#6-known-limits-to-document-for-users) and the rulings from the fix passes 3 and 4 (summarised below)

## Context
A hook in `settings.json` sits in a group with a matcher. Recording a user's hook into the personal layer means the next merge must neither run it twice nor bring back one the user deleted. The first fixes merged whole groups. Each review then found a new duplicate or lost-hook case, and a user edit or a deletion could be undone by the next merge.

## Decision
Hooks merge three-way per hook, not per group. A hook is identified by event, matcher (missing counts as empty) and command, and an exec-form hook also by its `args`. The merge uses the current file, the desired settings and the snapshot of what was applied. If the user deletes an applied hook, the merge records a tombstone (`loadoutDeletedHooks`) and never adds it again until the kit or personal layer drops it. A user edit equal to the desired hook counts as in sync.

## Alternatives considered
- Merge at group level with dedupe by equality: kept producing new duplicate cases; each of three reviews found another.
- Keep hooks out of the personal layer: hooks are the most common own tool, so users would lose the feature.
- Drop global hooks if the merge did not converge (the fallback named in the ruling): not needed, because a randomised test over thousands of operation sequences now passes.

## Consequences
- The class of duplicate and resurrected hooks is removed, and a property test guards it: seeded random sequences of adopt, edit, delete and merge, checking the invariants.
- Edge cases remain: a user edit to an applied hook survives until the personal layer changes it, existing duplicates are not cleaned up, and two exec-form hooks with the same command share one keep or leave decision.
- The snapshot grows a second key, so it must be backed up before changes ([0003](0003-three-way-settings-merge.md)).

## In the code
- `cli/loadout/settings_merge.py` (`hook_id`, `_merge_hooks`, `merge_settings`, `record_applied_hook`, `TOMBSTONES`)
- `cli/loadout/own.py` (`_hook_group`, `_replace_hook`, `_find_hook`)
- `tests/test_hook_merge_properties.py`
- Reference: [Settings merge](../reference/settings-merge.md)
