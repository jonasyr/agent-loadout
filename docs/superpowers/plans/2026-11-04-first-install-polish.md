# First-install polish (0.3.0) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Smooth the five rough spots a first-time user (the friend's stable install) can hit, then release 0.3.0.

**Architecture:** Small, independent fixes in the entry scripts, `bootstrap._channel_step`, `snapshot._entries`/`create`, `update` (channel command) and `bootstrap._npm_fix`. No new modules.

**Tech Stack:** bash, PowerShell, Python 3.11 stdlib, pytest.

**Spec:** none written; the design was agreed in chat on 2026-11-04 (group A of the 0.3.0 scope; item 1 = "Pull dev, note stable"). Sources: `.superpowers/handoff/2026-11-02-install-readiness.md` item 9, and the deferred minors in the 2026-11-03 channels and snapshot ledgers.

## Global Constraints

- Python 3.11+, standard library only in `cli/loadout/`; external commands only via `runner.run` with argument lists.
- Tests use `fake_home`/`fake_runner`; entry-script tests use the stub `env` fixture. Set `XDG_STATE_HOME` into tmp, never only `HOME`.
- A reused clone is never moved to another release by the scripts (the move needs loadout's backup and undo); only a fast-forward of `main` is allowed.
- Conventional Commits, no AI attribution.

## Review Focus

1. A reused clone on `main` with local commits, a dirty tree, no upstream, or offline: the pull must not run (dirty) or must fail softly with a warning and setup must go on with the code it has.
2. A reused clone that is detached (stable) or on another branch: no pull at all.
3. An unreadable folder in `~/.claude`: it is listed as skipped, and `restore --first-install` must not move it (or its contents) aside as "added since".
4. A file that becomes unreadable between the walk and `tar.add`: skipped, never a half-written member.
5. The bootstrap re-run note on stable only names a release that `loadout update` would really offer (same `eligible` rule), and says nothing offline.

---

### Task 1: Entry scripts update a reused clone on main; honest checkout error

**Files:**
- Modify: `bootstrap.sh` (the two "using the … clone" branches; the `git checkout "$ref"` failure text)
- Modify: `bootstrap.ps1` (same two branches)
- Test: `tests/test_entry_scripts.py`

Behaviour (both scripts): after "using the clone in …" or "using the existing clone in …", when `LOADOUT_NO_AUTO_PULL` is not `1`, `LOADOUT_REF` is unset, the clone is on branch `main` (`git symbolic-ref -q --short HEAD`), and `git status --porcelain --untracked-files=no` is empty: print `updating the clone (git pull --ff-only)` and run `git -C "$kit" pull -q --ff-only` with `GIT_TERMINAL_PROMPT=0`. On failure print to stderr `could not update the clone in $kit; going on with the code it has (loadout update tries again)` and continue. Detached HEAD, another branch or a dirty tree: no pull, no message.

The dev checkout failure on a fresh clone says `could not check out $ref in $kit` (git's own error is shown above it), as bootstrap.ps1 already does.

- [ ] **Step 1: Write the failing tests**
  - `test_sh_reuse_on_main_pulls_new_commits`: `_release_repo` with `[("v0.2.0", True, 5)]`, first run with `LOADOUT_REF=main`; add a commit to upstream (VERSION = "newer"); second run without `LOADOUT_REF` → returncode 0, `(kit/"VERSION").read_text() == "newer"`, `"updating the clone" in p.stdout`.
  - `test_sh_reuse_dirty_main_is_not_pulled`: as above but write an uncommitted change to a tracked file (`bin/loadout`) before the second run → VERSION still `main`, no "updating" line.
  - `test_sh_reuse_failed_pull_goes_on`: first run, then make upstream diverge (`_git(repo, "commit", "--amend", ...)` after the clone, i.e. rewrite main) → returncode 0, `"could not update the clone" in p.stderr`, bootstrap still runs (log has `bin/loadout bootstrap`).
  - `test_sh_reuse_no_auto_pull_skips`: `LOADOUT_NO_AUTO_PULL=1` on the second run → VERSION unchanged.
  - The existing `test_sh_reuse_leaves_a_clone_where_it_is` (detached at v0.1.0) stays green: no pull on a detached clone.
  - `test_sh_dev_checkout_failure_names_checkout`: `LOADOUT_REF=nope` on a fresh clone → returncode 1, `"could not check out nope" in p.stderr`, `"offline?" not in p.stderr`.
  - `test_ps1_reuse_pulls_main_only` (text test, no pwsh): the reuse block between "using the clone in" and "cloning agent-loadout into" contains `pull -q --ff-only`, `symbolic-ref`, `LOADOUT_NO_AUTO_PULL`, and still no `Get-ReleaseTag`/`checkout`.
- [ ] **Step 2: Run them; expect FAIL** — `uv run --python 3.12 --with pytest pytest -q tests/test_entry_scripts.py`
- [ ] **Step 3: Implement** a `refresh_clone` function in bootstrap.sh and `Update-Clone` in bootstrap.ps1, called from both reuse branches. Adjust `test_ps1_reuse_does_not_move_the_clone` only if its slice now includes the helper's call (it must still contain no `checkout`).
- [ ] **Step 4: Run the file; expect PASS.**
- [ ] **Step 5: Commit** `fix(bootstrap): a re-run updates a reused clone on main; name a failed checkout`

### Task 2: A bootstrap re-run on stable names a newer release

**Files:**
- Modify: `cli/loadout/bootstrap.py` (`_channel_step`)
- Test: `tests/test_bootstrap_channel.py`

Behaviour: on stable with a current release and a readable status, after the withdrawn check, `offer = channels.eligible(channels.parse_tag(current), now, status)`; when it is a tag, `out.problem(f"release {offer} is ready (you run {current}): loadout update moves this kit there")`. Never moves. A withdrawn current release keeps its own notice (and no second line).

- [ ] **Step 1: Failing tests** `test_a_rerun_on_stable_names_a_newer_release` (current v0.2.0, v0.3.0 seen 4 days ago in releases.json and on the remote → the line is printed, HEAD unchanged) and `test_a_rerun_on_the_newest_release_says_nothing` (no "is ready" in output). Use the module's `_kit`/`_releases` helpers and fake_runner patterns of `test_a_current_release_is_not_moved`.
- [ ] **Step 2: Run; FAIL. Step 3: implement. Step 4: run `tests/test_bootstrap_channel.py`; PASS.**
- [ ] **Step 5: Commit** `feat(bootstrap): a re-run on stable names a newer release`

### Task 3: The snapshot skips unreadable files and folders

**Files:**
- Modify: `cli/loadout/snapshot.py` (`_entries`, `create`)
- Test: `tests/test_snapshot.py`, `tests/test_restore_first_install.py`

Behaviour: in `_entries` a `PermissionError` on a folder's `scandir` keeps the folder's own entry (already yielded) and appends its name to a second list `unreadable`; a `PermissionError` on `lstat` appends the path too. In `create`, `tar.add` raising `PermissionError` or `FileNotFoundError` for a regular file skips it (`unreadable` for the first, silently for the second); `tarfile` opens the file before writing the header, so no partial member. `meta["skipped"]` gets `skipped (unreadable): <name>` lines after the size lines; `meta["skipped_names"]` holds both lists, so restore leaves those paths alone. Other OSErrors still fail the snapshot as today. Note: a skipped folder's contents are not in `skipped_names`; restore's walk cannot list an unreadable folder either, and the folder's own entry is in the archive, so it is "covered".

- [ ] **Step 1: Failing tests** (skip on Windows and when running as root: `os.geteuid() == 0`):
  - `test_unreadable_file_is_skipped_and_listed`: a file chmod 000 under the fake `~/.claude` → `create` returns an archive, the member is absent, `snapshot.skipped(archive)` contains `skipped (unreadable): .claude/<name>`.
  - `test_unreadable_folder_is_kept_as_an_entry`: a folder chmod 000 → archive has the folder entry, skipped lists it.
  - `test_restore_leaves_an_unreadable_file_alone` (in test_restore_first_install.py): snapshot with an unreadable file, restore it (chmod back for the assertion) → the file is still in place, not moved aside.
  Restore permissions in a `finally` so pytest can clean tmp.
- [ ] **Step 2: Run; FAIL. Step 3: implement. Step 4: run both files; PASS.**
- [ ] **Step 5: Commit** `fix(snapshot): skip unreadable files and folders instead of failing`

### Task 4: Clearer channel and npm lines

**Files:**
- Modify: `cli/loadout/update.py` (channel command, the `target == "stable" and channels.get() == "stable"` branch)
- Modify: `cli/loadout/bootstrap.py` (`NPM_MISSING_FIX`, `_npm_fix`)
- Test: `tests/test_channels_update.py` (or wherever the `channel` command's "already" output is tested; find with grep), `tests/test_bootstrap.py` (or the file testing `_npm_fix`)

Behaviour:
- `loadout channel stable` when already stable but `current_release` is None prints `channel: stable, but the kit is not on a release; run loadout update to move it to the newest one` and returns 0; on a release the old line stays.
- `_npm_fix` on macOS (`sys.platform == "darwin"`) with returncode 127 returns `NPM_MISSING_FIX_MAC = "fix: {name} needs npm: brew install node (or the installer from nodejs.org), then run this again"`.

- [ ] **Step 1: Failing tests** `test_channel_stable_off_a_release_points_to_update` and `test_npm_missing_on_macos_names_brew` (monkeypatch `sys.platform` to `"darwin"`; Linux keeps the apt line).
- [ ] **Step 2: Run; FAIL. Step 3: implement. Step 4: PASS.**
- [ ] **Step 5: Commit** `fix: point an off-release stable kit to loadout update; macOS npm fix line`

### Task 5: Docs and full suite

**Files:** `docs/reference/cli.md` / `docs/how-to/troubleshooting.md` / `docs/tutorials/getting-started.md` where they describe re-running the one-liner, the snapshot's skipped lines and `loadout channel stable` (only where a sentence became wrong).

- [ ] **Step 1:** grep the docs for "existing clone", "re-run", "skipped (over", "channel stable"; fix what is now wrong.
- [ ] **Step 2:** full suite `uv run --python 3.12 --with pytest pytest -q` → all pass.
- [ ] **Step 3: Commit** `docs: re-running the one-liner updates the clone; unreadable files in the snapshot`
