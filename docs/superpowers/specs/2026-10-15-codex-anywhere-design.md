# Codex anywhere: Windows/WSL, Serena as documented, setup from inside an agent (hardening 5): design

Status: approved in chat 2026-10-15. Goal from the user: a Codex-only user on Windows with WSL 2 (repos on `/mnt/d`, Serena already set up by Serena's docs, maybe superpowers, uv, Python 3.14) installs loadout and it works the first time, also in repos shared with Claude Code users; loadout can be set up from inside Codex or Claude Code without typing CLI commands; the docs cover every agent × platform × starting point.

## Facts this rests on (official sources, 2026-10-15)

- Codex on Windows reads `%USERPROFILE%\.codex`; Codex in WSL reads the Linux `~/.codex`; they share nothing by default. `CODEX_HOME` moves the home (the folder must exist). learn.chatgpt.com/docs/windows/windows-app, …/config-file/environment-variables.
- The VS Code extension picks the side with `chatgpt.runCodexInWindowsSubsystemForLinux` (default false, Windows only); in WSL mode it uses the WSL `~/.codex` (openai/codex discussion 5471).
- Serena for Codex (oraios.github.io/serena, clients page): `serena setup codex`, or `[mcp_servers.serena]` with `startup_timeout_sec = 15`, `command = "serena"`, `args = ["start-mcp-server", "--project-from-cwd", "--context=codex"]`, plus `~/.codex/hooks.json` with six `serena-hooks … --client=codex` entries: PreToolUse `Bash` → `remind` (timeout 5), PreToolUse `^mcp__serena__` → `plan-guard`, PostToolUse `^mcp__serena__.*$` → `reset`, SessionStart `startup|resume` → `activate`, UserPromptSubmit → `plan-context`, SessionEnd → `cleanup` (timeout 3; Codex ≥ 0.145, else `Stop`, never both). No auto-approve hook for Codex.
- Codex combines hooks from every layer (user, project, plugins); every non-managed hook needs a `/hooks` trust review, keyed by its hash. learn.chatgpt.com/docs/hooks.
- Skills: `$HOME/.agents/skills` (user), `.agents/skills` (repo); symlinks supported.

## Decisions (from the user)

1. Serena's Codex hooks: exactly the official set, exactly once. They move out of the loadout plugin into `~/.codex/hooks.json` as owned entries. Fresh setup: loadout writes them. Already there (the user's own): loadout adds nothing. Partly there: loadout adds only what is missing. Restore removes only loadout's entries. Codex loses `auto-approve` (Serena does not document it). Claude Code is unchanged.
2. Windows and WSL: one loadout per side (option A). Each configures only its own Codex home; both use the same personal layer through git. Each side's `loadout check` reads the other side read-only and reports it; loadout reports the VS Code extension setting and sets it only after a yes, with a backup. It never silently configures a home the active Codex does not read. A shared `CODEX_HOME` across sides is detected and warned about, not set up.
3. Setup from inside an agent: a page written for agents, linked from the README with one sentence to paste; the agent detects, asks, shows the bootstrap command and runs it after a yes; the configure skill covers everything after.
4. Docs: one "Setups" page with the agent × platform × starting-point matrix, each cell a tested path; Codex-in-WSL troubleshooting.
5. Live tour after the PRs: a real Codex in an isolated HOME (`CODEX_HOME=<test>/.codex`), the user logs in there once (`! CODEX_HOME=… codex login`); never the real `~/.codex`.

## PR A: Serena as documented (Codex)

