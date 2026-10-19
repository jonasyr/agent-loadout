# loadout's state and the daily sync

Where loadout keeps its own files, how it moved them out of `~/.claude`, and what the daily sync does step by step. Why it is built this way: [Architecture](../explanation/architecture.md#loadouts-own-files). The variables that change these paths are in [Environment variables](cli.md#environment-variables).

## State folders

loadout's state folder is `$XDG_STATE_HOME/loadout` when `XDG_STATE_HOME` is an absolute path, else `~/.local/state/loadout`. A relative or empty `XDG_STATE_HOME` is ignored. The rule is the same on every OS (on Windows `~` is `HOME`, else `USERPROFILE`) and for every user, Codex-only included: the path does not depend on whether Claude Code is on (`paths.state_dir`, [ADR 0025](../adr/0025-state-in-xdg-state-home.md)). The plugin's hook scripts (`advisor.py`, `tool_hint.py`, `reload_check.py`) compute the same path themselves.

| Folder | Holds |
|---|---|
| `~/.local/state/loadout/` | Machine-local state: the settings snapshot, the record of loadout's `config.toml` and `hooks.json` entries, your `leave` decisions, queued notices, the sync's timestamps and locks, the hook scripts' session files. Each file is listed in [Machine-local state](personal-layer.md#machine-local-state); the tool hints' `tool-hint/` folder is described in [Hooks](hooks.md). Not synced. |
| `~/.local/state/loadout/backups/` | One `loadout-<timestamp>` folder per change that moved or replaced something you own, with a manifest of undo steps (`paths.backups_root`). A run of `init`, `profile`, `configure new skill --to repo`, or `adopt` when it applies a profile to a repo, makes one for the repo files it changes; the manifest names the repo. See [Undo what loadout changed](../how-to/undo-and-restore.md). |

Every command except `kit-path`, `check` and `usage` creates the state folder at its start, readable only by you (mode `0700`; Windows keeps its default permissions). Those three promise to change nothing, so they neither create it nor run the move below.

Two more files belong to loadout on this machine but sit outside the state folder: the personal layer (`~/.config/loadout/personal`, or `$LOADOUT_PERSONAL`; see [Personal layer](personal-layer.md)) and `~/.config/loadout/secrets.env`. Neither follows `XDG_CONFIG_HOME`. loadout reads `XDG_CONFIG_HOME` only to find VS Code's user settings on Linux (`$XDG_CONFIG_HOME/Code/User`).

## The move out of ~/.claude

Older versions kept the state in `~/.claude/.loadout` and the backups in `~/.claude/backups`. loadout moves both in two steps (`migrate.py`), because an older loadout run, or the hooks of a Claude Code session that has not reloaded its plugins, can still write the old place while a new run moves it.

**Copy.** At the start of every command except `kit-path`, `check` and `usage`, and of the session hook, loadout takes a lock (`migrate.lock` in the state folder) and copies everything of its own from the old places to the new one. It never overwrites a file at the new place. In `~/.claude/backups` only its own `loadout-<timestamp>` folders with a manifest count; Claude Code's own `.claude.json` copies there stay. Locks are never copied. Each copy is recorded with a signature of the old entry and of the copy in `migrated.json`.

- Another run waits up to 10 seconds for the lock (the session hook waits 2). A lock not renewed for 5 minutes is from a killed run and is taken over.
- Until everything is copied, commands that change something stop with exit code 1 and say why. `kit-path`, `check`, `usage`, `restore` and `explain` still run, the session hook exits quietly, and the next run continues.
- An entry that can never be copied (for example a file owned by root after a `sudo` run) blocks the move: move or delete it by hand. `loadout check` names it in the row `loadout state`.

**Retire.** A later run deletes each old entry that is still exactly what was copied, but only 10 minutes after the copy at the earliest, and only while no older loadout run holds a maintenance lock in `~/.claude/.loadout` that is younger than an hour.

- An old entry that an older run changed after the copy replaces the copy at once (in the next run, before the command does anything), if the copy is untouched.
- When both changed, both stay. The run names the old one once, and `loadout check` warns in the row `loadout state` until you compare and delete it by hand.
- A copy you deleted at the new place is not copied back. If the old entry changed as well, both are kept and named.
- Session files of the hooks (`advisor-pending.json`, `advisor-done.json`, `reload-notified.json`) are never copied back over the new ones. Their old copies go once they have been untouched for a day.

Afterwards loadout removes the old folders when they are empty, and an empty `~/.claude` only when Claude Code is off. Backups made before the move restore from the new place ([loadout restore](cli.md#loadout-restore)).

## The daily sync

### At each session start

The loadout plugin's `SessionStart` hook runs `loadout hook-session-start`: from `hooks/hooks.json` in Claude Code, from `hooks/codex.json` in the Codex CLI after you approve loadout's hooks in `/hooks`. The hook goes through `hooks/run.sh`, which skips it when `loadout` is not on the `PATH` the agent sees. The hook never breaks a session: errors are swallowed and it always exits 0. It:

1. Prints the queued notices (`pending-notice`) as one message and empties the queue.
2. Starts `loadout maintenance` as a detached process, from your home folder, when the daily pull or the weekly check is due. The session never waits for it. With `LOADOUT_NO_AUTO_PULL=1` only the weekly check can make it due.
3. With Codex on, rewrites loadout's block in `~/.codex/AGENTS.md` when a rule or `me.md` changed by hand (`codex.refresh_instructions`), with a backup first. It only touches an existing block that loadout wrote, and skips this while another loadout run sets Codex up.

While the move out of `~/.claude` is unfinished, the hook exits quietly before any of this.

**VS Code's Codex extension without the Codex CLI** loads no plugins, so it runs no plugin hook and never starts the sync. On such a machine the daily pull, the weekly check and the notices run only when a Claude Code session starts them (Claude Code on, in the terminal or in the Claude Code extension), or when the Codex CLI is installed next to the extension and its hooks are approved ([Use loadout with VS Code](../how-to/vscode.md#the-codex-cli-alongside-vs-code)).

### The background run

`loadout maintenance` (`maintenance._maintain`) runs one at a time: it takes `maintenance.lock` in the state folder (`locks.py`) and gives up silently when another run holds it. A foreground command (`loadout update`, `bootstrap`, `configure`) takes the same locks but waits for the holder instead: `waiting for the other loadout run (<command>, started <HH:MM>)… <n>s` on a terminal until it is free, up to 10 minutes without a terminal, then it stops with `the other loadout run (…) is still running; run this again when it has finished`. The lock file holds the holder's command, start time, process id, host name and (Linux) its pid namespace and boot id as JSON. A lock not touched for an hour counts as left over from a crash and is taken over; on Linux so is a lock whose process has ended (a run that was killed), but only when host, pid namespace and boot id all match, so a container or distrobox sharing the state folder never takes over a live run. Elsewhere only the age counts. When both are needed, `maintenance.lock` comes first, then `codex.lock`.

**The daily pull**, at most once a day, unless `LOADOUT_NO_AUTO_PULL=1`:

1. It records the time (`last-pull`) first, so a failed pull is not retried until the next day.
2. It runs `git pull --ff-only` on the kit and on the personal layer, each only when it is a git checkout (`maintenance.pull`). There is no clean-tree gate: untracked files and edits to files the pull does not touch do not stop it, and git itself refuses when a change would overwrite something, so your work is never changed. A detached HEAD or a branch without an upstream is skipped. A refusal (local changes the pull would overwrite, a diverged branch, any other git error) is written to `sync-paused.json` with the files git named and queued once as a notice (`the daily sync of <root> paused: <reason>: <files>; commit or stash them, then run loadout update`); `loadout check` warns while it stands, and the next successful pull clears it. Git's terminal and credential prompts are turned off (`GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=never`) and git runs with `LC_ALL=C`.
3. Only when a pull brought new commits does it re-apply anything:
   - **Claude Code**, when it is on: the settings merge, your personal MCP servers, and the links (skills, hook scripts, and copies in copy mode). Links and copies it replaces go to a backup first.
   - **Codex**, when it is on and usable (a supported `codex` on `PATH`, or, without one, VS Code's Codex extension on this side with a new enough codex ([version](../how-to/codex.md#switch-it-on)): extension mode): `codex.apply_all(refresh=True)` refreshes the `AGENTS.md` block, the `config.toml` entries, Serena's hooks in `hooks.json`, the skill links and the plugins, with a backup first. In extension mode the plugins are skipped. A plugin refresh leaves marketplaces set to `autoUpdate: false` as they are. Then, when both agents are on, the drift check compares their MCP servers and skills.
4. Problems, backups made and drift become notices for the next session. An error never crashes the run; it becomes a notice too.

The next session runs the pulled `loadout` code and the plugin's hooks. Plugins newly enabled through the personal layer are installed by Claude Code at its next start, not by this run ([ADR 0015](../adr/0015-claude-code-installs-synced-plugins.md)). In Claude Code the run never calls `claude plugin update`: Claude Code updates the kit's marketplaces itself (`autoUpdate: true` in `settings.base.json`; [ADR 0024](../adr/0024-codex-parity-update-model.md)).

**The weekly check**, at most once a week (`last-update-check`), also with `LOADOUT_NO_AUTO_PULL=1`: it compares the installed and the latest version of each installed catalog tool, through mise when mise manages the tool (so its pins and release-age rules count). An update that the package manager already refused (`refused-updates.json`) is not named again until a newer version appears. It queues "updates available … run `loadout update`" and never installs anything.

`maintenance` and `hook-session-start` are internal subcommands and do not appear in `loadout --help`. What reaches your machine through the pull, and who can push it, is in [the trust boundary](../explanation/security-and-trust.md#the-trust-boundary).
