# 0012. Destructive actions: dry run, confirm, backup, restore

- Status: Accepted
- Date: 2026-10-08
- Source: [Design spec, decision D12 and section 6.2](../superpowers/specs/2026-10-08-agent-loadout-design.md#2-decisions)

## Context
The kit runs on machines that have a long-grown configuration, often not the author's. Removing or replacing something there must be safe, and the user must be able to undo it.

## Decision
Commands that remove or replace an item the user owns (adopt, own-tool choices, restore) show a plan or ask, and move it into a timestamped backup instead of deleting it. Routine merges of kit-managed state are backed up only by bootstrap and adopt. The backup holds a manifest with the original location and the undo step. `loadout restore <backup>` replays it in reverse.

## Alternatives considered
- Delete with a warning: cannot be undone.
- Plain file copies without a manifest: restoring a CLI change (an uninstalled plugin, a removed MCP server) would be manual.

## Consequences
- Nothing is lost by running `adopt`. The user can inspect the plan first (`adopt` without `--apply`).
- Backups pile up under `~/.claude/backups/` and are private; modes in [Undo what loadout changed](../how-to/undo-and-restore.md#backups).
- Some changes are not covered by a backup: bootstrap merges settings without a plan or prompt; `configure`, `apply-settings` and the daily maintenance rewrite `settings.json` and the snapshot without a backup; personal MCP servers are re-added or removed without one; `loadout profile` merges into a repo's files without one; and the settings snapshot is only included in newer backups. The full list is in [What restore does not undo](../how-to/undo-and-restore.md#what-restore-does-not-undo).

## In the code
- `cli/loadout/backup.py` (`Backup`: `move`, `save_copy`, `record_created`, `record_command`; `restore`, `list_backups`)
- `cli/loadout/adopt.py` (`render_plan`, `apply`, `run`)
- `cli/loadout/commands.py` (`restore` subcommand)
