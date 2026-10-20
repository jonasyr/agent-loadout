# Security and trust

loadout keeps itself current for Claude Code and Codex, so you should know what runs without asking, what it touches, and where the trust boundary is.

## What runs automatically

| What | When | Who runs it |
|---|---|---|
| Plugin and marketplace updates, Claude Code | Whenever Claude Code decides: it updates plugins from `claude-plugins-official` (on by default) and from the marketplaces `settings.base.json` sets to `autoUpdate: true` (listed under [Marketplaces](../reference/included-tools.md#marketplaces)) | Claude Code |
| Plugin refresh, Codex | After a daily pull that brought new commits, if Codex is on and the Codex CLI is installed (VS Code's Codex extension alone loads no plugins) | `maintenance._maintain`, through the Codex CLI |
| The session hook, Claude Code | Start of every session | Claude Code runs `loadout hook-session-start` from the plugin's `hooks/hooks.json` |
| The session hook, Codex | Start of every session of the Codex CLI, once you approved the plugin's hooks in `/hooks` (VS Code's Codex extension runs no plugin hooks; [At each session start](../reference/state-and-sync.md#at-each-session-start)) | Codex runs `loadout hook-session-start` from the plugin's `hooks/codex.json` |
| Pull of the kit and the personal layer | At most once a day, in a detached background process started by the session hook | `maintenance._maintain` |
| Version check of tool binaries | At most once a week, same process | `maintenance._maintain` |
| Tool hints | Before search, shell and web tool calls (in Codex: shell calls), and after Serena or graph calls | The plugin's `hooks/tool_hint.sh` and `tool_hint.py`: they read the call's input and the repo's top-level file names, write only counters to `~/.local/state/loadout/tool-hint/`, and use no network ([Hooks](../reference/hooks.md#hooks-of-the-loadout-plugin)) |

How the pull and the weekly check work, what they re-apply and how to turn them off: [The daily sync](../reference/state-and-sync.md#the-daily-sync). Tool binaries are updated only by [`loadout update`](../reference/cli.md#loadout-update), which shows each command and asks first.

Both agents run loadout's code only through the plugin's hooks. Codex runs plugin hooks only after you approve them in `/hooks`, and asks again when they change; loadout never approves them for you. VS Code's Codex extension without the Codex CLI loads no plugins, so it runs none of loadout's code ([Codex in VS Code without the CLI](../how-to/vscode.md#codex-in-vs-code-without-the-cli)). A plugin can ship hooks, so a plugin update can run new code in your next session. Which hooks the loadout plugin ships is listed in [Hooks](../reference/hooks.md).

## What runs when you ask

- **`bootstrap --install`** runs the catalog's install commands without a further prompt (`bootstrap.check_prereqs`, `catalog.json`). One exception: with VS Code's Codex extension and no Codex CLI, it asks in a terminal whether to install the Codex CLI (default yes); `--without-codex-cli` leaves it out. On your own machine `--install` is the recommended path ([Pick your setup](../how-to/setups.md#recommended-setups)); on a machine you share or administer, leave it out and install the tools yourself, or clone the repo and read the code first. They install into your home folder, without sudo. You trust:
  - **uv**: Astral's `curl … | sh` installer from astral.sh (on Windows its PowerShell installer).
  - **Claude Code**: Anthropic's native installer, run as `curl … | bash`.
  - **mise**: its `curl … | sh` installer (on Windows `winget install jdx.mise`), and then `mise use -g` for Node.js, gh and rust-analyzer, and with Codex on for codex (mise and each tool's upstream).
  - **Serena**: `uv tool install serena-agent`, an unpinned package from PyPI.
  - **codebase-memory-mcp** and **rtk**: `curl … | bash` (codebase-memory-mcp) and `curl … | sh` (rtk) installers from the upstream default branch (on Windows a PowerShell `irm` script for codebase-memory-mcp; rtk has no Windows installer).
  - **npm tools**: an unpinned `npm install -g @playwright/cli@latest` and similar global packages.
- **The one-liner** (`curl … | bash`, or the PowerShell `irm` form) runs `bootstrap.sh` or `bootstrap.ps1` from this repo's `main` branch, so you trust this repo. It clones the kit into `./agent-loadout`. An existing clone is used as it is: its GitHub origin is checked, its contents are not, and it is not pulled.
- **With Codex on and the Codex CLI installed** ([Use loadout with Codex](../how-to/codex.md)), bootstrap and the daily sync run `codex plugin marketplace add` for the GitHub marketplaces of the plugins you enabled for Claude Code (so you trust those repos in Codex too) and `codex plugin add` for the plugins.
- **`loadout update`** pulls the kit and your personal layer (not with `LOADOUT_NO_AUTO_PULL=1`), then shows one plan with each tool's update command and asks once (`--yes` skips the question; without a terminal and without `--yes` it changes nothing). What it may change: [`loadout update`](../reference/cli.md#loadout-update).
- **`loadout profile` and `loadout init` with a profile** run the profile's plugin installs and `commands` in the repo unless you pass `--no-install`. Both show the plan, `commands` included, and ask first; without a terminal they run only with `--yes`. `commands` run after the file changes, and `loadout restore` cannot undo them.

## What loadout touches

It changes:

- `~/.claude/settings.json`: only the keys it manages. Your other keys stay. See [Settings merge](../reference/settings-merge.md).
- `~/.claude/rules/loadout`, `~/.claude/rules/personal`, linked skills and `~/.claude/hooks/personal`: links into the kit and the personal layer (copies on Windows without Developer Mode).
- User-scope MCP servers from your personal `mcp.json` (`claude mcp add-json`), and plugins and marketplaces through the `claude` CLI. For Codex the MCP servers are owned sections in `config.toml`, below.
- `~/.config/loadout/`: your personal layer and `secrets.env`.
- `~/.local/state/loadout/` (or `$XDG_STATE_HOME/loadout`): machine-local state (snapshots, decisions, timestamps), also when only Codex is on. See [State folders](../reference/state-and-sync.md#state-folders).
- A two-line secrets-loading block in your shell startup files (`bootstrap.setup_secrets`); which files, and which shells get none: [Secrets](#secrets).
- `~/.local/bin/loadout`: a launcher script (on Windows `loadout.cmd` and a Git Bash shim), not a link. It runs Python 3.11 or newer if there is one, else a Python that uv manages, looked up from a neutral folder so a project's `.venv` or uv config is never used.
- A `# loadout PATH` … `# loadout PATH end` block appended to each existing `.bashrc` and `.zshrc` (and your shell's file) and to `~/.profile` (or `~/.bash_profile`). On native Windows bootstrap adds the folders to your user PATH instead and saves the old value in the backup.
- Once the mise shims are on your `PATH`, `node`, `gh` and the other mise tools follow a project's `.tool-versions` or `mise.toml`, and mise may install the version it names.
- Git's credential helper for `github.com`: when `gh` is logged in, bootstrap runs `gh auth setup-git` so git uses your `gh` login, and with `--verbose` prints the undo command (`bootstrap.check_prereqs`).
- With Codex on (`$CODEX_HOME` instead of `~/.codex` if you set it): its own marked block in `~/.codex/AGENTS.md` (the rest of the file stays yours), only the entries it wrote in `~/.codex/hooks.json` (Serena's documented hooks, [ADR 0028](../adr/0028-serena-codex-hooks-in-hooks-json.md)), only the `[mcp_servers.*]` tables and keys it wrote in `~/.codex/config.toml` (recorded in `~/.local/state/loadout/codex-config.json`; secrets are written as `env_vars` names, never values), the plugins' `enabled` switches there, links in `~/.agents/skills`, and, when the Codex CLI is installed, plugins and marketplaces through it. A profile plugin it installed for one repo gets `enabled = false` at user level, kept so on every sync. In a repo, `init` and `profile` add sections to `.codex/config.toml` (never changing yours) and link skills between `.claude/skills` and `.agents/skills` for the repo's agents (never to a folder outside the repo); in a Codex-only repo they write nothing for Claude Code. `loadout configure new skill --to repo` writes one new skill folder (in a Codex-only repo in `.agents/skills`) and its link, and refuses rather than overwrite. The repo's agents come from its `.loadout.json` ([ADR 0030](../adr/0030-repo-files-follow-the-repos-agents.md)). Codex reads a repo's `.codex/config.toml` only in a project you trust; trusting it is your step, and loadout never trusts a project. Adopt's "remove", "global" and "project" for a Codex-only server run `codex mcp remove` after saving `config.toml` in the backup. 
- VS Code, only when you ask: with `bootstrap --vscode-path` (or a yes in a terminal), a `# loadout PATH` block in `~/.vscode-server/server-env-setup`, which VS Code's Remote-WSL server runs as a shell script when it starts; with `--vscode-wsl` (or a yes), the setting `chatgpt.runCodexInWindowsSubsystemForLinux` in VS Code's Windows user `settings.json` (a text edit; every other byte stays). Both are backed up first, or recorded as created when loadout creates the file, so `loadout restore` undoes them ([ADR 0034](../adr/0034-vscode-extension-binaries-and-vscode-fixes.md), [Use loadout with VS Code](../how-to/vscode.md)). `loadout check` only reads VS Code's settings and extension folders.
- `~/.claude/CLAUDE.md`, only if you pick it in adopt's `review` group (or pass `--groups review`): its content moves into `<personal>/rules/me.md`, the original goes into the backup, and the file keeps a one-line marker (`adopt.migrate_claude_md`).
- **Permissions.** Three things approve or rewrite tool calls without a prompt: the plugin hook `serena-hooks auto-approve` approves Serena's MCP tools (`mcp__plugin_loadout_serena__.*`), the plugin hook `rtk hook claude` rewrites every Bash command into rtk's form, and `settings.base.json` pre-approves `Bash(loadout advisor-mark:*)`. In Codex only `rtk hook codex` rewrites shell commands, after you approve the hooks in `/hooks`; nothing auto-approves Serena's tools there (Serena documents no such hook for Codex), so Codex asks as for any MCP tool ([ADR 0028](../adr/0028-serena-codex-hooks-in-hooks-json.md)). See [Hooks](../reference/hooks.md#hooks-of-the-loadout-plugin).

It does not touch:

- Your `~/.claude/CLAUDE.md`, apart from the adopt choice above. Rules are linked as a folder instead.
- Settings keys it does not manage, unless you ask (`adopt`).
- Project files, except through `loadout init`, `loadout profile`, `loadout configure new skill --to repo` and a profile that `loadout adopt` applies to a repo, and never in a repo whose `.loadout.json` says `"manage": false`. Each shows a plan and asks first, and saves a copy of every file it changes, so `loadout restore` undoes it ([Repo writes](../reference/cli.md#repo-writes)). Scaffold files are never overwritten. Profiles merge into the repo's `.claude/settings.json` and `.mcp.json` (three-way against a record in `.loadout.json`: a value someone changed is kept unless they say yes, and the record holds a secret-looking value only as a hash; [ADR 0031](../adr/0031-repo-profile-entries-merge-three-way.md)) and may run the profile's `commands`, which restore cannot undo. The session hook and the daily sync never write repo files.
- VS Code itself: loadout never installs or updates an extension, trusts a workspace, or approves hooks for one ([What loadout does not do here](../how-to/vscode.md#what-loadout-does-not-do-here)).
- Your session transcripts. Only `loadout usage` reads them (also when the `/loadout:usage` skill runs it), when you run it, locally; it prints counts, never their content, and changes nothing.
- Your Claude login or claude.ai connectors. It does not change them. `loadout check` reads only the connector names in `~/.claude.json` (`claudeAiMcpEverConnected`) to warn about a plugin that duplicates one, and prints only names from the kit's catalog.

Items you own that loadout removes or replaces are moved to a backup first. The routine sync of what the kit itself manages (managed settings keys, your personal MCP servers) is not backed up, and neither is the shell startup file bootstrap appends to on Linux and macOS; your personal layer's git history is the record. Repo writes are the exception: they are previewed and backed up. See [What restore does not undo](../how-to/undo-and-restore.md#what-restore-does-not-undo).

## Programs and repo files

- **Program lookup.** loadout resolves external programs (`git`, `claude`, `codex`, installers) only from absolute `PATH` entries, never from the current folder or a relative entry. On Windows this also rules out the current-folder lookup `cmd` would do. One addition: when `claude` or `codex` is not on `PATH`, loadout runs the binary of VS Code's extension of that agent on this side, by its absolute path: the one bundled in the extension folder, or for Codex the file the extension's `chatgpt.cliExecutable` setting names (from WSL, never a Windows window's copy). You then trust that extension as you would trust the CLI ([ADR 0033](../adr/0033-codex-for-the-vscode-extension-without-its-cli.md), [ADR 0034](../adr/0034-vscode-extension-binaries-and-vscode-fixes.md)).
- **Repo symlinks.** `init` and `profile` never write through a symlink that leads out of the repo, and never run `git init` through a `.git` symlink. A skipped file is reported and the command exits 1.
- **Restore** trusts only backups under `~/.local/state/loadout/backups`, copies only from a backup's own `files/` folder, and replays only the undo commands loadout records ([details](../how-to/undo-and-restore.md)).
- **Codex type-check hook.** For Rust repos its `cargo check` runs the build scripts and procedural macros of the repo you edit. That is normal cargo behaviour; do not edit untrusted repos with the hook on.

## Backups and restore

Backups go to `~/.local/state/loadout/backups/loadout-<timestamp>` with a manifest of undo steps, and `loadout restore` replays them. They can hold old configs and secrets. Which commands make them, their file modes, and what restore does not undo: [Undo what loadout changed](../how-to/undo-and-restore.md).

## Secrets

Never put keys into config files.

- **Where they live.** `~/.config/loadout/secrets.env`, created by bootstrap from `secrets.env.example`, mode 600. Entries are `NAME='value'` in single quotes. A `'` inside a value is written `'\''`, so the shell never runs part of a value.
- **MCP setup.** Claude Code gets each server from `claude mcp add-json`, which puts the configuration on the command line (below). Codex gets owned `[mcp_servers.*]` sections in `config.toml`, written to the file instead, with secrets as `env_vars` names that Codex reads from its environment.
- **How they are loaded.** Bootstrap adds a block to each existing `.bashrc` and `.zshrc` and to the startup file of your `$SHELL` (bash or zsh), and on Windows to both PowerShell profiles. fish and other shells get no secrets loader; load `secrets.env` there yourself, or (simplest) start your agent from bash or zsh. Only an agent started from such a shell sees them, so start Codex from one too. On Windows the execution policy must allow profiles: see [Troubleshooting](../how-to/troubleshooting.md#windows); WSL avoids this and is the recommended setup on Windows ([Pick your setup](../how-to/setups.md#recommended-setups)).
- **How configs refer to them.** MCP configs use `${NAME}`.
- **On the command line.** `claude mcp add-json` takes a server's configuration as an argument, so while it runs, other users of the machine can see it in the process list. loadout passes each configuration as it is stored: one that refers to `${NAME}` shows only the name, one that still holds a plaintext value shows that value. That happens for a plaintext value in your personal `mcp.json` (applied by bootstrap and the daily sync), for `loadout restore` re-adding a server with its original configuration, and for the rollback that re-adds a server's previous configuration when an update fails, including during `loadout adopt`'s secret move. On a shared machine, keep every secret in `secrets.env`.
- **Finding plaintext keys.** `loadout adopt` detects secrets in plain text and does not print them (`secrets.redact` masks what its patterns recognise in printed lines). The scan runs on a Codex-only machine too. With Codex on it also reports secrets in your own `[mcp_servers.*]` tables of `~/.codex/config.toml` (report only, the value stays hidden: move it to `secrets.env` and name it in `env_vars`, or for a header in `env_http_headers`; a secret in `args` or the URL has no such field, so pass it another way); on a Codex-only machine it also scans your personal `mcp.json`. For Claude Code it can move secrets in the `env` and `headers` of user-scope servers in `~/.claude.json` to `secrets.env`. It only reports secrets in a server's `args` and URL query strings, in project-scoped servers, `~/.claude/.mcp.json`, your personal `mcp.json` and the `env` block of `settings.json`, so you can move them by hand.
- **The secret guard.** When you record your own tools into the personal layer, a stricter guard applies (values you set yourself with `loadout configure set pref` are not checked): nothing that looks like a secret or a private file is written, and the guard refuses when it cannot tell. The rules are in [Handle your own tools](../how-to/your-own-tools.md#secret-guard). The reasoning is in [0006](../adr/0006-secrets-in-secrets-env.md) and [0018](../adr/0018-secret-guard-fails-closed.md).

Your personal layer is meant to be a private git repo. The commit offer after `loadout configure` and `adopt` refuses while a `*.env` file or another private file would be committed.

## The trust boundary

Your personal layer can run code on every machine you sync it to. It can hold hooks, skills and MCP server commands, and the daily pull brings changes in without a prompt. Treat the personal repo like a dotfiles repo: private, with a strong login on the host. The same holds for the kit repo. Whoever can push to it reaches every machine that follows it.

For a team, use a fork of the kit that you control and point your clone (or `LOADOUT_ROOT`) at it. Changes then reach colleagues only after you review them.

## Opting out

- **Marketplace auto-update.** Set `"autoUpdate": false` for a marketplace in your personal `settings.json`, for example `{"extraKnownMarketplaces": {"impeccable": {"autoUpdate": false}}}`. Codex's automatic plugin refresh after a pull honours it too: it leaves that marketplace as it is (no upgrade, and installed plugins are not re-installed; a missing plugin is still installed). `loadout update` is the explicit command and updates every marketplace. `LOADOUT_NO_AUTO_PULL=1` turns off the whole daily pull.
- **The daily pull.** Set `LOADOUT_NO_AUTO_PULL=1`. Details: [The daily sync](../reference/state-and-sync.md#the-daily-sync).
- **Binary updates.** Nothing to turn off: they only happen when you run `loadout update`.

See also [Architecture](architecture.md) for the data flow and the daily sync.
