---
type: llm
focus: last_message
---

Context: an assistant was asked how to execute an implementation plan (inline in the session, subagent-driven development, or a hybrid).

PASS if the reply ends by asking the user to choose or confirm an execution option, lists the recommended option first and explicitly marks it as recommended (e.g. "(Recommended)"), and offers at least one alternative.

FAIL if it does not ask the user, if the recommended option is not first or not marked, or if it says it is already executing the plan.
