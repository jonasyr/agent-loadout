# 0008. Code intelligence: LSP plugins, Serena and codebase-memory, routed by a rule

- Status: Accepted
- Date: 2026-10-08
- Source: [Design spec, decision D8](../superpowers/specs/2026-10-08-agent-loadout-design.md#2-decisions)

## Context
An agent needs three kinds of help with code: diagnostics (type errors), exact symbol work (definitions, references, rename) and structure (call chains, architecture, impact). No single tool is best at all three, and several tools with overlapping tool lists make the agent pick badly.

## Decision
Use the official LSP plugins for diagnostics, Serena for exact symbol work and its memories, and codebase-memory-mcp for structural questions. A rule file, `rules/tooling.md`, says which tool answers which question. Serena's `remind` hook is dropped.

## Alternatives considered
- Serena alone: its symbol tools are exact but it has no graph for call chains and impact.
- codebase-memory alone: it answers structure well but is not the tool for a rename or a body replacement.
- No routing rule: the agent falls back to Grep for everything.

## Consequences
- Each tool has one job. The routing table costs a few lines of context in every session.
- Three tools to install and keep current. The catalog tracks their versions.
- If a tool is missing, the hook wrappers exit silently and the agent falls back to Grep/Read.

## In the code
- `rules/tooling.md` (the routing table)
- `plugins/loadout/.mcp.json` (`serena`, `codebase-memory-mcp`)
- `plugins/loadout/hooks/hooks.json`, `plugins/loadout/hooks/run.sh` (wrapper that exits 0 when a binary is missing)
- `settings.base.json` (`pyright-lsp`, `typescript-lsp`, `rust-analyzer-lsp`)
