# CLI reference

`loadout` is the command-line tool of the kit. Run `loadout --help` or `loadout <command> --help` for the built-in help. The flag tables below match that help.

The commands are `bootstrap`, `adopt`, `configure`, `init`, `profile`, `check`, `apply-settings`, `update` and `restore`. Three more exist and are internal: `hook-session-start` and `maintenance` are called by the plugin's session hook and its background job, `advisor-mark` is called by the `/loadout:execution-advisor` skill. They have no `--help` entry and are not meant to be run by hand.

## Exit codes

Every command returns 0 on success. These apply to all commands:

| Code | Meaning |
|---|---|
| 1 | A `ValueError` or invalid JSON (`InvalidJSON`) reached the top level. The message is printed to stderr as `loadout: ...`, with secrets redacted. |
| 2 | Wrong command-line usage, reported by argparse. |

Some commands return their own codes. They are listed per command and add to the table above.

## loadout bootstrap

Set up or repair this machine. Safe to re-run.

```
loadout bootstrap [--install] [--yes] [--no-plugins] [--no-adopt]
```

| Flag | Meaning |
|---|---|
| `--install` | Install missing tool binaries. |
| `--yes` | Accept defaults without asking. Adopt applies remove, migrate and scope-down; binary updates are never applied. |
| `--no-plugins` | Skip adding marketplaces and installing plugins (offline or CI). |
| `--no-adopt` | Skip reviewing the existing setup. |

Without a terminal and without `--yes`, bootstrap skips the configure prompt and the adopt step and says so.

Exit codes:

