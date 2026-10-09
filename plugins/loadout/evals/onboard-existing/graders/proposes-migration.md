---
type: llm
focus: last_message
weight: 2
---

Context: the repository has a CLAUDE.md with real content (commands, conventions) and had no AGENTS.md. The onboarding skill must propose moving that content into AGENTS.md (leaving CLAUDE.md as just `@AGENTS.md`) and only do it after the user agrees.

PASS if the reply proposes or offers this migration (moving/merging CLAUDE.md content into AGENTS.md and reducing CLAUDE.md to an `@AGENTS.md` import) and asks the user to confirm, or clearly says it is waiting for the user's agreement before changing CLAUDE.md.

FAIL if the reply says CLAUDE.md was already replaced, overwritten, emptied or reduced to `@AGENTS.md`, or if it does not mention what should happen with the existing CLAUDE.md content at all.
