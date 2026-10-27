# codex-reviewer plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship today's repo-only `codex-reviewer` agent as an opt-in, Claude-Code-only plugin `codex-reviewer@agent-loadout`.

**Architecture:**
- A second plugin folder `plugins/codex-reviewer/`, with one repo-neutral agent, listed second in `.claude-plugin/marketplace.json`.
- A catalog add-on entry with `offer` and `"target": "claude"` keeps it off by default.
- Codex's plugin routing and the profile mirror skip catalog plugins targeted at Claude Code only.
- This repo turns the plugin on through a new project `.claude/settings.json`. Its own agent copy goes, and the copy's repo rules move into `AGENTS.md`.

**Tech Stack:** Python 3.11+ standard library (`cli/loadout/`), pytest, Claude Code plugin manifests, Markdown docs.

**Spec:** `docs/superpowers/specs/2026-10-27-codex-reviewer-plugin-design.md`

Implementers: use codebase-memory (`search_graph`, `trace_path`, project `home-jonas-Documents-Code-agent-loadout`) and Serena (`find_symbol`, `find_referencing_symbols`) before grep.

## Global Constraints

- Standard library only in `cli/loadout/`; tests use `fake_home`/`fake_runner`; never run real `claude`, `codex`, `loadout` or installers. `claude plugin validate` is read-only and allowed.
- Conventional Commits; no `Co-Authored-By` or AI attribution.
- One home per fact: edit `docs/`, link from elsewhere.
- Plugin id: `codex-reviewer@agent-loadout`. Marketplace entry second, source `./plugins/codex-reviewer`, no `version` (in the marketplace entry or in `plugin.json`).
- Agent tools: `Read, Grep, Glob, Bash` plus, in both name variants (`mcp__plugin_loadout_serena__` / `mcp__serena__`, `mcp__plugin_loadout_codebase-memory-mcp__` / `mcp__codebase-memory-mcp__`): Serena `find_symbol`, `find_referencing_symbols`, `get_symbols_overview`; codebase-memory `search_graph`, `trace_path`, `get_code_snippet`, `query_graph`. Never Edit, Write, MultiEdit or any `replace_`/`insert_` tool.
- The rubric attribution stays: openai/codex `codex-rs/prompts/templates/review/rubric.md`, Apache License 2.0.
- Test command: `uv run --python 3.12 --with pytest pytest -q --deselect "tests/test_docs_links.py::test_links_resolve[docs/examples/Niklas_Serena_Config.md]"`. Never commit `docs/examples/Niklas_Serena_Config.md`.

