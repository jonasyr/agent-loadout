# Architecture

- `src/tasklog/cli.py` parses the command line and calls the storage layer.
- `src/tasklog/store.py` defines `TaskRepository`, which wraps SQLite and validates titles.
- `src/tasklog/config.py` decides where the database file lives.

Archiving keeps the row and sets `archived = 1`.
