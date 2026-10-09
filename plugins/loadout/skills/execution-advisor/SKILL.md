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

Model tiers: **cheap** (Haiku-class) for transcription and mechanical edits, **standard** (Sonnet-class) for normal implementation, **top** (Opus-class) for design-heavy or risky work and for the final whole-branch review. A tier only applies to delegated work: an inline task runs on the session's model, so write `session` in its Model column. Transcription done inline is paid at the session model's price; delegating it to the cheap tier pays off once the tasks are several or long enough to amortise a subagent's ramp-up (re-reading the repo). You may batch trivial same-shape edits into one cheap delegated dispatch.

## 3. Verdict

Each task row is **Inline** (done in this session) or **Delegated** (an implementer subagent with an explicit model). Its review is **per-task** (an independent task reviewer right after it) or **final-review-only** (covered by the one whole-branch review at the end).

- **Inline**: every task is Inline.
- **SDD**: every task is Delegated with a per-task review (exactly what superpowers:subagent-driven-development does).
- **Hybrid**: anything else, e.g. some tasks Inline, or Delegated tasks that are final-review-only.

Interactive and real-machine steps are always Inline, whatever the verdict.

## 4. Record the evaluation

Run `loadout advisor-mark <plan path>` once the verdict is settled, before you write the answer. It records this version of the plan as evaluated, so the Stop hook does not ask again; a changed plan is evaluated again. If the command is missing, skip it.

## 5. Output (compact, in one final message)

```
Verdict: Hybrid — <one sentence why>

| Task | Mode | Model | Review | Why |
|---|---|---|---|---|
| 1 Schema migration | Inline | session | per-task | migrates user data; needs the user's go-ahead |
| 2 CSV writer | Delegated | cheap | final-review-only | complete code in plan, independent |

Cost: recommended <low|medium|high> · all-Inline <…> · all-SDD <…>
Review policy: <e.g. per-task review on tasks 1 and 4, then one top-tier whole-branch review at the end>
```

Always include the Cost and Review policy lines. Then ask the user to choose, with the recommended option first and marked **(Recommended)**, followed by the alternatives (e.g. "1. Hybrid as above (Recommended) 2. All Inline 3. All SDD"). If an execution question or recommendation was already shown (for example the planner's "Subagent-driven or Inline?"), say explicitly that this recommendation supersedes it. Do not start executing before the user answers.

## 6. Running the chosen option

- **SDD** (every row Delegated with per-task review): superpowers:subagent-driven-development, unchanged, with the model from each row.
- **Inline** and **Hybrid**: one driver, superpowers:executing-plans. It owns the single workspace and ledger (`<workspace>/progress.md`, from the `sdd-workspace` script), the pre-flight scan and the final review. Walk the tasks in plan order:
  - **Inline row**: executing-plans' own per-task loop (`task-start`, the steps, `task-done`).
  - **Delegated row**: dispatch one implementer subagent with subagent-driven-development's `implementer-prompt.md` and the row's model set explicitly. A batched dispatch covers its consecutive tasks in one brief.
  - **Per-task review**: only on rows that say so, dispatch a reviewer with subagent-driven-development's `task-reviewer-prompt.md` before moving on; fix what it finds.
  - **Ledger**: record every finished task, inline or delegated, as its own `Task <N>: complete` line in that `progress.md`.
  - **End**: one top-tier whole-branch review, as executing-plans prescribes, then superpowers:finishing-a-development-branch.
