---
type: regex
target: { source: file, path: CLAUDE.md }
pattern: "^# tasklog \u2014 notes for Claude\n\ntasklog is a small CLI to log tasks and export them as JSON or CSV\\. Data lives in a SQLite file under `~\\/\\.local\\/share\\/tasklog` \\(override with `TASKLOG_HOME`\\)\\.\n\n## Commands\n\n- Install: `uv sync --extra dev`\n- Tests: `uv run pytest`\n- Run: `uv run tasklog --help`\n- Publish the docs site: `make deploy` \\(needs the VPN; pushes to the production web server\\)\n\n## Conventions\n\n- Python 3\\.11\\+, type hints everywhere, no runtime dependencies\\.\n- Conventional commits \\(`feat:`, `fix:`, `docs:`\\)\\.\n- Never change the SQLite schema without a migration note in the release notes\\.\n- Keep `cli\\.py` thin: logic belongs in `store\\.py`\\.\n$(?![\\s\\S])"
weight: 2
---
