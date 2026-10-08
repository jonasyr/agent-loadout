# claude-config: one global Claude Code setup for every machine

Date: 2026-10-08 · Status: approved design, pending spec review · Claude Code v2.1.294

## 1. Goal

Replace the hand-grown, per-machine `~/.claude` setups with one private git repo that:

- installs the same curated toolset on any machine (Linux first-class, Windows supported) with one bootstrap command;
- keeps every plugin, skill, hook and MCP server up to date without manual work;
- removes overlapping, stale or unused tools, so each remaining tool has one clear job;
- makes the tools actually get used, via concise always-on rules instead of competing hook nags;
- keeps secrets out of git and out of `~/.claude.json`.

Success criteria:

1. On a fresh machine, `bootstrap.sh` (or `bootstrap.ps1`) plus `gh auth login` yields the full global setup; `bootstrap --check` passes.
2. A commit pushed to the repo reaches every machine with no manual step (plugins via marketplace auto-update; home layer via daily pull hook).
3. `/context` at session start shows less skill/hook overhead than the 2026-10-08 baseline (measured before/after).
4. No plaintext secret in the repo, `~/.claude.json` or `settings.json`.
5. CI validates the repo on every push.

## 2. Decisions (with rationale)

| # | Decision | Why |
|---|---|---|
| D1 | Approach A: repo is a personal plugin marketplace plus a thin symlinked home layer | Plugins already solve auto-update and cross-platform delivery; the home layer covers what plugins can't (CLAUDE.md, rules, settings) |
| D2 | Private repo `jonasyr/claude-config`, cloned to `~/Documents/Code/claude-config` (override: `CLAUDE_CONFIG_REPO`) | One place; private because it describes the personal environment |
| D3 | Secrets in untracked `~/.config/claude/secrets.env` (mode 600), loaded by the shell, referenced as `${VAR}` | Plugin `.mcp.json` expands env vars; nothing secret is committed |
| D4 | Tiered scoping: core plugins global, domain plugins per project via profiles | Every enabled skill's description costs context in every session |
| D5 | Code intelligence: official LSP plugins + Serena (memories kept, `remind` hook removed) + codebase-memory-mcp | LSP: automatic diagnostics. Serena: symbol-level editing and committed memories. codebase-memory: call graph and architecture. Each has one job (see `rules/tooling.md`) |
| D6 | Design: official `frontend-design` + `impeccable`; drop all taste-skill skills | 6 of the 13 don't work in Claude Code, the core one costs about 22k tokens per use, there's no auto-update; Impeccable adds audit/polish as a real plugin |
| D7 | Docs model: `docs/` is the single source of truth; AGENTS.md and Serena memories link to it instead of copying it | Keep always-loaded context small; fetch details on demand; verbose generated context files hurt agents |
| D8 | Binaries are not auto-installed: weekly notice, deliberate `claude-config update` | Upstream binary releases have broken before (codebase-memory 0.10.7) |
| D9 | Removals confirmed by user: github-server, MCP_DOCKER, omarchy-kb MCPs; auto-memory, testing-suite, documentation-generator plugins; taste-skill skills | Stale, redundant, or insecure (plaintext keys) |

## 3. Repo layout

```
claude-config/
├── .claude-plugin/marketplace.json    marketplace "jonas"; lists jonas-core
├── plugins/jonas-core/
│   ├── .claude-plugin/plugin.json     no "version" field → every commit is an update
│   ├── .mcp.json                      serena, codebase-memory-mcp
│   ├── hooks/hooks.json
│   ├── hooks/*.sh                     wrappers: exit 0 silently if binary missing; timeouts set
│   └── skills/{docs-sync,onboard}/SKILL.md
├── home/                              linked into ~/.claude/
│   ├── CLAUDE.md
│   ├── settings.json
│   └── rules/{tooling,docs-policy,memory-policy,workflow,rtk}.md
├── profiles/{thesis,sonar,db,web}.json
├── bin/claude-config                  subcommands: init [profiles…], profile <name>, check, update
├── bootstrap.sh, bootstrap.ps1
├── secrets.env.example
├── tests/                             fresh-HOME bootstrap test, JSON/plugin validation, hook smoke tests
├── .github/workflows/ci.yml
└── README.md                          inventory: every tool, its job, when to use it, scope
```

