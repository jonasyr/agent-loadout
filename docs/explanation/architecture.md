# Architecture

loadout has three parts: the kit repo (shared), your personal layer (yours) and the configuration folders of your agents (where Claude Code and Codex read theirs). The CLI merges the first two into the third and keeps it current. Which agents it serves is your choice ([Use loadout with Codex](../how-to/codex.md#switch-it-on)); one stays on. Where a page says "your agent", it holds for both.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../diagrams/architecture-overview.dark.svg">
  <img alt="For Claude Code: Claude Code installs the kit's plugin and the kit's rules are linked into ~/.claude/rules/loadout. Your personal layer's rules, skills and hooks are linked into ~/.claude, and its mcp.json is added with claude mcp add-json. settings.base.json and your settings.json go through a three-way merge, which reads and rewrites a snapshot and writes ~/.claude/settings.json. For Codex: loadout installs and refreshes the same plugins, copies the kit's rules and your personal rules (rules/*.md, such as me.md) into its block in ~/.codex/AGENTS.md, links your skills into ~/.agents/skills, and writes your MCP servers, the kit's Serena (and Context7) servers, effort and notifications as owned sections of ~/.codex/config.toml." src="../diagrams/architecture-overview.light.svg">
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
| Your MCP servers | `claude mcp add-json` (user scope) | owned `[mcp_servers.*]` sections in `config.toml`, secrets as `env_vars` names; loadout also owns a `serena` section, and a `context7` section when the Context7 plugin is on |
| Settings | three-way merge into `settings.json` | effort and notifications as `model_reasoning_effort` and `tui.notifications` in `config.toml`; for plugins a project profile installed, a `plugins.<id>.enabled` switch that keeps them off at user level |
| Plugins | the kit marketplace; Claude Code installs and updates them | loadout installs and refreshes the same plugins through the `codex` CLI |
| Your own text | `~/.claude/CLAUDE.md` is not edited, unless you ask adopt to move its content into your personal layer | the rest of `AGENTS.md` is not edited; `AGENTS.override.md` would shadow the block (`loadout check` warns) |

What the Codex side maps, and what stays different, is in [Use loadout with Codex](../how-to/codex.md).

## loadout's own files

Two folders belong to loadout itself, for every user, Codex-only included. They sit in `$XDG_STATE_HOME/loadout` (an absolute path), or `~/.local/state/loadout` when that is not set, on every OS. The path does not depend on whether Claude Code is on (`paths.state_dir`, `paths.backups_root`), so a Codex-only machine has no `~/.claude`. See [ADR 0025](../adr/0025-state-in-xdg-state-home.md).

- `~/.local/state/loadout/`: machine-local state. It records what the merge last applied (the snapshot), which `config.toml` entries loadout owns (`codex-config.json`), your `leave` decisions, queued notices and the maintenance timestamps. It is not synced.
- `~/.local/state/loadout/backups/`: one `loadout-<timestamp>` folder per change that moved or replaced something you own, with a manifest of undo steps. See [Undo what loadout changed](../how-to/undo-and-restore.md).

Older versions kept both folders in `~/.claude`. At the start of every loadout command (and of the session hook) loadout moves them once, under a lock: all of `~/.claude/.loadout`, but from `~/.claude/backups` only its own `loadout-<timestamp>` folders (Claude Code keeps its own `.claude.json` copies there, and they stay); another run waits up to 10 seconds for it. Where the new place already has an entry of the same name, the new one wins, the old one stays in `~/.claude` and is named once, and `loadout check` warns (row `loadout state`) until you delete it by hand. If the move did not finish, commands that change things stop with exit code 1 and say why; `kit-path`, `check` and `restore` still run, the session hook exits quietly, and the next run finishes the move. If an entry can never be moved (for example a file owned by root after a `sudo` run), move or delete it by hand; `loadout check` names it. Files an older plugin version still writes from an open Claude Code session are handled quietly: one the new place lacks moves in; otherwise the old one stays for that session and goes once it has been untouched for a day. An empty `~/.claude` is removed afterwards only when Claude Code is off.

## The settings merge

This part is about Claude Code. Codex has no settings file that loadout merges; it writes only the keys it owns (see [The parts](#the-parts)). The merge combines the kit's `settings.base.json`, your personal `settings.json` and the snapshot of what was applied last time. Because it has the snapshot, it can tell a value you changed from a value the kit changed, and it can tell a hook you deleted from a hook it never added. The kit manages only the keys it declares, so everything else in your `settings.json` survives. The exact rules, including the per-hook merge, are in [Settings merge](../reference/settings-merge.md).

## The daily sync

At each session start the plugin runs `loadout hook-session-start`. It prints queued notices and, when the daily pull or the weekly check is due, starts `loadout maintenance` as a detached process. The session never waits for it. Both agents run the same hook through the plugin: Claude Code from `hooks/hooks.json`, Codex from `hooks/codex.json` (after you approve the hooks in `/hooks`).

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../diagrams/architecture-daily-sync.dark.svg">
  <img alt="When a session starts, hook-session-start returns queued notices at once and, when due, starts maintenance in the background without making the session wait. Maintenance runs one at a time: daily it runs git pull --ff-only on the kit and personal repos (skipping a checkout with uncommitted changes or untracked files) and, after new commits, merges settings and relinks skills and hooks for Claude Code and refreshes plugins, config and skills for Codex (each only when that agent is on, Codex also only when it is usable); weekly it checks tool versions without installing anything. It queues notices for the next session." src="../diagrams/architecture-daily-sync.light.svg">
</picture>

<sub>[Source](../diagrams/architecture-daily-sync.mmd)</sub>

**Plugin updates.** In Claude Code the sync does not run `claude plugin update`. `settings.base.json` sets `"autoUpdate": true` on the marketplaces it declares, so Claude Code updates those plugins itself (after a random delay in a running session; then `/reload-plugins`). For Codex, loadout refreshes the plugins in the Codex step below, after a pull that brought commits. `loadout update` updates the enabled plugins at once, in Claude Code and Codex, after a yes. How both agents' plugins are updated is decided in [0024](../adr/0024-codex-parity-update-model.md).

Details, from `maintenance._maintain`:

- One maintenance run at a time: a lock file in the state folder, taken over only after an hour.
- The pull is `git pull --ff-only` on the kit and on the personal layer (when each is a git checkout), at most once a day, with git's terminal and credential prompts turned off (`maintenance.pull_if_clean`). It is skipped for a checkout with uncommitted changes or untracked files.
- With `LOADOUT_NO_AUTO_PULL=1` the pull and the re-apply are skipped; the weekly version check still runs.
- Only when a pull brought new commits does the sync re-apply anything (`maintenance._maintain`). Errors become a notice for the next session instead of a crash.
  - **Claude Code** (when it is on): settings, personal MCP servers and links (skills, hook scripts, and copies in copy mode).
  - **Codex** (when it is on and usable, meaning a supported `codex` is on `PATH`): `codex.apply_all(refresh=True)` refreshes the plugins, the `AGENTS.md` block, `config.toml` entries and skill links, then the drift check (when both agents are on, since it compares them) queues a notice for anything that no longer matches. Replaced or edited files go to a backup first.
- The next session runs the pulled `loadout` code and the plugin's hooks. Whoever can push to the kit or your personal layer reaches every machine that follows it; see [the trust boundary](security-and-trust.md#the-trust-boundary).
- Plugins newly enabled through the personal layer are installed by Claude Code at its next start, not by this job ([0015](../adr/0015-claude-code-installs-synced-plugins.md)).
- The weekly check compares installed and latest versions (through mise when it manages the tool, so its pins and release-age rules count). It queues "updates available, run `loadout update`". It never installs.

## Why it is built this way

The main decisions, in short. Each has a decision record in [`docs/adr/`](../adr/README.md) with the alternatives that were considered.

- **A kit and a personal repo** ([0001](../adr/0001-kit-repo-plus-personal-repo.md)). The shared part can be updated for everybody while your own part stays yours and syncs through your own git. Without the split, either every user forks the kit or personal settings leak into it.
- **The kit is a plugin marketplace** ([0002](../adr/0002-kit-is-a-plugin-marketplace.md)). Claude Code already knows how to install, enable and update plugins. loadout reuses that instead of copying files into `~/.claude` itself.
- **Three-way settings merge** ([0003](../adr/0003-three-way-settings-merge.md)). A plain overwrite would destroy your own settings. A plain merge cannot tell whether you or the kit changed a value. The snapshot makes both safe and lets you delete a kit hook without it coming back.
- **Rules are linked as folders** ([0004](../adr/0004-rules-linked-as-directories.md)). Linking `rules/` leaves `~/.claude/CLAUDE.md` yours, and a pull updates the rules without touching a file you own.

All decisions, including the ones not summarised here, are in the [ADR index](../adr/README.md).

## Other agents

Claude Code and Codex are the two supported agents, each a target of the same kit and personal layer; the decision is [0022](../adr/0022-codex-as-a-second-target.md). Other agents (Gemini CLI, Cursor) are not supported; the same pattern would add them as further targets.
