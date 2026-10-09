# tasklog — notes for Claude

tasklog is a small CLI to log tasks and export them as JSON or CSV. Data lives in a SQLite file under `~/.local/share/tasklog` (override with `TASKLOG_HOME`).

## Commands

- Install: `uv sync --extra dev`
- Tests: `uv run pytest`
- Run: `uv run tasklog --help`
- Publish the docs site: `make deploy` (needs the VPN; pushes to the production web server)

## Conventions

- Python 3.11+, type hints everywhere, no runtime dependencies.
- Conventional commits (`feat:`, `fix:`, `docs:`).
- Never change the SQLite schema without a migration note in the release notes.
- Keep `cli.py` thin: logic belongs in `store.py`.