## 4. Inventory

### 4.1 Global (`home/settings.json` → `enabledPlugins`)

| Plugin | Marketplace | Job |
|---|---|---|
| jonas-core | jonas | Own hooks, serena + codebase-memory MCP config, docs-sync skill |
| superpowers | claude-plugins-official | Process skills (brainstorm, plan, TDD, debugging, verification) |
| frontend-design | claude-plugins-official | Aesthetic direction for new UI |
| impeccable | pbakaus/impeccable | UI audit, critique, polish; deterministic checks. Per-edit hook off by default |
| commit-commands | claude-plugins-official | Commit and PR commands |
| security-guidance | claude-plugins-official | Security warnings while editing. Check the cost of its LLM review on Stop during implementation; disable that part if it costs too much |
| claude-md-management | claude-plugins-official | Audit and revise CLAUDE.md/AGENTS.md on demand (no hooks) |
| pyright-lsp, typescript-lsp, rust-analyzer-lsp | claude-plugins-official | Automatic diagnostics after edits, navigation |
| context7 | claude-plugins-official | Library docs. Optional `CONTEXT7_API_KEY` |
| microsoft-docs | claude-plugins-official | Microsoft Learn docs |

All marketplaces in `extraKnownMarketplaces` have `"autoUpdate": true`.

`kotlin-lsp` goes in a profile `android.json`, not global, since Android work is occasional.

### 4.2 Profiles (per project, merged into `<repo>/.claude/settings.json` by `claude-config profile <name>`)

| Profile | Enables | Used in |
|---|---|---|
| thesis | academic-research-skills (updated to latest), deepeval, huggingface-skills | bachelor-rag-chunking, PaperLab |
| sonar | sonarqube plugin; its secrets-scanning hooks come with the plugin | gitray, sonarqube-issues-export-to-excel, others with a Sonar project |
| db | dbhub via project `.mcp.json`, `--dsn ${DATABASE_URL}`, pinned version | any repo with a database |
| web | playwright (CLI skill preferred over MCP); chrome-devtools-mcp available but off | web apps |
| android | kotlin-lsp | Android repos |

Per-project autoMode environment text (currently stormcut-specific in global settings) moves into that project's `.claude/settings.json`.

### 4.3 Removed

- MCP servers (user scope): github-server, MCP_DOCKER, omarchy-kb, and user-scope serena, codebase-memory-mcp, sonarqube. serena and codebase-memory move into jonas-core; sonarqube into the sonar profile.
- `~/.claude/.mcp.json` (duplicate codebase-memory entry).
- Plugins: auto-memory, testing-suite, documentation-generator, global sonarqube.
- Marketplaces no longer needed: severity1-marketplace, claude-code-templates.
- Skills: the 13 taste-skill symlinks and `~/.agents/skills` copies.
- Hooks: `serena-hooks remind`; auto-memory hooks; global sonar-secrets hooks (move with the sonar profile).
- claude.ai connector Context7, replaced by the plugin. User disconnects it in claude.ai settings.

### 4.4 Not managed by the repo

- Omarchy-provided skills (`omarchy`, `diagnose-crash`): system symlinks, Omarchy machines only.
- Native auto-memory: machine-local by design.
- claude.ai connectors and Cowork-synced plugins (data, productivity, cowork-plugin-management): account-level. The README lists them, and the user prunes unused ones on claude.ai; their failing auth prompts are noise.

## 5. Knowledge model (`rules/docs-policy.md`, `rules/memory-policy.md`)

