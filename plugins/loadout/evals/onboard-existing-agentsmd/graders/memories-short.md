---
type: llm
focus: mock_calls
weight: 2
---
Context: during onboarding of a repo without docs/ or memories, the agent wrote Serena memories through the `write_memory` tool. The memory policy says each memory is a 1-3 line summary per topic that points to where the facts live (AGENTS.md, source files, docs/), plus genuine agent notes (gotchas); never a copy of content that lives elsewhere.

PASS if there is at least one `write_memory` call and every memory's content is short (roughly 10 lines or fewer) and points to files (e.g. AGENTS.md, src/tasklog/..., Makefile) instead of reproducing them.

FAIL if there is no `write_memory` call, or a memory copies a whole command table, the whole AGENTS.md/README, or long code/architecture descriptions.