- `codex.SERENA` gains `startup_timeout_sec = 15`; its args stay in the documented order (`start-mcp-server`, `--project-from-cwd`, `--context=codex`).
- A user `[mcp_servers.<any name>]` whose command runs Serena's MCP server (`serena start-mcp-server`, or `uvx … serena … start-mcp-server`, or a full path to `serena`) counts as "Serena is there": loadout writes no `serena` table of its own, says so once (`mcp serena: you already have it as <name>; loadout uses yours`), and `loadout check` stays quiet about it. A table named `serena` that is not Serena keeps today's "left as is" and its check line names the fix (rename one of them), not `loadout bootstrap`.
- The plugin's `.mcp.json` must not give Codex a second Serena: verify what Codex does with a plugin's MCP servers; if it starts them, the Codex manifest stops pointing at `.mcp.json` for Serena (codebase-memory keeps its route).
- New owned-entries module for `~/.codex/hooks.json` (same contract as `config.toml`: record what loadout wrote by exact content, parse guard, atomic write, backup before change, restore removes only owned entries, user entries byte for byte). It ensures the six official Serena entries; an entry counts as present when an existing hook for the same event runs `serena-hooks <same subcommand>` with `--client=codex` (any path, any timeout). `cleanup` goes under SessionEnd on Codex ≥ 0.145, else Stop; never both, and an existing one under either counts.
- `plugins/loadout/hooks/codex.json` drops `serena-hooks activate`, `cleanup` and `auto-approve`. Session notice, type check and tool hints stay in the plugin.
- With Serena off (the user turned the kit's Serena off, or no `serena-hooks` binary), no Serena hook entries are written, and loadout's own entries are removed.
- `/hooks` trust: the existing per-key tracking covers the new entries; the open-steps line names `/hooks` once after a change.

## PR B: Windows and WSL

- `wsl.codex_side()` (in WSL): which Codex the user runs. Signals, read-only: `codex` on PATH resolving under `/mnt/<drive>/` (Windows binary or npm shim); a Linux `codex`; `CODEX_HOME` set, and whether it points under `/mnt/`; the Windows home (`/mnt/c/Users/<user>`, from `cmd.exe /c echo %USERPROFILE%` via `wslpath`, else `/mnt/c/Users/$USER`) having `.codex/` with recent `sessions/`; the VS Code setting in `<Windows home>/AppData/Roaming/Code/User/settings.json` (`chatgpt.runCodexInWindowsSubsystemForLinux`). Result: `wsl`, `windows`, `both`, `none`, plus the reasons.
- Bootstrap in WSL: with only a Windows Codex (or the extension in Windows mode and no Linux Codex), it does not configure the Linux `~/.codex` silently. It explains both ways and asks: install Codex in WSL (`--install` does it) and switch the extension to WSL mode (offered as a yes/no edit of that one key, backup first, restore reverts it), or run `bootstrap.ps1` on Windows. Non-interactive: the flag `--codex-side wsl|windows` decides; without it, it stops the Codex step with that explanation (exit code unchanged for the rest).
- The agent question is never skipped because `codex` is not on PATH: with `codex.exe` under `/mnt/` the question is asked (or `--agents` decides), and the Codex step then follows the rule above.
- `runner` finds `codex.exe` on WSL for reporting only (never to configure the Linux home).
- `loadout check` in WSL: a "Codex (Windows side)" line, read-only: the Windows home is used (recent sessions) but has no loadout block in its `AGENTS.md` → warn with `bootstrap.ps1`; it has one older than the kit commit → warn with `loadout update` there. On native Windows the same for a WSL side when `wsl.exe` lists a distribution with `~/.codex` (via `\\wsl$`), read-only and best effort.
- A shared `CODEX_HOME` (WSL `CODEX_HOME` under `/mnt/`): `check` warns that one config is read by both sides and its commands fit only one; bootstrap does not write it without `--codex-side`.
- WSL checks follow the agents that are on: no `claude` path check and no "Claude Code's sandbox" packages with Claude Code off.
- `/mnt/<drive>` repos: `init`/`profile` print one note (slower I/O; Serena and codebase-memory indexing take longer; links in repo skill folders are Linux links that Windows-side Codex does not follow), not a warning.

## PR C: setup from inside an agent

- `docs/how-to/install-with-an-agent.md`, written as instructions for an agent (plain steps, exact commands, one question at a time, never change anything before the user's yes, never touch `~/.claude`/`~/.codex` by hand). Steps: detect (OS, WSL, `codex_side` signals, existing Serena/superpowers/uv/Python, an existing loadout); ask (agents; personal layer: new, or a git URL; the starter preferences); show the exact bootstrap command; run it after a yes; then `/hooks` and project trust, explained; finish with `loadout check` and what each remaining line means.
- Bootstrap flags so that nothing needs a terminal: `--personal new|<git URL>`, `--answers FILE` (JSON with the starter-layer answers; unknown keys refused), `--codex-side wsl|windows` (PR B). With all answers given, `--yes` asks nothing.
- README: one sentence to paste into Codex or Claude Code, next to the one-liner.
- The configure skill: rows for "set loadout up / repair it" (→ bootstrap with flags, after a yes), "the other Windows/WSL side", and "Serena is already set up".

## PR D: docs as a framework

- `docs/how-to/setups.md`: the matrix (agent: Claude Code, Codex, both × platform: Linux, macOS, native Windows, WSL with Codex in WSL, WSL with Codex on Windows, both sides × starting point: fresh, own Serena, shared repo with Claude Code and Codex users). Each cell: the exact path and links; cells loadout does not support say so.
- `docs/how-to/wsl.md`: a Codex section (which side, the extension setting, `CODEX_HOME`, login in WSL, `/mnt/d`).
- `troubleshooting.md` rows for each new message.
- ADR 0028 "Codex on Windows and WSL: one loadout per side"; ADR 0029 "Serena's Codex hooks as owned hooks.json entries".

## Live tour (after A–D)

Isolated HOME, `CODEX_HOME=<test>/.codex`, the user's login there. Cases: fresh Codex-only; Serena already set up by `serena setup codex` (config and hooks.json); a shared repo with `.claude/skills` from a Claude Code user; `--agents codex` without `claude` on PATH. Each: bootstrap, `/hooks`, a real prompt that uses Serena and the graph, `loadout check` clean. Findings become fixes with tests. Real Windows: CI plus a guided first install on the friend's machine.

## Not in scope

- Writing the other side's Codex home from WSL (or the reverse).
- Moving repos off `/mnt/d`.
- Claude Code changes beyond what the shared code needs.
