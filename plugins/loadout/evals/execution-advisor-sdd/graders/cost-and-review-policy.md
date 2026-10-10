---
type: llm
focus: last_message
---

Context: an assistant recommended how to execute an implementation plan (Inline, subagent-driven, or a hybrid).

PASS if the reply contains both (a) a cost comparison that gives a cost class (low / medium / high or similar) for the recommended option and for at least one alternative, and (b) an explicit review policy (which tasks get a per-task review, and the final whole-branch review).

FAIL if either the cost classes or the review policy is missing.
