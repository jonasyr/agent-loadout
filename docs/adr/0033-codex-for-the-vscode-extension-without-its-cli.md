# 0033. Codex set up for VS Code's Codex extension without its CLI

- Status: Accepted
- Date: 2026-10-19
- Source: [Design: VS Code extensions as a surface of each agent](../superpowers/specs/2026-10-17-vscode-extensions-design.md), Part 2 (shipped in #50)
- Amends: [ADR 0024](0024-codex-parity-update-model.md) ("usable" includes Codex without its CLI, with no plugins to refresh)

## Context

VS Code's Codex extension runs its own bundled codex. It shares `config.toml`, `AGENTS.md`, the skills in `~/.agents/skills`, the MCP servers and the login with the Codex CLI, but it loads no plugins and has no `/hooks` ([ADR 0032](0032-vscode-extensions-are-a-surface-of-an-agent.md)). Its bundled codex can be older than loadout's Codex setup needs (0.145 on a test machine; loadout needs 0.161).

loadout's Codex setup needed the Codex CLI on PATH. Without it, Codex counted as not usable ("codex not found on PATH") and the Codex step was skipped. A user who works only in the extension got no rules block, no MCP servers and no skills, although the extension reads all of them.

The forces:

- The Codex CLI adds what the extension lacks: plugins (loadout's skills, superpowers, plugin hooks) and `/hooks`, where Serena's hooks are approved. The daily sync, the weekly check and loadout's notices start from a plugin hook.
- Requiring the CLI fails an extension-only user who never asked for it.
- Installing the CLI without asking adds a tool the user did not choose.

## Decision

We will set Codex up for VS Code's Codex extension when there is no Codex CLI on PATH (extension mode), and recommend the CLI next to it.

- Codex counts as usable without a CLI when a Codex extension on this side (a local install or the Remote-WSL server; not VS Code on Windows seen from WSL) runs a codex 0.161 or newer: its bundled one, or the file its `chatgpt.cliExecutable` setting names. An older one, or one that gives no version, is the reason Codex is not usable, with the fix: update the extension, or install the Codex CLI.
- In extension mode loadout writes what the extension reads: the rules block in `~/.codex/AGENTS.md`, its owned `config.toml` tables, Serena's hooks in `hooks.json` and the skill links in `~/.agents/skills`. It installs and refreshes no Codex plugins, because the extension loads none and they install through the CLI. `loadout check` shows the `Codex plugin` row as a warning, and `loadout update` says why it skips them.
- loadout's own `codex mcp` commands run the extension's codex (`codex.program()`).
- The Codex CLI next to the extension is recommended, not required. In a terminal, `bootstrap --install` asks `Install the Codex CLI alongside VS Code (for /hooks and plugins)? [Y/n]`; Enter is yes. Without a terminal, `--install` installs it. `--without-codex-cli` declines. A missing Codex CLI is then a warning (the Prerequisites line and the `binary codex` check row), never a failure.

## Alternatives considered

- Require the Codex CLI: an extension-only user gets a failing setup and none of the files the extension reads.
- Install the Codex CLI without asking: one more tool the user did not choose.
- Install Codex plugins in extension mode anyway: the extension loads none, and they install through the CLI.

## Consequences

- Good: an extension-only user gets the rules, MCP servers, skills and Serena's hooks, and `loadout check` names what is missing, each with its fix.
- Bad: without the Codex CLI there are no plugins (loadout's skills, superpowers, plugin hooks) and no `/hooks`, so Serena's hooks wait for an approval in the CLI. The daily sync, the weekly check and the notices start from a plugin hook: with Codex as the only agent, nothing starts them. When Claude Code's session hook starts the daily sync, it refreshes the extension-mode Codex setup too.
- Security: in extension mode loadout runs a binary it did not install, from a VS Code extension folder or the file `chatgpt.cliExecutable` names: the same program the extension runs. It runs through `runner.run` with argument lists. Besides `--version` and `codex mcp list`, this includes one write: `codex mcp remove` (`codex.remove_server`, used by `loadout adopt` when it removes a Codex server or records it in the personal layer), which saves `config.toml` first.
- Neutral: "usable" in [ADR 0024](0024-codex-parity-update-model.md) now includes extension mode, where there are no plugins to refresh. The extension's codex is asked `--version` once per binary and process; extensions update themselves, so it is found again on every run.

## In the code

- `cli/loadout/codex.py` (`unavailable`, `extension_state`, `program`, `apply_plugins`, `checks`, `remove_server`, `PLUGINS_EXTENSION`)
- `cli/loadout/vscode.py` (`extensions`, `bundled_version`, `too_old`, `CODEX_MIN`)
- `cli/loadout/bootstrap.py` (`CODEX_CLI_QUESTION`, `codex_cli_choice`, `codex_recommended`, `RECOMMENDED_WHY`, `_prereq_summary`)
- `cli/loadout/check.py` (`_binaries`), `cli/loadout/maintenance.py` (`update`), `cli/loadout/commands.py` (`--without-codex-cli`)
- [Use loadout with VS Code](../how-to/vscode.md)
