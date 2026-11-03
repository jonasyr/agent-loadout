# First-Install Snapshot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On a machine's first `loadout bootstrap`, offer (default yes) one archive of the person's agent setup before loadout changes anything, and `loadout restore --first-install` puts it all back.

**Architecture:** A new `cli/loadout/snapshot.py` builds a private `tar.gz` of the chosen agents' config (Python `tarfile`, stdlib) in the backups folder and restores it safely (path checks, current state moved into a `pre-restore` backup first). Bootstrap asks once, right after the agent choice and before its first write to an agent folder or startup file. `restore` gets a `--first-install` mode.

**Tech Stack:** Python 3.11 stdlib (`tarfile`, `os`, `stat`), the existing `Backup`/restore machinery, pytest with `fake_home`.

**Spec (approved in chat 2026-11-03):** first install only; asked "Save a snapshot of your current setup first?" default yes, with its size; `--snapshot`/`--no-snapshot` answer it; with `--yes` or no terminal the snapshot is taken. Contents: config only. Login data included, file private. Rollback: `loadout restore --first-install` shows what goes back, asks, moves what is there now into a pre-restore backup, then unpacks; installed tools stay.

## Global Constraints

- Stdlib only. Tests use `fake_home`; never the real `~/.claude`, `~/.claude.json`, `~/.codex`, `~/.config/loadout`.
- **First install** = no `paths.state_dir()` folder yet and no `first-install` snapshot recorded. Re-runs never ask again.
- **Agent-off (P1):** only the agents chosen in this bootstrap are read: Claude Code → `~/.claude`, `~/.claude.json`; Codex → `paths.codex_home()`. Shell startup files (`~/.bashrc`, `~/.zshrc`, `~/.profile`, `~/.bash_profile`, `~/.zprofile`, `~/.config/fish/config.fish`, `~/.config/fish/conf.d/`, and on Windows the PowerShell profile paths bootstrap writes) and VS Code user `settings.json` (the paths `vscode.py` uses) belong to neither agent and are always included when present.
- **Left out (config only):** under `~/.claude`: `projects/`, `cache/`, `plugins/cache/`, `plugins/marketplaces/`, `shell-snapshots/`, `todos/`, `statsig/`, `telemetry/`, `debug/`, `file-history/`, `ide/`, `session-env/`, `local/`, `downloads/`, `backups/`; under the Codex home: `sessions/`, `archived_sessions/`, `log/`, `logs/`, `cache/`, `.tmp/`, `tmp/`, `plugins/cache/`; any symlink is stored as a link (never followed); sockets/devices skipped; single files over 50 MB skipped with a line naming them.
- **Login data is included** (`~/.claude.json`, `~/.codex/auth.json`). Archive at `paths.backups_root()/first-install-<YYYYMMDD-HHMMSS>.tar.gz`, mode 0600 (folder 0700 as other backups), with a `snapshot.json` inside listing roots, agents, created time and loadout version.
- **Restore safety (P1):** extract only members whose normalised path stays inside one of the recorded roots under `HOME` (no absolute paths, no `..`, no link pointing outside HOME for hard links; symlinks restored as links), regular files/dirs/symlinks only; everything it would replace is moved into a `Backup(description="pre-restore first-install")` first; a failure mid-way reports and leaves the pre-restore backup.
- Undo rules: the snapshot is the undo; restore of the snapshot is itself undoable (pre-restore backup).
- Conventional Commits, no AI attribution.

## Review Focus

1. **A crafted or damaged archive** (member `../../etc/x`, absolute path, hard link to `/etc/passwd`, a device): refused member by member, nothing written outside HOME. Test in Task 1: `test_restore_refuses_members_outside_home`.
2. **Codex off / Claude Code off** at the first install: the off agent's folder is never read. Test in Task 2: `test_codex_off_snapshot_never_reads_codex_home`.
3. **Big `~/.claude`** (GBs of transcripts): excluded folders are never walked into (not just skipped at write time); size shown in the question. Test in Task 1: `test_excluded_folders_are_not_walked`.
4. **Disk full / unwritable backups folder:** bootstrap says the snapshot failed and asks whether to continue (default no in a terminal; with `--yes` it stops), nothing changed yet. Test in Task 2: `test_failed_snapshot_stops_before_changes`.
5. **Windows paths and file modes:** archive names use forward slashes; restore maps them back; 0600 set via `os.chmod` (no effect on Windows is fine). Test in Task 1: `test_member_names_are_posix`.

---

### Task 1: `snapshot.py`: build and restore

**Files:** Create `cli/loadout/snapshot.py`; Test `tests/test_snapshot.py`.

