# agent-loadout: a shareable, self-updating Claude Code setup

Date: 2026-10-08 · Status: design v2, pending spec review · Claude Code v2.1.294

v2 changes from v1 (`claude-config`):

- The single personal repo is split into a shareable **kit** and a per-user **personal layer**.
- `settings.json` is merged, not symlinked.
- An `adopt` command migrates machines that already have a config.
- Onboard gains a new-project mode.
- distill is replaced by a full `docs-audit` skill.

## 1. Goal

One kit that anyone (the author, a colleague) can install on any machine, whatever is already there, to get a clean, current, well-used Claude Code setup. Personal preferences live in a separate layer.

Success criteria:

1. **Fresh machine:** `bootstrap` + `gh auth login` yields the full setup; `loadout check` passes.
2. **Machine with an existing config:** `loadout adopt` shows a dry-run plan covering every MCP server, plugin, marketplace, skill, hook and tool binary. Each item gets a reason and a choice. Nothing changes without confirmation; everything removed is backed up and restorable.
3. **Updates:** a commit to the kit or personal repo reaches every machine without manual steps. Plugins update via marketplace auto-update, rules via a daily pull.
4. **Projects:** `loadout init` + `/loadout:onboard` work on an empty directory, a new repo and an existing repo with docs. They never overwrite without asking.
5. **Docs:** `/loadout:docs-audit` brings a repo's docs and memories into the target structure, verified against the current code.
6. **Secrets:** no plaintext secret in either repo, `~/.claude.json` or `settings.json`.
7. **Overhead:** `/context` at session start shows less overhead than the 2026-10-08 baseline on the author's machine.
8. **CI:** CI validates the kit on Linux and Windows on every push.

## 2. Decisions

| # | Decision | Why |
|---|---|---|
| D1 | Kit repo `jonasyr/agent-loadout` (generic, recommended public) + personal repo per user (author: `jonasyr/loadout-personal`, private) | Kit improvements reach everyone via auto-update; nobody merges upstream; personal data stays private |
| D2 | Kit is also a plugin marketplace delivering `loadout` (hooks, MCP config, skills) | Plugins solve auto-update and cross-platform delivery |
| D3 | `settings.json` is merged: the kit manages only the keys it sets (three-way merge against the last applied snapshot), user keys untouched | Works on machines with existing settings; no symlink overwrites |
| D4 | Rules are linked as directories: `~/.claude/rules/loadout/` → kit, `~/.claude/rules/personal/` → personal layer. The kit never edits `~/.claude/CLAUDE.md` | Coexists with any existing global instructions |
| D5 | A `catalog.json` in the kit encodes tool knowledge: what is core, profile-only, superseded or deprecated, version sources, install/update commands | Single source of truth for adopt, check and update; it captures the research behind each decision |
| D6 | Secrets live in untracked `~/.config/loadout/secrets.env` (mode 600), loaded by the shell, referenced as `${VAR}` | No secrets in git or `~/.claude.json` |
| D7 | Tiered scoping: core plugins global, domain plugins per project via profiles | Each globally enabled skill's description costs context in every session |
| D8 | Code intelligence: official LSP plugins + Serena (memories kept, `remind` hook dropped) + codebase-memory-mcp, routed by `rules/loadout/tooling.md` | Each tool has one job |
| D9 | Design: official `frontend-design` + `impeccable`; taste-skill is superseded | Researched 2026-10-08; see catalog reasons |
| D10 | Knowledge model: `docs/` is the single source of truth; AGENTS.md and Serena memories link to it rather than copying it | Keep always-loaded context small, load details on demand; verbose generated context files hurt agents |
| D11 | Tool binaries get a weekly update notice and are updated deliberately with `loadout update`; never silently | Upstream binary releases have broken before |
| D12 | Every destructive action: dry run first, confirm, move to a timestamped backup (never delete); `loadout restore <backup>` undoes it | Safe on other people's machines |

## 3. Layout

### 3.1 Kit repo (`agent-loadout`)

