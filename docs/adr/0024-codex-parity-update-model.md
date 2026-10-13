# 0024. Codex parity: loadout updates Codex plugins, forwards secrets by name and type-checks by hook

- Status: Accepted
- Date: 2026-10-13
- Source: [Hardening 3 design](../superpowers/specs/2026-10-13-hardening-3-docs-parity-design.md)

## Context
Codex became a second target in [ADR 0022](0022-codex-as-a-second-target.md), but several earlier decisions were written for Claude Code alone: [ADR 0002](0002-kit-is-a-plugin-marketplace.md) and [ADR 0015](0015-claude-code-installs-synced-plugins.md) rely on Claude Code to install and update plugins, [ADR 0006](0006-secrets-in-secrets-env.md) on `${VAR}` references in MCP configuration, [ADR 0008](0008-code-intelligence-routed-by-rule.md) on LSP plugins for type errors, and [ADR 0020](0020-bootstrap-installs-the-toolchain-in-user-space.md) on a Claude Code setup. Codex differs on each point.

## Decision
- **Plugins.** For Codex, loadout itself installs and refreshes plugins and their marketplaces, because Codex has no marketplace auto-update. It does so after a pull that brought commits (when Codex is on and usable) and on `loadout update`.
- **Secrets.** Secrets reach Codex as the names of environment variables (`env_vars` in `config.toml`), because Codex does not expand `${VAR}`. Values stay in `secrets.env`.
- **Type errors.** Codex gets type errors from the plugin's type-check hook after each edit, because it has no LSP plugins.
- **Bootstrap.** Bootstrap asks which agents to set up and installs and configures only the chosen ones.

## Alternatives considered
- Leave Codex plugins to Codex: they would go stale, since nothing refreshes them.
- Write secret values into `config.toml`: breaks the rule that no plaintext secret is written to config files.
- Skip type checks for Codex: Codex would lose the feedback Claude Code gets from LSP plugins.

## Consequences
- `loadout restore` removes the Codex plugins and marketplaces loadout installed.
- A plugin whose marketplace is not on GitHub has no Codex route; loadout says so.
- Type checks run once per edit, with a limit of 20 seconds per check.
