# Architecture

loadout has three parts: the kit repo (shared), your personal layer (yours) and `~/.claude` (where Claude Code reads its configuration). The CLI merges the first two into the third and keeps it current.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../diagrams/architecture-overview.dark.svg">
  <img alt="For Claude Code: Claude Code installs the kit's plugin and the kit's rules are linked into ~/.claude/rules/loadout. Your personal layer's rules, skills and hooks are linked into ~/.claude, and its mcp.json is added with claude mcp add-json. settings.base.json and your settings.json go through a three-way merge, which reads and rewrites a snapshot and writes ~/.claude/settings.json. For Codex: loadout installs and refreshes the same plugins, copies the kit's rules and your me.md into its block in ~/.codex/AGENTS.md, links your skills into ~/.agents/skills, and writes your MCP servers, effort and notifications as owned sections of ~/.codex/config.toml." src="../diagrams/architecture-overview.light.svg">
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

**`~/.claude`** is owned by Claude Code and by you. loadout adds links and merges its own keys into `settings.json`. It does not edit `~/.claude/CLAUDE.md`, unless you ask adopt to move its content into your personal layer. Your other settings stay.

**Machine-local state** (`~/.claude/.loadout/`) records what the merge last applied, your `leave` decisions and the maintenance timestamps. It is not synced.

## The settings merge

The merge combines the kit's `settings.base.json`, your personal `settings.json` and the snapshot of what was applied last time. Because it has the snapshot, it can tell a value you changed from a value the kit changed, and it can tell a hook you deleted from a hook it never added. The kit manages only the keys it declares, so everything else in your `settings.json` survives. The exact rules, including the per-hook merge, are in [Settings merge](../reference/settings-merge.md).

## The daily sync

At each session start the plugin runs `loadout hook-session-start`. It prints queued notices and, when the daily pull or the weekly check is due, starts `loadout maintenance` as a detached process. The session never waits for it.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../diagrams/architecture-daily-sync.dark.svg">
  <img alt="When a session starts, hook-session-start returns queued notices at once and, when due, starts maintenance in the background without making the session wait. Maintenance runs one at a time: daily it runs git pull --ff-only on the kit and personal repos (skipping a checkout with uncommitted changes) and, after new commits, merges settings and relinks skills and hooks for Claude Code and refreshes plugins, config and skills for Codex (each only when that agent is on, Codex also only when it is usable); weekly it checks tool versions without installing anything. It queues notices for the next session." src="../diagrams/architecture-daily-sync.light.svg">
</picture>

<sub>[Source](../diagrams/architecture-daily-sync.mmd)</sub>

**Plugin updates.** The sync does not run `claude plugin update`. `settings.base.json` sets `"autoUpdate": true` on the marketplaces it declares, so Claude Code updates those plugins itself (after a random delay in a running session; then `/reload-plugins`). After a pull, the sync refreshes the Codex plugins. `loadout update` updates the enabled plugins at once, in Claude Code and Codex, after a yes.

Details, from `maintenance._maintain`:

- One maintenance run at a time: a lock file in the state folder, taken over only after an hour.
- The pull is `git pull --ff-only` on the kit and on the personal layer (when each is a git checkout), at most once a day, with git's terminal and credential prompts turned off (`maintenance.pull_if_clean`). It is skipped for a checkout with uncommitted changes.
- With `LOADOUT_NO_AUTO_PULL=1` the pull and the re-apply are skipped; the weekly version check still runs.
- Settings, personal MCP servers and links (skills, hook scripts, and copies in copy mode) are re-applied only when a pull brought new commits. Errors become a notice for the next session instead of a crash.
- The next session runs the pulled `loadout` code and the plugin's hooks. Whoever can push to the kit or your personal layer reaches every machine that follows it; see [the trust boundary](security-and-trust.md#the-trust-boundary).
- Plugins newly enabled through the personal layer are installed by Claude Code at its next start, not by this job ([0015](../adr/0015-claude-code-installs-synced-plugins.md)).
- The weekly check compares installed and latest versions (through mise when it manages the tool, so its pins and release-age rules count). It queues "updates available, run `loadout update`". It never installs.

Plugins are not part of this loop: Claude Code updates them through the marketplace.

## Why it is built this way

The main decisions, in short. Each has a decision record in [`docs/adr/`](../adr/README.md) with the alternatives that were considered.

- **A kit and a personal repo** ([0001](../adr/0001-kit-repo-plus-personal-repo.md)). The shared part can be updated for everybody while your own part stays yours and syncs through your own git. Without the split, either every user forks the kit or personal settings leak into it.
- **The kit is a plugin marketplace** ([0002](../adr/0002-kit-is-a-plugin-marketplace.md)). Claude Code already knows how to install, enable and update plugins. loadout reuses that instead of copying files into `~/.claude` itself.
- **Three-way settings merge** ([0003](../adr/0003-three-way-settings-merge.md)). A plain overwrite would destroy your own settings. A plain merge cannot tell whether you or the kit changed a value. The snapshot makes both safe and lets you delete a kit hook without it coming back.
- **Rules are linked as folders** ([0004](../adr/0004-rules-linked-as-directories.md)). Linking `rules/` leaves `~/.claude/CLAUDE.md` yours, and a pull updates the rules without touching a file you own.

See the [decision records](../adr/README.md) for these and for the others: catalog ([0005](../adr/0005-catalog-as-source-of-tool-knowledge.md)), secrets ([0006](../adr/0006-secrets-in-secrets-env.md)), scoping ([0007](../adr/0007-tiered-scoping-with-profiles.md)), code intelligence ([0008](../adr/0008-code-intelligence-routed-by-rule.md)), design tooling ([0009](../adr/0009-design-tooling-frontend-design-and-impeccable.md)), documentation ([0010](../adr/0010-docs-as-single-source-of-truth.md)), binary updates ([0011](../adr/0011-tool-binaries-notice-and-deliberate-update.md)) and backups ([0012](../adr/0012-destructive-actions-dry-run-confirm-backup.md)).

## Codex and other agents

loadout can also set up OpenAI's Codex CLI from the same kit and personal layer: the rules as a block in `~/.codex/AGENTS.md`, every plugin you enabled for Claude Code through the same marketplace, your MCP servers, skills and settings, and Codex-only hooks with a type check after each edit. The code is `cli/loadout/codex.py`; what is mapped and what stays different is in [Use loadout with Codex](../how-to/codex.md); the decision is [0022](../adr/0022-codex-as-a-second-target.md). Other agents (Gemini CLI, Cursor) are not supported; the same pattern would add them as further targets.

