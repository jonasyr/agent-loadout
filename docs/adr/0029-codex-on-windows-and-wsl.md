# 0029. Codex on Windows and WSL: one loadout per side

- Status: Accepted; amended by [0034](0034-vscode-extension-binaries-and-vscode-fixes.md) (`--vscode-wsl` is the yes as a flag, since #47; a folder's or a profile's setting that turns the switch off is named, never edited)
- Date: 2026-10-16
- Source: [Design: Codex anywhere](../superpowers/specs/2026-10-15-codex-anywhere-design.md), section "PR B"

## Context

On a Windows machine with WSL there are two Codex homes. Codex on Windows reads `%USERPROFILE%\.codex`; Codex in WSL reads the Linux `~/.codex` (or `$CODEX_HOME`). They share nothing by default. The VS Code extension picks the side with `chatgpt.runCodexInWindowsSubsystemForLinux` (default `false`: Windows). The commands loadout writes differ per side: a `serena` or `codebase-memory-mcp` path, a hook script, a Python launcher. A loadout run in WSL that set up the Linux home for a user whose Codex runs on Windows changed nothing that user's Codex reads, and reported success.

## Decision

- One loadout per side. loadout in WSL configures only the WSL Codex home; loadout on Windows (`bootstrap.ps1`) configures only the Windows one. Both use the same personal layer through git. Neither writes the other side's Codex home.
- In WSL, `wsl.codex_side()` reads which side the user's Codex runs on, read-only: a Linux `codex` on `PATH`, a Windows `codex` or `codex.exe` (one that resolves under `/mnt/<drive>/`), sessions from the last 30 days in the Windows Codex home, the VS Code setting and a `CODEX_HOME` under `/mnt/`.
- Bootstrap in WSL does not set up the Linux home when the only Codex is the Windows one. In a terminal it asks which side to set up and, for WSL, offers to switch the VS Code setting (a text edit of that one key, after a yes, backup first). Without a terminal, or with `--yes`, `--codex-side wsl|windows` decides; without it, the Codex step stops with both ways. The side is settled before the prerequisites, so a Windows-side choice installs no Linux Codex.
- A `CODEX_HOME` in WSL that points into Windows would be read by both sides. loadout warns and does not set it up without `--codex-side wsl`.
- `loadout check` in WSL reports the Windows side read-only: a used Windows Codex home without loadout's block in its `AGENTS.md` is a warning that names `bootstrap.ps1`. With only the Windows Codex it does not check the WSL home: one `Codex` line points to `bootstrap.ps1`. A Windows `codex` on `PATH` is never used to set up the WSL home, also not by the daily sync or `configure`.

## Alternatives considered

- One loadout writes both homes: the commands in one home would point at the other side's binaries, and a WSL run would write Windows files it cannot run or check.
- A shared `CODEX_HOME` for both sides: one config, but its commands fit only one side.
- Set the VS Code setting without asking: it changes how the user's editor runs Codex, so it needs a yes.

## Consequences

- A user who runs Codex on both sides runs loadout on both sides. `loadout check` on the WSL side says when the Windows side is missing.
- The VS Code edit keeps every other byte of `settings.json` (comments, trailing commas, CRLF). A copy is saved first, so `loadout restore` of that run puts it back. Without a `settings.json`, bootstrap does not ask. When the file is not an object, gives the key a value other than `true` or `false` or cannot be written, loadout prints the manual step instead.
- Not covered yet: a Windows-side block older than the kit is not reported, and loadout on native Windows does not report the WSL side.

## In the code

- `cli/loadout/wsl.py` (`codex_side`, `windows_home`, `vscode_wsl_mode`, `set_vscode_wsl_mode`, `repo_note`, `problems`)
- `cli/loadout/bootstrap.py` (`codex_gate`, `missing_binary`, the Codex and Prerequisites steps)
- `cli/loadout/check.py` (`_codex_side`)
