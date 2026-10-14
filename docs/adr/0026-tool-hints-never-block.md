# 0026. Tool hints add context, never block

- Status: Accepted
- Date: 2026-10-14
- Source: [Design: tool use](../superpowers/specs/2026-10-14-tool-use-design.md)

## Context

A count over the user's transcripts after setup showed Serena in 0.8% of Claude Code main sessions, codebase-memory in 1.2%, Context7 in 0.8%, Microsoft Learn never, and subagents almost never, while shell grep and rg ran thousands of times. Use happened about only when the user named the tool. Text in rules and cards alone did not change that. Blocking a search and redirecting costs about three calls for a one-call task and can loop.

## Decision

A hook adds one short fact next to a search or a docs web lookup that a better tool would answer: on the 3rd symbol search since Serena or the graph was last used, at most once per 10 counted calls, for the main session and (Claude Code) its subagents. It never blocks, never asks for permission, and is never switched off for the rest of a session, so an agent that drifts back gets it again. `loadout usage` measures the effect.

## Alternatives considered

- Block the search and redirect it to the graph or Serena: costs about three calls for a one-call task and can loop.
- Rules and subagent cards only: tried; use did not change without the user naming the tool.
- Switch the hint off for a session after it was shown once: an agent that drifts back would never see it again.

## Consequences

- A few hundred characters of context per hint; hints stay rare by design.
- The thresholds are constants in `plugins/loadout/hooks/tool_hint.py` and are tuned with `loadout usage`.
- Codex: the hint covers shell searches; whether PreToolUse runs in Codex subagents is not documented, so the measurement decides.

## In the code

- `plugins/loadout/hooks/tool_hint.py` (the hook, its constants and its state)
- `plugins/loadout/hooks/hooks.json` and `plugins/loadout/hooks/codex.json` (the matchers)
- `cli/loadout/usage.py` (`loadout usage`, the measurement)
