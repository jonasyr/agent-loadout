# CLI reference

| Command | What it does |
|---|---|
| `tasklog add <title>` | Add a task. Titles must not be empty and are limited to 120 characters. |
| `tasklog list [--all]` | List open tasks, newest first. `--all` is accepted but not implemented yet; it is meant to also show archived tasks ([ADR 0001](../adr/0001-archive-is-a-soft-delete.md)). |
| `tasklog archive <id>` | Archive a task. It disappears from `list` and `export`. |
| `tasklog export [--format json\|csv]` | Export open tasks to stdout. Default format: `json`. |
