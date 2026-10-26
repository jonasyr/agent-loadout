# Codex marketplace-timeout workaround Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:**
- When Codex's upgrade of one of loadout's marketplaces times out at 30 s, `loadout update` removes the marketplace and adds it again, with a backup, a rollback, and never while Codex runs.
- `loadout check` warns when Codex's staging folder grows past 1 GB.

**Architecture:**
- **Running-Codex probe:** a small helper `codex.codex_running()`.
- **Re-add step:** `codex._readd(...)`, called from `_install_routes` where the upgrade result is handled today.
- **Check row:** a read-only row in `check.py` with a bounded size walk.

**Tech Stack:** Python 3.11+, standard library only; pytest with `fake_home` and `fake_runner`.

**Spec:** `docs/superpowers/specs/2026-10-25-codex-marketplace-timeout-design.md`

## Global Constraints

- Standard library only in `cli/loadout/`. External commands only through `runner.run` with argument lists and a timeout.
- Tests use `fake_home` and `fake_runner`. No test reads the real `/proc`, `~/.codex`, or runs a real `codex`, `ps` or `tasklist`.
- Re-add happens only for marketplaces in the routes `_install_routes` walks. A Codex turned off in `targets.json` is never reached (already true for `apply_plugins`).
- Output copy (exact):
  - Success: `marketplace <market>: Codex's upgrade timed out after 30s; removed and added it again (openai/codex#38770)`
  - Codex running: `marketplace <market>: Codex's upgrade timed out after 30s; quit Codex and run loadout update again to re-add it (openai/codex#38770)`
  - Cannot tell whether Codex runs: the same line with `could not tell whether Codex runs; ` placed before `quit Codex`.
  - Table not reproducible: today's line `marketplace <market>: failed to upgrade (<tail>); its installed plugins stay at the previous version`, followed by `; loadout did not re-add it because your table sets <keys>`, where `<keys>` are comma-joined and sorted.
  - Re-add failed: today's line, followed by `; re-adding it failed too (<tail>)`.
- Check row name `Codex marketplace staging`; threshold 1 GB (`1 << 30` bytes). Fix text: `quit Codex, then empty that folder (abandoned clones of failed marketplace upgrades, openai/codex#39421)`.
- Conventional Commits; no AI attribution.
- Full suite: `uv run --python 3.12 --with pytest pytest -q --deselect "tests/test_docs_links.py::test_links_resolve[docs/examples/Niklas_Serena_Config.md]"`.

## Review Focus

1. **A running Codex rewrote `config.toml` during a failed re-add** (the table is back, under other bytes). The rollback must not overwrite it. Test: `test_rollback_leaves_a_config_that_has_the_table_again` (Task 2).
2. **The snapshot folder is missing before the re-add** (Codex never cloned it, or the user deleted it). The re-add still runs, nothing is moved, and rollback has nothing to put back. Test: `test_readd_without_a_snapshot_folder` (Task 2).
3. **loadout's own runner timeout (exit 124) on the upgrade** must not count as Codex's 30 s timeout. It keeps today's line and triggers no re-add. Test: `test_loadout_runner_timeout_is_not_codex_timeout` (Task 2).
4. **A huge or unreadable staging folder** (permission error on a subfolder, symlink loop) must neither crash nor slow down `check`. Test: `test_staging_walk_stops_at_the_threshold_and_survives_errors` (Task 3).
5. **The daily sync (`auto=True`) with a frozen marketplace** never reaches the re-add. Test: `test_frozen_marketplace_is_never_readded` (Task 2).

---

### Task 1: `codex_running()` probe, and sequences in FakeRunner

**Files:**
- Modify: `cli/loadout/codex.py` (new helper near `program()`)
- Modify: `tests/conftest.py` (`FakeRunner.__call__`: a response value that is a `list` is consumed in order, and its last item repeats)
- Test: `tests/test_codex_running.py`

**Interfaces:**
- Produces:
  - `codex.PROC: Path = Path("/proc")`, which tests can monkeypatch.
  - `codex.codex_running(platform: str | None = None) -> bool | None`. `platform` defaults to `sys.platform`; `None` means it could not tell.
  - `FakeRunner` list responses.

The match rule: the basename of the program, lower-cased, is `codex` or `codex.exe`.

