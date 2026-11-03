# Release Channels Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Machines on the new stable channel run only released, 3-day-old kit code that the person applied themselves; dev keeps today's daily pull of `main`.

**Architecture:** One new module `cli/loadout/channels.py` owns the channel setting, the release record (first-seen per tag), the release status from `main`, eligibility and the checkout move. The daily maintenance run records releases and queues notices; `loadout update` and `loadout channel` move the kit checkout with a recorded undo and re-apply through today's restart path; the kit's Claude Code and Codex marketplaces are pinned to the release tag. A maintainer-only `cli/loadout/release.py` cuts and withdraws releases.

**Tech Stack:** Python 3.11+ standard library, git and gh through `runner.run`, POSIX sh and PowerShell bootstrap scripts, pytest with `fake_home`/`fake_runner`.

**Spec:** `docs/superpowers/specs/2026-11-03-release-channels-design.md`

## Global Constraints

- Standard library only in `cli/loadout/`; every git/gh/claude/codex call through `runner.run` with argument lists (no shell strings); background git runs with `GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=never`, `LC_ALL=C` (as `maintenance.pull`).
- Tag names: only `^v(\d+)\.(\d+)\.(\d+)$` at or above the floor `0.2.0` are ever used, stored or printed; anything else is ignored.
- Soak: 3 days (`3 * maintenance.DAY`) counted from this machine's `first_seen`; `now < first_seen` is not eligible.
- Never `checkout -f`, never stash, never reset; a move with local edits or local commits refuses and names them.
- Every kit move records its undo first: `["git", "-C", <kit root>, "checkout", "--detach", <old 40-hex sha>]`.
- Agent off (`targets.json`): nothing reads or writes `~/.claude` / `~/.codex` for that agent (ADR 0030).
- Tests use `fake_home` and `fake_runner` only; no real git network, no real `claude`/`codex`/`gh`. Shell-script tests may use a local bare repo as `LOADOUT_REPO_URL` (as `tests/test_entry_scripts.py` does).
- Conventional Commits, no AI attribution.
- New state files live in `paths.state_dir()`: `channel.json`, `releases.json`. `release-status.json` and `CHANGELOG.md` live at the repo root.
- Notices go through `maintenance.notify`; each says one action.

## Review Focus

1. **The background release check is offline, rate-limited or git fails.** Expected: nothing recorded, nothing said, the next day tries again. Test in Task 2: `test_release_check_offline_records_nothing`.
2. **A known tag later points at another commit.** Expected: never offered, one alarm notice, and a check row warns. Test in Task 1: `test_moved_tag_is_never_eligible_and_alarms_once`.
3. **The machine clock goes back (now < first_seen), or a tag is backdated.** Expected: not eligible; the tag date is never used outside bootstrap. Test in Task 1: `test_clock_before_first_seen_is_not_eligible`.
4. **The kit checkout has local edits or local commits when `update`/`channel` moves it.** Expected: refusal naming them, checkout and pins unchanged, no setting written. Test in Task 3: `test_move_refuses_local_commits_and_edits`.
5. **Windows: the kit root in the undo command is spelled differently** (case, slashes, a junction). Expected: restore accepts loadout's own recorded command and nothing else. Test in Task 3: `test_undo_allowlist_matches_kit_root_resolved`.

---

### Task 1: `channels` core: setting, tags, release record, status, eligibility

**Files:**
- Create: `cli/loadout/channels.py`
- Create: `release-status.json` (repo root): `{"urgent": [], "withdrawn": []}`
- Test: `tests/test_channels.py`