```
agent-loadout/
├── .claude-plugin/marketplace.json    marketplace "agent-loadout"; lists loadout
├── plugins/loadout/
│   ├── .claude-plugin/plugin.json     no "version" → every commit is an update
│   ├── .mcp.json                      serena, codebase-memory-mcp
│   ├── hooks/hooks.json, hooks/*.sh   wrappers: exit 0 silently when binary missing
│   └── skills/{onboard,docs-sync,docs-audit}/SKILL.md
├── rules/                             → ~/.claude/rules/loadout/
│   └── tooling.md, docs-policy.md, memory-policy.md, workflow.md, rtk.md
├── settings.base.json                 kit-managed settings keys
├── catalog.json                       tool knowledge (section 5)
├── profiles/{thesis,sonar,db,web,android}.json
├── templates/project/                 AGENTS.md, CLAUDE.md, docs/README.md, docs/adr/README.md
├── templates/personal/                starter personal layer (section 3.2)
├── cli/loadout/                    Python ≥3.10, stdlib only
├── bin/loadout, bin/loadout.cmd
├── bootstrap.sh, bootstrap.ps1        thin shims → `loadout bootstrap`
├── secrets.env.example
├── tests/
├── .github/workflows/ci.yml
└── README.md                          inventory, scenarios, catalog reasoning
```

### 3.2 Personal layer