| Code | Meaning |
|---|---|
| 0 | Done, and the final check found no error. |
| 1 | The personal-layer clone failed, or the final `loadout check` reported a failure (see [loadout check](#loadout-check)). |

## loadout adopt

Review an existing Claude Code setup and migrate it. It is a dry run unless `--apply` is given.

```
loadout adopt [--apply] [--groups GROUPS] [--skip SKIP] [--yes]
              [--own NAME=CHOICE,...] [--no-versions]
```

| Flag | Meaning |
|---|---|
| `--apply` | Choose and apply changes (default: dry run). |
| `--groups GROUPS` | Apply exactly these groups, for example `remove,migrate`. The valid groups are `remove`, `migrate`, `scope-down`, `update`, `install` and `review`. `update` and `install` run each command after confirmation unless `--yes` is also given. `own` is refused: use `--own`. |
| `--skip SKIP` | Comma-separated item names to skip in this run. Nothing is remembered. |
| `--yes` | No questions: apply `--groups`, or `remove,migrate,scope-down` when no groups are given, and move secrets. Your own tools stay as they are. |
| `--own NAME=CHOICE,...` | Decide for your own tools. Example: `my-db=project:mydb,foo@bar=global`. Choices: `global`, `project:<profile>`, `leave`, `remove`. Other items stay as they are. Hook naming: see [hooks](hooks.md#naming-hooks-of-your-own-tools). |
| `--no-versions` | Skip network version checks. |

Exit codes:

| Code | Meaning |
|---|---|
| 0 | Dry run, or applied. |
| 1 | `--own` was given and at least one named item was not recorded, or recorded but not active on this machine. The other items were applied. Also: an unknown group name in `--groups`, or `--groups own`. |
| 2 | `--own` had bad input (an unknown or duplicate name, a bad choice, or a name that needs `<kind>:` or `#n`), or `--apply` was run without a terminal and without any of `--yes`, `--groups` and `--own`. Nothing changed. |

## loadout configure

Choose preferences and global add-ons. Choices go into your personal layer. Without arguments it starts an interactive wizard.

```
loadout configure [--all] [--first-run] [show | prefs | own | set KIND NAME VALUE]
```

| Form | What it does |
|---|---|
| `loadout configure` | The wizard: the "about you" questions when `rules/me.md` is missing, the working preferences, then a menu of global add-ons. |
| `loadout configure show` | Print every add-on and preference with its current state and its id. Read-only. |
| `loadout configure prefs` | Ask only the working-preference questions. Enter keeps the current answer. |
| `loadout configure set plugin ID on\|off` | Switch a plugin on or off in your personal `settings.json`. `true`, `yes`, `false` and `no` are accepted too. |
| `loadout configure set mcp ID on\|off` | Switch an MCP add-on on or off in your personal `mcp.json`. `ID` is the catalog id or the server name. |
| `loadout configure set pref-choice ID OPTION` | Set one working preference to one of its options. |
| `loadout configure set pref KEY JSON` | Set a key in your personal `settings.json`. `JSON` is parsed as JSON; if that fails, it is stored as a string. |
| `loadout configure own [--all]` | List the tools loadout does not manage. Read-only. |
| `loadout configure set own NAME CHOICE` | Decide one own tool. `CHOICE` is `global`, `project:<profile>`, `leave` or `remove`. |

| Flag | Meaning |
|---|---|
| `--all` | With `own`: also list the tools you left on this machine. |
| `--first-run` | Also ask the "about you" questions again. Keeps your `me.md` unless you agree to replace it. |

`set plugin`, `set mcp`, `set pref-choice` and `set pref` afterwards merge the settings, set up plugins and apply your personal MCP servers. They list pending changes of a personal-layer git repo but never commit them. `set pref-choice` for the auto mode preference needs a terminal, because it shows a draft that you must confirm.

Examples:

```bash
loadout configure show
loadout configure set pref-choice effort_level high
loadout configure set plugin hookify@claude-plugins-official on
loadout configure set mcp dbhub on
loadout configure set own foo@bar global
loadout configure set pref effortLevel '"high"'
```

Exit codes:

| Code | Meaning |
|---|---|
| 0 | Done. |
| 1 | `set own`: at least one named item was not recorded, or recorded but not active on this machine (see the `skipped:` or `failed:` line). `set pref-choice`: the answer is written but another setting or `me.md` line still contradicts it ("not effective"). Also: a missing argument, or a value that is not `on` or `off`. |
| 2 | `set own` with bad input (unknown or duplicate name, bad choice, a name that needs `<kind>:` or `#n`). Nothing changed. |

The preference ids and options are in [preferences-format](preferences-format.md). The files this command writes are in [personal-layer](personal-layer.md).

## loadout init

Prepare the current project: `AGENTS.md`, `CLAUDE.md`, `docs/`, `.gitignore` entries and profiles. Never overwrites a file.

```
loadout init [--yes] [--no-install] [--dry-run] [PROFILE ...]
```

| Flag | Meaning |
|---|---|
| `PROFILE ...` | Profiles to apply. Default: suggest profiles from the project and ask. |
| `--yes` | No questions: run `git init` if needed and apply the suggested profiles. |
| `--no-install` | Do not install the profiles' plugins or run their commands. |
| `--dry-run` | Show what would change, change nothing. |

Without a terminal, no `PROFILE` and no `--yes`, no profile is applied. If `CLAUDE.md` exists without `AGENTS.md`, neither file is created and a note says that `/loadout:onboard` will offer the migration. It adds `.claude/settings.local.json` and `.serena/cache/` to `.gitignore`.

Exit codes: 0 on success; 1 for an unknown profile name (every name is checked before anything changes).

## loadout profile

Add one profile to the current project. It does what `init` does for a single profile, without the scaffolding.

```
loadout profile [--no-install] NAME
```

| Flag | Meaning |
|---|---|
| `NAME` | Profile name, for example `thesis`, `web`, `db`, `sonar`, `android`, or one in `<personal>/profiles`. |
| `--no-install` | Do not install the profile's plugins or run its commands. |

The file format is in [profile-format](profile-format.md). Exit codes: 0 on success; 1 for an unknown profile name.

## loadout check

Verify this machine. Read-only: it reports problems and names the fix, and never changes anything.

```
loadout check
```

It has no flags. Each line is `ok`, `warn` or `FAIL`.

| Check | Severity when it fails |
|---|---|
| The links under `~/.claude` (rules, global skills, `hooks/personal`) | FAIL |
| `settings.json` is valid JSON | FAIL |
| A required binary is on `PATH` | FAIL |
| Any other binary on `PATH` | warn |
| `skills.json` is valid JSON | warn |
| Settings drift (a kit-managed value was changed) | warn |
| Enabled plugins are installed | warn |
| Own tools that loadout does not manage | warn |
| `gh auth status` | warn |
| `secrets.env` exists and is readable only by you | warn |
| The kit and personal git repos have no uncommitted changes | warn |

Exit codes: 0 when nothing failed (warnings do not count); 1 when at least one `FAIL` line was printed.

## loadout apply-settings

Merge the kit's and your personal settings into `~/.claude/settings.json`.

```
loadout apply-settings
```

It has no flags. It prints `settings updated` or `settings already up to date`. The merge rules are in [settings-merge](settings-merge.md). Exit codes: 0 on success; 1 if `settings.json` or the snapshot is not valid JSON (nothing is written).

## loadout update

Update outdated tool binaries. It prints each command and asks before it runs, unless `--yes` is given.

```
loadout update [--yes]
```

| Flag | Meaning |
|---|---|
| `--yes` | Run every update command without asking. Each is still printed. |

It first refreshes the plugin marketplaces (`claude plugin marketplace update`). Then, for each outdated tool, it picks the package manager that installed it (`pkgmgr.update_plan`):

- `mise upgrade <tool>` when the binary lives under mise's `installs` directory, also behind a mise shim. The mise tool name is the catalog id, or `npm:<package>` for mise's npm backend; a catalog entry can override it with `"mise": "<name>"`. For these tools mise itself decides what is outdated (`mise outdated`), so its `minimum_release_age` and pins are respected.
- `brew upgrade <formula>` when the binary resolves into Homebrew's `Cellar/<formula>/`. Casks and npm packages installed with Homebrew's node are not formulae and keep their own updater.
- Otherwise the `update` command of the catalog entry (`claude update`, `uv self update`, ...). See [Catalog format](catalog-format.md#install-and-update).

For a tool not managed by mise, if the update command succeeds but installs nothing newer, loadout remembers that version in `~/.claude/.loadout/refused-updates.json` and does not notify again until a newer one appears. A failed update keeps notifying.

If an installer changed `~/.claude/settings.json`, the kit-merged version is put back and the installer's version goes into a backup.

Some installers re-register what the loadout plugin already provides (for example `codebase-memory-mcp update` re-adds its user-scope MCP server and `~/.claude/hooks/cbm-*` scripts). When at least one update command ran and the loadout plugin is enabled, `update` removes only exact duplicates (`maintenance.undo_reregistered`, `duplicates.py`):

- an MCP server with the same name, command, arguments, type and env as the plugin's, and not one of your personal-layer servers;
- a hook that runs the same command as a plugin hook, or is exactly a legacy `~/.claude/hooks/cbm-*` script;
- those scripts' files, when no settings hook references them.

They go into a backup, and `update` prints what it undid and how to restore it. Look-alikes (a forked or reconfigured server, your own context7) are only reported; review them with `loadout adopt`. Skills, plugins and marketplaces are never removed automatically.

Exit codes: 0 when finished (a failed update command is printed but does not change the code); 1 when the background maintenance job holds the lock. Try again after a minute.

## loadout restore

Undo a backup. What it replaces goes into a new backup, so a restore can be undone too.

```
loadout restore [--list] [--force] [BACKUP_DIR]
```

| Flag | Meaning |
|---|---|
| `BACKUP_DIR` | A directory printed by bootstrap or adopt, for example `~/.claude/backups/loadout-<timestamp>`. |
| `--list` | List backups, newest first. |
| `--force` | Replay a backup that was already restored. |

Without `BACKUP_DIR` it lists the backups, like `--list`.

Exit codes: 0 when listing or when every step succeeded; 1 when the backup has no manifest, was already restored (without `--force`), or a step failed.
