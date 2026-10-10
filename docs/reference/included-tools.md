# Included tools

What the kit sets up on a machine: the plugins and settings it manages, what the loadout plugin brings, the command-line tools, the per-project profiles and the optional add-ons. The sources are `settings.base.json`, `plugins/loadout/`, `rules/`, `catalog.json` and `profiles/`. Why each tool was kept or dropped is the `reason` of its entry in [`catalog.json`](../../catalog.json) (format: [Catalog format](catalog-format.md)).

## Global plugins

All are enabled by `settings.base.json`. Switch one off with `loadout configure set plugin ID off`, or with `"enabledPlugins": {"ID": false}` in your personal `settings.json` (see [Personal layer](personal-layer.md)).

| Plugin | What it does for you |
|---|---|
| `loadout@agent-loadout` | The kit's own plugin. See [The loadout plugin](#the-loadout-plugin). |
| `superpowers` | A disciplined workflow: brainstorm, plan, test-driven build, verify. |
| `frontend-design`, `impeccable@impeccable` | Distinctive UI, then audit and polish it. Why both: [ADR 0009](../adr/0009-design-tooling-frontend-design-and-impeccable.md). |
| `security-guidance` | Warns about security mistakes while code is written, and reviews each `git commit`. Its per-turn diff review is off by default to save usage (`ENABLE_STOP_REVIEW=0`, see [Settings](#settings)). |
| `pyright-lsp`, `typescript-lsp`, `rust-analyzer-lsp` | Claude sees type errors right after each edit. They need the language servers listed under [Command-line tools](#command-line-tools). |
| `context7`, `microsoft-docs` | Current library documentation instead of outdated training data. |
| `commit-commands`, `claude-md-management` | Commits and pull requests; keeping `CLAUDE.md` and `AGENTS.md` healthy. |

Plugins without a marketplace name come from `claude-plugins-official`.

## Marketplaces

`settings.base.json` registers three marketplaces, each with `"autoUpdate": true`: `agent-loadout` (this repo), `impeccable` and `academic-research-skills` (used by the `thesis` profile). Claude Code updates their plugins. How to turn that off: [Security and trust](../explanation/security-and-trust.md#opting-out).

## Settings

Besides `enabledPlugins` and `extraKnownMarketplaces`, `settings.base.json` sets:

| Key | Value | Why |
|---|---|---|
| `env.ENABLE_STOP_REVIEW` | `"0"` | Turns off security-guidance's per-turn review. Set it to `"1"` under `env` in your personal `settings.json` to turn it on. |
| `env.MCP_TIMEOUT` | `"60000"` | Gives MCP servers 60 seconds to start; codebase-memory can be slow on first start. |
| `permissions.allow` | `Bash(loadout advisor-mark:*)` | Lets the execution-advisor skill record that it evaluated a plan without a permission prompt. |

How these keys are merged with yours: [Settings merge](settings-merge.md).

## The loadout plugin

`plugins/loadout/` provides:

- **MCP servers:** Serena (symbolic code navigation and editing) and codebase-memory (a code graph for structure and call-chain questions), from `plugins/loadout/.mcp.json`. Both binaries are installed by bootstrap.
- **Skills:** `/loadout:onboard`, `/loadout:configure`, `/loadout:docs-audit`, `/loadout:docs-sync` and `/loadout:execution-advisor`. The documentation skills are described in [Documentation strategy](../explanation/documentation-strategy.md#how-the-kit-keeps-it-true), the advisor in [The execution advisor](../explanation/execution-advisor.md), configure in [Set your working preferences](../how-to/set-preferences.md#by-asking-claude).
- **Hooks:** the session-start maintenance hook, tool hooks for rtk, Serena and codebase-memory, and the execution-advisor hooks. All are listed in [Hooks](hooks.md).

The kit's `rules/` folder is linked to `~/.claude/rules/loadout` and loaded in every session: `tooling.md` (which tool for which question), `workflow.md` (process skills, review, UI checks), `docs-policy.md` and `memory-policy.md` (where facts and notes live) and `rtk.md`.

## Command-line tools

From the `binary` entries in `catalog.json`. `loadout bootstrap --install` installs every missing required and recommended tool that has an install command for your platform, and lists the rest with instructions. `loadout check` fails for a missing required tool and warns for the others.

| Tool | Status | For |
|---|---|---|
| `claude`, `git`, `uv`, `node`, `gh` | required | Claude Code itself, repo sync, Serena's installer, npm-based servers, GitHub access. |
| `serena`, `codebase-memory-mcp` | required | The plugin's two MCP servers. |
| `playwright-cli` | required | Claude checks UIs in a real browser; snapshots stay on disk. Why not a browser MCP server: [ADR 0013](../adr/0013-playwright-cli-instead-of-browser-mcp.md). |
| `rtk` | recommended | Shrinks noisy command output to save tokens. |
| `pyright`, `typescript-language-server`, `rust-analyzer` | recommended | Language servers for the LSP plugins. |

Python 3.10 or newer is needed before any of this runs; see [Getting started](../tutorials/getting-started.md#requirements). Updates: [`loadout update`](cli.md#loadout-update).

## Per-project profiles

Applied to one repo with `loadout profile NAME` or `loadout init`, which suggests profiles by looking at the project. Format and how to write your own: [Profile format](profile-format.md), [Write a personal profile](../how-to/write-a-profile.md).

| Profile | For | Adds |
|---|---|---|
| `thesis` | Academic writing and ML/RAG research | Plugins `academic-research-skills`, `deepeval`, `huggingface-skills` |
| `web` | Web UI work | Playwright skills (`playwright-cli install --skills`), the Chrome DevTools MCP server (off until you enable it in `/mcp`) |
| `db` | Database access | The DBHub MCP server, reading `${DATABASE_URL}` |
| `sonar` | SonarQube static analysis | Plugin `sonarqube` |
| `android` | Android and Kotlin | Plugin `kotlin-lsp` |

## Optional global add-ons

Off by default. `loadout configure` offers them with each one's reason; `loadout configure set plugin ID on` or `set mcp ID on` turns one on. They are the catalog entries with an `offer` key.

| Add-on | What it is |
|---|---|
| Playwright MCP | Playwright as an MCP server. Snapshots land in context, so `playwright-cli` is the default. |
| Chrome DevTools | Performance traces, network and console debugging in Chrome. Heavy context per call. |
| GitHub MCP | The official GitHub MCP server. The `gh` CLI covers most needs with less context. |
| hookify | Guard-rail hooks written as plain-language rules. |
| Exa | Web, code and paper search. Needs an API key and is paid per query. |
| Sentry | Sentry issues and traces while debugging production errors. |
| DBHub (global) | One database you use from every repo, reading `${DATABASE_URL}`. Otherwise use the `db` profile per project. |
