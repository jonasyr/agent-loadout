# VS Code extensions as a surface of each agent: design

Status: approved in chat 2026-10-17 (Sections 1–4). Goal from the user: a person who works in VS Code with the Codex and/or the Claude Code extension, with or without the CLIs, gets a setup that works perfectly and integrates into a machine that is already configured, on Linux, macOS, native Windows and WSL; the Windows/WSL path gets the most care. Where a surface lacks something, loadout says clearly what is missing, what it means and the fix (for example: use the Codex CLI alongside VS Code).

## Scope

- Editor: VS Code (stable) only: local windows and Remote-WSL windows. Insiders, Cursor, VSCodium and Windsurf later, after the live tour confirmed VS Code.
- Agents: the Claude Code extension (`anthropic.claude-code`) and the Codex extension (`openai.chatgpt`), each alone or next to its CLI.
- The careful-user rules of the repo-agents spec (Part 0) apply to every VS Code write: plan first, a yes or a flag, a backup, `loadout restore` undoes it, only named keys or lines change.

## Facts this rests on (2026-10-17)

Read from the extensions installed on the user's machine (Claude Code 2.1.217, Codex 26.715.61943, July builds) and from the official docs (code.claude.com/docs/en/vs-code, learn.chatgpt.com/docs/*, code.visualstudio.com/docs/remote/wsl). Marked (code) when only the installed code shows it; the live tour re-checks those on current builds.

