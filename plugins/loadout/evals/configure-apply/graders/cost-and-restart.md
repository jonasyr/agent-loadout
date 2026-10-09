---
type: llm
focus: last_message
---

Context: an assistant enabled the Chrome DevTools add-on globally for the user via `loadout configure set ...`.

PASS if the reply (a) tells the user to restart Claude Code or run `/reload-plugins` for the change to take effect, and (b) mentions that this add-on is heavy on context (context cost per call / tokens) or that it can be turned off again.

FAIL if the reply misses the restart/reload instruction, or claims it edited settings files directly.