| Platform | Source | Rule |
|---|---|---|
| Linux (`linux*`) | every numeric `PROC/<pid>/comm`, plus the first NUL-separated field of `cmdline` (its basename) | an unreadable single pid is skipped; `PROC` itself missing or unreadable → `None` |
| `darwin` | `ps -A -o comm=`, timeout 10 | the command failing → `None` |
| `win32` | `tasklist /FO CSV /NH`, timeout 10 | the first CSV field; the command failing → `None` |
| anything else | — | `None` |

- [ ] **Step 1: Write the failing tests** in `tests/test_codex_running.py`:
  - `test_linux_finds_codex_by_comm`: `tmp_path/123/comm` = `"codex\n"`, `PROC` patched to `tmp_path`, so `codex_running("linux") is True`.
  - `test_linux_finds_codex_by_cmdline_path`: `comm` = `"node"`, `cmdline` = `b"/opt/x/codex\x00app-server\x00"`, so the result is `True`.
  - `test_linux_ignores_lookalikes`: the comms `codex-reviewer`, `mycodex` and cmdline `/home/u/codex-stuff/run` give `False`.
  - `test_linux_without_proc_cannot_tell`: `PROC` = `tmp_path/"nope"`, so the result is `None`.
  - `test_mac_and_windows_use_runner`: with `fake_runner.responses[("ps", "-A", "-o", "comm=")] = Result(0, "/usr/sbin/cron\n/Applications/Codex.app/Contents/MacOS/Codex\n", "")`, `codex_running("darwin") is True`. With `fake_runner.responses[("tasklist",)] = Result(0, '"explorer.exe","1"\n"codex.exe","2"\n', "")`, `codex_running("win32") is True`. A `Result(1, "", "x")` gives `None`.
  - `test_fake_runner_list_responses_are_consumed_in_order`: the key gets `[Result(1,..), Result(0,..)]`. The first call returns 1, the second 0, and a third also 0.
- [ ] **Step 2: Run** `uv run --python 3.12 --with pytest pytest -q tests/test_codex_running.py`. Expected: FAIL (`codex_running` is missing; the list response is returned as the list itself).
- [ ] **Step 3: Implement** the list handling in `FakeRunner.__call__`: pop from the front while more than one item is left. Then implement `codex_running` as the table above says.
- [ ] **Step 4: Run** the same command. Expected: PASS. Then run the full suite. Expected: all pass.
- [ ] **Step 5: Commit** with `feat(codex): tell whether Codex is running`.

### Task 2: re-add after Codex's upgrade timeout

**Files:**
- Modify: `cli/loadout/codex.py`: `_upgrade`, `_install_routes`, and the new helpers `_codex_timed_out`, `_table_blockers` and `_readd`
- Test: `tests/test_codex_marketplace_readd.py` (reuse the patterns of `tests/test_codex_plugins.py`: `_fake`, `SETTINGS`, `settings_merge.desired_settings` monkeypatch)

**Interfaces:**
- Consumes: from Task 1, `codex_running()` and the FakeRunner list responses.
- Produces:
  - `_codex_timed_out(res: runner.Result) -> bool`. True when `not res.ok`, `res.returncode != 124`, and the lower-cased `stderr + stdout` contains `timed out after` together with either `git clone` or `marketplace`.
  - `_table_blockers(market: str, src: str) -> list[str]`. It reads `paths.codex_home()/"config.toml"` with `tomllib`, takes `[marketplaces.<market>]` and returns the sorted keys among `ref_name` and `sparse_paths` that an add of `src` would not write:
    - `sparse_paths`: a non-empty value is a blocker.
    - `ref_name`: a value is a blocker unless `src` ends in `@<that ref>`.

    A missing or unparsable file, or a missing table, returns `[]`.
  - `_readd(exe: str, src: str, market: str, bk) -> tuple[bool, str]`. It returns (ok, a detail for the line), as specified in Step 3.
- `_upgrade` returns at once (no retry) when `_codex_timed_out(res)`.

