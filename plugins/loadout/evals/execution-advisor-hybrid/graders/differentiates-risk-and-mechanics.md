---
type: llm
focus: last_message
weight: 3
---

Context: a seven-task plan. Tasks 1, 3 and 4 are risky and touch the user's real data: Task 1 migrates the existing database in place, Task 3 adds an irreversible purge, Task 4 imports into the database and must not half-import. Task 2 defines the Store API that Tasks 3 and 4 call (coupled). Tasks 5, 6 and 7 are independent mechanical text edits (help strings, a usage page, a changelog) whose exact content is in the plan. The assistant was asked for a per-task execution recommendation.

Judge the per-task assignment in the recommended option, not keywords. PASS only if all hold:
1. Each of Tasks 1, 3 and 4 gets a per-task (independent) review.
2. Each of Tasks 5, 6 and 7 is handled cheaply: either kept inline in the main session with only the final whole-branch review, or delegated to the cheap model tier (Haiku-class / "cheap" / cheapest). Batching them into one cheap dispatch counts.
3. None of Tasks 5, 6 and 7 gets a per-task review, the top model tier, or a subagent-driven (SDD) treatment with per-task review by default.
4. The risky tasks and the mechanical tasks get visibly different treatment (review, and/or mode or model tier); the plan is not given one uniform assignment.

FAIL if any of Tasks 1, 3, 4, 5, 6, 7 is missing from the assignment, or any condition above fails.
