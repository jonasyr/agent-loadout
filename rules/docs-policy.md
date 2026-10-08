# Documentation layers (loadout)

Every fact has exactly one home. Other layers link to it instead of copying it.

| Layer | Holds | Rule |
|---|---|---|
| `docs/` | Everything a human may need: concepts, architecture, how-tos, reference; decisions as ADRs in `docs/adr/` | Single source of truth |
| `AGENTS.md` (and `CLAUDE.md` containing only `@AGENTS.md`) | Purpose, commands, hard conventions, and a map of `docs/` and memories | Short and hand-curated; never copy docs content into it |
| `.serena/memories/` | Agent working notes: per topic a 1–3 line summary plus a link into `docs/`; gotchas; debugging lessons; "to do X, touch these files"; current status | Never the only home of a fact a human would need |
| `README.md` | What the project is, how to install and run it | Human entry point; links into `docs/` |

When you change behaviour, update the layer that owns the fact (usually `docs/`), then fix links. At the end of a feature, run `/loadout:docs-sync`. For a full verification and cleanup, run `/loadout:docs-audit`.
