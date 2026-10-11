# 0019. Upstream installers run without agent configuration

- Status: Accepted
- Date: 2026-10-11
- Source: [Repo polish B design, section 6](../superpowers/specs/2026-10-11-repo-polish-b-design.md#6-small-fixes)

## Context
Some upstream install scripts also configure coding agents. codebase-memory-mcp's `install.sh` and `install.ps1` register its MCP server and hooks in Claude Code unless they get `--skip-config`. The loadout plugin already declares that server (`plugins/loadout/.mcp.json`) and its hook, so a default install creates a second copy of each. Its `update` subcommand only prints the command to re-run the install script.

## Decision
loadout runs upstream installers with their "do not configure agents" flag (`--skip-config` for codebase-memory-mcp). The plugin owns MCP and hook configuration. An update re-runs the same install command.

## Alternatives considered
- Let the installer configure agents and remove the duplicate afterwards: adopt can detect exact duplicates (`cli/loadout/duplicates.py`), but every install would create work to undo.
- Keep `codebase-memory-mcp update`: it does not update anything.

## Consequences
- A new catalog binary whose installer configures agents needs the same flag; `tests/test_repo_static.py` checks it for codebase-memory-mcp.
- Users who install the tool by hand without the flag get duplicates, which `loadout adopt` reports.