- Both extensions bundle their own agent binary and never use one on PATH: Claude Code `resources/native-binary/claude` (its version is the extension's), Codex `bin/<os>-<arch>/codex`. The installed Codex extension bundles codex 0.145.0-alpha; loadout's Codex setup needs 0.161 or newer. Overrides: `claudeCode.claudeProcessWrapper` (machine scope), `chatgpt.cliExecutable` ("development only", application scope).
- Claude Code extension: shares `~/.claude` with the CLI (settings, plugins and marketplaces, hooks, MCP servers, CLAUDE.md, history, login). It writes some keys into `~/.claude/settings.json` itself (effort under `modelSettings`, `remoteControlAtStartup`, the hooks and permissions dialogs) and keeps `~/.claude/ide/*.lock`. It does not work in VS Code's Restricted Mode. On Linux and macOS it takes PATH from `$SHELL -lic` (code); `claudeCode.environmentVariables` reportedly does not apply in Remote-WSL windows (anthropics/claude-code#37709). Terminal mode on Windows needs `claude` on PATH.
- Codex extension: shares `config.toml`, `AGENTS.md`, `~/.agents/skills`, MCP servers and the login with the CLI. It does not support plugins (learn.chatgpt.com/docs/plugins). Its slash commands include `/mcp` but no `/hooks`; hook approval is documented for the CLI only. Untrusted projects skip the project `.codex/` layers; how the extension asks for trust is not documented. Its agent process gets VS Code's environment plus the bundled bin folder (code).
- Codex extension on Windows: a local window runs Codex natively and reads `%USERPROFILE%\.codex`; with `chatgpt.runCodexInWindowsSubsystemForLinux: true` it runs the bundled Linux codex through `wsl.exe … bash -lc` and reads the WSL `${CODEX_HOME:-~/.codex}` (code). A Remote-WSL window (`code .` from WSL) runs both extensions inside WSL (`~/.vscode-server/extensions`) with the Linux homes.
- VS Code: started from a desktop launcher it resolves the shell environment (`application.shellEnvironmentResolutionTimeout`); in Remote-WSL no shell startup files run, and `~/.vscode-server/server-env-setup` is the documented place for environment setup.
- VS Code paths: user settings `%APPDATA%\Code\User\settings.json` (Windows), `~/Library/Application Support/Code/User/settings.json` (macOS), `~/.config/Code/User/settings.json` (Linux), profiles under `User/profiles/<id>/settings.json`; extensions in `~/.vscode/extensions` (`%USERPROFILE%\.vscode\extensions`), `VSCODE_EXTENSIONS` or `--extensions-dir` override it; Remote-WSL server extensions in `~/.vscode-server/extensions`. Settings files are JSONC.
- A real careful setup (a friend's Serena guide, kept by the user outside the repo): Serena registered once per repo with an absolute command (`/home/USER/.local/bin/serena start-mcp-server --project <abs path> --context codex|claude-code`), in `~/.codex/config.toml` for Codex and a project `.mcp.json` or local scope for Claude Code, explicitly "no CLI installation required"; `.serena/project.yml` holds production-data exclusions.

## Part 1: detection (read-only)

A new module `cli/loadout/vscode.py` finds, per agent that is on:

- The CLI: `claude` / `codex` on PATH and its version (as today).
- VS Code installs: the local one (Linux, macOS, native Windows); in WSL also the Windows one (through the Windows home `wsl.py` finds) and the Remote-WSL server (`~/.vscode-server/extensions`). `VSCODE_EXTENSIONS` is honoured.
- Per install: whether each extension is installed, its newest version folder (found again on every run, because extensions update themselves), the bundled binary's path and its version (`--version` through `runner.run`, argument list, short timeout).
- Settings that matter: `chatgpt.runCodexInWindowsSubsystemForLinux`, `claudeCode.environmentVariables`, `claudeCode.claudeProcessWrapper`; read from the user settings, every profile's settings and the open folder's `.vscode/settings.json`, so an override that wins is found. JSONC is parsed leniently (comments, trailing commas, BOM); a file that does not parse is reported, never rewritten.
- Which home each surface reads: local window on Linux or macOS: the one home; local Windows window: `%USERPROFILE%\.claude` / `.codex`, except Codex with the WSL switch on: the WSL home; Remote-WSL window: the Linux homes.
- The PATH an extension's agent gets: Remote-WSL: only what `~/.vscode-server/server-env-setup` adds; desktop launch: the resolved shell environment (Claude Code follows the login shell, Codex VS Code's environment).
- For each MCP server an extension starts (the user's and loadout's): whether its command (`uvx`, `npx`, `serena`, an absolute path) is found on that PATH.

Nothing here writes. With an agent off, nothing of that agent is read (ADR 0030 rule for the user's agent folders, extended to its VS Code extension).

## Part 2: gaps, said plainly

Every gap is reported in one form: what is missing, what it means for the user, the fix.

Codex extension:

- Plugins do not load: loadout's own skills (`loadout:configure`, `loadout:onboard`, …), superpowers and plugin hooks are missing there; skills in `~/.agents/skills` work. Fix: use the Codex CLI alongside VS Code, in VS Code's terminal, for work that needs them.
- No `/hooks`: Serena's hooks in `~/.codex/hooks.json` do not run until approved. Fix: install the Codex CLI, run `codex` once and approve them in `/hooks` (the live tour confirms the extension honours that approval).
- Bundled Codex older than 0.161: fix: update the extension in VS Code.
- A local Windows window reads `%USERPROFILE%\.codex`, which loadout in WSL did not set up: fix: the WSL switch (`--vscode-wsl`) or `code .` from WSL.
- Project trust: until the live tour shows how the extension asks, the fix is `codex` once in that repo, in the WSL terminal or VS Code's terminal.

Claude Code extension: near parity with the CLI. Gaps: Restricted Mode (fix: trust the workspace); terminal mode on Windows without `claude` on PATH (fix: the CLI install); `environmentVariables` in Remote-WSL (fix: Part 3's PATH block).

Both: an MCP server whose command the extension cannot find on its PATH (fix: Part 3's PATH block, or an absolute command).

The example message (Codex extension, no CLI):

> VS Code's Codex extension does not load plugins: loadout's skills (loadout:configure, superpowers) and plugin hooks are missing there, and it has no `/hooks`, so Serena's hooks wait for your approval. Fix: use the Codex CLI alongside VS Code. `loadout bootstrap --install` installs it; then run `codex` once in VS Code's terminal and approve the hooks in `/hooks`. Use it there whenever you need the plugin skills.

Where it shows: `loadout check` (Part 4), bootstrap's "Still to do", the agent page and the configure skill (an agent says the same).

The Codex CLI next to the Codex extension is recommended, not required: in a terminal bootstrap asks `Install the Codex CLI alongside VS Code (for /hooks and plugins)? [Y/n]`; without a terminal `--install` installs it as today and the summary says why. An extension-only user who says no gets a clean run with these gaps listed, never a failure. The same holds for the Claude Code CLI next to its extension (asked only where a feature needs it).

## Part 3: fixes as plans (writes)

Each fix is a plan: one line per change with its reason, the question in a terminal or a flag, a backup before the write, `undo: loadout restore <dir>`. Only the named key or lines change; a run that changes nothing touches nothing; a file loadout cannot keep byte for byte (unparsable JSONC, a layout it cannot keep) is left, and the manual step is printed.

1. The Codex WSL switch (exists: `--vscode-wsl`, the Windows user `settings.json`). New: when a profile's or the folder's `.vscode/settings.json` sets it to `false`, that file wins; `check` names it, loadout does not edit it.
2. PATH for Remote-WSL windows (new, `--vscode-path`): a marked block in `~/.vscode-server/server-env-setup` that adds the PATH entries bootstrap gives the shell (mise shims, `~/.local/bin`). The file is created if missing (recorded as created) or the block appended; the user's lines stay. The plan says it takes effect after "WSL: Restart" or a reconnect.
3. The Claude Code CLI without `claude` on PATH: loadout runs the extension's bundled binary for the commands it needs (`claude plugin …`, `claude mcp …`); the plan names the binary. No VS Code file is written. A platform build without a bundled binary falls back to Part 2's CLI offer.

Printed, never done: updating an extension, trusting a workspace, `/hooks`, and changing MCP entries. The VS Code checks report problems with MCP entries and never rewrite one; profiles and the global setup keep writing MCP entries as before (ADR 0031, the existing Serena reuse). `.serena/project.yml` is never touched.

Where: bootstrap's VS Code step (in a terminal: the plan, one question); `loadout check` names `loadout bootstrap --vscode-wsl` / `--vscode-path`; the configure skill gives agents the same flags. The session hook and the daily sync never write VS Code files.

## Part 4: check, docs, proof

- `loadout check`, only for agents that are on and where VS Code is found: a `VS Code (Codex)` and a `VS Code (Claude Code)` row per window type that applies (local, Remote-WSL, Windows window seen from WSL): extension version, bundled binary version (Codex below 0.161 warns), the home it reads (warns when loadout did not set it up), the Part 2 gaps with fixes. A `VS Code PATH` row for an MCP server the extension cannot start. In a repo: a committed `.mcp.json` with a user's own absolute path (`/home/<user>/…`, `C:\Users\<user>\…`) warns that teammates cannot start that server (fix: local scope or a user-level server); nothing changes.
- Existing setups: an existing Serena entry is used whatever its name, with an absolute command and a fixed `--project` too; nothing of it is rewritten.
- Docs: a how-to "Use loadout with VS Code" (per OS and window type: what works, what is missing, the fix); rows in `setups.md`; the agent page asks whether the user works in VS Code, with which extensions, and with or without the CLIs; troubleshooting rows; ADR 0032 "VS Code extensions are a surface of an agent".
- Tests (`fake_home`, `fake_runner`): fake VS Code trees for Linux, macOS, Windows and WSL (with a Windows home) and a Remote-WSL server folder; fake bundled binaries; JSONC fixtures (comments, trailing commas, CRLF, BOM, tabs); profile and folder overrides; plan, apply and restore of each fix; "extension only, CLI declined" runs clean with the gaps listed; the friend's setup shape (absolute Serena command, fixed `--project`) is kept; Windows CI pins the `%APPDATA%` paths.
- Live tour (later, the user's login, isolated home): each extension × window type, and the friend's setup. It settles: hook approval and the trust question in the Codex extension, whether a CLI approval holds in the extension, current builds' binary and PATH handling.

## PRs

1. Part 1 and Part 4's check rows (read-only), ADR 0032, the how-to and docs.
2. Part 2: the gap messages in bootstrap, the agent page and the configure skill; the CLI-recommended offer.
3. Part 3: `--vscode-path`, the bundled Claude binary as runner, override detection.

## Not in scope

- Editors other than VS Code (stable).
- Remote-SSH and dev containers.
- Installing or updating extensions, or changing a user's MCP entries.
- The global careful-user audit (its own spec).
