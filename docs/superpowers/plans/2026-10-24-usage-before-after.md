# `loadout usage` tells whether a change helped: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `loadout usage` compares a before and an after window around a date. It reports four new metrics: the code-tool share of code lookups, reminder follow-through, tiny sessions left out, and subagents split into prompted and not prompted. It also gets a per-session breakdown to spot-check, and `--legacy` reproduces today's counting.

**Architecture:**
- A new module, `cli/loadout/usage_sessions.py`, reads each transcript once into a `Session` record (counts only, never content).
- `cli/loadout/usage.py` keeps today's `collect` as the legacy path, unchanged. It gains `report(...)`, which groups `Session`s into windows and rows and computes the metrics and arrows, plus renderers for the table and the session lines.
- `commands.py` wires the new flags.

**Tech stack:** Python 3.11+ standard library; pytest with `fake_home` and synthetic transcripts (the style of `tests/test_usage.py`).

**Spec:** `docs/superpowers/specs/2026-10-24-usage-before-after-design.md`

## Global constraints

- **Stdlib only** in `cli/loadout/`, Python 3.11+.
- **Counts only:** no command, prompt, path or other content from a transcript is ever printed or stored in the report. The prompted test keeps a bool. Session ids are the transcript's file stem.
- **One pass:** each transcript file is read at most once per run, whatever the windows.
- **Agent isolation:** with an agent off (`targets`), its transcripts are not read.
- **Tests:** they use `fake_home` and synthetic transcripts and never read the real `~/.claude` or `~/.codex`.
- **Defaults:** `--min-calls 5`, `--follow-within 5`, `--min-sessions 20`. Shares move at 5 percentage points, rates at 20 %.
- **Lookup tools** (matched by the tool name after its server prefix):
  - Serena: `find_symbol`, `get_symbols_overview`, `find_referencing_symbols`, `find_declaration`, `find_implementations`;
  - codebase-memory: `search_graph`, `trace_path`, `get_code_snippet`, `query_graph`, `search_code`, `get_file_outline`, `get_architecture`.
- **Prompted-subagent words** (case-insensitive substring): `serena`, `codebase-memory`, `find_symbol`, `search_graph`, `trace_path`, `get_code_snippet`.
- **Commits:** Conventional Commits, with no AI attribution.
- **Code tools:** implementers use Serena (`find_symbol`, `get_symbols_overview`) and codebase-memory (`search_graph`, `get_code_snippet`, project `home-jonas-Documents-Code-agent-loadout`) before grep.

## Review focus

1. **Sessions without timestamps:** older transcripts may have lines without `timestamp`. Such a session's start falls back to the file's mtime, and it must never crash or be placed in both windows. (Task 1: `test_a_session_without_timestamps_starts_at_file_mtime`.)
2. **The SubagentStart context:** it names the tools, but lives in an `attachment` record. It must not make a subagent "prompted". Only the first `user` message with string or text content counts. (Task 1: `test_subagent_context_attachment_is_not_the_prompt`.)
3. **A partial after window:** `--around` with an after window shorter than `--days` (the date is recent) must say how many days the window covers. Its rates must stay per session, so the arrows don't fall just because the window is shorter. (Task 3: `test_partial_after_window_is_labelled_and_normalised`.)
4. **Empty and zero rows:** a row with no counted sessions, or with no code lookups, must show "too few sessions" or `—`. A before rate of 0 shows `new`, never a division error. (Task 3: `test_empty_and_zero_rows_never_divide_by_zero`.)
5. **Today's keys:** `claude.main.sessions`, `.calls`, `.symbol_searches`, `.serena_denials` and `.families.*` stay present, with the same types, in the new JSON, so the `loadout:usage` skill and old scripts keep working. (Task 4: `test_json_keeps_todays_keys`.)

---

### Task 1: One `Session` per Claude Code transcript

**Files:**
- Create: `cli/loadout/usage_sessions.py`
- Test: `tests/test_usage_sessions.py`

