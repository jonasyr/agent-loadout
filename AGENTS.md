# agent-loadout

A shareable setup for Claude Code and Codex: a plugin marketplace (kit) plus the `loadout` CLI that links rules, merges settings, configures Codex and manages per-project profiles. Personal preferences live in a separate personal repo, never here.

## Commands

- Tests: `uv run --python 3.12 --with pytest pytest -q`
- Validate: `claude plugin validate .` and `claude plugin validate plugins/loadout`
- Skill evals: only via `plugins/loadout/evals/run.sh` (see `docs/how-to/run-evals.md`); never `claude plugin eval` directly

## Hard conventions

- Python 3.11+, standard library only in `cli/loadout/`.
- Tests use the `fake_home` and `fake_runner` fixtures. Never touch the real `~/.claude`, `~/.claude.json`, `~/.codex` or `~/.config/loadout`.
- Agents never run real installers or mutating `claude` or `codex` commands.
- Conventional Commits (`type(scope): subject`); no `Co-Authored-By` or other AI attribution.
- One home per fact: edit `docs/`, link from here (see `docs/explanation/documentation-strategy.md`).

## Code Review Rules

### User files
- loadout changes only what it recorded as its own in a user's files (`~/.claude/settings.json`, `~/.codex/config.toml`, `AGENTS.md`, shell startup files); text the user wrote stays byte for byte. Safe path: exact-text record, parse guard, atomic write. Treat a write that can change or lose user entries as P1.
- Every destructive change is undoable: a backup step or an undo command before it acts, so `loadout restore` reverts it. A removal or overwrite without one is P1.
- With an agent turned off (`targets.json`), nothing reads or changes that agent's files. P1.

### Secrets
- No plaintext secret is written to the personal layer, `mcp.json`, `config.toml`, the backup manifest or the output. Only variable names; values go to `secrets.env`. P1.

### External commands
- External commands run only through `runner.run` with argument lists, never a shell string built from user or file data. Restore replays only allowlisted undo commands. P1.

### Tests
- Tests use `fake_home` and `fake_runner`; a test that can reach the real `~/.claude`, `~/.claude.json`, `~/.codex` or `~/.config/loadout`, or run real `claude`/`codex`/installers, is P1.

## Where things are

`cli/loadout/` modules:

- `__main__.py` CLI entry; `commands.py` registers subcommands; `ui.py` prompt helpers; `out.py` calm status lines and `--verbose`
- `paths.py` locations from HOME; `runner.py` the only place external commands run; `jsonio.py` JSON and deep merge
- `bootstrap.py` first-time setup; `adopt.py` migrate an existing machine; `maintenance.py` session hook and `update`
- `link.py` rule links and PATH; `settings_merge.py` three-way settings merge; `personal_mcp.py` personal MCP servers
- `catalog.py`, `versions.py`, `pkgmgr.py` tool knowledge, versions, binary updates
- `profiles.py`, `project.py`, `detect.py`, `scaffold.py` profiles, `init`, detection, templates
- `preferences.py`, `configure.py` structured preferences and the wizard
- `own.py` your own tools; `inventory.py` machine inventory; `duplicates.py` exact plugin duplicates; `wsl.py` WSL detection and checks
- `targets.py` which agents are on (`targets.json` in the personal layer); `codex.py` Codex as a second target (rules block, owned config.toml entries, plugins, skills, drift); `codex_project.py` the Codex side of `init` and `profile`
- `secrets.py` secret detection and storage; `backup.py` undo backups; `check.py` health report; `advisor.py` advisor marker

Other kit parts:

- `plugins/loadout/`: the plugin (`.claude-plugin/` and `.codex-plugin/` manifests, `skills/`, `hooks/` with `hooks.json` for Claude Code and `codex.json` for Codex, `evals/`, `evals-browser/`, `.mcp.json`)
- `.claude/skills/diagrams`: repo-local skill for editing the docs diagrams (Codex finds it through a short pointer in `.agents/skills/diagrams`)
- `.github/`: CI workflows, issue forms and the PR template (see CONTRIBUTING.md)
- `demo/`: the README demo (VHS tape, sandbox, container render; see CONTRIBUTING.md)
- `catalog.json` tool knowledge; `profiles/` kit profiles; `rules/` rules linked into `~/.claude/rules/loadout`; `settings.base.json`, `preferences.json`

`docs/` (start at `docs/README.md`): `tutorials/`, `how-to/`, `reference/`, `explanation/` (toolset, architecture, security), `adr/` (decisions 0001-0025), `examples/`, `diagrams/` (Mermaid sources and their rendered SVGs; see CONTRIBUTING.md), and `docs/superpowers/` (where agents write specs and plans).

Agent notes: `.serena/memories/` (short summaries linking into `docs/`).
