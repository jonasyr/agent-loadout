# tasklog overview

tasklog is a CLI task logger backed by SQLite.

## Commands

| Command | What it does |
|---|---|
| `tasklog add <title>` | Add a task. Titles may be up to 200 characters. |
| `tasklog list [--all]` | List open tasks, newest first; `--all` includes archived ones. |
| `tasklog archive <id>` | Archive a task. |
| `tasklog export [--format json\|csv]` | Export open tasks. |

## Storage

Data lives in `~/.local/share/tasklog/tasks.db`.
