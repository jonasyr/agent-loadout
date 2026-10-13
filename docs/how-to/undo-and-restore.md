# Undo what loadout changed

Use this page when something went wrong after `bootstrap`, `adopt` or `configure`, or when you want a removed tool back.

## Backups

Before loadout removes or replaces a tool, file or link you own, it moves the old item into a backup folder `~/.claude/backups/loadout-<timestamp>` and records how to undo each step in `manifest.json`. These commands make backups: `bootstrap`, `adopt`, `configure` (preference choices and own-tool decisions), `update` (when it undoes an installer's changes) and the daily maintenance (when it refreshes copied links). The routine sync of kit-managed state is not backed up; see [What restore does not undo](#what-restore-does-not-undo). `bootstrap` and `adopt` end with:

```
Undo any time: loadout restore --list
```

`loadout restore --list` shows the backup with its path. With `--verbose`, bootstrap and adopt print the path directly, and `configure`, `update` and the maintenance always do:

```
backup: ~/.claude/backups/loadout-20261010-093000  (undo: loadout restore ~/.claude/backups/loadout-20261010-093000)
```

Backups can hold old configs and undo commands with secrets in them. On Linux and macOS the folder is private (0700); saved copies and the manifest are 0600, and moved items keep their own mode (`backup.PRIVATE_DIR`, `PRIVATE_FILE`). Delete old ones when you no longer need them.

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
- A recorded command runs: for Claude Code, `claude` reinstalls a plugin or re-adds a marketplace or an MCP server; for Codex, `codex` removes a plugin or marketplace that loadout installed. Plugins were uninstalled with `--keep-data`, so their data is still there. On a Windows `claude.cmd` shim, which cannot take JSON, the command is written to a private `manual-commands.txt` for you to run by hand.

Restore only trusts backups that loadout made: a folder outside `~/.claude/backups`, a backup copy outside its own `files/` folder, or an undo command loadout never records is refused, so a hand-edited or foreign manifest cannot make it run anything beyond the undo commands loadout records.

Whatever restore replaces goes into a new `pre-restore` backup, so a restore can be undone too. A step that failed is reported, and a backup with a failed step is not marked as restored: fix the cause and run the same restore again. A backup that was already restored is refused unless you pass `--force`.

## What restore does not undo

- Links that bootstrap created where nothing was before: `~/.claude/rules/loadout`, `~/.claude/rules/personal`, and the launcher script `~/.local/bin/loadout`. Remove them as in [Uninstall](uninstall.md).
- The `# loadout PATH` block that bootstrap appended to an existing shell startup file. It has no backup: remove the lines between `# loadout PATH` and `# loadout PATH end`.
- On native Windows, the folders added to your user PATH. The old value is in the backup folder.
- The tools `--install` installed: uv, Claude Code, Codex, mise and what mise installed. See [Uninstall](uninstall.md#what-stays).
- The "# loadout secrets" line that bootstrap appended to an existing shell startup file on Linux and macOS. A startup file that bootstrap created, and a Windows PowerShell profile (a copy is saved first), are covered.
- Claude Code plugins and marketplaces that bootstrap or `configure` installed. They stay; uninstall them with `claude plugin uninstall ID`. (Restore does remove the Codex plugins and marketplaces loadout installed; see [Codex](#codex).)
- What a profile writes into a repo with `loadout profile` or `loadout init`: `.claude/settings.json`, `.mcp.json` and, with Codex on, `.codex/config.toml` and the `.agents/skills` links. These are committed repo files; use git there. (The Codex plugins a profile installs, and the switch it sets in `~/.codex/config.toml`, are in a backup and restore removes them.)
- The routine settings merge. `loadout configure`, `apply-settings` and the daily maintenance write `~/.claude/settings.json` and the managed-settings snapshot `~/.claude/.loadout/managed-settings.json` without a backup, and `apply_mcp` re-adds or removes your personal MCP servers without a backup. They change only what the kit manages (see [Settings merge](../reference/settings-merge.md)); bootstrap and adopt do save `settings.json` and the snapshot before their merge. Your personal layer's git history is the record of what you asked for.
- The git credential helper that bootstrap sets with `gh auth setup-git` when `gh` is logged in. Bootstrap prints the undo command: `git config --global --unset-all credential.https://github.com.helper`.

## Codex

With Codex on, the first change to an existing `~/.codex/AGENTS.md` or `~/.codex/config.toml` saves a copy in the backup (`$CODEX_HOME` replaces `~/.codex` if set). A file loadout created is moved aside on restore. Restore also runs the recorded `codex plugin remove` and `codex plugin marketplace remove` for the plugins and marketplaces loadout installed, so they are gone afterwards; ones that were already there stay. `loadout adopt` removing a Codex-only MCP server saves `config.toml` first, and a removed skill moves into the backup, so restore brings both back. To turn Codex off, see [Use loadout with Codex](codex.md#switch-it-on); to remove it fully, [Uninstall](uninstall.md#codex).

## The managed-settings snapshot

Bootstrap and adopt save the snapshot in the backup, so restoring `settings.json` and the snapshot together keeps them consistent. Backups made before the snapshot was part of them do not hold it. Restoring one after a global hook or plugin choice can let the next settings merge drop the restored value again. Check `~/.claude/settings.json` afterwards. Why the snapshot exists: [settings merge](../reference/settings-merge.md#the-snapshot).

## Common cases

| I want to | Do |
|---|---|
| Undo the last adopt | `loadout restore <path adopt printed>` |
| Bring back one tool I removed | Restore replays a whole backup; it cannot pick single items. Reinstall one tool with its own command if you do not want the rest back |
| Undo a restore | `loadout restore <pre-restore backup path>` (it is printed, and listed by `--list`) |
| See what a backup holds | Open `~/.claude/backups/loadout-<timestamp>/manifest.json`. Do not share it: it can contain secrets |
