# Use the codex-reviewer when Codex's review quota is out

Use this page when Codex's GitHub review ("@codex review") is unavailable, for example because its quota is exhausted, and you want a review of your branch anyway. The `codex-reviewer` agent reviews the diff with Codex's open-source rubric and returns the same JSON findings.

It is an add-on, off by default ([why](../adr/0044-codex-reviewer-as-opt-in-plugin.md), [entry](../reference/included-tools.md#optional-global-add-ons)). It works in Claude Code only; loadout never adds it to Codex, which has its own `/review`.

## Turn it on

```bash
loadout configure set plugin codex-reviewer@agent-loadout on
```

Then run `/reload-plugins` in a running Claude Code session. In a repo whose `.claude/settings.json` already enables it (this one does), skip this step.

## Run it

On the branch you want reviewed, ask Claude Code:

> run the codex-reviewer agent on this branch

The agent compares the branch with the repo's default branch (`origin/HEAD`, else `main`, else `master`).

## Read the result

The answer is JSON in the rubric's format:

- `findings`: each has a title, a body and a priority. `P0` blocks, `P1` should be fixed, `P2` is minor. Nothing below P2 is reported.
- `code_location`: the file and line range a finding is about.
- `overall_correctness`: whether the change is correct as it stands, with a short explanation.

Fix what you agree with, then run it again.

## What it reads and does

- It reads the repo's `AGENTS.md`, the file Codex's own review reads. It applies the "Code Review Rules" section if there is one, else the whole file, and names the rule a finding rests on. Without an `AGENTS.md` it uses the rubric alone.
- It never edits files and never runs installers or commands that change the machine. It runs a test command only when `AGENTS.md` names one.

## Turn it off

```bash
loadout configure set plugin codex-reviewer@agent-loadout off
```
