---
type: llm
focus: last_message
weight: 3
---

Context: a seven-task plan. Tasks 1, 3 and 4 are risky and touch the user's real data: Task 1 migrates the existing database in place, Task 3 adds an irreversible purge, Task 4 imports into the database and must not half-import. Task 2 defines the Store API that Tasks 3 and 4 call (coupled). Tasks 5, 6 and 7 are independent mechanical text edits (help strings, a usage page, a changelog) whose exact content is in the plan. The assistant was asked for a per-task execution recommendation.

Judge the per-task assignment in the recommended option, not keywords. PASS only if all hold:
1. The recommended verdict is Hybrid or SDD (not all-Inline).
2. Each of Tasks 1, 3 and 4 gets a per-task (independent) review.
3. Each of Tasks 5, 6 and 7 is put on the cheap model tier (Haiku-class / "cheap" / cheapest), and none of them gets a per-task review.
4. The risky tasks and the mechanical tasks get visibly different treatment (mode, model tier or review), i.e. the plan is not given one uniform assignment.

FAIL if any of Tasks 1, 3, 4, 5, 6, 7 is missing from the assignment, or any condition above fails.
