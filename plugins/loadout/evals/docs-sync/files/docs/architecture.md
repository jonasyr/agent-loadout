# Architecture

- `src/tasklog/cli.py` parses arguments (`build_parser`) and dispatches in `main`.
- `src/tasklog/store.py` holds `Store`, a thin wrapper around SQLite, and the `Task` dataclass.
- `src/tasklog/config.py` resolves where data lives.

## Storage

Tasks live in `tasks.db` under `~/.local/share/tasklog`; `TASKLOG_HOME` overrides the directory. Archived tasks stay in the table with `archived = 1`.

Exports are written in the order the tasks were created, oldest first.
