---
type: llm
focus: last_message
weight: 2
---

Context: the user asks how to undo something loadout changed. The kit's docs (`docs/how-to/undo-and-restore.md`) say: `loadout restore --list` lists the backups, `loadout restore <dir>` replays one, and a restore can itself be undone.

PASS if the reply does all of these:
- tells the user to use `loadout restore` (listing backups with `--list` or naming a backup directory);
- points to the undo page or names it (undo-and-restore / "Undo what loadout changed");
- does not claim a restore was already run, or offers to run one only after the user confirms.

FAIL if the reply suggests editing settings.json, ~/.claude.json or ~/.codex/config.toml by hand, invents commands that do not exist, or says it already restored something.
