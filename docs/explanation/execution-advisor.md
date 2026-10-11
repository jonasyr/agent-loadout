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

Two hooks of the loadout plugin catch the moment a plan is finished, so you do not have to remember (`plugins/loadout/hooks/advisor.py`; the hook table is in [Hooks](../reference/hooks.md#hooks-of-the-loadout-plugin)):

1. **`record`** runs after a file is written or edited (`PostToolUse` on `Write|Edit|MultiEdit`). It acts only for a file whose path matches `*/docs/superpowers/plans/*.md` or `*/plans/*.md`, excluding Claude Code's own plan-mode folder `/.claude/plans/`. The file must look like a plan: a heading with "Implementation Plan" in its first 15 lines and at least one `- [ ]` task. It marks the plan as written in this turn.
2. **`stop`** runs when the agent stops. For a plan written in this turn, with no ticked checkbox, that has not been evaluated and has not been nudged about, it blocks the stop once and asks the agent to run `/loadout:execution-advisor`. The instruction says that the advisor's recommendation replaces any execution question already asked. Every stop clears the "written" marks, and it never blocks twice in a row.
3. **`loadout advisor-mark PLAN`** is called by the skill. It records the plan's current version as evaluated, so the hook stays quiet. `settings.base.json` pre-approves this command.

Each version of a plan is nudged at most once. Ticking boxes while executing does not count as a change, so execution never triggers it again. The hooks are stdlib only, use no network and always exit 0, so they cannot break a session. State is in `~/.claude/.loadout/advisor-pending.json` and `advisor-done.json`.

## Why not SDD by default

Subagent-driven development is a common default after a plan, and it costs more than it looks: a fresh context per task (which re-reads the repo) plus a review per task. It pays off for risky or independent tasks and for protecting a near-full context. It does not pay off for a short plan with complete code, or for tasks that depend on each other's names and files. The advisor makes the trade-off explicit and cheap to check, and it keeps interactive and real-machine steps in the session where the user can answer.

The decision and the alternatives are in [ADR 0014](../adr/0014-execution-advisor-instead-of-default-sdd.md). The workflow rule that calls the advisor after a plan is `rules/workflow.md`.
