# agent-loadout

**One command turns any machine's Claude Code into a clean, current, well-configured setup, and keeps it that way.**

Claude Code gets much better with the right plugins, MCP servers and instructions. But setups drift: every machine ends up different, old tools linger, versions go stale, and half of what is installed never gets used. loadout fixes that:

- **Curated defaults.** A small set of tools that complement each other instead of overlapping. Every keep/drop decision is explained in [`catalog.json`](catalog.json).
- **Works on existing setups.** It shows what it would change and why, asks you first, and backs everything up. Undo is one command.
- **Stays up to date by itself.** Plugins auto-update; the kit and your personal settings sync daily; you get a notice when tool binaries have updates.
- **Yours on top.** Your preferences live in a separate *personal layer*. Change them with a wizard in the terminal, or by asking Claude.
- **Projects too.** One command prepares any repo, empty or years old, for agent work. One skill audits and fixes its documentation.

**Requirements:** Linux, macOS or Windows; Claude Code, git, Python 3.10+, Node.js, uv and the GitHub CLI (`gh`). `--install` installs what it can; anything it cannot install is listed with instructions. On Windows, Git for Windows (Git Bash) is also needed for Claude Code hooks.

## Quick start (5 minutes)

```bash
git clone https://github.com/jonasyr/agent-loadout ~/agent-loadout
cd ~/agent-loadout
./bootstrap.sh --install          # Windows (PowerShell): .\bootstrap.ps1 --install
```

Keep the clone where it is: the installed links point into it.

Bootstrap asks a few questions along the way:

