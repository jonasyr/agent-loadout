# Security and trust

loadout keeps itself current, so you should know what runs without asking, what it touches, and where the trust boundary is.

## What runs automatically

| What | When | Who runs it |
|---|---|---|
| Plugin and marketplace updates | Whenever Claude Code decides: Claude Code updates plugins from `claude-plugins-official` (on by default) and from the marketplaces `settings.base.json` sets to `autoUpdate: true` (listed under [Marketplaces](../reference/included-tools.md#marketplaces)) | Claude Code |
| The session hook | Start of every session | Claude Code runs `loadout hook-session-start` |
| Pull of the kit and the personal layer | At most once a day, in a detached background process started by the session hook | `maintenance._maintain` |
| Version check of tool binaries | At most once a week, same process | `maintenance._maintain` |

How the pull and the weekly check work, what they re-apply and how to turn them off: [The daily sync](architecture.md#the-daily-sync). Tool binaries are updated only by [`loadout update`](../reference/cli.md#loadout-update), which shows each command and asks first.

A plugin can ship hooks, so a plugin update can run new code in your next session. Which hooks the loadout plugin ships is listed in [Hooks](../reference/hooks.md).

## What runs when you ask

- **`bootstrap --install`** runs the catalog's install commands without a further prompt (`bootstrap.check_prereqs`, `catalog.json`). Leave out `--install` to install tools yourself, or clone the repo and read the code first. They install into your home folder, without sudo. You trust:
  - **uv**: Astral's `curl … | sh` installer from the upstream default branch (on Windows its PowerShell installer).
  - **Claude Code**: Anthropic's native installer, run as `curl … | bash`.
  - **mise**: its installer, and then `mise use -g` for Node.js, gh and rust-analyzer (mise and each tool's upstream).
  - **codebase-memory-mcp** and **rtk**: `curl … | sh` installers from the upstream default branch (on Windows a PowerShell `irm` script for codebase-memory-mcp; rtk has no Windows installer).
  - **npm tools**: an unpinned `npm install -g @playwright/cli@latest` and similar global packages.
- **The one-liner** (`curl … | bash`, or the PowerShell `irm` form) runs `bootstrap.sh` or `bootstrap.ps1` from this repo's `main` branch, so you trust this repo. It clones the kit into `./agent-loadout`. An existing clone is used as it is: its GitHub origin is checked, its contents are not, and it is not pulled.
- **With Codex on** ([Use loadout with Codex](../how-to/codex.md)), bootstrap and the daily sync run `codex plugin marketplace add` for the GitHub marketplaces of the plugins you enabled for Claude Code (so you trust those repos in Codex too) and `codex plugin add` for the plugins.
- **`loadout update`** shows each update command and asks first (`--yes` skips the question).
- **`loadout profile` and `loadout init` with a profile** run the profile's plugin installs and `commands` in the repo unless you pass `--no-install` (`project._install`).

## What loadout touches

It changes:

- `~/.claude/settings.json`: only the keys it manages. Your other keys stay. See [Settings merge](../reference/settings-merge.md).
- `~/.claude/rules/loadout`, `~/.claude/rules/personal`, linked skills and `~/.claude/hooks/personal`: links into the kit and the personal layer (copies on Windows without Developer Mode).
- User-scope MCP servers from your personal `mcp.json`, and plugins and marketplaces through the `claude` CLI.
- `~/.config/loadout/`: your personal layer and `secrets.env`.
- `~/.claude/.loadout/`: machine-local state (snapshots, decisions, timestamps).
- A two-line secrets-loading block appended to each existing `.bashrc` and `.zshrc` and to the startup file of your `$SHELL` (`bootstrap.setup_secrets`), or both PowerShell profiles on Windows.
- `~/.local/bin/loadout`: a launcher script (on Windows `loadout.cmd` and a Git Bash shim), not a link. It runs Python 3.11 or newer if there is one, else a Python that uv manages, looked up from a neutral folder so a project's `.venv` or uv config is never used.
- A `# loadout PATH` … `# loadout PATH end` block appended to each existing `.bashrc` and `.zshrc` (and your shell's file) and to `~/.profile` (or `~/.bash_profile`). On native Windows bootstrap adds the folders to your user PATH instead and saves the old value in the backup.
- Once the mise shims are on your `PATH`, `node`, `gh` and the other mise tools follow a project's `.tool-versions` or `mise.toml`, and mise may install the version it names.
- Git's credential helper for `github.com`: when `gh` is logged in, bootstrap runs `gh auth setup-git` so git uses your `gh` login, and prints the undo command (`bootstrap.check_prereqs`).
- With Codex on: its own marked block in `~/.codex/AGENTS.md`, only the `[mcp_servers.*]` tables and keys it wrote in `~/.codex/config.toml` (recorded in `~/.claude/.loadout/codex-config.json`), links in `~/.agents/skills`, and plugins and marketplaces through the `codex` CLI. A profile plugin it installed for one repo gets `enabled = false` at user level, kept so on every sync. In a repo, `init` and `profile` add sections to `.codex/config.toml` (never changing yours) and link `.claude/skills` into `.agents/skills`. Adopt's "remove" and "global" for a Codex-only server run `codex mcp remove` after saving `config.toml` in the backup. In Codex, `serena-hooks auto-approve` approves Serena's tools (`mcp__serena__.*`) and `rtk hook codex` rewrites shell commands, after you approve the hooks in `/hooks`.
- `~/.claude/CLAUDE.md`, only if you pick it in adopt's `review` group (or pass `--groups review`): its content moves into `<personal>/rules/me.md`, the original goes into the backup, and the file keeps a one-line marker (`adopt.migrate_claude_md`).
- **Permissions.** Three things approve or rewrite tool calls without a prompt: the plugin hook `serena-hooks auto-approve` approves Serena's MCP tools (`mcp__plugin_loadout_serena__.*`), the plugin hook `rtk hook claude` rewrites every Bash command into rtk's form, and `settings.base.json` pre-approves `Bash(loadout advisor-mark:*)`. See [Hooks](../reference/hooks.md#hooks-of-the-loadout-plugin).

It does not touch:

- Your `~/.claude/CLAUDE.md`, apart from the adopt choice above. Rules are linked as a folder instead.
- Settings keys it does not manage, unless you ask (`adopt`).
- Project files, except through `loadout init` and `loadout profile`. Scaffold files are never overwritten. Profiles merge into the repo's `.claude/settings.json` and `.mcp.json` (the profile's value wins on the same key), may run the profile's `commands`, and are not backed up; use git.
- Your Claude login or claude.ai connectors. It does not change them. `loadout check` reads only the connector names in `~/.claude.json` (`claudeAiMcpEverConnected`) to warn about a plugin that duplicates one, and prints only names from the kit's catalog.

Items you own that loadout removes or replaces are moved to a backup first. The routine sync of what the kit itself manages (managed settings keys, your personal MCP servers) is not backed up, and neither is the shell startup file bootstrap appends to on Linux and macOS; your personal layer's git history is the record. See [What restore does not undo](../how-to/undo-and-restore.md#what-restore-does-not-undo).

## Programs and repo files

- **Program lookup.** loadout resolves external programs (`git`, `claude`, `codex`, installers) only from absolute `PATH` entries, never from the current folder or a relative entry. On Windows this also rules out the current-folder lookup `cmd` would do.
- **Repo symlinks.** `init` and `profile` never write through a symlink that leads out of the repo, and never run `git init` through a `.git` symlink. A skipped file is reported and the command exits 1.
- **Restore** trusts only backups under `~/.claude/backups`, copies only from a backup's own `files/` folder, and replays only the undo commands loadout records ([details](../how-to/undo-and-restore.md)).
- **Codex type-check hook.** For Rust repos its `cargo check` runs the build scripts and procedural macros of the repo you edit. That is normal cargo behaviour; do not edit untrusted repos with the hook on.

## Backups and restore

Backups go to `~/.claude/backups/loadout-<timestamp>` with a manifest of undo steps, and `loadout restore` replays them. They can hold old configs and secrets. Which commands make them, their file modes, and what restore does not undo: [Undo what loadout changed](../how-to/undo-and-restore.md).

## Secrets

Never put keys into config files.

- **Where they live.** `~/.config/loadout/secrets.env`, created by bootstrap from `secrets.env.example`, mode 600. Entries are `NAME='value'` in single quotes. A `'` inside a value is written `'\''`, so the shell never runs part of a value.
- **How they are loaded.** Bootstrap adds a block to each existing `.bashrc` and `.zshrc` and to the startup file of your `$SHELL` (bash or zsh), and on Windows to both PowerShell profiles. fish and other shells get no secrets loader; load `secrets.env` there yourself. Only Claude Code started from such a shell sees them. On Windows the execution policy must allow profiles: see [Troubleshooting](../how-to/troubleshooting.md#windows).
- **How configs refer to them.** MCP configs use `${NAME}`.
- **On the command line.** `claude mcp add-json` takes a server's configuration as an argument, so while it runs, other users of the machine can see it in the process list. loadout passes each configuration as it is stored: one that refers to `${NAME}` shows only the name, one that still holds a plaintext value shows that value. That happens for a plaintext value in your personal `mcp.json` (applied by bootstrap and the daily sync), for `loadout restore` re-adding a server with its original configuration, and for the rollback that re-adds a server's previous configuration when an update fails, including during `loadout adopt`'s secret move. On a shared machine, keep every secret in `secrets.env`.
- **Finding plaintext keys.** `loadout adopt` detects secrets in plain text and does not print them (`secrets.redact` masks what its patterns recognise in printed lines). It can move secrets in user-scope servers in `~/.claude.json` to `secrets.env`. It only reports secrets in project-scoped servers, `~/.claude/.mcp.json`, your personal `mcp.json`, the `env` block of `settings.json` and URL query strings, so you can move them by hand.
- **The secret guard.** When you record your own tools into the personal layer, a stricter guard applies (values you set yourself with `loadout configure set pref` are not checked): nothing that looks like a secret or a private file is written, and the guard refuses when it cannot tell. The rules are in [Handle your own tools](../how-to/your-own-tools.md#secret-guard). The reasoning is in [0006](../adr/0006-secrets-in-secrets-env.md) and [0018](../adr/0018-secret-guard-fails-closed.md).

Your personal layer is meant to be a private git repo. The commit offer after `loadout configure` and `adopt` refuses while a `*.env` file or another private file would be committed.

## The trust boundary

Your personal layer can run code on every machine you sync it to. It can hold hooks, skills and MCP server commands, and the daily pull brings changes in without a prompt. Treat the personal repo like a dotfiles repo: private, with a strong login on the host. The same holds for the kit repo. Whoever can push to it reaches every machine that follows it.

For a team, use a fork of the kit that you control and point your clone (or `LOADOUT_ROOT`) at it. Changes then reach colleagues only after you review them.

## Opting out

- **Marketplace auto-update.** Set `"autoUpdate": false` for a marketplace in your personal `settings.json`, for example `{"extraKnownMarketplaces": {"impeccable": {"autoUpdate": false}}}`.
- **The daily pull.** Set `LOADOUT_NO_AUTO_PULL=1`. Details: [The daily sync](architecture.md#the-daily-sync).
- **Binary updates.** Nothing to turn off: they only happen when you run `loadout update`.

See also [Architecture](architecture.md) for the data flow and the daily sync.
