# 0039. Serena's reminder, tools that load upfront, and a fresh code graph

- Status: Accepted; amended by [0040](0040-serena-remind-skips-harmless.md) (the guard skips harmless searches, in Claude Code and Codex)
- Date: 2026-10-22
- Source: [Design: Serena and codebase-memory get used, in sessions and subagents](../superpowers/specs/2026-10-22-serena-cbm-usage-design.md)
- Supersedes: in [ADR 0008](0008-code-intelligence-routed-by-rule.md), the sentence "Serena's `remind` hook is dropped"; [ADR 0026](0026-tool-hints-never-block.md) for code searches (its docs hint for web lookups stands).

## Context

The maintainer, verbatim: "it still doesn't reliably work at all that they are being used in the session consistently without the user constantly reminding it … doesn't really work at all in subagents". These are 14 days of Claude Code transcripts (2.1.305) on that machine, counted with `loadout usage`'s parser:

| | Sessions | Serena used in | codebase-memory used in | Symbol-like greps |
|---|---|---|---|---|
| Main sessions | 592 | 5 | 6 | 1375 |
| Subagents | 590 | 17 | 17 | 3146 |

The causes, from strongest to weakest:

1. **The tools load on demand.** Claude Code loads MCP tool definitions only when the agent needs them, so a subagent has to search for `find_symbol` before it can call it. Only 27 of 585 subagents ever did.
2. **Hints that never block were ignored.** loadout's search hint (ADR 0026) was shown 109 times. In only 3 of those cases did Serena, the graph or a tool search follow within the next six calls.
3. **Hook paths that never fire.** On Linux, macOS and WSL, Claude Code has no Grep or Glob tools; it searches through Bash instead. That left 12 Grep calls against 11 217 shell calls in subagents. A hook on `Grep|Glob` therefore almost never runs. codebase-memory's own `hook-augment` (0.12.1) misses its 2 s deadline on every call, so it prints nothing. It hashes its 330 MB binary on every call (upstream #2683; see also #2441, #2239, #1335).
4. **Use follows the prompt.** In 23 of the 34 subagents that used the tools, the parent's prompt named them.

Serena's own docs say the same for Claude Code. Dynamic tool loading makes agents skip Serena, and Serena "strongly recommends" its hooks, `remind` included.

## Decision

- **Serena's documented hooks, for Claude Code too.** The plugin runs `serena-hooks activate`, `cleanup`, `auto-approve` and `remind` with `--client=claude-code`, as Serena documents them. `remind` denies the 3rd grep, the 3rd code-file read or the 4th mixed call made without a Serena symbolic tool in between. It does so once, then stays silent for 2 minutes. Its matcher is the tools it counts or resets on (`Bash|Read|Grep|Glob` and Serena's tools), not every tool.
  - Each hook runs through `hooks/mcp_guard.py`, which stays silent in three cases:
    - Serena is not on `PATH`;
    - Claude Code has the server switched off for the folder (and the user has no own server of that name switched on);
    - the user's or the project's settings already run the same `serena-hooks` subcommand for that event.
  - Two `remind`s would share one counter and deny at half the threshold.
  - Codex keeps the six Serena hooks in `~/.codex/hooks.json` (ADR 0028).
- **The plugin's two servers load upfront** (`"alwaysLoad": true` in `plugins/loadout/.mcp.json`). This costs about 50 000 characters of tool definitions, roughly 12k to 13k tokens, in every session and subagent. There is no per-user switch, because the plugin's file is the same for everyone. Codex decides the same thing from the model's tool-search support, and its config has no per-server switch.
- **loadout's own search hint goes.** Serena's `remind` covers code searches in both agents. The Context7 and Microsoft Learn hint for library-docs web lookups stays (ADR 0026 for that part).
- **Subagents get exact tool names.** The subagent context names exact tool names and says that Serena's project is already active. A hook names the codebase-memory project of the folder, using a file check and no daemon. The rules tell the parent to name the tools when it delegates.
- **codebase-memory's `hook-augment` is not wired** while it misses its own deadline (see Context). loadout's project pointer replaces the context it would add at session and subagent start.
- **A fresh graph.**
  - A preference (`cbm_auto_index`, default on) turns on codebase-memory's own `auto_index`. The change can be undone, and a value the user set themselves stays.
  - `hooks/refresh.py` re-indexes, in the background, an indexed repo that codebase-memory's watcher does not watch. It does so at the end of a turn with code changes, after a git command that rewrites the tree, and after 20 changed code files.
  - Serena needs no refresh. It found an edit made outside it, a new file and a deleted file at once, in Python and TypeScript (Serena 2.1.0).

## Alternatives considered

- **Keep hints that never block** (ADR 0026): measured above; 3 of 109 were followed.
- **Wire codebase-memory's own hooks as its installer does:** each Bash call would wait up to 2 s for no output.
- **A system-prompt override** (`serena prompts print-cc-system-prompt-override`), which Serena also suggests: it replaces Claude Code's whole system prompt. It stays the next lever if the numbers do not move.
- **Load the tools on demand and teach ToolSearch:** this keeps an extra step that subagents skip.

## Consequences

- An agent that drifts into grep gets one denial with Serena's reason. The next call goes through.
- Serena's reminder adds about 0.5 s to each Bash, Read, Grep or Glob call (Python start plus `serena-hooks`).
- Every context carries Serena's and codebase-memory's tool definitions.
- `loadout usage` counts sessions with a Serena reminder; the effect is measured against the table above.
- When codebase-memory fixes its hook latency, its hooks can be wired again through the guard.

## In the code

- `plugins/loadout/hooks/hooks.json`, `plugins/loadout/hooks/mcp_guard.py`, `plugins/loadout/.mcp.json`
- `plugins/loadout/hooks/subagent-context.sh`, `plugins/loadout/hooks/cbm_project.py`, `rules/tooling.md`
- `plugins/loadout/hooks/refresh.py`, `cli/loadout/cbm.py` (`cbm_auto_index`), `cli/loadout/check.py`
- `cli/loadout/searches.py`, `cli/loadout/usage.py`, `plugins/loadout/hooks/tool_hint.py` (docs hint only)
