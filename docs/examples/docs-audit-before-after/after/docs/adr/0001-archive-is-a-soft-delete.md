# 0001. Archiving is a soft delete

## Status

Accepted

## Context

`tasklog archive <id>` removes a task from `list` and `export`. The storage layer keeps the row and sets `archived = 1` (`Store.archive`); `Store.list(include_archived=True)` can already return archived tasks. The CLI parses `list --all`, but ignores it, with a TODO saying it was undecided whether `--all` should show archived tasks or be removed. Docs and an agent memory already described `--all` as "also shows archived tasks".

## Decision

Archiving stays a soft delete: rows are never removed. `tasklog list --all` will show archived tasks next to open ones; it is not removed from the CLI.

## Consequences

- Archived tasks can be shown again without a migration; the database grows with every task ever added.
- Until the CLI passes `--all` through to `Store.list`, the reference marks the flag as "not implemented yet".
- A real delete command, if ever needed, requires a new ADR that supersedes this one.
