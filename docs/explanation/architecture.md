# Architecture

loadout has three parts: the kit repo (shared), your personal layer (yours) and the configuration folders of your agents (where Claude Code and Codex read theirs). The CLI merges the first two into the third and keeps it current. Which agents it serves is your choice ([Use loadout with Codex](../how-to/codex.md#switch-it-on)); one stays on. Where a page says "your agent", it holds for both. A repo is a fourth, shared place: loadout keeps no list of repos, and each repo names its own agents in a committed `.loadout.json` ([ADR 0030](../adr/0030-repo-files-follow-the-repos-agents.md)). Which agents, surfaces and bootstrap flags fit your machine: [Pick your setup](../how-to/setups.md#recommended-setups). Where each module of the CLI lives: [Modules](../reference/modules.md).

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../diagrams/architecture-overview.dark.svg">
  <img alt="For Claude Code: Claude Code installs the kit's plugin and the kit's rules are linked into ~/.claude/rules/loadout. Your personal layer's rules, skills and hooks are linked into ~/.claude, and its mcp.json is added with claude mcp add-json. settings.base.json and your settings.json go through a three-way merge, which reads and rewrites a snapshot and writes ~/.claude/settings.json. For Codex: loadout installs and refreshes the same plugins (only with the Codex CLI), copies the kit's rules and your personal rules into its block in ~/.codex/AGENTS.md, links your skills into ~/.agents/skills, writes Serena's documented hooks as owned entries in ~/.codex/hooks.json, and writes your MCP servers, effort, notifications and plugin switches as owned sections of ~/.codex/config.toml. The VS Code extensions of both agents read these same folders. For a repo: the kit's profiles go through repo writes (a plan, your yes, a backup) into the repo's .claude, .mcp.json, .codex and .agents/skills files, merged three-way against the record in the repo's .loadout.json." src="../diagrams/architecture-overview.light.svg">
</picture>

<sub>[Source](../diagrams/architecture-overview.mmd)</sub>

## The parts

**The kit repo** (this repository) holds what is the same for everybody:

- `plugins/loadout/`: the plugin with hooks, two MCP servers (Serena and codebase-memory) and the skills. The repo is also a plugin marketplace, so Claude Code installs and updates the plugin itself.
- `rules/`: how Claude should use the tools. `~/.claude/rules/loadout` is a link to this folder.
- `catalog.json`: what is good, superseded or optional, and how to install and update each tool. See [Catalog format](../reference/catalog-format.md).
- `profiles/`: per-project add-ons. See [Profile format](../reference/profile-format.md).
- `settings.base.json` and `preferences.json`: the settings loadout manages and the working preferences it asks about.
- `cli/loadout/`: the CLI, Python standard library only. See the [CLI reference](../reference/cli.md).

**The personal layer** (`~/.config/loadout/personal`, ideally a private git repo) holds what is yours: `rules/me.md`, `settings.json` overrides, `mcp.json`, your skills, hooks and profiles. It is linked into `~/.claude/rules/personal`, `~/.claude/skills` and `~/.claude/hooks/personal`. See [Personal layer](../reference/personal-layer.md).

**Your agents' configuration** is owned by the agent and by you. loadout adds links and merges or writes only what it recorded as its own; the rest stays yours.

| | Claude Code | Codex |
|---|---|---|
| Folder | `~/.claude` | `$CODEX_HOME`, else `~/.codex`; skills in `~/.agents/skills` |
| Kit rules | `~/.claude/rules/loadout` is a link to `rules/` | a marked block in `AGENTS.md` (`<!-- loadout:start -->` ... `<!-- loadout:end -->`) |
| Your personal rules (`rules/*.md`, such as `me.md`) | the folder is linked as `~/.claude/rules/personal` | copied into the same block |
| Your skills | linked into `~/.claude/skills` | linked into `~/.agents/skills` |
| Your hooks | linked into `~/.claude/hooks/personal` | not linked |
| Your MCP servers | `claude mcp add-json` (user scope) | owned `[mcp_servers.*]` sections in `config.toml`, secrets as `env_vars` names; loadout also owns a `serena` section unless you have your own Serena server, and a `context7` section when the Context7 plugin is on; Serena's hooks are owned entries in `hooks.json` |
| Settings | three-way merge into `settings.json` | effort and notifications as `model_reasoning_effort` and `tui.notifications` in `config.toml`; for plugins a project profile installed, a `plugins.<id>.enabled` switch that keeps them off at user level |
| Plugins | the kit marketplace; Claude Code installs and updates them | loadout installs and refreshes the same plugins through the Codex CLI; with only VS Code's Codex extension, none (it loads no plugins; [Codex in VS Code without the CLI](../how-to/vscode.md#codex-in-vs-code-without-the-cli)) |
| Your own text | `~/.claude/CLAUDE.md` is not edited, unless you ask adopt to move its content into your personal layer | the rest of `AGENTS.md` is not edited; `AGENTS.override.md` would shadow the block (`loadout check` warns) |

What the Codex side maps, and what stays different, is in [Use loadout with Codex](../how-to/codex.md).

## VS Code extensions

The Claude Code extension and VS Code's Codex extension are a surface of the same agent, not a third target. They read the same folders as the CLIs (`~/.claude` and `~/.claude.json`; `~/.codex` and `~/.agents/skills`), so loadout sets up no folder of their own for them ([ADR 0032](../adr/0032-vscode-extensions-are-a-surface-of-an-agent.md)). What loadout does around them:

- **Detection, read-only.** `vscode.py` finds the extensions on this side: a local install, a Remote-WSL server (`~/.vscode-server`), and from WSL a Windows window's install. `loadout check` reports one row per extension and window type, all warnings.
- **Codex extension mode.** With VS Code's Codex extension and no Codex CLI on `PATH`, loadout still writes the rules block, `config.toml`, Serena's hooks and the skills for it. It skips plugins, because the extension loads none, and it runs the extension's own `codex` for its `codex mcp` commands. The extension has no `/hooks` ([ADR 0033](../adr/0033-codex-for-the-vscode-extension-without-its-cli.md)). The Codex CLI next to the extension is the recommended setup.
- **The extensions' binaries as runners.** With no `claude` on `PATH`, loadout's `claude plugin` and `claude mcp` commands run the binary bundled in the Claude Code extension on this side (`runner.FALLBACK`; never a Windows window's copy from WSL). `which` and `have` still answer only for `PATH` ([ADR 0034](../adr/0034-vscode-extension-binaries-and-vscode-fixes.md)).
- **VS Code files only when asked.** `bootstrap --vscode-wsl` sets the Codex extension's WSL switch in VS Code's Windows user settings, and `--vscode-path` adds a PATH block to `~/.vscode-server/server-env-setup`; each takes a flag or a yes, and makes a backup first (or records a file it creates), so `loadout restore` undoes it ([ADR 0034](../adr/0034-vscode-extension-binaries-and-vscode-fixes.md)).

What each extension sees, what it lacks, and the fixes: [Use loadout with VS Code](../how-to/vscode.md).

## Repos

A repo is shared, so loadout keeps no list of repos and writes into one only when you run `loadout init`, `loadout profile` or `loadout configure new skill --to repo` there (or let `loadout adopt` apply a profile to it).

- **`.loadout.json`** (`repo_config.py`) is committed. It names the repo's agents, so a Codex-only repo gets no Claude Code files; `"manage": false` keeps loadout out; and it holds the record of what each profile wrote ([ADR 0030](../adr/0030-repo-files-follow-the-repos-agents.md)).
- **Repo writes are a plan** (`repo_writes.py`): every change is collected, shown, and applied after your yes, with a backup that `loadout restore` replays. Only a `run` step (a profile's `commands`, `git init`) cannot be undone, and the plan says so ([Repo writes](../reference/cli.md#repo-writes)).
- **Profile entries merge three-way** (`repo_merge.py`) against the record, so a re-run keeps a value someone changed in the repo unless they say yes. The record keeps a secret-looking value only as a hash ([ADR 0031](../adr/0031-repo-profile-entries-merge-three-way.md)).
- **`loadout explain FILE`** shows which entries of a repo file loadout wrote, from which profile, and whether each is unchanged ([loadout explain](../reference/cli.md#loadout-explain)).

The session hook and the daily sync never write repo files.

## loadout's own files

loadout keeps its own state and backups in one folder of its own, `~/.local/state/loadout` (or `$XDG_STATE_HOME/loadout`), on every OS and for every user. The state is what makes a safe re-run possible: the snapshot of what the settings merge applied, the record of the entries loadout owns in Codex's files, your `leave` decisions and the sync's bookkeeping. The backups are what makes every change undoable. Both belong to this machine and are never synced. The folder does not depend on Claude Code being on, so a Codex-only machine has no `~/.claude` ([ADR 0025](../adr/0025-state-in-xdg-state-home.md)).

Older versions kept both in `~/.claude`. loadout moves them in two steps, copy now and delete the old copy later, because an older loadout run or the hooks of a Claude Code session that has not reloaded its plugins can still write the old place; deleting at once could lose what they write. The folders are listed in [State folders](../reference/state-and-sync.md#state-folders); the exact rules of the move, and what `loadout check` reports while it is unfinished, are in [The move out of ~/.claude](../reference/state-and-sync.md#the-move-out-of-claude).

## The settings merge

This part is about Claude Code. Codex has no settings file that loadout merges; it writes only the keys it owns (see [The parts](#the-parts)). The merge combines the kit's `settings.base.json`, your personal `settings.json` and the snapshot of what was applied last time. Because it has the snapshot, it can tell a value you changed from a value the kit changed, and it can tell a hook you deleted from a hook it never added. The kit manages only the keys it declares, so everything else in your `settings.json` survives. The exact rules, including the per-hook merge, are in [Settings merge](../reference/settings-merge.md).

## The daily sync

loadout keeps a machine current without a scheduler of its own: the start of an agent session is the trigger. The plugin's session hook prints the notices queued since the last session and, when the daily pull or the weekly check is due, starts `loadout maintenance` in the background. The session never waits for it, and nothing it does can break the session: problems become notices for the next one.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../diagrams/architecture-daily-sync.dark.svg">
  <img alt="When a Claude Code or Codex CLI session starts, hook-session-start returns queued notices at once and, when due, starts maintenance in the background without making the session wait. Maintenance runs one at a time: daily it runs git pull --ff-only on the kit and personal repos (skipping a checkout with uncommitted changes or untracked files) and, after new commits, merges settings and relinks skills and hooks for Claude Code and refreshes the rules block, config, hooks and skills for Codex, plugins only with the Codex CLI (each only when that agent is on, Codex also only when it is usable); weekly it checks tool versions without installing anything. It queues notices for the next session." src="../diagrams/architecture-daily-sync.light.svg">
</picture>

<sub>[Source](../diagrams/architecture-daily-sync.mmd)</sub>

The pull is fast-forward only and skips a checkout with local changes, so it never overwrites your work. Only a pull that brought new commits makes the sync re-apply anything, and only for the agents that are on. The weekly check only reports updates; installing them is `loadout update`, after a yes. In Claude Code the sync leaves plugin updates to Claude Code itself, which updates the kit's marketplaces; for Codex, loadout refreshes the plugins after a pull, when the Codex CLI is installed ([0024](../adr/0024-codex-parity-update-model.md)).

The hook runs in Claude Code and in the Codex CLI; VS Code's Codex extension without the Codex CLI does not start the sync ([At each session start](../reference/state-and-sync.md#at-each-session-start)).

Each step, the locks, the timestamps and `LOADOUT_NO_AUTO_PULL=1` are in [The daily sync](../reference/state-and-sync.md#the-daily-sync). Whoever can push to the kit or your personal layer reaches every machine that follows it; see [the trust boundary](security-and-trust.md#the-trust-boundary).

## Why it is built this way

The main decisions, in short. Each has a decision record in [`docs/adr/`](../adr/README.md) with the alternatives that were considered.

- **A kit and a personal repo** ([0001](../adr/0001-kit-repo-plus-personal-repo.md)). The shared part can be updated for everybody while your own part stays yours and syncs through your own git. Without the split, either every user forks the kit or personal settings leak into it.
- **The kit is a plugin marketplace** ([0002](../adr/0002-kit-is-a-plugin-marketplace.md)). Claude Code already knows how to install, enable and update plugins. loadout reuses that instead of copying files into `~/.claude` itself.
- **Three-way settings merge** ([0003](../adr/0003-three-way-settings-merge.md)). A plain overwrite would destroy your own settings. A plain merge cannot tell whether you or the kit changed a value. The snapshot makes both safe and lets you delete a kit hook without it coming back.
- **Rules are linked as folders** ([0004](../adr/0004-rules-linked-as-directories.md)). Linking `rules/` leaves `~/.claude/CLAUDE.md` yours, and a pull updates the rules without touching a file you own.
- **Repo files follow the repo's agents** ([0030](../adr/0030-repo-files-follow-the-repos-agents.md), [0031](../adr/0031-repo-profile-entries-merge-three-way.md)). A repo is shared, so what loadout writes there depends on the agents the repo names, not on yours, and a re-run never overwrites a teammate's change without a yes.
- **VS Code extensions are a surface of an agent** ([0032](../adr/0032-vscode-extensions-are-a-surface-of-an-agent.md), [0033](../adr/0033-codex-for-the-vscode-extension-without-its-cli.md), [0034](../adr/0034-vscode-extension-binaries-and-vscode-fixes.md)). They read the agents' folders, so one setup serves the CLI and the extension; loadout adds only detection, the extension mode for Codex, the bundled binaries as runners, and VS Code fixes you ask for.

All decisions, including the ones not summarised here, are in the [ADR index](../adr/README.md).

## Other agents

Claude Code and Codex are the two supported agents, each a target of the same kit and personal layer; the decision is [0022](../adr/0022-codex-as-a-second-target.md). Other agents (Gemini CLI, Cursor) are not supported; the same pattern would add them as further targets.
