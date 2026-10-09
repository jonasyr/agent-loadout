---
type: llm
weight: 2
---

The user started onboarding of an empty repository and has not said anything about the project yet.

PASS if the reply asks the user what the project should do (its purpose and/or what success looks like) and waits for the answer. Offering example options or a short explanation is fine. Asking about one closely related point together with the purpose (for example who uses it) is fine.

FAIL if any of these is true:
- the reply does not ask about the project's purpose;
- the reply asks the full questionnaire at once (purpose, users, stack AND constraints all in the same message);
- the reply says it already wrote AGENTS.md, an ADR or other project files;
- the reply hands the conversation to another skill or workflow (for example "brainstorming") instead of asking the question itself.
