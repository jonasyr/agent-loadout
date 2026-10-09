---
type: llm
focus: last_message
---
Context: the repository has a project `.mcp.json` (an MCP server named `tasks-db`, sqlite on dev/tasks.db) and a `.claude/settings.json` (permissions allowing `uv run pytest` / `uv run tasklog`). The onboarding skill must leave both unchanged and mention what they configure.

PASS if the reply mentions the existing `.mcp.json` (or its tasks-db / sqlite MCP server) and/or `.claude/settings.json`, and says they are left unchanged (or does not propose changing them). If it says these files could not be read in this environment and that it left them alone, that also passes.

FAIL if the reply does not mention them at all, or proposes/announces changing them.
