# 0016. Your own tools: nothing without an answer; Enter decides later, an explicit leave is remembered

- Status: Accepted
- Date: 2026-10-10
- Source: [Adopt design, section 2](../superpowers/specs/2026-10-10-adopt-own-tools-design.md#2-goal), plus the rulings made while building it (summarised below)

## Context
`adopt` used to offer only to remove items that are not in the catalog, and kept them on one machine, unmanaged. A kept tool was not reproduced on another machine and could not be project-scoped. The user's standing rule is to ask before removing or replacing anything. Several early drafts treated an empty answer as a decision.

## Decision
Every tool that is not in the catalog and not already managed gets one of four choices: global (record it in the personal layer), project (disable it globally and write it into a personal profile), leave (stay on this machine), or remove (restorable). The default everywhere is to decide later: `--yes`, non-interactive runs, an empty answer and three invalid answers change nothing and store nothing. Only an explicit `l` is remembered, in a machine-local file.

## Alternatives considered
- Treat Enter as leave and remember it: a user who pressed Enter by habit would never be asked again. A review found exactly this and the ruling reversed it.
- Remove what is not listed: contradicts the ask-first rule.
- Record everything automatically as global: moves possibly private or machine-specific tools into a repo.

## Consequences
- Re-running `adopt` asks again about undecided items until the user answers. A recorded item is classified as managed and is not asked about.
- Decisions are stored per machine and not synced. The key never holds a command line (a hook is keyed by event, matcher and a hash).
- `loadout configure own` and `configure set own` apply the same choices without the prompt, with exit code 1 when an item was not recorded.

## In the code
- `cli/loadout/own.py` (`options`, `ask_choices`, `parse_spec`, `record_global`, `record_project`, `remember_leave`, `decision_key`, `unmanaged`)
- `cli/loadout/inventory.py` (`classify`: action `own`; personal-layer items are `keep`)
- `cli/loadout/adopt.py` (`apply_own`, `select`)
- `cli/loadout/check.py` (the `own tools` warning)
- Guide: [Handle your own tools](../how-to/your-own-tools.md)
