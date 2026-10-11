# tasklog

> Agent entry point. Facts live in `docs/`; this file maps them.

## Purpose

A small CLI that logs tasks in a local SQLite file and exports them.

## Commands

| Task | Command |
|---|---|
| Install | `uv sync --extra dev` |
| Test | `uv run pytest` |
| Run | `uv run tasklog --help` |

There is no linter configured.

## Conventions

- Python 3.11 or newer (`requires-python` in `pyproject.toml`).

## Map

- `docs/README.md` — documentation index (single source of truth)
- `docs/adr/` — architecture decision records
- `.serena/memories/` — agent working notes; each links into `docs/`