Located at `$LOADOUT_PERSONAL`, default `~/.config/loadout/personal`. Can be a git clone (the author's) or a plain folder created by the wizard.

```
personal/
├── rules/me.md          who I am, working style; other personal rules
├── settings.json        overlay: extra plugins/marketplaces, opt-outs ("x@y": false), preferences
└── profiles/*.json      optional personal profiles (override kit profiles with the same name)
```

The author's personal layer receives:

- `me.md`: CS student; Linux/Omarchy; Python, TS, Rust, Kotlin; ask before removing; research-backed recommendations with trade-offs; the skill-check rule from the current global CLAUDE.md.
- `settings.json`: `alwaysThinkingEnabled`, `effortLevel`, `tui`, `agentPushNotifEnabled`, the hyprctl permission, and the existing `autoMode` block verbatim.

## 4. Inventory (kit defaults)

### 4.1 Global (`settings.base.json`)

| Plugin | Marketplace | Job |
|---|---|---|
| loadout | agent-loadout | Hooks, serena + codebase-memory MCP config, onboard/docs skills |
| superpowers | claude-plugins-official | Process skills |
| frontend-design | claude-plugins-official | Aesthetic direction for UI |
| impeccable | impeccable (`pbakaus/impeccable`) | UI audit/critique/polish; per-edit hook off |
| commit-commands | claude-plugins-official | Commit/PR commands |
| security-guidance | claude-plugins-official | Edit-time security warnings; measure cost of its Stop-time review, disable that part if expensive |
| claude-md-management | claude-plugins-official | On-demand CLAUDE.md/AGENTS.md audit |
| pyright-lsp, typescript-lsp, rust-analyzer-lsp | claude-plugins-official | Diagnostics after edits, navigation |
| context7 | claude-plugins-official | Library docs |
| microsoft-docs | claude-plugins-official | Microsoft Learn docs |

All third-party marketplaces are declared with `"autoUpdate": true`.

Core binary (not a plugin): **Playwright CLI** (`@playwright/cli`, catalog `required: true`). Used skill-less in every repo via `rules/loadout/tooling.md` (agent reads `playwright-cli --help`), so it adds no idle context. Chosen over the Playwright MCP plugin because it keeps snapshots/screenshots on disk (about 4× fewer tokens); the MCP stays in the catalog as `alternative`.

### 4.2 Profiles

Profiles are merged into `<repo>/.claude/settings.json` and `<repo>/.mcp.json`. Each plugin is installed with `--scope project`.

| Profile | Enables |
|---|---|
| thesis | academic-research-skills (latest), deepeval, huggingface-skills |
| sonar | sonarqube |
| db | dbhub `@bytebase/dbhub@1.4.0`, `--dsn ${DATABASE_URL}` |
| web | `playwright-cli install --skills` in the project (richer Playwright guidance); chrome-devtools-mcp `@1.10.1` (listed in `disabledMcpjsonServers`, enable for perf/network debugging); onboard suggests `@playwright/test` E2E as a project dependency |
| android | kotlin-lsp |

### 4.3 Catalog verdicts for things found on the author's machine (adopt proposes these)

- **Remove:**
  - github-server MCP (superseded by `gh`)
  - MCP_DOCKER, omarchy-kb (user decision)
  - auto-memory (superseded by native memory + docs model)
  - testing-suite, documentation-generator (stale, superseded)
  - taste-skill skills (superseded by frontend-design + impeccable)
  - the `serena-hooks remind` hook
- **Migrate into loadout:**
  - user-scope serena and codebase-memory-mcp MCP entries
  - the cbm and serena hooks in `settings.json`
  - `~/.claude/.mcp.json`
- **Scope down to a profile:** sonarqube (and the sonar-secrets hooks) → sonar; academic-research-skills → thesis.
- **Not managed** (catalog status `system`): Omarchy skills, claude.ai connectors and Cowork-synced plugins. The README lists them; the user prunes them on claude.ai. The claude.ai Context7 connector duplicates the plugin and should be disconnected.

## 5. Catalog (`catalog.json`)

Each entry:

```json
{
  "id": "github-server",
  "kind": "mcp | plugin | marketplace | skill | hook | binary",
  "match": { "names": ["github-server"], "contains": ["server-github"] },
  "status": "core | profile | superseded | deprecated | recommended | system",
  "profile": "sonar",
  "by": "gh CLI",
  "reason": "Archived reference server; gh is better known to the model and cheaper in context.",
  "version": { "cmd": ["serena", "--version"], "github": "oraios/serena" },
  "install": { "posix": [["uv", "tool", "install", "-p", "3.12", "serena-agent"]], "windows": [["uv", "tool", "install", "-p", "3.12", "serena-agent"]] },
  "update":  { "posix": [["uv", "tool", "upgrade", "serena-agent"]], "windows": [["uv", "tool", "upgrade", "serena-agent"]] }
}
```

`match` is evaluated against names; `contains` is evaluated against the command line, URL, hook command or symlink target. Items not matched by any entry are `unknown`.

## 6. Machine setup

### 6.1 `bootstrap`

Runs `loadout bootstrap [--install] [--yes]`. Safe to re-run.

1. **Prerequisites:**
   - claude, git, python3, uv, node;
   - `gh auth status` (then `gh auth setup-git`; needed only for private repos).
   - Catalog binaries with `required: true` are checked. `--install` installs missing ones via their catalog commands; otherwise they are reported.
2. **Personal layer:**
   - If `$LOADOUT_PERSONAL` is missing, ask: clone an existing personal repo (URL), or create a starter one via a wizard (name, role, languages, working preferences). The wizard renders `templates/personal`.
3. **Link** the rules directories (D4) and `bin/loadout` into `~/.local/bin` (Windows: `.cmd` shim in `%USERPROFILE%\.local\bin`).
   - If symlinks are unavailable (Windows without Developer Mode), copy and record copy mode.
4. **Settings:** three-way merge of `settings.base.json` + personal `settings.json` into `~/.claude/settings.json` (section 6.3).
5. **Plugins:**
   - `claude plugin marketplace add` for each declared marketplace;
   - `claude plugin install --scope user` for each enabled plugin not yet installed.
6. **Adopt:** run `loadout adopt` (dry run, then interactive).
7. **Secrets:**
   - create `secrets.env` from the example if missing;
   - add a guarded load line to the shell profile (bashrc/zshrc/PowerShell profile);
   - report empty variables.
8. **Check:** run `loadout check`.

### 6.2 `adopt` (existing configs)

1. **Inventory:**
   - user-scope MCP servers (`~/.claude.json`), `~/.claude/.mcp.json`;
   - installed plugins and marketplaces;
   - `~/.claude/skills/*` (including symlink targets);
   - hooks in `~/.claude/settings.json`;
   - `~/.claude/CLAUDE.md` and its `@imports`;
   - catalog binaries with installed and latest versions.
2. **Secret scan:** flag values in `~/.claude.json` MCP `env`/`args`/`headers` that match token patterns: `ghp_`, `github_pat_`, `sk-`, `apk_`, long base64/hex strings, or keys named `*KEY*`/`*TOKEN*`/`*SECRET*`. The fix moves the value to `secrets.env` and replaces it with `${VAR}`.
3. **Classify** each item via the catalog into these actions:
   - *keep*;
   - *migrate* (duplicates something loadout provides → remove the user-level copy);
   - *scope down* (profile-only → disable globally, print `loadout init <profile>` hint);
   - *remove* (superseded/deprecated, with reason and replacement);
   - *update* (binary outdated: installed → latest);
   - *unknown* (kept untouched).
4. **Present** the grouped plan.
   - `--dry-run` (default when not interactive) stops here.
   - Interactive: confirm per group, with an option to pick individual items.
5. **Apply:**
   - Back up everything touched to `~/.claude/backups/loadout-<timestamp>/`, with a manifest recording the original location and the undo command.
   - Execute via the `claude` CLI where possible (`claude mcp remove`, `claude plugin uninstall`, `claude plugin marketplace remove`); move files/symlinks into the backup.
6. **Global CLAUDE.md:** if `~/.claude/CLAUDE.md` has content, offer to move it into `personal/rules/me.md` and leave CLAUDE.md empty except a comment. It is never changed without confirmation.

`loadout restore <backup-dir>` replays the manifest in reverse.

### 6.3 Settings merge

- **State:** `~/.claude/.loadout/managed-settings.json` is the snapshot last applied.
- **Inputs:**
  - `desired = deep_merge(settings.base.json, personal/settings.json)`
  - `current` = the existing `~/.claude/settings.json`
  - `previous` = the snapshot.
- **Result:** start from `deep_merge(current, desired)`. Then for every leaf in `previous` absent from `desired` whose value in `current` still equals `previous`, delete it. This removes kit-managed values the kit dropped but keeps values the user changed.
- **Dict and list rules:** dict leaves are compared by path. Lists are unioned, and an item the kit dropped is removed only if it was added by the kit.
- **After merge:** write the result and the new snapshot.
- **check:** reports drift only on desired paths.

### 6.4 Configure wizard (`loadout configure`, `/loadout:configure`)

One engine, two front-ends. Defaults stay as the kit ships them; the wizard only writes the personal layer.

- **Engine (CLI, non-interactive):**
  - `loadout configure set plugin <id> on|off` → `<personal>/settings.json` `enabledPlugins`. `off` opts out of a kit default.
  - `loadout configure set mcp <catalog-id> on|off` → `<personal>/mcp.json`. The servers listed there are applied as user-scope MCP servers via `claude mcp add-json -s user`. The managed names are kept in a snapshot, so an `off` removes only kit-applied servers.
  - `loadout configure set pref <key> <json-value>` → `<personal>/settings.json`.
  - `loadout configure show` prints the effective setup: kit default vs personal override.
  - After each change it runs the settings merge and the MCP apply. If the personal layer is a git repo, it offers to commit and push.
- **Interactive CLI wizard** (`loadout configure`; bootstrap runs it in first-run mode instead of the separate personal wizard):
  1. About you (`me.md`).
  2. Preferences (effort, thinking, UI).
  3. Global add-ons, grouped by category: kit defaults (opt out) + profile plugins (opt in globally) + catalog `offer` items, each with its reason and context-cost note.
  4. Done: summary and apply.
- **Skill `/loadout:configure`**: the same choices, conversationally inside Claude Code. Reads the catalog and the current personal layer, asks what you want ("I mostly do X", "I'd like browser automation everywhere"), recommends, then calls the non-interactive engine commands.
- **Catalog additions:**
  - an optional `category` (docs, browser, design, data, research, security, workflow, language);
  - an optional `offer`: `{ "plugin": "<id>" }` or `{ "mcp": { "<name>": <config> } }` with an optional `"needs": ["ENV_VAR"]`. Only entries with an offer appear as global add-ons.

### 6.5 Updates

| What | Mechanism |
|---|---|
| Plugins (incl. loadout) | Marketplace auto-update |
| Kit and personal repos | loadout SessionStart hook (sync, fast) prints a pending notice if any, spawns detached `loadout maintenance`. maintenance runs at most daily: `git pull --ff-only` on kit and personal repos when clean, then re-apply the settings merge and relink (copy mode: re-copy) |
| Binaries | maintenance, weekly: compare catalog versions; write a notice ("updates available → `loadout update`") shown at the next session start via `systemMessage` |
| `loadout update` | Runs catalog update commands for outdated binaries. Before and after, snapshots `~/.claude/settings.json`; if a tool's installer modified it (e.g. re-adding its own hooks), the change is shown and reverted to the merged result |

## 7. Project setup

### 7.1 `loadout init [profiles…]`

Run in the project directory; never overwrites.

- If the directory is not a git repo, offer `git init`.
- **Detect suggested profiles:**
  - `sonar-project.properties` → sonar;
  - `com.android` in `build.gradle*` → android;
  - package.json dependency react/next/vue/svelte/astro → web;
  - `DATABASE_URL` in `.env.example` → db;
  - `*.tex`/`*.bib` or `thesis`/`paper` in the directory name → thesis.
  - Dependency/build dirs are skipped.
- Confirm or edit profiles; merge them; run `claude plugin install <p> --scope project`.
- **Scaffold missing** `AGENTS.md`, `CLAUDE.md` (`@AGENTS.md`), `docs/README.md`, `docs/adr/README.md`.
  - If `CLAUDE.md` exists but `AGENTS.md` doesn't, skip both and note that onboard will offer the migration.
- **`.gitignore`:** add `.claude/settings.local.json` and `.serena/cache/`.
- **Print profile notes and next step:** `/loadout:onboard`.

### 7.2 `/loadout:onboard` (skill)

- **Mode detection:** *new project* if the repo has no source files (only README/LICENSE/.gitignore/templates); otherwise *existing*.
- **New project:**
  - Ask the definition questions itself, one at a time (purpose, users, stack, constraints). Do not hand off to `superpowers:brainstorming`; suggest it only for the first feature afterwards.
  - Then write AGENTS.md, `docs/README.md` and `docs/adr/0001-<stack-decision>.md`.
  - Suggest profiles (`loadout profile <name>`) and create the initial directory skeleton the stack calls for.
  - Commit after approval.
- **Existing project:**
  - Fill or repair AGENTS.md from the code: purpose, commands (verified by running `--help`/dry forms), conventions, map of docs and memories.
  - Offer to move CLAUDE.md content into AGENTS.md.
  - Pick up an existing `.mcp.json` and `.claude/settings.json` without changing them.
  - Run Serena onboarding under `memory-policy.md` if neither memories nor docs exist.
  - Index with codebase-memory-mcp.
  - If docs or memories already exist, recommend `/loadout:docs-audit`.
  - Show the diff; commit after approval.

## 8. Knowledge model and docs skills

| Layer | Role | Rule |
|---|---|---|
| `docs/` | Single source of truth for everything a human may need; ADRs in `docs/adr/` | Facts live here only |
| `AGENTS.md` (+ `CLAUDE.md` = `@AGENTS.md`) | Agent entry: purpose, commands, hard conventions, map | Short, curated, no copied content |
| Serena memories | Agent working notes + index into docs (1–3 line summary + link), gotchas, debugging lessons, task recipes, status | Never the only home of a human-relevant fact |
| Native auto-memory | Machine-local or temporary notes | No project facts |
| Personal layer | User preferences and working style | Changed by commit |

**`/loadout:docs-sync`** (cheap, end of each feature, after superpowers finishing-a-development-branch): find which layers the change affects; update only those; verify links.

**`/loadout:docs-audit`** (full, expensive, run on request):

1. **Inventory:** every doc layer above plus README; write `.loadout/docs-audit/<date>.md` as a resumable checklist (gitignored until done).
2. **Claim extraction:** commands, paths, symbols, parameters, architecture/behaviour statements, decisions, status claims.
3. **Verification against current code:**
   - parallel subagents, one per doc area (a small repo, under about 30 claims, is verified inline under the same rules);
   - symbols and structure via codebase-memory/Serena, paths via the filesystem, commands via read-only invocation (`--help`, dry run). Test or build commands run only after asking.
4. **Classification:** correct, stale, wrong, unclear, contradictory, duplicated, misplaced (wrong layer), missing (significant undocumented code: modules, entry points, config).
5. **Questions:**
   - Batch everything the code cannot settle (intent, open decisions, contradictions between docs, which of two behaviours is intended) and ask before editing.
   - Never guess intent.
6. **Rewrite** to the target model: facts into `docs/` (Diátaxis-style sections where it fits), memories to summary + link, AGENTS.md short and accurate, ADRs for decisions found.
7. **Validation:** every link and path resolves; every remaining claim was verified or confirmed by the user.
8. **Report + diff:** changes grouped by layer; commit per layer after approval; delete the checklist.

## 9. Global rules (`rules/` in kit)

- **`tooling.md`:**
  - structure → codebase-memory-mcp (index first if not indexed);
  - exact symbol lookup or editing → Serena;
  - diagnostics → LSP (automatic);
  - text/config → Grep/Read;
  - docs → Context7, then Microsoft Learn, then web;
  - UI verification / browser checks → `playwright-cli` (read `--help` first);
  - shell → rtk when installed (`rtk proxy` for raw output).
- **`docs-policy.md`, `memory-policy.md`:** section 8 table and rules.
- **`workflow.md`:**
  - superpowers process skills;
  - one review pass (`/code-review` or superpowers review, not both);
  - `/security-review` before merging security-relevant changes;
  - UI loop: frontend-design (direction) → build → playwright-cli (render at 320/768/1280 px, exercise flows, read console) → impeccable audit/polish; UI is not done until verified in a browser;
  - docs-sync at the end of features;
  - profiles for domain tools.
- **`rtk.md`:** rtk usage (applies only when rtk is installed).

The SubagentStart hook injects a one-line pointer to the tooling routing. The SessionStart "ALWAYS use codebase-memory FIRST" reminder is dropped, since the rules load every session.

## 10. loadout hooks

| Event | Command (via `run.sh`, which exits 0 if binary missing) |
|---|---|
| SessionStart | `serena-hooks activate --client=claude-code`; `loadout hook-session-start` |
| SessionEnd | `serena-hooks cleanup --client=claude-code` |
| PreToolUse `Bash` | `rtk hook claude` |
| PreToolUse `mcp__plugin_loadout_serena__.*` | `serena-hooks auto-approve --client=claude-code` (it matches on "serena" substring, so plugin-namespaced names work) |
| PreToolUse `Grep\|Glob` | `codebase-memory-mcp hook-augment` (soft: stderr dropped, always exit 0) |
| SubagentStart | tooling pointer JSON |

## 11. Error handling

- Hooks never fail a session; timeouts on all; background work detached with timestamps acting as locks.
- All destructive actions follow D12.
- Network failures in version checks or pulls are silent and retried next interval.
- `check` reports, never fixes; each failing check prints the command that fixes it.

## 12. Testing

- **Unit tests** (pytest via `uv run --with pytest`), all in temp dirs with fake HOME and a stubbed command runner:
  - deep merge; three-way settings merge (add, user-changed, kit-dropped);
  - profile apply idempotence; profile detection;
  - scaffold never overwrites; gitignore idempotence;
  - linking with symlink and copy fallback;
  - catalog matching and adopt classification (fixture modelled on the author's real 2026-10-08 config, secrets replaced by fakes);
  - secret detection; backup manifest + restore round trip;
  - session hook due-logic and notice;
  - update's settings guard.
- **Fresh-HOME bootstrap test** (no network, `--no-plugins`).
- **Static checks:** `claude plugin validate --strict` on the marketplace and loadout; all JSON parses; profiles and settings reference only declared marketplaces; catalog schema check.
- **Hook smoke tests:** each hook with its binary absent from PATH exits 0 with no output (POSIX).
- **Skill evals** (`claude plugin eval`, paid model calls, run on demand, not in CI): `plugins/loadout/evals/run.sh` only (about $8 per full run). It puts stubbed `loadout`/`playwright-cli`/browser binaries first on PATH and checksums the user's global state before and after. Every scaffold refuses to run outside such a run. Cases cover onboard (new/existing variants), docs-sync, docs-audit (planted errors) and configure. The browser routing case for `tooling.md` is opt-in (`--eval-dir evals-browser`). `tests/test_evals_static.py` checks the suite statically.
- **CI:** GitHub Actions on ubuntu-latest and windows-latest.
- **Acceptance on the author's machine:**
  - `/context` before and after;
  - adopt dry-run output reviewed;
  - first session shows no failing MCP servers from the kit;
  - init + onboard tried on an empty temp repo and on bachelor-rag-chunking (dry run).

## 13. Security

- **Action for the user:** the author's machine has a plaintext Devin API key and GitHub PAT in `~/.claude.json`. Rotate both; adopt removes the servers that use them.
- **Repo guards:** `secrets.env` is gitignored; CI fails if a committed file matches the secret patterns from section 6.2.
- **Pinning:** npx-launched MCP servers in profiles are version-pinned.
- **Installer scripts:** `curl | sh` installers run only with `--install` or after confirmation in `update`, and the exact command is shown first.

## 14. Roadmap: other agents (not in this version)

The kit is becoming an agent-neutral framework. The parts that are already agent-neutral:
- the catalog;
- rules (plain Markdown);
- AGENTS.md / `docs/`;
- Serena / codebase-memory (MCP);
- skills (agentskills.io format).

The Claude-specific parts are settings, plugins/marketplace, hooks, and MCP registration. A later version adds **targets**:
- `targets/claude` (today's code);
- `targets/codex` (`~/.codex/config.toml` MCP servers, `AGENTS.md` global rules, skills directory);
- possibly Gemini CLI / Cursor.

Each target maps the same personal layer and catalog to that agent's config format.

Decisions now that keep this cheap:
- The CLI keeps Claude-specific code in `settings_merge`, `bootstrap.setup_plugins`, `adopt._apply_*` and `link`, so it can later move behind a target interface.
- Rules stay free of Claude-only syntax where possible.
- Naming (decided 2026-10-08): project/repo/marketplace `agent-loadout`; CLI, plugin and Python package `loadout`.

## 15. Out of scope

- Managing claude.ai account connectors and Cowork plugins.
- Configs for non-Claude agents (AGENTS.md stays agent-neutral).
- Running docs-audit on all repos (run per repo on request).

## 16. Verify during implementation

- Does `~/.claude/rules/` load subdirectories (`rules/loadout/`, `rules/personal/`)? If not, link per-file as `kit-*.md` / `personal-*.md`.
- Is user-level `~/.claude/settings.local.json` honored? If not, the adopt plan migrates its contents into the personal overlay.
- Is `autoMode` honored in project settings? If yes, offer to move the stormcut-specific lines to stormcut.
- Exact tool-name prefix of plugin MCP tools (for the auto-approve matcher).
- The security-guidance Stop-hook cost.
- `codebase-memory-mcp update -y` behaviour and whether it rewrites settings.
- rtk on Windows.
- Whether `claude plugin validate` works unauthenticated in CI (fallback: JSON-schema validation).
