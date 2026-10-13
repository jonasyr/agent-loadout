# CLI reference

`loadout` is the command-line tool of the kit. Run `loadout --help` or `loadout <command> --help` for the built-in help. The flag tables below match that help.

The commands are `bootstrap`, `adopt`, `configure`, `init`, `profile`, `check`, `apply-settings`, `update`, `restore` and `kit-path`. Three more exist and are internal: `hook-session-start` and `maintenance` are called by the plugin's session hook and its background job, `advisor-mark` is called by the `/loadout:execution-advisor` skill. They are not listed in `loadout --help` and are not meant to be run by hand.

`loadout --version` prints the release and the kit's commit, for example `loadout 0.1.0 (54af5b7)`; the commit is left out when the kit is not a git clone. Bug reports ask for it.

## Exit codes

Every command returns 0 on success. These apply to all commands:

| Code | Meaning |
|---|---|
| 1 | A `ValueError` or invalid JSON (`InvalidJSON`) reached the top level. The message is printed to stderr as `loadout: ...`, with secrets redacted. |
| 2 | Wrong command-line usage, reported by argparse. |
| 130 | You pressed Ctrl+C. loadout prints `interrupted; run the same command again to continue` and stops. A re-run picks up where it stopped. |

Some commands return their own codes. They are listed per command and add to the table above.

## Environment variables