- [ ] **Step 1: Write the failing tests.** Every test monkeypatches `codex.codex_running` unless it says otherwise.

  Each test uses this setup:
  - impeccable is `alreadyAdded: True` and installed;
  - `refresh=True`;
  - the upgrade response is `Result(1, "", "Error: Failed to upgrade marketplace `impeccable`: git clone marketplace source timed out after 30s")`;
  - `fake_home/.codex/config.toml` holds `[marketplaces.impeccable]` with `source_type = "git"` and `source = "https://github.com/pbakaus/impeccable.git"`;
  - `fake_home/.codex/.tmp/marketplaces/impeccable/x` exists.

  The tests:
  - `test_codex_timeout_readds_and_reinstalls`:
    - the calls contain, in order: `marketplace upgrade impeccable` exactly once (no retry), `marketplace remove impeccable`, `marketplace add pbakaus/impeccable --json`, `plugin add impeccable@impeccable --json`;
    - the success line is in `lines`;
    - `bk.steps` has a `restore-file` step for `config.toml`;
    - the moved-aside snapshot no longer exists in the backup folder.
  - `test_no_readd_while_codex_runs`: `codex_running` returns `True`. There is no `remove` call, the line equals the Codex-running copy, and there is no `plugin add impeccable@impeccable`.
  - `test_cannot_tell_counts_as_running`: `None`. The line contains `could not tell whether Codex runs; quit Codex`, and there is no `remove`.
  - `test_table_with_sparse_paths_is_not_readded`: the table adds `sparse_paths = ["plugins"]`. There is no `remove`, and the line ends with `; loadout did not re-add it because your table sets sparse_paths`.
  - `test_failed_readd_rolls_back`:
    - the add key gets a list: the first add returns the alreadyAdded JSON, the second `Result(1, "", "boom")`;
    - the test simulates Codex's remove by giving `("codex","plugin","marketplace","remove")` a response, and monkeypatches `runner.run` through `fake_runner`, so that the call deletes the `[marketplaces.impeccable]` table from the file;
    - afterwards the file bytes equal the originals, `snapshot/x` exists again, and the line ends with `; re-adding it failed too (boom)`.
  - `test_rollback_leaves_a_config_that_has_the_table_again`: as above, but the file holds the table again, with other bytes, when the add fails. The file keeps those other bytes.
  - `test_readd_without_a_snapshot_folder`: no snapshot folder. The re-add succeeds and nothing is moved.
  - `test_loadout_runner_timeout_is_not_codex_timeout`: the upgrade returns `Result(124, "", "codex: timed out after 1800s")`. There is no `remove`, today's failure line stays, and `upgrade` was called once.
  - `test_other_upgrade_failure_keeps_todays_behaviour`: `Result(1, "", "network down")`. `upgrade` is called twice (the retry), there is no `remove`, and today's line stays.
  - `test_frozen_marketplace_is_never_readded`: `auto=True` with `_frozen_settings()` (copy the shape from `test_codex_plugins.py`). There is no `upgrade` and no `remove` for impeccable.
  - `test_codex_timed_out_and_table_blockers_units`: direct cases.
    - `_codex_timed_out`: exit 124 gives False; `ok` gives False; Codex's text gives True.
    - `_table_blockers("impeccable", "pbakaus/impeccable")` gives `["ref_name"]` for `ref_name = "v2"`, and `[]` for `src` `pbakaus/impeccable@v2` with the same table.
- [ ] **Step 2: Run** `uv run --python 3.12 --with pytest pytest -q tests/test_codex_marketplace_readd.py`. Expected: FAIL (missing helpers; no remove call).
- [ ] **Step 3: Implement.**
  - `_upgrade`: add `or _codex_timed_out(res)` to the early return.
  - In `_install_routes`, when `stale` and `_codex_timed_out(up)`:
    - `_table_blockers` non-empty: today's line plus the blocker suffix.
    - Otherwise check `codex_running()`. `True` or `None` gives the running line (with the `could not tell` variant for `None`), and the route stays stale.
    - Otherwise call `_readd`. On ok, set `refreshed, stale = True, False` and use the success line instead of today's line. On failure, today's line plus the failure suffix.

  `_readd` steps:
  1. `bk.save_copy(config.toml, "codex config before re-adding <market>")` when the file exists.
  2. Move the snapshot `paths.codex_home()/".tmp/marketplaces"/market` with `bk.move(..., "codex marketplace snapshot <market>")` when it exists.
  3. `_keep_lock()`, then run `[exe, "plugin", "marketplace", "remove", market]` with timeout 120.
  4. `_keep_lock()`, then run `[exe, "plugin", "marketplace", "add", src, "--json"]` with timeout `CLONE_TIMEOUT`. Success means an ok result whose JSON has `marketplaceName`.

  On success, delete the moved copy (`shutil.rmtree`, errors ignored).

  On failure of remove or add:
  - move the copy back only when the snapshot path does not exist;
  - write the saved config bytes back with `jsonio.write_atomic_bytes` only when the current file lacks the `[marketplaces.<market>]` table (parse with `tomllib`; a file that does not parse counts as lacking it);
  - return `(False, _tail(res))`.
