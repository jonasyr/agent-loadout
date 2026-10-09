---
type: llm
focus: last_message
---

Context: a documentation-sync pass updated docs/reference/cli.md after the task-title limit changed from 120 to 200. That file links to `../../src/tasklog/store.py` and `../architecture.md#storage` and mentions the symbol `MAX_TITLE_LEN`.

PASS if the reply states that the links and/or referenced paths/symbols in the edited file were checked and resolve (or names a specific one that is broken).

FAIL if the reply says nothing about checking links, paths or referenced files/symbols.
