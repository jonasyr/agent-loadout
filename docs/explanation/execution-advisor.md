# The execution advisor

After a plan is written, someone has to decide how to run it: in the current session, task by task with a subagent each, or a mix. The execution advisor answers that from a rubric instead of a habit.

## What it does

`/loadout:execution-advisor` is a skill in the loadout plugin (`plugins/loadout/skills/execution-advisor/SKILL.md`). It reads the plan once, judges each task, and recommends one of three verdicts.

| Verdict | Meaning |
|---|---|
| Inline | Every task runs in this session. |
| SDD | Every task goes to an implementer subagent and gets its own review (subagent-driven development). |
| Hybrid | Anything else: some tasks inline, some delegated, some reviewed only at the end. |

Each task gets a row with its mode (Inline or Delegated), a model tier for delegated work (cheap, standard or top), and a review (per-task or final-review-only). The answer also names a cost for the recommended option and for all-Inline and all-SDD, plus a review policy. The user then picks, with the recommended option first. Nothing runs before that answer. Inline and Hybrid both run under superpowers:executing-plans, with one shared `progress.md` ledger; in a Hybrid the delegated rows go to subagents.

The rubric looks at:

- how complete the plan is (full code and exact commands favour transcription by a cheap model, or inline);
- coupling between tasks (shared names and files favour one implementer);
- risk (user data, security, irreversible actions justify an independent review);
- user interaction and real-machine actions (publish, deploy, anything needing a yes): always Inline, because a subagent cannot ask and must not act on your machine;
- size (one to three small tasks: inline);
- how full the current context is;
- whether tasks are independent enough to run in parallel;
- cost.

The skill must name the rubric reasons for SDD. "Subagents are cleaner" is not a reason. When it is done, it runs `loadout advisor-mark <plan>` to record that this version of the plan was evaluated.

## When the hook nudges

Two hooks of the loadout plugin catch the moment a plan is finished, so you do not have to remember. The full conditions are in [Hooks](../reference/hooks.md#the-execution-advisor-hooks). In short:

1. After a file write, `advisor.py record` remembers files under `docs/superpowers/plans/` or `plans/` that look like a plan: an "Implementation Plan" heading in the first 15 lines and at least one `- [ ]` task. Claude Code's own plan-mode files are excluded.
2. When the agent stops, `advisor.py stop` blocks once for a plan written in that turn if no box is ticked yet and the plan version was neither evaluated nor nudged about. The message asks the agent to run the skill and says its recommendation replaces any execution question already asked.

Each version of a plan is nudged at most once. Ticking boxes while executing does not count as a change, so execution never triggers it again. The hooks are stdlib only, use no network and always exit 0, so they cannot break a session.

## Why not SDD by default

Subagent-driven development is a common default after a plan, and it costs more than it looks: a fresh context per task (which re-reads the repo) plus a review per task. It pays off for risky or independent tasks and for protecting a near-full context. It does not pay off for a short plan with complete code, or for tasks that depend on each other's names and files. The advisor makes the trade-off explicit and cheap to check, and it keeps interactive and real-machine steps in the session where the user can answer.

The decision and the alternatives are in [ADR 0014](../adr/0014-execution-advisor-instead-of-default-sdd.md). The workflow rule that calls the advisor after a plan is `rules/workflow.md`.
