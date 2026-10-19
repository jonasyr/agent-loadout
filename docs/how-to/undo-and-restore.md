# Undo what loadout changed

Use this page when something went wrong after `bootstrap`, `adopt`, `configure`, `loadout init` or `loadout profile`, or when you want a removed tool back.

## Backups

Before loadout removes or replaces a tool, file or link you own, it moves the old item into a backup folder `~/.local/state/loadout/backups/loadout-<timestamp>` and records how to undo each step in `manifest.json`. These make backups:

- `bootstrap` and `adopt`;
- `configure` (preference choices, own-tool decisions, turning an agent on);
- `update` (when it undoes an installer's changes, and for the Codex plugins it updates);
- the daily sync after a pull that brought new commits (the links and copies it replaces, and the Codex files it refreshes);
- `init`, `profile` and `configure new skill --to repo` (for the files they write in a repo);
- `bootstrap --vscode-wsl` and `bootstrap --vscode-path` (the VS Code files they change);
- `restore` itself (a `pre-restore` backup);
- and any other step that replaces a file you own.

The routine sync of kit-managed state is not backed up; see [What restore does not undo](#what-restore-does-not-undo). `bootstrap` and `adopt` end with:

```
Undo any time: loadout restore --list
```

`loadout restore` in a terminal lets you pick it from a numbered list; `--list` shows the backups with their paths. `init`, `profile` and `configure new skill --to repo` always print the path (`undo: loadout restore <dir>`). With `--verbose`, bootstrap and adopt print the path directly, and `configure`, `update` and the daily sync always do:

```
backup: ~/.local/state/loadout/backups/loadout-20261010-093000  (undo: loadout restore ~/.local/state/loadout/backups/loadout-20261010-093000)
```

Backups can hold old configs and undo commands with secrets in them. On Linux and macOS the folder is private (0700); saved copies and the manifest are 0600, and moved items keep their own mode. Delete old ones when you no longer need them.

## List and restore

```bash
loadout restore                 # pick one by number, see what goes back, confirm
loadout restore --last          # the newest backup of any kind; asks in a terminal
loadout restore --show <path>   # what a backup puts back, nothing changed
loadout restore --list          # paths, for agents and scripts
loadout restore ~/.local/state/loadout/backups/loadout-<timestamp>
```

In a terminal, `loadout restore` without a folder shows the last 10 backups, numbered, newest first: how long ago and when, the command that made it, where (`home` or `repo <path>`), what it holds (`3 files, 2 commands`) and `restored <date>` if it was. Answer a number (`m` shows 10 more, Enter cancels); loadout then shows exactly what goes back (each file and each undo command, secrets masked) and asks `Restore this? [y/N]`. `--repo PATH` keeps only one repo's backups. Without a terminal nothing is picked: give a path or `--last`. Flags and exit codes: [CLI reference](../reference/cli.md#loadout-restore).

Backups made before loadout moved its files out of `~/.claude` restore from the new place, and an old printed command such as `loadout restore ~/.claude/backups/loadout-<timestamp>` still works. If the old `~/.claude/backups` folder still exists, restore says so: the move has not finished, or a different backup of the same name was kept in both places.

Restore replays the steps in reverse:

- A moved item is moved back. If something else now sits at that place, it goes into the new pre-restore backup first when it is a link or when loadout itself had replaced the original. In any other case the step is skipped with `skipped (exists)` and the backup is not marked as restored.
- A saved file (such as `settings.json` before a merge) is copied back unless it is identical.
- A file loadout created (a new `me.md`, `settings.json`, `secrets.env` or shell startup file) is moved aside, not deleted. In a repo, restore takes away the files and links `init`, `profile` or `new skill --to repo` created, and puts the files they changed back byte for byte. A folder loadout created goes only when it is empty; otherwise restore keeps it and prints a `kept` line.
- A recorded command runs: for Claude Code, `claude` reinstalls or re-enables a plugin, re-adds a marketplace, or puts an MCP server back (removing loadout's rewritten copy first); for Codex, `codex` removes a plugin or marketplace that loadout installed. Plugins were uninstalled with `--keep-data`, so their data is still there. On a Windows `claude.cmd` shim, which cannot take JSON, the command is written to a private `manual-commands.txt` for you to run by hand.

Restore only trusts backups that loadout made: a folder outside `~/.local/state/loadout/backups` (or `$XDG_STATE_HOME/loadout/backups`), a backup copy outside its own `files/` folder, or an undo command loadout never records is refused, so a hand-edited or foreign manifest cannot make it run anything beyond the undo commands loadout records.

Whatever restore replaces goes into a new `pre-restore` backup, so a restore can be undone too. A step that failed is reported, and a backup with a failed step is not marked as restored: fix the cause and run the same restore again. A backup that was already restored is refused unless you pass `--force`.

## What restore does not undo

- Links that bootstrap created where nothing was before: `~/.claude/rules/loadout`, `~/.claude/rules/personal`, `~/.claude/hooks/personal`, the links of your personal skills (`~/.claude/skills/<name>`, and with Codex on `~/.agents/skills/<name>`), and the launcher script `~/.local/bin/loadout`. A link or folder that was already there is in a backup. Remove them as in [Uninstall](uninstall.md).
- The `# loadout PATH` block that bootstrap appended to an existing shell startup file. It has no backup: remove the lines between `# loadout PATH` and `# loadout PATH end`. (A later update of that block saves a copy first. The same block that `bootstrap --vscode-path` writes to `~/.vscode-server/server-env-setup` is in a backup, so restore undoes it, as it undoes the VS Code setting that `--vscode-wsl` switches on.)
- On native Windows, the folders added to your user PATH. The old value is in the backup folder.
- The tools `--install` installed: uv, Claude Code, mise and what mise installed (Codex, Node, gh, rust-analyzer), Serena (a uv tool), codebase-memory-mcp, rtk and the npm tools (playwright-cli, pyright, typescript-language-server). See [Uninstall](uninstall.md#what-stays).
- The "# loadout secrets" line that bootstrap appended to an existing shell startup file on Linux and macOS. A startup file that bootstrap created, and a Windows PowerShell profile (a copy is saved first), are covered.
- Claude Code plugins and marketplaces that bootstrap or `configure` installed. They stay; uninstall them with `claude plugin uninstall ID`. (Restore does remove the Codex plugins and marketplaces loadout installed; see [Codex](#codex).)
- What a profile's `commands` do, and the `git init` that `loadout init` runs in a folder that is not a repo yet. The plan shows both as `run` steps and says restore cannot undo them. (The files `init` and `profile` write in a repo, and the Codex plugins and the switch in `~/.codex/config.toml`, are in a backup and restore undoes them; see [Repo writes](../reference/cli.md#repo-writes).)
- The routine settings merge. `loadout configure`, `apply-settings` and the daily sync write `~/.claude/settings.json` and the managed-settings snapshot `~/.local/state/loadout/managed-settings.json` without a backup, and `configure` and the daily sync re-add or remove your personal MCP servers without a backup. They change only what the kit manages (see [Settings merge](../reference/settings-merge.md)); bootstrap and adopt do save `settings.json` and the snapshot before their merge. Your personal layer's git history is the record of what you asked for.
- The git credential helper that bootstrap sets with `gh auth setup-git` when `gh` is logged in. With `--verbose`, bootstrap prints the undo command; see also [Uninstall](uninstall.md#what-stays).

## Codex

With Codex on, every change to `~/.codex/AGENTS.md` (adding loadout's block, every rewrite of it, also the refresh at a session start) and to `~/.codex/hooks.json` saves a copy in the backup first. For `~/.codex/config.toml` that is loadout's first change, every plugin switch on or off, and every removal of one of its sections. `$CODEX_HOME` replaces `~/.codex` if set. A file loadout created is moved aside on restore. Restore also runs the recorded `codex plugin remove` and `codex plugin marketplace remove` for the plugins and marketplaces loadout installed, so they are gone afterwards; ones that were already there stay. `loadout adopt` removing a Codex-only MCP server saves `config.toml` first, and a removed skill moves into the backup, so restore brings both back. To turn Codex off, see [Use loadout with Codex](codex.md#switch-it-on); to remove it fully, [Uninstall](uninstall.md#codex).

## The managed-settings snapshot

Bootstrap and adopt save the snapshot in the backup, so restoring `settings.json` and the snapshot together keeps them consistent. Backups made before the snapshot was part of them do not hold it. Restoring one after a global hook or plugin choice can let the next settings merge drop the restored value again. Check `~/.claude/settings.json` afterwards. Why the snapshot exists: [settings merge](../reference/settings-merge.md#the-snapshot).

## Common cases

| I want to | Do |
|---|---|
| Undo the last adopt | `loadout restore` and pick the adopt backup by its command and age (a later command or restore may have made a newer one) |
| Bring back one tool I removed | Restore replays a whole backup; it cannot pick single items. Reinstall one tool with its own command if you do not want the rest back |
| Undo what `init`, `profile` or `configure new skill --to repo` wrote in a repo | `loadout restore --repo PATH` and pick the backup (recommended: it shows what goes back before it asks), or `loadout restore <dir>` with the `undo:` path the command printed (a profile's `commands` stay done) |
| Undo a restore | `loadout restore <pre-restore backup path>` (it is printed), or pick it in `loadout restore` |
| See what a backup holds | Open `~/.local/state/loadout/backups/loadout-<timestamp>/manifest.json`. Do not share it: it can contain secrets |
