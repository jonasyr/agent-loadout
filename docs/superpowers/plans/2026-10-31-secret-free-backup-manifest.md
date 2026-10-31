# Secret-free backup manifest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** New backups keep MCP server configs (and their secrets) out of `manifest.json`: the config goes to a 0600 file in the backup's `files/`, and the manifest step only points at it.

**Architecture:** One new `Backup.record_mcp_add` writes the config file and a `run` step with a `config-file` key. One resolver `_resolve_run` turns any `run` step into the full command (loading the config file, with containment and shape checks). `_undo`, `_refused_pairs` and `contents` go through it. The two call sites switch to the new method.

**Tech Stack:** Python 3.11+, standard library only; pytest with `fake_home` / `fake_runner` (and `windows_cmd` from `tests/test_windows_edges.py`).

**Spec:** `docs/superpowers/specs/2026-10-31-secret-free-backup-manifest-design.md`

## Global Constraints

- Standard library only in `cli/loadout/`; external commands only through `runner.run` with argument lists.
- Tests use `fake_home` and `fake_runner`; never the real `~/.claude*`, `~/.codex`, `~/.config/loadout`.
- Restore never removes a server it then cannot re-add.
- Old manifests (inline 7-argument `add-json`) keep restoring unchanged.
- The config file is private: `PRIVATE_FILE` (0600) on POSIX, inside the 0700 backup root.
- Conventional Commits, no AI attribution.
- Test command (full suite): `uv run --python 3.12 --with pytest pytest -q --deselect "tests/test_docs_links.py::test_links_resolve[docs/examples/Niklas_Serena_Config.md]"`

## Review Focus

1. A server name with path characters (`../x`, `a/b`) must not let the config file land outside `files/` → name sanitised in the file name (Task 1 test `test_config_file_name_is_sanitised`).
2. A hand-edited `config-file` pointing at a symlink inside `files/` that leads elsewhere → refused (Task 1 test `test_config_file_symlink_refused`).
3. A legacy backup under `~/.claude/backups` with a `config-file` key → path mapped like `restore-file` (Task 1 test `test_config_file_path_is_mapped_for_legacy_backups`).
4. A `config-file` step whose `run` is not the 6-argument `claude mcp add-json -s user NAME` (e.g. someone adds a 7th argument or another program) → refused, nothing runs (Task 1 test `test_config_file_with_other_command_refused`).
5. `--force` replay after a successful restore → config file still there, add runs again (Task 1 test `test_force_replay_reuses_config_file`).

---

### Task 1: Record and restore a config-file step (`backup.py`)

**Files:**
- Modify: `cli/loadout/backup.py` (`Backup` class: new method after `record_command`; `_mapped`; `_undo` "run" branch; `contents`)
- Test: `tests/test_backup_config_file.py` (new)

**Interfaces:**
- Produces: `Backup.record_mcp_add(self, label: str, name: str, config: dict) -> Path` — writes `json.dumps(config)` to `self._slot(Path(f"mcp-{safe}.json"))` where `safe = re.sub(r"[^A-Za-z0-9._-]", "_", name).strip(".") or "server"`, sets `PRIVATE_FILE`, then `self._add(label, {"run": ["claude", "mcp", "add-json", "-s", "user", name], "config-file": str(dest)})`. File first, step second; returns the file path.
- Produces: `_resolve_run(undo: dict, root: Path) -> tuple[list[str] | None, str | None]` — `(full_cmd, None)` or `(None, reason)`. Without `config-file`: `(undo["run"], None)` unchanged. With it: requires `undo["run"]` to equal `["claude","mcp","add-json","-s","user",NAME]` (6 strings, NAME non-empty and not starting with `-`), the path `_inside(path, root / "files")`, not a symlink, a regular file, content parsing to a `dict`; returns `run + [json.dumps(cfg)]`. Reasons (exact text, used in `failed: {label}: {reason}`): `"its config file is not inside {root}"`, `"its config file {path} is missing"`, `"its config file {path} is not a JSON object"`, `"its config-file step is not a claude mcp add-json command"`.
- `_mapped` also maps a string `config-file` through `_map_legacy`.

- [ ] **Step 1: Write the failing tests** in `tests/test_backup_config_file.py`:
  - `test_record_mcp_add_keeps_secret_out_of_manifest`: record `{"command": "x", "env": {"TOKEN": SECRET}}` for `srv`; `SECRET not in (bk.root / "manifest.json").read_text()`; the returned file contains `SECRET`; on POSIX `stat.S_IMODE(file.stat().st_mode) == 0o600`.
  - `test_restore_runs_add_json_with_exact_config`: after restore, `fake_runner.calls == [["claude","mcp","add-json","-s","user","srv", ANY]]` and `json.loads(calls[0][6]) == cfg`.
  - `test_config_file_outside_files_refused`, `test_config_file_symlink_refused`, `test_config_file_missing_refused`, `test_config_file_not_object_refused` (content `[1]`), `test_config_file_with_other_command_refused`: edit the manifest step accordingly; restore returns `ok is False`, a line starting `failed: `, and `fake_runner.calls == []`.
  - `test_config_file_name_is_sanitised`: name `"../x/y"` → file's parent is `bk.root / "files"`.
  - `test_config_file_path_is_mapped_for_legacy_backups`: build the backup, move its folder under `paths.legacy_backups_root()` path shape as existing legacy tests do (see `tests/` for `_map_legacy` tests), rewrite `config-file` to the legacy path; restore succeeds.
  - `test_force_replay_reuses_config_file`: restore, then `restore(root, force=True)` → two add-json calls, file still present.
  - `test_inline_add_json_still_restores`: `record_command` with the 7-arg inline form → restore calls it unchanged.
  - `test_show_names_config_file_without_secret`: `"\n".join(backup.contents(info))` contains `"add-json -s user srv <config in "` and not `SECRET` (get `info` the way existing `contents` tests do).
