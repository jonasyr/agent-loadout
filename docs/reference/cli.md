# CLI reference

`loadout` is the command-line tool of the kit. Run `loadout --help` or `loadout <command> --help` for the built-in help. The flag tables below match that help.

The commands are `bootstrap`, `adopt`, `configure`, `init`, `profile`, `check`, `apply-settings`, `update`, `restore`, `usage`, `explain` and `kit-path`. Three more exist and are internal: `hook-session-start` and `maintenance` are called by the plugin's session hook and its background job, `advisor-mark` is called by the `/loadout:execution-advisor` skill. They are not listed in `loadout --help` and are not meant to be run by hand.

`loadout --version` prints the release and the kit's commit, for example `loadout 0.1.0 (54af5b7)`; the commit is left out when the kit is not a git clone. Bug reports ask for it.

## Exit codes

Every command returns 0 on success. These apply to all commands:

| Code | Meaning |
|---|---|
| 1 | A `ValueError` or invalid JSON (`InvalidJSON`) reached the top level. The message is printed to stderr as `loadout: ...`, with secrets redacted. |
| 1 | Also: the move of loadout's state out of `~/.claude` ([ADR 0025](../adr/0025-state-in-xdg-state-home.md)) did not finish. Nothing was changed; run the command again, and `loadout check` shows what is left. Not for `check`, `restore`, `usage`, `explain` and `kit-path`. |
| 2 | Wrong command-line usage, reported by argparse. |
| 130 | You pressed Ctrl+C. loadout prints `loadout: interrupted; run the same command again to continue (it picks up where it stopped)` and stops. A re-run picks up where it stopped. |

Some commands return their own codes. They are listed per command and add to the table above.

## Environment variables

