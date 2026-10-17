# Architecture
Kit repo (plugin marketplace + `loadout` CLI) linked to a separate personal repo; settings are merged three-way, rules linked as directories. Codex is a second target (`cli/loadout/codex.py`, `codex_project.py`, `targets.json`): docs/how-to/codex.md, ADR 0022/0024; repo files follow the repo's agents and profile entries merge three-way against a record (`.loadout.json`, `repo_config.py`, `repo_writes.py`, `repo_merge.py`): ADR 0030, 0031 (0027 for skill folders and links).
Details: docs/explanation/architecture.md, docs/adr/README.md, docs/reference/cli.md.
Gotcha: `cli/loadout/usage.py` imports the hook's parser from `plugins/loadout/hooks/tool_hint.py`, so a change there changes the hint and the metric (ADR 0026).
To change CLI behaviour touch `cli/loadout/<module>` (map in AGENTS.md) and update the matching docs/reference page.
Serena in Codex: `cli/loadout/codex_hooks.py` owns Serena's hooks in `~/.codex/hooks.json`; a user's own Serena server means loadout adds none: docs/reference/hooks.md#serenas-hooks-in-codex, ADR 0028.
