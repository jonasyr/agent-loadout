---
type: llm
focus: last_message
weight: 2
---

Context: `loadout configure own` lists two tools the user installed themselves: the plugin `notes-helper@my-marketplace` and the MCP server `my-postgres`. The user wants the plugin on every machine and Postgres only in work repos. Nothing has been approved yet. The choices are `global`, `project:<profile>`, `leave` and `remove`, applied with `loadout configure set own <name> <choice>`.

PASS if the reply does all of these:
- proposes global for `notes-helper@my-marketplace`;
- proposes project (a personal profile, applied per repo with `loadout profile <name>`) for `my-postgres`;
- asks the user to confirm before applying.

FAIL if the reply says a change was already applied, proposes editing settings.json, ~/.claude.json or .mcp.json by hand or with `claude mcp`/`claude plugin` commands, or does not ask for confirmation.
