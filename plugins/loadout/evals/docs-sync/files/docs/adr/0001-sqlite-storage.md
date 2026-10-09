# 0001. Store tasks in a local SQLite file

## Context

tasklog runs on a single machine and must work offline.

## Decision

Use the standard-library `sqlite3` module with one `tasks.db` file.

## Consequences

No server and no runtime dependencies; no sync between machines.

## Status

accepted