- [ ] **Step 2: Run** `uv run --python 3.12 --with pytest pytest -q tests/test_backup_config_file.py` — expected: FAIL (`record_mcp_add` missing).
- [ ] **Step 3: Implement** `record_mcp_add`, `_resolve_run`, the `_mapped` addition, and in `_undo`'s `"run"` branch call `_resolve_run(undo, root or pre.root)` first (reason → `return f"failed: {label}: {reason}"`), then the existing `_allowed_run` / codex / `would_refuse` / `runner.run` path on the full command. In `contents`, a `run` step with `config-file` shows `"run: " + " ".join(run) + f" <config in {_shown(config_file)}>"`.
- [ ] **Step 4: Run** the same command — expected: all PASS; then `uv run --python 3.12 --with pytest pytest -q tests/test_windows_edges.py tests/test_fix_pass_2.py` — PASS.
- [ ] **Step 5: Commit** `git commit -m "fix(backup): keep MCP configs out of the manifest in a private config file"`

### Task 2: Pair safety for config-file steps (`_refused_pairs`)

**Files:**
- Modify: `cli/loadout/backup.py` (`_refused_pairs`)
- Test: `tests/test_backup_config_file.py`

**Interfaces:**
- Consumes: `_resolve_run(undo, root)` from Task 1 (call it on `_mapped(undo)`).
- `_refused_pairs` matches the later `add-json` by `_mcp_target` of the **resolved** command when it resolves, or of `undo["run"]` when it does not. A pair whose add does not resolve: both positions get `f"failed: {{label}}: not run, the paired add-json's config cannot be loaded ({reason})"`. A pair whose resolved add `would_refuse`: unchanged behaviour (manual-commands file with the full resolved pair).

- [ ] **Step 1: Write the failing tests:**
  - `test_pair_with_broken_config_runs_neither`: record `record_mcp_add("s (original)", "s", cfg)` then `record_command("s (remove rewritten)", ["claude","mcp","remove","-s","user","s"])`; delete the config file; restore → `fake_runner.calls == []`, two `failed:` lines, `ok is False`.
  - `test_pair_refused_on_windows_writes_full_commands` (uses `windows_cmd`; import the fixture from `tests/test_windows_edges.py` or move it to `conftest.py` if not shared): same recording with an `env` secret; restore → `fake_runner.calls == []`; `manual-commands.txt` contains `mcp remove -s user s` and the secret; restore lines do not contain the secret.
- [ ] **Step 2: Run** `uv run --python 3.12 --with pytest pytest -q tests/test_backup_config_file.py` — expected: the two new tests FAIL.
- [ ] **Step 3: Implement** the `_refused_pairs` change as in Interfaces.
- [ ] **Step 4: Run** the file plus `tests/test_windows_edges.py` — PASS.
- [ ] **Step 5: Commit** `git commit -m "fix(backup): never run a remove whose paired add-json config cannot be loaded"`

### Task 3: Switch the call sites, docs

**Files:**
- Modify: `cli/loadout/adopt.py` `_apply_mcp` (the `bk.record_command(f"mcp {v.item.name}", undo)` line), `cli/loadout/personal_mcp.py` `replace_user_server` (the `"(original)"` `record_command`)
- Modify: `tests/test_adopt.py::test_secret_fix_undo_removes_then_readds_original` (last assert reads the add call's last argument, unchanged meaning)
- Modify: `docs/how-to/undo-and-restore.md` (line ~30 and the "See what a backup holds" row ~85), `docs/explanation/security-and-trust.md` (line ~78)
- Test: `tests/test_backup_config_file.py`

**Interfaces:**
- Consumes: `Backup.record_mcp_add(label, name, config)` from Task 1. Labels stay `f"mcp {name}"` and `f"mcp {name} (original)"`. The in-memory 7-arg command is still built for `runner.would_refuse` and `_manual` / `write_manual_commands`; `record_mcp_add` is called only after that check passed.

- [ ] **Step 1: Write the failing tests:**
  - `test_adopt_remove_keeps_secret_out_of_manifest`: user server with an env secret in `~/.claude.json` (follow `tests/test_adopt.py` `machine` setup), apply its removal → manifest text has no secret; restore re-adds the exact config.
  - `test_fix_secrets_original_is_in_config_file`: `adopt.fix_secrets` on a finding → manifest has no secret value; restore order is `remove`, then `add-json` with the original config (as parsed JSON).
  - `test_adopt_refused_removal_leaves_no_config_file` (with `windows_cmd`): no file under `bk.root / "files"` named `*mcp-*`, no manifest step for the server, manual-commands written.
- [ ] **Step 2: Run** them — expected: FAIL (secret still in the manifest).
- [ ] **Step 3: Implement** the two call-site switches (`json.loads(cfg)` not needed: pass the dict `v.item.extra.get("config", {})` / `original`).
- [ ] **Step 4: Update docs** in plain words: the manifest of a new backup holds no secret values and is safe to show; MCP server configs and copied files in `files/` can hold secrets (0600); backups made before this change can still carry secrets in the manifest; a restore passes the config to `claude` on the command line for that call.
- [ ] **Step 5: Run** the full suite (Global Constraints command) — expected: all pass.
- [ ] **Step 6: Commit** `git commit -m "fix(adopt): record removed MCP servers through the private config file"` and `docs(restore): the manifest holds no secrets` (one commit is fine if small).