| Layer | Role | Rule |
|---|---|---|
| `docs/` | Single source of truth for anything a human may need: concepts, architecture, how-tos, reference, `docs/adr/` | Facts live here only |
| `AGENTS.md` (+ `CLAUDE.md` = `@AGENTS.md`) | Agent entry point: purpose, commands, hard conventions, map of docs and memories | Short, hand-curated, no copied content |
| Serena memories | Agent working notes and index into docs: 1–3 line summary + link per topic; gotchas; debugging lessons; "to do X touch these files"; current status | Never the only home of a fact a human needs |
| Native auto-memory | Machine-local or temporary notes | No project facts |
| `claude-config/home` | Personal preferences and working style | Changed by commit |

`docs-sync` skill:

- **sync mode:** at the end of a feature (after superpowers finishing-a-development-branch), find which layers the change affects and update only those.
- **distill mode:** run per repo on request. Moves memory-only content into `docs/`, reduces memories to summary + link, shows the diff, commits only after approval. Not run as part of this project.

## 6. Global instructions

- `home/CLAUDE.md`, ≤ 50 lines: user profile (CS student, Linux/Omarchy; Python, TS, Rust, Kotlin), working preferences (ask before removing, research-backed recommendations with trade-offs), `@rules/...` imports.
- `rules/tooling.md`: tool routing.
  - Structure questions → codebase-memory-mcp.
  - Exact symbol lookup or editing → Serena.
  - Diagnostics → LSP (automatic).
  - Text, config, non-code → Grep/Read.
  - Docs → Context7, then Microsoft Learn, then web search.
  - Shell → rtk (automatic; `rtk proxy` for raw output).
  - The codebase-memory reminder hooks are rewritten to point at this rule instead of "ALWAYS FIRST", so they no longer conflict with Serena's instructions.
- `rules/workflow.md`: superpowers process skills, then `/code-review` or superpowers review (not both); `/security-review` before merging security-relevant changes; Impeccable for UI; profile-gated domain tools.
- `rules/rtk.md`: current RTK.md content.
- Optional path-scoped rules (`paths:` frontmatter), e.g. `rules/python.md` for `**/*.py`. Added only when the user supplies conventions.

## 7. Bootstrap (`bootstrap.sh`, `bootstrap.ps1`)

Safe to re-run; each step reports what it did.

1. **Prerequisites.**
   - claude, git, node/npx, python3, uv.
   - `gh auth status`, then `gh auth setup-git`, so background updates of the private marketplace work.
   - Binaries: serena, codebase-memory-mcp, rtk, pyright, typescript-language-server, rust-analyzer.
   - `--install` installs missing items; without it, the script only reports.
2. **Backup** of `~/.claude/{CLAUDE.md,RTK.md,rules,settings.json,settings.local.json}` to `~/.claude/backups/<timestamp>/`.
3. **Link** `home/*` → `~/.claude/`. On Windows: symlink if Developer Mode is on, else copy and record copy mode in `~/.claude/.claude-config-mode`.
4. **Marketplaces and plugins:** `claude plugin marketplace add` for each, then `claude plugin install` for each globally enabled plugin, so they don't wait for a session start.
5. **Legacy cleanup** (section 4.3): list items, confirm, then `claude mcp remove -s user …`, `claude plugin uninstall …`, unlink skills.
6. **Secrets:** create `~/.config/claude/secrets.env` from the example if missing (chmod 600); add one guarded `source` line to `~/.bashrc` / `~/.zshrc` (PowerShell profile on Windows); report empty variables.
7. **Check:** run `claude-config check`.

`claude-config check` verifies links, valid JSON, enabled plugins present, binaries on PATH, secrets set, and the repo working tree clean (drift).

## 7b. Project setup (new and existing repos)

Two steps: mechanical work in a CLI, work that needs to understand the code in a skill.

