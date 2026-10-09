# tasklog

> Agent entry point. Facts live in `docs/`; this file maps them.

## Purpose

A small CLI that logs tasks in a local SQLite file and exports them as JSON or CSV.

## Commands

| Task | Command |
|---|---|
| Install | `uv sync --extra dev` |
| Test | `uv run pytest` |
| Run | `uv run tasklog --help` |

## Conventions

- Python 3.11+, no runtime dependencies.
- Keep `src/tasklog/cli.py` thin; logic belongs in `src/tasklog/store.py`.

## Map

- `docs/README.md` — documentation index
- `docs/reference/cli.md` — commands and limits
- `docs/architecture.md` — modules and data flow
- `docs/adr/` — decisions
- `.serena/memories/` — agent notes
