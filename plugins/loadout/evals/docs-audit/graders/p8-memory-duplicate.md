---
type: llm
focus: last_message
---

Context: the Serena memory `.serena/memories/project_overview.md` copies the whole CLI command table from `docs/reference/cli.md` (the docs policy says memories hold a short summary plus a link, never copies of docs).

PASS if the reply flags that memory (project_overview / the Serena memory) as duplicating the docs, being a copy of the CLI reference, or being in the wrong layer / misplaced.

FAIL if the reply does not mention that the memory duplicates docs content (only mentioning the 200-character number is not enough).