- **Personal layer:** paste the git URL of your own personal repo to clone it, or leave empty to create a starter one (it asks four short questions about you, then the [working preferences](#your-personal-layer)).
- **Preferences and add-ons:** optionally run the configure wizard.
- **Existing setup:** reviews your current tools (`loadout adopt`): it offers to remove superseded or duplicate tools, disable per-project tools globally, and move plaintext secrets into `secrets.env`, and asks what to do with tools loadout does not manage: record them globally (they follow you to every machine), put them in a personal profile for some repos, leave them on this machine, or remove them. Without an answer they stay as they are. A backup comes first, and a final "Apply N changes?" question. Binary updates and installs (which run package-manager or installer commands) are never pre-selected; each command is shown and confirmed.

Without a terminal (CI, `ssh host ./bootstrap.sh`, piped input) bootstrap never changes your existing setup: it skips adopt and the configure prompt and tells you so. Pass `--yes` to accept the safe defaults instead.

Then **restart Claude Code** and verify:

```bash
loadout check
```

If `loadout: command not found`, see [Troubleshooting](#troubleshooting).

## How it works

```
┌────────────── loadout (this repo, shared) ──────────────┐     ┌──── personal layer (yours) ───┐
│ plugins/loadout  hooks, MCP servers, skills             │     │ rules/me.md    who you are    │
│ rules/           how Claude should use the tools        │  +  │ settings.json  your overrides │
│ catalog.json     what is good, superseded, optional     │     │ mcp.json       extra servers  │
│ profiles/        per-project add-ons (thesis, web, ...) │     │ profiles/      your presets   │
└─────────────────────────────────────────────────────────┘     └───────────────────────────────┘
                              │  loadout merges both
                              ▼
   ~/.claude/  (your existing settings are kept; the kit only manages its own keys)
```

## Common tasks

| I want to... | Run |
|---|---|
| Set up a new machine | `./bootstrap.sh --install` |
| Clean up a machine that already has a Claude Code setup | `loadout adopt` (shows the plan only), then `loadout adopt --apply` |
| Undo what loadout changed | `loadout restore --list`, then `loadout restore ~/.claude/backups/loadout-<timestamp>` |
| Change preferences or add tools globally | `loadout configure`, or ask Claude: `/loadout:configure` |
| See what is on and why | `loadout configure show` |
| Start a new project | `mkdir app && cd app && loadout init`, then in Claude Code: `/loadout:onboard` |
| Prepare an existing repo | `loadout init` (never overwrites files), then `/loadout:onboard` |
| Add a domain tool to one repo | `loadout profile thesis` (also: `web`, `db`, `sonar`, `android`) |
| Fix outdated or wrong docs in a repo | `/loadout:docs-audit` (thorough; asks when something is unclear) |
| Keep docs current after a feature | `/loadout:docs-sync` |
| Decide how to run a finished plan (inline, subagents or a mix) | `/loadout:execution-advisor` (offered automatically after a plan is written) |
| Update tool binaries | `loadout update` |
| Re-apply settings after editing your personal layer by hand | `loadout apply-settings` |
| Check that everything is healthy | `loadout check` |

## Command reference

Run `loadout <command> --help` for details.

| Command | What it does | Options |
|---|---|---|
| `loadout bootstrap` | Set up or repair this machine (safe to re-run) | `--install` install missing tools, `--yes` accept defaults (never binary updates), `--no-plugins`, `--no-adopt` |
| `loadout adopt` | Review an existing setup. Dry run unless `--apply`; without a terminal, `--apply` needs `--yes` or `--groups` (otherwise exit code 2) | `--apply`, `--groups remove,migrate`, `--skip NAME,...`, `--yes`, `--own NAME=CHOICE,...`, `--no-versions` |
| `loadout restore DIR` | Undo a backup. Whatever it replaces goes into a new backup, so a restore can be undone too | `--list` (newest first), `--force` (replay an already restored backup) |
| `loadout configure` | Wizard for preferences and add-ons | `show` (lists each add-on's and preference's id); `prefs` (only the working-preference questions); `set plugin ID on\|off`; `set mcp ID-or-server-name on\|off`; `set pref-choice ID OPTION`; `set pref KEY JSON`; `--first-run` (ask the "about you" questions again) |
| `loadout configure own` / `configure set own NAME CHOICE` | List the tools loadout does not manage (`--all` adds the ones you left on this machine), or decide one: `global`, `project:<profile>`, `leave`, `remove` | `--all` |
| `loadout init [PROFILE...]` | Prepare the current project (AGENTS.md, CLAUDE.md, docs/, .gitignore entries, profiles) | `--yes`, `--no-install`, `--dry-run` |
| `loadout profile NAME` | Add one profile to the current project | `--no-install` |
| `loadout check` | Verify this machine | none |
| `loadout apply-settings` | Merge kit and personal settings into `~/.claude/settings.json` | none |
| `loadout update` | Update outdated tool binaries (through mise/Homebrew when they manage the tool), then undo duplicates an installer re-registered | `--yes` |

## What you get

**Global plugins** (all enabled by default; you can switch any off in your personal layer):

| Plugin | What it does for you |
|---|---|
| loadout | Code-navigation servers (Serena, codebase-memory), tool hooks, the onboard/configure/docs/execution-advisor skills, update notices |
| superpowers | A disciplined workflow: brainstorm, plan, test-driven build, verify |
| frontend-design, impeccable | Distinctive UI, then audit and polish it |
| security-guidance | Warns about security mistakes while code is written, and reviews each `git commit`. The per-turn Opus diff review is off by default (`ENABLE_STOP_REVIEW=0`, to save usage) — set it to `"1"` under `env` in your personal settings.json to turn it on |
| pyright-lsp, typescript-lsp, rust-analyzer-lsp | Claude sees type errors right after each edit |
| context7, microsoft-docs | Up-to-date library documentation instead of outdated training data |
| commit-commands, claude-md-management | Commits and PRs; keeping CLAUDE.md/AGENTS.md healthy |

**After a plan.** When superpowers writes an implementation plan (`docs/superpowers/plans/*.md`), Claude runs `/loadout:execution-advisor` in the same turn instead of asking the planner's own execution question; if it forgets, a plugin hook asks it once for that plan, and the advisor's answer then explicitly replaces the planner's. The advisor judges each task (complete code in the plan, coupling, risk, steps that need you, size, context, cost) and recommends Inline, subagent-driven or a Hybrid with a per-task table of mode, model tier and review, instead of defaulting to subagents, with a cost class and review policy. You confirm before anything runs. Hybrid runs under superpowers:executing-plans, with delegated tasks dispatched to subagents and one shared `progress.md` ledger.

**Command-line tools** (installed by `--install` where possible): `serena`, `codebase-memory-mcp`, `playwright-cli` (Claude checks UIs in a real browser), `rtk` (shrinks noisy command output to save tokens), and the language servers `pyright`, `typescript-language-server`, `rust-analyzer`.

**Per-project profiles** (`loadout profile NAME`):

| Profile | For |
|---|---|
| `thesis` | Academic writing and ML/RAG research |
| `web` | Web UI work: Playwright skills, Chrome DevTools MCP (off by default) |
| `db` | Database access via DBHub MCP |
| `sonar` | SonarQube static analysis |
| `android` | Android / Kotlin |

`loadout init` suggests profiles by looking at your project. You can also write your own in `<personal layer>/profiles/NAME.json`.

**Optional global add-ons** (turn on with `loadout configure`; the wizard shows each one's reason): Playwright MCP, Chrome DevTools, GitHub MCP, hookify, Exa search, Sentry, and a global DBHub database connection.

## Your personal layer

Your preferences live in `~/.config/loadout/personal` (or wherever `LOADOUT_PERSONAL` points):

| File | Purpose |
|---|---|
| `rules/me.md` | Who you are and how you like to work; loaded in every session |
| `settings.json` | Your overrides, e.g. `"effortLevel": "high"` or `"enabledPlugins": {"impeccable@impeccable": false}` |
| `mcp.json` | Extra MCP servers you want everywhere |
| `skills/<name>/`, `skills.json`, `hooks/` | Skills and hook scripts you recorded as global (see [Your own tools](#your-own-tools)) |
| `profiles/*.json` | Your own project presets |
| `profiles/skills/<name>/` | Skills used by your profiles; copied into a repo by `loadout profile` |

**Working preferences** are a fixed set of questions defined in the kit's [`preferences.json`](preferences.json): answer language, commit style, AI attribution in commits/PRs, answer style, destructive actions, effort level, extended thinking, agent push notifications, the auto mode trust environment, and the language of commits and docs. `loadout configure prefs` asks them (Enter keeps the current answer), `loadout configure set pref-choice ID OPTION` sets one, and `loadout configure show` lists them.

- Answers go only into your personal layer: text answers as lines in a block of `rules/me.md` between `<!-- loadout:preferences:start -->` and `<!-- loadout:preferences:end -->`, the others into `settings.json` (AI attribution goes into both).
- Your own lines in `me.md` are read to recognise answers you already gave (e.g. a "Language: …" line), but never moved or rewritten. When you change an answer that one of your lines also states, loadout names that line and, in a terminal, offers to remove it (with a backup). Only a line that is exactly one of the kit's own preference lines moves into the block, and only when the block is written anyway.
- Values in your existing `~/.claude/settings.json` count as answers too, so re-running changes nothing you already decided. If something there, a legacy `includeCoAuthoredBy`, or one of your `me.md` lines (e.g. "never add Co-Authored-By") still contradicts a choice, loadout names it instead of claiming success.
- A first run (bootstrap's starter layer, `configure --first-run`) starts unanswered questions at the recommended defaults; without a terminal it takes them silently.
- The auto mode environment is drafted from the git remotes under your code folder (default `~/Documents/Code`). You choose which owners are yours (nothing is preselected when several are equally common), see the full draft, and must confirm it; it replaces an existing personal `autoMode.environment` and is skipped without a terminal.

You rarely edit these by hand: `loadout configure` does it for you. **To sync them across machines, make the folder a private git repo**; loadout pulls it daily and offers to commit and push after `loadout configure` (not while a `*.env` file would be committed: secrets belong in `~/.config/loadout/secrets.env`).

### Your own tools

`loadout adopt` lists every plugin, marketplace, MCP server, skill and hook that is not in the catalog under **YOUR OWN TOOLS**. Items already in your personal layer or in a personal profile show as keep. For each item you choose:

| Choice | Meaning |
|---|---|
| `global` | Record it in your personal layer, so it follows you to every machine. |
| `project:<profile>` | Disable it globally and write it into a personal profile; adopt then offers to apply that profile to repos. |
| `leave` | Stay as is, on this machine only. Not asked again here. |
| `remove` | Remove it. It goes into a backup and `loadout restore` brings it back. |

Nothing changes without an answer. An empty answer, three invalid answers, `--yes` and runs without a terminal decide nothing and remember nothing; only an explicit `leave` is remembered (in `~/.claude/.loadout/own-decisions.json`, local to this machine). Catalog plugins that adopt would disable globally accept `global` ("keep global"). Not every choice fits every item: marketplaces and skills that are links to a shared source cannot go into a profile, and servers outside `~/.claude.json` cannot be recorded.

Without a terminal: `loadout adopt --apply --own "foo@bar=global,my-db=project:mydb,notes=leave"`. Items not named stay as they are. If a name matches several kinds, write `<kind>:<name>`. A name listed twice, an unknown name or a bad choice exits with code 2 before anything changes. `loadout configure own` lists the items later; `loadout configure set own NAME CHOICE` decides one. `loadout check` warns "N tool(s) not managed by loadout" and checks `skills.json`.

Where each choice writes (global, in your personal layer):

| Kind | Personal layer | This machine |
|---|---|---|
| Plugin | `settings.json`: `enabledPlugins`, plus the marketplace in `extraKnownMarketplaces` | unchanged |
| Marketplace | `settings.json`: `extraKnownMarketplaces` | unchanged |
| MCP server | `mcp.json`, secrets rewritten to `${VAR}` and moved to `secrets.env` | the server is re-added with the `${VAR}` config and managed by loadout |
| Skill (folder) | copied to `skills/<name>/` | replaced by a link to the copy; the original goes into the backup |
| Skill (link to a shared source) | a pointer in `skills.json` | unchanged |
| Hook | `settings.json`: `hooks`; a local script under `$HOME` is copied to `hooks/` and the command points to `$HOME/.claude/hooks/personal/<file>` | the hook is replaced by the recorded one, so it does not run twice |

With `project`, the item goes into a personal profile instead (`profiles/<name>.json`; skills into `profiles/skills/<name>/`) and is disabled or removed from your global setup. `loadout profile` copies a profile's skills into a repo and never overwrites an existing one.

Secrets: nothing that looks like a secret is written to the personal layer. Recording refuses an MCP server whose secret sits in `args`, the URL or a multi-line value, and any hook command, hook script or skill file that still looks secret after the `${VAR}` rewrite. Move the secret to `secrets.env`, use `${VAR}`, then try again. Every file of a skill is scanned; an unreadable file refuses too.

**Known limits**

- An MCP server is managed by loadout only if it is in `managed-mcp.json` or its config in `~/.claude.json` is identical to the personal one; otherwise loadout leaves your server alone. Recording through adopt seeds `managed-mcp.json`.
- A plugin recorded on one machine reaches another through the daily pull of your personal layer. Claude Code then installs it at its next start, in the background; it is active after `/reload-plugins` or a new session. loadout does not install it itself. `LOADOUT_NO_AUTO_PULL=1` stops the pull, and with it this.
- A profile is copied into a repo when applied. Later changes to the personal profile do not reach repos until you apply it again, and skill copies in a repo can drift from your personal layer.
- A skill recorded as a pointer to a shared source is linked only on machines where that source exists.
- A hook whose command points outside `$HOME`, or a hook in exec form (`args`), is recorded as it is and only works where that path exists. Adopt prints a note.
- For a hook script only the script file is copied, even behind an interpreter (`/bin/sh ~/x.sh`). Files it reads next to it must be copied into `hooks/` by hand.
- A hook matcher that contains a comma cannot be named in `--own`; use the interactive prompt.

## Staying up to date

| What | How |
|---|---|
| Plugins (including loadout) | Claude Code auto-updates them |
| This kit and your personal layer | Pulled at most once a day in the background, only when you have no local changes |
| Tool binaries | Checked weekly; Claude Code then shows "updates available, run `loadout update`" |

`loadout update` updates a tool through the package manager that installed it: `mise upgrade <tool>` when the binary lives under mise's `installs` directory (also behind a mise shim), `brew upgrade <formula>` when it resolves into Homebrew's `Cellar/<formula>/` (casks and npm packages installed with Homebrew's node keep their own updater), otherwise the tool's own updater (`claude update`, `uv self update`, ...). The mise tool name is the catalog id, or `npm:<package>` for mise's npm backend; a catalog entry can override it with `"mise": "<name>"`. For mise-managed tools, mise itself decides what is outdated (`mise outdated`), so its `minimum_release_age` and pins are respected. For other tools, if an update command succeeds but installs nothing newer, loadout remembers that version and does not notify you again until a newer one appears; a failed update keeps notifying.

Some installers re-register what the loadout plugin already provides (for example `codebase-memory-mcp update` re-adds its user-scope MCP server, `~/.claude/.mcp.json` and `~/.claude/hooks/cbm-*`). While the loadout plugin is enabled, `loadout update` removes only exact duplicates of it: an MCP server with the same name, command, arguments, type and env as the plugin's (and not one of your personal-layer servers), a hook that runs the same command as a plugin hook or is exactly a legacy `~/.claude/hooks/cbm-*` script, and those scripts' files when no settings hook references them. They go into a backup, and loadout prints what it undid and how to restore it. Look-alikes (a forked or reconfigured server, your own context7) are only reported; review them with `loadout adopt`. Skills, plugins and marketplaces are never removed automatically.

## Security & trust

loadout is self-updating, so it is worth knowing what runs without asking:

- **Plugins and marketplaces** with `"autoUpdate": true` (the kit's own, and the third-party ones in `settings.base.json`) are updated by Claude Code. A plugin can ship hooks, so an update can run new code in your next session.
- **This kit and your personal layer** are pulled once a day (`git pull --ff-only`, only when the checkout has no local changes). After a pull, loadout re-merges settings into `~/.claude/settings.json`, applies your personal `mcp.json`, and the next session runs the pulled `loadout` code and the plugin's hooks.
- **Tool binaries are never updated silently**; `loadout update` shows each command and asks.

To opt out:

- set `"autoUpdate": false` for a marketplace in your personal `settings.json`, e.g. `{"extraKnownMarketplaces": {"impeccable": {"autoUpdate": false}}}`;
- set `LOADOUT_NO_AUTO_PULL=1` in your environment to stop the daily pull (run `git pull` in the kit and personal folders yourself).

For a team, use a fork of this repo that you control (and point `LOADOUT_ROOT` or your clone at it), so changes reach colleagues only after you review them.

Backups under `~/.claude/backups/` can contain old configs and undo commands with secrets in them; they are created readable only by you (0700/0600). Delete old ones when you no longer need them.

## Secrets

Never put API keys into config files. Put them in `~/.config/loadout/secrets.env` (created for you, readable only by you):

```bash
DATABASE_URL='postgres://readonly:password@localhost/app'
```

Write values in single quotes; a `'` inside a value is written as `'\''`. That way the shell never runs or mangles part of a value. Bootstrap adds a line to your shell startup file (the one for your `$SHELL`, plus an existing `.bashrc`/`.zshrc`; on Windows both the Windows PowerShell and PowerShell 7 profiles) that loads this file. MCP configs reference values as `${DATABASE_URL}`.

`loadout adopt` finds keys sitting in plain text and never prints them. Secrets in user-scope MCP servers in `~/.claude.json` can be moved to `secrets.env` automatically; it also reports (for you to move by hand) secrets in project-scoped servers, `~/.claude/.mcp.json`, your personal `mcp.json`, the `env` block of `~/.claude/settings.json`, and URL query strings.

Secrets loaded by your shell only reach Claude Code started from that shell. On Windows, if PowerShell's execution policy is `Restricted`, profiles do not run; bootstrap prints the command to allow them (`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`) but does not change it.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `loadout: command not found` | Add `~/.local/bin` to your `PATH` (Windows: `%USERPROFILE%\.local\bin`) and open a new terminal |
| `npm error code EACCES` when installing pyright / typescript-language-server / playwright-cli | Your global npm prefix is root-owned (e.g. `/usr`). Either `npm config set prefix ~/.local` (then re-run `loadout bootstrap --install`), or install them with your version manager, e.g. `mise use -g npm:pyright npm:typescript-language-server` |
| A plugin or MCP server is missing in Claude Code | Restart Claude Code; then `loadout check` lists what is missing and how to fix it |
| `invalid JSON in .../settings.json` | Fix the syntax error at the reported position, then run `loadout apply-settings` |
| "settings drift" warning | Something changed a kit-managed value. Run `loadout apply-settings`, or put your preferred value in your personal `settings.json` |
| Windows: links were copied instead of linked | Enable Developer Mode (Settings, For developers) and re-run bootstrap, which switches back to links; copies still work and are refreshed after each daily sync. Edit the source in your personal layer, not the copy: an edited copy is moved into a backup on the next refresh (the session notice names it) |
| Something went wrong after adopt | `loadout restore <backup path printed by adopt>` (`loadout restore --list` shows all backups) |
| `adopt --apply` exits with code 2 | It was run without a terminal. Add `--yes` (safe defaults) or `--groups remove,migrate,...` |
| Windows: "cannot take JSON arguments (Windows .cmd shim)" | The npm-installed `claude.cmd` cannot receive JSON safely, so loadout changes nothing. Best fix: install the native `claude.exe` and re-run. Otherwise open the private `manual-commands.txt` (path printed): with Claude Code closed, add the JSON block it shows under `"mcpServers"` in `%USERPROFILE%\.claude.json` (the file also has the macOS/Linux shell form) |
| A required tool is missing | Re-run `./bootstrap.sh --install`; `loadout check` shows manual install steps for what it cannot install |

## FAQ

**Will it delete my stuff?** No. Anything it removes or replaces is moved into `~/.claude/backups/loadout-<timestamp>`, and `loadout restore` puts it back. Restore itself moves whatever it replaces into a new backup first, and files loadout created (such as a new `me.md` or `secrets.env`) are moved aside, not deleted. Plugins are uninstalled with `--keep-data`. Tools it does not know are left alone. Restore undoes what loadout removed or replaced; it does not take back additions such as the rules links, the secrets line appended to an existing shell rc file or the kit's keys in `settings.json` (see Uninstall for those).

**I already have my own CLAUDE.md, hooks and settings.** They stay. The kit only manages its own keys. `adopt` offers to move your global CLAUDE.md content into your personal layer. Plugins, MCP servers, skills and hooks loadout doesn't know are listed under *Your own tools*; you decide per item.

**Does it cost many tokens?** It is built to cost fewer: heavy tools are per-project, and rtk compresses command output. Check with `/context` in Claude Code.

**Codex, Gemini CLI, Cursor?** Not yet. The rules, catalog and docs model are agent-neutral, and support for other agents is on the roadmap.

## Uninstall

```bash
claude plugin uninstall loadout@agent-loadout
claude plugin marketplace remove agent-loadout
rm ~/.claude/rules/loadout ~/.claude/rules/personal ~/.local/bin/loadout
rm -r ~/.claude/.loadout          # loadout's state (snapshots, timestamps)
```

Windows: delete `loadout` and `loadout.cmd` in `%USERPROFILE%\.local\bin`, and delete the folders `%USERPROFILE%\.claude\rules\loadout`, `%USERPROFILE%\.claude\rules\personal` and `%USERPROFILE%\.claude\.loadout`.

MCP servers from your personal `mcp.json` were added with `claude mcp add-json -s user`; remove them with `claude mcp remove -s user NAME` if you no longer want them. Plugins that bootstrap installed stay installed; uninstall them with `claude plugin uninstall ID` if you want.

Your `~/.claude/settings.json` keeps the merged values. Remove the kit's `enabledPlugins` and `extraKnownMarketplaces` entries if you want, or restore an older backup from `~/.claude/backups/`. You can also delete the "# loadout secrets" block that bootstrap added to your shell startup file. Your personal layer and `secrets.env` under `~/.config/loadout/` are never touched; delete them yourself if you want them gone.

## Contributing / development

```bash
uv run --python 3.12 --with pytest pytest -q
claude plugin validate . && claude plugin validate plugins/loadout
```

Skill evals: run `plugins/loadout/evals/run.sh [--case <name>] [--runs N]`. They make real model calls (a full run costs about $8). Never run `claude plugin eval` on the plugin directly. The scaffolds refuse to run without run.sh's stubs and global-state checks. The browser routing case is opt-in: `run.sh --eval-dir evals-browser`.

To propose a tool, add or adjust its `catalog.json` entry with a `reason`; that is where the "why" lives.

## License

[MIT](LICENSE)
