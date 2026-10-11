# CLI reference

| Command | What it does |
|---|---|
| `tasklog add <title>` | Add a task. Titles are limited to 120 characters. |
| `tasklog list [--all]` | List open tasks, newest first. `--all` also shows archived tasks. |
| `tasklog archive <id>` | Archive a task. |
| `tasklog export [--format json\|csv]` | Export open tasks to stdout. Default format: `csv`. |
