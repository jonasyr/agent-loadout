# 0034. The extensions' own binaries as runners, and VS Code fixes as asked-for plans

- Status: Accepted
- Date: 2026-10-19
- Source: [Design: VS Code extensions as a surface of each agent](../superpowers/specs/2026-10-17-vscode-extensions-design.md), Parts 2 and 3 (shipped in #50 and #51); for `--vscode-wsl`: [Design: repos for chosen agents](../superpowers/specs/2026-10-16-repo-agents-and-careful-ux-design.md), Part 4 (shipped in #47)
- Amends: [ADR 0032](0032-vscode-extensions-are-a-surface-of-an-agent.md) ("loadout changes no VS Code file") and [ADR 0029](0029-codex-on-windows-and-wsl.md) (the WSL switch as a flag, and the settings that override it)

## Context

[ADR 0032](0032-vscode-extensions-are-a-surface-of-an-agent.md) made loadout read-only towards VS Code: it finds the extensions and reports their gaps, and fixes that write were left to their own change.

- The Claude Code extension bundles its own `claude` (`resources/native-binary/claude`) and shares `~/.claude` with the CLI. With Claude Code on and no `claude` on PATH, loadout's `claude plugin` and `claude mcp` commands failed, so an extension-only user got no plugins and no MCP servers.
- A Remote-WSL window runs no shell startup file. The tool folders bootstrap adds to PATH in the shell profile (block `# loadout PATH`) are missing for the extensions' agents and the MCP servers they start. VS Code documents `~/.vscode-server/server-env-setup` as the place for that environment.
- The Codex WSL switch of [ADR 0029](0029-codex-on-windows-and-wsl.md) needed a yes in a terminal. An agent or a script that runs bootstrap without a terminal could not give it.
- A folder's `.vscode/settings.json` wins over the user settings, and an active VS Code profile's settings do too. Either can turn the WSL switch off again. These files belong to the user or the repo.
- Running a binary from an extension folder is a trust decision: loadout starts a program it did not install.

## Decision

We will run the Claude Code extension's own `claude` for loadout's claude commands when no CLI is on PATH, and write VS Code files only as asked-for plans with a backup.

- **The bundled `claude`.** When Claude Code is on and no `claude` is on PATH, every loadout run registers the Claude Code extension's `claude` as `runner.FALLBACK["claude"]`: the newest version of `anthropic.claude-code` in the local extensions folder (`~/.vscode/extensions`, or the folder `VSCODE_EXTENSIONS` names) or in the Remote-WSL server's (`~/.vscode-server/extensions`). VS Code on Windows seen from WSL does not count: its `claude.exe` reads the Windows home. `runner.run` starts the fallback only when its path is absolute and an existing file; `which()` and `have()` keep answering for PATH only. Bootstrap names the binary in a `Claude Code CLI` warning line, and the `binary claude` check row warns: the Claude Code CLI is recommended for a terminal and the extension's terminal mode, not required. Codex's own binary is decided in [ADR 0033](0033-codex-for-the-vscode-extension-without-its-cli.md).
- **VS Code files only when asked.** loadout writes a VS Code file only after a yes in a terminal or a flag, saves a copy first (or records the file as created), and `loadout restore` of that run undoes it:
  - `--vscode-wsl` (since #47) is the yes for the Codex WSL switch of ADR 0029: the one key in the Windows user `settings.json`, by a text edit.
  - `--vscode-path`, or a yes to `Add loadout's tool folders to PATH for VS Code's Remote-WSL windows (~/.vscode-server/server-env-setup, backup first)? [y/N]`, writes a `# loadout PATH` block in `~/.vscode-server/server-env-setup`. The file is created when it is missing, otherwise the block is added and the user's lines stay byte for byte; a link is followed and its target written. Bootstrap asks only when a tool folder is missing from the Remote-WSL PATH, and keeps a block it wrote earlier current.
- **Overrides are named, never edited.** A folder's `.vscode/settings.json` or a VS Code profile that sets `chatgpt.runCodexInWindowsSubsystemForLinux` to `false` is named in bootstrap and `loadout check`, with the fix.
- The session hook and the daily sync never write a VS Code file.

## Alternatives considered

- Require the Claude Code CLI: an extension-only user gets no plugins and no MCP servers, although the extension reads `~/.claude`.
- Let `which()` and `have()` report the fallback too: code that needs a `claude` for a terminal (the extension's terminal mode, printed commands) would think one exists.
- Write `claudeCode.environmentVariables` or VS Code's terminal settings instead of `server-env-setup`: that setting reaches only the Claude process (not VS Code's Codex extension or the MCP servers it starts), and it edits the user's `settings.json`.
- Edit the folder's or the profile's override: it changes a file the user or the repo owns.
- Keep VS Code read-only (ADR 0032 as written): the user does every fix by hand, and an agent without a terminal cannot do the WSL switch.

## Consequences

- Good: an extension-only Claude Code user gets the kit's plugins and MCP servers without a CLI. An agent can do both VS Code fixes without a terminal, with the flags.
- Security: loadout runs a program it did not install. The bundled `claude` runs only from a known extension folder (the local one, `VSCODE_EXTENSIONS`, or the Remote-WSL server's), only as an absolute path to an existing file, and only through `runner.run` with argument lists. It runs mutating commands too (`claude plugin install`, `claude mcp add-json`, `claude mcp remove`). In extension mode the Codex extension's codex likewise runs `codex mcp remove` ([ADR 0033](0033-codex-for-the-vscode-extension-without-its-cli.md)). Whoever can write those folders can already change what the extension itself runs.
- Bad: extensions update themselves, so the binary's path changes with each version; loadout finds it again on every run. A terminal still has no `claude`, and `loadout check` keeps warning until the CLI is installed.
- Neutral: the `server-env-setup` block takes effect when VS Code's WSL server restarts: close every Remote-WSL window, run `wsl --shutdown` in Windows (it stops every WSL distro), then reopen the folder. A `settings.json` loadout cannot edit safely is left as it is, and the manual step is printed.

## In the code

- `cli/loadout/vscode.py` (`bundled_claude`, `use_bundled_claude`, `installs`, `extensions`, `wsl_switch_overrides`, `override_text`, `SERVER_ENV`)
- `cli/loadout/runner.py` (`FALLBACK`, `_fallback`, `run`), `cli/loadout/__main__.py` (the `use_bundled_claude` call before each command)
- `cli/loadout/bootstrap.py` (`setup_vscode_path`, `_vscode_path_step`, `vscode_path_wanted`, `SERVER_ENV_QUESTION`, `_vscode_step`, `codex_gate`, `CLAUDE_BUNDLED`, `RECOMMENDED_WHY`)
- `cli/loadout/wsl.py` (`set_vscode_wsl_mode`), `cli/loadout/check.py` (`_binaries`, `_vscode`), `cli/loadout/commands.py` (`--vscode-wsl`, `--vscode-path`)
- [Use loadout with VS Code](../how-to/vscode.md)
