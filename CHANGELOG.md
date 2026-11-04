# Changelog

## [0.3.0] - 2026-11-04

A safer first install: before it changes anything, setup offers to save your current Claude Code and Codex setup, and one command puts it all back. Re-running the installer also picks up fixes pushed since your first try.

### Added

- Snapshot before the first install: setup asks once (default yes) to save your agent config, including logins, to a private archive; `loadout restore --first-install` puts it back and moves aside what the install added (#83)
- A re-run of setup on stable names a newer release when one is ready and points to `loadout update` (#84)

### Fixed

- Re-running the one-liner on an existing clone on `main` updates it first (`git pull --ff-only`, only without local edits; `LOADOUT_NO_AUTO_PULL=1` turns it off); a failed dev checkout says so instead of "offline?" (#84)
- The snapshot skips files and folders it cannot read and lists them, instead of stopping; a rollback leaves those places alone (#84)
- `loadout channel stable` on a kit that is not on a release now points to `loadout update`, and the missing-npm fix line on macOS says `brew install node` (#84)

[0.3.0]: https://github.com/jonasyr/agent-loadout/compare/v0.2.0...v0.3.0

## [0.2.0] - 2026-11-03

The first release with release channels: a stable machine now gets only tested releases, three days after they come out and only when you run `loadout update`; dev keeps following main. Since 0.1.0, loadout also sets up Codex next to Claude Code (CLI, VS Code extension, Windows and WSL), shows every change to a repo as a plan you can undo, and brings a machine current with one command.

### Breaking

- loadout needs Python 3.11 or newer (#29)

### Added

- Release channels: `loadout channel stable|dev`, updates that wait for your `loadout update`, installs from the latest GitHub Release; `loadout release` writes Keep a Changelog notes, with a `/loadout:release` skill to polish them (#81, #82)
- Codex as a second target: choose Claude Code, Codex or both at setup; projects, adopt, catalog skills and Serena work for Codex too (#18, #24, #25, #26, #34, #40)
- Codex in VS Code, with or without the Codex CLI, and on Windows and WSL with one loadout per side (#41, #47, #49, #50, #51, #56)
- Context7 for Codex without a login; open approvals and logins are named where you work (#21)
- `loadout update`: one command that brings a machine current and says what changed and what to do (#53)
- Repos choose their agents; every repo change is shown as a plan first and can be undone; profile re-runs merge with your edits; `loadout explain` shows what loadout wrote (#38, #44, #45, #46)
- Your own tools: scopes for both agents, a command to create a skill, and your own codebase-memory setups (#35, #64)
- Serena and codebase-memory get used in sessions and subagents, with hints that never block; `loadout usage` and `/loadout:usage` show whether that helped (#36, #39, #57, #60, #61)
- Set loadout up from inside an agent; the configure skill answers loadout questions and makes setup changes for you (#27, #28, #42)
- Start clean with loadout's Serena: `--use-loadout` replaces your own copy, `--keep-own` keeps it (#79)
- `loadout check` names this machine's recommended setup and flags a loadout plugin copy that differs from the kit (#37, #70)
- An opt-in plugin that stands in for Codex's GitHub code review (#69)

### Changed

- loadout's state and backups live in `~/.local/state/loadout`, moved once from `~/.claude` (#33)
- A calmer first run and quieter output, with one to-do list at the end; `loadout check` runs its rows in parallel and shows progress (#32, #71, #72, #73, #74)

### Fixed

- First-time installs on a new machine: the missing steps and fix lines a first-time user needs (#75, #77)
- Codex marketplaces: an upgrade that times out is re-added, a failed one is reported and retried, and a marketplace pinned to a ref keeps its pin (#59, #66, #80)
- A fresh machine gets the whole kit, Codex entries you changed stay yours, and WSL installs Linux copies (#54, #55)
- Codex setup shows progress, stops cleanly on Ctrl+C and says that Codex asks about new hooks at start (#19, #20, #67)
- No false warnings: an identical Codex server, rtk's missing-hook message, an optional Context7 login (#22, #23, #68)
- Robustness and correctness across bootstrap, adopt, usage and the codebase-memory setup (#17, #30, #62, #65)

### Security

- MCP server secrets no longer end up in the backup manifest (#76)
- Hardening: restore runs only loadout's own undo commands, no program runs from the current folder, safer file writes (#29)

[0.2.0]: https://github.com/jonasyr/agent-loadout/compare/v0.1.0...v0.2.0