**Interfaces:**
- Produces:
  - `FLOOR: tuple[int, int, int] = (0, 2, 0)`, `SOAK: float = 3 * maintenance.DAY`, `KIT_MARKET = "agent-loadout"`, `DEFAULT_SLUG = "jonasyr/agent-loadout"`
  - `get() -> str | None` (None when `channel.json` is missing or invalid), `effective() -> str` (`"dev"` when unset), `set_channel(name: str, bk: Backup | None = None) -> None` (validates `stable|dev`; saves a copy of the old file into `bk` first when given; atomic write)
  - `parse_tag(name: str) -> tuple[int, int, int] | None` (None for a bad name or below `FLOOR`)
  - `remote_tags(root: Path) -> dict[str, str] | None`: `git ls-remote --tags origin`, tag → commit sha (the peeled `^{}` sha wins for annotated tags); None on any failure
  - `record_seen(tags: dict[str, str], now: float) -> list[str]`: updates `releases.json` `{"tags": {name: {"sha", "first_seen", "moved"?, "notified"?}}}`; returns the names newly found moved
  - `mark_notified(name: str) -> None`, `notified(name: str) -> bool`
  - `release_status(root: Path) -> Status` where `@dataclass Status: urgent: set[str]; withdrawn: dict[str, dict]` (keys are versions `"1.5.0"`, values `{"reason": str, "use": str | None}`); fetched with `git fetch origin main` then `git show FETCH_HEAD:release-status.json`; any failure or bad shape → empty `Status()`
  - `eligible(current: tuple[int, int, int] | None, now: float, status: Status) -> str | None`: the newest eligible tag name
  - `current_release(root: Path) -> str | None`: `git describe --tags --exact-match HEAD`, validated by `parse_tag`
  - `kit_slug(root: Path) -> str`: `owner/repo` from `git remote get-url origin` (https or ssh GitHub forms), else `DEFAULT_SLUG`