| Variable | Effect |
|---|---|
| `HOME` (Windows: `USERPROFILE` when `HOME` is not set) | Every path loadout uses derives from it. |
| `LOADOUT_PERSONAL` | The personal layer's folder, instead of `~/.config/loadout/personal`. See [personal-layer](personal-layer.md). |
| `LOADOUT_ROOT` | The kit's folder, instead of the clone the `loadout` launcher lives in. `loadout kit-path` prints it. |
| `CODEX_HOME` | Codex's folder, instead of `~/.codex`. |
| `XDG_STATE_HOME` | Where loadout keeps its state: `$XDG_STATE_HOME/loadout` instead of `~/.local/state/loadout`. Only an absolute path counts; a relative one, `~/…` included, is ignored. The plugin's hook scripts follow the same rule. See [State folders](state-and-sync.md#state-folders). |
| `XDG_CONFIG_HOME` | Only where loadout looks for VS Code's user settings on Linux: `$XDG_CONFIG_HOME/Code/User` instead of `~/.config/Code/User`. The personal layer and `secrets.env` under `~/.config/loadout` do not follow it. |
| `APPDATA`, `LOCALAPPDATA` | Windows only: where loadout looks for VS Code's user settings (`%APPDATA%\Code\User`) and for the tool folders it puts on `PATH` (mise shims, WinGet links, npm globals). Without them, the default folders under your home. |
| `VSCODE_EXTENSIONS` | The local VS Code extensions folder that `check` and bootstrap search for the agents' extensions, instead of `~/.vscode/extensions`. |
| `LOADOUT_NO_AUTO_PULL=1` | Turns off the daily pull and what follows it; see [The daily sync](state-and-sync.md#the-daily-sync). |
| `NO_COLOR` (any non-empty value), `TERM=dumb` | No colour in the output. |
| `LOADOUT_REPO_URL`, `LOADOUT_REF` | Read by the one-liner scripts `bootstrap.sh` and `bootstrap.ps1`, not by `loadout`: the repo and the branch or tag to clone (default: this repo's `main`). For forks and tests. |
| `LOADOUT_PROPERTY_SEEDS`, `LOADOUT_PROPERTY_FIRST_SEED` | Tests only: how many seeds the hook-merge property test tries (default 2000), and the first one (default 0). |

loadout sets a few variables for itself; do not set them by hand: `LOADOUT_REEXEC` (the launcher restarted itself under a newer Python, so it does not try again) and `LOADOUT_PATH_ADD`, `LOADOUT_PATH_BACKUP` (passed to the PowerShell step that edits the Windows user `PATH`), `LOADOUT_PATH_REFRESH` (a user variable that step clears, so Windows tells running programs that `PATH` changed) and `LOADOUT_PY` (the Python that the Windows `loadout.cmd` launcher found; it lives only inside that launcher).

loadout also reads two VS Code settings, never writes them: `chatgpt.cliExecutable` (when it names a codex that runs, VS Code's Codex extension runs that codex, so loadout checks its version and, without a Codex CLI, uses it) and `claudeCode.claudeProcessWrapper` (the claude the Claude Code extension starts). `check` warns when either names a file that cannot run. See [Use loadout with VS Code](../how-to/vscode.md).

Without a `claude` on `PATH`, and with Claude Code on, every loadout command runs its `claude` commands (`claude plugin`, `claude mcp`) with the Claude Code extension's own `claude` when VS Code has one on this side ([Claude Code in VS Code without the CLI](../how-to/vscode.md#claude-code-in-vs-code-without-the-cli)). Likewise, without a Codex CLI, loadout runs its `codex` commands, including `codex mcp remove`, with VS Code's Codex extension's own codex ([Codex in VS Code without the CLI](../how-to/vscode.md#codex-in-vs-code-without-the-cli)).

## loadout bootstrap

Set up or repair this machine. Safe to re-run.

```
loadout bootstrap [--install] [--yes] [--no-plugins] [--no-adopt] [--verbose] [--agents LIST]
                  [--codex-side wsl|windows] [--vscode-wsl] [--vscode-path] [--without-codex-cli]
                  [--personal new|URL] [--answers FILE]
```

| Flag | Meaning |
|---|---|
| `--install` | Install missing tool binaries. |
| `--yes` | Accept defaults without asking, also in a terminal (see [When bootstrap does not ask](#when-bootstrap-does-not-ask)). Adopt applies remove, migrate and scope-down; binary updates are never applied. Without `--agents`, a machine that has not chosen gets Claude Code. |
| `--no-plugins` | Skip adding marketplaces and installing plugins (offline or CI). |
| `--no-adopt` | Skip reviewing the existing setup. |
| `--agents LIST` | `claude`, `codex` or `claude,codex`: the coding agents to set up, without asking. Stored in `<personal>/targets.json`; it wins over the personal layer's choice. A typo stops bootstrap before any question or clone. Without it: [Which agents bootstrap sets up](#which-agents-bootstrap-sets-up). Which agents to pick for your platform: [Pick your setup](../how-to/setups.md#recommended-setups). |
| `--codex-side wsl\|windows` | In WSL, with Codex on: set up the WSL Codex home (`wsl`) or leave Codex to `bootstrap.ps1` on Windows (`windows`), without asking. Needed without a terminal, or with `--yes`, when the only Codex is the Windows one, and always when `CODEX_HOME` points into Windows; otherwise the Codex step stops. Ignored outside WSL. With `wsl` in a terminal, bootstrap also asks whether to switch VS Code's Codex extension to WSL. In a terminal, bootstrap's own question defaults to `1` (WSL). Which side to pick: [Recommended setups](../how-to/setups.md#recommended-setups) ([Codex in WSL](../how-to/wsl.md#codex)). |
| `--vscode-wsl` | In WSL with Codex: switch VS Code's Codex extension to WSL without asking. It edits only `chatgpt.runCodexInWindowsSubsystemForLinux` in VS Code's `settings.json` on Windows, saves a copy first, and `loadout restore` undoes it. Without it and without a terminal, bootstrap prints the manual step. A folder's `.vscode/settings.json` or a VS Code profile that sets the switch to `false` again is named as a warning (with or without the flag); loadout does not edit it. Outside WSL it changes nothing and prints two warnings (`--vscode-wsl applies to loadout in WSL only` and `Codex is not set up in WSL in this run`); in WSL, when Codex is off or its step stops (`--codex-side windows`, a skipped side question), it changes nothing and says so. The recommended way in WSL is a Remote-WSL window (`code .` from WSL); this flag is for a Windows window you open anyway ([Pick your setup](../how-to/setups.md#wsl-2-recommended-on-windows)). |
| `--vscode-path` | In WSL with VS Code's Remote-WSL server: put loadout's tool folders on PATH for Remote-WSL windows, in a marked block in `~/.vscode-server/server-env-setup` (created if missing; your lines stay; a copy first, `loadout restore` undoes it). It takes effect when VS Code's WSL server restarts: close every Remote-WSL window, run `wsl --shutdown` in Windows, which stops every WSL distro, then reopen the folder. In a terminal, bootstrap offers it when a tool folder is missing there; a block written earlier is kept current. Elsewhere it changes nothing and says so ([VS Code](../how-to/vscode.md#mcp-servers-in-a-remote-wsl-window)). |
| `--without-codex-cli` | With VS Code's Codex extension and no Codex CLI: do not install the CLI. loadout sets Codex up for the extension (its own codex, new enough: [version](../how-to/codex.md#switch-it-on)) and lists what only the CLI adds (`/hooks`, plugins). Without the flag, `--install` in a terminal asks `Install the Codex CLI alongside VS Code (for /hooks and plugins)? [Y/n]`; without a terminal, or with `--yes`, it installs the CLI without asking. Where the flag does not apply (a Codex CLI is on `PATH`, no Codex extension with a usable codex, or Codex is not set up in this run), bootstrap prints `--without-codex-cli: not used; …`. Recommended: leave the flag out and keep the CLI next to the extension ([The Codex CLI alongside VS Code](../how-to/vscode.md#the-codex-cli-alongside-vs-code), [Codex in VS Code without the CLI](../how-to/vscode.md#codex-in-vs-code-without-the-cli)). |
| `--personal new\|URL` | The personal layer without asking: `new` creates a starter layer, a git URL is cloned. Used only when no personal layer exists yet; otherwise bootstrap says so and keeps the one there. |
| `--answers FILE` | A JSON file with the starter layer's answers: `about` (`name`, `role`, `languages`, `preferences`) and `preferences` (ids and values as in [Preferences format](preferences-format.md), free text as `other:<text>`). Give an absolute path: `bootstrap.sh` and `bootstrap.ps1` run bootstrap from the kit's folder. Every value is text. Checked before anything changes: an unknown key or value, a value that is not text, a value that looks like a secret, or a preference that needs a terminal (one that shows a draft to confirm, such as the auto mode preference: `--answers: <id> needs a terminal; run loadout configure prefs after setup`) stops bootstrap. Used only for a new personal layer; otherwise bootstrap says the flag was not used. Format and example: [Set loadout up from inside an agent](../how-to/install-with-an-agent.md#3-show-the-answers-file). |
| `--verbose` | Print every detail of every step (links, commands, the full check list, the backup path). |

By default bootstrap prints one status line per step (`✓`, `!` for a warning, `✗` for a failure), the adopt questions, and at the end the health-check count, `Undo any time: loadout restore --list` when it made a backup, and the next step. Problem lines (a failed install or plugin, a check that failed) are always printed in full. Without a terminal, colour is off (also with `NO_COLOR` or `TERM=dumb`, see [Environment variables](#environment-variables)); where the console cannot show `✓`, ASCII stands in.

`--install` runs the catalog's install commands without a further prompt, including `curl … | sh` installers. See [Security and trust](../explanation/security-and-trust.md#what-runs-when-you-ask).

The one-liner scripts that clone the kit and then run bootstrap can clone a fork instead: see `LOADOUT_REPO_URL` and `LOADOUT_REF` under [Environment variables](#environment-variables).

Exit codes:

| Code | Meaning |
|---|---|
| 0 | Done, and the final check found no error. |
| 1 | The personal-layer clone failed, or the final `loadout check` reported a failure (see [loadout check](#loadout-check)). |

### Which agents bootstrap sets up

Bootstrap settles the agents in this order:

1. `--agents`, when given. It is stored in `<personal>/targets.json` and wins over the layer's choice.
2. The choice your personal layer already has (`targets.json`), whether you just cloned the layer or it was already on this machine. Bootstrap does not ask. Only after a fresh clone it prints `using your personal layer's agents: …`; an existing layer's choice is used without a line.
3. Otherwise, in a terminal and without `--yes`, it asks `Which coding agents should loadout set up?  1) Claude Code  2) Codex  3) both`. The default (Enter) is `3` when it sees a Codex (a `codex` on `PATH`, or in WSL a Windows `codex.exe`), else `1`. VS Code's Codex extension alone does not count. An answer that is not 1, 2 or 3 takes the default and says so. The answer is stored in `targets.json`.
4. Otherwise it sets up Claude Code only, and stores nothing: without a terminal, with `--yes`, or when a personal layer already exists (without a choice) and no Codex is seen.

Which agents to choose for your platform and editor: [Pick your setup](../how-to/setups.md#recommended-setups). Change the choice later with [`loadout configure set target`](#loadout-configure).

### When bootstrap does not ask

Without a terminal (CI, `ssh host ./bootstrap.sh`, piped or closed input), or with `--yes`, bootstrap asks nothing and never waits for input:

- **Personal layer:** from `--personal`; without it, a starter layer. In a terminal without `--yes`, it asks for a git URL instead (empty creates a starter). The clone never prompts for a password: for a private HTTPS repo log in with `gh` first, or use an SSH URL.
- **Starter answers:** from `--answers`, defaults for the rest.
- **Agents:** as in [Which agents bootstrap sets up](#which-agents-bootstrap-sets-up): `--agents`, else the layer's choice, else Claude Code.
- **Codex CLI next to VS Code's Codex extension:** with `--install`, installed without asking, unless `--without-codex-cli` is given.
- **WSL:** the Codex side needs `--codex-side` when the only Codex is the Windows one (otherwise the Codex step stops and says so); the VS Code switch needs `--vscode-wsl` (otherwise bootstrap prints the manual step), and the Remote-WSL `PATH` block needs `--vscode-path`.
- **Configure prompt** (`Customize preferences and global add-ons now?`): skipped. Without a terminal and without `--yes` bootstrap says so; run `loadout configure` later.
- **Adopt step:** without a terminal and without `--yes`, skipped with a line naming `loadout adopt`. With `--yes`, it applies remove, migrate and scope-down.

It still runs `--install` when given, links files, merges settings, applies personal MCP servers and sets up plugins. The recommended way to run bootstrap from an agent or a script, with the flags it needs: [Set loadout up from inside an agent](../how-to/install-with-an-agent.md).

The adopt step runs only with Claude Code on. A Codex-only bootstrap does not review the tools that only Codex has: run [`loadout adopt`](#loadout-adopt) for that.

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
| `loadout configure set target claude\|codex on\|off` | Set up that coding agent, or stop doing so (nothing is uninstalled; one agent stays on). Stored in `<personal>/targets.json`. `codex on` sets Codex up at once. `claude on` with a `claude` on `PATH` links the rules and skills and applies settings, plugins and MCP servers at once; without one it stores the choice, prints `Claude Code is not installed yet: run loadout bootstrap --install …` and exits 0. See [Use loadout with Codex](../how-to/codex.md). |
| `loadout configure new skill NAME [--to global\|project:<profile>\|repo] [--description TEXT] [--yes]` | Create a skill of your own: see [Create a skill of your own](../how-to/your-own-tools.md#create-a-skill-of-your-own). With `--to repo` it shows a plan first ([Repo writes](#repo-writes)). |

| Flag | Meaning |
|---|---|
| `--all` | With `own`: also list the tools you left on this machine. |
| `--first-run` | Also ask the "about you" questions again. Keeps your `me.md` unless you agree to replace it. |
| `--to` | With `new skill`: where the skill lives. `global` (default) is the personal layer, `project:<profile>` a personal profile, `repo` the current git repo (committed in `.claude/skills/`, linked into `.agents/skills/`, when the repo is for both agents; in `.claude/skills/` with no `.agents/skills` link when it is for Claude Code only; in `.agents/skills/` when it is for Codex only; the repo's agents are in [`.loadout.json`](#loadoutjson)). |
| `--description` | With `new skill`: one line saying when an agent should use the skill. Without it the stub says `TODO`. |
| `--yes` | With `new skill --to repo`: create the skill without asking. Needed without a terminal; without it the plan is shown and nothing is written. |

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
| 1 | `set own`: at least one named item was not recorded, or recorded but not active on this machine (see the `skipped:` or `failed:` line). `set pref-choice`: the answer is written but another setting or `me.md` line still contradicts it ("not effective"). `set target codex on` when Codex is not found or too old: the choice is stored, and Codex is set up once that is fixed (`loadout bootstrap`). Also: a missing argument, a value that is not `on` or `off`, an unknown agent, turning the last agent off, an unknown MCP add-on, preference or option, and `set pref-choice` for the auto mode draft without a terminal. `new skill`: the name is taken, the profile or `skills.json` is damaged, a name or `--to` that looks like a secret, `--to repo` outside a git repo, in a repo whose `.loadout.json` is invalid, in a repo that is your home folder (a dotfiles repo), or where `.claude/skills` or `.agents/skills` (or its parent) is a link, leads outside the repo or is not a folder, or the description is refused (empty, more than one line, or looks like a secret; nothing written); or the skill was written but an agent that is on cannot see it, because its link could not be made (a `not linked` line, e.g. Windows without symlink rights). |
| 2 | `set own` with bad input (unknown or duplicate name, bad choice, a name that needs `<kind>:` or `#n`). Nothing changed. `new skill` with a bad name, profile name or `--to`. Nothing written. |

The preference ids and options are in [preferences-format](preferences-format.md). The files this command writes are in [personal-layer](personal-layer.md).

## loadout init

Prepare the current project (what it writes per agent is in the table under [loadout profile](#loadout-profile)): `.loadout.json`, `AGENTS.md`, `CLAUDE.md`, `docs/`, `.gitignore` entries and profiles. It never overwrites an existing scaffold file. It first builds a plan of every change, shows it and asks ([Repo writes](#repo-writes)). How profiles merge into the repo's files is in [Applying a profile](profile-format.md#what-applying-a-profile-does).

```
loadout init [--agents claude|codex|claude,codex] [--yes] [--no-install] [--dry-run] [--verbose] [PROFILE ...]
```

| Flag | Meaning |
|---|---|
| `PROFILE ...` | Profiles to apply. Default: suggest profiles from the project and ask. |
| `--agents` | Which agents the repo is for. Written to [`.loadout.json`](#loadoutjson); in a repo that has the file, it changes the list. Any other value exits 1. The choice decides the files everyone who clones the repo gets: for a shared repo, name every agent your team uses; for a repo only you use, the default (the agents that are on for you) fits. |
| `--yes` | No questions: apply the suggested profiles and the plan. A folder that is not a git repo yet gets `git init` as a step of the plan. |
| `--no-install` | Do not install the profiles' plugins or run their commands. |
| `--verbose` | Print every detail of the steps that run after the plan. `init` and `profile` always show the full plan first, then one status line (`Init` or `Profile NAME`), the problems and notes, the `undo:` line and the next step. |
| `--dry-run` | Print the plan and change nothing. |

In a terminal, `init` asks which agents the repo is for (Enter: the agents that are on for you), unless `--agents` is given or the repo's `.loadout.json` already names its agents (with `--yes` or `--dry-run` it does not ask). Then it asks which profiles (not with `--yes` or `--dry-run`, which take the suggested ones). Without a terminal it takes the repo's agents (`--agents`, or what `.loadout.json` names; else yours), applies no profile unless you name one, pass `--yes` or `--dry-run` (which plan the suggested ones), shows the plan and writes nothing unless `--yes` is given. `git init` is a step of the plan: declining the plan or `--dry-run` skips it, and `loadout restore` cannot undo it (the plan says so). If `CLAUDE.md` exists without `AGENTS.md`, neither file is created and a note says that `/loadout:onboard` will offer the migration. It adds `.serena/cache/` and, when the repo is for Claude Code, `.claude/settings.local.json` to `.gitignore`, under a `# loadout` line.

Exit codes: 0 on success, and also when the plan was declined, when there was no terminal and no `--yes`, for `--dry-run`, and when `.loadout.json` says `"manage": false`. 1 for an unknown profile name (every name is checked before anything changes), an invalid `.loadout.json` or `--agents` value, or when a profile was applied with problems (the run goes on and ends with `Init: applied with problems (below)` or `Profile NAME: applied with problems (below)`). Problems are: a repo file skipped because it is, or lies behind, a symlink out of the repo; a JSON file that is not in a layout loadout can keep (its entries are printed, the file is left as it is); skills not copied; a plugin install or command that failed, a plugin id that is not `name@marketplace`, or a command that is not a list of words; a repo skill that was not linked for an agent the repo is for, or a different item left at the link's place (`not linked`, `left as is`); a committed skill link that this checkout wrote as a plain file (Git without symlinks) is not a problem: it is reported once with the fix; with Codex, a Codex step that failed or was skipped. A `not written` or `not installed` note for an agent that is off for you or not in the repo's list is not a problem. `init` also returns 1 when it skipped `git init` because `.git` points out of the repo.

## loadout profile

Add one profile to the current project. It does what `init` does for a single profile, without the scaffolding.

```
loadout profile [--no-install] [--dry-run] [--yes] [--take-profile] [--verbose] NAME
```

| Flag | Meaning |
|---|---|
| `NAME` | Profile name, for example `thesis`, `web`, `db`, `sonar`, `android`, or one in `<personal>/profiles`. |
| `--no-install` | Do not install the profile's plugins or run its commands. |
| `--dry-run` | Print the plan and change nothing. |
| `--yes` | Apply the plan without asking. Needed without a terminal; without it the plan is shown and nothing is written. |
| `--take-profile` | Where someone changed an entry the profile set, use the profile's value. Without it, a terminal asks once (`Use the profile's values for these? [y/N]`); with `--yes` or without a terminal the repo's values stay. |
| `--verbose` | Print every file, command and note instead of the one status line. |

A re-run merges three-way against what the profile wrote last time ([Applying a profile](profile-format.md#what-applying-a-profile-does), [ADR 0031](../adr/0031-repo-profile-entries-merge-three-way.md)): updates apply by themselves, a teammate's changes stay unless you say yes, and a value you declined is not asked about again.

What `init` and `profile` write in the repo, per agent. The repo's agents come from [`.loadout.json`](#loadoutjson); without that file, from the agents that are on for you.

| | Claude Code (only when the repo is for Claude Code) | Codex (only when the repo is for Codex) |
|---|---|---|
| Profile MCP servers | Merged into `.mcp.json`. | Added as sections to `.codex/config.toml`; `${VAR}` arguments are skipped with the reason. |
| Profile settings | Merged into `.claude/settings.json`. | Not used, except which servers are switched off. |
| Profile plugins (`install`) | `claude plugin install ID --scope project`, only when Claude Code is also on for you. | `codex plugin add`, switched on only in this repo (`enabled = true` in `.codex/config.toml`), only when Codex is also on for you. |
| Profile skills | Copied into `.claude/skills/`; every skill in `.agents/skills` is linked into `.claude/skills`. | Copied into `.agents/skills/` when the repo is for Codex only; every skill in `.claude/skills` is linked into `.agents/skills`. |
| `commands` | Run once, after all file changes; they are not tied to an agent. | |
| Scaffold (`init` only) | `CLAUDE.md` and the `.claude/settings.local.json` line in `.gitignore`. | `AGENTS.md`, `docs/` and the other `.gitignore` entries are for both agents. |
| Next step printed (`init`) | Start Claude Code here and run `/loadout:onboard`. | Start Codex here and ask it to use the `loadout:onboard` skill (printed when Claude Code is off for you or not in the repo's list). |

When the repo is not for Claude Code, the profile's `.mcp.json` and `.claude/settings.json` are not written and the plan says so; files already in the repo stay. When the repo is for an agent that is off for you, you get its files but not its installs, and the plan says which ([ADR 0030](../adr/0030-repo-files-follow-the-repos-agents.md)). Codex reads `.codex/config.toml` only in a trusted project; loadout prints the step and never trusts one for you. Details per field: [In Codex](profile-format.md#in-codex). The format of a profile is in [profile-format](profile-format.md). Exit codes: as for [init](#loadout-init).

## .loadout.json

A committed file at the repo root. `init` and `profile` write it; you can edit it by hand.

```json
{"agents": ["claude", "codex"], "manage": true}
```

| Key | Meaning |
|---|---|
| `agents` | The agents the repo is for: `"claude"`, `"codex"` or both, each once. `init`, `profile` and `configure new skill --to repo` write the files of these agents, whichever agents are on for the user running them. Missing: the agents that are on for the user decide, and the first `init` or `profile` adds the file to its plan. |
| `profiles` | Written by loadout: per profile and file, the entries it wrote (JSON-pointer paths such as `env/MODE`; for a list, the entries loadout added; a value that looks like a secret only as `sha256:…`). Re-runs merge against it; `loadout explain` reads it. Commit it with the files. |
| `manage` | `false` makes every loadout command refuse to write in the repo: it prints its plan, then `manage is false in .loadout.json: nothing written`, and exits 0. Default `true`. |

Other keys are kept when loadout rewrites the file. An invalid file stops every repo-writing command before anything changes: it prints the reason, for example `.loadout.json: agents must be a list of "claude" and "codex" (each once)` or `.loadout.json: profiles must map each profile to its files and their entries …`, and exits 1. A `.loadout.json` in a layout loadout cannot reproduce is left byte for byte: the other files are written, the `profiles` record is not, and the plan says so. Changing its `agents` with `init --agents` in such a file is refused before anything is written (`its layout is not one loadout rewrites; set "agents": [...] by hand`, exit 1). A `.loadout.json` that is a link leading outside the repo is refused the same way.

Changing the list with `init --agents`: an added agent gets its missing files and skill links. A removed agent's files stay; the plan lists them as no longer needed, and removing them is yours to do. `loadout adopt` applies a profile to a repo the same way: it shows the plan and asks before it writes. loadout writes none of this at session start or in the daily sync.

## Repo writes

`init`, `profile` and `configure new skill --to repo` write in a repo only through a plan.

1. **Plan.** One line per change, with its reason: `create` (a new file, with its number of lines and, for JSON, the entries), `change` (the diff: added and changed JSON keys, or unified diff lines for text), `copy` (a skill folder, with its number of files), `link` and `run` (a command). File changes come first; commands run after all of them. Secret values are masked.
2. **Question.** In a terminal: `Apply these changes? [y/N]`. Without a terminal: `no terminal: nothing written (run it again with --yes to apply this plan)`, then `nothing changed`. Declined: `nothing changed`. `--dry-run` stops after the plan.
3. **Apply.** Before each change loadout saves a copy of the file it changes and records every file and folder it creates, in a backup that names the repo. The run ends with `undo: loadout restore <dir>` (`configure new skill`: `backup: <dir>  (undo: loadout restore <dir>)`). A file that changed after the plan was shown (an edit, a `git pull`) is left as is: `changed since the plan, left as is`; run the command again for a new plan. If `.loadout.json` changed in that time, the plan no longer fits the repo's agents and nothing is written.
4. **After the commands.** Skills that a profile's commands installed get a short second plan, `The commands of profile NAME added skills; link them for the repo's other agent:`, with the same question (`--yes` covers it). With Codex on for you, the repo's `.codex/config.toml` is written after the Codex plugin installs and names only the plugins that installed; a failed one gets a note.
5. **Layout kept.** A repo JSON file is rewritten only in the layout it has (indentation or one line, line endings, key order); new keys go at the end. A file that cannot be kept that way is left, and its entries are printed for you to add. Nothing is written through a link that leads outside the repo.

`loadout restore` puts changed files back byte for byte and takes away the files loadout created. A folder loadout created is removed only when it is empty; otherwise it stays and restore prints a `kept` line. It cannot undo a `run` step: a profile's `commands`, and the `git init` of `init`; the plan says so.

## loadout check

Verify this machine. Read-only: it reports problems and names the fix, and never changes anything, also not in VS Code's or a repo's files.

```
loadout check [--verbose]
```

By default it prints `Health check: N of M OK`, then only the warnings and failures, each with a `fix:` line. `--verbose` lists every check. Each listed line is `ok`, `warn` or `FAIL`. Bootstrap runs the same checks at its end. What to do about each warning or failure: [Troubleshooting](../how-to/troubleshooting.md).

Which rows appear depends on the agents that are on (`targets.json`, see [personal-layer](personal-layer.md)): with Claude Code off, the rows marked "Claude Code on" are skipped; with Codex off, nothing about Codex is checked (no `Codex …` rows, no `binary codex`, no Codex extension rows). In WSL, when your only Codex is the Windows one, the `Codex …` rows below, and the Codex parts of the `loadout plugin` and `own tools` rows, are replaced by one `ok` line, `Codex`, that points to `bootstrap.ps1` ([Codex in WSL](../how-to/wsl.md#codex)).

The rows, in the order they are printed:

| Row | What it checks | Severity |
|---|---|---|
| `Python 3.x` | The Python that runs loadout. Always `ok`: loadout needs 3.11 or newer and stops before this on older versions. | — |
| `WSL <version>`, `WSL` | Inside WSL only: the version (an `ok` line), then one `WSL` row per problem from [WSL 2](../how-to/wsl.md): WSL 1 (with Claude Code on), the kit, the personal layer or the current folder on the Windows filesystem, a tool that resolves to a Windows program, missing sandbox packages. The `claude`, WSL 1 and sandbox rows only with Claude Code on. | warn |
| `Codex home` | Inside WSL with Codex on: `CODEX_HOME` points into Windows. | warn |
| `Codex (Windows side)` | Inside WSL with Codex on: the Windows Codex home has sessions from the last 30 days and no loadout block in its `AGENTS.md`. | warn |
| `VS Code` | Inside WSL with Codex set up in WSL: whether VS Code's Codex extension runs the Codex in WSL (`chatgpt.runCodexInWindowsSubsystemForLinux`). A warning when it still runs Codex on Windows (fix: `loadout bootstrap --codex-side wsl --vscode-wsl`, or the manual step), and one warning for each folder's `.vscode/settings.json` or VS Code profile that sets the switch to `false` again. An `ok` line when it runs Codex in WSL. | warn |
| `VS Code settings` | A VS Code `settings.json` that loadout reads (user, profile, or the open folder's) does not parse, so loadout cannot read the settings that matter there. | warn |
| `VS Code (Codex)`, `VS Code (Codex, Windows window)`, `VS Code (Codex, Remote-WSL window)` | One row per Codex extension install and window type, for the agents that are on; `ok` when nothing is missing. Warnings: `chatgpt.cliExecutable` names a file that cannot run; the codex it runs (bundled, or the one `chatgpt.cliExecutable` names) is older than the version loadout needs ([version](../how-to/codex.md#switch-it-on)); the extension has no bundled Codex for this platform; a Windows window reads a Windows `.codex` that loadout has not set up; a Remote-WSL window reads the WSL `~/.codex` while your Codex runs on Windows; and, with no Codex CLI on this side, that plugins do not load in the extension and it has no `/hooks` (fix: the Codex CLI next to it, `loadout bootstrap --install`). | warn |
| `VS Code (Claude Code)`, `VS Code (Claude Code, Windows window)`, `VS Code (Claude Code, Remote-WSL window)` | The same for the Claude Code extension. Warnings: a Windows window reads `%USERPROFILE%\.claude`, which loadout in WSL does not set up; terminal mode (`claudeCode.useTerminal`) starts the `claude` on `PATH` and there is none; `claudeCode.claudeProcessWrapper` names a file that cannot run; the extension has no bundled Claude Code for this platform. | warn |
| `VS Code PATH` | An MCP server whose command an extension's agent may not find: in a Remote-WSL window VS Code's Codex extension gets VS Code's server `PATH` (no shell startup file runs there; fix: `loadout bootstrap --vscode-path`, then restart VS Code's WSL server: close every Remote-WSL window, run `wsl --shutdown` in Windows, reopen); elsewhere the command is not on your shell's `PATH`. loadout's own plugin servers have the `MCP servers on PATH` row instead. | warn |
| `loadout state` | Everything of loadout's in `~/.claude/.loadout` and its `loadout-<timestamp>` folders in `~/.claude/backups` was copied to the new place ([The move out of ~/.claude](state-and-sync.md#the-move-out-of-claude)). Warnings: not everything was copied yet; an old entry was kept because both places have it (compare and delete it by hand); the old folder cannot be read. Old copies waiting to be retired, and Claude Code's own files in `~/.claude/backups`, are not counted. | warn |
| `link <folder>/<name>` | Claude Code on: each link under `~/.claude` (rules, global skills, `hooks/personal`) points to its source. `link rules/personal` fails while `<personal>/rules` does not exist. | FAIL |
| `skills.json` | Your personal `skills.json`, when it exists, is valid JSON. | warn |
| `settings.json` | Claude Code on: `~/.claude/settings.json` is valid JSON. | FAIL |
| `settings drift` | Claude Code on: a kit-managed value was changed in `~/.claude/settings.json`. | warn |
| `plugins installed` | Claude Code on: the plugins enabled in the merged settings are installed. | warn |
| `Codex` | Codex on: a usable codex, new enough ([version](../how-to/codex.md#switch-it-on)): the Codex CLI, or without it VS Code's Codex extension's own codex on this side. In WSL also a warning when the `codex` on `PATH` is the Windows one, or `CODEX_HOME` points into Windows. When this row warns, it is the only `Codex …` row. | warn |
| `Codex plugin` | The loadout plugin is installed in Codex. In extension mode (no Codex CLI) always a warning: only the CLI loads plugins, VS Code's Codex extension loads none. | FAIL with the Codex CLI; warn in extension mode |
| `Codex instructions` | The block in `~/.codex/AGENTS.md` is current (FAIL). An `AGENTS.override.md` that shadows it adds a second `Codex instructions` line (warn). | FAIL; the override line warn |
| `Codex config` | loadout's entries in `~/.codex/config.toml` are current, or a table of yours is in the way ("left as is"). | warn |
| `Codex Serena hooks` | Serena's hooks in `~/.codex/hooks.json` are current ([Serena's hooks in Codex](hooks.md#serenas-hooks-in-codex)); when loadout cannot rewrite the file, the entries to add by hand. | warn |
| `Codex plugins` | Plugins enabled in the merged settings that have no Codex route (their marketplace is not on GitHub). | warn |
| `Codex hooks` | loadout's hooks are approved in Codex's `/hooks`, or changed since you approved them. In extension mode the fix names the Codex CLI, because the extension has no `/hooks`. | warn |
| `Codex logins` | MCP servers waiting for a login. The fix is `codex mcp login NAME`, or in extension mode the extension's MCP settings. | warn |
| `Codex drift` | MCP servers and skills present in only one agent. | warn |
| `loadout plugin (Claude Code)`, `loadout plugin (Codex)`, `loadout plugin (Claude Code, project <path>)`, `loadout plugin (Claude Code, local <path>)` | The installed loadout plugin, per agent that is on, has the kit's files: the same files as the kit's `plugins/loadout/`, with the same bytes and executable bits (not on Windows), and no others (a skill the kit removed would still load from an old copy). Files the agents add (`.in_use`, `__pycache__`) and the eval folders, which never run, are left out. An old copy runs old hooks and skills, which can act on state that has since moved. A Claude Code copy at project or local scope gets its own line; `loadout update` refreshes only the user scope, so its fix is `claude plugin update loadout@agent-loadout --scope project` (or `--scope local`) in that project. No line when the agent has no copy or the loadout plugin is turned off. Unpushed changes in the kit checkout also show as a difference. | warn |
| `duplicate <plugin>` | Claude Code on: an enabled plugin and a claude.ai connector with the same tools (the connector is in "ever connected" in `~/.claude.json`, an undocumented Claude Code field). | warn |
| `own tools` | Tools that loadout does not manage, or a file it reads for them that does not parse. | warn |
| `binary <name>` | Each catalog binary is on `PATH`; a binary tied to an agent (`claude`, `codex`) only while that agent is on, and helpers (`mise`) never. Two exceptions are warnings: `binary codex` when VS Code's Codex extension runs its own (the fix recommends the Codex CLI next to it), and `binary claude` when the Claude Code extension's bundled `claude` is found (loadout then runs that one, see [Environment variables](#environment-variables)). In WSL, `codex` is not checked when your only Codex is the Windows one. | FAIL for a required binary, warn for the others |
| `MCP servers on PATH` | `serena` and `codebase-memory-mcp` are installed but not on the `PATH` a new terminal gets (Claude Code starts them by name). | warn |
| `gh auth` | `gh auth status`, when `gh` is installed. | warn |
| `secrets.env` | `~/.config/loadout/secrets.env` exists and is readable only by you (the permissions are not checked on Windows). | warn |
| `kit repo clean`, `personal repo clean` | The daily sync of the kit and personal git repos is not paused. Uncommitted changes alone are fine; the warning appears only while git refuses the pull, and it names the files (`daily sync paused: local changes the pull would overwrite: <files>`). | warn |
| `repo skill links` | Inside a git repo (not your home folder): committed skill links that the checkout wrote as plain files (Git without symlinks), with the fix. | warn |
| `repo .mcp.json` | Inside a git repo for Claude Code: the committed `.mcp.json` starts a server from a path in one person's home, so teammates' agents cannot start it. loadout does not change the file. | warn |

Exit codes: 0 when nothing failed (warnings do not count); 1 when at least one `FAIL` line was printed.

## loadout usage

```
loadout usage [--days N] [--json]
```

To get the numbers read out, ask your agent, or run `/loadout:usage` (Codex: `$loadout:usage`): the skill runs `loadout usage --json` and compares the shares with the measurement in [ADR 0026](../adr/0026-tool-hints-never-block.md).

Read-only. Counts, per agent and for main sessions and subagents separately, how often each tool family was used in the last N days (default 14): Serena, codebase-memory, Context7, Microsoft Learn, Grep, Glob, Read, the shell, other. It also counts symbol-like searches (the Grep tool, or shell `rg`, `grep`, `egrep` and `git grep`, by the hint's own rule; `find` does not count) and, as one total for both agents, the sessions in the window in which loadout's search or docs hint appeared (the hook keeps its state for 7 days, so a longer window counts only about the last week). It reads the local transcripts of the agents that are on (`~/.claude/projects`, `$CODEX_HOME/sessions`) and prints counts only, never their content. Unreadable lines are skipped and counted.

| Flag | Meaning |
|---|---|
| `--days N` | Look back N days (default 14; values below 1 count as 1). |
| `--json` | Print the counts as JSON: `days`, `hint_sessions`, and per agent (`claude`, `codex`) `main` and `subagent` with `sessions`, `calls`, `symbol_searches` and `families.<name>.calls`/`.sessions`, plus `skipped_lines`. An agent without a transcript folder is left out. |

Exit codes: 0 done (an empty transcript folder prints zero counts); 1 when no agent that is on has a transcript folder (`~/.claude/projects`, `$CODEX_HOME/sessions`).

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

With Claude Code on, it first refreshes the plugin marketplaces (`claude plugin marketplace update`). Then, with Claude Code on, it runs `claude plugin update <id> --scope user` for each plugin that is enabled in the merged settings and installed with user scope, and with Codex on it upgrades the Codex marketplaces and adds each routed plugin again (`codex plugin add`), but only those whose upstream changed: it compares each marketplace's remote head (`git ls-remote`, no prompts) with the one recorded after the last refresh (`codex-marketplaces.json`, see [Machine-local state](personal-layer.md#machine-local-state)), and a plugin with its own unpinned git source by that source's head. A missing plugin is always installed, and whatever cannot be compared (offline, private repository, nothing recorded) is refreshed as before. Without a Codex CLI (extension mode) the Codex plugins are not refreshed: `update` prints that VS Code's Codex extension loads none and that the Codex CLI is needed for them. It names the plugins first and asks once before it touches them (`--yes` answers for you; without a terminal and without `--yes` they stay as they are). It prints one line per plugin that changed (`plugin <id>: updated`) or failed (`plugin <id>: failed: ...`; the others still run), and a closing line to run `/reload-plugins` or restart the agent when something changed. Plugins already at the latest version print nothing. The daily background sync does not run `claude plugin update`; Claude Code updates the marketplaces in `settings.base.json` by itself, and the sync refreshes the Codex plugins after it pulls a new kit (see [the daily sync](state-and-sync.md#the-daily-sync)). Then, for each outdated tool, it picks the package manager that installed it (`pkgmgr.update_plan`):

- `mise upgrade <tool>` when the binary lives under mise's `installs` directory, also behind a mise shim. The mise tool name is the catalog id, or `npm:<package>` for mise's npm backend; a catalog entry can override it with `"mise": "<name>"`. For these tools mise itself decides what is outdated (`mise outdated`), so its `minimum_release_age` and pins are respected.
- `brew upgrade <formula>` when the binary resolves into Homebrew's `Cellar/<formula>/`. Casks and npm packages installed with Homebrew's node are not formulae and keep their own updater.
- Otherwise the `update` command of the catalog entry (`claude update`, `uv self update`, ...). See [Catalog format](catalog-format.md#install-and-update).

For a tool not managed by mise, if the update command succeeds but installs nothing newer, loadout remembers that version in `refused-updates.json` in loadout's state folder (`~/.local/state/loadout` by default, see `XDG_STATE_HOME` under [Environment variables](#environment-variables)) and does not notify again until a newer one appears. A failed update keeps notifying.

The next two steps run only with Claude Code on. If an installer changed `~/.claude/settings.json`, the kit-merged version is put back and the installer's version goes into a backup.

Some installers re-register what the loadout plugin already provides (for example an install of codebase-memory-mcp without `--skip-config` adds its user-scope MCP server and `~/.claude/hooks/cbm-*` scripts). When at least one update command ran and the loadout plugin is enabled, `update` removes only exact duplicates (`maintenance.undo_reregistered`, `duplicates.py`):

- an MCP server with the same name, command, arguments, type and env as the plugin's, and not one of your personal-layer servers;
- a hook that runs the same command as a plugin hook, or is exactly a legacy `~/.claude/hooks/cbm-*` script;
- those scripts' files, when no settings hook references them.

They go into a backup, and `update` prints what it undid and how to restore it. Look-alikes (a forked or reconfigured server, your own context7) are only reported; review them with `loadout adopt`. Skills, plugins and marketplaces are never removed automatically.

Exit codes: 0 when finished (a failed update command is printed but does not change the code); 1 when another loadout run still holds the lock after the wait (on a terminal `update` waits until it is free; without one it waits 10 minutes). Run it again when that run has finished.

## loadout restore

Undo a backup. What it replaces goes into a new backup, so a restore can be undone too.

```
loadout restore [--list] [--last] [--repo PATH] [--show] [--force] [BACKUP_DIR]
```

| Flag | Meaning |
|---|---|
| `BACKUP_DIR` | A directory a loadout command printed (`backup: …` or `undo: loadout restore …`; bootstrap and adopt in their default output print only `Undo any time: loadout restore --list`, and the folder with `--verbose`), for example `~/.local/state/loadout/backups/loadout-<timestamp>` (under `$XDG_STATE_HOME/loadout/backups` when that is set). Commands that print one include bootstrap, adopt, `configure` (the wizard, `prefs`, `set …`, `new skill`), `init`, `profile` and `update`. `loadout restore --list` lists them all. A path from before the move, `~/.claude/backups/loadout-<timestamp>`, still works. |
| `--list` | List backups, newest first, with their paths (for agents and scripts). |
| `--last` | Restore the newest backup of any kind (a later command's backup, or a restore's own, is newer than the one you may mean); it first prints what goes back and, in a terminal, asks `Restore this? [y/N]`; without a terminal it restores without asking, so show the user `--list` first. |
| `--show` | With `BACKUP_DIR`: print what that backup puts back (each file, each undo command, secrets masked) and change nothing. |
| `--repo PATH` | Only the backups made for that repo (with `--list`, `--last` or the pick). |
| `--force` | Replay a backup that was already restored. |

In a terminal, `loadout restore` without a folder shows the last 10 backups, numbered, newest first: how long ago and when, the command that made it, where (`home` or `repo <path>`), what it holds (`3 files, 2 commands`) and `restored <date>` if it was. Answer a number (`m` shows 10 more, Enter cancels); loadout then shows exactly what goes back (each file and each undo command, secrets masked) and asks `Restore this? [y/N]`. After a wrong answer the question comes again; after three wrong answers nothing is restored. A backup that was already restored is refused with the `--force` command to replay it. Without a terminal nothing is picked: loadout lists the backups and names `loadout restore <path>` and `--last`. A backup path goes alone or with `--show`; with `--list` or `--last` it is refused (exit 2) and nothing is restored. Previews mask secrets in paths and commands.

Backups are kept in `backups/` in loadout's state folder (`~/.local/state/loadout/backups` by default), for every user, Codex-only setups included; see [State folders](state-and-sync.md#state-folders). Backups taken before the move restore from the new place. If the old `~/.claude/backups` folder still exists, restore names it: the move has not finished, or a different backup of the same name was kept in both places. Restore only accepts folders under the backups location and only runs the undo commands loadout itself records (`claude mcp add-json|remove -s user`, `claude plugin enable|install … --scope user`, `claude plugin marketplace add`, `codex plugin remove`, `codex plugin marketplace remove`); anything else is refused with a message and exit code 1.

Exit codes: 0 when listing, when nothing was picked or the pick was declined, and when every step succeeded; 1 when the backup has no manifest, was already restored (without `--force`), or a step failed, and for `--show` without a backup path or with a path that holds no backup. 2 for a path given with `--list` or `--last`.

## loadout explain

```
loadout explain FILE
```

Read-only. For a file in the current repo, it lists the entries loadout wrote there (from the `profiles` record in [`.loadout.json`](#loadoutjson)), from which profile, and the state of each: `loadout's value`, `changed in this repo (now …)`, `removed in this repo`, or `cannot compare, the file does not parse`. A value that looks like a secret is shown as `(a secret value, not shown)`. Everything else in the file is yours. For `.loadout.json` it prints the repo's agents, `manage` and how many entries each profile recorded; for `.gitignore`, the lines under its `# loadout` line. A file without recorded entries says so (files `init` created are yours once they exist). Text from the repo is printed with control characters made visible, so a file cannot drive your terminal.

Exit codes: 0 when it printed the entries (or that there are none). 1 outside a git repo, for a missing file without a record, for a missing `.loadout.json` or a missing or unreadable `.gitignore`, for a link that leads outside the repo, and for an invalid `.loadout.json`.

## loadout kit-path

Print the kit's folder (your clone). The doc skills read the kit's `rules/` and `docs/explanation/documentation-strategy.md` from there, so they work the same in Claude Code and Codex.

```
loadout kit-path
```

Exit code: 0.
