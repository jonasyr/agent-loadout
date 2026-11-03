# Release Notes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `loadout release` writes Keep a Changelog notes from the merged PRs since the last tag, and a `/loadout:release` skill turns that draft into user-facing notes and releases only after the person's yes.

**Architecture:** `cli/loadout/release.py` gets a notes generator (first-parent PR subjects since the newest `vX.Y.Z` tag of any version, mapped to Keep a Changelog sections) and two flags: `--draft-notes FILE` (all checks, write only the draft, change nothing) and `--notes FILE` (use a given section). A new plugin skill drives the AI step through those flags; the CLI stays AI-free.

**Tech Stack:** Python 3.11 stdlib, git and gh via `runner.run`, a Markdown skill in `plugins/loadout/skills/`, eval cases in `plugins/loadout/evals/`.

**Spec:** the design approved in chat on 2026-11-03 (recorded here): Keep a Changelog 1.1.0; generated at release time from merged PRs; AI help as a `/loadout:release` skill that drafts, rewrites from PR titles and bodies, shows, and runs the release only after the person's yes in the chat.

## Global Constraints

- Stdlib only; every git/gh call through `runner.run` with argument lists. Tests use `fake_home`/`fake_runner`; never real git network, gh or a push.
- `--draft-notes` writes nothing in the repo, commits nothing, tags nothing, pushes nothing; it runs every refusal check `cut` runs first (same order, same messages).
- Section heading exactly `## [X.Y.Z] - YYYY-MM-DD`; compare link line exactly `[X.Y.Z]: https://github.com/<slug>/compare/<prev>...vX.Y.Z` (`<slug>` from `channels.kit_slug`; without a previous tag: `https://github.com/<slug>/releases/tag/vX.Y.Z`).
- Section order: Breaking, Added, Changed, Fixed, Security; empty sections are left out; at most 15 bullets per section, then `- …and N more (see the compare link)`.
- The skill never publishes without an explicit yes from the person in the chat and never edits CHANGELOG.md itself. Agents never run evals (`plugins/loadout/evals/run.sh` is the user's).
- Conventional Commits, no AI attribution.

## Review Focus

1. **History with direct pushes and merge commits** (like this repo before PRs): only first-parent subjects ending in `(#N)` count. Test in Task 1: `test_only_first_parent_pr_subjects_count`.
2. **The previous tag is below the floor** (`v0.1.0`): it still bounds the range. Test in Task 1: `test_range_starts_at_the_newest_tag_of_any_version`.
3. **A `--notes` file for another version, empty, or without the heading**: refused, nothing changed. Test in Task 1: `test_notes_file_must_carry_this_version`.
4. **PR titles with Markdown or control characters**: printed through `printable`, written as plain bullets. Test in Task 1: `test_pr_subjects_are_printable_in_the_plan`.
5. **The skill is asked to release without a yes** (or the person says "looks good" to a question that was not the release question): it must ask the explicit question. Grader in Task 2.

---

### Task 1: Notes generator, `--draft-notes`, `--notes`

**Files:**
- Modify: `cli/loadout/release.py`, `cli/loadout/commands.py` (`_register_release`: the two flags; usage line)
- Test: `tests/test_release.py`

**Interfaces:**
- Produces:
  - `release.base_tag(root: Path) -> str | None`: the newest tag matching `v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)` of any version (local tags plus ls-remote ones, as `_tags` already reads), by version.
  - `release.pr_subjects(root: Path, prev: str | None) -> list[tuple[str, int]]`: `git log --first-parent --format=%s <prev>..HEAD` (or `HEAD`), kept only when the subject ends in `(#N)`; returns (subject without the `(#N)` suffix, N). Raises `RuntimeError` on a git failure (as `_bullets` does now).
  - `release.notes_section(version: str, today: str, prs: list[tuple[str, int]], slug: str, prev: str | None) -> str`: the Keep a Changelog section. Mapping: subject `type(scope)!:` or containing `BREAKING CHANGE` → Breaking; `feat` → Added; `fix` with scope `security`, or a subject mentioning `secret`/`security` → Security; other `fix` → Fixed; `refactor`/`perf` → Changed; `docs`, `chore`, `test`, `ci`, `build`, `style` → left out. A bullet is `- <description> (#N)` where description is the subject after `type(scope)!: `. A summary placeholder line `<!-- one to three sentences for users: what this release brings -->` sits under the heading. No PRs → `- No user-facing changes.` under the summary.
  - `cut(..., draft_notes: Path | None = None, notes: Path | None = None)`: `--draft-notes` writes the section to that file after all checks and returns 0 with `draft notes for vX.Y.Z written to FILE; nothing else changed`; `--notes` reads FILE, refuses (nothing changed) unless it starts with `## [X.Y.Z] - ` for this version and has a non-empty line after the heading; `--edit` and `--notes` together are refused; `--draft-notes` and `--notes` together are refused.
  - The GitHub Release body is the section without its heading line and without the compare-link line, plus `**Full changelog:** <compare url>` at the end.
- [ ] **Step 1: Write the failing tests** in `tests/test_release.py`: `test_only_first_parent_pr_subjects_count` (fake `git log --first-parent` output with PR and non-PR subjects), `test_range_starts_at_the_newest_tag_of_any_version` (tags `v0.1.0` only → range `v0.1.0..HEAD`), `test_sections_follow_keep_a_changelog` (feat/fix/fix(security)/feat!/docs/refactor subjects → exact section text incl. order, compare link, omitted docs), `test_long_section_is_capped_at_15`, `test_draft_notes_runs_the_checks_and_changes_nothing` (a refusal still refuses; on success no write to pyproject/CHANGELOG, no commit/tag/push/gh release call, the file holds the section), `test_notes_file_must_carry_this_version` (other version, empty, no heading → refused, nothing changed), `test_notes_file_is_used_for_changelog_and_release_body` (CHANGELOG gets the file's section; gh release `--notes-file` content has no heading and ends with the full-changelog line), `test_edit_and_notes_exclude_each_other`, `test_pr_subjects_are_printable_in_the_plan`. Update existing tests that asserted the old `## X.Y.Z (date)` heading.
- [ ] **Step 2: Run** `uv run --python 3.12 --with pytest pytest -q tests/test_release.py`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement** the Produces list; replace `_bullets`/`_NOTABLE`.
- [ ] **Step 4: Run** the same, then the full suite. Expected: PASS.
- [ ] **Step 5: Commit** `feat(release): Keep a Changelog notes from merged PRs; --draft-notes and --notes`.

### Task 2: `/loadout:release` skill and its evals

**Files:**
- Create: `plugins/loadout/skills/release/SKILL.md`
- Create: `plugins/loadout/evals/release-notes/` (`case.yaml`, `prompt.md`, `scaffold.sh`, `graders/*.md`), following `plugins/loadout/evals/usage-report/`
- Modify: `plugins/loadout/evals/bin/loadout` (the stub answers `release X.Y.Z --draft-notes FILE` by writing a fixed draft with 3 PRs, and `release … --notes FILE --yes` by printing `Released vX.Y.Z.`), and a `gh` stub for `gh pr view N --json title,body` if the eval harness has a stub folder for it (check `plugins/loadout/evals/bin/`).
- Test: `claude plugin validate plugins/loadout` (the user runs it if the agent may not); a static test if the repo has one for skill frontmatter (check `tests/` for skill tests and extend it).

**Interfaces:**
- Consumes: Task 1's flags and messages.
- Produces: skill `release` (name `release`, description that triggers on "release", "cut a release", "publish vX", "release notes"). Steps: (1) ask for the version if not given, suggest the next one from the last tag and the PR types (patch for fixes only, minor for feat, never major without the person); (2) run `loadout release X.Y.Z --draft-notes <tmp file>`; on a refusal show it and stop; (3) for each `(#N)` in the draft run `gh pr view N --json title,body` (read-only); (4) rewrite: fill the summary (1–3 sentences for people using loadout), one plain line per user-visible change, merge related PRs into one line keeping all `(#N)`, drop internal-only lines, keep the section order, the heading and the compare link exactly, invent nothing; (5) write it back to the file, show it in full, and ask "Release vX.Y.Z with these notes? (yes/no)"; (6) only on an explicit yes to that question run `loadout release X.Y.Z --notes <file> --yes` and report its output; anything else: stop and say the file path and the command to run later. Never edit CHANGELOG.md or run git/gh commands that write. Codex: the same skill works as `$loadout:release`.
- [ ] **Step 1: Write the eval case** (prompt: "Release 0.3.0 with good notes."; graders: skill fired; ran `--draft-notes`; read at least one PR with `gh pr view`; asked the explicit question before any `--notes … --yes` run; never edited CHANGELOG.md) and the stub changes.
- [ ] **Step 2: Write the skill.**
- [ ] **Step 3: Run** `uv run --python 3.12 --with pytest pytest -q` (any skill/eval static tests). Expected: PASS. Do not run the evals.
- [ ] **Step 4: Commit** `feat(skills): /loadout:release drafts user-facing notes and releases after a yes`.

### Task 3: Docs

**Files:** `CONTRIBUTING.md` ("Releasing": the template, `--draft-notes`, `--notes`, `--edit`, the skill), `docs/reference/cli.md` (release flags), `docs/adr/0046-release-channels.md` (a short "Release notes" addendum: Keep a Changelog, generated from merged PRs, the skill), `docs/reference/modules.md` / skills list if the repo lists skills (check `docs/reference/` for a skills page and add `release`), README only if it lists the plugin's skills.
- [ ] **Step 1: Write** the docs. **Step 2: Run** `uv run --python 3.12 --with pytest pytest -q tests/test_docs_links.py tests/test_docs_commands.py`. Expected: PASS. **Step 3: Commit** `docs: release notes (Keep a Changelog, /loadout:release)`.
