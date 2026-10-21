# 0036. Codex tool approvals stay yours, and Codex asks once about Serena's

- Status: Accepted
- Date: 2026-10-21
- Source: [Design: live tour fixes](../superpowers/specs/2026-10-21-live-tour-fixes-design.md), fixes 4 and 5 (live tour findings 31 and 7)
- Amends: [ADR 0022](0022-codex-as-a-second-target.md) (how loadout owns `[mcp_servers]` tables in `~/.codex/config.toml`)

## Context

loadout writes its MCP server tables (`serena`, `context7`, the personal layer's servers) into `~/.codex/config.toml` and records their exact text. A table that no longer matches that text, or that has sub-tables, is the person's from then on: loadout says so once and never changes it again.

On the Linux live tour (2026-10-21) one click ended that ownership. Choosing "Always allow" in Codex writes a sub-table under the server's table:

```toml
[mcp_servers.serena]
command = "serena"
args = ["start-mcp-server", "--project-from-cwd", "--context=codex"]

[mcp_servers.serena.tools.serena_repl]
approval_mode = "approve"
```

The next run said `mcp serena: left as is in config.toml (it has sub-tables); loadout no longer manages it`, and loadout's later changes to Serena's command never reached Codex. The forces:

- The approval is the person's text and must stay byte for byte (AGENTS.md, "User files").
- Codex refuses to start when `[mcp_servers.x.tools.y]` remains without `[mcp_servers.x]`, so loadout cannot simply remove a table it no longer wants while approvals sit under it.
- Other sub-tables (`[mcp_servers.x.env]`) change what the server does; loadout cannot know whether its own text still fits next to them.
- Claude Code auto-approves Serena through loadout's hook; Codex asks before every `serena_repl` call (finding 7). `serena_repl` runs code in Serena's process, so approving it automatically is a real trade-off, not a default to impose.

## Decision

We will treat `[mcp_servers.<name>.tools.*]` sub-tables as the person's text inside a table loadout keeps managing, and ask once, when Codex is on, whether Codex should approve Serena's tools automatically.

**Tool approvals (fix 4).**

- A `tools.*` section (`codex.is_tool_section`) is never compared and never rewritten. It does not end loadout's ownership of the table above it. A comment and the blank lines directly above a `tools.*` header belong to that sub-table, not to the table before it.
- When loadout's text for a table it owns changes, loadout replaces the table **in place** (before this decision it removed the table and appended the new one at the end of the file). The `tools.*` sections and the comment above them keep their lines; blank lines between sections stay as loadout's writer already normalises them (one). The change is backed up as before.
- When loadout would remove a table it owns that still has `tools.*` sections, it keeps both and says once `mcp NAME: kept in config.toml: your tool approvals ([mcp_servers.NAME.tools.*]) need it`. The table is recorded as kept (`kept` in `codex-config.json`), so neither a later run nor `loadout check` repeats it. Once the approvals are gone, the next run removes the table as any other it no longer wants; once loadout wants it again, it is loadout's again quietly.
- The parse guard leaves the `tools` part of loadout's tables in its comparison, so a write that would lose an approval is refused.
- A table released earlier only because of `tools.*` sub-tables is managed again once its own text equals loadout's, without a note (as any released table put back to loadout's text). A released Serena table in that state is no longer taken for the person's own Serena.
- Every other sub-table (`env`, anything not `tools`) still releases the table, as before.

**Serena's approval in Codex (fix 5).**

- A new preference asks once when Codex is on (in `loadout bootstrap` and `loadout configure prefs`), with the trade-off stated (`serena_repl` runs code in Serena's process): "ask each time" (the default) or "approve automatically".
- "Approve automatically" writes `approval_mode = "approve"` in `[mcp_servers.serena.tools.serena_repl]` when loadout owns the `serena` table, and records that line. "Ask each time" writes nothing, and on a switch back removes only the line loadout wrote (and the header, if loadout added it and nothing else is in it); an `approval_mode` the person wrote stays.
- A Serena table of the person's own (named `serena` since Serena 2.1's `serena setup codex`) is never changed; the answer is then a note, said once, that points to "Always allow" in Codex.
- When loadout's `serena` table becomes the person's (they changed it) while the answer is "approve automatically", loadout's `approval_mode` line under it becomes theirs too and stays as it is. When loadout drops a `serena` table it owns, its own line goes first, so the table is not kept for loadout's own approval.
- A personal layer cloned onto a new machine, or Codex turned on later, is not asked: the default applies and `loadout configure prefs` changes it.
- The choice is stored in a new personal-layer file, `loadout.json` (data only loadout reads; a preference target for Codex-only choices), so it syncs with the personal layer.

## Alternatives considered

- Keep releasing a table for any sub-table: one click in Codex silently ends loadout's updates for that server.
- Rewrite the approvals together with loadout's table: their text is the person's; rewriting it breaks the byte-for-byte rule.
- Remove a table loadout no longer wants together with its approvals: removes the person's choices, and without them the table cannot go alone either.
- Approve Serena automatically for everyone, as Claude Code's hook does: `serena_repl` runs code, so the person decides; Codex has its own approval flow that loadout should not bypass by default.

## Consequences

- Good: "Always allow" in Codex no longer costs loadout's management of the server, and loadout's later changes still arrive.
- Good: a changed table keeps its place in the file, so the person's approvals stay next to it.
- Neutral: `loadout explain ~/.codex/config.toml` shows a kept table as `loadout's, kept for your tool approvals (tools.* sub-tables)`; the record gains a `kept` list.
- Neutral: a comment that sat directly above a `tools.*` header without a blank line before it gets one blank line before it when loadout rewrites the file (the writer's existing normalisation).
- Bad: a table loadout no longer wants stays in the file while approvals sit under it; the person removes the approvals (or both) to get rid of it.

## In the code

- `cli/loadout/codex.py`: `is_tool_section`, `_sections` (the comment above a `tools.*` header), `_ownership`, `_wanted_tables`, `apply_config` (in-place replacement, `kept`), `_without_owned` (the guard keeps `tools`), `is_release`, `refresh_record`, `explain_config`
- Fix 5: `preferences.json` (`codex_serena_approval`, `agents`, target `loadout`), `cli/loadout/preferences.py` (`available`, `_write_loadout`), `cli/loadout/paths.py` (`personal_loadout_json`), `cli/loadout/codex.py` (`desired_keys`, `_drop_approval`, `apply_config`, `refresh_record`; the record lists `added_headers` and `said`)