| Variable | Effect |
|---|---|
| `HOME` (Windows: `USERPROFILE` when `HOME` is not set) | Every path loadout uses derives from it. |
| `LOADOUT_PERSONAL` | The personal layer's folder, instead of `~/.config/loadout/personal`. See [personal-layer](personal-layer.md). |
| `LOADOUT_ROOT` | The kit's folder, instead of the clone the `loadout` launcher lives in. `loadout kit-path` prints it. |
| `CODEX_HOME` | Codex's folder, instead of `~/.codex`. |
| `XDG_STATE_HOME` | Where loadout keeps its state: `$XDG_STATE_HOME/loadout` instead of `~/.local/state/loadout`. Only an absolute path counts; a relative one, `~/…` included, is ignored. See [loadout's own files](../explanation/architecture.md#loadouts-own-files). |
| `LOADOUT_NO_AUTO_PULL=1` | Turns off the daily pull and what follows it; see [The daily sync](../explanation/architecture.md#the-daily-sync). |
| `NO_COLOR` (any value), `TERM=dumb` | No colour in the output. |
| `LOADOUT_REPO_URL`, `LOADOUT_REF` | Read by the one-liner scripts `bootstrap.sh` and `bootstrap.ps1`, not by `loadout`: the repo and the branch or tag to clone (default: this repo's `main`). For forks and tests. |
| `LOADOUT_PROPERTY_SEEDS`, `LOADOUT_PROPERTY_FIRST_SEED` | Tests only: how many seeds the hook-merge property test tries (default 2000), and the first one (default 0). |

## loadout bootstrap

Set up or repair this machine. Safe to re-run.

```
loadout bootstrap [--install] [--yes] [--no-plugins] [--no-adopt] [--verbose] [--agents LIST]
```

| Flag | Meaning |
|---|---|
| `--install` | Install missing tool binaries. |
| `--yes` | Accept defaults without asking. Adopt applies remove, migrate and scope-down; binary updates are never applied. Without `--agents`, a machine that has not chosen gets Claude Code. |
| `--no-plugins` | Skip adding marketplaces and installing plugins (offline or CI). |
| `--no-adopt` | Skip reviewing the existing setup. |
| `--agents LIST` | `claude`, `codex` or `claude,codex`: the coding agents to set up, without asking. Stored in `<personal>/targets.json`; it wins over the personal layer's choice. |
| `--verbose` | Print every detail of every step (links, commands, the full check list, the backup path). |

By default bootstrap prints one status line per step (`✓`, `!` for a warning, `✗` for a failure), the adopt questions, and at the end the health-check count, `Undo any time: loadout restore --list` when it made a backup, and the next step. Problem lines (a failed install or plugin, a check that failed) are always printed in full. Without a terminal, colour is off (also with `NO_COLOR` or `TERM=dumb`, see [Environment variables](#environment-variables)); where the console cannot show `✓`, ASCII stands in.

Without a terminal and without `--yes`, bootstrap skips the configure prompt and the adopt step and says so. It still runs `--install` when given, links files, creates a starter personal layer with default preferences if none exists, merges settings, applies personal MCP servers and sets up plugins.

`--install` runs the catalog's install commands without a further prompt, including `curl … | sh` installers. See [Security and trust](../explanation/security-and-trust.md#what-runs-when-you-ask).

The one-liner scripts that clone the kit and then run bootstrap can clone a fork instead: see `LOADOUT_REPO_URL` and `LOADOUT_REF` under [Environment variables](#environment-variables).

Exit codes:

| Code | Meaning |
|---|---|
| 0 | Done, and the final check found no error. |
| 1 | The personal-layer clone failed, or the final `loadout check` reported a failure (see [loadout check](#loadout-check)). |

## loadout adopt

Review an existing Claude Code setup and migrate it. It is a dry run unless `--apply` is given.
It reads Claude Code's `~/.claude/plugins/installed_plugins.json` and `known_marketplaces.json` to see what is installed; loadout never writes them itself (`check`, bootstrap and `update` read `installed_plugins.json` too).
With Codex on, it also lists the MCP servers and skills that only Codex has; their choices are `global`, `leave` and `remove` (see [Handle your own tools](../how-to/your-own-tools.md#tools-only-one-agent-has)).

```
loadout adopt [--apply] [--groups GROUPS] [--skip SKIP] [--yes]
              [--own NAME=CHOICE,...] [--no-versions] [--verbose]
```

| Flag | Meaning |
|---|---|
| `--apply` | Choose and apply changes (default: dry run). |
| `--groups GROUPS` | Apply exactly these groups, for example `remove,migrate`. The valid groups are `remove`, `migrate`, `scope-down`, `update`, `install`, `review` and `secrets` (moves the plaintext secrets the dry run lists into `secrets.env`; it selects no tool, and with `--groups` secrets move only when it is named). `update` and `install` run each command after confirmation unless `--yes` is also given. `own` is refused: use `--own`. |
| `--skip SKIP` | Comma-separated item names to skip in this run. Nothing is remembered. |
| `--yes` | No questions: apply `--groups`, or `remove,migrate,scope-down` when no groups are given, and move secrets (with `--groups`, only when it includes `secrets`). Your own tools stay as they are. |
| `--own NAME=CHOICE,...` | Decide for your own tools. Example: `my-db=project:mydb,foo@bar=global`. Choices: `global`, `project:<profile>`, `leave`, `remove`. Other items stay as they are. Hook naming: see [hooks](hooks.md#naming-hooks-of-your-own-tools). |
| `--no-versions` | Skip network version checks. |
| `--verbose` | Full detail: each item's command line, long reason, replacement and notes, the items that stay, and the backup path. |

By default adopt prints a count line (`Your existing setup: 7 suggestions (25 other items are fine)`), then each group under a plain heading (for example "Remove: superseded by something better") with one line per item and its short reason. With `--apply` in a terminal, each group is shown right before its question; then one `✓` line per group that was applied, or every result line when something did not complete.

Exit codes:

| Code | Meaning |
|---|---|
| 0 | Dry run, or applied. |
| 1 | `--own` was given and at least one named item was not recorded, or recorded but not active on this machine (see the `skipped:` or `failed:` line; a removal that did not happen says `skipped (...)` or `not removed`). The other items were applied. Also: an unknown group name in `--groups`, or `--groups own`. |
| 2 | `--own` had bad input (an unknown or duplicate name, a bad choice, or a name that needs `<kind>:` or `#n`), or `--apply` was run without a terminal and without any of `--yes`, `--groups` and `--own`. Nothing changed. |

## loadout configure

Choose preferences and global add-ons. Choices go into your personal layer. Without arguments it starts an interactive wizard.

```
loadout configure [--all] [--first-run] [show | prefs | own | set KIND NAME VALUE | new skill NAME]
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
| `loadout configure set target claude\|codex on\|off` | Set up that coding agent, or stop doing so (nothing is uninstalled; one agent stays on). Stored in `<personal>/targets.json`. See [Use loadout with Codex](../how-to/codex.md). |
| `loadout configure new skill NAME [--to global\|project:<profile>\|repo] [--description TEXT]` | Create a skill of your own: see [Create a skill of your own](../how-to/your-own-tools.md#create-a-skill-of-your-own). |

| Flag | Meaning |
|---|---|
| `--all` | With `own`: also list the tools you left on this machine. |
| `--first-run` | Also ask the "about you" questions again. Keeps your `me.md` unless you agree to replace it. |
| `--to` | With `new skill`: where the skill lives. `global` (default) is the personal layer, `project:<profile>` a personal profile, `repo` the current git repo (committed in `.claude/skills/`). |
| `--description` | With `new skill`: one line saying when an agent should use the skill. Without it the stub says `TODO`. |

`set plugin`, `set mcp`, `set pref-choice` and `set pref` afterwards apply the change: with Claude Code on they merge the settings, set up plugins and apply your personal MCP servers; with Codex on (and usable) the same choices are applied to Codex. They list pending changes of a personal-layer git repo but never commit them. `set pref-choice` for the auto mode preference needs a terminal, because it shows a draft that you must confirm.

Examples:

```bash
loadout configure show
loadout configure set pref-choice effort_level high
loadout configure set plugin hookify@claude-plugins-official on
loadout configure set mcp dbhub on
loadout configure set own foo@bar global
loadout configure new skill notes --description "Use when taking meeting notes."
loadout configure set pref effortLevel '"high"'
```

Exit codes:

| Code | Meaning |
|---|---|
| 0 | Done. |
| 1 | `set own`: at least one named item was not recorded, or recorded but not active on this machine (see the `skipped:` or `failed:` line). `set pref-choice`: the answer is written but another setting or `me.md` line still contradicts it ("not effective"). `set target codex on` when Codex is not found or too old: the choice is stored, and Codex is set up once that is fixed (`loadout bootstrap`). Also: a missing argument, a value that is not `on` or `off`, an unknown agent, turning the last agent off, an unknown MCP add-on, preference or option, and `set pref-choice` for the auto mode draft without a terminal. `new skill`: the name is taken, the profile is damaged, `--to repo` outside a git repo, or the description is refused (nothing written). |
| 2 | `set own` with bad input (unknown or duplicate name, bad choice, a name that needs `<kind>:` or `#n`). Nothing changed. `new skill` with a bad name, profile name or `--to`. Nothing written. |

The preference ids and options are in [preferences-format](preferences-format.md). The files this command writes are in [personal-layer](personal-layer.md).

## loadout init

Prepare the current project (what it writes per agent is in the table under [loadout profile](#loadout-profile)): `AGENTS.md`, `CLAUDE.md`, `docs/`, `.gitignore` entries and profiles. It never overwrites an existing scaffold file. How profiles merge into the repo's files, and why there is no backup, is in [Applying a profile](profile-format.md#what-applying-a-profile-does).

```
loadout init [--yes] [--no-install] [--dry-run] [--verbose] [PROFILE ...]
```

| Flag | Meaning |
|---|---|
| `PROFILE ...` | Profiles to apply. Default: suggest profiles from the project and ask. |
| `--yes` | No questions: run `git init` if needed and apply the suggested profiles. |
| `--no-install` | Do not install the profiles' plugins or run their commands. |
| `--verbose` | Print every file, command and note. Without it, `init` prints one status line per profile and one for the scaffold, then the next step; problems always show. |
| `--dry-run` | Change nothing. Print what would happen (see [Applying a profile](profile-format.md#what-applying-a-profile-does)) and the files and `.gitignore` entries `init` would create. |

Without a terminal, no `PROFILE` and no `--yes`, no profile is applied. If `CLAUDE.md` exists without `AGENTS.md`, neither file is created and a note says that `/loadout:onboard` will offer the migration. It adds `.claude/settings.local.json` and `.serena/cache/` to `.gitignore`.

Exit codes: 0 on success; 1 for an unknown profile name (every name is checked before anything changes), or when a profile was applied with problems (the run goes on and prints `profile NAME: applied with problems`). Problems are: a repo file skipped because it is, or lies behind, a symlink out of the repo; skills not copied; a plugin install or command that failed, a plugin id that is not `name@marketplace`, or a command that is not a list of words; with Codex on, a Codex step that failed or was skipped. `init` also returns 1 when it skipped `git init` because `.git` points out of the repo.

## loadout profile

Add one profile to the current project. It does what `init` does for a single profile, without the scaffolding.

```
loadout profile [--no-install] [--verbose] NAME
```

| Flag | Meaning |
|---|---|
| `NAME` | Profile name, for example `thesis`, `web`, `db`, `sonar`, `android`, or one in `<personal>/profiles`. |
| `--no-install` | Do not install the profile's plugins or run its commands. |
| `--verbose` | Print every file, command and note instead of the one status line. |

What `init` and `profile` write in the repo, per agent:

| | Claude Code (shared repo files, written even when Claude Code is off) | Codex (only when Codex is on) |
|---|---|---|
| Profile MCP servers | Merged into `.mcp.json`. | Added as sections to `.codex/config.toml`; `${VAR}` arguments are skipped with the reason. |
| Profile settings | Merged into `.claude/settings.json`. | Not used, except which servers are switched off. |
| Profile plugins (`install`) | `claude plugin install ID --scope project`. Skipped when Claude Code is off. | `codex plugin add`, switched on only in this repo (`enabled = true` in `.codex/config.toml`). |
| Profile skills | Copied into `.claude/skills/`. | Every skill in `.claude/skills` is linked into `.agents/skills`. |
| `commands` | Run once; they are not tied to an agent. | |
| Scaffold (`init` only) | `AGENTS.md`, `CLAUDE.md`, `docs/`, `.gitignore` entries: the same for both agents. | |
| Next step printed (`init`) | Start Claude Code here and run `/loadout:onboard`. | Start Codex here and ask it to use the `loadout:onboard` skill (printed when Claude Code is off). |

Codex reads `.codex/config.toml` only in a trusted project; loadout prints the step and never trusts one for you. Details per field: [In Codex](profile-format.md#in-codex). The format of a profile is in [profile-format](profile-format.md). Exit codes: as for [init](#loadout-init): 0 on success; 1 for an unknown profile name or when the profile was applied with problems.

## loadout check

Verify this machine. Read-only: it reports problems and names the fix, and never changes anything. With Claude Code switched off in `targets.json`, the Claude Code rows are skipped (the links under `~/.claude`, `settings.json` and its drift, the enabled-plugins check and the claude.ai connector check); with Codex off, the Codex rows are. See [personal-layer](personal-layer.md).

```
loadout check [--verbose]
```

By default it prints `Health check: N of M OK`, then only the warnings and failures. `--verbose` lists every check. Each listed line is `ok`, `warn` or `FAIL`.

| Check | Severity when it fails |
|---|---|
| The Python version that runs loadout (an `ok` line; loadout needs 3.11 or newer and stops before this on older versions) | — |
| Inside WSL: the WSL version (an ok line), then one warning per problem from [WSL 2](../how-to/wsl.md) | warn |
| `loadout state`: everything of loadout's in `~/.claude/.loadout` and its `loadout-<timestamp>` folders in `~/.claude/backups` was copied to the new place, and no old entry was kept because both places have it (compare and delete it by hand). Old copies waiting to be retired, and Claude Code's own files in `~/.claude/backups`, are not counted | warn |
| The links under `~/.claude` (rules, global skills, `hooks/personal`) | FAIL |
| `settings.json` is valid JSON | FAIL |
| A required binary is on `PATH` | FAIL |
| Any other binary on `PATH` | warn |
| `serena` and `codebase-memory-mcp` are on the PATH a new terminal gets (Claude Code starts them by name) | warn |
| `skills.json` is valid JSON | warn |
| Settings drift (a kit-managed value was changed) | warn |
| Enabled plugins are installed | warn |
| An enabled plugin and a claude.ai connector with the same tools ("ever connected" in `~/.claude.json`, an undocumented Claude Code field) | warn |
| Own tools that loadout does not manage | warn |
| `gh auth status` | warn |
| `secrets.env` exists and is readable only by you | warn |
| The kit and personal git repos have no uncommitted changes | warn |
| With Codex on (nothing is checked about Codex while it is off): `codex` found and new enough (`Codex`), the loadout plugin installed (`Codex plugin`), the block in `~/.codex/AGENTS.md` current (`Codex instructions`; an `AGENTS.override.md` that shadows it adds a second `Codex instructions` line, a warning), loadout's entries in `config.toml` current (`Codex config`), enabled plugins without a Codex route (`Codex plugins`), loadout's hooks approved in `/hooks` (`Codex hooks`), MCP servers waiting for a login (`Codex logins`), MCP servers and skills present in only one agent (`Codex drift`) | warn, except `Codex plugin` and `Codex instructions`: FAIL |

Exit codes: 0 when nothing failed (warnings do not count); 1 when at least one `FAIL` line was printed.

## loadout apply-settings

Merge the kit's and your personal settings into `~/.claude/settings.json`.

```
loadout apply-settings
```

Claude Code only: Codex has no settings file that loadout merges. With Claude Code turned off in `targets.json`, it prints `Claude Code is turned off (loadout configure set target claude on); nothing to merge` and changes nothing. It has no flags. It prints `settings updated` or `settings already up to date`. The merge rules are in [settings-merge](settings-merge.md). Exit codes: 0 on success, and when Claude Code is off; 1 if `settings.json`, the snapshot, or the kit's or your personal `settings.json` is not valid JSON (nothing is written).

## loadout update

Update outdated tool binaries and the plugins loadout enables. It prints each command and asks before it runs, unless `--yes` is given.

```
loadout update [--yes]
```

| Flag | Meaning |
|---|---|
| `--yes` | Run every update command without asking. Each is still printed. |

With Claude Code on, it first refreshes the plugin marketplaces (`claude plugin marketplace update`). Then, with Claude Code on, it runs `claude plugin update <id> --scope user` for each plugin that is enabled in the merged settings and installed with user scope, and with Codex on it upgrades the Codex marketplaces and adds each routed plugin again (`codex plugin add`). It names the plugins first and asks once before it touches them (`--yes` answers for you; without a terminal and without `--yes` they stay as they are). It prints one line per plugin that changed (`plugin <id>: updated`) or failed (`plugin <id>: failed: ...`; the others still run), and a closing line to run `/reload-plugins` or restart the agent when something changed. Plugins already at the latest version print nothing. The daily background sync does not run `claude plugin update`; Claude Code updates the marketplaces in `settings.base.json` by itself, and the sync refreshes the Codex plugins after it pulls a new kit (see [the daily sync](../explanation/architecture.md#the-daily-sync)). Then, for each outdated tool, it picks the package manager that installed it (`pkgmgr.update_plan`):

- `mise upgrade <tool>` when the binary lives under mise's `installs` directory, also behind a mise shim. The mise tool name is the catalog id, or `npm:<package>` for mise's npm backend; a catalog entry can override it with `"mise": "<name>"`. For these tools mise itself decides what is outdated (`mise outdated`), so its `minimum_release_age` and pins are respected.
- `brew upgrade <formula>` when the binary resolves into Homebrew's `Cellar/<formula>/`. Casks and npm packages installed with Homebrew's node are not formulae and keep their own updater.
- Otherwise the `update` command of the catalog entry (`claude update`, `uv self update`, ...). See [Catalog format](catalog-format.md#install-and-update).

For a tool not managed by mise, if the update command succeeds but installs nothing newer, loadout remembers that version in `~/.local/state/loadout/refused-updates.json` and does not notify again until a newer one appears. A failed update keeps notifying.

If an installer changed `~/.claude/settings.json`, the kit-merged version is put back and the installer's version goes into a backup.

Some installers re-register what the loadout plugin already provides (for example an install of codebase-memory-mcp without `--skip-config` adds its user-scope MCP server and `~/.claude/hooks/cbm-*` scripts). When at least one update command ran and the loadout plugin is enabled, `update` removes only exact duplicates (`maintenance.undo_reregistered`, `duplicates.py`):

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
| `BACKUP_DIR` | A directory printed by bootstrap or adopt, for example `~/.local/state/loadout/backups/loadout-<timestamp>`. A path from before the move, `~/.claude/backups/loadout-<timestamp>`, still works. |
| `--list` | List backups, newest first. |
| `--force` | Replay a backup that was already restored. |

Without `BACKUP_DIR` it lists the backups, like `--list`.

Backups are kept in `~/.local/state/loadout/backups`, for every user, Codex-only setups included; see [loadout's own files](../explanation/architecture.md#loadouts-own-files). Backups taken before the move restore from the new place. If the old `~/.claude/backups` folder still exists, restore names it: the move has not finished, or a different backup of the same name was kept in both places. Restore only accepts folders under the backups location and only runs the undo commands loadout itself records (`claude mcp add-json|remove -s user`, `claude plugin enable|install … --scope user`, `claude plugin marketplace add`, `codex plugin remove`, `codex plugin marketplace remove`); anything else is refused with a message and exit code 1.

Exit codes: 0 when listing or when every step succeeded; 1 when the backup has no manifest, was already restored (without `--force`), or a step failed.

## loadout kit-path

Print the kit's folder (your clone). The doc skills read the kit's `rules/` and `docs/explanation/documentation-strategy.md` from there, so they work the same in Claude Code and Codex.

```
loadout kit-path
```

Exit code: 0.
