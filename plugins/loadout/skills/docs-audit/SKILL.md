---
name: docs-audit
description: Full, expensive audit of all docs and memories in a repo — verifies every claim against the current code, asks about anything unclear, and rewrites everything into the loadout docs structure (docs/ as single source of truth). Resumable. Use when docs or memories may be stale, wrong or duplicated.
disable-model-invocation: true
---

# Docs audit

Thorough by design: it may take long and use many tokens. Correctness over speed. Follow `~/.claude/rules/loadout/docs-policy.md` and `memory-policy.md`.

## 0. Resume or start

- If `.loadout/docs-audit/` contains a checklist, resume it from the first unchecked item.
- Otherwise create `.loadout/docs-audit/<YYYY-MM-DD>.md` and make sure `.loadout/` is in `.gitignore` while the audit runs.
- Update the checklist after every step, so the audit survives context compaction or a new session.

## 1. Inventory

List every documentation artifact: `README*`, `AGENTS.md`, `CLAUDE.md`, `docs/**`, ADRs, `.serena/memories/*`, other `*.md` outside dependency dirs, and doc comments only where docs reference them. Record each in the checklist with its size.

## 2. Extract claims

For each artifact, extract atomic claims into the checklist:
- commands
- file paths
- symbols (functions, classes, config keys)
- parameters and defaults
- behaviour and architecture statements
- decisions and their rationale
- status claims ("implemented", "TODO", "deprecated")

Note where each claim lives (file and line).

## 3. Verify against the current code

Dispatch parallel subagents (superpowers:dispatching-parallel-agents), one per doc area or about 30 claims; for a small repo (under ~30 claims) verify inline instead. Give each its claim list and these rules:
- **Symbols and structure:** codebase-memory-mcp (`search_graph`, `trace_path`, `get_code_snippet`) and Serena (`find_symbol`). Index first if needed.
- **Paths:** check existence.
- **Commands:** verify with harmless forms only (`--help`, `--version`, dry run, `--collect-only`). Ask the user before running tests or builds. Never run anything that deploys, deletes or writes outside the repo.
- **Behaviour:** read the implementing code; quote the lines that confirm or refute the claim.
- **Classification**, with evidence for each claim: `correct` | `stale` | `wrong` | `unclear` | `contradictory` (with the other claim's location) | `duplicated` | `misplaced` (wrong layer) | `unverifiable`.

Then find **missing** documentation: modules, entry points, CLI commands, config options and env vars that no doc mentions but that a user or contributor would need.

Record all results in the checklist.

## 4. Ask

Collect everything the code cannot settle:
- intent ("which of these two behaviours is intended?");
- open decisions;
- contradictions between docs;
- `unverifiable` claims;
- planned-but-unimplemented features.

Ask in batches of related questions (multiple choice where possible). Never guess intent. Record the answers in the checklist.

## 5. Plan the target structure

Propose the target layout before rewriting:
- `docs/` sections (Diátaxis where it fits: tutorials, how-to, reference, explanation; `docs/adr/` for decisions);
- what moves where;
- which memories shrink to a summary plus a link;
- which content is deleted as duplicate.

Get approval.

## 6. Rewrite

- Facts go into their single home in `docs/`; corrected per the verification and answers.
- Decisions found in prose become ADRs.
- `AGENTS.md`: short and accurate (purpose, verified commands, hard conventions, map).
- Serena memories: a 1–3 line summary plus link per topic, plus genuine agent notes (gotchas, task recipes, status). Delete memories that only duplicated docs.
- `README.md`: human entry point linking into `docs/`.

## 7. Validate

- Every relative link and referenced path resolves.
- Every symbol mentioned exists.
- Every remaining claim is either verified or confirmed by the user.

Re-run the checks on the rewritten files.

## 8. Report and commit

Present:
- counts per classification;
- the list of corrections (wrong → right, with evidence);
- open items the user deferred;
- the diff grouped by layer.

After approval, commit per layer (`docs: ...`, `docs(agents): ...`, `docs(memories): ...`). Delete the checklist and the temporary `.gitignore` entry.
