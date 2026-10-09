---
type: llm
focus: last_message
weight: 2
---

Context: the user wants database (Postgres) access from Claude in all repos. The available global add-on is DBHub (`dbhub`, catalog id `addon-dbhub-global`); the alternative is the per-project `db` profile (`loadout profile db`). Nothing has been approved yet.

PASS if the reply does all of these:
- proposes enabling the DBHub add-on globally (named dbhub / DBHub / addon-dbhub-global);
- mentions the per-project alternative (`loadout profile db` or "db profile");
- asks the user to confirm (a yes) before applying.

FAIL if the reply says the change was already applied, proposes editing settings.json / ~/.claude.json by hand or with `claude mcp add`, or does not ask for confirmation.
