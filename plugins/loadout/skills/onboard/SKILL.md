---
name: onboard
description: Set up a repository for agent work — new/empty repos get a guided project definition (purpose, stack, structure, first ADR); existing repos get an accurate AGENTS.md, Serena memories and a codebase-memory index. Use after `loadout init`, or when a repo has no AGENTS.md.
---

# Onboard a repository

Read `~/.claude/rules/loadout/docs-policy.md` and `memory-policy.md` first; everything you write must follow them.

## 1. Detect the mode

List tracked files (`git ls-files`; if not a git repo, list the directory).
- **New project**: no source files; only README, LICENSE, .gitignore, AGENTS.md/CLAUDE.md skeletons or docs skeletons.
- **Existing project**: anything else.

Say which mode you detected and why, and let the user correct you.

## 2a. New project

1. Invoke `superpowers:brainstorming` to settle what the project should become: purpose, users, success criteria, constraints, stack. Ask one question at a time.
2. When the design is agreed:
   - write `docs/README.md` (index) and `docs/adr/0001-<stack-decision>.md` (Context, Decision, Consequences, Status: accepted);
   - write `AGENTS.md`: purpose (one paragraph), commands (install/test/run for the chosen stack), hard conventions, map.
3. Suggest profiles for the stack (`loadout profile <name>`: web, db, android, thesis, sonar) and run the ones the user accepts. For a web stack, suggest `@playwright/test` for E2E tests.
4. Create the minimal directory skeleton the stack's conventions call for, such as package manifest, `src/`, `tests/` and a first passing test. Stop there; feature work goes through the normal superpowers flow.
5. Show the diff and commit after approval.

## 2b. Existing project

1. If the repo is not indexed, index it with codebase-memory-mcp (`index_repository`) and use `get_architecture` for the overview.
2. Commands: find how to install, test, lint and run (manifests, Makefile/justfile, CI config). Verify each with a harmless form (`--help`, `--version`, `--collect-only`, dry run). Never run something that deploys, deletes or writes outside the repo.
3. AGENTS.md:
   - **Missing:** write it.
   - **Exists:** repair it. Fix wrong commands and paths, remove content that duplicates `docs/` (link instead), keep it short.
   - **CLAUDE.md** with real content and no AGENTS.md: propose moving that content into AGENTS.md and replacing CLAUDE.md with `@AGENTS.md`; do it only after the user agrees.
4. Leave an existing `.mcp.json` and `.claude/settings.json` unchanged; mention what they configure.
5. Serena:
   - **No memories:** run Serena onboarding, but keep each memory a short summary plus links into `docs/`.
   - **Memories or docs already exist:** recommend `/loadout:docs-audit` instead of rewriting them here.
6. Show the diff and commit after approval (`docs: onboard repository for agents`).
