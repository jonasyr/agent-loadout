# Architecture decision records

An ADR records one decision: the situation, what was decided, what else was considered and what follows from it. Each file is one decision.

An accepted ADR is not edited when the decision changes. A new ADR supersedes it, and the old one gets the status "Superseded by 00NN". Small corrections (a typo, a renamed file) are fine.

The records 0001 to 0013 were decided when the design was written and were written down afterwards, with the date of the original decision. Each links to its source in the design specs under [`docs/superpowers/`](../superpowers/).

Template:

```markdown
# 00NN. Title

- Status: Accepted
- Date: YYYY-MM-DD
- Source: link

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
| [0004](0004-rules-linked-as-directories.md) | Rules are linked as directories; the kit never edits `~/.claude/CLAUDE.md` | Accepted |
| [0005](0005-catalog-as-source-of-tool-knowledge.md) | `catalog.json` is the source of tool knowledge | Accepted |
| [0006](0006-secrets-in-secrets-env.md) | Secrets live in `secrets.env` and are referenced as `${VAR}` | Accepted |
| [0007](0007-tiered-scoping-with-profiles.md) | Tiered scoping: core tools global, domain tools per project | Accepted |
| [0008](0008-code-intelligence-routed-by-rule.md) | Code intelligence: LSP plugins, Serena and codebase-memory, routed by a rule | Accepted |
| [0009](0009-design-tooling-frontend-design-and-impeccable.md) | Design tooling: frontend-design and impeccable | Accepted |
| [0010](0010-docs-as-single-source-of-truth.md) | `docs/` is the single source of truth; AGENTS.md and memories link to it | Accepted |
| [0011](0011-tool-binaries-notice-and-deliberate-update.md) | Tool binaries: a weekly notice and a deliberate `loadout update` | Accepted |
| [0012](0012-destructive-actions-dry-run-confirm-backup.md) | Destructive actions: dry run, confirm, backup, restore | Accepted |
| [0013](0013-playwright-cli-instead-of-browser-mcp.md) | playwright-cli instead of a browser MCP server | Accepted |
| [0014](0014-execution-advisor-instead-of-default-sdd.md) | Execution advisor instead of subagent-driven development by default | Accepted |
| [0015](0015-claude-code-installs-synced-plugins.md) | Claude Code, not loadout, installs plugins synced through the personal layer | Accepted |
| [0016](0016-your-own-tools-ask-and-remember-leave.md) | Your own tools: nothing without an answer; Enter decides later, an explicit leave is remembered | Accepted |
| [0017](0017-hooks-merge-per-hook-with-tombstones.md) | Hooks merge per hook (event, matcher, command) with tombstones | Accepted |
| [0018](0018-secret-guard-fails-closed.md) | The secret guard fails closed | Accepted |
