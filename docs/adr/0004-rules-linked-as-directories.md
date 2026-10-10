# 0004. Rules are linked as directories; `~/.claude/CLAUDE.md` changes only when you ask adopt to migrate it

- Status: Accepted
- Date: 2026-10-08
- Source: [Design spec, decision D4](../superpowers/specs/2026-10-08-agent-loadout-design.md#2-decisions)

## Context
Many users already have a global `~/.claude/CLAUDE.md` with their own instructions. Claude Code also loads every file under `~/.claude/rules/`. The kit needs a place for its rules and for the user's, and a way to update them with a pull.

## Decision
`~/.claude/rules/loadout` is linked to the kit's `rules/` folder and `~/.claude/rules/personal` to the personal layer's `rules/` folder. Linking and the settings merge never read or write `~/.claude/CLAUDE.md`.

## Alternatives considered
- Append a managed block to `~/.claude/CLAUDE.md`: edits a file the user owns, and the block can be damaged by hand edits.
- Import the rules from `CLAUDE.md` with `@` lines: still needs an edit to that file.

## Consequences
- The user's global file stays theirs. A `git pull` updates the rules with no file written.
- Where symlinks are unavailable (Windows without Developer Mode), the folders are copied and the copy is refreshed after a pull (copy mode).
- A user who deletes the link also drops the rules. `loadout check` reports a missing link.
- One exception, on request only: `loadout adopt` lists a non-empty `~/.claude/CLAUDE.md` in its `review` group. If the user picks it, its content moves into `<personal>/rules/me.md`, the original goes into the backup, and the file keeps a one-line marker (`adopt.migrate_claude_md`). Linking and merging never write it.

## In the code
- `cli/loadout/link.py` (`LINKS`, `link_all`, `_link_one`, `is_copy_mode`)
- `rules/` (kit rules), `<personal>/rules/`
