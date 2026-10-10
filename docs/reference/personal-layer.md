# Personal layer

The personal layer is your own folder of preferences. It is separate from the kit, so the kit can update without touching it. By default it is `~/.config/loadout/personal`. Set `LOADOUT_PERSONAL` to use another folder. The code is `cli/loadout/paths.py`, `link.py`, `settings_merge.py`, `personal_mcp.py` and `own.py`.

`loadout bootstrap` clones it from a git URL you give, or creates a starter layer: `settings.json` containing `{}`, plus a `rules/me.md` written from the "about you" questions and the working preferences. Make the folder a private git repo to sync it across machines. See [Sync](#sync).

## Files

```
<personal>/
├── rules/me.md
├── settings.json
├── mcp.json
├── skills/<name>/
├── skills.json
├── hooks/
└── profiles/
    ├── NAME.json
    └── skills/<name>/
```

Every file is optional, and a missing file counts as empty. The one exception is `rules/`: `loadout check` reports `link rules/personal` as a failure while `<personal>/rules` does not exist, because loadout only creates that link when its target exists.

| Path | Holds | What loadout does with it |
|---|---|---|
| `rules/me.md` | Who you are and how you like to work. May contain the managed preferences block, see [preferences-format](preferences-format.md#the-managed-block). | Linked into `~/.claude/rules/personal`. Claude Code loads it in every session. |
| `settings.json` | Your overrides of the kit's settings, for example `"effortLevel": "high"` or `"enabledPlugins": {"impeccable@impeccable": false}`. Also the hooks you recorded as global. | Merged with the kit's `settings.base.json` and written into `~/.claude/settings.json`. See [settings-merge](settings-merge.md). |
| `mcp.json` | `{"mcpServers": {...}}`: extra MCP servers you want everywhere. Secrets are written as `${VAR}`. | Applied as user-scope servers with `claude mcp add-json -s user`. |
| `skills/<name>/` | Skill folders you recorded as global. | Each is linked to `~/.claude/skills/<name>`. |
| `skills.json` | `{name: path}`: skills you recorded as a pointer to a shared source. | Each is linked to `~/.claude/skills/<name>` on machines where the path exists. `loadout check` warns if the file is not valid JSON. |
| `hooks/` | Scripts of hooks you recorded as global. | Linked as `~/.claude/hooks/personal`. The recorded commands point to `$HOME/.claude/hooks/personal/<file>`. |
| `profiles/NAME.json` | Your own project presets. See [profile-format](profile-format.md). | Applied to a repo by `loadout profile NAME`. |
| `profiles/skills/<name>/` | Skills used by your profiles. | Copied into a repo by `loadout profile`. They are never linked into `~/.claude`. |

The kit's own rules are linked the same way, to `~/.claude/rules/loadout`. `loadout` itself is linked to `~/.local/bin/loadout` (on Windows, two small shim files are written there).

### Links and copies

loadout links with symlinks. If the system cannot create them (Windows without Developer Mode), it writes a marker `~/.claude/.loadout/copy-mode` and copies the files instead. Copied folders carry a `.loadout-copy` file and are refreshed after each daily sync and by `loadout bootstrap`. A copy you edited in place is moved into a backup on the next refresh, so edit the source in the personal layer. `loadout bootstrap` returns to links when they work again.

If a link target would replace something you own, the old item goes into a backup first.

### What gets recorded here

[`loadout adopt`](cli.md#loadout-adopt) and [`loadout configure set own`](cli.md#loadout-configure) write your own tools into the personal layer:

| Choice | Plugin | Marketplace | MCP server | Skill folder | Skill link | Hook |
|---|---|---|---|---|---|---|
| `global` | `settings.json`: `enabledPlugins` and the marketplace in `extraKnownMarketplaces` | `settings.json`: `extraKnownMarketplaces` | `mcp.json` | `skills/<name>/` | `skills.json` | `settings.json`: `hooks`; a simple command's script goes to `hooks/` |
| `project:<profile>` | `profiles/<profile>.json`: `install` and `settings` | not available | `profiles/<profile>.json`: `mcp` | `profiles/skills/<name>/` and the profile's `skills` | not available | `profiles/<profile>.json`: `settings.hooks` |

An MCP server from `~/.claude/.mcp.json` can only be left or removed. Before anything is written, a secret guard checks every item: secrets in MCP `env` and `headers` become `${VAR}` and move to `~/.config/loadout/secrets.env`, and anything that cannot be moved safely is refused.

## Machine-local state

`~/.claude/.loadout/` belongs to this machine and is not part of the personal layer. Do not sync it.

| File | Holds |
|---|---|
| `managed-settings.json` | The snapshot of what the settings merge last applied. Under `hooks` it records exactly the hooks loadout applied. Under `loadoutDeletedHooks` it records hooks you deleted, so they are not added back. Written by `apply-settings`, `configure`, and the daily maintenance, and backed up by `bootstrap` and `adopt`. |
| `managed-mcp.json` | `{"mcpServers": {...}}`: the personal MCP servers loadout added successfully. A same-named server that is not in this file and differs from the personal one is left alone. |
| `own-decisions.json` | Your `leave` decisions for own tools. Hooks are keyed by a hash of the command, so a command line is never stored. |
| `copy-mode` | Marker for copy instead of link mode. |
| `last-pull`, `last-update-check`, `pending-notice`, `refused-updates.json`, the maintenance lock | Bookkeeping of the daily and weekly maintenance. |
| `advisor-pending.json`, `advisor-done.json` | State of the execution-advisor hook. See [hooks](hooks.md). |

`~/.config/loadout/secrets.env` holds secrets in the form `NAME='value'`. It lives next to, not inside, the personal layer and is never committed. Backups are in `~/.claude/backups/`.

## Sync

The kit and the personal layer are pulled once a day in the background with `git pull --ff-only`, but only when the checkout has no local changes. `LOADOUT_NO_AUTO_PULL=1` turns the pull off. After a pull that brought commits, loadout merges the settings, applies `mcp.json`, and relinks skills and hook scripts. Plugins install at the next Claude Code start.

A personal layer reaches another machine only if you commit and push it. `loadout configure` offers to do that after a change. It does not offer while a private file would be committed (a `*.env` file or a file such as a key or credential). The same applies to the commit offer at the end of interactive `loadout adopt`.

`leave` decisions and the machine-local state stay on the machine where they were made.
