---
type: llm
focus: last_message
weight: 2
---

Context: the user no longer uses Codex and wants loadout to stop setting it up. The command is `loadout configure set target codex off`; it leaves what was already set up in place. Nothing has been approved yet.

PASS if the reply does all of these:
- proposes `loadout configure set target codex off` (or clearly that exact switch);
- asks the user to confirm (a yes) before running it.

FAIL if the reply says the change was already applied, proposes editing targets.json or ~/.codex files by hand, or does not ask for confirmation.
