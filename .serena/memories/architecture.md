# Architecture
Kit repo (plugin marketplace + `loadout` CLI) linked to a separate personal repo; settings are merged three-way, rules linked as directories. Codex is a second target (`cli/loadout/codex.py`, `codex_project.py`, `targets.json`): docs/how-to/codex.md, ADR 0022/0024.
Details: docs/explanation/architecture.md, docs/adr/README.md, docs/reference/cli.md.
Tool hints: `cli/loadout/usage.py` loads the hook's parser (`shell_search`, `symbol`) from `plugins/loadout/hooks/tool_hint.py`, so a change there changes both the hint and the metric (tests: test_tool_hint.py, test_usage.py); ADR 0026.
To change CLI behaviour touch `cli/loadout/<module>` (map in AGENTS.md) and update the matching docs/reference page.
