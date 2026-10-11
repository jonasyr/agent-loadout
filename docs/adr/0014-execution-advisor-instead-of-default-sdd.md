# 0014. Execution advisor instead of subagent-driven development by default

- Status: Accepted
- Date: 2026-10-09
- Source: [Design spec, sections 9 and 10](../superpowers/specs/2026-10-08-agent-loadout-design.md#10-loadout-hooks) (workflow rule, advisor hooks), [execution advisor skill](../../plugins/loadout/skills/execution-advisor/SKILL.md)

## Context
After a plan is written, the superpowers planner offers to run it with subagent-driven development (SDD). SDD gives every task a fresh context and a review. For short plans with complete code, or tasks that depend on each other, that costs more than it returns. For risky or independent tasks it is worth it. A default in either direction is wrong some of the time.

## Decision
A skill, `/loadout:execution-advisor`, judges each task against a rubric (completeness, coupling, risk, interaction, size, context, parallelism, cost) and recommends Inline, SDD or a Hybrid with a table of mode, model tier and review per task. The workflow rule makes the agent run it right after a plan and ask only its question. Two plugin hooks catch a finished plan the agent forgot to evaluate and nudge once per plan version.

## Alternatives considered
- SDD by default: pays for a fresh context and a review per task even when the plan is small or tightly coupled.
- Inline by default: gives up independent review for risky tasks and context protection for long plans.
- Leave the choice to the planner prompt: no evidence is shown, and users pick habitually.

## Consequences
- The recommendation names its reasons and its cost. "Subagents are cleaner" is not accepted as a reason.
- Anything that needs a yes from the user or acts on their machine runs inline, because a subagent cannot ask.
- It adds a skill, two hooks and a rule line to maintain, and the advisor's answer supersedes a planner question already shown.

## In the code
- `plugins/loadout/skills/execution-advisor/SKILL.md`
- `plugins/loadout/hooks/advisor.py` (`record`, `stop`, `mark`, `looks_like_plan`, `PLAN_GLOBS`)
- `cli/loadout/advisor.py` (`mark`), `cli/loadout/commands.py` (`advisor-mark`)
- `rules/workflow.md`
- Explanation: [The execution advisor](../explanation/execution-advisor.md)