**Interfaces — Produces:**
- `roots(agents: dict[str, bool]) -> list[Path]`: the existing paths to include, per the Global Constraints.
- `estimate(roots: list[Path]) -> int`: bytes that would be archived (walks with the exclusions; never enters excluded folders).
- `create(roots: list[Path], agents: dict[str, bool]) -> Path`: writes the archive, returns its path; raises `OSError` on failure (partial archive removed).
- `latest() -> Path | None`: the newest `first-install-*.tar.gz` in the backups root.
- `contents(archive: Path) -> list[str]`: the HOME-relative member names that would be restored (after the safety checks), for the preview.
- `restore(archive: Path) -> tuple[list[str], bool, Path | None]`: same shape as `backup.restore` (lines, ok, pre-restore backup root).
- [ ] **Step 1: Write the failing tests:** `test_roots_follow_agents_and_include_shell_files`, `test_excluded_folders_are_not_walked` (a huge `projects/` tree is never listed: monkeypatch `os.scandir`/count), `test_create_is_private_and_lists_roots` (0600 on POSIX, `snapshot.json` present), `test_symlinks_stored_as_links`, `test_big_file_skipped_with_a_line`, `test_member_names_are_posix`, `test_restore_puts_files_back_and_moves_current_aside` (current files land in the pre-restore backup; restored bytes equal the originals), `test_restore_refuses_members_outside_home` (`../`, absolute, hard link outside, device), `test_restore_of_a_missing_or_corrupt_archive_says_so`.
- [ ] **Step 2: Run** `uv run --python 3.12 --with pytest pytest -q tests/test_snapshot.py`. Expected: FAIL (no module).
- [ ] **Step 3: Implement.** Use `tarfile.open(..., "w:gz")` with `add(..., recursive=False)` per entry from your own walk (so exclusions prune the walk); on Python ≥ 3.12 pass `filter="data"` on extraction and additionally keep the manual checks (3.11 has no filter).
- [ ] **Step 4: Run** the tests, then the full suite. Expected: PASS.
- [ ] **Step 5: Commit** `feat(snapshot): archive the agent setup and put it back safely`.

### Task 2: Bootstrap asks; `restore --first-install`

**Files:** Modify `cli/loadout/bootstrap.py` (the question right after the agent choice in `_bootstrap`, before the first write to an agent folder or startup file — verify no earlier step writes there), `cli/loadout/commands.py` (bootstrap `--snapshot/--no-snapshot`; restore `--first-install`), `bootstrap.sh`/`bootstrap.ps1` only if they must forward the flags (they forward unknown args already — check); Test `tests/test_bootstrap_snapshot.py`, `tests/test_restore_first_install.py`.

**Interfaces:** Consumes Task 1. Produces: question text `Save a snapshot of your current setup first (<size>, into <path>)? [Y/n] `; on success the line `snapshot: <path> (undo everything: loadout restore --first-install)`, and the same line in bootstrap's final summary next to the undo line; `loadout restore --first-install [--yes]` previews `contents()` (count plus the first 20 names), asks `Put your setup from <date> back? [y/N]`, prints the restore lines, exits 0 on success, 1 on failure or when there is no snapshot.
- [ ] **Step 1: Write the failing tests:** `test_first_install_asks_and_snapshots`, `test_rerun_never_asks`, `test_no_snapshot_flag_skips`, `test_yes_and_no_terminal_take_the_snapshot`, `test_codex_off_snapshot_never_reads_codex_home`, `test_snapshot_runs_before_any_agent_file_changes` (call order: archive created before the first write under `~/.claude`/`~/.codex`/startup files), `test_failed_snapshot_stops_before_changes`, `test_restore_first_install_previews_and_asks`, `test_restore_first_install_without_a_snapshot_exits_1`.
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the tests, then the full suite. Expected: PASS.
- [ ] **Step 5: Commit** `feat(bootstrap): offer a snapshot of your setup before the first install; restore --first-install`.

### Task 3: Docs

**Files:** `docs/how-to/undo-and-restore.md` (a "Roll back the first install" section: what the snapshot holds and leaves out, logins included and private, how to delete it, `restore --first-install`; adjust "What restore does not undo"), `docs/reference/cli.md` (bootstrap flags, restore flag), `docs/tutorials/getting-started.md` (one line: the question at first install), `docs/how-to/uninstall.md` (link), `docs/reference/modules.md` (`snapshot.py`), `docs/reference/state-and-sync.md` or `personal-layer.md` where backups are listed.
- [ ] **Step 1: Write** the docs. **Step 2: Run** `uv run --python 3.12 --with pytest pytest -q tests/test_docs_links.py tests/test_docs_commands.py`. Expected: PASS. **Step 3: Commit** `docs: the first-install snapshot`.
