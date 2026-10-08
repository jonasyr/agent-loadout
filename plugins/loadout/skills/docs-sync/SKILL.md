---
name: docs-sync
description: Cheap end-of-feature documentation pass — find which doc layers (docs/, AGENTS.md, Serena memories, README) the current change affects and update only those, then verify links. Use after finishing a feature or before merging.
---

# Docs sync

Follow `~/.claude/rules/loadout/docs-policy.md`.

1. Determine the change: `git diff --stat <base>...HEAD` (base: the merge base with the default branch) plus uncommitted changes.
2. For each changed area, decide which facts changed (commands, behaviour, configuration, architecture, decisions) and which layer owns each fact.
3. Update the owning layer, normally `docs/`:
   - a new decision becomes an ADR in `docs/adr/`;
   - update AGENTS.md only if commands, conventions or the map changed;
   - update a Serena memory only if its summary or link became wrong, or if a gotcha was learned.
4. Check every link and path in the files you touched: relative links resolve, referenced files and symbols exist.
5. Show the diff. Commit separately from code (`docs: ...`) after approval.

Keep it proportional: a small change usually touches zero or one doc file. If you find widespread rot, stop and recommend `/loadout:docs-audit`.
