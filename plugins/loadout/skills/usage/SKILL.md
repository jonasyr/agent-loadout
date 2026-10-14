---
name: usage
description: Report how often the agents used Serena, codebase-memory, Context7 and Microsoft Learn versus grep and the shell, from `loadout usage` (counts only), and whether loadout's tool hints changed that. Use when the user asks whether the tools or hints are used, for a usage report, or to re-measure tool use.
---

# Usage report

Answer from `loadout usage`, the read-only counter of tool calls in this machine's local transcripts. Never open, grep or quote a transcript yourself: the command reads them and returns counts only, and that is all you report. Its reference is `docs/reference/cli.md`, section "loadout usage", in the folder `loadout kit-path` prints.

## 1. Run it

`loadout usage --json` (default: the last 14 days). If the user names a period, pass `--days N`; "since the hints shipped", "this week" and similar become a number of days. If the command is missing or exits 1 (no transcript folder for an agent that is on), say so and suggest `loadout check`; do not count by hand.

## 2. Read the JSON

- `days`, and `hint_sessions`: sessions whose last tool hint was shown inside the window. It is one total for both agents, main sessions and subagents, and the hook keeps its state for 7 days, so it covers about the last week whatever `--days` says.
- Per agent (`claude`, `codex`; an agent without a transcript folder is missing) and per kind (`main`, `subagent`): `sessions`, `calls`, `symbol_searches` (symbol-like Grep, `rg`, `grep` or `git grep` searches, which a hint could have answered) and `families.<name>.calls` / `.sessions` for `serena`, `codebase-memory`, `context7`, `microsoft-learn`, `grep`, `glob`, `read`, `shell`, `other`.
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

- **Hints.** Give `hint_sessions` as a sign that hints fire, not a denominator: it mixes both agents and session kinds and only reaches back 7 days. A hint fires only after enough searches, so a low count does not say when the plugin got the hints; if the user wants an effect measured, suggest comparing two runs some weeks apart.
- **Against the reference.** ADR 0026 (`docs/adr/0026-tool-hints-never-block.md`, section "Context") holds the measurement the hints were built against: the share of Claude Code main sessions that used each tool. Compare only `claude.main` with it and say plainly whether use went up, stayed or went down. It was measured on one setup, so call it a reference, not a target. There is no reference for Codex (other tools and hooks): report its shares without an up or down, and with Codex only, say that no reference applies.
- **Caveats, only those that apply.** Many sessions with very few calls (hook or eval runs) lower every share; a Codex row with only a handful of sessions is too small to judge.
- **One next step**, if the numbers call for one: a longer `--days`, a re-measure after the hints have been out for two weeks, or, if use stays low after that, a stronger nudge at session or prompt start (ADR 0026 ruled out blocking a search).

Do not change settings, hooks or thresholds from here; for that the user asks the `loadout:configure` skill or opens a change in the kit.
