# Use loadout with VS Code

Use this page if you work in VS Code with the Claude Code extension, the Codex extension, or both, with or without the CLIs. loadout sets up the same agent folders the CLIs read; this page says what each extension sees of that, what it lacks, and the fix. Why it works this way: [ADR 0032](../adr/0032-vscode-extensions-are-a-surface-of-an-agent.md).

## What each extension sees

Both extensions bring their own copy of the agent and do not use the `claude` or `codex` on your PATH. `loadout check` shows one row per extension, `VS Code (Claude Code)` and `VS Code (Codex)`, with the window type added for a Windows window or a Remote-WSL window; every row is a warning, never a failure. A `VS Code settings` row means a settings file does not parse, so loadout cannot read what it sets: fix its JSON (Preferences: Open User Settings (JSON)).

| | Claude Code extension | Codex extension |
|---|---|---|
| Reads | `~/.claude` and `~/.claude.json`, like the CLI: rules, settings, plugins, hooks, MCP servers, `CLAUDE.md`, your login | `~/.codex` (or `$CODEX_HOME`), like the CLI: `config.toml`, `AGENTS.md`, `hooks.json`, MCP servers, your login; skills in `~/.agents/skills` |
| Lacks | Little: it does not run in VS Code's Restricted Mode (trust the folder) | Plugins: loadout's skills (such as `loadout:configure`), superpowers and plugin hooks do not load. `/hooks`: there is no command to approve hooks |
| Fix for what it lacks | Trust the workspace | Use the Codex CLI alongside VS Code (below) |

### The Codex CLI alongside VS Code

`loadout check` shows `VS Code (Codex)` with the warning "plugins do not load" when the Codex CLI is missing (for a local or Remote-WSL window). The fix: install the Codex CLI with `loadout bootstrap --install`, open VS Code's terminal, run `codex` once and approve loadout's hooks in `/hooks`. Use `codex` in that terminal whenever you need a plugin skill; the extension and the CLI share your settings and login.

`loadout check` also warns when the extension's own Codex is older than 0.161: update the extension in VS Code's Extensions view.

## Windows and WSL

Which home an extension reads depends on the window:

| Window | Claude Code extension reads | Codex extension reads |
|---|---|---|
| A Remote-WSL window (`code .` from WSL) | the WSL `~/.claude` | the WSL `~/.codex` |
| A local Windows window | `%USERPROFILE%\.claude` | `%USERPROFILE%\.codex`, or the WSL `~/.codex` when `chatgpt.runCodexInWindowsSubsystemForLinux` is on ([the switch](wsl.md#when-your-only-codex-is-the-windows-one)) |

With loadout in WSL, open your repos with `code .` from WSL, so both extensions read what loadout set up. `loadout check` in WSL warns `VS Code (Claude Code, Windows window)` when the Claude Code extension is installed in VS Code on Windows and loadout has not set up Windows (if you use only Remote-WSL windows, uninstall that Windows copy), and the `VS Code` row when the Codex extension still runs the Windows Codex. To use the Windows window instead, set loadout up on Windows too with `bootstrap.ps1` ([Codex on both sides](wsl.md#codex-on-both-sides)).

### MCP servers in a Remote-WSL window

A Remote-WSL window runs no shell startup file, so folders that your shell adds to PATH (mise's shims, `~/.local/bin`) may be missing when the Codex extension starts an MCP server. `loadout check` warns `VS Code PATH` and names the servers. Fix: give the server an absolute command (for example `/home/you/.local/bin/serena`), or add the folder in `~/.vscode-server/server-env-setup`:

```bash
export PATH="$HOME/.local/bin:$HOME/.local/share/mise/shims:$PATH"
```

Then run "WSL: Restart" in VS Code, or reconnect. The Claude Code extension takes PATH from your login shell, according to its current code; the live tour confirms it.

## A committed .mcp.json with your own path

A repo's `.mcp.json` is shared. When it starts a server from a path in one person's home (`/home/you/…`, `C:\Users\you\…`), teammates' agents cannot start it. `loadout check` in that repo warns `repo .mcp.json` and names the servers. Fix: register that server in local scope (`claude mcp add --scope local …`) or as your user-level server, and remove it from the committed file. loadout never changes the file.

## What loadout does not do here

loadout does not install or update extensions, trust a workspace, approve hooks, or change your MCP entries. An MCP entry you wrote, such as a Serena entry with an absolute command and a fixed `--project`, is used as it is ([Serena already set up](codex.md#what-stays-different)).
