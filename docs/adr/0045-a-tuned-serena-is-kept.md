# 0045. A Serena with settings of its own is kept on `--yes`

- Status: Accepted
- Date: 2026-11-02
- Source: [Design: use loadout's Serena (start clean)](../superpowers/specs/2026-10-31-start-clean-design.md)
- Amends:
  - [ADR 0016](0016-your-own-tools-ask-and-remember-leave.md): a tuned Serena is a tool of your own for the "nothing without an answer" rule, although the catalog knows Serena;
  - [ADR 0028](0028-serena-codex-hooks-in-hooks-json.md): the own-Serena handling it set up for Codex now also decides what `adopt --yes` does with Claude Code's Serena.

## Context

The catalog lists Serena as provided by loadout's plugin, so `adopt` classified every Claude Code MCP server that starts Serena as `migrate`, and `--yes` removed it. A Serena you tuned (another `--context`, `env`, extra arguments, a fork on a fixed path) went the same way, silently. Codebase-memory already had the opposite rule since [ADR 0041](0041-own-codebase-memory-by-command.md).

## Decision

- **Plain duplicate:** `command` is `serena` (or `serena.exe`, no path), the argument set equals loadout's for that agent (order does not matter), and no key beyond `command`, `args`, `type`, `enabled`, `alwaysLoad` and `startup_timeout_sec` is set (`env` counts only when it is not empty). `codex.serena_has_own_settings(cfg, agent)` is that test.
- **Plain** stays `migrate`, as today.
- **Anything else is own settings** (it fails closed) and becomes `keep`, with a reason that names `loadout adopt --apply --own NAME=remove`. `--yes` never removes it.
- Removing a tuned one happens only on that explicit command.

## Alternatives considered

- **Keep migrating every Serena:** silently drops a fork or a tuned context.
- **Ask for each tuned one:** `--yes` is for runs without a person; the explicit `--own NAME=remove` is the answer.

## Consequences

- A Serena that differs from loadout's in any way stays next to the plugin's until you remove it, so two Serena servers can run. `check` and `adopt` name it.
- The test is conservative: a harmless difference counts as own settings.

## In the code

- `cli/loadout/codex.py` (`serena_has_own_settings`), `cli/loadout/inventory.py` (`SERENA_OWN_CLAUDE`, `classify`)
