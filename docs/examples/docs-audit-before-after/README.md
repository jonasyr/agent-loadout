# Example: a docs audit, before and after

> **Simulated example based on the kit's eval fixture.** `before/` is the exact documentation of the `tasklog` repo that the `/loadout:docs-audit` eval builds ([`scaffold.sh`](../../../plugins/loadout/evals/docs-audit/scaffold.sh), source code in [`fixtures/tasklog`](../../../plugins/loadout/evals/fixtures/tasklog)). The eval checks that the audit flags eight planted errors and asks about one ambiguous item. `after/` is a hand-written illustration of what the rewrite phase produces once that question is answered; it is not a recorded model output. The user's answer below is also simulated.

Back to [Documentation strategy](../../documentation-strategy.md).

## The repo

`tasklog` is a small Python CLI (`add`, `list`, `archive`, `export`) on SQLite. Its docs look reasonable at first glance: a README, an AGENTS.md, three pages in `docs/` and two Serena memories. Eight claims in them are false.

## Claims checked against the code

| # | Where | Claim | Classification | Evidence | Fix in `after/` |
|---|---|---|---|---|---|
| P1 | `README.md` | `tasklog export --format xml` | wrong | `cli.py`: `choices=["json", "csv"]` | Examples use the default (JSON) and `--format csv` |
| P2 | `README.md` | Link to `docs/usage.md` | wrong (broken link) | File does not exist; the CLI reference is `docs/reference/cli.md` | Link to the reference and the docs index |
| P3 | `README.md` | Roadmap: `[ ] JSON export` | stale | `cli.py`: `default="json"`; JSON export exists and is the default | Item removed |
| P4 | `docs/reference/cli.md` | Export default is `csv` | wrong | `cli.py`: `default="json"` | Default: `json` |
| P5 | `docs/configuration.md` | `TASKLOG_DIR` changes the data directory | wrong | `config.py` reads `TASKLOG_HOME`; `TASKLOG_DIR` does nothing | `TASKLOG_HOME` in the configuration reference and the how-to |
| P6 | `docs/architecture.md` | `store.py` defines `TaskRepository` | wrong | `store.py` defines `class Store`; no `TaskRepository` anywhere | `Store` |
| P7 | `AGENTS.md` | Test: `uv run pytest test/`; lint: `make lint` | wrong | Tests live in `tests/` (`testpaths = ["tests"]`); there is no Makefile and no linter | `uv run pytest`; lint row removed, "no linter configured" stated |
| P8a | `.serena/memories/project_overview.md` | Full CLI command table | duplicated | Copy of `docs/reference/cli.md` | Memory shrinks to summary plus links |
| P8b | same memory | Titles may be 200 characters | contradictory (with `docs/reference/cli.md`: 120) | `store.py`: `MAX_TITLE_LEN = 120` | Gone with the copied table; the reference keeps 120 |
| A1 | `docs/reference/cli.md`, memory | `list --all` also shows archived tasks | unclear | `cli.py` parses `--all` and ignores it: `# TODO: decide whether --all should also show archived tasks or be removed again` | Asked (see below), recorded as ADR 0001 |

The audit also finds what is **missing**: no doc says that empty titles are rejected (`store.py` raises `ValueError`). The reference now says so.

Correct claims stay as they are: the install commands, the default data directory `~/.local/share/tasklog`, `uv run tasklog --help`, and the testing gotcha in `suggested_commands.md`.

## The one question

The code cannot settle A1: it contradicts the docs, and the TODO says the intent is undecided. The skill never guesses intent, so it asks before rewriting anything:

> `list --all` is documented as "also shows archived tasks", but `cli.py` ignores the flag and a TODO says this is undecided. What should `--all` do?
> 1. Show archived tasks too (implement later; docs mark it as not implemented until then)
> 2. Remove `--all` from the CLI and the docs
> 3. Something else

Simulated answer: **1**. That answer is a decision, so it becomes [`after/docs/adr/0001-archive-is-a-soft-delete.md`](after/docs/adr/0001-archive-is-a-soft-delete.md), together with the soft-delete design that `docs/architecture.md` mentioned in passing.

## What moved where

| Before | After | Why |
|---|---|---|
| `docs/configuration.md` (env var plus a Dropbox example) | `docs/reference/configuration.md` and `docs/how-to/use-a-synced-folder.md` | Facts to look up and steps to follow are different [Diátaxis](../../documentation-strategy.md#diátaxis-four-kinds-of-docs) types |
| `docs/architecture.md` | `docs/explanation/architecture.md` | It explains structure; it is not a lookup table |
| "Archiving keeps the row and sets `archived = 1`" (one sentence in architecture.md) | `docs/adr/0001-archive-is-a-soft-delete.md` | A design decision with consequences gets an ADR |
| CLI table in `project_overview.md` (memory) | Links to `docs/reference/cli.md` | One home per fact; the copy had already drifted (200 vs 120) |
| `docs/README.md` (three rows) | Index grouped by type, plus `adr/` | Readers and agents find the right page from one place |
| `AGENTS.md` | Same shape, verified commands, links only | It is loaded into every agent session, so every wrong line costs on every task |

Unchanged: `CLAUDE.md` (already `@AGENTS.md`) and `suggested_commands.md` (genuine agent notes, all correct).

## How the real run works

On a real repo, `/loadout:docs-audit` keeps a resumable checklist in `.loadout/docs-audit/<date>.md` (gitignored while it runs), shows the target structure for approval before rewriting, validates every link and path afterwards, reports counts per classification, and commits per layer only after approval. The checklist is deleted at the end, so it does not appear in `after/`.
