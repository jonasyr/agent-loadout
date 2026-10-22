#!/usr/bin/env bash
# SubagentStart: subagents get the kit's tool routing, triggers first (docs/reference/hooks.md).
# `subagent-context.sh codex`: Codex loads MCP tools on demand, so its card says to search for them first.
# Claude Code: the "loaded, call them directly" sentence only when Serena and codebase-memory are installed.
tail_text="Library docs, also while planning -> Context7; Microsoft APIs -> Microsoft Learn; text and config -> Grep/Read. Use the paths and symbols the parent gave you."
if [ "${1:-}" = "codex" ]; then
  text="Tool routing (loadout): code structure, callers, impact -> codebase-memory (search_graph, trace_path, get_code_snippet) before grep; a definition, references or an edit -> Serena (find_symbol, find_referencing_symbols, replace_symbol_body). Codex loads these tools on demand: search for them before you decide they are missing. ${tail_text}"
elif command -v serena >/dev/null 2>&1 && command -v codebase-memory-mcp >/dev/null 2>&1; then
  text="Tool routing (loadout): code structure, callers, impact -> codebase-memory (mcp__plugin_loadout_codebase-memory-mcp__search_graph, trace_path, get_code_snippet) before grep; a definition, references or an edit -> Serena (mcp__plugin_loadout_serena__find_symbol, find_referencing_symbols, replace_symbol_body); both are loaded and Serena's project is already active, so call them directly. A user's own servers may be named mcp__serena__* / mcp__codebase-memory-mcp__*. ${tail_text}"
else
  text="Tool routing (loadout): code structure or callers -> codebase-memory search_graph/trace_path before grep; exact symbol or edit -> Serena, when they are installed. ${tail_text}"
fi
printf '{"hookSpecificOutput":{"hookEventName":"SubagentStart","additionalContext":"%s"}}\n' "$text"
