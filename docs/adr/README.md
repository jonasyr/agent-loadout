# Architecture decision records

An ADR records one decision: the situation, what was decided, what else was considered and what follows from it. Each file is one decision.

An accepted ADR is not edited when the decision changes. A new ADR supersedes it, and the old one gets the status "Superseded by 00NN"; when only part of it is superseded, the status names that part ("Accepted; decision line superseded by 00NN"). The new ADR names what it supersedes in a `Supersedes:` line. An ADR that adds to an earlier one without replacing any part of it names it in an `Amends:` line, and the earlier one gets "amended by 00NN" in its status. Small corrections (a typo, a renamed file or symbol) are fine.

The records 0001 to 0013 were decided when the design was written and were written down afterwards, with the date of the original decision. Each links to its source in the design specs under [`docs/superpowers/`](../superpowers/).

Template:

```markdown
# 00NN. Title

- Status: Accepted
- Date: YYYY-MM-DD
- Source: link
- Supersedes: (optional) the ADR and the part it replaces
- Amends: (optional) the ADR it adds to

## Context
## Decision
## Alternatives considered
## Consequences
## In the code
```

| # | Decision | Status |
|---|---|---|
| [0001](0001-kit-repo-plus-personal-repo.md) | Kit repo plus a personal repo per user | Accepted |
| [0002](0002-kit-is-a-plugin-marketplace.md) | The kit is a plugin marketplace | Accepted |
| [0003](0003-three-way-settings-merge.md) | settings.json is merged three-way; the kit manages only its keys | Accepted |
| [0004](0004-rules-linked-as-directories.md) | Rules are linked as directories; `~/.claude/CLAUDE.md` changes only when you ask adopt to migrate it | Accepted |
| [0005](0005-catalog-as-source-of-tool-knowledge.md) | `catalog.json` is the source of tool knowledge | Accepted |
| [0006](0006-secrets-in-secrets-env.md) | Secrets live in `secrets.env` and are referenced as `${VAR}` | Accepted |
| [0007](0007-tiered-scoping-with-profiles.md) | Tiered scoping: core tools global, domain tools per project | Accepted; merge rule superseded by 0031 |
| [0008](0008-code-intelligence-routed-by-rule.md) | Code intelligence: LSP plugins, Serena and codebase-memory, routed by a rule | Accepted |
| [0009](0009-design-tooling-frontend-design-and-impeccable.md) | Design tooling: frontend-design and impeccable | Accepted |
| [0010](0010-docs-as-single-source-of-truth.md) | `docs/` is the single source of truth; AGENTS.md and memories link to it | Accepted |
| [0011](0011-tool-binaries-notice-and-deliberate-update.md) | Tool binaries: a weekly notice and a deliberate `loadout update` | Accepted |
| [0012](0012-destructive-actions-dry-run-confirm-backup.md) | Destructive actions: dry run, confirm, backup, restore | Accepted |
| [0013](0013-playwright-cli-instead-of-browser-mcp.md) | playwright-cli instead of a browser MCP server | Accepted |
| [0014](0014-execution-advisor-instead-of-default-sdd.md) | Execution advisor instead of subagent-driven development by default | Accepted |
| [0015](0015-claude-code-installs-synced-plugins.md) | Claude Code, not loadout, installs plugins synced through the personal layer | Accepted; amended by 0035 |
| [0016](0016-your-own-tools-ask-and-remember-leave.md) | Your own tools: nothing without an answer; Enter decides later, an explicit leave is remembered | Accepted |
| [0017](0017-hooks-merge-per-hook-with-tombstones.md) | Hooks merge per hook (event, matcher, command) with tombstones | Accepted |
| [0018](0018-secret-guard-fails-closed.md) | The secret guard fails closed | Accepted |
| [0019](0019-upstream-installers-without-agent-configuration.md) | Upstream installers run without agent configuration | Accepted |
| [0020](0020-bootstrap-installs-the-toolchain-in-user-space.md) | Bootstrap installs the toolchain in user space | Accepted; Python minimum superseded by 0023 |
| [0021](0021-diagrams-as-code-rendered-to-svg.md) | Diagrams as code, rendered to committed SVGs | Accepted |
| [0022](0022-codex-as-a-second-target.md) | Codex as a second target | Accepted; amended by 0036 |
| [0023](0023-python-3-11-minimum.md) | Python 3.11 minimum | Accepted |
| [0024](0024-codex-parity-update-model.md) | Codex parity: loadout updates Codex plugins, forwards secrets by name and type-checks by hook | Accepted; amended by 0033 and 0035 |
| [0025](0025-state-in-xdg-state-home.md) | loadout's own files live in XDG state, not in `~/.claude` | Accepted |
| [0026](0026-tool-hints-never-block.md) | Tool hints add context, never block | Accepted |
| [0027](0027-repo-files-follow-the-agents.md) | Repo files follow the agents that are on | Accepted; decision line superseded by 0030 |
| [0028](0028-serena-codex-hooks-in-hooks-json.md) | Serena's Codex hooks as owned entries in hooks.json | Accepted |
| [0029](0029-codex-on-windows-and-wsl.md) | Codex on Windows and WSL: one loadout per side | Accepted; amended by 0034 |
| [0030](0030-repo-files-follow-the-repos-agents.md) | Repo files follow the repo's agents | Accepted |
| [0031](0031-repo-profile-entries-merge-three-way.md) | Profile entries in repo files merge three-way against a record | Accepted |
| [0032](0032-vscode-extensions-are-a-surface-of-an-agent.md) | VS Code extensions are a surface of an agent | Accepted; amended by 0034 |
| [0033](0033-codex-for-the-vscode-extension-without-its-cli.md) | Codex set up for VS Code's Codex extension without its CLI | Accepted |
| [0034](0034-vscode-extension-binaries-and-vscode-fixes.md) | The extensions' own binaries as runners, and VS Code fixes as asked-for plans | Accepted |
| [0035](0035-loadout-update-brings-a-machine-current.md) | `loadout update` brings a machine current | Accepted |
| [0036](0036-codex-tool-approvals-and-serena-approval.md) | Codex tool approvals stay yours, and Codex asks once about Serena's | Accepted |
| [0037](0037-marketplaces-only-when-a-plugin-uses-them.md) | Marketplaces only when a plugin uses them | Accepted |
