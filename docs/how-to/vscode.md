# Use loadout with VS Code

Use this page if you work in VS Code with the Claude Code extension, VS Code's Codex extension, or both, with or without the CLIs. loadout sets up the same agent folders the CLIs read; this page says what each extension sees of that, what it lacks, and the fix. Which bootstrap flags fit your platform: [Setup matrix](../reference/setup-matrix.md) ([how to pick](setups.md)). Why it works this way: [ADR 0032](../adr/0032-vscode-extensions-are-a-surface-of-an-agent.md), [ADR 0033](../adr/0033-codex-for-the-vscode-extension-without-its-cli.md), [ADR 0034](../adr/0034-vscode-extension-binaries-and-vscode-fixes.md) and [ADR 0038](../adr/0038-codex-extension-loads-plugins-and-reviews-hooks.md).

## What loadout recommends

The flags for each platform are in the [Setup matrix](../reference/setup-matrix.md); in short:

- **VS Code's Codex extension alone is a full setup.** The Codex CLI next to it is optional, for `codex` in a terminal ([Setup matrix](../reference/setup-matrix.md); [Codex in VS Code without the CLI](#codex-in-vs-code-without-the-cli)).
- **Let `--install` install the Claude Code CLI too** ([Setup matrix](../reference/setup-matrix.md); [Claude Code in VS Code without the CLI](#claude-code-in-vs-code-without-the-cli)).
- **In WSL, open repos in a Remote-WSL window** (`code .` from WSL), for both extensions; `--vscode-wsl` is the fix for a Windows window you open anyway ([Setup matrix](../reference/setup-matrix.md); [Windows and WSL](#windows-and-wsl)).

## What each extension sees

Both extensions bring their own copy of the agent and do not use the `claude` or `codex` on your PATH. `loadout check` shows one row per extension install, `VS Code (Claude Code)` and `VS Code (Codex)`, with the window type added for a Windows window or a Remote-WSL window; every `VS Code (…)` row is a warning, never a failure. Without a Codex CLI, one `Codex CLI` row says it is optional and counts as no problem. A `VS Code settings` row means a settings file does not parse, so loadout cannot read what it sets: fix its JSON (Preferences: Open User Settings (JSON)).

| | Claude Code extension | VS Code's Codex extension |
|---|---|---|
| Reads | `~/.claude` and `~/.claude.json`, like the CLI: rules, settings, plugins, hooks, MCP servers, `CLAUDE.md`, your login | `~/.codex` (or `$CODEX_HOME`), like the CLI: `config.toml`, `AGENTS.md`, `hooks.json`, plugins, MCP servers, your login; skills in `~/.agents/skills` |
| Lacks | Little: it does not run in VS Code's Restricted Mode | Nothing loadout sets up. It has its own hook review instead of `/hooks`, and it does not run in VS Code's Restricted Mode |
| Step 1 | Trust the workspace (Restricted Mode: Trust Folder & Continue) | Trust the workspace (Trust Folder & Continue), then approve the hooks: the hooks icon in the prompt bar, then Allow all |

### The Codex CLI alongside VS Code

The Codex CLI is optional next to the extension. Both read the same `~/.codex`, so what loadout installs once serves both. Without `--install`, bootstrap installs nothing and asks nothing. With `--install`, it asks in a terminal whether to install it, default No (`[y/N]`); without a terminal, or with `--yes`, it installs it. `--without-codex-cli` skips the question and the install. Install it only if you want `codex` in a terminal.

`loadout check` warns `VS Code (Codex)` when the extension's own Codex is older than the version loadout needs ([Switch it on](codex.md#switch-it-on)): update the extension in VS Code's Extensions view. With a Codex CLI next to the extension, the same row warns that an old extension may not load what the CLI installed.

A Codex CLI on PATH that is unusable (too old, no version, or the Windows codex in WSL) next to a working extension: loadout uses the extension's Codex for everything and the `Codex CLI` row warns once, with the reason and the fix.

## Codex in VS Code without the CLI

With VS Code's Codex extension and no Codex CLI on your PATH, loadout sets Codex up fully for the extension: the rules block in `AGENTS.md`, `config.toml`, Serena's hooks, the skills and the plugins (loadout's skills such as `loadout:configure`, superpowers, codebase-memory-mcp). It installs the plugins with the extension's own bundled Codex, and bootstrap, `loadout update`, the daily sync and `loadout profile` do the same. The daily sync, the weekly update check and the notices from Codex sessions work as with the CLI ([At each session start](../reference/state-and-sync.md#at-each-session-start)).

Do this, in order:

1. Open the folder in VS Code and choose Trust Folder & Continue (Restricted Mode). The extension does not run in an untrusted workspace.
2. Run `loadout bootstrap`.
3. In VS Code, click the hooks icon in the prompt bar ("Review hooks · N need approval"), then Allow all. Or use Settings > Hooks.
4. If bootstrap says so, reload the window (Command Palette: Developer: Reload Window) so the extension loads the plugins.

loadout never writes hook approval for you. The extension records it in `config.toml` (`[hooks.state]`), as the CLI does, and the `Codex hooks` row and the "Still to do" step clear once you approve. The loadout plugin's hooks need approval only while the plugin is on in `config.toml`; Serena's hooks (including its `remind` hook) always do. Logins run in the extension (gear, MCP servers, Authenticate) instead of `codex mcp login`.

When this applies:

- The extension's own Codex must be new enough ([Switch it on](codex.md#switch-it-on)) and report its version. With an older one, or one that gives no version, Codex is not set up: bootstrap's Codex step stops with a line that says to update the extension, then run `loadout update`. A Codex that is 0.161 or newer but has no `codex plugin` command skips the plugins with one line; the rest is set up.
- `loadout check` shows one `Codex CLI` row: "not installed (optional: VS Code's Codex extension runs its own)". It is not a warning. The `Codex plugin`, `Codex hooks`, `Codex plugins missing` and `Codex MCP` rows check the real state through the extension's Codex.
- In WSL, only VS Code's Codex extension in a Remote-WSL window counts (it lives in `~/.vscode-server/extensions` once it is installed in WSL: install it from the Extensions view in a Remote-WSL window, or select Install on a dimmed local copy; [VS Code's WSL docs](https://code.visualstudio.com/docs/remote/wsl)), never the one in a Windows window. The walkthrough [Codex only on Windows with VS Code](setups.md#codex-only-on-windows-with-vs-code) shows the Windows case.

## Claude Code in VS Code without the CLI

The Claude Code extension runs the same plugin hooks as the CLI. Which hooks those are: [Hooks](../reference/hooks.md).

With no `claude` on your PATH, loadout runs the Claude Code extension's own binary for its `claude plugin …` and `claude mcp …` commands: the newest copy in a local or Remote-WSL install (from WSL, never a Windows window's, which reads the Windows home). Bootstrap's `Claude Code CLI` line names the binary, and `loadout check` shows an `ok` row `Claude Code CLI` (`not installed (optional): …`) instead of failing. The CLI is optional, decided like the Codex CLI: with `--install`, a terminal is asked `Install the Claude Code CLI too (optional, for claude in a terminal)? [y/N]` (default No); without a terminal, or with `--yes`, it is installed; `--without-claude-cli` skips the question and the install. Install it only if you want `claude` in a terminal or the extension's terminal mode (`claudeCode.useTerminal`). `Next` names the extension (reload the window if it is open) also when the CLI is there. Without a bundled binary, the CLI is required as before.

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

The block takes effect when VS Code's WSL server restarts: close every Remote-WSL window, run `wsl --shutdown` in Windows (it stops every WSL distro), then reopen the folder. In other windows, `VS Code PATH` warns when a server's command (one of yours: in `config.toml` or `~/.claude.json`, or in the repo's `.mcp.json` or trusted `.codex/config.toml`) is not on your shell's PATH: install it, or give it an absolute command. That check uses the PATH `loadout check` runs with; it does not start your login shell (its startup files can prompt or change things), so run it from a plain terminal, not an activated virtualenv, to see what VS Code sees. Claude Code's extension is expected to take PATH from your login shell (read from its code, not yet confirmed in a live test).

## VS Code on native Windows

With loadout on native Windows (`bootstrap.ps1`, experimental; WSL 2 is recommended, see [Setup matrix](../reference/setup-matrix.md#native-windows-experimental)), a local VS Code window reads `%USERPROFILE%\.claude` and `%USERPROFILE%\.codex`, which `bootstrap.ps1` sets up. The rest of this page applies as for a local window: the `VS Code (Claude Code)` and `VS Code (Codex)` rows, the `VS Code PATH` row against your shell's PATH, and the extensions' own binaries when no CLI is on PATH. `--vscode-wsl`, `--vscode-path` and the `VS Code` switch row are for WSL only: on Windows the two flags change nothing and say so. loadout on Windows does not report a Codex in WSL.

## A committed .mcp.json with your own path

A repo's `.mcp.json` is shared. When it starts a server from a path in one person's home (`/home/you/…`, `C:\Users\you\…`), teammates' agents cannot start it. `loadout check` in that repo warns `repo .mcp.json` and names the servers. Fix: register that server in local scope (`claude mcp add --scope local …`) or as your user-level server, and remove it from the committed file. loadout never changes the file.

## What loadout does not do here

loadout does not install or update extensions, trust a workspace, approve hooks (you do, in the extension), or change your MCP entries. It writes VS Code files only when you ask: the `chatgpt.runCodexInWindowsSubsystemForLinux` switch (`--vscode-wsl`, or a yes in a terminal) and the PATH block (`--vscode-path`, or a yes), each with a backup ([ADR 0034](../adr/0034-vscode-extension-binaries-and-vscode-fixes.md)). An MCP entry you wrote, such as a Serena entry with an absolute command and a fixed `--project`, is used as it is ([Serena already set up](codex.md#what-stays-different)).
