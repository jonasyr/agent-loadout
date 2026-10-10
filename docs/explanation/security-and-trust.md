# Security and trust

loadout keeps itself current, so you should know what runs without asking, what it touches, and where the trust boundary is.

## What runs automatically

| What | When | Who runs it |
|---|---|---|
| Plugin and marketplace updates | Whenever Claude Code decides, for marketplaces with `"autoUpdate": true` (the kit's own and the third-party ones in `settings.base.json`) | Claude Code |
| The session hook | Start of every session | Claude Code runs `loadout hook-session-start` |
| Pull of the kit and the personal layer | At most once a day, in a detached background process started by the session hook | `maintenance._maintain` |
| Version check of tool binaries | At most once a week, same process | `maintenance._maintain` |

The daily pull is `git pull --ff-only`. It runs only when the checkout has no uncommitted changes, with git's terminal prompt turned off (`maintenance.pull_if_clean`). After a pull that brought new commits, loadout re-merges `settings.json`, applies your personal `mcp.json` and relinks skills and hook scripts. The next session then runs the pulled `loadout` code and the plugin's hooks.

The weekly check only looks. It queues a notice for the next session start. Tool binaries are updated only by `loadout update`, which shows each command and asks first (`--yes` skips the question).

A plugin can ship hooks, so a plugin update can run new code in your next session. Which hooks the loadout plugin ships is listed in [Hooks](../reference/hooks.md).

## What loadout touches

It changes:

- `~/.claude/settings.json`: only the keys it manages. Your other keys stay. See [Settings merge](../reference/settings-merge.md).
- `~/.claude/rules/loadout`, `~/.claude/rules/personal`, linked skills and `~/.claude/hooks/personal`: links into the kit and the personal layer (copies on Windows without Developer Mode).
- User-scope MCP servers from your personal `mcp.json`, and plugins and marketplaces through the `claude` CLI.
- `~/.config/loadout/`: your personal layer, `secrets.env`, and the machine-local state in `~/.claude/.loadout/`.
- A secrets-loading line in your shell startup file (or both PowerShell profiles on Windows).
- `loadout` on your `PATH`.
- Git's credential helper for `github.com`: when `gh` is logged in, bootstrap runs `gh auth setup-git` so git uses your `gh` login, and prints the undo command (`bootstrap.check_prereqs`).
- `~/.claude/CLAUDE.md`, only if you pick it in adopt's `review` group (or pass `--groups review`): its content moves into `<personal>/rules/me.md`, the original goes into the backup, and the file keeps a one-line marker (`adopt.migrate_claude_md`).

It does not touch:

- Your `~/.claude/CLAUDE.md`, apart from the adopt choice above. Rules are linked as a folder instead.
- Settings keys it does not manage, unless you ask (`adopt`).
- Project files, except through `loadout init` and `loadout profile`, which never overwrite a file.
- Your account, claude.ai connectors or any credentials.

Anything loadout removes or replaces is moved to a backup first.

## Backups and restore

Every command that removes or replaces something writes a backup folder `~/.claude/backups/loadout-<timestamp>` with a manifest of undo steps. `loadout restore <dir>` replays them, and what it replaces goes into a new backup, so a restore can be undone too. Backups can hold old configs and undo commands with secrets in them, so the folders are created readable only by you (0700, files 0600, `backup.PRIVATE_DIR`). Delete old ones when you no longer need them. How to use them, and what restore does not undo, is in [Undo what loadout changed](../how-to/undo-and-restore.md).

## Secrets

Never put keys into config files.

- **Where they live.** `~/.config/loadout/secrets.env`, created by bootstrap from `secrets.env.example`, mode 600. Entries are `NAME='value'` in single quotes. A `'` inside a value is written `'\''`, so the shell never runs part of a value.
- **How they are loaded.** Bootstrap adds a line to the startup file of your `$SHELL` (plus an existing `.bashrc` or `.zshrc`), and on Windows to both PowerShell profiles. Only Claude Code started from such a shell sees them. A Windows execution policy of `Restricted` stops the profiles from running. Bootstrap prints the fix and does not apply it.
- **How configs refer to them.** MCP configs use `${NAME}`.
- **Finding plaintext keys.** `loadout adopt` detects secrets in plain text and never prints them (`secrets.redact` masks every printed line). It can move secrets in user-scope servers in `~/.claude.json` to `secrets.env`. It only reports secrets in project-scoped servers, `~/.claude/.mcp.json`, your personal `mcp.json`, the `env` block of `settings.json` and URL query strings, so you can move them by hand.
- **The secret guard.** When you record your own tools into the personal layer, a stricter guard applies: nothing that looks like a secret or a private file is written, and the guard refuses when it cannot tell. The rules are in [Handle your own tools](../how-to/your-own-tools.md#secret-guard). The reasoning is in [0006](../adr/0006-secrets-in-secrets-env.md) and [0018](../adr/0018-secret-guard-fails-closed.md).

Your personal layer is meant to be a private git repo. The commit offer after `loadout configure` and `adopt` refuses while a `*.env` file or another private file would be committed.

## The trust boundary

Your personal layer can run code on every machine you sync it to. It can hold hooks, skills and MCP server commands, and the daily pull brings changes in without a prompt. Treat the personal repo like a dotfiles repo: private, with a strong login on the host. The same holds for the kit repo. Whoever can push to it reaches every machine that follows it.

For a team, use a fork of the kit that you control and point your clone (or `LOADOUT_ROOT`) at it. Changes then reach colleagues only after you review them.

## Opting out

- **Marketplace auto-update.** Set `"autoUpdate": false` for a marketplace in your personal `settings.json`, for example `{"extraKnownMarketplaces": {"impeccable": {"autoUpdate": false}}}`.
- **The daily pull.** Set `LOADOUT_NO_AUTO_PULL=1` in your environment (`maintenance._maintain`). Pull the kit and personal folders yourself when you want changes.
- **Binary updates.** Nothing to turn off: they only happen when you run `loadout update`.

See also [Architecture](architecture.md) for the data flow and [Personal layer](../reference/personal-layer.md#sync) for the sync rules.
