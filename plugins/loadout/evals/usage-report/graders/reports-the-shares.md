---
type: llm
focus: last_message
weight: 2
---

Context: `loadout usage --json` returned, for Claude Code main sessions, 200 sessions with Serena in 6, codebase-memory in 8 and Context7 in 4; subagents 150 sessions with Serena in 0; 300 symbol-like searches in main sessions; hint_sessions 40. ADR 0026's reference was Serena 0.8%, codebase-memory 1.2%, Context7 0.8% of main sessions.

PASS if the reply does all of these:
- gives the main-session shares (Serena about 3%, codebase-memory about 4%, Context7 about 2%) or the counts they come from;
- compares them with the reference from ADR 0026 and says use went up;
- mentions that subagents still almost never use them, or gives their numbers;
- mentions the hint sessions (40).

FAIL if the reply invents numbers that are not in the output, quotes transcript content, or claims it changed a setting.
