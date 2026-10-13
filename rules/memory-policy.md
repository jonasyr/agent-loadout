# Memory policy (loadout)

| Store | Use for | Never use for |
|---|---|---|
| Serena memories (in repo, committed) | Project working notes and an index into `docs/` (see docs-policy) | Copies of docs content |
| Claude Code auto memory (`~/.claude/projects/...`, this machine only; Codex: loadout sets up no counterpart) | Temporary or machine-specific notes | Project facts (they belong in the repo) or personal preferences |
| Personal layer (`~/.config/loadout/personal/rules/me.md`, loaded via `~/.claude/rules/personal/`; Codex: copied into loadout's block in `~/.codex/AGENTS.md`) | The user's preferences and working style | Project facts |

If you learn a durable project fact, write it to `docs/` and link it from a memory. If you learn a durable preference of the user, propose adding it to `~/.config/loadout/personal/rules/me.md` (or via the `loadout:configure` skill) rather than storing it in auto memory; if that folder is a git repo, offer to commit it.
When Serena onboarding writes memories, keep each one a short summary plus links into `docs/`.