- [ ] **Step 1: Write the failing tests** in `tests/test_channels.py`:
  - `test_unset_channel_is_dev`: no file → `get() is None`, `effective() == "dev"`; `set_channel("stable")` → `get() == "stable"`; `set_channel("beta")` raises `ValueError`.
  - `test_parse_tag_accepts_only_release_names_at_or_above_floor`: `parse_tag("v0.2.0") == (0, 2, 0)`, `parse_tag("v1.10.3") == (1, 10, 3)`; None for `"v0.1.0"`, `"0.2.0"`, `"v0.2"`, `"v0.2.0-rc1"`, `"v0.2.0\n"`, `"v0.2.0; rm -rf ~"`.
  - `test_remote_tags_prefers_peeled_sha`: fake `ls-remote` output with `refs/tags/v0.2.0` and `refs/tags/v0.2.0^{}` lines → the `^{}` sha; a failing run → None.
  - `test_soak_counts_from_first_seen`: `record_seen({"v0.2.0": "a"*40}, now=T)`; `eligible(None, T + SOAK - 1, Status()) is None`; `eligible(None, T + SOAK, Status()) == "v0.2.0"`.
  - `test_clock_before_first_seen_is_not_eligible`: seen at T, `eligible(None, T - 10, Status()) is None`.
  - `test_moved_tag_is_never_eligible_and_alarms_once`: seen with sha a, later with sha b → `record_seen` returns `["v0.2.0"]` once, then `[]`; never eligible after.
  - `test_urgent_skips_soak_and_withdrawn_is_skipped`: `Status(urgent={"0.3.0"})` makes a just-seen `v0.3.0` eligible; `Status(withdrawn={"0.3.0": {...}})` makes it ineligible and the older one is picked.
  - `test_withdrawal_target_counts_as_urgent`: `Status(withdrawn={"0.3.0": {"reason": "r", "use": "0.3.1"}})` makes a just-seen `v0.3.1` eligible (spec: urgent is implied for a withdrawal's `use` target).
  - `test_only_newer_than_current`: `eligible((0, 3, 0), ...)` ignores `v0.2.0` and `v0.3.0`.
  - `test_release_status_bad_shapes_are_empty`: invalid JSON, a list, `"urgent": "x"`, a withdrawn entry without `reason` → those parts empty.
  - `test_kit_slug_from_origin_forms`: `https://github.com/o/r.git`, `git@github.com:o/r.git`, and a failing remote call → `DEFAULT_SLUG`.

- [ ] **Step 2: Run** `uv run --python 3.12 --with pytest pytest -q tests/test_channels.py`. Expected: FAIL (`ModuleNotFoundError: loadout.channels`).
- [ ] **Step 3: Implement** the Produces list in `cli/loadout/channels.py` (state files through `jsonio.load_json`/`save_json`, git env as in Global Constraints, `timeout=60` for network calls). Add `release-status.json`.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `feat(channels): channel setting, release record and eligibility`.

### Task 2: Daily release check and notices

**Files:**
- Modify: `cli/loadout/maintenance.py` (`session_start` spawn condition; `_maintain`: skip the kit's pull on stable, call the check)
- Modify: `cli/loadout/channels.py`
- Test: `tests/test_channels_maintenance.py`

**Interfaces:**
- Consumes: Task 1 Produces.
- Produces:
  - `channels.check_releases(now: float) -> None`: the daily step. `remote_tags(kit)` → `record_seen` → alarms queued (`loadout: release {tag} was changed after it was released; it is not offered. Tell the maintainer.`). On stable only, also: `release_status`; when the current release is withdrawn, one notice (`loadout: the release you run ({tag}) was withdrawn: {reason}; run loadout update` naming the `use` version when there is one, else `run loadout restore`); else `eligible(...)` → one notice per version via `notified`/`mark_notified`: `loadout {version} is available (since {current}: {up to 3 changelog lines joined by "; "}); run loadout update`.
  - `channels.changelog_lines(root: Path, tag: str, limit: int = 3) -> list[str]`: `git fetch origin tag {tag} --no-tags`, `git show {tag}:CHANGELOG.md`, the bullet lines of that version's `## {version}` section, printable and capped at 120 chars each; `[]` on any failure.
  - `channels.migration_notice() -> None`: with no `channel.json`, queues once (stamp `channel-notice`): `loadout now has release channels: you are on dev (main). For tested releases only: loadout channel stable`.
  - Stamp `last-release-check` (DAY), due independently of `LOADOUT_NO_AUTO_PULL`.
  - `check_releases` stores the last fetched status in `releases.json` (`"status": {"urgent": [...], "withdrawn": {...}}`) and `channels.last_status() -> Status` reads it back (empty when missing), so `loadout check` needs no network.

- [ ] **Step 1: Write the failing tests:**
  - `test_release_check_offline_records_nothing`: `ls-remote` fails → `releases.json` absent, no notice, and the stamp is set (tries again next day).
  - `test_stable_gets_one_notice_per_release`: stable, tag seen 3 days ago, CHANGELOG with 4 bullets → one notice containing `loadout 0.3.0 is available` and 3 bullets; a second `check_releases` adds nothing.
  - `test_dev_records_but_never_notifies`: dev → `releases.json` has the tag, no notice.
  - `test_withdrawn_current_release_notice_names_the_fix`.
  - `test_moved_tag_alarm_is_queued`.
  - `test_stable_daily_pull_skips_kit_but_pulls_personal`: `_maintain` on stable runs `pull` only for the personal root.
  - `test_release_check_runs_with_no_auto_pull`: `LOADOUT_NO_AUTO_PULL=1`, `last-release-check` due → `session_start` spawns, `_maintain` calls `check_releases`, no `git pull`.
  - `test_migration_notice_once`.
- [ ] **Step 2: Run** `uv run --python 3.12 --with pytest pytest -q tests/test_channels_maintenance.py`. Expected: FAIL.
- [ ] **Step 3: Implement.** In `_maintain`, build the pull list without the kit when `channels.effective() == "stable"`; call `migration_notice()` and, when due, `check_releases(now)` inside `try/except Exception` with a `notify` on error, like the other steps.
- [ ] **Step 4: Run** the task's tests plus `tests/test_maintenance.py`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(channels): daily release check with one notice per release`.

### Task 3: Moving the kit checkout, with undo

**Files:**
- Modify: `cli/loadout/channels.py`, `cli/loadout/maintenance.py` (`_refusal`), `cli/loadout/backup.py` (`_allowed_run`)
- Test: `tests/test_channels_move.py`

**Interfaces:**
- Consumes: Task 1.
- Produces:
  - `channels.local_changes(root: Path, base: str) -> list[str]`: files from `git status --porcelain` (tracked changes only; untracked files never block, as git itself would refuse when one is in the way) plus `commit <short sha> <subject>` for each commit in `git rev-list HEAD --not {base}` (base: `--tags` on stable, `origin/main` on dev).
  - `channels.move_to(root: Path, tag: str, bk: Backup) -> str | None`: refusal text or None. Order: `local_changes` (refuse with `local changes: …`) → record the undo with `bk.record_command("kit checkout", [...checkout --detach <old sha>])` → `git fetch origin tag {tag} --no-tags` → `git checkout --detach {tag}`; a failed checkout returns `maintenance._refusal`'s text.
  - `channels.move_to_dev(root: Path, bk: Backup) -> str | None`: refuse on `local_changes(root, "origin/main")`; record the undo; `git switch main` or `git switch -c main --track origin/main`; `git pull --ff-only`.
  - `maintenance._refusal` also recognises `would be overwritten by checkout:`.
  - `backup._allowed_run` accepts `["git", "-C", root, "checkout", "--detach", sha]` only when `Path(root).resolve() == paths.kit_root().resolve()` (compare `os.path.normcase` on Windows) and `sha` is 40 hex characters.

- [ ] **Step 1: Write the failing tests:**
  - `test_move_refuses_local_commits_and_edits`: a porcelain line ` M cli/x.py` → the refusal names `cli/x.py`, no `checkout`, `fetch` or `record_command`; a local commit → named as `commit abc1234 …`.
  - `test_move_records_undo_before_checkout`: call order `rev-parse HEAD`, then the undo recorded, then `fetch`, then `checkout --detach v0.3.0`.
  - `test_checkout_refusal_is_reported`: stderr `error: Your local changes to the following files would be overwritten by checkout:\n\tREADME.md` → refusal names `README.md`.
  - `test_undo_allowlist_matches_kit_root_resolved`: accepted for the kit root (also with a trailing slash or other spelling of the same path); refused for another path, a short sha, `--force` or extra arguments.
  - `test_move_to_dev_creates_main_tracking_origin`.
- [ ] **Step 2: Run** `uv run --python 3.12 --with pytest pytest -q tests/test_channels_move.py`. Expected: FAIL.
- [ ] **Step 3: Implement** the Produces list.
- [ ] **Step 4: Run** the task's tests plus `tests/test_backup*.py tests/test_maintenance.py`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(channels): move the kit checkout to a release, with undo`.

### Task 4: Pin the kit's plugins to the release

**Files:**
- Modify: `cli/loadout/settings_merge.py` (`desired_settings`), `cli/loadout/bootstrap.py:513`, `cli/loadout/profiles.py:123`, `cli/loadout/update.py:83-87,142`, `cli/loadout/adopt.py:433`, `cli/loadout/codex.py` (`_install_routes` source and `remote_head` ref)
- Modify: `cli/loadout/channels.py`
- Test: `tests/test_channels_pins.py`

**Interfaces:**
- Consumes: Task 1 (`effective`, `current_release`, `kit_slug`, `KIT_MARKET`).
- Produces:
  - `channels.pin() -> str | None`: the current release tag on stable, None on dev or when the checkout is on no release.
  - `channels.claude_origin(origin: str) -> str`: `origin + "#" + tag` when `origin` is the kit's slug and `pin()` is set, else `origin` unchanged.
  - `channels.codex_source(src: str) -> str`: `src + "@" + tag` likewise.
  - `desired_settings()`: on stable, the `agent-loadout` entry of `extraKnownMarketplaces` gets `"source": {"source": "github", "repo": kit_slug, "ref": tag}`; on dev it is unchanged (no `ref`). `autoUpdate` stays.
  - Every `claude plugin marketplace add` for the kit marketplace goes through `claude_origin`; every Codex `marketplace add` for it through `codex_source`; `codex.remote_head(url, ref)` gets the pin as `ref` for the kit route.

- [ ] **Step 1: Write the failing tests:**
  - `test_stable_settings_pin_the_kit_marketplace`: stable on `v0.3.0` → `desired_settings()["extraKnownMarketplaces"]["agent-loadout"]["source"]["ref"] == "v0.3.0"`; the other three marketplaces have no `ref`.
  - `test_dev_settings_have_no_ref`.
  - `test_claude_marketplace_add_passes_the_tag`: bootstrap's marketplace step on stable runs `["claude", "plugin", "marketplace", "add", "jonasyr/agent-loadout#v0.3.0"]`; `claude-plugins-official` is unchanged.
  - `test_codex_add_passes_the_tag_and_head_checks_it`: `_install_routes` on stable runs `marketplace add jonasyr/agent-loadout@v0.3.0 --json` and `remote_head(url, "v0.3.0")`.
  - `test_codex_off_touches_no_codex_config` and `test_claude_off_runs_no_claude_marketplace_add` on stable.
- [ ] **Step 2: Run** `uv run --python 3.12 --with pytest pytest -q tests/test_channels_pins.py`. Expected: FAIL.
- [ ] **Step 3: Implement.** `_table_blockers` (fixed in #80) then passes because the source ends with `@{ref}`.
- [ ] **Step 4: Run** the task's tests plus `tests/test_settings_merge*.py tests/test_codex*.py tests/test_profiles*.py tests/test_update*.py`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(channels): pin the kit's Claude Code and Codex marketplaces to the release`.

### Task 5: `loadout update` on stable and `loadout channel`

**Files:**
- Modify: `cli/loadout/update.py` (`run`, `_pull`, `_after_restart`, plan), `cli/loadout/commands.py`, `cli/loadout/__main__.py` (parser)
- Modify: `cli/loadout/channels.py`
- Test: `tests/test_channels_update.py`

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces:
  - In `update._pull`, on stable the kit is not pulled; instead `channels.eligible(...)` (after `remote_tags` + `record_seen` + `release_status`) gives the target. A `PlanItem` `kit: {current} → {tag}` with its changelog lines is shown under the existing yes rules (`--yes`, or the question). On yes: `Backup(description="loadout update: kit to {tag}")`, `move_to`; a refusal goes to `summary.failed` with the fix `commit or remove them in {root}, then run loadout update`; success sets `PULLED = "release:{tag}"` and restarts through `_exec`; `_after_restart` adds `kit: moved to {tag} (this run continued in it)` and re-applies as after a pull (Claude settings carry the new pin; then `claude plugin marketplace update agent-loadout` and the existing plugin refresh; Codex `apply_all(refresh=True)`).
  - A detached kit on a release is never listed as `not refreshed (detached HEAD)` on stable.
  - `commands.channel(target: str | None) -> int`: no argument prints `stable, v0.3.0` / `dev, main` (exit 0). `stable`: refuse unless the kit is a git checkout; pick `eligible(...)`, else the newest tag ≥ floor whose tagger date (`git for-each-ref --format=%(taggerdate:unix)`) is ≥ 3 days old, else print `no release is ready yet; you stay on dev` (exit 1); show the plan and ask (or `--yes`); `move_to`; `set_channel("stable", bk)`; continue in the new code with `update --yes`-style re-apply. `dev`: `move_to_dev`, `set_channel("dev", bk)`, re-apply. The setting is written only after the move succeeded; one `Backup` holds the undo, the copy of `channel.json` and the re-apply's backups.
  - Parser: `loadout channel [stable|dev] [--yes]`.

- [ ] **Step 1: Write the failing tests:**
  - `test_update_on_stable_moves_to_the_eligible_release_and_restarts`.
  - `test_update_on_stable_without_a_release_changes_nothing_and_lists_no_failure`.
  - `test_update_refusal_names_local_changes_and_keeps_the_pin`.
  - `test_channel_without_argument_prints_state`.
  - `test_channel_stable_with_no_ready_release_stays_dev` (exit 1, no `channel.json`).
  - `test_channel_stable_falls_back_to_tagger_date_once`.
  - `test_channel_dev_from_stable_refuses_local_commits`.
  - `test_restore_after_channel_switch_puts_the_old_checkout_and_setting_back` (restore replays the allowlisted checkout and restores `channel.json`).
- [ ] **Step 2: Run** `uv run --python 3.12 --with pytest pytest -q tests/test_channels_update.py`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the task's tests plus `tests/test_update*.py tests/test_cli*.py`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(channels): loadout update follows releases on stable; loadout channel`.

### Task 6: `loadout check` rows and `--version`

**Files:**
- Modify: `cli/loadout/check.py` (`_repos` or a new `_channel` row next to it), `cli/loadout/__main__.py` (`kit_version`)
- Test: `tests/test_channels_check.py`, `tests/test_version.py`

**Interfaces:**
- Consumes: Tasks 1–2 (`effective`, `current_release`, `releases.json` moved flags, `last_status`, `eligible`).
- Produces:
  - Check row `Channel`: ok `stable, v0.3.0` / `dev, main`; warn `stable, v0.3.0: v0.4.0 is available` (fix `loadout update`); warn `stable, v0.3.0 was withdrawn: {reason}` (fix `loadout update` or `loadout restore`); warn `release {tag} was changed after it was released` (fix: tell the maintainer). The row reads only local state (no network).
  - `kit_version()`: `loadout 0.3.0 (stable, v0.3.0)` when HEAD is exactly a release tag; `loadout 0.3.0 (dev, abc1234)` otherwise.

- [ ] **Step 1: Write the failing tests** for each row text above and both version forms.
- [ ] **Step 2: Run** `uv run --python 3.12 --with pytest pytest -q tests/test_channels_check.py tests/test_version.py`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the same plus `tests/test_check*.py`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(channels): channel row in check, channel in --version`.

### Task 7: Bootstrap installs a release

**Files:**
- Modify: `bootstrap.sh`, `bootstrap.ps1`, `cli/loadout/bootstrap.py`, `cli/loadout/__main__.py` (`--channel`)
- Test: `tests/test_entry_scripts.py`, `tests/test_bootstrap_channel.py`

**Interfaces:**
- Consumes: Tasks 1, 3, 5.
- Produces:
  - Both scripts take `--channel dev|stable` (default stable) and pass it on. With `LOADOUT_REF` set the scripts check out that ref (tests and forks). Otherwise on stable, after the clone: the newest annotated tag matching `v<major>.<minor>.<patch>` at or above `0.2.0` whose tagger date is ≥ 3 days old (`git for-each-ref --sort=-v:refname --format='%(refname:short) %(objecttype) %(taggerdate:unix)' refs/tags`); none → print `no stable release is ready yet; wait a few days, or install dev: … --channel dev` and exit 1, never falling back to `main`. On dev: `main`. The same rule applies to an existing clone the scripts reuse only when it has no commits ahead of the chosen tag (else they leave it as it is and say so).
  - `bootstrap.run(..., channel: str = "stable")`: seeds `releases.json` with every current remote tag as first seen now (`record_seen`), writes `channel.json` (`set_channel` into the run's backup), on stable reads `release_status` and, if the checked-out release is withdrawn and its `use` is a tag, `move_to` it and continue in it.
- [ ] **Step 1: Write the failing tests:**
  - `test_sh_picks_newest_soaked_annotated_tag` (local bare repo with `v0.1.0` lightweight, `v0.2.0` annotated 5 days old, `v0.3.0` annotated now → checks out `v0.2.0`; tag dates via `GIT_COMMITTER_DATE`).
  - `test_sh_stops_when_no_release_is_ready` (exit 1, message, no `main` checkout).
  - `test_sh_channel_dev_checks_out_main`.
  - `test_ps1_tag_pick_matches_sh` (skipped where `pwsh` is missing, as the existing ps1 tests are).
  - `test_bootstrap_writes_channel_and_seeds_releases`.
  - `test_bootstrap_moves_off_a_withdrawn_release`.
- [ ] **Step 2: Run** `uv run --python 3.12 --with pytest pytest -q tests/test_entry_scripts.py tests/test_bootstrap_channel.py`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the same plus `tests/test_bootstrap*.py`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(bootstrap): install the newest soaked release; --channel dev for main`.

### Task 8: `loadout release` (maintainer)

**Files:**
- Create: `cli/loadout/release.py`, `CHANGELOG.md` (header `# Changelog` only)
- Modify: `cli/loadout/__main__.py` (parser; the command is hidden from the short help like `maintenance`)
- Test: `tests/test_release.py`

**Interfaces:**
- Consumes: Task 1 (`parse_tag`, `FLOOR`).
- Produces:
  - `release.cut(version: str, urgent: bool, yes: bool, edit: bool, ask) -> int`. Refusals (exit 1, one line each): not run from the kit checkout; branch is not `main`; working tree not clean; HEAD differs from `origin/main` after `git fetch origin main`; `version` not `X.Y.Z` or `<= newest tag` or `< FLOOR`; `gh` missing or `gh auth status` fails; newest `ci.yml` run for HEAD (`gh run list --commit <sha> --workflow ci.yml --limit 1 --json conclusion,status`) not `completed`/`success`. Then a plan, and on yes: set `version = "X.Y.Z"` in `pyproject.toml`; prepend `## X.Y.Z (YYYY-MM-DD)` with bullets from `git log v<prev>..HEAD --format=%s` filtered to `feat`, `fix` and `!` subjects (`--edit` opens `$EDITOR` on the section first); with `urgent` add `"X.Y.Z"` to `release-status.json` `urgent`; refuse if the staged diff touches anything but `pyproject.toml`, `CHANGELOG.md`, `release-status.json`; commit `chore(release): vX.Y.Z`; `git tag -a vX.Y.Z -m "loadout X.Y.Z"`; `git push origin main vX.Y.Z`; `gh release create vX.Y.Z --title "loadout X.Y.Z" --notes-file <section file> bootstrap.sh bootstrap.ps1`.
  - `release.withdraw(version: str, reason: str, use: str | None, yes: bool, ask) -> int`: same checkout/clean/`main` refusals; `use` must name an existing tag newer than `version`; adds `{"version", "reason", "use"}` to `withdrawn`; commit `chore(release): withdraw vX.Y.Z`; push.
  - Parser: `loadout release X.Y.Z [--urgent] [--edit] [--yes]`, `loadout release withdraw X.Y.Z --reason TEXT [--use A.B.C] [--yes]`.
- [ ] **Step 1: Write the failing tests:** one per refusal above; `test_cut_writes_version_changelog_and_tags_in_order` (exact call order of commit, tag, push, gh release); `test_urgent_lists_the_version`; `test_cut_refuses_a_diff_outside_release_files`; `test_withdraw_requires_an_existing_newer_use`.
- [ ] **Step 2: Run** `uv run --python 3.12 --with pytest pytest -q tests/test_release.py`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the same. Expected: PASS.
- [ ] **Step 5: Commit** `feat(release): loadout release and release withdraw`.

### Task 9: Docs

**Files:**
- Create: `docs/adr/0046-release-channels.md`
- Modify: `docs/adr/README.md`, `AGENTS.md` (ADR range `0001-0046`), `docs/reference/state-and-sync.md` ("The daily sync": stable path, release check), `docs/reference/cli.md` (`channel`, `release`, `bootstrap --channel`, env vars incl. `LOADOUT_REF`, `LOADOUT_NO_AUTO_PULL` scope), `docs/reference/personal-layer.md` (machine-local state: `channel.json`, `releases.json`), `docs/explanation/security-and-trust.md` (trust boundary: what stable protects and what not, from the spec's threat model), `README.md` and `docs/tutorials/getting-started.md` (install command `curl -fsSL https://github.com/jonasyr/agent-loadout/releases/latest/download/bootstrap.sh | bash`, the `.ps1` twin, `--channel dev`), `CONTRIBUTING.md` (how to release and withdraw, fix before withdraw), `docs/reference/modules.md` (`channels.py`, `release.py`), `docs/how-to/troubleshooting.md` (no release ready yet; local changes block a move; moved-tag alarm).
- Test: `tests/test_docs_links.py`, `tests/test_docs_commands.py`

- [ ] **Step 1: Write** the pages (one home per fact; others link).
- [ ] **Step 2: Run** `uv run --python 3.12 --with pytest pytest -q tests/test_docs_links.py tests/test_docs_commands.py`. Expected: PASS.
- [ ] **Step 3: Commit** `docs: release channels (ADR 0046)`.

## After the plan (maintainer, not agents)

Merge, then cut `v0.2.0` with `loadout release 0.2.0` yourself (it pushes and creates the GitHub Release). Stable installs work 3 days later; the friend's install waits for that.