**Interfaces:**
- Produces:
  - `@dataclass Session`, with these fields:
    - `id: str`, `agent: str` (`"claude"` or `"codex"`), `kind: str` (`"main"` or `"subagent"`), `start: float` (epoch);
    - `calls: dict[str, int]` (per family, as `usage.family`), `total_calls: int`;
    - `lookups: dict[str, int]` (`{"serena": n, "codebase-memory": n}`, lookup tools only);
    - `symbol_searches: int` (as today's counters);
    - `denials: int`, `followed: int`;
    - `prompted: bool | None` (None for main sessions, or when the prompt cannot be found).
  - `LOOKUP_TOOLS: dict[str, frozenset[str]]`, family → tool names (the Global Constraints list).
  - `PROMPT_WORDS: tuple[str, ...]`.
  - `claude_sessions(earliest: float, follow_within: int, skipped: list[int]) -> list[Session]`: every transcript under `paths.claude_home()/"projects"` with an mtime ≥ `earliest`. `skipped[0]` counts unreadable lines, as today.
- Consumes: `usage.family`, `usage._lines`-style reading (reuse `_read_record`, the `MAX_LINE` guard and `_denial`, `_symbol_pattern`, `_symbol_searches`, `_command_text` from `usage.py`, without its window filter).

**Rules:**
- **`start`:** the earliest parsable `timestamp` of the file's records, else the file's mtime.
- **`kind`:** `"subagent"` when `"subagents"` is in the path parts, as today.
- **Tool calls:** taken in order. Each `tool_use` is one call. The lookup tool name is `name.rsplit("__", 1)[-1]` for `mcp__…` names.
- **Follow-through:** a tool result for which `_denial` is true opens a denial. The denial is followed when one of the next `follow_within` tool calls is a lookup tool (Serena or codebase-memory). A denial with fewer calls after it, at the end of the session, counts as not followed.
- **`prompted`:** for a subagent, true or false from the first record of `type == "user"` whose message content is a string, or a list holding a `text` item. Any `PROMPT_WORDS` word in that text means true. No such record gives None. Never store the text.

- [ ] **Step 1: Write the failing tests** in `tests/test_usage_sessions.py`, with a helper that writes a synthetic Claude Code transcript (records with `type`, `timestamp` and `message.content` items, like `tests/test_usage.py::_claude`):
  - `test_lookups_count_only_lookup_tools`: `mcp__plugin_loadout_serena__find_symbol` ×2, `mcp__serena__initial_instructions`, `mcp__plugin_loadout_codebase-memory-mcp__search_graph`, `…__index_status` → `lookups == {"serena": 2, "codebase-memory": 1}`, `calls["serena"] == 3`.
  - `test_denial_followed_within_n`: denial, then Bash, Read, `find_symbol` → `denials == 1`, `followed == 1`. With `follow_within=2` → `followed == 0`.
  - `test_denial_at_the_end_is_not_followed`: denial, then one Bash, then the end → `followed == 0`.
  - `test_prompted_subagent`: a subagent whose first user text holds "use Serena find_symbol" → `prompted is True`. One with "fix the README" → False. A main session → None.
  - `test_subagent_context_attachment_is_not_the_prompt`: an `attachment` record holding `hook_additional_context` with "mcp__plugin_loadout_serena__find_symbol", then a first user text "fix the README" → False.
  - `test_start_is_the_earliest_timestamp`, and `test_a_session_without_timestamps_starts_at_file_mtime`.
  - `test_symbol_searches_match_todays_counter`: the same transcript gives the same `symbol_searches` as `usage.collect`'s `claude.main.symbol_searches`.
  - `test_no_content_is_kept`: the transcript holds the string "SECRET-PROMPT". No field of the resulting `Session` (via `dataclasses.asdict`) contains it.
- [ ] **Step 2: Run them and see them fail.** Run `uv run --python 3.12 --with pytest pytest -q tests/test_usage_sessions.py`. Expected: FAIL (the module does not exist).
- [ ] **Step 3: Implement `usage_sessions.py`** per the rules above. Move the helpers you reuse into it only if `usage.py` keeps importing them from there; never duplicate them.
- [ ] **Step 4: Run the tests and see them pass**, and run `tests/test_usage.py` unchanged. Expected: all PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat(usage): one session record per Claude Code transcript"`

### Task 2: One `Session` per Codex session file

**Files:**
- Modify: `cli/loadout/usage_sessions.py`
- Test: `tests/test_usage_sessions.py`

**Interfaces:**
- Consumes: `Session`, `LOOKUP_TOOLS`, `PROMPT_WORDS` (Task 1).
- Produces: `codex_sessions(earliest: float, follow_within: int, skipped: list[int]) -> list[Session]`. It reads `paths.codex_home()/"sessions"/**/*.jsonl`. `kind` comes from `session_meta`, as today's `_codex` decides it. The calls come from `function_call`, `custom_tool_call` and `mcp_tool_call_end`, deduplicated by `call_id` as today. A lookup comes from an MCP tool name (the `name` after its server prefix, or `invocation.tool`). Denials come from `function_call_output` and `custom_tool_call_output`.

**Ruling for the builder:** look up where a Codex subagent's task prompt lives:
- from the structure of a real session file under `~/.codex/sessions`: record `type`s and `payload` keys only. Never print values;
- or from Codex's source (`openai/codex`, `codex-rs/protocol`).

If a user-input record exists (for example a `response_item` with `role: "user"`, or an `event_msg` of `user_message`), `prompted` comes from its first one. If none exists, Codex subagents get `prompted=None`. Write which case holds into the report file and into a code comment.

- [ ] **Step 1: Write the failing tests**:
  - `test_codex_lookups_and_calls`: an `mcp_tool_call_end` for server `serena`, tool `find_symbol`, and a `function_call` named `mcp__serena__find_symbol` with the same `call_id` → counted once, `lookups["serena"] == 1`.
  - `test_codex_denial_followed`: a `function_call_output` with Serena's deny reason, then a shell call, then a serena lookup → `followed == 1`.
  - `test_codex_subagent_kind`: `session_meta` with a subagent source → `kind == "subagent"`.
  - `test_codex_prompted` (per the ruling above): either it asserts True or False from the user-input record, or it asserts `prompted is None`.
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement `codex_sessions`.**
- [ ] **Step 4: Run** `tests/test_usage_sessions.py` and `tests/test_usage.py`. Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat(usage): one session record per Codex session"`

### Task 3: Windows, rows, metrics and arrows

**Files:**
- Modify: `cli/loadout/usage.py` (new functions; `collect` stays as it is)
- Test: `tests/test_usage_report.py`

**Interfaces:**
- Consumes: `Session`, `claude_sessions` and `codex_sessions` (Tasks 1 and 2).
- Produces:
  - `metrics(sessions: list[Session], min_calls: int) -> dict`. It returns the counted sessions' sums under today's keys: `sessions` (counted), `calls`, `symbol_searches`, `serena_denials` (counted sessions with ≥ 1 denial), and `families.<name>.calls/.sessions`. It adds new keys:
    - `tiny` (sessions left out);
    - `lookups: {"serena", "codebase-memory"}`;
    - `code_tool_share: float | None`, that is lookups ÷ (lookups + symbol_searches), or None when the denominator is 0;
    - `denials`, `followed`, and `follow_through: float | None`;
    - `per_session: {"symbol_searches": float, "calls": float}`;
    - `family_share: {name: float}`, that is family sessions ÷ counted sessions.
  - `change(before: dict, after: dict, min_sessions: int) -> dict[str, str]`. It maps each compared metric to `"↑"`, `"↓"`, `"="`, `"new"` or `"too few sessions"`. Shares use the 5-point rule: `code_tool_share`, `follow_through`, and `family_share` of serena, codebase-memory, context7 and microsoft-learn. Rates use the 20 % rule: `per_session.symbol_searches` and `per_session.calls`. "too few sessions" applies when either side has fewer than `min_sessions` counted sessions. A metric that is None on either side gives `"—"`.
  - `report(after_start: float, after_end: float, before_start: float | None, *, min_calls=5, follow_within=5, min_sessions=20, now: float | None = None) -> dict`. Its JSON shape:
    - top level: `{"days", "windows": {"after": {"start", "end", "days", "partial"}, "before": {...}?}, "thresholds": {...}, "claude"?: A, "codex"?: A, "hint_sessions"}`;
    - `A = {"main": M, "subagent": M, "subagent_prompted": M, "subagent_unprompted": M, "prompted_known": bool, "skipped_lines": n, "before"?: {same four rows}, "change"?: {row: {metric: arrow}}}`.

    Rows hold the after window. A window holds a session whose `start` lies in [start, end). `partial` is true when the after window ends at `now` before `start + days`. Agents that are off are missing, as today.

- [ ] **Step 1: Write the failing tests** in `tests/test_usage_report.py`. Build `Session` lists directly for the `metrics`/`change` tests, and synthetic transcripts in `fake_home` for `report`:
  - `test_tiny_sessions_are_left_out_and_counted`: sessions with 3 and 10 calls, `min_calls=5` → `sessions == 1`, `tiny == 1`.
  - `test_code_tool_share`: lookups 3+1, symbol_searches 4 → `code_tool_share == 0.5`.
  - `test_follow_through_share`: denials 4, followed 1 → 0.25.
  - `test_arrows_use_points_for_shares_and_percent_for_rates`: share 0.10 → 0.14 gives `"="`, 0.10 → 0.16 gives `"↑"`. A rate of 10 → 7.9 per session gives `"↓"`, 10 → 8.5 gives `"="`, 0 → 2 gives `"new"`.
  - `test_too_few_sessions_guard`: 19 counted sessions on one side → every metric of that row is `"too few sessions"`.
  - `test_sessions_belong_to_the_window_of_their_start`: one session starting before the before window, one in before, one in after → counted 0, 1 and 1.
  - `test_partial_after_window_is_labelled_and_normalised`: `report` with an after window of 2 days out of `--days 7` → `windows.after.partial is True` and `days == 2`. Rates are per session.
  - `test_empty_and_zero_rows_never_divide_by_zero`.
  - `test_prompted_split_rows`: two prompted and one unprompted subagent → the row sizes match. With Codex `prompted=None`, `prompted_known` is False and the split rows are empty.
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement `metrics`, `change` and `report`.**
- [ ] **Step 4: Run** `tests/test_usage_report.py`, `tests/test_usage_sessions.py` and `tests/test_usage.py`. Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat(usage): before and after windows with shares, follow-through and arrows"`

### Task 4: CLI flags, the table, `--sessions` and `--legacy`

**Files:**
- Modify: `cli/loadout/commands.py` (`_register_usage`)
- Modify: `cli/loadout/usage.py` (`render_report`, `render_sessions`, `parse_moment`)
- Test: `tests/test_usage_report.py`, plus `tests/test_usage.py` where its CLI tests assert today's default output

**Interfaces:**
- Consumes: `report`, `metrics` (Task 3), `claude_sessions`/`codex_sessions` (Tasks 1–2).
- Produces:
  - `parse_moment(text: str) -> float`: `YYYY-MM-DD` gives local midnight, and `YYYY-MM-DDTHH:MM` gives local time. Anything else raises `ValueError` with the message `"use YYYY-MM-DD or YYYY-MM-DDTHH:MM"`;
  - `render_report(rep: dict) -> str`;
  - `render_sessions(sessions: list[Session], windows: dict, min_calls: int) -> str`.
- **Flags:**
  - `--days N`: default 14;
  - `--around MOMENT`: before = [M − N days, M), after = [M, min(M + N days, now));
  - `--since MOMENT`: after only, [M, now);
  - `--min-calls 5`, `--follow-within 5`, `--min-sessions 20`;
  - `--sessions`: one line per session;
  - `--legacy`: today's `collect` and `render`, unchanged, with `--days` only. It refuses with `--around`, `--since` and `--sessions`;
  - `--json`.

  `--around` and `--since` are mutually exclusive. Without either, the after window is [now − N days, now), as today, with the new rules. Exit 1 with today's message when no agent has history.
- **The table:**
  - **Header:** one line per window: dates, days, and `(partial)` where it applies.
  - **Rows:** per agent with sessions, for the rows `main`, `subagent`, `subagent prompted` and `subagent not prompted`, the latter two only when `prompted_known`. Each row shows counted sessions (and tiny ones left out), the code-tool share with its counts, follow-through, the Serena, codebase-memory, Context7 and Microsoft Learn session shares, and symbol-like searches per session. With `--around`, each metric shows before → after and its arrow.
  - **Footer:** one or two plain lines: hint sessions (after window only), skipped lines when there are any, and "Codex subagents are not split: their prompt is not in the session file" when it applies.
  - **Width:** at most 100 columns.
- **`render_sessions`:** one line per session, with fields separated by two spaces: `id`, agent, kind, `counted|tiny`, `before|after|outside`, `lookups=S/G`, `symbol=N`, `share=P%|—`, `denials=D followed=F`, `prompted=yes|no|—`. Ids and numbers only.

- [ ] **Step 1: Write the failing tests**:
  - `test_parse_moment` (both forms, plus a bad form).
  - `test_cli_around_shows_both_windows_and_arrows` (synthetic sessions on both sides; the output holds both dates and `↑`).
  - `test_cli_since_shows_one_window`.
  - `test_cli_legacy_matches_collect` (`--legacy --json` equals `usage.collect(days)`).
  - `test_cli_sessions_lists_ids_and_numbers_only` (a transcript holding "SECRET-PROMPT" never appears in the output).
  - `test_json_keeps_todays_keys`.
  - `test_table_fits_100_columns`.
  - `test_around_and_since_are_exclusive`, and `test_legacy_refuses_window_flags`.

  Update `tests/test_usage.py`'s CLI tests only where they assert today's default text. Ruling for the builder: they move to `--legacy` where they test legacy counting. Note each moved test in the report.
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement it.**
- [ ] **Step 4: Run all `tests/test_usage*.py`, then the full suite.** Run `uv run --python 3.12 --with pytest pytest -q --deselect "tests/test_docs_links.py::test_links_resolve[docs/examples/Niklas_Serena_Config.md]"`. Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat(usage): --around, --since, --sessions and --legacy"`

### Task 5: Docs, the skill and the known-effect check

**Files:**
- Modify:
  - `docs/reference/cli.md` (section "loadout usage": the flags, the metrics with their definitions from the spec, the arrows, the guard, the JSON keys, and the `--legacy` note that ADR 0039's reference was measured that way);
  - `plugins/loadout/skills/usage/SKILL.md`. "Did X help?" runs `loadout usage --around <date or time> --days 7 --json`. Report the code-tool share and follow-through first, then the family shares and the prompted split. "too few sessions" reads as "not yet measurable". Compare with ADR 0039 only through `--legacy`;
  - `docs/reference/modules.md` (`usage_sessions.py`).
- **Real-machine step, inline:**
  - Run `loadout usage --around 2026-10-22T19:35 --days 2` and `--sessions` on this machine. Read only the counts and show them to the maintainer.
  - Expected: Claude Code subagents show a clear `↑` in code-tool share or Serena family share. If not, stop and investigate the measurement before merging.

- [ ] **Step 1: Update the three docs.**
- [ ] **Step 2: Run** `tests/test_docs_links.py` (with the usual deselect) and `tests/test_evals_static.py`. Expected: PASS.
- [ ] **Step 3: Commit.** `git commit -m "docs(usage): before/after, the new metrics and the skill"`
- [ ] **Step 4: Run the known-effect check** and show its table to the maintainer.
