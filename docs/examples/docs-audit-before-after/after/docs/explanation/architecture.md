# Architecture

tasklog has three modules:

- `src/tasklog/cli.py` parses the command line and calls the storage layer.
- `src/tasklog/store.py` defines `Store`, which wraps SQLite and validates titles (`MAX_TITLE_LEN`).
- `src/tasklog/config.py` decides where the database file lives.

Archiving does not delete anything; why, and what that means for `list --all`, is recorded in [ADR 0001](../adr/0001-archive-is-a-soft-delete.md).