Ruling (plan, on the spec's "Decided" list): the spec's catalog field `"agents": ["claude"]` becomes the existing catalog key `"target": "claude"`. It already means "tied to one coding agent" for binaries (`catalog.binaries`, `docs/reference/catalog-format.md`). The meaning is the same and there is one key fewer. Cost if wrong: one rename.

## Review Focus

1. A user with their own Serena or codebase-memory server: the agent's tool list must also name `mcp__serena__…` and `mcp__codebase-memory-mcp__…` (Task 1 test).
2. A user turns the add-on on, then runs `loadout update` with Codex on: Codex must not get `codex-reviewer@agent-loadout`, and the output says why once (Task 2 test).
3. A profile whose `install` lists `codex-reviewer@agent-loadout`: the Codex mirror skips it (Task 2 test).
4. `loadout configure own` / inventory must not report the enabled add-on as "your own tool": it is a catalog entry (Task 2 test).
5. A repo without `AGENTS.md`, or with `master` and no `origin/HEAD`: the agent prompt says what to do (the default-branch order and "no rules file: rubric only") (Task 1 test on the prompt text).

---

### Task 1: The plugin and its repo-neutral agent

**Files:**
- Create: `plugins/codex-reviewer/.claude-plugin/plugin.json`
- Create: `plugins/codex-reviewer/.codex-plugin/plugin.json`: minimal (`name`, `description`, `author`, `homepage`, `repository`, `license`), shaped like `plugins/loadout/.codex-plugin/plugin.json`, with no skills, hooks or servers.
- Create: `plugins/codex-reviewer/agents/codex-reviewer.md`, from `.claude/agents/codex-reviewer.md`.
- Create: `plugins/codex-reviewer/NOTICE`: the rubric's source URL, "Apache License 2.0", the adaptation note.
- Create: `plugins/codex-reviewer/README.md`: what it is, how to turn it on, how to run it, and a link to the how-to from Task 4.
- Modify: `.claude-plugin/marketplace.json`, adding the second entry (category `development`).
- Test: `tests/test_hooks.py`. Move `test_codex_reviewer_can_use_serena_and_graph` to read the plugin's agent, and extend `test_marketplace_lists_kit_core_without_version`.

**Interfaces:**
- Produces: the plugin id `codex-reviewer@agent-loadout` and the agent file path `plugins/codex-reviewer/agents/codex-reviewer.md` (Tasks 2–4).

- [ ] **Step 1: Write the failing tests** in `tests/test_hooks.py`
  - `test_codex_reviewer_can_use_serena_and_graph` reads `paths.kit_root() / "plugins/codex-reviewer/agents/codex-reviewer.md"` and asserts the full tool list from Global Constraints, both variants. It keeps the no-Edit/Write/MultiEdit/`replace_`/`insert_` assertion.
  - `test_marketplace_lists_kit_core_without_version` additionally asserts:
    - `market["plugins"][1]["name"] == "codex-reviewer"`;
    - its `source == "./plugins/codex-reviewer"`;
    - no `version` in that entry or in `plugins/codex-reviewer/.claude-plugin/plugin.json`.
  - New `test_codex_reviewer_prompt_is_repo_neutral` asserts that the agent text:
    - contains `origin/HEAD`, `master` and `AGENTS.md`;
    - contains `"apache license 2.0"` (case-insensitive);
    - does not contain `"# This repository"`;
    - does not contain `uv run --python 3.12`.
- [ ] **Step 2: Run them.** `uv run --python 3.12 --with pytest pytest -q tests/test_hooks.py -k "codex_reviewer or marketplace"`. Expected: FAIL (file missing).
- [ ] **Step 3: Write the plugin files.** The agent keeps the rubric body unchanged. Its frontmatter `description` says to use it when Codex's GitHub review is unavailable, and when asked to "run the codex-reviewer agent on this branch". The repo section "This repository" becomes "How to review", which says:
  - Base: `origin/HEAD` (`git symbolic-ref refs/remotes/origin/HEAD`), else `main`, else `master`. Diff with `git diff <base>...HEAD`.
  - Read `AGENTS.md` at the repo root: its "Code Review Rules" section if present, else the whole file. Cite the rule a finding rests on. With no `AGENTS.md`, use the rubric alone.
  - Report P0–P2 only.
  - Trace call paths across files (codebase-memory, Serena, then grep).
  - Read-only: run only read-only commands, plus the test command `AGENTS.md` names, on the files under review. Never edit files, never run installers, deploys or mutating commands.
  - Output exactly the rubric's JSON.

  Leave `.claude/agents/codex-reviewer.md` in place for now (Task 3 removes it).
- [ ] **Step 4: Run the tests and validate.** Run the Step 2 command (expected: PASS), then `claude plugin validate .` and `claude plugin validate plugins/codex-reviewer` (expected: both report valid).
- [ ] **Step 5: Commit.** `feat(codex-reviewer): ship the review stand-in as its own plugin in the marketplace`

### Task 2: Off by default, and never in Codex

**Files:**
- Modify: `catalog.json`. Add an entry: `id` `addon-codex-reviewer`, `kind` `plugin`, `status` `alternative`, `category` `workflow`, `target` `claude`, `match.names` `["codex-reviewer@agent-loadout"]`, `offer` `{"plugin": "codex-reviewer@agent-loadout"}`. Its `reason` says it stands in for Codex's GitHub review when its quota is out, adds one agent description to every session, and is Claude Code only. Place it per `tests/test_catalog_order.py`.
- Modify: `cli/loadout/catalog.py`. Add `claude_only_plugins() -> frozenset[str]`: the `match.names` of plugin entries whose `target == "claude"`.
- Modify: `cli/loadout/codex.py`.
  - `plugin_routes` skips ids in `catalog.claude_only_plugins()`, so they are neither routed nor `missing`.
  - `apply_plugins` adds `f"plugin {pid}: Claude Code only, not added to Codex"` for each such id enabled in the desired settings. Use the same wording in the update plan's Codex part if it lists plugins.
- Modify: `cli/loadout/codex_project.py`. The profile loop skips such ids with `skipped.append(f"plugin {p}: Claude Code only, not added to Codex")`.
- Modify: `docs/reference/catalog-format.md`. Document `target` on plugin entries: Codex never gets the plugin.
- Test: `tests/test_codex_claude_only.py` (new).

**Interfaces:**
- Consumes: plugin id `codex-reviewer@agent-loadout` (Task 1).
- Produces: `catalog.claude_only_plugins() -> frozenset[str]`.

- [ ] **Step 1: Write the failing tests** in `tests/test_codex_claude_only.py`
  - `test_claude_only_plugin_has_no_codex_route`: `routes, missing = codex.plugin_routes(settings)` with `enabledPlugins` `{"codex-reviewer@agent-loadout": True, "loadout@agent-loadout": True}` and the agent-loadout GitHub marketplace. Asserts `"codex-reviewer" not in sum(routes.values(), [])`, `"loadout" in` it, and `missing == []`.
  - `test_apply_plugins_says_claude_only_once`: through `apply_plugins` with `fake_runner`, the desired settings enabling it. Asserts that exactly one line equals `"plugin codex-reviewer@agent-loadout: Claude Code only, not added to Codex"`, and that no `fake_runner` call contains `codex-reviewer`.
  - `test_profile_mirror_skips_claude_only`: a profile whose `install` has it; the codex_project plugin collector returns it in `skipped`, not in `plugins`.
  - `test_catalog_offers_codex_reviewer_off_by_default`: `catalog.by_id("addon-codex-reviewer")["offer"]["plugin"] == "codex-reviewer@agent-loadout"`, and `"codex-reviewer@agent-loadout"` is not in `settings.base.json`'s `enabledPlugins`.
  - `test_enabled_addon_is_not_an_own_tool`: with it enabled in user settings, the inventory/`configure own` listing does not include it. Use the existing own-tools test helpers.
- [ ] **Step 2: Run them.** `uv run --python 3.12 --with pytest pytest -q tests/test_codex_claude_only.py`. Expected: FAIL.
- [ ] **Step 3: Implement** as in Files.
- [ ] **Step 4: Run them, then the full suite.** Expected: PASS, and the full suite green.
- [ ] **Step 5: Commit.** `feat(codex): keep Claude-Code-only catalog plugins out of Codex; offer codex-reviewer as an add-on`

### Task 3: This repo uses the plugin

**Files:**
- Create: `.claude/settings.json` with `{"enabledPlugins": {"codex-reviewer@agent-loadout": true}}`.
- Delete: `.claude/agents/codex-reviewer.md`.
- Modify: `AGENTS.md` "Code Review Rules". Add the lines from the old agent's "This repository" section that are repo rules, as a `### Edge cases and limits` subsection:
  - the machines to consider: Codex-only, VS Code's Codex extension without the CLI, WSL with a Windows-side Codex, the extension's bundled `claude`, Git Bash, valid-but-odd inputs, commands that report success on failure;
  - reviewers that run commands run only read-only commands and `uv run --python 3.12 --with pytest pytest -q <files>`;
  - never real `claude`/`codex`/`loadout` against the real home, never installers or evals, never edits.
- Modify: `CONTRIBUTING.md:106` and `docs/reference/modules.md:132`. Point to the plugin (`plugins/codex-reviewer/`), which this repo turns on in `.claude/settings.json`.
- Test: `tests/test_hooks.py` (or a new small test file).

- [ ] **Step 1: Write the failing test** `test_repo_enables_codex_reviewer_and_has_no_copy`. It asserts:
  - the repo `.claude/settings.json` has `enabledPlugins["codex-reviewer@agent-loadout"] is True`;
  - `.claude/agents/codex-reviewer.md` does not exist;
  - `AGENTS.md` contains `"Codex-only"` under the "Code Review Rules" heading.
- [ ] **Step 2: Run it.** Expected: FAIL.
- [ ] **Step 3: Make the changes** in Files.
- [ ] **Step 4: Run the full suite.** It includes the docs link tests. Expected: green.
- [ ] **Step 5: Commit.** `chore(repo): use the codex-reviewer plugin here; its rules move to AGENTS.md`

### Task 4: Docs

**Files:**
- Create: `docs/adr/0044-codex-reviewer-as-opt-in-plugin.md` (Status, Context, Decision, Consequences). It records:
  - a second plugin in the marketplace, off by default via the catalog `offer`;
  - `target: claude` keeps it out of Codex;
  - the minimal Codex manifest;
  - the repo enables it in its project settings.
- Modify: `docs/adr/README.md` (the list) and the `AGENTS.md` map, which becomes "decisions 0001-0044".
- Create: `docs/how-to/codex-review-stand-in.md`. It covers:
  - turning it on: `loadout configure set plugin codex-reviewer@agent-loadout on`, then `/reload-plugins`;
  - running it ("run the codex-reviewer agent on this branch");
  - reading the JSON (P0–P2, `code_location`);
  - what it reads (`AGENTS.md`), and that it never edits.
- Modify: `docs/README.md` (link the how-to) and `docs/reference/included-tools.md` (add-ons section: the entry and its reason).
- Test: the existing docs link tests.

- [ ] **Step 1: Write the pages.**
- [ ] **Step 2: Run the full suite.** Expected: green (link tests included).
- [ ] **Step 3: Commit.** `docs: ADR 0044 and the codex-reviewer how-to`