- [ ] **Step 4: Run** the same command. Expected: PASS. Then `tests/test_codex_plugins.py`, then the full suite. Expected: all pass.
- [ ] **Step 5: Commit** with `fix(codex): re-add a marketplace whose upgrade hit Codex's 30s timeout`.

### Task 3: `Codex marketplace staging` check row

**Files:**
- Modify: `cli/loadout/check.py`: add the row where the other Codex rows are built (`_codex`), only with Codex on.
- Test: `tests/test_check_codex_staging.py`

**Interfaces:**
- Produces:
  - `check.STAGING_WARN_BYTES = 1 << 30`.
  - `check._dir_size_capped(root: Path, cap: int) -> tuple[int, bool]`, which returns (bytes counted, reached cap). It uses an `os.scandir` stack, never follows symlinks, skips `OSError` per entry, and stops as soon as `total >= cap`.

- [ ] **Step 1: Write the failing tests.** The folder is `fake_home/.codex/.tmp/marketplaces/.staging`; Codex is on via `targets.OVERRIDE`.
  - `test_missing_staging_is_ok`: the row has `ok` True and detail `empty`.
  - `test_small_staging_is_ok`: two folders with small files give `ok` True.
  - `test_large_staging_warns`:
    - monkeypatch `check.STAGING_WARN_BYTES = 10`; three folders with 8 bytes each;
    - expect `ok` False, severity `warn`, and a detail starting with `over ` and containing `in 3 folders in ~/.codex/.tmp/marketplaces/.staging`;
    - `fix` equals the constraint's copy.
  - `test_staging_walk_stops_at_the_threshold_and_survives_errors`: `_dir_size_capped` on a tree with a symlink loop and a `chmod 000` subfolder (skip on Windows or as root). It returns without raising, and `reached` is True once the cap is hit.
  - `test_no_row_with_codex_off`.
- [ ] **Step 2: Run** `uv run --python 3.12 --with pytest pytest -q tests/test_check_codex_staging.py`. Expected: FAIL (no row).
- [ ] **Step 3: Implement** the row. Detail strings:
  - under the cap: the human size (reuse any size formatter in `check.py`, else MB with one decimal);
  - over the cap: `over 1 GB in <n> folders in ~/.codex/.tmp/marketplaces/.staging`, with `<n>` the top-level entries.
- [ ] **Step 4: Run** the same command, then the full suite. Expected: all pass.
- [ ] **Step 5: Commit** with `feat(check): warn when Codex's marketplace staging folder grows`.

### Task 4: docs

**Files:**
- Create: `docs/adr/0042-readd-codex-marketplace-after-upgrade-timeout.md`, in the format of ADR 0041. It records:
  - the trigger;
  - the scope (loadout's marketplaces only);
  - not while Codex runs, and "cannot tell" counts as running;
  - the backup and rollback rules;
  - why the old snapshot is not kept;
  - the links to openai/codex#38770 and #39421;
  - the alternatives: retrying only, a patched timeout, and leaving it to the user.
- Modify:
  - `docs/adr/README.md` (the index);
  - `AGENTS.md` (`decisions 0001-0041` becomes `0001-0042`);
  - `docs/how-to/troubleshooting.md`: one entry, "Codex marketplace upgrade times out / `.staging` is huge", covering what loadout does and the manual fix;
  - the place in `docs/` that lists `loadout check` rows (find it via the `codebase-memory cache folders` mention in `troubleshooting.md`): the new row;
  - `docs/reference/modules.md` only if it lists `codex.py` helpers by name;
  - `.superpowers/handoff/2026-10-13-hardening-backlog.md`: the Codex 30 s timeout BUG becomes DONE with this PR.

- [ ] **Step 1:** Write the docs.
- [ ] **Step 2: Run** `uv run --python 3.12 --with pytest pytest -q tests/test_docs_links.py --deselect "tests/test_docs_links.py::test_links_resolve[docs/examples/Niklas_Serena_Config.md]"`. Expected: PASS.
- [ ] **Step 3: Commit** with `docs: re-adding a Codex marketplace after the 30s upgrade timeout (ADR 0042)`.
