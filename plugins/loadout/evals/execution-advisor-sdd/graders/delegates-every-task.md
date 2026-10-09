---
type: llm
focus: last_message
weight: 3
---

Context: an eight-task plan. Every task creates one new exporter module and its own test file; the tasks share no code and touch disjoint files; they only read user data; the plan gives requirements, not code, so each task needs judgment. The user said the session's context is about 80% full. The assistant was asked whether to run it inline or with subagents.

Judge the assignment in the recommended option. PASS only if all hold:
1. Every one of the eight tasks is delegated to subagents (the verdict is SDD, or a Hybrid in which no task stays in the main session). Batching several tasks into one subagent dispatch counts as delegated.
2. The reasons cite at least one of: the nearly full context, the tasks' independence or parallelism, or that they need judgment rather than transcription.

FAIL if Inline is recommended, if any task is kept in the main session, or if no such reason is given.
