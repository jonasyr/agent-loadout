# Adopt the documentation strategy in a repo

Give a repo the layout from [Documentation strategy](../explanation/documentation-strategy.md): one home per fact, `docs/` split by kind, a short AGENTS.md, and memories that only point.

## With the kit

| Situation | Steps |
|---|---|
| New project | `loadout init`, then the onboard skill: `/loadout:onboard` in Claude Code, `$loadout:onboard` in Codex (the CLI or VS Code's Codex extension) |
| Existing repo | `loadout init` (never overwrites a scaffold file; if only a CLAUDE.md exists, it leaves it for onboard to migrate), then the onboard skill |
| Existing repo with messy docs | Then `/loadout:docs-audit` |
| Every feature | `/loadout:docs-sync` before merging |

`loadout init` shows a plan, asks, then scaffolds what is missing ([loadout init](../reference/cli.md#loadout-init)).

## Without the kit

1. Create `docs/README.md` as an index and `docs/adr/` with a one-line README describing the format.
2. Move your CLAUDE.md content into AGENTS.md, cut it to purpose, commands, hard conventions and a map, and make CLAUDE.md the single line `@AGENTS.md`.
3. Move every other fact into `docs/`, sorted by Diátaxis type, only creating the types you need. Delete the copies.
4. Turn decisions buried in notes, issues and commit messages into ADRs.
5. Shrink agent memories to one summary line and a link per topic.
6. Add "docs updated?" to your pull request checklist, and check links in CI.

Why the layout looks like this: [Documentation strategy](../explanation/documentation-strategy.md).
