# Repo polish, sub-project A: docs and repo content

Status: approved design (2026-10-10). Part of the repo-polish work (handoff 2026-10-09 §4.2 + §4.4), split into:
**A** docs and repo content (this spec) → **B** small code items (Wiley catalog entry, execution-advisor follow-ups, `/reload-plugins` notice, WSL detection and a WSL 2 CI job) → **C** publication (terminal demo, GitHub description/topics/social preview, release `v0.1.0`; every outward step only after the user confirms).

## 1. Goal

A sceptical first visitor ("would I trust this with my `~/.claude`?") can tell within a minute what loadout is, why it is safe, and how to install it. Details live in `docs/`, and the repo follows its own documentation strategy: every fact has one home (`docs/`), the README and `AGENTS.md` link to it, and every claim matches the code.

Success criteria:
- README about 100 lines: value statement, badges, what you get, why you can trust it, quick start, link table into `docs/`. No copies of `docs/` content and no collapsible duplicates.
- `docs/` in Diátaxis form with an index; every current README topic has exactly one home there.
- About 18 ADRs, one decision each (§5).
- `AGENTS.md` (+ `CLAUDE.md` = `@AGENTS.md`), `CONTRIBUTING.md`, `SECURITY.md`, Serena memories.
- WSL 2 documented as the recommended Windows setup for loadout; native Windows still supported.
- An automated link check passes; the final sceptical-first-visitor review finds no inaccurate claim.
- No behaviour change: only docs, tests and file moves.

## 2. Structure

Plain Markdown in the repo, rendered by GitHub (Mermaid renders natively). No docs site build (can be added later without rewriting).

```
README.md                      hero, badges, what you get, why trust it, quick start, link table
AGENTS.md / CLAUDE.md          CLAUDE.md contains only @AGENTS.md
CONTRIBUTING.md                setup, tests, evals (only via run.sh), catalog changes, Conventional Commits, PR flow
SECURITY.md                    what runs automatically, what is touched, secrets, backups, how to report
docs/
├── README.md                  index: which page answers which question (Diátaxis)
├── tutorials/getting-started.md       Linux · macOS · Windows (WSL 2 recommended, native supported)
├── how-to/                    your-own-tools · add-to-catalog · write-a-profile · set-preferences
│                              · undo-and-restore · run-evals · wsl · troubleshooting · uninstall
├── reference/                 cli (commands, flags, exit codes) · catalog-format · profile-format
│                              · preferences-format · personal-layer (files) · hooks · settings-merge
├── explanation/               architecture (Mermaid: kit + personal layer, daily sync, settings merge)
│                              · documentation-strategy (from the docs branch) · security-and-trust
│                              · execution-advisor
├── adr/                       README index + 0001-… one per decision
├── examples/docs-audit-before-after/   from the docs branch; nested CLAUDE.md → CLAUDE.md.example
└── internal/                  superpowers specs + plans, with a README: working documents, not user docs
.serena/memories/              4–6 notes: summary + links into docs/
```

Content moves (README → docs):

| README section today | New home |
|---|---|
| Quick start | README (short) + `tutorials/getting-started.md` (full, per platform) |
| How it works | `explanation/architecture.md` (README keeps two sentences) |
| Common tasks | spread over `how-to/` pages; README link table |
| Command reference | `reference/cli.md` |
| What you get | README (5 bullets) + `reference/` details where needed |
| Your personal layer | `reference/personal-layer.md` + `how-to/set-preferences.md` |
| Your own tools | `how-to/your-own-tools.md` (choices, sync, secret guard, exit codes) + `reference/settings-merge.md` (hook merge rules) |
| Staying up to date | `explanation/architecture.md` (sync) + `reference/cli.md` (`loadout update`) |
| Security & trust | `explanation/security-and-trust.md` + `SECURITY.md` (policy, reporting) + README 3 bullets |
| Secrets | `explanation/security-and-trust.md` (model) + `how-to/` where a task needs it |
| Troubleshooting | `how-to/troubleshooting.md` |
| FAQ | answers moved into the matching pages (no FAQ page) |
| Uninstall | `how-to/uninstall.md` |
| Contributing / development | `CONTRIBUTING.md` |

## 3. Content rules

- Write every page against the code; every factual claim must be checkable (file and symbol). No marketing language; short, concrete sentences; the existing README tone.
- One home per fact; other pages link to it.
- Tutorials teach one path end to end; how-to pages solve one task; reference pages are complete and dry; explanation pages say why.
- Mermaid diagrams: architecture (kit repo, personal layer, `~/.claude`, the plugin), daily sync and settings merge (three-way, per-hook for hooks), documentation layers.

