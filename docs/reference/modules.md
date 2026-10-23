# Modules

Every module of the `loadout` CLI and every other part of the kit, grouped by what it does. Use it to find the file to read or change. How the parts work together is in [Architecture](../explanation/architecture.md).

## The CLI: `cli/loadout/`

Python 3.11+, standard library only. `bin/loadout` starts it; `__init__.py` holds only the package docstring.

### Entry and plumbing

| Module | What it does |
|---|---|
| `__main__.py` | The command line: the parser, `init` and `profile`, the state-move gate that runs before every command (see [The move out of ~/.claude](state-and-sync.md#the-move-out-of-claude)), and the switch to the Claude Code extension's `claude` when none is on `PATH`. |
| `commands.py` | Registers the other subcommands: `restore`, `adopt`, `check`, `apply-settings`, `hook-session-start` and `maintenance` (internal), `update`, `bootstrap`, `configure`, `advisor-mark` (internal), `usage`, `kit-path`, `explain`. Kept apart from `__main__.py` to avoid import cycles. |
| `paths.py` | Every location, derived from `HOME` (and the variables in [Environment variables](cli.md#environment-variables)) at call time, so tests can redirect it. |
| `runner.py` | The only place external commands run, always as argument lists. It finds programs only in absolute `PATH` folders. `runner.FALLBACK` maps a program to an absolute path that `run()` starts when the program is not on `PATH`; `vscode.use_bundled_claude` puts the Claude Code extension's bundled `claude` there. `have()` and `which()` still answer for `PATH` only. On Windows it refuses to pass cmd.exe metacharacters to a `.cmd` shim; `write_manual_commands` then writes such commands to `manual-commands.txt` for you to run. |
| `jsonio.py` | JSON load and save (atomic writes) and the deep merge. |
| `out.py` | Calm output: one status line per step, details only with `--verbose`, problems always; no colour with `NO_COLOR` or `TERM=dumb`. |
| `ui.py` | Prompt helpers shared by the interactive commands. |
| `migrate.py` | Moves loadout's own files out of `~/.claude` in two steps, copy and retire ([ADR 0025](../adr/0025-state-in-xdg-state-home.md); [details](state-and-sync.md#the-move-out-of-claude)). |

### Setting up a machine

| Module | What it does |
|---|---|
| `bootstrap.py` | `loadout bootstrap`: first-time setup and repair, safe to re-run. It also writes the PATH block for `--vscode-path` (`setup_vscode_path`) and asks whether to install the optional Codex CLI next to VS Code's Codex extension. |
| `answers.py` | Checks the `--answers` file that bootstrap reads when there is no terminal ([Set loadout up from inside an agent](../how-to/install-with-an-agent.md)). |
| `adopt.py` | `loadout adopt`: moves an existing machine's setup onto the kit. |
| `link.py` | Links the kit's and your rules, skills and hook scripts into `~/.claude` (or copies them when links do not work: copy mode), and puts `loadout` on `PATH`. |
| `settings_merge.py` | The three-way merge into `~/.claude/settings.json` ([Settings merge](settings-merge.md)). |
| `personal_mcp.py` | Adds your personal `mcp.json` servers to Claude Code at user scope; touches only servers it added. |
| `secrets.py` | Finds, redacts and stores plaintext secrets (values go to `secrets.env`, only names elsewhere). |
| `backup.py` | Timestamped backups with an undo manifest; restore first backs up what it would overwrite (`pre-restore`). |
| `restore_cmd.py` | `loadout restore`: a path, `--list`, `--last`, `--show`, or a numbered pick in a terminal. |

### Keeping it current and checking it

| Module | What it does |
|---|---|
| `maintenance.py` | The session hook (`hook-session-start`), the background daily and weekly run (`maintenance`), the pull both it and `loadout update` use (`pull`, with the pause record `sync-paused.json`) and the tool-update helpers; `update` there only hands over to `update.py` ([The daily sync](state-and-sync.md#the-daily-sync)). |
| `update.py` | `loadout update`: takes the lock, pulls, restarts into the pulled code, builds and shows the numbered plan, asks once, applies it and prints What changed and Now do this ([ADR 0035](../adr/0035-loadout-update-brings-a-machine-current.md); [`loadout update`](cli.md#loadout-update)). |
| `apply.py` | The apply steps bootstrap, configure and update share (links, settings merge, Claude Code plugins, the Codex step). Each returns its status text and the facts of what it changed; with `dry=True` it changes nothing. |
| `steps.py` | "Now do this": derives each agent's open steps from what a run changed, saves them in `open-steps.json`, shows them at that agent's session start and clears them when done ([state-and-sync](state-and-sync.md#at-each-session-start)). |
| `locks.py` | The run locks `maintenance.lock` and `codex.lock`: a foreground command waits for the holder, the background job does not; a crashed holder's lock is taken over ([The background run](state-and-sync.md#the-background-run)). |
| `check.py` | `loadout check`: reports problems and names each fix; changes nothing. |
| `catalog.py` | Reads tool knowledge from `catalog.json`. |
| `versions.py` | Installed and latest versions of catalog tools; a network failure means "unknown". |
| `pkgmgr.py` | Updates a tool through the package manager that installed it (mise, Homebrew). |
| `duplicates.py` | Exact duplicates of what the loadout plugin ships: the only things `loadout update` removes without asking. |
| `inventory.py` | Lists a machine's Claude Code setup and classifies it against the catalog (used by `adopt`, `check`, `configure`, `own` and `update`). |
| `own.py` | Your own tools, which loadout does not manage: record them in the personal layer or a personal profile, leave them, or remove them ([Handle your own tools](../how-to/your-own-tools.md)). |
| `searches.py` | The one parser for symbol-like searches in a tool call (`a\|b` alternations, every search of a compound command line); `usage.py` uses it. |
| `cbm.py` | codebase-memory's `auto_index` from the `cbm_auto_index` preference: set, record, undo ([preference](preferences-format.md#codebase-memorys-auto_index)). |
| `usage.py` | `loadout usage`: how often the agents used each tool family, counted from local transcripts; read-only. |
| `advisor.py` | `loadout advisor-mark <plan>`: records that the execution advisor evaluated a plan. It loads the plugin's `hooks/advisor.py`, so both share one format. |

### Preferences and agents

| Module | What it does |
|---|---|
| `preferences.py` | Structured working preferences from `preferences.json`; answers go only into the personal layer (`rules/me.md`, `settings.json`, `loadout.json`). A preference for some agents only is skipped while they are off. |
| `configure.py` | The `loadout configure` wizard. |
| `new_skill.py` | `loadout configure new skill`: a `SKILL.md` stub in one of the three places a skill of yours can live. |
| `targets.py` | Which agents loadout sets up (`targets.json` in the personal layer). |

### Repos

| Module | What it does |
|---|---|
| `project.py` | `loadout init` and `loadout profile`. |
| `profiles.py` | Profiles from the personal layer and the kit: settings and `.mcp.json` fragments, plugins to install and the marketplaces they need ([ADR 0037](../adr/0037-marketplaces-only-when-a-plugin-uses-them.md)). |
| `detect.py` | Suggests profiles from the files in a repo. |
| `scaffold.py` | Creates missing repo files from `templates/project`; never overwrites. |
| `repo_config.py` | The repo's `.loadout.json`: its agents, `manage`, and the record of what each profile wrote ([ADR 0030](../adr/0030-repo-files-follow-the-repos-agents.md)). |
| `repo_writes.py` | Repo writes as a plan: collected, shown, then applied with a backup ([Repo writes](cli.md#repo-writes)). |
| `repo_merge.py` | The three-way merge of a profile's entries into a repo JSON file, against the record ([ADR 0031](../adr/0031-repo-profile-entries-merge-three-way.md)). |
| `explain.py` | `loadout explain FILE`: which entries loadout wrote in a repo file, from which profile, and whether each is unchanged; read-only. |
| `skill_links.py` | Finds committed skill links that a checkout wrote as plain files (Git without symlinks) and reports the fix; never repairs them. |

### Codex

| Module | What it does |
|---|---|
| `codex.py` | Codex as a second target: the rules block in `AGENTS.md`, owned `config.toml` entries, plugins, skill links, the drift check. `mode()` and `program()` pick the codex: the CLI, or without a usable one VS Code's Codex extension's own (extension mode), which gets the same setup, plugins included ([Use loadout with VS Code](../how-to/vscode.md)). |
| `codex_hooks.py` | Serena's hooks as owned entries in `~/.codex/hooks.json` ([ADR 0028](../adr/0028-serena-codex-hooks-in-hooks-json.md)). |
| `codex_project.py` | The Codex side of `init` and `profile`: the repo's `.codex/config.toml`, `.agents/skills` and plugins. |

### Platforms

| Module | What it does |
|---|---|
| `wsl.py` | WSL detection, the problems it can see from inside WSL, which side Codex runs on, and the VS Code WSL switch that `--vscode-wsl` sets ([Use loadout on Windows with WSL 2](../how-to/wsl.md)). |
| `vscode.py` | VS Code and the agents' extensions, read-only: where VS Code is (local, a Windows window seen from WSL, a Remote-WSL server), which agent extensions it has, their bundled binaries, the settings and overrides that matter, and the Remote-WSL server's `PATH`. `use_bundled_claude` registers the Claude Code extension's `claude` in `runner.FALLBACK`. The files that `--vscode-path` and `--vscode-wsl` write are written by `bootstrap.py` and `wsl.py` ([ADR 0032](../adr/0032-vscode-extensions-are-a-surface-of-an-agent.md)). |

## The plugin: `plugins/loadout/`

| Part | What it is |
|---|---|
| `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json` | The plugin's manifests for Claude Code and Codex. The marketplace that lists it is `.claude-plugin/marketplace.json` at the repo root. |
| `.mcp.json`, `.codex-mcp.json` | The plugin's MCP servers: Serena and codebase-memory in Claude Code; only codebase-memory in Codex, where loadout writes Serena into `config.toml` instead. |
| `skills/` | The plugin's skills: `configure`, `docs-audit`, `docs-sync`, `execution-advisor`, `onboard`, `usage`. |
| `hooks/hooks.json`, `hooks/codex.json` | The hooks for Claude Code and for Codex ([Hooks](hooks.md)). |
| `hooks/run.sh` | Runs a hook command only when its program is on `PATH`; `--soft` and `--python` as described in [Hooks](hooks.md). |
| `hooks/tool_hint.sh`, `hooks/tool_hint.py` | The docs hint for library-docs web lookups (Claude Code): a fast bash filter, then the Python script. Code searches are Serena's `remind` hook. |
| `hooks/mcp_guard.py` | The guard that runs Serena's hooks for Claude Code (and Serena's `remind` for Codex with `--agent codex`) and stays silent when Serena is absent, off for the folder, or already hooked by the user, or when `remind` would see a harmless search ([the guard](hooks.md#the-guard)). |
| `hooks/harmless.py` | Decides whether a call is a search or read Serena's symbolic tools cannot help with (piped output, config and docs, files outside the folder); it mirrors Serena's shell parsing ([ADR 0040](../adr/0040-serena-remind-skips-harmless.md)). |
| `hooks/cbm_project.py` | Session and subagent start: names the folder's codebase-memory project ([details](hooks.md#the-codebase-memory-project-pointer)). |
| `hooks/refresh.py` | Re-indexes a stale codebase-memory graph in the background ([details](hooks.md#the-code-graph-refresh)). |
| `hooks/advisor.py` | The execution advisor's `record` and `stop` hooks. |
| `hooks/reload_check.py` | Claude Code only: says once per session to run `/reload-plugins` after a plugin update, and clears the saved `/reload-plugins` step once the session runs loadout's newly installed plugin. |
| `hooks/typecheck.py` | Codex only: runs the language's type checker after an edit. |
| `hooks/subagent-context.sh` | Gives a subagent the tool routing, with exact tool names. |
| `evals/` | The skill evals: `run.sh` (the only way to run them), the cases, `bin/` stubs, `lib/`, `mocks/`, `fixtures/` ([Run the skill evals](../how-to/run-evals.md)). |
| `evals-browser/` | The opt-in browser routing case (`run.sh --eval-dir evals-browser`). |

## The rest of the kit

| Part | What it is |
|---|---|
| `bootstrap.sh`, `bootstrap.ps1` | The entry scripts (the one-liners): clone the kit when needed, then run `loadout bootstrap`. `bootstrap.ps1` is for native Windows (experimental). |
| `bin/loadout`, `bin/loadout.cmd` | The launchers. `bin/loadout` restarts itself under a Python 3.11+ that uv finds when it was started by an older one; `loadout.cmd` starts it on Windows. |
| `catalog.json` | Tool knowledge: what is good, superseded or optional, how to install and update each tool ([Catalog format](catalog-format.md)). |
| `profiles/` | The kit's profiles (`android`, `db`, `sonar`, `thesis`, `web`) ([Profile format](profile-format.md)). |
| `rules/` | The kit's rules, linked into `~/.claude/rules/loadout` and copied into loadout's block in `~/.codex/AGENTS.md`. |
| `settings.base.json` | The Claude Code settings the kit manages ([Settings merge](settings-merge.md)). |
| `preferences.json` | The working preferences loadout asks about ([Preferences format](preferences-format.md)). |
| `templates/personal/` | The starter personal layer (`rules/me.md`, `settings.json`). |
| `templates/project/` | The files `init` creates when missing: `AGENTS.md`, `CLAUDE.md`, `docs/README.md`, `docs/adr/README.md`. |
| `.claude/skills/diagrams` | A repo-local skill for editing the docs diagrams; Codex finds it through the pointer in `.agents/skills/diagrams`. |
| `.claude/agents/codex-reviewer.md` | A stand-in for Codex's GitHub review when its quota is used up ([CONTRIBUTING](../../CONTRIBUTING.md)). |
| `.github/` | CI (`ci.yml` on Linux, Windows and WSL 2; `fresh-machine.yml` for CLI and bootstrap changes, and weekly), the issue forms and the PR template. |
| `demo/` | The README demo: the VHS tapes, the sandbox, the container render ([CONTRIBUTING](../../CONTRIBUTING.md)). |
| `dev/codex-sandbox.sh` | Runs loadout's Codex part against the real Codex CLI in a throwaway `HOME` and `CODEX_HOME`. |
| `tests/` | The test suite (`fake_home` and `fake_runner` fixtures). |
| `docs/` | These docs; start at [docs/README.md](../README.md). |
