# agent-loadout

A shareable setup for Claude Code and Codex: a plugin marketplace (kit) plus the `loadout` CLI that links rules, merges settings, configures Codex and manages per-project profiles. Personal preferences live in a separate personal repo, never here.

## Commands

- Tests: `uv run --python 3.12 --with pytest pytest -q`
- Validate: `claude plugin validate .` and `claude plugin validate plugins/loadout`
- Skill evals: only via `plugins/loadout/evals/run.sh` (see `docs/how-to/run-evals.md`); never `claude plugin eval` directly
- CLI help from a checkout: `bin/loadout <sub> --help`

## Hard conventions

- Python 3.11+, standard library only in `cli/loadout/`.
- Tests use the `fake_home` and `fake_runner` fixtures. Never touch the real `~/.claude`, `~/.claude.json`, `~/.codex` or `~/.config/loadout`.
- Agents never run real installers or mutating `claude` or `codex` commands.
- Conventional Commits (`type(scope): subject`); no `Co-Authored-By` or other AI attribution.
- One home per fact: edit `docs/`, link from here (see `docs/explanation/documentation-strategy.md`).

## Code Review Rules

### User files
- loadout changes only what it recorded as its own in a user's files (`~/.claude/settings.json`, `~/.codex/config.toml`, `AGENTS.md`, shell startup files); text the user wrote stays byte for byte. Safe path: exact-text record, parse guard, atomic write. Treat a write that can change or lose user entries as P1.
- Every destructive change is undoable: a backup step or an undo command before it acts, so `loadout restore` reverts it. A removal or overwrite without one is P1. A profile re-run that changes an entry a person changed in a repo file, without their yes, is P1 (ADR 0031). Repo writes (`init`, `profile`, `configure new skill --to repo`) are a plan first and are backed up (ADR 0030); only a `run` step (a profile's `commands`, `git init`) is not undoable, and the plan says so.
- With an agent turned off (`targets.json`), nothing reads or changes that agent's files in the user's agent folders (`~/.claude`, `~/.codex`); repo files follow `.loadout.json` (ADR 0030). P1. loadout's own old state under `~/.claude` (`~/.claude/.loadout`, `~/.claude/backups/loadout-*`) is loadout's, not Claude Code's: the move out of it runs for every user (ADR 0025).

### Secrets
- No plaintext secret is written to the personal layer, `mcp.json`, `config.toml`, the backup manifest or the output. Only variable names; values go to `secrets.env`. P1.

### External commands
- External commands run only through `runner.run` with argument lists, never a shell string built from user or file data. Hook scripts in `plugins/loadout/hooks/` run from the installed plugin and cannot import `loadout`: they use `subprocess` with argument lists and timeouts, never `shell=True`. Restore replays only allowlisted undo commands. P1.

### Tests
- Tests use `fake_home` and `fake_runner`; a test that can reach the real `~/.claude`, `~/.claude.json`, `~/.codex` or `~/.config/loadout`, or run real `claude`/`codex`/installers, is P1.

## Where things are

Every module and kit part, grouped, is in [docs/reference/modules.md](docs/reference/modules.md). Start with these:

- `cli/loadout/__main__.py` (the parser and the state-move gate), `project.py` (`init` and `profile`) and `commands.py` (the other subcommands); `bin/loadout` runs them from a checkout
- `cli/loadout/runner.py`, the only place external commands run; `paths.py`, every location from `HOME`
- `cli/loadout/bootstrap.py` (setup), `check.py` (health report), `codex.py` (Codex as a second target), `vscode.py` (VS Code's extensions)
- `plugins/loadout/`: the plugin (`skills/`, `hooks/`, `evals/`, `evals-browser/`); at the repo root: `catalog.json`, `profiles/`, `rules/`, `templates/`, `tests/conftest.py` (the fixtures)
- loadout's state folders and the daily sync: [docs/reference/state-and-sync.md](docs/reference/state-and-sync.md)

`docs/` (start at `docs/README.md`): `tutorials/`, `how-to/`, `reference/`, `explanation/` (toolset, architecture, security, documentation strategy, execution advisor), `adr/` (decisions 0001-0043), `examples/`, `assets/` (wordmark, demo GIF), `diagrams/` (Mermaid sources and their rendered SVGs; see CONTRIBUTING.md), and `docs/superpowers/` (where agents write specs and plans).

Agent notes: `.serena/memories/` (short summaries linking into `docs/`).
