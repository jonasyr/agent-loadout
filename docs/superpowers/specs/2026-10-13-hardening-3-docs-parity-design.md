# Hardening 3: Claude Code and Codex as equal targets in the docs

Status: approved design, 2026-10-13. Third of four hardening PRs (1 security #29, 2 robustness #30, 3 docs parity, 4 own-tool scopes).

## Goal

A reader who uses only Codex finds their way through the README and `docs/` as easily as a Claude Code user, and no page states something that is false for Codex. Diagrams show both agents. This PR changes documentation, manifests' descriptions, rules wording, one CI validate step, tests that guard the docs, and adds one repo-local skill. It changes no CLI behaviour.

Success criteria:

1. Every shared page that describes a flow (setup, projects, personal layer, hooks, undo, uninstall, troubleshooting, security) covers both agents where they differ.
2. `docs/how-to/codex.md` holds only facts that are true of Codex alone; everything else links to the shared page that owns it.
3. No doc claim contradicts the code (verified by a stand-in review with code and docs side by side).
4. Every relative link and anchor in `README.md`, `AGENTS.md`, `CONTRIBUTING.md` and `docs/` resolves (new test).
5. Diagrams that show where loadout writes or what the daily sync does include Codex; light and dark SVGs re-rendered and checked in a browser.
6. A final `/loadout:docs-audit` pass is clean, or its findings are fixed before the PR.

## Constraints

- One home per fact (`docs/explanation/documentation-strategy.md`). A fact lives on one page; others link.
- The kit's writing guide applies (plain English, short sentences, no marketing).
- ADR bodies are not rewritten. A decision that changed gets a status note and a new ADR.
- Every Codex claim is checked against `cli/loadout/` (mainly `codex.py`, `codex_project.py`, `targets.py`, `maintenance.py`, `paths.py`, `backup.py`) before it is written.
- Tests never touch the real home; agents never run real `claude`/`codex`.

## Out of scope

- Moving loadout's state (`~/.claude/.loadout`) and backups (`~/.claude/backups`) out of `~/.claude` (`paths.py:38-43`). This PR documents where they are; moving them is an open question for hardening 4 (it needs a migration).
- A Codex demo recording (the demo sandbox has no `codex`). The tape text only becomes agent-neutral.
- A kit-wide diagram skill (it would need `loadout init` to scaffold `docs/diagrams/`; own ADR if ever).

## Design

### 1. Page structure

Shared pages describe both agents. Where behaviour differs, a page uses a two-column table (`Claude Code | Codex`) or short `In Claude Code` / `In Codex` subsections, whichever reads better for that page. Where behaviour is the same, the page says "your agent" and names no agent.

Pages and what changes:

| Page | Change |
|---|---|
| `explanation/architecture.md` | Three parts described for both agents; daily sync includes the Codex refresh (`maintenance.py`: `codex.apply_all(refresh=True)` after a pull); remove "Plugins are not part of this loop" for Codex; the trailing Codex section folds into the body. New short section "loadout's own files": state and backups live under `~/.claude` for every user, Codex-only included. |
| `explanation/security-and-trust.md` | What runs and what changes, per agent; Codex permissions (`serena-hooks auto-approve --client=codex`, `rtk hook codex`) and that hooks run only after approval in `/hooks`; project trust before `.codex/config.toml` is read; project files include `.codex/config.toml`, `.agents/skills` and the user-level `enabled = false` switch; MCP setup per agent. |
| `tutorials/getting-started.md` | Log in to the chosen agents; trust the project after `init` (Codex); approve hooks in `/hooks` (Codex); restart wording per agent; what happens by itself, per agent. |
| `reference/cli.md` | Exit code 130 (Ctrl+C); `init`/`profile` write per agent; `check` rows skipped for a turned-off agent; `apply-settings` marked Claude Code only; backup location stated once. |
| `reference/personal-layer.md` | "Where it goes" gains a Codex column (`me.md` → `~/.codex/AGENTS.md` block, `mcp.json` → `config.toml` tables, `skills/` → `~/.agents/skills`, `settings.json` → effort and notifications only); `hooks/` and `skills.json` marked Claude Code only. |
| `reference/profile-format.md` | What `install`, `mcp` and `skills` mean in Codex (project `enabled = true` plus user-level `false`; add-only `.codex/config.toml`, servers with `${VAR}` args skipped; links in `.agents/skills`); trust required. |
| `reference/hooks.md` | Per-hook table gains a Codex column; the `/hooks` approval gate stated here (owner of that fact). |
| `reference/included-tools.md` | `codex` binary row; Codex gets the typecheck hook where Claude Code gets LSP plugins. |
| `reference/preferences-format.md` | `ai_attribution` per agent (Codex: account setting). |
| `how-to/uninstall.md` | New Codex section: the `~/.codex/AGENTS.md` block, owned `config.toml` tables, `codex-config.json` record, `~/.agents/skills` links, `codex plugin remove` and marketplaces, repo `.codex/` and `.agents/skills`. |
| `how-to/undo-and-restore.md` | Restore also removes the Codex plugins and marketplaces it recorded; restoring the `AGENTS.md` block and `config.toml`. |
| `how-to/troubleshooting.md` | Codex rows: hooks not approved, project not trusted, Serena tools deferred, `AGENTS.override.md` shadowing the block, no Codex route for a plugin. |
| `how-to/your-own-tools.md` | Scan list per agent; Codex adopt items move here from `codex.md`. |
| `how-to/wsl.md`, `set-preferences.md`, `personal-repo.md` | Agent-neutral wording; `CODEX_HOME` where relevant; settings location per agent. |
| `explanation/the-toolset.md`, `documentation-strategy.md` | Name the Codex alternative where a Claude Code built-in is named; skills run in either agent. |
| `docs/README.md` | Map presents both agents equally; Codex page described as "Codex-only details". |
| `how-to/codex.md` | Shrinks to: turning Codex on, version floor, project trust, `/hooks` approval, deferred MCP tools, drift, attribution. Everything else becomes a link. |

Every Codex claim in a rewritten page is checked against the code before it is written, and the plan names the source line for each new claim.

### 2. Entry points, manifests, rules

- `README.md`: tagline and intro name both agents; badge for both; "What you get" written for both; the update model per agent (Claude Code updates the plugins from the marketplace with `autoUpdate`; for Codex, loadout refreshes them after each pull and on `update`); login for the chosen agents.
- `AGENTS.md`: line 3 describes a setup for Claude Code and Codex; hard conventions name `~/.codex` and mutating `codex` commands.
- `CONTRIBUTING.md`: bug reports ask for `codex --version` too; the test-isolation line names `~/.codex`; the demo note says the demo shows Claude Code.
- CI: the Codex manifest `plugins/loadout/.codex-plugin/plugin.json` gets a pytest check (valid JSON, required fields, referenced paths exist); it runs in the existing test jobs, no `codex` invocation.
- `.claude-plugin/marketplace.json` and both `plugin.json` descriptions: agent-neutral and symmetric.
- `demo/loadout.tape`: caption text agent-neutral; commands unchanged.
- `rules/tooling.md` and `rules/workflow.md`: where advice names a Claude Code-only tool (LSP plugins, `/code-review`), add the Codex alternative in the same row. `plugins/loadout/skills/configure/SKILL.md`: restart advice follows `targets.restart_hint()` (both agents).

### 3. Diagrams and the diagram skill

New repo-local skill `.agents/skills/diagrams/SKILL.md` (Codex reads `.agents/skills`), linked from `.claude/skills/diagrams` (Claude Code). About 80 lines:

- Points to `CONTRIBUTING.md#diagrams` and `docs/diagrams/README.md` instead of copying them.
- Class vocabulary from `palette.light.mmd` with when to use each class; `%% palette` as the last line; no inline colours or `style` lines.
- Mermaid pitfalls: quote labels with parentheses, `<br>` for line breaks.
- Workflow: edit `<name>.mmd` → `docs/diagrams/render.sh <name>` → check the SVG has no "Syntax error" text → `pytest tests/test_diagrams.py` → open both SVGs with playwright-cli on light and dark backgrounds at 320 and 1280 px and read them for clipped labels → embed with the `<picture>` snippet and real alt text → commit `.mmd` and both SVGs together.

Diagram changes, made with the skill:

| Diagram | Change |
|---|---|
| `architecture-overview.mmd` | A Codex subgraph parallel to the Claude Code one: `~/.codex/AGENTS.md` block, `config.toml`, `~/.agents/skills`, `codex plugin`. |
| `architecture-daily-sync.mmd` | After the pull, a Codex branch: refresh plugins, skills and config. |
| `settings-merge.mmd` | Unchanged; the embedding page captions it as Claude Code only. |
| `documentation-layers.mmd` | "Claude Code auto memory" becomes agent-neutral. |
| `toolset-workflow.mmd` | Unchanged. |

A new diagram is added only if a page stays unclear without it (default: none).

### 4. ADRs

- `0022`: status note: project profiles and adopt for Codex shipped (#26).
- New `0024-codex-parity-update-model.md`: for Codex, loadout itself installs and refreshes plugins (after each pull and on `update`); secrets reach Codex through `env_vars`, not `${VAR}`; Codex gets type errors from the typecheck hook, not LSP plugins; bootstrap installs only the chosen agents.
- `0002`, `0006`, `0008`, `0015`, `0020`: one status line each, "For Codex, see ADR 0024." Bodies unchanged.
- `docs/adr/README.md` and the ADR range in `AGENTS.md` (0001-0024) updated.

### 5. Tests and checks

- New `tests/test_docs_links.py`: every relative Markdown link in `README.md`, `AGENTS.md`, `CONTRIBUTING.md` and `docs/**/*.md` (excluding `docs/superpowers/`) points to an existing file, and every `#anchor` matches a heading in the target (GitHub slug rules). Written first; it may fail on today's tree, and those failures are fixed in this PR.
- New test: `plugins/loadout/.codex-plugin/plugin.json` parses, has `name` and `description`, and its `skills`, `mcpServers` and `hooks` paths exist relative to the plugin folder.
- New test: `.claude/skills/diagrams` resolves to `.agents/skills/diagrams/SKILL.md`, which has valid frontmatter (`name`, `description`).
- Existing `tests/test_diagrams.py` and `test_diagrams_render.py` stay green after re-rendering.
- Stand-in review (`.claude/agents/codex-reviewer.md`) with an extra instruction: find doc claims the code contradicts.
- Final task: `/loadout:docs-audit` over the whole tree; findings fixed before the PR.

## Process

Spec → plan → execution advisor → execute → final whole-branch review → stand-in review loop → `/loadout:docs-audit` → PR → merge with the user's OK.
