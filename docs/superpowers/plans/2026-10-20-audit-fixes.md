# Audit fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the code issues the docs audit (#52) found and #53 left open, plus two wording flaws the first real `loadout update` showed, so the docs can describe intended behaviour instead of quirks.

**Architecture:** Small, independent fixes grouped by file. Each one has a test that fails first and changes the docs page that describes the behaviour (one home per fact). The two larger pieces are the Codex ownership rule ("note once, then quiet", recorded at session start) and WSL installs treating Windows binaries as missing.

**Tech Stack:** Python 3.11+ standard library (`cli/loadout/`), pytest with `fake_home` and `fake_runner`.

**Spec:** the backlog entry "TODO (2026-10-19, docs audit, one `fix:` PR with tests)" and its "Answers 2026-10-19" line in `.superpowers/handoff/2026-10-13-hardening-backlog.md`, plus the answers of 2026-10-20 below. Code facts per item, re-checked on main b61eb5e, with file:line, the test to imitate and the docs lines: `.superpowers/sdd/2026-10-20-audit-fixes/facts.md` (read the item's section before each task; line numbers drift, re-read the named functions).

## Answers 2026-10-20 (binding)

- Item 4: with only VS Code's Codex extension, `loadout profile` prints a note ("VS Code's Codex extension loads no plugins; the profile's Codex plugins are not set"), writes the profile's other files, exits 0.
- Item 10: uninstall.md uses the read-only `loadout explain ~/.codex/config.toml` and `loadout explain ~/.codex/hooks.json` to see what is loadout's; the record is kept current by the session-start rule of items 17+19; no `configure set target codex on` step before uninstalling.
- Items 17+19: an entry loadout wrote that the person changed is recorded as theirs at the next session start (Codex on, lock respected with no wait), with one notice ("you changed X; it is yours now"); `loadout check` is quiet about it afterwards. The person's own kept value (`KEY: left as is in config.toml (your value)`) also gets one note, then quiet. A same-named table that was never loadout's keeps warning.
- Item 12: in WSL a Windows node/npm/uv/git/claude on PATH counts as missing (a Linux copy in the home, the Windows one untouched), also without `--install` in the report, and `loadout update` offers the install.
- Item 5: fix the comment only (no new check row). Items 14/15: fix lines name the real Codex home (`CODEX_HOME`), not a literal `~/.codex`.

## Global Constraints

- Python 3.11+, standard library only in `cli/loadout/`; external commands only through `runner` with argument lists.
- loadout changes only what it recorded as its own; user text byte for byte; backup before any removal or overwrite; with an agent off nothing of it is read or changed (AGENTS.md "Code Review Rules").
- Every printed path or name from a file or a command is escaped with `out.printable`; command output that can carry credentials goes through `secrets.redact`.
- Tests use `fake_home` and `fake_runner`; never the real home; never real `claude`, `codex`, installers or a restart into the real launcher (conftest guards `update._exec`). Full suite with `--deselect "tests/test_docs_links.py::test_links_resolve[docs/examples/Niklas_Serena_Config.md]"` (an untracked local file).
- Windows and WSL CI must pass (host binary helpers; POSIX-only tests skip on `os.name == "nt"`).
- Conventional Commits, no AI attribution.

## Review Focus

1. A Codex `config.toml` table loadout wrote and the person edited: recorded as theirs exactly once, never overwritten, never removed by a later `configure set target codex off` (Task 6).
2. A WSL machine with only Windows tools on PATH and no `--install`: the report says missing with the install command and changes nothing (Task 4).
3. `python3 -m loadout` from `cli/` and `bin/loadout` both list every subcommand, on Windows too (Task 1).
4. A first `loadout update` with no `codex-marketplaces.json`: the plan names the real marketplace and plugin ids and says re-add for installed plugins (Task 0).
5. A Codex-only user (Claude Code off): nothing in these fixes reads or writes Claude Code files (all tasks; checked in the final review).

---

### Task 0: The update plan names Codex marketplaces from Codex's own list

**Files:** Modify `cli/loadout/update.py` (the Codex plugin item builder, `_codex_item` area ~55-100); Test `tests/test_update_plan.py`.

**Decision:** when loadout's record has no name for a source, take the marketplace name from `codex.marketplaces()` whose source matches (`codex._norm_source` / `_same_source`). With a name, plugin ids are real (`superpowers@claude-plugins-official`) and installed ones count as re-add; the label says "refresh N; plugins: re-add M" and adds "(no record to compare yet)" when every route is refreshed for lack of a record. The `<…'s marketplace>` placeholder remains only for a marketplace Codex does not list yet (a real add).

- [ ] Test `test_a_first_update_names_codex_marketplaces_from_codex_list`: no record; `codex plugin marketplace list --json` lists `claude-plugins-official` with source `https://github.com/anthropics/claude-plugins-official.git`; `codex plugin list` lists `superpowers@claude-plugins-official`. Assert the rendered plan contains `re-add plugin superpowers@claude-plugins-official`, `codex plugin marketplace upgrade claude-plugins-official`, "no record to compare yet", and no `<` placeholder for that route. Run: FAIL (placeholder, "add").
- [ ] Implement; run `tests/test_update_plan.py tests/test_update_run.py tests/test_codex_plugins.py`: PASS.
- [ ] Commit `fix(update): name Codex marketplaces from Codex's list on a first update`.

### Task 1: `python3 -m loadout` registers every subcommand (item 1)

**Files:** `cli/loadout/__main__.py`, `cli/loadout/commands.py` (top import), `tests/test_version.py` (or a new `tests/test_cli_entry.py`), `AGENTS.md:10`, `CONTRIBUTING.md:14`. Facts §1.

- [ ] Test: a subprocess `python -m loadout check --help` with `PYTHONPATH=cli`, `HOME` a tmp dir and `LOADOUT_UPDATE_PULLED=1` exits 0 and its help names `check`; and `--help` lists `update`, `check`, `configure`. Run: FAIL (`invalid choice`).
- [ ] Implement the facts file's cleanest fix (one registry module both entry points share; no second import of `__main__`).
- [ ] Docs: AGENTS.md and CONTRIBUTING.md no longer warn about `python -m`; AGENTS.md keeps the `bin/loadout <sub> --help` command.
- [ ] Commit `fix: python -m loadout registers every subcommand`.

### Task 2: Small command and help fixes (items 3, 6, 7)

**Files:** `cli/loadout/commands.py`, `cli/loadout/bootstrap.py` (help text, `--vscode-wsl` path), tests per facts §3, §6, §7; docs `docs/reference/cli.md`, `docs/how-to/codex.md` per facts.

- [ ] Item 3 test: `configure set target claude on` with no `claude` on PATH but the Claude Code extension's bundled claude (`runner.FALLBACK`) does not print "not installed yet" and sets the target. FAIL first.
- [ ] Item 6 test: `bootstrap --vscode-wsl` outside WSL prints exactly one line saying it applies to WSL only. FAIL first (two lines).
- [ ] Item 7 test: `bootstrap --help` for `--agents` names the stored choice ("default: the personal layer's choice, else ask"). FAIL first.
- [ ] Implement each; docs; one commit per item (`fix(configure): …`, `fix(bootstrap): …`).

### Task 3: Codex fix lines that name the right thing (items 2, 14, 15, 16)

**Files:** `cli/loadout/codex.py` (`program` docstring, `checks()`), `cli/loadout/codex_hooks.py` (constants); tests per facts §2, §14-16; `docs/how-to/troubleshooting.md` rows per facts.

- [ ] Item 14 test: Serena hooks missing while the user's hooks are inline in `config.toml` → the `Codex Serena hooks` fix names `config.toml` (its real path), not `hooks.json`. Item 15 test: "old Serena hooks still in it" → the fix says to remove them by hand (or the precise command from facts), not `loadout bootstrap`. Item 16 test: each cause of the `Codex` row (no codex, too old, Windows codex in WSL, CODEX_HOME into Windows) gets its own fix line. All FAIL first. Paths via the real Codex home.
- [ ] Item 2: docstring of `codex.program()` says it also runs `codex mcp remove` (no test; docstring only).
- [ ] Implement; troubleshooting rows match the new lines exactly; commits `fix(codex): …`.

### Task 4: WSL installs replace Windows tools on PATH (item 12)

**Files:** `cli/loadout/bootstrap.py` (`missing_binary`, `_windows_program`, `_prereq_summary` per facts §12), `cli/loadout/update.py` if it consumes `missing_tools`; tests `tests/test_wsl_codex_bootstrap.py` style; docs `docs/how-to/wsl.md`, `docs/how-to/troubleshooting.md`, `docs/reference/cli.md` per facts.

- [ ] Tests: in WSL with `node`, `npm`, `uv`, `git`, `claude` resolving to `/mnt/c/...` (fake `which`), `missing_tools` lists each as missing with its Linux install command; with `--install` the Linux install runs and nothing under `/mnt/c` is touched; without `--install` the report says missing and runs nothing (Review Focus 2); outside WSL nothing changes. FAIL first.
- [ ] Implement by generalising today's codex rule (one predicate for "a Windows binary seen from WSL"); docs.
- [ ] Commit `fix(bootstrap): in WSL a Windows tool on PATH counts as missing`.

### Task 5: Profile plan in extension mode and for repos not for Claude Code (items 4, 11)

**Files:** `cli/loadout/codex_project.py`, `cli/loadout/project.py`, `cli/loadout/profiles.py` per facts §4, §11; tests `tests/test_codex_project.py`, `tests/test_repo_writers_plan.py`; docs `docs/reference/profile-format.md`, `docs/reference/cli.md`, `docs/how-to/troubleshooting.md`.

- [ ] Item 4 test: extension mode (no Codex CLI, usable extension) → `loadout profile NAME` prints the note from the answers, writes the other files, exits 0. FAIL first (exit 1, "run loadout profile again").
- [ ] Item 11 test: a repo whose `.loadout.json` excludes Claude Code → the plan has one line "skipped for this repo (not for Claude Code): plugin a, plugin b". FAIL first.
- [ ] Implement; docs; commits `fix(profile): …`.

### Task 6: Codex entries the person changed: note once, then quiet (items 17+19, then 10)

**Files:** `cli/loadout/codex.py` (factor the ownership check out of `apply_config`; a `release_changed()` that records changed entries as the person's), `cli/loadout/maintenance.py` (`session_start` with Codex on: call it under the Codex lock with wait 0, queue one notice), `cli/loadout/explain.py` if `loadout explain` needs to cover `~/.codex/config.toml` and `hooks.json` (facts §10); tests `tests/test_codex_config.py`, new `tests/test_codex_release_notice.py`, new `tests/test_explain_codex.py`; docs `docs/how-to/troubleshooting.md`, `docs/reference/personal-layer.md`, `docs/how-to/uninstall.md`, `docs/reference/cli.md` per facts.

- [ ] Tests: (a) a `[mcp_servers.x]` table loadout wrote, edited by the person → at the next `session_start` it is recorded as theirs, one notice is queued, the table is byte-identical, and a later `loadout check` has no warning about it (FAIL first: the warning repeats); (b) the person's own kept value line gets one note and is quiet afterwards; (c) a same-named table never loadout's keeps its warning; (d) the session start never waits for a busy Codex lock and never fails the session; (e) `configure set target codex off` afterwards removes only what is still loadout's (Review Focus 1); (f) `loadout explain ~/.codex/config.toml` names loadout's entries and the person's, read-only.
- [ ] Implement; uninstall.md uses `loadout explain` and drops the `configure set target codex on` step; docs.
- [ ] Commits `fix(codex): an entry you changed is yours after one note` and `docs(uninstall): …`.

### Task 7: Repo meta (items 5, 8, 9, 18)

**Files:** `cli/loadout/check.py` (comment), `.github/ISSUE_TEMPLATE/1-bug.yml`, `.github/workflows/fresh-machine.yml`, `catalog.json` (mise `reason`), `CONTRIBUTING.md`, `docs/reference/modules.md` per facts §5, §8, §9, §18; tests `tests/test_github_templates.py`, `tests/test_fix_pass_a.py`, `tests/test_catalog_order.py`.

- [ ] Item 8 test: the bug form asks for the agent and surface (Claude Code / Codex, CLI / VS Code extension, which window) and does not require `claude --version`. Item 9 test: fresh-machine.yml's path filter includes every module bootstrap and update run through (`codex.py`, `vscode.py`, `wsl.py`, `runner.py`, `update.py`, `apply.py`, `locks.py`, `steps.py`, `maintenance.py`). Item 18 test: every tool mise installs is named in mise's `reason`. All FAIL first.
- [ ] Item 5: fix the comment at check.py (no test).
- [ ] Implement; `uvx check-jsonschema --builtin-schema vendor.github-issue-forms .github/ISSUE_TEMPLATE/1-bug.yml` if available; commits `fix(ci): …`, `docs(contributing): …`, `fix(catalog): …`.

### Task 8: Docs sync and backlog

- [ ] Run the `loadout:docs-sync` skill over `git diff --stat main...HEAD`; fix what it finds.
- [ ] Docs tests: `tests/test_docs_links.py tests/test_docs_commands.py tests/test_docs_vscode.py tests/test_readme.py` (Niklas deselect): PASS.
- [ ] Commit `docs: the audit fixes in the reference and how-tos`.
