# Undo what loadout changed

Use this page when something went wrong after `bootstrap`, `adopt`, `configure`, `loadout init` or `loadout profile`, or when you want a removed tool back.

## Backups

Before loadout removes or replaces a tool, file or link you own, it moves the old item into a backup folder `~/.local/state/loadout/backups/loadout-<timestamp>` and records how to undo each step in `manifest.json`. These make backups:

- `bootstrap` and `adopt`;
- `configure` (preference choices, own-tool decisions, turning an agent on);
- `update` (any file its re-apply replaces, and what it undoes after an installer);
- the daily sync after a pull that brought new commits (the links and copies it replaces, and the Codex files it refreshes);
- `init`, `profile` and `configure new skill --to repo` (for the files they write in a repo);
- `bootstrap --vscode-wsl` and `bootstrap --vscode-path` (the VS Code files they change);
- `restore` itself (a `pre-restore` backup);
- and any other step that replaces a file you own.

The first install also saves one snapshot archive of your setup before it writes anything. That is not a `loadout-<timestamp>` folder: see [Roll back the first install](#roll-back-the-first-install).

The routine sync of kit-managed state is not backed up; see [What restore does not undo](#what-restore-does-not-undo). `bootstrap` and `adopt` end with:

```
Undo any time: loadout restore --list
```

`loadout restore` in a terminal lets you pick it from a numbered list; `--list` shows the backups with their paths. `init`, `profile` and `configure new skill --to repo` always print the path (`undo: loadout restore <dir>`). With `--verbose`, bootstrap and adopt print the path directly. `configure` and `update` print it when they made a backup. The daily sync prints it as a notice, and only when it replaced or edited something:

```
backup: ~/.local/state/loadout/backups/loadout-20261010-093000  (undo: loadout restore ~/.local/state/loadout/backups/loadout-20261010-093000)
```

The manifest of a new backup holds no secret values. Saved copies, copied files and the config of a removed MCP server (a file in `files/`) can hold secrets. On Linux and macOS the folder is private (0700); saved copies, MCP configs and the manifest are 0600, and moved items keep their own mode. Backups made before this change can still carry secrets in the manifest. A restore passes an MCP server's config to `claude` on the command line for that one call. Delete old backups when you no longer need them.

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

## Roll back the first install

The first time bootstrap runs on a machine, it saves one archive of your agent setup before it writes anything. Bootstrap asks first:

```
Save a snapshot of your current setup first (2.4 MB, into ~/.local/state/loadout/backups)? [Y/n]
```

Enter takes it. `n` skips it, and so does `--no-snapshot`; `--snapshot` takes one on a later run too, without asking. Without a terminal, or with `--yes`, bootstrap takes it without asking. Bootstrap counts a run as a first install when the machine has no earlier snapshot, no recorded setup (`managed-settings.json`, `channel.json`) and no bootstrap backup; a machine that ran loadout before is not asked. Flags: [loadout bootstrap](../reference/cli.md#loadout-bootstrap).

If the archive cannot be written (a full disk, an unreadable file), bootstrap asks `Go on without a snapshot? [y/N]`. Without a terminal it stops before it changes anything and exits 1; run it again with `--no-snapshot` to go on without one.

**What it holds.** The places loadout changes, as they were before the install:

- `~/.claude` (the folders below left out) and `~/.claude.json`, for Claude Code;
- `$CODEX_HOME` (or `~/.codex`), for Codex, without its session and log folders;
- the shell startup files `.bashrc`, `.zshrc`, `.profile`, `.bash_profile` and `.zprofile`, fish's `config.fish` and `conf.d`, Windows PowerShell profiles, and VS Code's user `settings.json`.

Only the agents you chose are included. A place that did not exist is recorded as missing, so a restore can remove what the install created.

Left out: caches, transcripts and logs. In `~/.claude`: `projects`, `cache`, `plugins/cache`, `plugins/marketplaces`, `shell-snapshots`, `todos`, `statsig`, `telemetry`, `debug`, `file-history`, `ide`, `session-env`, `local`, `downloads` and `backups`. In Codex: `sessions`, `archived_sessions`, `log`, `logs`, `cache`, `.tmp`, `tmp` and `plugins/cache`. A symlink is stored as a link and never followed. A file over 50 MB is left out; bootstrap prints its name, and the restore preview repeats it.

**Your logins are in it.** `~/.claude.json` holds your Claude Code account data, and Codex's `auth.json` (inside `~/.codex`) holds its login. Both are in the archive as they were before the install, unencrypted inside a gzip tar. The archive is readable only by you (0600) in the private backups folder, and that is the only protection: anyone who can read the file can use those logins. Delete it when you no longer need it (below).

The file is `first-install-<timestamp>.tar.gz`. A snapshot taken later with `bootstrap --snapshot` is `snapshot-<timestamp>.tar.gz`; the rollback never uses it, only the oldest `first-install-*` archive.

**Roll back.** Preview first, then confirm:

```bash
loadout restore --first-install          # shows what comes back and what is moved aside, then asks
loadout restore --first-install --yes    # the same, without the question
```

The preview lists `The snapshot from <date> puts back` (the files and links), `Moved aside first` (what the install added and is no longer in the archive), and any skipped file. It then asks `Put your setup from <date> back? [y/N]`. `n` changes nothing and exits 0. Without a terminal and without `--yes` nothing changes and it exits 1.

Restore then works file by file:

- Each file or link the archive holds replaces the one there now. The current item moves into a `pre-restore` backup first, and the restored copy is written beside the target before the swap, so a failure never leaves the target missing.
- What the install added (a link such as `~/.claude/rules/loadout`, a startup file that did not exist, a folder that was not there) is moved aside into the same pre-restore backup, not deleted.
- Folders left out of the archive are not touched.
- A member whose path would resolve outside HOME (through `..`, an absolute path, a hard link or a symlink on the way) is refused and named in the output; the rest is still restored.
- The whole archive is read before anything changes. A damaged archive, or one that is not loadout's snapshot, stops the restore with nothing changed.

Anything you changed in those files since the install goes back to the snapshot's version. The pre-restore backup keeps those versions; undo the rollback with the path it prints (`loadout restore <path>`).

**Not rolled back.** Installed tools (uv, Claude Code, Codex, mise and its tools, Serena and the rest), the plugin caches that were left out, and the git credential helper set by `gh auth setup-git`. See [What restore does not undo](#what-restore-does-not-undo).

**Delete the archive** when you no longer need the rollback. Find it, then remove it:

```bash
ls ~/.local/state/loadout/backups/
rm ~/.local/state/loadout/backups/first-install-<timestamp>.tar.gz
```

[Uninstall](uninstall.md) removes it with the state folder.

## What restore does not undo

- Links that bootstrap created where nothing was before: `~/.claude/rules/loadout`, `~/.claude/rules/personal`, `~/.claude/hooks/personal`, the links of your personal skills (`~/.claude/skills/<name>`, and with Codex on `~/.agents/skills/<name>`), and the launcher script `~/.local/bin/loadout`. A link or folder that was already there is in a backup. `loadout restore` does not remove the new ones; [Roll back the first install](#roll-back-the-first-install) does. Remove them as in [Uninstall](uninstall.md).
- The `# loadout PATH` block that bootstrap appended to an existing shell startup file. It has no backup (a `~/.config/fish/conf.d/loadout.fish` that bootstrap created is in the backup, so restore removes it), and `loadout restore` does not touch it. The first-install snapshot holds the startup files as they were before the install, so [Roll back the first install](#roll-back-the-first-install) removes the block too. Otherwise remove the lines between `# loadout PATH` and `# loadout PATH end` by hand. (A later update of that block saves a copy first. The same block that `bootstrap --vscode-path` writes to `~/.vscode-server/server-env-setup` is in a backup, so restore undoes it, as it undoes the VS Code setting that `--vscode-wsl` switches on.)
- On native Windows, the folders added to your user PATH. The old value is in the backup folder.
- The tools `--install` installed: uv, Claude Code, mise and what mise installed (Codex, Node, gh, rust-analyzer), Serena (a uv tool), codebase-memory-mcp, rtk and the npm tools (playwright-cli, pyright, typescript-language-server). See [Uninstall](uninstall.md#what-stays).
- The "# loadout secrets" line that bootstrap appended to an existing shell startup file on Linux and macOS. A startup file that bootstrap created, and a Windows PowerShell profile (a copy is saved first), are covered. [Roll back the first install](#roll-back-the-first-install) also removes this line, because the snapshot holds the startup files as they were before the install.
- Claude Code plugins and marketplaces that bootstrap or `configure` installed. They stay; uninstall them with `claude plugin uninstall ID`. (Restore does remove the Codex plugins and marketplaces loadout installed; see [Codex](#codex).)
- What a profile's `commands` do, and the `git init` that `loadout init` runs in a folder that is not a repo yet. The plan shows both as `run` steps and says restore cannot undo them. (The files `init` and `profile` write in a repo, and the Codex plugins and the switch in `~/.codex/config.toml`, are in a backup and restore undoes them; see [Repo writes](../reference/cli.md#repo-writes).)
- The routine settings merge. `loadout configure`, `apply-settings` and the daily sync write `~/.claude/settings.json` and the managed-settings snapshot `~/.local/state/loadout/managed-settings.json` without a backup, and `configure` and the daily sync re-add or remove your personal MCP servers without a backup. They change only what the kit manages (see [Settings merge](../reference/settings-merge.md)); bootstrap and adopt do save `settings.json` and the snapshot before their merge. Your personal layer's git history is the record of what you asked for.
- The git credential helper that bootstrap sets with `gh auth setup-git` when `gh` is logged in. With `--verbose`, bootstrap prints the undo command; see also [Uninstall](uninstall.md#what-stays).

## Codex

With Codex on, every change to `~/.codex/AGENTS.md` (adding loadout's block, every rewrite of it, also the refresh at a session start) and to `~/.codex/hooks.json` saves a copy in the backup first. For `~/.codex/config.toml` that is loadout's first change, every plugin switch on or off, and every removal of one of its sections. `$CODEX_HOME` replaces `~/.codex` if set. A file loadout created is moved aside on restore. Restore also runs the recorded `codex plugin remove` and `codex plugin marketplace remove` for the plugins and marketplaces loadout installed, so they are gone afterwards; ones that were already there stay. `loadout adopt` removing a Codex-only MCP server saves `config.toml` first, and a removed skill moves into the backup, so restore brings both back. A backup that holds loadout's record `codex-config.json` puts back the record as it was then, so it forgets which entries became yours since; each such entry gets its one note again at the next session start, and your file stays as it is. To turn Codex off, see [Use loadout with Codex](codex.md#switch-it-on); to remove it fully, [Uninstall](uninstall.md#codex).

## The managed-settings snapshot

Bootstrap and adopt save the snapshot in the backup, so restoring `settings.json` and the snapshot together keeps them consistent. Backups made before the snapshot was part of them do not hold it. Restoring one after a global hook or plugin choice can let the next settings merge drop the restored value again. Check `~/.claude/settings.json` afterwards. Why the snapshot exists: [settings merge](../reference/settings-merge.md#the-snapshot).

## Common cases

| I want to | Do |
|---|---|
| Undo the last adopt | `loadout restore` and pick the adopt backup by its command and age (a later command or restore may have made a newer one) |
| Bring back one tool I removed | Restore replays a whole backup; it cannot pick single items. Reinstall one tool with its own command if you do not want the rest back |
| Undo what `init`, `profile` or `configure new skill --to repo` wrote in a repo | `loadout restore --repo PATH` and pick the backup (recommended: it shows what goes back before it asks), or `loadout restore <dir>` with the `undo:` path the command printed (a profile's `commands` stay done) |
| Undo a restore | `loadout restore <pre-restore backup path>` (it is printed), or pick it in `loadout restore` |
| See what a backup holds | Open `~/.local/state/loadout/backups/loadout-<timestamp>/manifest.json`. A new backup's manifest holds no secrets, but the `files/` folder next to it can, and older manifests can too. Do not share the folder |
