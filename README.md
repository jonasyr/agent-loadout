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

- **Personal layer:** paste the git URL of your own personal repo to clone it, or leave empty to create a starter one (it asks four short questions about you).
- **Preferences and add-ons:** optionally run the configure wizard.
- **Existing setup:** reviews your current tools and offers to remove duplicates, with a backup first.

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
| Undo what loadout changed | `loadout restore ~/.claude/backups/loadout-<timestamp>` |
| Change preferences or add tools globally | `loadout configure`, or ask Claude: `/loadout:configure` |
| See what is on and why | `loadout configure show` |
| Start a new project | `mkdir app && cd app && loadout init`, then in Claude Code: `/loadout:onboard` |
| Prepare an existing repo | `loadout init` (never overwrites files), then `/loadout:onboard` |
| Add a domain tool to one repo | `loadout profile thesis` (also: `web`, `db`, `sonar`, `android`) |
| Fix outdated or wrong docs in a repo | `/loadout:docs-audit` (thorough; asks when something is unclear) |
| Keep docs current after a feature | `/loadout:docs-sync` |
| Update tool binaries | `loadout update` |
| Re-apply settings after editing your personal layer by hand | `loadout apply-settings` |
| Check that everything is healthy | `loadout check` |

## Command reference

Run `loadout <command> --help` for details.

| Command | What it does | Options |
|---|---|---|
| `loadout bootstrap` | Set up or repair this machine (safe to re-run) | `--install` install missing tools, `--yes` accept defaults, `--no-plugins`, `--no-adopt` |
| `loadout adopt` | Review an existing setup. Dry run unless `--apply` | `--apply`, `--groups remove,migrate`, `--skip NAME,...`, `--yes`, `--no-versions` |
| `loadout restore DIR` | Undo a backup | none |
| `loadout configure` | Wizard for preferences and add-ons | `show`; `set plugin ID on\|off`; `set mcp ID on\|off`; `set pref KEY JSON` |
| `loadout init [PROFILE...]` | Prepare the current project (AGENTS.md, CLAUDE.md, docs/, .gitignore entries, profiles) | `--yes`, `--no-install`, `--dry-run` |
| `loadout profile NAME` | Add one profile to the current project | `--no-install` |
| `loadout check` | Verify this machine | none |
| `loadout apply-settings` | Merge kit and personal settings into `~/.claude/settings.json` | none |
| `loadout update` | Update outdated tool binaries | `--yes` |

## What you get

**Global plugins** (all enabled by default; you can switch any off in your personal layer):

| Plugin | What it does for you |
|---|---|
| loadout | Code-navigation servers (Serena, codebase-memory), tool hooks, the onboard/configure/docs skills, update notices |
| superpowers | A disciplined workflow: brainstorm, plan, test-driven build, verify |
| frontend-design, impeccable | Distinctive UI, then audit and polish it |
| security-guidance | Warns about security mistakes while code is written |
| pyright-lsp, typescript-lsp, rust-analyzer-lsp | Claude sees type errors right after each edit |
| context7, microsoft-docs | Up-to-date library documentation instead of outdated training data |
| commit-commands, claude-md-management | Commits and PRs; keeping CLAUDE.md/AGENTS.md healthy |

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
| `profiles/*.json` | Your own project presets |

You rarely edit these by hand: `loadout configure` does it for you. **To sync them across machines, make the folder a private git repo**; loadout pulls it daily and offers to commit and push after `loadout configure`.

## Staying up to date

| What | How |
|---|---|
| Plugins (including loadout) | Claude Code auto-updates them |
| This kit and your personal layer | Pulled at most once a day in the background, only when you have no local changes |
| Tool binaries | Checked weekly; Claude Code then shows "updates available, run `loadout update`" |

## Secrets

Never put API keys into config files. Put them in `~/.config/loadout/secrets.env` (created for you, readable only by you):

```bash
DATABASE_URL=postgres://readonly:password@localhost/app
```

Bootstrap adds a line to your shell startup file (`.bashrc`/`.zshrc`, or your PowerShell profile) that loads this file. MCP configs reference values as `${DATABASE_URL}`. `loadout adopt` finds keys already sitting in plain text in your MCP configs and offers to move them.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `loadout: command not found` | Add `~/.local/bin` to your `PATH` (Windows: `%USERPROFILE%\.local\bin`) and open a new terminal |
| A plugin or MCP server is missing in Claude Code | Restart Claude Code; then `loadout check` lists what is missing and how to fix it |
| `invalid JSON in .../settings.json` | Fix the syntax error at the reported position, then run `loadout apply-settings` |
| "settings drift" warning | Something changed a kit-managed value. Run `loadout apply-settings`, or put your preferred value in your personal `settings.json` |
| Windows: links were copied instead of linked | Enable Developer Mode (Settings, For developers) and re-run bootstrap; copies still work and are refreshed daily |
| Something went wrong after adopt | `loadout restore <backup path printed by adopt>` |
| A required tool is missing | Re-run `./bootstrap.sh --install`; `loadout check` shows manual install steps for what it cannot install |

## FAQ

**Will it delete my stuff?** No. Anything it removes or replaces is moved into `~/.claude/backups/loadout-<timestamp>`, and `loadout restore` puts it back. Tools it does not know are left alone.

**I already have my own CLAUDE.md, hooks and settings.** They stay. The kit only manages its own keys. `adopt` offers to move your global CLAUDE.md content into your personal layer.

**Does it cost many tokens?** It is built to cost fewer: heavy tools are per-project, and rtk compresses command output. Check with `/context` in Claude Code.

**Codex, Gemini CLI, Cursor?** Not yet. The rules, catalog and docs model are agent-neutral, and support for other agents is on the roadmap.

## Uninstall

```bash
claude plugin uninstall loadout@agent-loadout
rm ~/.claude/rules/loadout ~/.claude/rules/personal ~/.local/bin/loadout
```

Windows: delete `loadout` and `loadout.cmd` in `%USERPROFILE%\.local\bin`, and replace the `rm` links with the copied folders under `%USERPROFILE%\.claude\rules`.

Your `~/.claude/settings.json` keeps the merged values. Remove the kit's `enabledPlugins` and `extraKnownMarketplaces` entries if you want, or restore an older backup from `~/.claude/backups/`. You can also delete the "# loadout secrets" block that bootstrap added to your shell startup file. Your personal layer and `secrets.env` under `~/.config/loadout/` are never touched; delete them yourself if you want them gone.

## Contributing / development

```bash
uv run --python 3.12 --with pytest pytest -q
claude plugin validate . && claude plugin validate plugins/loadout
```

To propose a tool, add or adjust its `catalog.json` entry with a `reason`; that is where the "why" lives.

## License

[MIT](LICENSE)
