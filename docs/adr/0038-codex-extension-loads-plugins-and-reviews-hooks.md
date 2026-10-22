# 0038. VS Code's Codex extension loads plugins and reviews hooks itself

- Status: Accepted
- Date: 2026-10-22
- Source: [Design: Codex extension mode, as the extension really works](../superpowers/specs/2026-10-22-codex-extension-mode-design.md) (live tour case D, VS Code's Codex extension 26.1007 with bundled codex 0.162.0-alpha, no Codex CLI)
- Supersedes: the plugin and hooks parts of the decision in [ADR 0033](0033-codex-for-the-vscode-extension-without-its-cli.md) (extension mode installs no plugins; the Codex CLI is the way to approve hooks). The usability rule, the 0.161 floor and `chatgpt.cliExecutable` stand.

## Context

ADR 0033 set Codex up for VS Code's Codex extension without its CLI on two claims: the extension loads no plugins, and it has no `/hooks`. The live tour disproved both:

- The extension loads plugins that its bundled `codex plugin marketplace add` and `codex plugin add` install into `~/.codex`. `$loadout` then lists loadout's skills, and Settings > MCP servers > "From plugins" shows the plugin's codebase-memory-mcp.
- It has its own hook review: the hooks icon in the prompt bar ("Review hooks · N need approval", Allow all) and Settings > Hooks. Allow all writes the approval to `config.toml` in `[hooks.state]`, the table the CLI's `/hooks` writes.

So a person with only the extension got no loadout skills and no codebase-memory, four warning rows for one cause, a "hooks not approved" warning that never cleared after Allow all, and advice to install a CLI they do not need. The forces:

- The goal is a setup where the person opens VS Code, trusts the folder, clicks Allow all once, and has what a CLI user has.
- loadout does not write hook trust: the approval is Codex's safety gate ([ADR 0036](0036-codex-tool-approvals-and-serena-approval.md)).
- A Codex CLI may sit next to the extension and read the same `~/.codex`, or be broken while the extension works.

## Decision

We will treat the extension's codex as a full Codex for plugins and hooks, and ask the person to approve hooks in the extension.

1. **Plugins in extension mode.** Bootstrap, `loadout update`, the daily sync and `loadout profile` add marketplaces and install plugins with the extension's codex (`codex.program()`), as in CLI mode, with the same timeouts and progress lines. There is no question first.
2. **Hooks.** The person approves them in the extension. loadout never writes into `[hooks.state]`. Every message that said the extension has no `/hooks` names the way instead: the hooks icon in the prompt bar, then Allow all (or Settings > Hooks). `hooks_status` counts only hooks that can exist: Serena's always, and the loadout plugin's only while `config.toml` has `[plugins."loadout@agent-loadout"]` with `enabled = true`. Then Allow all makes the status `trusted` and the step and the `Codex hooks` row clear.
3. **One cause, one row.** Without a Codex CLI next to a usable extension, `loadout check` shows one row, `Codex CLI: not installed (optional: VS Code's Codex extension runs its own)`. It is `ok` and not a problem. The `Codex plugin`, `Codex hooks`, `Codex plugins missing` and `Codex MCP` rows check the real state through the extension's codex. The `binary codex` row and the `VS Code (Codex)` gap about plugins and `/hooks` stop warning.
4. **CLI and extension on one machine.** The CLI installs as before; both read the same `~/.codex`, so one install serves both. The `VS Code (Codex)` row also warns when the extension's codex is older than 0.161, since it may not load what the CLI installed.
5. **Windows, CLI in WSL, extension native.** These are two homes. loadout recommends VS Code's switch that runs the extension's codex in WSL (`--vscode-wsl`) and, declined, names that the extension sees none of loadout's setup. It does not set up a second home.
6. **Machines set up under ADR 0033 without plugins.** The next `loadout update`, bootstrap or daily sync installs the missing plugins. "Now do this" then says to approve the hooks in the extension, and to reload the VS Code window so the extension loads the plugins.
7. **A too-old extension codex.** An extension codex under 0.161, with no usable CLI, still means Codex is not set up, and the line names the extension update, then `loadout update`. From 0.161, a `codex plugin` call that fails as an unknown command skips plugins with one line and sets up the rest. The floor compares major and minor only, so `0.161.0-alpha` passes; a prerelease sorts before its release wherever versions are compared for updates.
8. **A broken CLI next to a working extension.** A Codex CLI on PATH that is unusable (too old, no version, or the Windows codex in WSL), with a usable extension on this side, is passed over: loadout uses the extension's codex for everything, and the `Codex CLI` row warns once with the reason and the fix. `codex.mode()` and `codex.program()` decide this in one place.
9. **The CLI offer is optional.** With `--install`, a terminal is asked `Install the Codex CLI too (optional, for codex in a terminal)? [y/N]`, default No. `--without-codex-cli` still skips it.

## Alternatives considered

- Keep ADR 0033's extension mode and fix only the wording: the extension still gets no loadout skills and no codebase-memory.
- Write the hook approval into `[hooks.state]` for the person: it removes Codex's safety gate, and the state format is Codex's.
- Install plugins only after asking: a second question for what the person already chose by turning Codex on.
- Treat a broken CLI as a failure when the extension works: it blocks a setup that works.

## Consequences

- Good: an extension-only person gets plugins, skills, MCP servers and the daily sync, with one click of Allow all, and `loadout check` is green afterwards.
- Good: a row or step clears after the person did what it said.
- Bad: the extension's own codex is the one that runs `codex plugin`; a very new or old bundled codex changes what loadout can do, and the answer is "update the extension".
- Neutral: the loadout plugin's hook approval is asked only while the plugin is on in `config.toml`. A Codex that installs a plugin without writing that table would not be asked; Codex 0.16x writes it.
- Neutral: loadout's undo records for plugin installs keep `codex ...` and resolve to `program()` when replayed, so the allowlisted undo command still matches.

## In the code

- `cli/loadout/codex.py` (`mode`, `program`, `cli_problem`, `has_codex`, `hooks_status`, `apply_plugins`, `checks`, `CLI_OPTIONAL`, `CLI_UNUSABLE`, `HOOKS_EXTENSION`, `HOOKS_EXTENSION_CHANGED`, `RESTART_EXTENSION`, `PLUGINS_OLD`)
- `cli/loadout/versions.py` (prerelease ordering), `cli/loadout/steps.py`, `cli/loadout/update.py`, `cli/loadout/codex_project.py`, `cli/loadout/bootstrap.py` (`codex_cli_choice`), `cli/loadout/check.py`
- [Codex in VS Code without the CLI](../how-to/vscode.md#codex-in-vs-code-without-the-cli)