1. **`claude-config init [profiles…]`** (terminal, in the repo root; safe to re-run, never overwrites):
   - Detects suggested profiles:
     - `sonar-project.properties` → sonar
     - Android Gradle plugin in `build.gradle*` → android
     - `package.json` with react, next, vue, svelte or astro → web
     - `DATABASE_URL` in `.env.example` → db
     - `*.tex`, `*.bib`, or `thesis`/`paper` in the repo name → thesis
   - Prints the suggestions; the user confirms or edits them.
   - Merges the chosen profiles into committed `.claude/settings.json` and runs `claude plugin install <p> --scope project` for each plugin they enable.
   - Scaffolds missing files only:
     - `AGENTS.md` skeleton (purpose, commands, conventions, map of docs and memories)
     - `CLAUDE.md` containing `@AGENTS.md`
     - `docs/README.md` (index)
     - `docs/adr/`
   - Adds `.gitignore` entries: `.claude/settings.local.json`, `.serena/cache/`. `.serena/memories/` and `.serena/project.yml` stay committed.
   - Existing files: prints a diff of what it would add; asks before changing.
2. **`/jonas-core:onboard`** (skill, first session in the repo):
   - Fills the AGENTS.md skeleton from the codebase, staying concise and hand-curated in style.
   - Runs Serena onboarding under `rules/memory-policy.md`: memories are summary + link, never copies of `docs/`.
   - Indexes the repo with codebase-memory-mcp.
   - Shows all changes; commits only after approval.

Existing repos use the same two steps. docs-sync distill mode remains a separate optional step.

## 8. Update flow

| What | Mechanism |
|---|---|
| Third-party and official plugins | Marketplace `autoUpdate: true`; background update after first message; active after `/reload-plugins` or next launch |
| jonas-core | Same; no `version` field, so each pushed commit is an update |
| Home layer | jonas-core SessionStart hook: at most once per 24h, in background, `git pull --ff-only` if working tree clean; in copy mode, re-copy afterwards |
| Binaries | Same hook, weekly: compare installed vs latest; print one line "updates available → `claude-config update`". `claude-config update` runs `uv tool upgrade serena-agent`, the codebase-memory installer, rtk update, npm/rustup updates |
| Config edits | Edit in repo (or via the `~/.claude` symlinks), commit, push |

## 9. Error handling

- Hooks:
  - never block;
  - exit 0 silently when a binary is missing;
  - have explicit timeouts;
  - run the pull/update checks in the background with a lock and a timestamp file.
- Bootstrap: backup before any change; confirmation before any removal; `set -euo pipefail` with a clear message per failed step.
- `claude-config check` reports drift; it never auto-fixes destructively.

## 10. Testing

- `tests/bootstrap_fresh_home.sh`: runs bootstrap with `HOME` set to a temp dir (no `--install`, network-light). Checks:
  - links resolve;
  - `settings.json` and `marketplace.json` parse;
  - check-mode output is as expected.
- `claude plugin validate plugins/jonas-core` (or the equivalent JSON schema check if unavailable in CI).
- Hook smoke tests: each hook runs with PATH stripped of its binary and exits 0 with no output.
- CI (GitHub Actions, ubuntu + windows): runs the above on push.
- Manual acceptance on the main machine: `/context` snapshot before and after; first session after bootstrap shows no failing MCP servers from this config.

## 11. Security notes

- Plaintext secrets found in `~/.claude.json` (Devin API key in MCP_DOCKER env; GitHub PAT in github-server args). Both servers are removed. **The user must rotate both credentials**, since they also appeared in a session transcript.
- `secrets.env` is never committed (`.gitignore` + CI check that fails if a file matching `*secrets.env` other than the example exists).
- Pinned versions for npx-launched MCP servers in profiles (no `@latest`).

## 12. Out of scope

- Distilling Serena memories into `docs/` across repos (docs-sync distill mode is provided; runs per repo on request).
- Managing claude.ai account connectors.
- Non-Claude agent configs (Codex etc.), beyond AGENTS.md being agent-neutral.
- Machine-wide packages unrelated to Claude Code.

## 13. Verify during implementation

- Whether `/config` and `claude plugin` writes go through the symlinked `settings.json` correctly.
- Whether a user-level `~/.claude/settings.local.json` is honored (currently holds a hyprctl permission). If not, move that permission into `home/settings.json`.
- Exact marketplace names and plugin ids for impeccable and the playwright CLI skill.
- security-guidance Stop-hook cost and configuration.
- rtk Windows availability.
- The 2026 AGENTS.md study citation, if it ends up in README.
