# Personal layer

The personal layer is your own folder of preferences. It is separate from the kit, so the kit can update without touching it. By default it is `~/.config/loadout/personal`. Set `LOADOUT_PERSONAL` to use another folder (all variables: [Environment variables](cli.md#environment-variables)). The code is `cli/loadout/paths.py`, `link.py`, `settings_merge.py`, `personal_mcp.py` and `own.py`.

`loadout bootstrap` clones it from a git URL you give, or creates a starter layer: `settings.json` containing `{}`, plus a `rules/me.md` written from the "about you" questions and the working preferences. Make the folder a private git repo to sync it across machines: [Keep your personal layer in a private git repo](../how-to/personal-repo.md).

## Files

```
<personal>/
├── rules/me.md
├── settings.json
├── mcp.json
├── skills/<name>/
├── skills.json
├── targets.json
├── hooks/
└── profiles/
    ├── NAME.json
    └── skills/<name>/
```

Every file is optional, and a missing file counts as empty. The one exception is `rules/`: `loadout check` reports `link rules/personal` as a failure while `<personal>/rules` does not exist, because loadout only creates that link when its target exists.

| Path | Holds | In Claude Code | In Codex |
|---|---|---|---|
| `rules/me.md` | Who you are and how you like to work. May contain the managed preferences block, see [preferences-format](preferences-format.md#the-managed-block). | Linked into `~/.claude/rules/personal`. Claude Code loads it in every session. | Written, with the kit's rules, into a block between `<!-- loadout:start -->` and `<!-- loadout:end -->` in `~/.codex/AGENTS.md`. Your own text in that file stays as it is. If `AGENTS.override.md` exists there, Codex ignores the block and `loadout check` warns. The block is a copy: it is rewritten by bootstrap, `loadout configure set …`, the daily sync after a pull that brought new commits, and at every session start when a kit rule or a personal rules file changed. So a hand edit of `me.md` or a kit rule reaches Codex at the next session; no command is needed. Your text and its line endings stay byte for byte, and every rewrite first keeps the old file in a backup, so `loadout restore` undoes it. Write your own text outside the markers: when you edit inside the block, the session-start refresh leaves it as you left it and tells you once, and the next `loadout bootstrap` rewrites it. A block from an older loadout that no longer matches is also left until bootstrap or the daily sync rewrites it once. The refresh never creates the file or a block, and it is skipped while another loadout run is setting Codex up (the next session start catches up). |
| `settings.json` | Your overrides of the kit's settings, for example `"effortLevel": "high"` or `"enabledPlugins": {"impeccable@impeccable": false}`. Also the hooks you recorded as global. | Merged with the kit's `settings.base.json` and written into `~/.claude/settings.json`. See [settings-merge](settings-merge.md). | Only two things reach Codex: the effort level (`model_reasoning_effort`) and push notifications (`tui.notifications`), both in `~/.codex/config.toml`. Plugins switched on in its `enabledPlugins` are installed in Codex too (not with only VS Code's Codex extension and no Codex CLI, which loads no plugins). Switching one off (`false`) also switches it off in Codex when Codex has it installed: loadout writes `[plugins."NAME@MARKET"] enabled = false` into `~/.codex/config.toml` as its own key. An existing line is replaced only when loadout wrote it, or when loadout's own `codex plugin add` wrote it (loadout records that right after the install and forgets it once a run sees the plugin uninstalled). Any other line is yours and stays, and so does any change you make to loadout's line, also a later `enabled = true`; `loadout` says "your value" then. To hand a line of yours back, delete it. Every such change is in a backup, so `loadout restore` undoes it. Switching it on again sets loadout's line back to `enabled = true`, only while the plugin is installed. Removing the `false` entry has the same effect for a kit plugin (it falls back to the kit's `true`); for any other plugin it leaves the owned `enabled = false` line in place, so set it to `true` instead. A plugin that is not in your settings is never touched, and without the list of installed plugins nothing is switched. Thinking mode, auto mode, the permission list and hooks have no Codex equivalent and have no effect there. |
| `mcp.json` | `{"mcpServers": {...}}`: extra MCP servers you want everywhere. Secrets are written as `${VAR}`. | Applied as user-scope servers with `claude mcp add-json -s user`. | One `[mcp_servers.NAME]` section each in `~/.codex/config.toml`. A secret becomes the variable's name in `env_vars`, never its value. Codex passes a variable on only under its own name, so an `env` value must be exactly `${SAME_NAME}` (`"API_KEY": "${API_KEY}"`). A server that cannot be mapped is skipped and reported with the reason, for example: a plaintext secret, a `${…}` in `command`, `args` or `url`, an `env` value pointing to a differently named variable, a header or `env` value that mixes text with a variable, or keys Codex has no equivalent for (such as `timeout`). |
| `skills/<name>/` | Skill folders you recorded as global, or created with `loadout configure new skill` ([Create a skill of your own](../how-to/your-own-tools.md#create-a-skill-of-your-own)). | Each is linked to `~/.claude/skills/<name>`. | Each is linked to `~/.agents/skills/<name>`. |
| `targets.json` | `{"claude": true, "codex": true}`: the coding agents loadout sets up (a missing `claude` means on; `codex` is off unless `true`). One agent must stay on. | Read by bootstrap, the daily sync and `loadout check`. Set it with `loadout configure set target claude\|codex on\|off` or `bootstrap --agents`. With `claude` off, loadout sets up no Claude Code links, settings or plugins (loadout's own state lives in `~/.local/state/loadout`, see [Machine-local state](#machine-local-state)). It covers your own folders; a repo's files follow the repo's [`.loadout.json`](cli.md#loadoutjson), and this file decides only in a repo without one. Without the file, bootstrap asks in a terminal (default: both when it sees a Codex, else Claude Code; [Which agents bootstrap sets up](cli.md#which-agents-bootstrap-sets-up)). Recommended: turn on every agent you use on any machine, since every machine that uses this layer reads the same file ([Pick your setup](../how-to/setups.md#one-agent-choice-for-every-machine)). | Same file, same commands. With `codex` off, loadout does not read or change Codex files. See [Use loadout with Codex](../how-to/codex.md#switch-it-on). |
| `skills.json` | `{name: path}`: skills you recorded as a pointer to a shared source. | Each is linked to `~/.claude/skills/<name>` on machines where the path exists. `loadout check` warns if the file is not valid JSON. | Each is linked to `~/.agents/skills/<name>` on machines where the path exists. |
| `hooks/` | Scripts of hooks you recorded as global. | Linked as `~/.claude/hooks/personal`. The recorded commands point to `$HOME/.claude/hooks/personal/<file>`. | Not used. |
| `profiles/NAME.json` | Your own project presets. See [profile-format](profile-format.md). | Applied to a repo by `loadout profile NAME`. | Same command; the Codex side of a profile is described in [profile-format](profile-format.md#in-codex). |
| `profiles/skills/<name>/` | Skills used by your profiles: recorded with adopt's `project:<profile>`, or created with `loadout configure new skill NAME --to project:<profile>`. | Copied into a repo's `.claude/skills` by `loadout profile` (when the repo is for Claude Code). They are never linked into `~/.claude`. | Linked from the repo's `.claude/skills` into its `.agents/skills`; in a Codex-only repo copied into `.agents/skills`, see [profile-format](profile-format.md#in-codex). |

The Codex folder is `$CODEX_HOME`, or `~/.codex` when that is not set. loadout writes there only the marked block in `AGENTS.md` and the entries it recorded in `config.toml` and `hooks.json` (Serena's hooks, see [Serena's hooks in Codex](hooks.md#serenas-hooks-in-codex); the record is described in [Machine-local state](#machine-local-state)); text you wrote yourself stays byte for byte. Codex-only setups and the account-level differences are in [Use loadout with Codex](../how-to/codex.md#what-stays-different).

The kit's own rules are linked the same way, to `~/.claude/rules/loadout` for Claude Code, and go into the same `AGENTS.md` block for Codex. `loadout` itself is a launcher script at `~/.local/bin/loadout` (on Windows, `loadout.cmd` and a Git Bash shim).

### Links and copies

loadout links with symlinks. If the system cannot create them (Windows without Developer Mode), it writes a marker `~/.local/state/loadout/copy-mode` and copies the files instead. Copied folders carry a `.loadout-copy` file and are refreshed after each [daily sync](state-and-sync.md#the-daily-sync) and by `loadout bootstrap`. Recommended on Windows: turn on Developer Mode, so links work and an edit reaches every agent at once. A copy you edited in place is moved into a backup on the next refresh, so edit the source in the personal layer. `loadout bootstrap` returns to links when they work again.

If a link target would replace something you own, the old item goes into a backup first.

### What gets recorded here

[`loadout adopt`](cli.md#loadout-adopt) and [`loadout configure set own`](cli.md#loadout-configure) write your own tools into the personal layer:

| Choice | Plugin | Marketplace | MCP server | Skill folder | Skill link | Hook |
|---|---|---|---|---|---|---|
| `global` | `settings.json`: `enabledPlugins` and the marketplace in `extraKnownMarketplaces` | `settings.json`: `extraKnownMarketplaces` | `mcp.json` | `skills/<name>/` | `skills.json` | `settings.json`: `hooks`; a simple command's script goes to `hooks/` |
| `project:<profile>` | `profiles/<profile>.json`: `install` and `settings` | not available | `profiles/<profile>.json`: `mcp` | `profiles/skills/<name>/` and the profile's `skills` | not available | `profiles/<profile>.json`: `settings.hooks` |

An MCP server from `~/.claude/.mcp.json` can only be left or removed. Before anything is written, a secret guard checks every item: secrets in MCP `env` and `headers` become `${VAR}` and move to `~/.config/loadout/secrets.env`, and anything that cannot be moved safely is refused.

## Machine-local state

`~/.local/state/loadout/` (or `$XDG_STATE_HOME/loadout`) belongs to this machine and is not part of the personal layer. Do not sync it. Older versions kept it in `~/.claude/.loadout/`; loadout moves it once ([The move out of ~/.claude](state-and-sync.md#the-move-out-of-claude)). The rule for the folder's path: [State folders](state-and-sync.md#state-folders).

| File | Holds |
|---|---|
| `managed-settings.json` | The snapshot of what the settings merge last applied. Under `hooks` it records exactly the hooks loadout applied. Under `loadoutDeletedHooks` it records hooks you deleted, so they are not added back. Written by every settings merge; which runs back it up is in [Undo](../how-to/undo-and-restore.md#what-restore-does-not-undo). |
| `codex-config.json` | `{"tables": {...}, "keys": {...}, "install_lines": {...}, "project_plugins": [...], "hooks": [...], "hook_events": [...], "block": ..., "block_notice": ...}`: `block` is a hash of loadout's block in `~/.codex/AGENTS.md` as loadout last wrote it, so the session-start refresh can tell whether you edited inside it; `block_notice` remembers that it told you once about such an edit. The other keys hold the exact text loadout wrote into `~/.codex/config.toml` and `~/.codex/hooks.json` (and the hook event keys it added there), the `enabled = true` lines that loadout's own `codex plugin add` wrote (`install_lines`), and the plugins a profile installed for single repos (their user-level `enabled` switch is kept off unless your personal layer enables them). loadout changes only entries that still match it, apart from those switches. |
| `managed-mcp.json` | `{"mcpServers": {...}}`: the personal MCP servers loadout added successfully. A same-named server that is not in this file and differs from the personal one is left alone. |
| `own-decisions.json` | Your `leave` decisions for own tools. Hooks are keyed by a hash of the command, so a command line is never stored. |
| `codex-hooks.json` | `{"digest": ..., "hashes": {...}, "serena": {...}}`: a hash of loadout's Codex hooks file, Codex's approvals and the Serena hooks in `hooks.json`, as last seen approved. It lets `loadout check` tell hooks that changed since you approved them in `/hooks` from hooks never approved. |
| `codex-marketplaces.json` | Per Codex marketplace source (`owner/repo`): its Codex name, the git head loadout last refreshed it at, and the heads of its plugins that have their own unpinned git source. `loadout update` compares these with `git ls-remote` and leaves a marketplace and its plugins alone when nothing moved. Written only after a successful add, upgrade or plugin install; delete it to force a full refresh. |
| `manual-commands.txt` | Private (readable only by you), and may hold secret values. The exact `claude mcp` commands loadout could not run itself, because a Windows `claude.cmd` shim cannot take JSON arguments; you run them by hand (see [Troubleshooting](../how-to/troubleshooting.md)). Some runs (adopt, restore, a personal MCP server change) write the same file into their backup folder instead. |
| `copy-mode` | Marker for copy instead of link mode. |
| `last-pull`, `last-update-check`, `pending-notice`, `refused-updates.json`, `sync-paused.json`, `maintenance.lock` | Bookkeeping of the daily and weekly maintenance (`sync-paused.json`: `{root: {reason, files, at}}` for a pull git refused, removed by the next good pull); the lock lets one maintenance run (or `loadout update`) work at a time. It holds the holder's command, start time, process id, host and (Linux) pid namespace and boot id (JSON); a second foreground run waits for it, the background job does not. One not touched for an hour, or (Linux, same host, pid namespace and boot) whose process has ended, counts as left over. |
| `open-steps.json` | The "Now do this" steps each agent still has to do (`{"claude": [...], "codex": [...]}`, each with id, text, reason and first time). `loadout update` adds the steps its run left (merged by id) and drops those that no longer hold (agent off, hooks approved, bootstrap rows passing, server gone); bootstrap saves only the steps visible without a run's facts (hooks, plugin copy). The agent's session-start hook shows them and clears them as described in [state-and-sync](state-and-sync.md#the-daily-sync). Machine-local. |
| `codex.lock` | Lets one Codex setup run at a time (bootstrap, configure, update, the daily sync). Same format and waiting as `maintenance.lock`. A lock not touched for an hour counts as left over from a crash. |
| `reload-notified.json` | The sessions already told to run `/reload-plugins`. See [hooks](hooks.md#hooks-of-the-loadout-plugin). |
| `advisor-pending.json`, `advisor-done.json` | State of the execution-advisor hook. See [hooks](hooks.md). |
| `tool-hint/<session>.json` | The tool hints' per-session search count; files older than 7 days are removed. See [hooks](hooks.md#hooks-of-the-loadout-plugin). |
| `migrated.json`, `migrate.lock` | The move out of `~/.claude`: what was copied, with signatures of the old entry and its copy, and the lock that lets one run move at a time ([The move out of ~/.claude](state-and-sync.md#the-move-out-of-claude)). |
| `backups/` | One `loadout-<timestamp>` folder per backup, with its manifest. See [State folders](state-and-sync.md#state-folders) and [Undo](../how-to/undo-and-restore.md). |

`~/.config/loadout/secrets.env` holds secrets in the form `NAME='value'`. It lives next to, not inside, the personal layer and is never committed. Backups and this state folder are described in [State folders](state-and-sync.md#state-folders).

## Sync

The kit and the personal layer are pulled once a day in the background; see [The daily sync](state-and-sync.md#the-daily-sync).

A personal layer reaches another machine only if you commit and push it; how to set up the repo is in [Keep your personal layer in a private git repo](../how-to/personal-repo.md). `loadout configure` offers to do that after a change. It does not offer while a private file would be committed (a `*.env` file or a file such as a key or credential). The same applies to the commit offer at the end of interactive `loadout adopt`.

`leave` decisions and the machine-local state stay on the machine where they were made.
