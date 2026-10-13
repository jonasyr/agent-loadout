# 0022. Codex as a second target

- Status: Accepted. Project profiles and adopt for Codex shipped in #26; see also [ADR 0024](0024-codex-parity-update-model.md).
- Date: 2026-10-12
- Source: [Codex target design](../superpowers/specs/2026-10-12-codex-target-design.md)

## Context
The user works with Claude Code and the Codex CLI on the same machine and wants Codex to work exactly as well with the kit. Codex reads Claude Code marketplaces and Agent Skills, and its hooks use the same JSON shape, but it has no rules folder, no `@include`, no LSP support and no `${VAR}` in its config, and its own writes drop comments in `config.toml`.

## Decision
`cli/loadout/codex.py` maps the same kit and personal layer to Codex: the rules as a marked block in `~/.codex/AGENTS.md`; every plugin enabled for Claude Code through the same marketplace source; personal MCP servers and Serena's Codex context as `config.toml` tables that loadout owns by recording their exact text (not by marker comments); personal skills linked into `~/.agents/skills`. The plugin's `.codex-plugin/plugin.json` points Codex to its own hooks file with Codex arguments and a type-check hook that replaces Claude Code's LSP plugins. One source: changes made directly in one agent are reported as drift, not copied.

## Alternatives considered
- Each tool's own Codex installer: no single source, no daily sync, nothing to undo.
- Codex's built-in importer of Claude Code settings: a one-time copy without sync.
- Two-way automatic sync between the agents: conflicts, removals and secrets would cross between the agents unchecked.

## Consequences
- Codex runs plugin hooks only after the user approves them in `/hooks`; commit attribution stays an account setting.
- `config.toml` sections the user edits stop being managed by loadout.
- Project profiles and adopt for Codex follow in a second step.
