# Undo what loadout changed

Use this page when something went wrong after `bootstrap`, `adopt` or `configure`, or when you want a removed tool back.

## Backups

Before loadout removes or replaces anything, it moves the old item into a backup folder `~/.claude/backups/loadout-<timestamp>` and records how to undo each step in `manifest.json`. These commands make backups: `bootstrap`, `adopt`, `configure`, `update` (when it undoes an installer's changes) and the daily maintenance (when it refreshes copied links). The command prints the path at the end:

```
backup: ~/.claude/backups/loadout-20261010-093000  (undo: loadout restore ~/.claude/backups/loadout-20261010-093000)
```

Backups can hold old configs and undo commands with secrets in them. They are readable only by you (0700/0600). Delete old ones when you no longer need them.

## List and restore

```bash
loadout restore --list
loadout restore ~/.claude/backups/loadout-<timestamp>
```

`--list` shows backups newest first, with the number of steps and whether each was restored. `loadout restore` without a folder lists them too. Flags and exit codes: [CLI reference](../reference/cli.md#loadout-restore).

Restore replays the steps in reverse:

- A moved item is moved back. If something else now sits at that place, it goes into the new pre-restore backup first when it is a link or when loadout itself had replaced the original. In any other case the step is skipped with `skipped (exists)` and the backup is not marked as restored.
- A saved file (such as `settings.json` before a merge) is copied back unless it is identical.
- A file loadout created (a new `me.md`, `settings.json`, `secrets.env` or shell startup file) is moved aside, not deleted.
- A recorded command runs through `claude` again: reinstall a plugin, re-add a marketplace or an MCP server. Plugins were uninstalled with `--keep-data`, so their data is still there. On a Windows `claude.cmd` shim, which cannot take JSON, the command is written to a private `manual-commands.txt` for you to run by hand.

Whatever restore replaces goes into a new `pre-restore` backup, so a restore can be undone too. A step that failed is reported, and a backup with a failed step is not marked as restored: fix the cause and run the same restore again. A backup that was already restored is refused unless you pass `--force`.

## What restore does not undo

- Links that bootstrap created where nothing was before: `~/.claude/rules/loadout`, `~/.claude/rules/personal`, `~/.local/bin/loadout`. Remove them as in [Uninstall](uninstall.md).
- The "# loadout secrets" line that bootstrap appended to an existing shell startup file on Linux and macOS. A startup file that bootstrap created, and a Windows PowerShell profile (a copy is saved first), are covered.
- Plugins and marketplaces that bootstrap installed. Uninstall them with `claude plugin uninstall ID`.
- A profile applied to a repo with `loadout profile` or `loadout init`. It writes the repo's committed `.claude/settings.json` and `.mcp.json`; use git there.
- The routine settings merge. `loadout configure`, `apply-settings` and the daily maintenance write `~/.claude/settings.json` without a backup. They change only the keys and hooks the kit manages (see [Settings merge](../reference/settings-merge.md)); bootstrap and adopt do save `settings.json` before their merge.
- The git credential helper that bootstrap sets with `gh auth setup-git` when `gh` is logged in. Bootstrap prints the undo command: `git config --global --unset-all credential.https://github.com.helper`.
- Edits made by `loadout configure`, `apply-settings` and the daily maintenance to the managed-settings snapshot `~/.claude/.loadout/managed-settings.json`. They rewrite it without a backup. See [Limits](../reference/settings-merge.md#limits).

## The managed-settings snapshot

Bootstrap and adopt save the snapshot in the backup, so restoring `settings.json` and the snapshot together keeps them consistent. Backups made before the snapshot was part of them do not hold it. Restoring one after a global hook or plugin choice can let the next settings merge drop the restored value again. Check `~/.claude/settings.json` afterwards. Why the snapshot exists: [settings merge](../reference/settings-merge.md#the-snapshot).

## Common cases

| I want to | Do |
|---|---|
| Undo the last adopt | `loadout restore <path adopt printed>` |
| Bring back one tool I removed | Restore replays a whole backup; it cannot pick single items. Reinstall one tool with its own command if you do not want the rest back |
| Undo a restore | `loadout restore <pre-restore backup path>` (it is printed, and listed by `--list`) |
| See what a backup holds | Open `~/.claude/backups/loadout-<timestamp>/manifest.json`. Do not share it: it can contain secrets |
