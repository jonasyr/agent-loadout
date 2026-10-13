# 0025. loadout's own files live in XDG state, not in `~/.claude`

- Status: Accepted
- Date: 2026-10-13
- Source: [Design: state out of ~/.claude](../superpowers/specs/2026-10-13-state-out-of-claude-design.md)

## Context
loadout kept its state (`~/.claude/.loadout`) and its undo backups (`~/.claude/backups`) under `~/.claude` for every user. A Codex-only user, who has no use for Claude Code, therefore still got a `~/.claude` folder. Backups also sat next to Claude Code's configuration, which is not where machine-local state belongs.

## Decision
- State lives in `$XDG_STATE_HOME/loadout` (absolute paths only), or `~/.local/state/loadout` when that is not set. Backups live in its `backups/` folder. The rule is the same on every OS.
- The old folders move in two steps, because older loadout processes and hooks cannot be stopped from writing them meanwhile: every loadout run copies what is new (under a lock, never overwriting), and a later run, at least ten minutes after the copy and with no older run busy, deletes each old copy that is still exactly what was copied. An old copy changed after its copy replaces an untouched new copy; when both changed, both stay and are named.
- `loadout restore` maps old paths: backups taken before the move restore from the new place, and an old printed `~/.claude/backups/...` command still works.

## Alternatives considered
- Keep `~/.claude`: Codex-only machines keep a folder they do not need.
- `~/.config/loadout`: that folder is the user's, and a dotfile sync would carry backups (which can hold secrets) to other machines.

## Consequences
- A Codex-only machine has no `~/.claude`. An empty `~/.claude` is removed after the move, only when Claude Code is off.
- A sync of `~/.config` never carries backups.
- `~/.claude/backups` is shared with Claude Code (its `.claude.json` copies): only loadout's own `loadout-<timestamp>` folders with a manifest move; everything else stays where its owner keeps it.
- An entry kept in `~/.claude` because both places have it is named by the migration and by `loadout check` (row `loadout state`) until you delete it by hand.
- Until everything is copied, commands that change things stop with exit code 1; old copies wait about ten minutes (on a Codex-only machine, `~/.claude` disappears with them).
- No step deletes an old entry that changed after it was copied, so neither an ownership record nor a backup can be lost to an older process writing at the same time.
