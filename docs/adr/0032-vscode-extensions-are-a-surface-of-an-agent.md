# 0032. VS Code extensions are a surface of an agent

- Status: Accepted; amended by [0034](0034-vscode-extension-binaries-and-vscode-fixes.md) (loadout runs the extensions' own binaries and writes VS Code files when asked)
- Date: 2026-10-17
- Source: [Design: VS Code extensions as a surface of each agent](../superpowers/specs/2026-10-17-vscode-extensions-design.md)

## Context

Many people use Claude Code and Codex only through their VS Code extensions, or next to the CLIs. Both extensions bundle their own agent binary and never use the one on PATH; the Codex extension installed on a test machine bundled codex 0.145, older than loadout needs. The Claude Code extension shares `~/.claude` with the CLI, plugins included. The Codex extension shares `config.toml`, `AGENTS.md`, skills, MCP servers and the login, but loads no plugins and has no `/hooks`. On Windows, a local VS Code window reads the Windows homes, which loadout in WSL never sets up. loadout looked only at the CLIs, so it could report a healthy setup that the user's editor did not see.

## Decision

loadout treats each extension as a surface of its agent: `targets.json` still says which agents are on, and for each agent that is on loadout finds its VS Code extensions, read-only (`cli/loadout/vscode.py`). `loadout check` reports per extension and window type what it lacks, each with its fix (a window that reads a home loadout did not set up is one of them); where a feature needs a CLI (Codex's plugins and `/hooks`), the fix is the CLI alongside VS Code. These rows are warnings, never failures. loadout changes no VS Code file and no MCP entry for this; fixes that write follow the repo-writes rules (plan, yes, backup, restore) and come with their own change.

## Consequences

- An extension-only user learns what their editor misses and how to get it, instead of a clean report that does not apply to them.
- Every check reads the newest extension folder again, because extensions update themselves; the bundled Codex is asked `--version` once per installed Codex extension (in WSL up to twice: VS Code on Windows and its Remote-WSL server).
- What only the installed code shows (the binary resolution, a Remote-WSL window's PATH) is checked again in the live tour; the PATH row says "may not find" until then.
- Editors other than VS Code (Insiders, Cursor, VSCodium, Windsurf) are not covered.

## In the code
- `cli/loadout/vscode.py`
- `cli/loadout/check.py` (`_surface_rows`, `_vscode_path`, `_vscode`)
- [Use loadout with VS Code](../how-to/vscode.md)
