---
name: onboard
description: Set up a repository for agent work — new/empty repos get a guided project definition (purpose, stack, structure, first ADR); existing repos get an accurate AGENTS.md, Serena memories and a codebase-memory index. Use after `loadout init`, or when a repo has no AGENTS.md.
disable-model-invocation: true
---

# Onboard a repository

Read `~/.claude/rules/loadout/docs-policy.md` and `memory-policy.md` first; everything you write must follow them.

## 1. Detect the mode

List tracked files (`git ls-files`; if not a git repo, list the directory).
- **New project**: no source files; only README, LICENSE, .gitignore, AGENTS.md/CLAUDE.md skeletons or docs skeletons.
- **Existing project**: anything else.

Until the user confirms the mode, start every message, including your final report, with `Mode: new project — <why>` or `Mode: existing project — <why>`, so the user can correct you. This applies even when the user gave all answers up front.

## 2a. New project

Define the project yourself; do not hand off to another workflow skill here.

1. Ask these questions one at a time, waiting for each answer (offer choices where you can):
   - **Purpose:** what should the project do, and what does success look like?
   - **Users:** who uses it, and how (CLI, web app, library, service)?
   - **Stack:** language, framework, package manager, test runner (suggest a default that fits the answers so far).
   - **Constraints:** deadlines, hosting, licences, performance, things to avoid.
2. Summarise the answers in a few lines and get a yes.
3. Write the project definition (`loadout init` already created skeletons; fill them in, do not create second copies):
   - `docs/adr/0001-<stack-decision>.md` (Context, Decision, Consequences, Status: accepted);
   - `AGENTS.md`: purpose (one paragraph), commands (install/test/run for the chosen stack), hard conventions, map;
   - `docs/README.md`: the index, linking the ADR.
4. Suggest profiles for the stack (`loadout profile <name>`: web, db, android, thesis, sonar) and run the ones the user accepts. For a web stack, suggest `@playwright/test` for E2E tests.
5. Create the minimal skeleton the stack's conventions call for, such as package manifest, `src/`, `tests/` and a first passing test.
6. Show the diff and commit after approval.

Stop there. For the first feature, suggest `superpowers:brainstorming`.

## 2b. Existing project

1. Before reading code, call codebase-memory-mcp `index_repository` (skip only if this repo is already indexed), then `get_architecture` for the overview. If the server is unavailable, say so and continue with Read/Grep.
2. Commands: find how to install, test, lint and run (manifests, Makefile/justfile, CI config). Verify each with a harmless form (`--help`, `--version`, `--collect-only`, dry run). Never run something that deploys, deletes or writes outside the repo.
3. AGENTS.md:
   - **Missing:** write it.
   - **Exists:** repair it. Fix wrong commands and paths, remove content that duplicates `docs/` (link instead), keep it short.
   - **CLAUDE.md** with real content and no AGENTS.md: propose moving that content into AGENTS.md and replacing CLAUDE.md with `@AGENTS.md`; do it only after the user agrees.
4. Leave an existing `.mcp.json` and `.claude/settings.json` unchanged; mention what they configure.
5. Serena:
   - **No memories and no docs:** run Serena onboarding, but keep each memory a 1–3 line summary that links to where the facts live (`AGENTS.md`, source files, `docs/` once it exists).
   - **Memories or docs already exist:** leave them as they are and recommend `/loadout:docs-audit` instead of rewriting them here.
6. Show the diff and commit after approval (`docs: onboard repository for agents`).
