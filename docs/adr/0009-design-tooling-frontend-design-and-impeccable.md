# 0009. Design tooling: frontend-design and impeccable

- Status: Accepted
- Date: 2026-10-08
- Source: [Design spec, decision D9 and section 4.3](../superpowers/specs/2026-10-08-agent-loadout-design.md#2-decisions)

## Context
UI work needs two things: a design direction before building, and an audit and polish pass after. Several design skills exist. They overlap, and each one's description costs context.

## Decision
Use the official `frontend-design` plugin for aesthetic direction and `impeccable` for audit, critique and polish, with its per-edit hook turned off. Other design skill sets, such as taste-skill, are marked superseded in the catalog. The research behind this was done on 2026-10-08, and the catalog entries keep the reasons.

## Alternatives considered
- taste-skill and similar sets: overlap with the two chosen plugins, so they only add context.
- A single tool for both phases: none covered direction and audit well.

## Consequences
- A fixed UI loop in `rules/workflow.md`: frontend-design, build, browser check, impeccable audit and polish.
- `adopt` proposes removing the superseded skills on machines that have them, after asking.
- The choice rests on research from one date and may need revisiting.

## In the code
- `settings.base.json` (`frontend-design@claude-plugins-official`, `impeccable@impeccable`)
- `catalog.json` (entry `skills-taste`, status superseded)
- `rules/workflow.md` (UI loop)
