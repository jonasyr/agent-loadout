# 0025. loadout's own files live in XDG state, not in `~/.claude`

- Status: Accepted
- Date: 2026-10-13
- Source: [Design: state out of ~/.claude](../superpowers/specs/2026-10-13-state-out-of-claude-design.md)

## Context
loadout kept its state (`~/.claude/.loadout`) and its undo backups (`~/.claude/backups`) under `~/.claude` for every user. A Codex-only user, who has no use for Claude Code, therefore still got a `~/.claude` folder. Backups also sat next to Claude Code's configuration, which is not where machine-local state belongs.

## Decision
- State lives in `$XDG_STATE_HOME/loadout` (absolute paths only), or `~/.local/state/loadout` when that is not set. Backups live in its `backups/` folder. The rule is the same on every OS.
- At the start of every loadout run, a one-time migration moves the old folders, under a lock. Where the new place already holds an entry of the same name, the new one wins.
- `loadout restore` maps old paths: backups taken before the move restore from the new place, and an old printed `~/.claude/backups/...` command still works.

## Alternatives considered
- Keep `~/.claude`: Codex-only machines keep a folder they do not need.
- `~/.config/loadout`: that folder is the user's, and a dotfile sync would carry backups (which can hold secrets) to other machines.

## Consequences
- A Codex-only machine has no `~/.claude`. An empty `~/.claude` is removed after the move, only when Claude Code is off.
- A sync of `~/.config` never carries backups.
- An entry kept in `~/.claude` because of a name conflict is named by the migration and by `loadout check` (row `loadout state`) until you delete it by hand.
- If the move does not finish, commands that change things stop with exit code 1 until the next run completes it.
