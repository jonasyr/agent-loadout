# Docs baseline for the repo-agents change (Part 7, before PR 1)

B: done in repo-agents PR 2.
E: done in repo-agents PR 4.

Audit of `main` at da5db5c: every place that states the old model. Categories: A repo files follow the user's agents (ADR 0027); B profiles deep-merge, the profile wins; C repo writes have no backup, restore does not undo them; D `--dry-run` omits the settings diff; E restore needs a copied path / `--list`; F init/profile write without a preview or a yes; G loadout keeps no per-repo state. Owner PR: A, C, D, F, G → PR 1; B → PR 2; E → PR 4 (Part 6). Each PR updates the lines of its categories; PR 5 re-audits everything.

| File | Lines | Cat |
|---|---|---|
| README.md | 108-113, 126, 154 | F |
| README.md | 153 | C |
| AGENTS.md | 22 | B, C |
| AGENTS.md | 23 | C |
| AGENTS.md | 24, 58 (ADR range 0001-0030) | A |
| AGENTS.md | 40 | B |
| AGENTS.md | 44, 47 (map: new modules) | G, A |
| CONTRIBUTING.md | 74, 79 (demo tape: init output changes, re-render) | F |
| docs/README.md | 18 | C |
| docs/README.md | 42 | G |
| docs/tutorials/getting-started.md | 116 | A, D, F |
| docs/tutorials/getting-started.md | 123 | F |
| docs/how-to/setups.md | 19, 30 | A |
| docs/how-to/codex.md | 18, 41 | A |
| docs/how-to/write-a-profile.md | 21 | D |
| docs/how-to/write-a-profile.md | 28 | A, B, C |
| docs/how-to/undo-and-restore.md | 3, 7, 36, 51 | C |
| docs/how-to/undo-and-restore.md | 9-13, 21-28, 67, 69 | E |
| docs/how-to/troubleshooting.md | 41 | E |
| docs/how-to/troubleshooting.md | 55 | A |
| docs/how-to/your-own-tools.md | 16, 28, 39 | A |
| docs/how-to/your-own-tools.md | 27 | B |
| docs/how-to/your-own-tools.md | 29, 56 | C, F |
| docs/how-to/your-own-tools.md | 39 (`--to repo` previews, `--yes`) | F |
| docs/how-to/install-with-an-agent.md | 102 | F, A |
| docs/how-to/ask-about-loadout.md | 20 | C, F |
| docs/how-to/uninstall.md | 32, 68 | A, G |
| docs/reference/cli.md | 5 (`explain`, PR 2) | G |
| docs/reference/cli.md | 56, 296-310 | E |
| docs/reference/cli.md | 122, 128, 150, 173, 191, 195-196, 198-199, 201 | A |
| docs/reference/cli.md | 157 | B, C |
| docs/reference/cli.md | 160, 166, 171 | F |
| docs/reference/cli.md | 169 | D |
| docs/reference/cli.md | 177-187 (`profile --dry-run --yes`) | D, F |
| docs/reference/cli.md | 193-194 | B |
| docs/reference/cli.md | 306 | C |
| docs/reference/profile-format.md | 14, 46, 57, 61, 62, 70, 79, 81 | A |
| docs/reference/profile-format.md | 15-16, 43 | B |
| docs/reference/profile-format.md | 49 | C |
| docs/reference/profile-format.md | 51 | D |
| docs/reference/personal-layer.md | 31, 35 | A |
| docs/explanation/architecture.md | 3, 45 | A, G |
| docs/explanation/architecture.md | 46 | C |
| docs/explanation/security-and-trust.md | 33, 61 | F, C |
| docs/explanation/security-and-trust.md | 49 | A |
| docs/explanation/security-and-trust.md | 57 | B, C, F |
| docs/explanation/documentation-strategy.md | 187, 191 | F, A |
| docs/adr/README.md | 53 (0027 partly superseded; add 0030) | A |
| docs/adr/0027-repo-files-follow-the-agents.md | 3 (status note) | A |
| docs/adr/0007-tiered-scoping-with-profiles.md | 11 (status note, PR 2) | B |
| docs/adr/0012-*.md | 11, 20 (status note: repo writes previewed and backed up) | C, F |
| plugins/loadout/skills/configure/SKILL.md | 26, 33 | F, A |
| plugins/loadout/skills/configure/SKILL.md | 31 | E |
| plugins/loadout/skills/onboard/SKILL.md | 33 | F |
| .serena/memories/architecture.md | 2 | A |

Nothing in `templates/**` or `rules/**` states the old model. No page describes the per-run `# loadout` header in `.gitignore`.

## Full audit (PR 5)

Run on the finished branch (2026-10-17): an old-model grep pass, then about 1,000 claims checked against the code by area. No page still stated the old model; the fixes were gaps, wrong strings and duplicates.

| Area | Pages checked | Fixed |
|---|---|---|
| Entry | README.md, docs/README.md, docs/tutorials/getting-started.md, CONTRIBUTING.md | README steps count, repo-write list, `--yes`; undo entry; tutorial `--dry-run` sentence; "now" |
| How-to | setups, install-with-an-agent, wsl, codex, troubleshooting, undo-and-restore, write-a-profile, your-own-tools, ask-about-loadout, uninstall, personal-repo, set-preferences, run-evals, add-to-catalog | new walkthrough; `--vscode-wsl` stated once (wsl.md); bootstrap default without a terminal; two troubleshooting rows; restore for repo writes; undo claim; uninstall restore |
| Reference | cli, profile-format, hooks, personal-layer, preferences-format, included-tools, catalog-format, settings-merge | exit codes (state move, `explain`, `--show`), init question, `new skill` backup line, `--last` without a terminal; profile `why` field, problem line, empty overlay, code list; `restore --help` |
| Explanation and ADRs | architecture, security-and-trust, documentation-strategy, the-toolset, execution-advisor, docs/adr/README.md (0007, 0027 partial supersede), docs/diagrams/*.mmd | adopt's repo step; stale code citation; partial-supersede status rule |
| Agents | AGENTS.md map, skills configure, onboard, docs-sync, docs-audit, .serena/memories (5) | three modules and top-level parts in the map; `--take-profile`, `manage: false`, `explain`, `--last` in configure; onboard's files; memories trimmed to summaries plus links |
