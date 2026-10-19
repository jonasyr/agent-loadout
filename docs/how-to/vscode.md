# Use loadout with VS Code

Use this page if you work in VS Code with the Claude Code extension, VS Code's Codex extension, or both, with or without the CLIs. loadout sets up the same agent folders the CLIs read; this page says what each extension sees of that, what it lacks, and the fix. Which bootstrap flags fit your platform: [Pick your setup](setups.md#recommended-setups). Why it works this way: [ADR 0032](../adr/0032-vscode-extensions-are-a-surface-of-an-agent.md), [ADR 0033](../adr/0033-codex-for-the-vscode-extension-without-its-cli.md) and [ADR 0034](../adr/0034-vscode-extension-binaries-and-vscode-fixes.md).

## What loadout recommends

The home of these is [Recommended setups](setups.md#recommended-setups); in short:

- **Keep the Codex CLI next to VS Code's Codex extension** ([Recommended setups](setups.md#recommended-setups); what you lose without it: [Codex in VS Code without the CLI](#codex-in-vs-code-without-the-cli)).
- **Let `--install` install the Claude Code CLI too** ([Recommended setups](setups.md#recommended-setups); [Claude Code in VS Code without the CLI](#claude-code-in-vs-code-without-the-cli)).
- **In WSL, open repos in a Remote-WSL window** (`code .` from WSL), for both extensions; `--vscode-wsl` is the fix for a Windows window you open anyway ([Recommended setups](setups.md#recommended-setups); [Windows and WSL](#windows-and-wsl)).

## What each extension sees

Both extensions bring their own copy of the agent and do not use the `claude` or `codex` on your PATH. `loadout check` shows one row per extension install, `VS Code (Claude Code)` and `VS Code (Codex)`, with the window type added for a Windows window or a Remote-WSL window; every `VS Code (…)` row is a warning, never a failure. A `VS Code settings` row means a settings file does not parse, so loadout cannot read what it sets: fix its JSON (Preferences: Open User Settings (JSON)).

| | Claude Code extension | VS Code's Codex extension |
|---|---|---|
| Reads | `~/.claude` and `~/.claude.json`, like the CLI: rules, settings, plugins, hooks, MCP servers, `CLAUDE.md`, your login | `~/.codex` (or `$CODEX_HOME`), like the CLI: `config.toml`, `AGENTS.md`, `hooks.json`, MCP servers, your login; skills in `~/.agents/skills` |
| Lacks | Little: it does not run in VS Code's Restricted Mode | Plugins: loadout's skills (such as `loadout:configure`), superpowers and plugin hooks do not load. `/hooks`: there is no command to approve hooks. Restricted Mode: it declares no support for untrusted workspaces either |
| Fix for what it lacks | Trust the workspace | Use the Codex CLI alongside VS Code (below), and trust the workspace |

### The Codex CLI alongside VS Code

`loadout check` shows `VS Code (Codex)` with the warning "plugins do not load" when the Codex CLI is missing (for a local or Remote-WSL window). The fix: install the Codex CLI with `loadout bootstrap --install`, open VS Code's terminal, run `codex` once and approve loadout's hooks in `/hooks`. Use `codex` in that terminal whenever you need a plugin skill; the extension and the Codex CLI share your settings and login.

`loadout check` also warns when the extension's own Codex is older than the version loadout needs ([Switch it on](codex.md#switch-it-on)): update the extension in VS Code's Extensions view.

## Codex in VS Code without the CLI

With VS Code's Codex extension and no Codex CLI on your PATH, loadout still sets Codex up for the extension: the rules block in `AGENTS.md`, `config.toml`, Serena's hooks and the skills. It runs the extension's own Codex for the little it runs. It skips plugins, which the extension does not load.

Without the Codex CLI you lose:

- **Plugins:** loadout's skills (such as `loadout:configure`), superpowers and the plugin hooks.
- **`/hooks`:** the extension has no command to approve hooks, so Serena's hooks in `~/.codex/hooks.json` wait for an approval only the Codex CLI can give.
- **The daily sync, the weekly update check and the notices** from Codex sessions ([At each session start](../reference/state-and-sync.md#at-each-session-start)).

Bootstrap's "Still to do" and `loadout check` name the approval as the one step only the Codex CLI has, and name logins in the extension (gear, MCP servers, Authenticate) instead of `codex mcp login`. `loadout check` warns `binary codex` instead of failing.

When this applies:

- The extension's own Codex must be new enough ([Switch it on](codex.md#switch-it-on)) and report its version. With an older one, or one that gives no version, extension mode is off: bootstrap's Codex step stops with a line that says to update the extension (or install the Codex CLI), and `loadout check` fails `binary codex`.
- With `--install`, bootstrap asks in a terminal whether to install the Codex CLI next to the extension (default yes). Without a terminal, or with `--yes`, it installs it. `--without-codex-cli` leaves it out; when no extension qualifies, or a Codex CLI is already on PATH, bootstrap prints `--without-codex-cli: not used` and goes on as without the flag.
- In WSL, only VS Code's Codex extension in a Remote-WSL window counts (it lives in `~/.vscode-server/extensions` once it is installed in WSL: install it from the Extensions view in a Remote-WSL window, or select Install on a dimmed local copy; [VS Code's WSL docs](https://code.visualstudio.com/docs/remote/wsl)), never the one in a Windows window. The walkthrough [Codex only on Windows with VS Code](setups.md#codex-only-on-windows-with-vs-code) installs the Codex CLI in WSL.

## Claude Code in VS Code without the CLI

With no `claude` on your PATH, loadout runs the Claude Code extension's own binary for its `claude plugin …` and `claude mcp …` commands: the newest copy in a local or Remote-WSL install (from WSL, never a Windows window's, which reads the Windows home). Bootstrap's `Claude Code CLI` line names the binary, and `loadout check` warns `binary claude` instead of failing. `--install` still installs the Claude Code CLI, which a terminal and the extension's terminal mode (`claudeCode.useTerminal`) need; this is the intended path. Without a bundled binary, the CLI is required as before.

## Windows and WSL

Which home an extension reads depends on the window:

| Window | Claude Code extension reads | VS Code's Codex extension reads |
|---|---|---|
| A Remote-WSL window (`code .` from WSL) | the WSL `~/.claude` | the WSL `~/.codex` |
| A local Windows window | `%USERPROFILE%\.claude` | `%USERPROFILE%\.codex`, or the WSL `~/.codex` when `chatgpt.runCodexInWindowsSubsystemForLinux` is on ([the switch](wsl.md#when-your-only-codex-is-the-windows-one)) |

With loadout in WSL, open your repos with `code .` from WSL, so both extensions read what loadout set up. `loadout check` in WSL warns `VS Code (Claude Code, Windows window)` when the Claude Code extension is installed in VS Code on Windows and loadout has not set up Windows (if you use only Remote-WSL windows, uninstall that Windows copy), and the `VS Code` row when VS Code's Codex extension still runs the Windows Codex. To use a Windows window anyway: for VS Code's Codex extension, `loadout bootstrap --codex-side wsl --vscode-wsl` switches it to the Codex in WSL, with a backup (`loadout restore` undoes it); for the Claude Code extension, set loadout up on Windows too with `bootstrap.ps1` ([Codex on both sides](wsl.md#codex-on-both-sides)).

A folder's `.vscode/settings.json` that sets `chatgpt.runCodexInWindowsSubsystemForLinux` to `false` wins over your user settings, and a VS Code profile's does while that profile is active. Run in that repo, `loadout check` names the file in a `VS Code` row (in WSL, with Codex in WSL), and bootstrap names it when it sets up the switch; loadout edits neither.

### MCP servers in a Remote-WSL window

A Remote-WSL window runs no shell startup file, so folders that your shell adds to PATH (mise's shims, `~/.local/bin`) may be missing when VS Code's Codex extension starts an MCP server. `loadout check` warns `VS Code PATH` and names the servers. Fix: `loadout bootstrap --vscode-path` adds a marked block with the folders bootstrap gives your shell to `~/.vscode-server/server-env-setup` (it creates the file if missing, keeps your lines, saves a copy first; `loadout restore` undoes it). In a terminal, bootstrap offers it when one of those folders is missing there. `~/.vscode-server` exists only after the first `code .` from WSL; before that, the flag changes nothing and says so, so run it after that first window. For a command elsewhere, give the server an absolute command (for example `/home/you/.local/bin/serena`), or add its folder in that file yourself:

```bash
export PATH="$HOME/.local/bin:$HOME/.local/share/mise/shims:$PATH"
```

The block takes effect when VS Code's WSL server restarts: close every Remote-WSL window, run `wsl --shutdown` in Windows (it stops every WSL distro), then reopen the folder. In other windows, `VS Code PATH` warns when a server's command (one of yours: in `config.toml` or `~/.claude.json`, or in the repo's `.mcp.json` or trusted `.codex/config.toml`) is not on your shell's PATH: install it, or give it an absolute command. That check uses the PATH `loadout check` runs with; it does not start your login shell (its startup files can prompt or change things), so run it from a plain terminal, not an activated virtualenv, to see what VS Code sees. The Claude Code extension takes PATH from your login shell, according to its current code (not yet confirmed in a live test).

## VS Code on native Windows

With loadout on native Windows (`bootstrap.ps1`, experimental; WSL 2 is recommended, see [Pick your setup](setups.md#native-windows-experimental)), a local VS Code window reads `%USERPROFILE%\.claude` and `%USERPROFILE%\.codex`, which `bootstrap.ps1` sets up. The rest of this page applies as for a local window: the `VS Code (Claude Code)` and `VS Code (Codex)` rows, the `VS Code PATH` row against your shell's PATH, the extensions' own binaries when no CLI is on PATH, and `--without-codex-cli`. `--vscode-wsl`, `--vscode-path` and the `VS Code` switch row are for WSL only: on Windows the two flags change nothing and say so. loadout on Windows does not report a Codex in WSL.

## A committed .mcp.json with your own path

A repo's `.mcp.json` is shared. When it starts a server from a path in one person's home (`/home/you/…`, `C:\Users\you\…`), teammates' agents cannot start it. `loadout check` in that repo warns `repo .mcp.json` and names the servers. Fix: register that server in local scope (`claude mcp add --scope local …`) or as your user-level server, and remove it from the committed file. loadout never changes the file.

## What loadout does not do here

loadout does not install or update extensions, trust a workspace, approve hooks, or change your MCP entries. It writes VS Code files only when you ask: the `chatgpt.runCodexInWindowsSubsystemForLinux` switch (`--vscode-wsl`, or a yes in a terminal) and the PATH block (`--vscode-path`, or a yes), each with a backup ([ADR 0034](../adr/0034-vscode-extension-binaries-and-vscode-fixes.md)). An MCP entry you wrote, such as a Serena entry with an absolute command and a fixed `--project`, is used as it is ([Serena already set up](codex.md#what-stays-different)).
