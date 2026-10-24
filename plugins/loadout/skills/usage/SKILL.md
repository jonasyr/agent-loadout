---
name: usage
description: Report how often the agents used Serena, codebase-memory, Context7 and Microsoft Learn versus grep and the shell, from `loadout usage` (counts only), and whether a change (Serena's reminder, loadout's setup) helped, as before/after. Use when the user asks whether the tools or hints are used, whether a change helped, for a usage report, or to re-measure tool use.
---

# Usage report

Answer from `loadout usage`, the read-only counter of tool calls in this machine's local transcripts. Never open, grep or quote a transcript yourself: the command reads them and returns counts only, and that is all you report. Its reference is `docs/reference/cli.md`, section "loadout usage", in the folder `loadout kit-path` prints.

## 1. Run it

- **"Did X help?", "since #57", "after the update":** run `loadout usage --around <moment> --days 7 --json`. The moment is when the change reached this machine: `YYYY-MM-DD` or `YYYY-MM-DDTHH:MM`. Ask for it if the user does not know. A merge date from `git log` in the kit (`loadout kit-path`) is a fair guess; say it is one.
- **"How is it now?":** run `loadout usage --json` (the last 14 days), or `--days N` / `--since <moment>` for the period the user names.
- **Against ADR 0026 or ADR 0039's numbers:** run `loadout usage --legacy --json`. Those references were measured that way.
- **When a number looks wrong:** `loadout usage --sessions` lists one line per session (ids and counts only). The user can open a few of those sessions themselves to check.

If the command is missing or exits 1 (no transcript folder for any agent that is on), say so and suggest `loadout check`; do not count by hand.

## 2. Read the JSON

- `windows.after` and, with `--around`, `windows.before`: `start`, `end`, `days`, and `partial` (the after window is not over yet).
- `thresholds`: `min_calls`, `follow_within` and `min_sessions`.
- Per agent (`claude`, `codex`; an agent without a transcript folder is missing) there are the rows `main`, `subagent`, `subagent_prompted` and `subagent_unprompted`. The last two count only when `prompted_known` is true. Each row holds:
  - `sessions` (counted, at least `min_calls` tool calls) and `tiny` (left out);
  - `code_tool_share`: lookup calls ÷ (lookups + symbol-like searches), the headline;
  - `follow_through`, with `followed` / `denials`: after a reminder, a lookup within `follow_within` calls;
  - `family_share.<family>`, `per_session.symbol_searches`, and today's `families` and `serena_denials` counts.
- With `--around`: `before` holds the same rows, and `change.<row>.<metric>` holds `↑`, `↓`, `=`, `new`, `—` or `too few sessions`.
- `hint_sessions`: docs hints in the after window. The hook keeps only 7 days, so treat it as a sign.
- `skipped_lines`: mention it only when it is large next to the calls.

## 3. Report

A short table, then a few lines:

| | Main sessions | Subagents (prompted / not) |
|---|---|---|
| Code-tool share | before → after, arrow | … |
| Reminder follow-through | … | … |
| Sessions with Serena / codebase-memory | … | … |
| Symbol searches per session | … | … |
| Counted sessions (+ tiny) | … | … |

Then:

- **The verdict:** did the change help, in one sentence per kind, from the arrows. `too few sessions` means "not measurable yet", never "no effect". Say when the after window is partial.
- **Not prompted subagents** show default behaviour. Prompted ones show what naming the tools in a prompt does. Say which one moved.
- **Follow-through:** a low share means agents repeat the grep after a reminder instead of switching tools.
- **Against the reference** (only with `--legacy`): compare `claude.main` with ADR 0039's Context. It is a reference measured on one setup, not a target. Codex has none.
- **One next step**, if the numbers call for one: wait and re-run `--around` once the after window has 20 sessions, or, if use stays low, the next lever in ADR 0039 (a system-prompt override).

Do not change settings, hooks or thresholds from here; for that the user asks the `loadout:configure` skill or opens a change in the kit.