## 4. Docs branch

`docs/documentation-strategy` (3 commits beyond main): merge main into it first, then bring it into this branch.
- `docs/documentation-strategy.md` → `docs/explanation/documentation-strategy.md`.
- `docs/examples/docs-audit-before-after/` stays under `docs/examples/`; its nested `CLAUDE.md` files are renamed `CLAUDE.md.example`, with a note in the example's README: Claude Code loads nested `CLAUDE.md` files when it reads those folders, which would leak the example into kit sessions.
- Its README row is folded into the new README/docs.
- Its accuracy review happens in the final review (§8), not separately.

## 5. ADRs

Format (MADR-lite): title, status, date, context, decision, alternatives considered, consequences, links to code. One decision per ADR; historic decisions get status Accepted with the date they were made.

| # | Decision | Source |
|---|---|---|
| 0001 | Kit repo plus a personal repo per user | D1 |
| 0002 | The kit is a plugin marketplace | D2 |
| 0003 | settings.json is merged three-way; the kit manages only its keys | D3 |
| 0004 | Rules linked as directories; the kit never edits `~/.claude/CLAUDE.md` | D4 |
| 0005 | `catalog.json` as the source of tool knowledge | D5 |
| 0006 | Secrets in `secrets.env`, referenced as `${VAR}` | D6 |
| 0007 | Tiered scoping: core global, domain tools per project (profiles) | D7 |
| 0008 | Code intelligence: LSP plugins + Serena + codebase-memory, routed by rule | D8 |
| 0009 | Design tooling: frontend-design + impeccable | D9 |
| 0010 | `docs/` is the single source of truth; AGENTS.md and memories link | D10 |
| 0011 | Tool binaries: weekly notice, deliberate `loadout update` | D11 |
| 0012 | Destructive actions: dry run, confirm, backup, restore | D12 |
| 0013 | playwright-cli instead of a browser MCP server | spec §4 / catalog |
| 0014 | Execution advisor instead of subagent-driven development by default | execution-advisor spec / rules |
| 0015 | Claude Code, not loadout, installs plugins synced through the personal layer | adopt spec G1 |
| 0016 | Your own tools: nothing without an answer; Enter decides later, an explicit leave is remembered | adopt spec §2, rulings |
| 0017 | Hooks merge per hook (event + matcher + command) with tombstones | adopt rulings, fix passes 3–4 |
| 0018 | The secret guard fails closed | adopt rulings, fix passes A–4 |

The final list may merge or split an entry when the sources show it was one decision or two; each ADR links to its source.

## 6. AGENTS.md and memories

- `AGENTS.md`: purpose (two sentences); commands (tests, plugin validate, evals only via `plugins/loadout/evals/run.sh`); hard conventions (stdlib only, Python ≥ 3.10; tests use `fake_home`/`fake_runner` and never touch the real `~/.claude`; Conventional Commits, never an attribution trailer; no real installers or `claude` mutations from agents); a map of `docs/` and the memories. Short and hand-curated, no copied docs content.
- Serena memories (each a 1–3 line summary plus links): architecture overview; testing gotchas (fake fixtures, Windows-only skips, timing tests); evals (run.sh only, cost, graders with `flags: m`); own-tools rules (hook merge, secret guard) → links into docs; Windows/WSL notes.
- Re-index codebase-memory and refresh Serena's memories at the end of A (and again after B).

## 7. Automated checks (tests/test_repo_static.py)

- Every relative link in every tracked `*.md` (outside `docs/internal/`) resolves to an existing file (and anchor, where present).
- No `CLAUDE.md` outside the repo root (examples use `CLAUDE.md.example`).
- `CLAUDE.md` contains exactly `@AGENTS.md`.

## 8. Final review

One sceptical-first-visitor review (Opus): "would I trust this with my `~/.claude`?". It checks every claim in README, `docs/`, `AGENTS.md`, `CONTRIBUTING.md`, `SECURITY.md` and the strategy doc against the code (a docs-audit of the repo), all links, the Diátaxis split (no duplicated facts) and the professional look. One consolidated fix round follows, then a scoped re-review.

## 9. Out of scope (here)

Code changes (sub-project B), the demo GIF, GitHub metadata and the release (sub-project C), a docs website.
