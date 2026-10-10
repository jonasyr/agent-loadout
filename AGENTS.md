# agent-loadout

A shareable Claude Code setup: a plugin marketplace (kit) plus the `loadout` CLI that links rules, merges settings and manages per-project profiles. Personal preferences live in a separate personal repo, never here.

## Commands

- Tests: `uv run --python 3.12 --with pytest pytest -q`
- Validate: `claude plugin validate .` and `claude plugin validate plugins/loadout`
- Skill evals: only via `plugins/loadout/evals/run.sh` (see `docs/how-to/run-evals.md`); never `claude plugin eval` directly

## Hard conventions

- Python 3.10+, standard library only in `cli/loadout/`.
- Tests use the `fake_home` and `fake_runner` fixtures. Never touch the real `~/.claude`, `~/.claude.json` or `~/.config/loadout`.
- Agents never run real installers or mutating `claude` commands.
- Conventional Commits (`type(scope): subject`); no `Co-Authored-By` or other AI attribution.
- One home per fact: edit `docs/`, link from here (see `docs/explanation/documentation-strategy.md`).

## Where things are

`cli/loadout/` modules:

- `__main__.py` CLI entry; `commands.py` registers subcommands; `ui.py` prompt helpers
- `paths.py` locations from HOME; `runner.py` the only place external commands run; `jsonio.py` JSON and deep merge
- `bootstrap.py` first-time setup; `adopt.py` migrate an existing machine; `maintenance.py` session hook and `update`
- `link.py` rule links and PATH; `settings_merge.py` three-way settings merge; `personal_mcp.py` personal MCP servers
- `catalog.py`, `versions.py`, `pkgmgr.py` tool knowledge, versions, binary updates
- `profiles.py`, `project.py`, `detect.py`, `scaffold.py` profiles, `init`, detection, templates
- `preferences.py`, `configure.py` structured preferences and the wizard
- `own.py` your own tools; `inventory.py` machine inventory; `duplicates.py` exact plugin duplicates
- `secrets.py` secret detection and storage; `backup.py` undo backups; `check.py` health report; `advisor.py` advisor marker

`docs/` (start at `docs/README.md`): `tutorials/`, `how-to/`, `reference/`, `explanation/` (architecture, security), `adr/` (decisions 0001-0018), `examples/`.

Agent notes: `.serena/memories/` (short summaries linking into `docs/`).
