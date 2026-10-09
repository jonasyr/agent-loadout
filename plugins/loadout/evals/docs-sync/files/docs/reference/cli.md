# CLI reference

| Command | What it does |
|---|---|
| `tasklog add <title>` | Add a task. |
| `tasklog list` | List open tasks, newest first. |
| `tasklog archive <id>` | Archive a task; archived tasks no longer appear in `list` or `export`. |
| `tasklog export [--format json\|csv]` | Export open tasks to stdout. Default format: `json`. |

## Limits

- Task titles must not be empty and are limited to 120 characters (`MAX_TITLE_LEN` in [`src/tasklog/store.py`](../../src/tasklog/store.py)); longer titles are rejected with an error.

Data location: see [architecture](../architecture.md#storage).
