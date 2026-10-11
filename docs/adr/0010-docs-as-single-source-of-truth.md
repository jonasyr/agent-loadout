# 0010. docs/ is the single source of truth; AGENTS.md and memories link to it

- Status: Accepted
- Date: 2026-10-08
- Source: [Design spec, decision D10 and section 8](../superpowers/specs/2026-10-08-agent-loadout-design.md#8-knowledge-model-and-docs-skills)

## Context
Agents read always-loaded context files (AGENTS.md, CLAUDE.md, memories) at the start of every session. Long, generated files there cost tokens and are often out of date. Humans need complete documentation somewhere else. The same fact written in three places drifts apart.

## Decision
Every fact has one home. `docs/` holds everything a human may need, with decisions as ADRs in `docs/adr/`. `AGENTS.md` (and a `CLAUDE.md` that only contains `@AGENTS.md`) stays short and links into `docs/`. Serena memories hold a short summary plus a link. The README is the human entry point. `/loadout:docs-sync` and `/loadout:docs-audit` keep the layers in line.

## Alternatives considered
- A large AGENTS.md with everything: always loaded, goes stale, costs context in every session.
- Memories as the main store: invisible to humans and tied to one tool.

## Consequences
- Small always-loaded context; details load on demand through links.
- Discipline is needed: a change updates the owning layer and then fixes links. The static tests check links and that `CLAUDE.md` only imports `AGENTS.md`.
- The policy is delivered as a rule file, so it applies to the user's other repos as well.

## In the code
- `rules/docs-policy.md`, `rules/memory-policy.md`
- `plugins/loadout/skills/docs-sync/SKILL.md`, `plugins/loadout/skills/docs-audit/SKILL.md`
- `templates/project/` (`AGENTS.md`, `CLAUDE.md`, `docs/`)
- `tests/test_repo_static.py`
- Explanation: [Documentation strategy](../explanation/documentation-strategy.md)
