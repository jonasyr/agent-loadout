# Tool use that just works: design

Status: approved in chat 2026-10-14 (with the user's change to the hint timing). Backlog item "Tool use that just works" (top priority).

## Problem (measured)

A read-only spike counted tool calls in the user's transcripts since loadout was set up (2026-10-09; 256 Claude Code main sessions, 212 subagent sessions):

- Serena was used in 0.8% of main sessions, codebase-memory in 1.2%, Context7 in 0.8%, Microsoft Learn never. Subagents: almost never. Claude Code use happened about only when the user named the tool.
- Claude Code searched with shell `grep`/`rg` about 1,560 times in main sessions and 2,390 times in subagents; about 1,190 of those look like symbol searches the graph or Serena would answer better (loose estimate). No improvement after setup.
- Claude Code rarely uses its Grep tool here; it searches through Bash. So a hook that watches only Grep (codebase-memory's `hook-augment` today) almost never fires. A probe of `hook-augment` on an indexed symbol printed nothing even for Grep.

Research (sources in the plan's references): tools recommend fail-open, context-only hooks over blocking (blocking costs about 3 calls for a 1-call task); Claude Code PreToolUse hooks run inside subagents; both agents support SubagentStart context; trigger-first instructions help (Microsoft, Context7).

## Goal and non-goals

Agents and their subagents use Serena, codebase-memory, Context7 and Microsoft Learn when they fit, without being told, while hints stay rare, small and never block. Not: forcing tools, blocking Grep, a reminder on every prompt, replacing Claude Code's system prompt.

## 1. `loadout usage [--days N]` (read-only)

- Reads `~/.claude/projects/**/*.jsonl` (main and `subagents/` transcripts) and `$CODEX_HOME/sessions/**/*.jsonl` for the last N days (default 14), for the agents that are on.
- Prints, per agent and for main vs subagent sessions: sessions, tool calls, calls and share of sessions per family (Serena, codebase-memory, Context7, Microsoft Learn, Grep/Glob/Read, shell), symbol-like searches done with grep/rg, and how many loadout hints were shown (from the hint state, part 2).
- Counts only; never prints transcript content. Unreadable or malformed lines are skipped and counted.
- `--json` for scripts. Exit 0; exit 1 only if no transcript folder exists for any agent that is on.

## 2. Search hint hook (`plugins/loadout/hooks/tool_hint.py`, stdlib only)

Events and matchers:

- Claude Code: PreToolUse `Grep|Glob|Bash`; PostToolUse on Serena and codebase-memory tools (`mcp__plugin_loadout_serena__.*|mcp__plugin_loadout_codebase-memory-mcp__.*`) to reset the counter.
- Codex: PreToolUse `Bash` (shell); PostToolUse `mcp__serena__.*|mcp__codebase-memory-mcp__.*` (names checked against Codex's MCP naming).

A search counts when it looks for a symbol in a code repo:

- Grep: `pattern` is an identifier (`^[A-Za-z_][A-Za-z0-9_]{2,}$`), or `def|class|function|fn|func|interface|struct|type NAME`, or `NAME\(`.
- Shell: the command's first word (after `rtk`) is `rg`, `grep`, `egrep` or `git grep`, and its pattern argument matches the same rule. `find` counts only with `-name` set to a code file glob.
- Not counted: searches whose path arguments are only logs, docs, configs or data (`*.log`, `*.md`, `*.json`, `*.toml`, `*.yaml`, `*.txt`, `*.csv`), and repos without code files.

Timing (the user's rule):

- A per-session counter counts symbol searches since Serena or the graph was last used.
- The hint fires on the 3rd such search; the counter then goes to 0. Using Serena or the graph also sets it to 0. It never switches off for the session.
- Spacing: at most one hint per 10 tool calls of that session (counted by the hook on every matched event).
- Constants `SEARCHES = 3`, `SPACING = 10` at the top of the file.

Output: `hookSpecificOutput.additionalContext` (never `permissionDecision`), at most 300 characters, phrased as a fact, e.g. "`record_project` looks like a symbol. codebase-memory `search_graph` and `trace_path` give its definition and callers; Serena `find_symbol` and `find_referencing_symbols` give the exact place to edit." Without a symbol name it names the tools only.

State: one small JSON file per session in `<state_dir>/tool-hint/<session_id>.json` (counter, last hint, calls); files older than 7 days are removed by the hook. Missing session id: no state, no hint. Any error: exit 0, no output. Subagents share the parent's session id in Claude Code; the counter is per session id either way.

Serena's own `serena-hooks remind` is not added (two hints for one search). codebase-memory's `hook-augment` stays; why it printed nothing is checked during the build (a note in docs/reference/hooks.md either way).

## 3. Docs tools and the cards

- Docs hint: the same hook on Claude Code `WebSearch|WebFetch` (Codex: its web search tool name, if exposed to hooks) adds "Library or API docs: Context7 first (`resolve-library-id`, `query-docs`); Microsoft Learn for .NET, Azure and Windows" when the query or URL names a library, package, API or framework docs host (a short keyword and host list). Same spacing rule, own counter of 1 (at most once per 10 calls).
- SubagentStart card (`subagent-context.sh`, both agents): trigger first, under 400 characters: "Code structure or callers: codebase-memory `search_graph`/`trace_path` before grep. Exact symbol or edit: Serena. Library docs, also while planning: Context7; Microsoft APIs: Microsoft Learn. Use the paths and symbols the parent gave you."
- `rules/tooling.md`: each row leads with its trigger ("When you need X: Y"), same facts.
- Codex: fix the Serena auto-approve matcher to the name Codex actually uses; add the hint hook entries to `codex.json`.

## 4. Measuring success

- Baseline: `loadout usage --days 14` before the switch, saved in the PR description (counts only).
- After about two weeks of normal work: run it again. Success: clearly more sessions with unprompted Serena or graph use (main and subagents), hints at most a few per session on average.
- Every hook keeps a 5 s timeout, is `--soft` (never breaks a tool call) and removing one is one line in the hook config.

## Testing

- `loadout usage`: fake transcripts for both agents in `fake_home` (main, subagent, malformed lines, outside the window), only counts in the output, `--json` shape.
- Hint hook: payload fixtures for Claude Code and Codex (Grep, Bash with rg/grep/git grep behind rtk, find, MCP PostToolUse); the 3-search rule, reset on MCP use, reset after a hint, spacing of 10, no permanent silence (hint again after drifting), non-code paths ignored, no session id, broken state file, 300-character cap, never a permission decision.
- Docs hint keyword/host rule and spacing.
- Hook config files: matchers present for both agents (JSON parse tests, as today).

## Review focus

- A search inside a non-code repo or for a common word (`error`, `TODO`) must not trigger a hint.
- Concurrent tool calls of one session (parallel calls) racing on the state file: worst case one extra or missing hint, never a crash.
- Very long shell commands or binary input in the payload: bounded parsing, no hang.
- A subagent's searches counting into the parent's session counter (Claude Code shares the id): acceptable; the hint still reaches whoever searched.
- `loadout usage` on a very large history: streaming, bounded memory.
