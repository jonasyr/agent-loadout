# Design: `loadout usage` tells whether a change helped

- Date: 2026-10-24
- Status: Draft (waiting for approval)
- Builds on: [ADR 0039](../../adr/0039-serena-remind-tools-load-upfront-cbm-refresh.md) (the reference measurement), [ADR 0040](../../adr/0040-serena-remind-skips-harmless.md), `cli/loadout/usage.py`, `docs/reference/cli.md#loadout-usage`

## Why

The maintainer ships changes meant to make agents use Serena and codebase-memory instead of grep: #57 (Serena's reminder, tools loaded upfront, subagent context) and #60 (the reminder skips harmless searches). The question after each one is whether it helped. Today's `loadout usage` answers that question poorly.

The first check after #57 (2026-10-24, last 24 hours) showed four weaknesses:

- **Diluted shares.** 16 main sessions, many of them hook runs, headless checks or evals with a handful of calls, pulled every share down.
- **Fixed windows only.** The window is "the last N days". A window that straddles the change mixes before and after. A before/after comparison means two runs and mental arithmetic.
- **The wrong question.** "Sessions that used Serena at least once" says nothing about whether the agent picks the right tool when it looks for code. A session with one Serena call and 50 greps counts the same as one with no grep at all.
- **Reminders without outcomes.** `serena_denials` counts sessions with a denial, but not whether the agent then switched to Serena or the graph, or just repeated the grep.

There is also a bias. Subagents whose parent's prompt names the tools use them far more often (ADR 0039: 23 of the 34 subagents that used them). That hides how subagents behave by default.

## Goals

