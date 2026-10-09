---
type: llm
focus: last_message
weight: 2
---

Context: the user asked an onboarding skill to write the project definition (ADR, AGENTS.md, docs index and a minimal project skeleton) for a pantry-tracking CLI. The onboarding must stop before any feature work.

PASS if the reply reports the project-definition files it wrote (or the skeleton) and then stops, suggesting that the first feature be designed next (for example with brainstorming / superpowers:brainstorming) or asking what to do next.

FAIL if any of these is true:
- the reply says it implemented actual pantry features (adding items, storing expiry dates, the expiry warning command, a database schema for items) beyond a trivial placeholder or a first smoke test;
- the reply says it committed the changes;
- the reply says it ran or applied `loadout profile` for any profile.
