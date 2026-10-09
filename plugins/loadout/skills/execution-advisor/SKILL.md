---
name: execution-advisor
description: Recommend how to execute an implementation plan — Inline, subagent-driven (SDD) or a Hybrid with a per-task table (mode, model tier, review) — from a rubric instead of defaulting to subagents. Use right after a plan is written, when a hook asks for it, or when the user asks "SDD or inline?" / how to run a plan.
---

# Execution advisor

Judge the plan on evidence, then let the user choose. Never recommend SDD without naming the rubric reasons that justify it; "subagents are cleaner" is not a reason.

## 1. Read the plan once

Use the plan path from the hook message or the user; otherwise the newest file in `docs/superpowers/plans/`. Read it once, in full. List its tasks (number, title, files touched).

## 2. Judge each task

| Criterion | Pushes towards |
|---|---|
| **Plan completeness**: the plan already contains the complete code and exact commands | Transcription: Inline, or the cheapest model tier if delegated |
| **Cross-task interface coupling**: later tasks depend on names, types or files from earlier ones | Continuity: Inline or the same implementer; still give risky parts an independent review |
| **Risk**: user data, security, other people's machines, irreversible actions | Per-task independent review is worth its cost (SDD task or inline + a dedicated reviewer) |
| **User interaction or real-machine actions**: publish, deploy, migration on real data, questions, credentials, anything needing a yes | Must be Inline (a subagent cannot ask the user and must not act on the real machine) |
| **Size and count**: 1–3 small tasks | Inline: SDD overhead is not worth it |
| **Current session context**: large or near-full context | SDD protects it; a fresh session makes Inline cheap |
| **Independent, parallelisable tasks** (no shared files or interfaces) | Parallel subagents |
| **Cost**: SDD = a fresh context per task + a review per task; Inline = one context + one final review | Pick the cheapest option that still covers the risk |

Model tiers: **cheap** (Haiku-class) for transcription and mechanical edits, **standard** (Sonnet-class) for normal implementation, **top** (Opus-class) for design-heavy or risky work and for the final whole-branch review.

## 3. Verdict

- **Inline**: every task stays in this session (superpowers:executing-plans).
- **SDD**: every task goes to a subagent (superpowers:subagent-driven-development).
- **Hybrid**: some tasks inline, some delegated, per the table.

Interactive and real-machine steps are always Inline, whatever the verdict.

## 4. Output (compact)

```
Verdict: Hybrid — <one sentence why>

| Task | Mode | Model | Review | Why |
|---|---|---|---|---|
| 1 Schema migration | Inline | top | per-task | migrates user data; needs the user's go-ahead |
| 2 CSV writer | SDD | cheap | final-only | complete code in plan, independent |

Cost: recommended <low|medium|high> · all-Inline <…> · all-SDD <…>
Review policy: <e.g. per-task review on tasks 1 and 4, then one Opus whole-branch review at the end>
```

Review is one of `per-task`, `final-only` or `none`. Then ask the user to choose, with the recommended option first and marked **(Recommended)**, followed by the alternatives (e.g. "1. Hybrid as above (Recommended) 2. All Inline 3. All SDD"). Do not start executing before the user answers.

## 5. Record the evaluation

Run `loadout advisor-mark <plan path>` once you have presented the recommendation. It records this version of the plan as evaluated, so the Stop hook does not ask again; a changed plan is evaluated again. If the command is missing, skip it.

## 6. Running the chosen option

- **Inline**: superpowers:executing-plans in this session.
- **SDD**: superpowers:subagent-driven-development, passing each task's model tier and review policy.
- **Hybrid**: one session, one shared ledger (the plan's checkboxes plus the todo list). Walk the tasks in plan order: run delegated tasks through superpowers:subagent-driven-development (one task per subagent, with the tier from the table) and inline tasks through superpowers:executing-plans, ticking each task in the plan as it lands. Run independent delegated tasks in parallel only when they touch disjoint files. Apply the review column, then the final review policy.
