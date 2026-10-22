---
name: usage
description: Report how often the agents used Serena, codebase-memory, Context7 and Microsoft Learn versus grep and the shell, from `loadout usage` (counts only), and whether Serena's reminder and loadout's setup changed that. Use when the user asks whether the tools or hints are used, for a usage report, or to re-measure tool use.
---

# Usage report

Answer from `loadout usage`, the read-only counter of tool calls in this machine's local transcripts. Never open, grep or quote a transcript yourself: the command reads them and returns counts only, and that is all you report. Its reference is `docs/reference/cli.md`, section "loadout usage", in the folder `loadout kit-path` prints.

## 1. Run it

`loadout usage --json` (default: the last 14 days). If the user names a period, pass `--days N`; "since the hints shipped", "this week" and similar become a number of days. If the command is missing or exits 1 (no transcript folder for any agent that is on), say so and suggest `loadout check`; do not count by hand.

## 2. Read the JSON

- `days`, and `hint_sessions`: sessions whose last docs hint (Context7 and Microsoft Learn for web lookups; loadout no longer hints on code searches) was shown inside the window. It is one total for both agents, main sessions and subagents, and the hook keeps its state for 7 days, so it covers the window you asked for, capped at about 7 days.
- Per agent (`claude`, `codex`; an agent without a transcript folder is missing) and per kind (`main`, `subagent`): `sessions`, `calls`, `symbol_searches` (symbol-like Grep, `rg`, `grep` or `git grep` searches), `serena_denials` (sessions in which Serena's reminder denied a call) and `families.<name>.calls` / `.sessions` for `serena`, `codebase-memory`, `context7`, `microsoft-learn`, `grep`, `glob`, `read`, `shell`, `other`.
- Per agent, `claude.skipped_lines` (and `codex.skipped_lines`): that agent's transcript lines it could not read. Mention it only when it is large next to that agent's `calls`.

## 3. Report

Keep it to a short table and a few lines:

| | Main sessions | Subagents |
|---|---|---|
| Serena | sessions with a call / all sessions (percent) | … |
| codebase-memory | … | … |
| Context7 | … | … |
| Microsoft Learn | … | … |
| Symbol-like text searches | count | count |

Then:

- **Reminders and hints.** Give `serena_denials` as the sessions in which Serena's reminder fired. `hint_sessions` counts docs hints only; it mixes both agents and session kinds and only reaches back 7 days, so use it as a sign, not a denominator. If the user wants an effect measured, suggest comparing two runs some weeks apart.
- **Against the reference.** ADR 0026 (`docs/adr/0026-tool-hints-never-block.md`, section "Context") holds the first measurement, and ADR 0039 (`docs/adr/0039-serena-remind-tools-load-upfront-cbm-refresh.md`, section "Context") the one Serena's reminder and the upfront tools were built against: the share of Claude Code main sessions that used each tool. Compare only `claude.main` with it and say plainly whether use went up, stayed or went down. It was measured on one setup, so call it a reference, not a target. There is no reference for Codex (other tools and hooks): report its shares without an up or down, and with Codex only, say that no reference applies.
- **Caveats, only those that apply.** Many sessions with very few calls (hook or eval runs) lower every share; a Codex row with only a handful of sessions is too small to judge.
- **One next step**, if the numbers call for one: a longer `--days`, a re-measure after the hints have been out for two weeks, or, if use stays low after that, the next lever named in ADR 0039 (a system-prompt override).

Do not change settings, hooks or thresholds from here; for that the user asks the `loadout:configure` skill or opens a change in the kit.