1. **Before and after, side by side** (the maintainer's choice):
   - `loadout usage --around DATE --days N` gives N days before DATE and N days after it.
   - Every metric appears in both windows, followed by a plain arrow: `↑`, `↓` or `=`.
   - When the after window is not over yet, the output says how many days it covers.
   - `--since DATE` gives only the after window (DATE to now).
   - `--days N` alone keeps today's meaning: the last N days, one window.
2. **The new metrics** (the maintainer chose all four):
   - **Code-tool share of code lookups**, per agent and kind: Serena and codebase-memory *lookup* calls, divided by those calls plus symbol-like searches (today's `symbol_searches` counter). It is shown as a percentage, with the two counts behind it. This is the headline metric. Only lookup tools count (the maintainer's choice):
     - Serena: `find_symbol`, `get_symbols_overview`, `find_referencing_symbols`, `find_declaration`, `find_implementations`;
     - codebase-memory: `search_graph`, `trace_path`, `get_code_snippet`, `query_graph`, `search_code`, `get_file_outline`, `get_architecture`.

     Housekeeping calls do not count: `initial_instructions`, memories, `onboarding`, `index_status`, `index_repository`. They rise on their own since the tools load upfront, and would inflate the after window. Tools are matched by the name after the server prefix (`mcp__plugin_loadout_serena__find_symbol`, `mcp__serena__find_symbol` and Codex's form alike).
   - **Reminder follow-through:** of the denials by Serena's reminder in the window, how many were followed within the next 5 tool calls by a Serena or codebase-memory call. Shown as "followed / denials".
   - **Tiny sessions left out:** sessions with fewer than 5 tool calls are not counted in any share. The output says how many were left out.
   - **Subagents split into prompted and not prompted:** a subagent is *prompted* when its task prompt names the tools. The subagent rows are split into those two groups.
3. **A guard against small samples:** a window with fewer than 20 counted sessions for a row shows "too few sessions" instead of an arrow.
4. **Overridable defaults:** `--min-calls 5`, `--follow-within 5` and `--min-sessions 20` (the maintainer took the proposed defaults).
5. **Output:**
   - A terminal table, plus two or three plain lines.
   - `--json` carries every number, so the `loadout:usage` skill can report it.
   - The rows of today's output stay: sessions per tool family and symbol-like search counts. They now follow the new session rules (the maintainer's choice: one consistent set of numbers). `--legacy` reproduces today's counting exactly (line by line, tiny sessions included, one `--days` window), so ADR 0039's reference stays reproducible.

## Non-goals

- No HTML report or charts over time (the maintainer chose the terminal table).
- No change to what counts as a symbol-like search (`cli/loadout/searches.py`) or to the families.
- No new data source. Only the local transcripts that `loadout usage` already reads.
- No resolving a PR number or commit to a date in this change. The date form comes first; a `#57` form can be added later.

## Anti-goals

- **Leaking transcript content.** The command reads transcripts and prints counts only. It never quotes or prints a command, a prompt or a path from a transcript. The prompted/not-prompted test looks for tool names in the prompt and keeps only the yes or no. This rule holds today (the `loadout:usage` skill says so) and must hold for every new metric.
- **Becoming slow.** One pass over the transcripts, as today. Two windows do not mean two passes.
- **Precision that is not there.** A share from 7 sessions must not read like a finding. The guard in goal 3 is part of the design.

## Definitions (decided)

- **Session windows:** a session belongs to the window that holds its first timestamped event. All of its events count there. A session that started before the before window is not counted, even if it ran into it.
- **Counted session:** a session with at least `--min-calls` tool calls, of any kind.
- **Code lookups of a session:** its Serena calls, plus its codebase-memory calls, plus its symbol-like searches. The share of a row is the sum over its counted sessions: (Serena + graph) ÷ (Serena + graph + symbol-like searches). It is shown only when the row has at least one code lookup.
- **Follow-through:** a denial is a tool result that today's `_denial` recognises. It is *followed* when one of the next `--follow-within` tool calls in the same session is a Serena or codebase-memory call. A denial with fewer calls after it, at the end of the session, counts as not followed.
- **Prompted subagent:**
  - **Claude Code:** the first user message of the subagent's transcript (its task prompt) mentions `serena`, `codebase-memory`, `find_symbol`, `search_graph`, `trace_path` or `get_code_snippet` (case-insensitive).
  - **Codex:** the same test on its subagent's first user input, if the session file carries it. If it does not, Codex subagents are reported unsplit, and the output says so.
- **The arrows** *(my call, after the builder check)*: every compared row is normalised per counted session, because the two windows differ in size.
  - Shares get the 5-point rule: sessions using a family ÷ counted sessions, the code-tool share, and follow-through.
  - Rates get the 20 % rule: symbol-like searches per counted session, calls per counted session.
  - A rate that goes from 0 to more than 0 shows `new`.
  - The 20-session guard applies per row: agent × kind, and each half of the prompted split on its own.
- **The date** *(my call)*: `--around` and `--since` take `YYYY-MM-DD` (local midnight) or `YYYY-MM-DDTHH:MM` (local time). The moment itself belongs to the after window.
- **Docs hints:** `hint_sessions` covers only the after window, because the hook keeps 7 days of state. The output says so.

## Validation (the maintainer chose all three)

1. **Synthetic transcripts with known answers.** Tests build small Claude Code and Codex sessions whose right answer is known, and assert every metric exactly:
   - a tiny session;
   - lookups next to housekeeping calls;
   - a denial followed within 5 calls, and a denial followed by more greps;
   - a denial at the end of a session;
   - prompted and unprompted subagents, with the SubagentStart context stored as its own attachment record, which must not count as the prompt;
   - sessions on both sides of the date, and one that started before the before window;
   - `--legacy` reproducing today's output.
2. **`--sessions`: a breakdown to spot-check.** One line per session: its id (the transcript's file name), agent, kind, counted or tiny, window, code lookups by kind, the share, denials and how many were followed, and prompted yes or no. Numbers and ids only, never content. With it, the maintainer opens a sample of sessions and checks the counts by hand.
3. **A known-effect check.** Before the merge, `loadout usage --around 2026-10-22T19:35 --days 2` must show a clear rise for Claude Code subagents. The 2026-10-24 check found subagent use going from about 3 % to about 50 %. If that rise does not show, the measurement is wrong. Repeat around 2026-10-29 with `--days 7`.

## Constraints

- **Stdlib only:** standard library only in `cli/loadout/`, Python 3.11+.
- **Tests:** they use `fake_home` and synthetic transcripts, as `tests/test_usage*.py` do today. They never read the real `~/.claude` or `~/.codex`.
- **Agent isolation:** with an agent off, its transcripts are not read, as today.
- **Compatible JSON:** today's JSON keys keep their meaning. New keys are added. For example, a `windows` object holds `before` and `after` when `--around` is given; plain `--days` keeps today's shape plus the new metrics.
- **Docs:** `docs/reference/cli.md#loadout-usage` and the `loadout:usage` skill (`plugins/loadout/skills/usage/SKILL.md`) are updated. The skill learns to run `--around` when asked "did X help", and to report follow-through and the prompted split.

## Left to the builder

- **The table layout:** within a terminal width of about 100 columns.
- **Codex's first user input:** how to find it in a Codex session file, if it is there at all. Verify this against a real Codex session's structure (keys only, no content), or against Codex's source.
- **Timestamps:** how session start times are read. Today `_lines` filters lines by timestamp. Keep one pass.
- **Where the code goes:** whether the new metrics live in `usage.py` or a small sibling module.
