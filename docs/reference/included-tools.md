# Included tools

What the kit sets up on a machine (how the tools work together: [The toolset](../explanation/the-toolset.md)): the plugins and settings it manages, what the loadout plugin brings, the command-line tools, the per-project profiles and the optional add-ons. The sources are `settings.base.json`, `plugins/loadout/`, `rules/`, `catalog.json` and `profiles/`. Why each tool was kept or dropped is the `reason` of its entry in [`catalog.json`](../../catalog.json) (format: [Catalog format](catalog-format.md)).

## Global plugins

All are enabled by `settings.base.json`. Switch one off with `loadout configure set plugin ID off`, or with `"enabledPlugins": {"ID": false}` in your personal `settings.json` (see [Personal layer](personal-layer.md)). With Codex on, switching a plugin off also switches it off in Codex when Codex has it installed ([how](personal-layer.md#files)). Switching it on again turns it back on there.

| Plugin | What it does for you | Project |
|---|---|---|
| `loadout@agent-loadout` | The kit's own plugin. See [The loadout plugin](#the-loadout-plugin). | this repo |
| `superpowers` | A disciplined workflow: brainstorm, plan, test-driven build, verify. | [obra/superpowers](https://github.com/obra/superpowers) |
| `frontend-design`, `impeccable@impeccable` | Distinctive UI, then audit and polish it. Why both: [ADR 0009](../adr/0009-design-tooling-frontend-design-and-impeccable.md). | [frontend-design](https://github.com/anthropics/claude-plugins-official/tree/main/plugins/frontend-design), [pbakaus/impeccable](https://github.com/pbakaus/impeccable) |
| `security-guidance` | Warns about security mistakes while code is written, and reviews each `git commit`. Its per-turn diff review is off by default to save usage (`ENABLE_STOP_REVIEW=0`, see [Settings](#settings)). | [security-guidance](https://github.com/anthropics/claude-plugins-official/tree/main/plugins/security-guidance) |
| `pyright-lsp`, `typescript-lsp`, `rust-analyzer-lsp` | Claude sees type errors right after each edit. They need the language servers listed under [Command-line tools](#command-line-tools). Codex: a type-check hook instead, see [Hooks](hooks.md). | [Anthropic's official plugins](https://github.com/anthropics/claude-plugins-official) |
| `context7`, `microsoft-docs` | Current library documentation instead of outdated training data. | [upstash/context7](https://github.com/upstash/context7), [MicrosoftDocs/mcp](https://github.com/MicrosoftDocs/mcp) |
| `commit-commands`, `claude-md-management` | Commits and pull requests; keeping `CLAUDE.md` and `AGENTS.md` healthy. | [commit-commands](https://github.com/anthropics/claude-plugins-official/tree/main/plugins/commit-commands), [claude-md-management](https://github.com/anthropics/claude-plugins-official/tree/main/plugins/claude-md-management) |

Plugins without a marketplace name come from `claude-plugins-official`.

With Codex on, the plugins enabled here are installed in Codex too, from the same marketplaces (Codex reads Claude Code marketplaces), when their marketplace is on GitHub; one without such a route is listed by `loadout check` (`Codex plugins`).

## Marketplaces

`settings.base.json` registers four marketplaces, each with `"autoUpdate": true`: `agent-loadout` (this repo), `impeccable`, `academic-research-skills` (used by the `thesis` profile) and `life-sciences`. The `life-sciences` marketplace carries the Wiley Scholar Gateway plugin, which is known but not enabled: use the claude.ai connector or enable the plugin, not both. Claude Code updates their plugins. How to turn that off: [Security and trust](../explanation/security-and-trust.md#opting-out).

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

- **MCP servers:** Serena (symbolic code navigation and editing) and codebase-memory (a code graph for structure and call-chain questions), from `plugins/loadout/.mcp.json`. Both binaries are installed by bootstrap. In Codex the same plugin comes from the same marketplace, but it brings only codebase-memory (`plugins/loadout/.codex-mcp.json`); Serena comes from `~/.codex/config.toml` in its Codex mode, or your own Serena when you set one up ([ADR 0028](../adr/0028-serena-codex-hooks-in-hooks-json.md)).
- **Skills:** `/loadout:onboard`, `/loadout:configure`, `/loadout:docs-audit`, `/loadout:docs-sync`, `/loadout:execution-advisor` and `/loadout:usage` (a short report from [`loadout usage`](cli.md#loadout-usage): how often the agents used Serena, the code graph, Context7 and Microsoft Learn, and whether the [tool hints](hooks.md) changed that). The documentation skills are described in [Documentation strategy](../explanation/documentation-strategy.md#how-the-kit-keeps-it-true), the advisor in [The execution advisor](../explanation/execution-advisor.md), configure in [Ask your agent about loadout](../how-to/ask-about-loadout.md).
- **Hooks:** the session-start maintenance hook, tool hooks for rtk, Serena and codebase-memory, loadout's tool hints, the subagent routing card, and the execution-advisor hooks. Codex gets a variant of them plus a type-check hook. All are listed in [Hooks](hooks.md).

The kit's `rules/` folder is loaded in every session. Claude Code reads it through the link `~/.claude/rules/loadout`; Codex reads it from the marked block that loadout keeps in `~/.codex/AGENTS.md` (`$CODEX_HOME/AGENTS.md`), a copy that loadout refreshes at set times (see [Personal layer](personal-layer.md#files)). It holds `tooling.md` (which tool for which question), `workflow.md` (process skills, review, UI checks), `docs-policy.md` and `memory-policy.md` (where facts and notes live) and `rtk.md`.

## Command-line tools

From the `binary` entries in `catalog.json`. `loadout bootstrap --install` installs every missing required and recommended tool that has an install command for your platform, and lists the rest with instructions. `loadout check` fails for a missing required tool and warns for the others.

| Tool | Status | For | Project |
|---|---|---|---|
| `claude`, `git`, `uv`, `node`, `gh` | required | Claude Code itself, repo sync, Serena's installer, npm-based servers, GitHub access. `claude` is checked and installed only while Claude Code is on. | [uv](https://github.com/astral-sh/uv), [gh](https://github.com/cli/cli) |
| `codex` | required while Codex is on | OpenAI's Codex CLI, installed through mise (`mise use -g codex`). Entries with a `target` in `catalog.json` count only while that agent is chosen in `targets.json`. loadout needs codex 0.161 or newer. | [openai/codex](https://github.com/openai/codex) |
| `mise` | helper | Installs Node.js, gh, rust-analyzer and codex (`mise use -g`) when they are missing. Not installed otherwise, and `loadout check` does not report it. | [jdx/mise](https://github.com/jdx/mise) |
| `serena`, `codebase-memory-mcp` | required | The plugin's two MCP servers. | [oraios/serena](https://github.com/oraios/serena), [DeusData/codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp) |
| `playwright-cli` | required | Claude checks UIs in a real browser; snapshots stay on disk. Why not a browser MCP server: [ADR 0013](../adr/0013-playwright-cli-instead-of-browser-mcp.md). | [microsoft/playwright-cli](https://github.com/microsoft/playwright-cli) |
| `rtk` | recommended | Shrinks noisy command output to save tokens. | [rtk-ai/rtk](https://github.com/rtk-ai/rtk) |
| `pyright`, `typescript-language-server`, `rust-analyzer` | recommended | Language servers for the LSP plugins. Codex has no LSP plugins; its [type-check hook](hooks.md) runs `pyright`, `tsc` or `cargo` instead, whichever is on `PATH`. | [pyright](https://github.com/microsoft/pyright), [typescript-language-server](https://github.com/typescript-language-server/typescript-language-server), [rust-analyzer](https://github.com/rust-lang/rust-analyzer) |

codebase-memory-mcp is installed and updated with its install script and `--skip-config`, so it does not register a second MCP server next to the plugin's ([ADR 0019](../adr/0019-upstream-installers-without-agent-configuration.md)). On Windows, bootstrap uses `install.ps1`.

Python is provided by uv; git and curl are the only prerequisites ([Before you start](../tutorials/getting-started.md#before-you-start)). Updates: [`loadout update`](cli.md#loadout-update).

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
