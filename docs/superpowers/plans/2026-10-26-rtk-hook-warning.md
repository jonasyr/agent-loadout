# rtk Hook Warning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Where loadout's plugin provides rtk's Claude Code hook, loadout sets `[hooks] suppress_hook_warning = true` in rtk's `config.toml`, and removes its own line once that no longer holds.

**Architecture:**

- The module `cli/loadout/rtk_config.py` mirrors `codex_hooks.py`:
  - a path;
  - an exact-text record in `paths.state_dir()/"rtk-config.json"`;
  - `apply(bk, dry_run) -> list[str]`.
- `apply.rtk_step` wraps it the way `apply.cbm_step` wraps `cbm.apply_auto_index`.
- `rtk_step` runs wherever `cbm_step` runs (bootstrap, update re-apply, configure, the daily sync), so Codex-only runs remove the key too.

**Tech Stack:** Python 3.11+ standard library (`tomllib`, `re`), pytest with the `fake_home` / `fake_runner` fixtures.

**Spec:** `docs/superpowers/specs/2026-10-26-rtk-hook-warning-design.md`

## Global Constraints

- Standard library only in `cli/loadout/`.
- Tests use `fake_home` and `fake_runner`. They never touch the real `~/.claude`, `~/.codex`, `~/.config/loadout` or rtk's real config, and never run rtk.
- User text stays byte for byte:
  - exact-text record;
  - parse guard (the result parses to the old data plus `hooks.suppress_hook_warning = true`, nothing else);
  - `jsonio.write_atomic`.
- Every change has a backup step first:
  - `bk.save_copy` of the config and of the record;
  - `bk.record_created` for a new file.
- The exact line is `suppress_hook_warning = true`.
- A new file is exactly `[hooks]\nsuppress_hook_warning = true\n`.
- "Wanted" means all of these hold:
  - `targets.claude_enabled()`;
  - `duplicates.plugin_enabled()`;
  - the plugin's hooks include an rtk hook (`duplicates.plugin_guarded_hooks("rtk")` non-empty);
  - `runner.have("rtk")`.
- Commits: Conventional Commits, no AI attribution.
- Test command: `uv run --python 3.12 --with pytest pytest -q --deselect "tests/test_docs_links.py::test_links_resolve[docs/examples/Niklas_Serena_Config.md]"`

## Review Focus

1. **A user `[hooks]` table with comments and other keys (`exclude_commands = [...]`) followed by another table.** The line goes at the end of `[hooks]`, before the next header, and all other bytes are equal. Covered in Task 2 by `test_inserts_into_user_hooks_table_keeping_text`.
2. **The user edits loadout's line (`suppress_hook_warning = true  # mine`) and the plugin is later turned off.** The line stays, it is released, and nothing is written. Covered in Task 2 by `test_edited_line_is_released_not_removed`.
3. **A config that does not end with a newline, or uses CRLF.** The appended table keeps the file's newline style. Covered in Task 2 by `test_crlf_and_missing_final_newline`.
4. **A restore after loadout created the file.** The file is gone, and the next apply creates it again (the record does not claim a file that is gone). Covered in Task 2 by `test_restore_of_created_file_then_apply_again`.
5. **A dotted-keys or inline `hooks`.** Nothing is written, "could not add" is said once, and the run is not flagged as failed twice. Covered in Task 2 by `test_inline_or_dotted_hooks_left_and_said_once`.

---

### Task 1: rtk's config path

**Files:**
- Modify: `cli/loadout/paths.py` (next to `state_dir()`)
- Test: `tests/test_rtk_config.py`

**Interfaces:**
- Produces: `paths.rtk_config() -> Path`

- [ ] **Step 1: Write the failing tests**

```python
def test_rtk_config_path_per_os(fake_home, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux"); monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    assert paths.rtk_config() == fake_home / ".config/rtk/config.toml"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(fake_home / "xdg"))
    assert paths.rtk_config() == fake_home / "xdg/rtk/config.toml"
    monkeypatch.setenv("XDG_CONFIG_HOME", "relative")  # not absolute: ignored, as rtk's dirs crate does
    assert paths.rtk_config() == fake_home / ".config/rtk/config.toml"
    monkeypatch.setattr(sys, "platform", "darwin")
    assert paths.rtk_config() == fake_home / "Library/Application Support/rtk/config.toml"
    monkeypatch.setattr(sys, "platform", "win32"); monkeypatch.setenv("APPDATA", str(fake_home / "AD"))
    assert paths.rtk_config() == fake_home / "AD/rtk/config.toml"
    monkeypatch.delenv("APPDATA")
    assert paths.rtk_config() == fake_home / "AppData/Roaming/rtk/config.toml"
```

- [ ] **Step 2: Run them and see them fail** with `AttributeError: … rtk_config`.

- [ ] **Step 3: Implement `rtk_config()`.** It derives from `home()` and branches on `sys.platform` as in the test. Add a one-line docstring naming `dirs::config_dir()`.

- [ ] **Step 4: Run them; they pass.**

- [ ] **Step 5: Commit** `feat(rtk): locate rtk's config.toml per OS`.

### Task 2: `rtk_config.apply`

**Files:**
- Create: `cli/loadout/rtk_config.py`
- Test: `tests/test_rtk_config.py`

**Interfaces:**
- Consumes: `paths.rtk_config()`.
- Produces:
  - `rtk_config.wanted() -> bool`;
  - `rtk_config.apply(bk, dry_run: bool = False) -> list[str]`, with lines in loadout's apply-line forms;
  - `rtk_config.record_path() -> Path`, which is `paths.state_dir()/"rtk-config.json"`.
- The record holds:
  - `line`: the exact line text written, without the newline;
  - `header`: bool, true when loadout added `[hooks]`;
  - `created`: bool, true when loadout created the file;
  - `said`: a list of once-notices (`"user_false"`, `"unplaceable"`).

**Line wording** (the builder may polish it, but tests pin the key words):

| Case | Line |
|---|---|
| Change | `rtk config.toml: silenced rtk's "No hook installed" warning (loadout's plugin provides the hook)` |
| Dry run | `… to silence …` |
| Removal | `rtk config.toml: removed loadout's suppress_hook_warning (loadout no longer provides rtk's hook)` |
| User's `false` | `rtk config.toml: suppress_hook_warning = false is yours; rtk's "No hook installed" warning stays (left as is)` |
| Unplaceable | `rtk config.toml: could not add suppress_hook_warning to your [hooks]; add it by hand to silence rtk's warning` |
| Does not parse | `skipped rtk config.toml: it does not parse now; left as is` |

For "Does not parse", `apply.refused` must match this line, so the run is flagged.

- [ ] **Step 1: Write the failing tests.**
  - A helper `_wanted(monkeypatch, on=True)` sets the four conditions through `targets.OVERRIDE`, `duplicates.plugin_enabled`, `duplicates.plugin_guarded_hooks` and `fake_runner.have`.
  - Tests, with their assertions:
    - `test_creates_file_when_missing`: content `== "[hooks]\nsuppress_hook_warning = true\n"`; the backup has a `created` step; the record has `created` set to True.
    - `test_inserts_into_user_hooks_table_keeping_text`: input `"# mine\n[hooks]\nexclude_commands = [\"curl\"] # keep\n\n[display]\ncolors = true\n"`. Output equals the input with `suppress_hook_warning = true\n` inserted after the `exclude_commands` line. The blank line and `[display]` are unchanged.
    - `test_appends_table_when_no_hooks`: the input has no newline at the end. A newline is added, then `[hooks]\n…`.
    - `test_crlf_and_missing_final_newline`: a CRLF file gets `\r\n` endings in the inserted lines.
    - `test_user_true_is_left_unrecorded`: no write, no record line.
    - `test_user_false_left_and_said_once`: the first apply has a line with "left as is"; the second apply has no such line; the file is unchanged.
    - `test_inline_or_dotted_hooks_left_and_said_once`: both `hooks = { exclude_commands = [] }` and `hooks.exclude_commands = []` are left unchanged and said once. The line matches `apply.refused` at most on the first run.
    - `test_unparseable_left`.
    - `test_dry_run_writes_nothing`.
    - `test_idempotent`: the second apply returns `[]`.
    - `test_removed_when_not_wanted`: covers loadout's line, its header and its created file. Each one goes only when it matches the record; a file loadout created that equals its own text is deleted.
    - `test_removal_keeps_user_lines_in_shared_hooks_table`.
    - `test_edited_line_is_released_not_removed`.
    - `test_restore_of_created_file_then_apply_again`: `backup.restore(bk.root)`, after which the file is gone. The next apply creates it again.
    - `test_backup_saves_record_and_config_before_write`.
    - `test_not_wanted_and_never_written_is_silent`: returns `[]` and creates no file.

- [ ] **Step 2: Run them and see them fail** (`ModuleNotFoundError: loadout.rtk_config`).

- [ ] **Step 3: Implement the module.**
  - Find the `hooks` table with the header regex from `codex._table_span`: bare or quoted segments, an optional `\r`, exactly one match.
  - A table that `tomllib` sees but no header finds is unplaceable.
  - Insert before the next line that starts with `[`, after the last non-blank line of the table.
  - The parse guard compares `tomllib.loads(new)` with the old data plus the key, or minus the key on removal.
  - Write order: `bk.save_copy(record_path())` when the record exists, then `bk.save_copy(cfg)` or `bk.record_created(cfg)`, then `write_atomic`, then save the record.
  - A record whose file has been deleted (`created` with no file present) is cleared before applying.

- [ ] **Step 4: Run them; they pass.**

- [ ] **Step 5: Commit** `feat(rtk): silence rtk's false missing-hook warning where loadout provides the hook`.

### Task 3: wire `rtk_step` into every re-apply

**Files:**
- Modify:
  - `cli/loadout/apply.py`: `rtk_step`, plus a docstring line in the module header ("rtk_step: no facts");
  - `cli/loadout/bootstrap.py`: next to `apply.cbm_step(bk)` at about line 1054;
  - `cli/loadout/update.py`: `_reapply` next to `cbm_step` at about line 481, and the plan parts at about line 169;
  - `cli/loadout/configure.py`: about line 209;
  - `cli/loadout/maintenance.py`: about line 377, next to the cbm try block, with its own `Backup(description="maintenance: rtk config")`.
- Test: `tests/test_rtk_step.py`

**Interfaces:**
- Consumes: `rtk_config.apply`.
- Produces: `apply.rtk_step(bk, dry: bool = False) -> StepResult`, with the name `"rtk"`. It is an empty `StepResult` when `apply` returns `[]`, and it is finished through `_finish(…, "rtk")`.

In the update plan, `rtk_step(object(), dry=True)` lines add the part `"rtk (config)"` to the "Re-apply the loadout setup" item only when the dry run has a change line.

- [ ] **Step 1: Write the failing tests.**
  - `test_update_plan_names_rtk_part`: with the condition wanted and no config, the plan's first item contains `rtk (config)`.
  - `test_update_reapply_writes_rtk_config` (update `--yes` path).
  - `test_codex_only_update_removes_key`: Claude is off and the record exists, so the key is removed.
  - `test_daily_sync_runs_rtk_step`: the change goes through `maintenance.notify` as a notice that names the backup.
  - `test_bootstrap_runs_rtk_step`.
  - Use the existing harnesses in `tests/test_update*.py` / `test_maintenance.py` / `test_bootstrap.py` (find them with codebase-memory `search_graph` on `cbm_step` callers' tests).

- [ ] **Step 2: Run them and see them fail.**

- [ ] **Step 3: Implement it.** In bootstrap and update the step runs whenever `cbm_step` runs, and also when only Codex is on.

- [ ] **Step 4: Run the full suite** with the test command from Global Constraints. Expected: all pass.

- [ ] **Step 5: Commit** `feat(rtk): run the rtk config step in bootstrap, update, configure and the daily sync`.

### Task 4: docs

**Files:**
- Create: `docs/adr/0043-silence-rtk-missing-hook-warning.md` (Context, Decision, Alternatives, Consequences, In the code; link the spec and rtk-ai/rtk#4800).
- Modify:
  - `docs/adr/README.md` (index row);
  - `AGENTS.md` ("decisions 0001-0043");
  - `docs/how-to/troubleshooting.md` (a row for the rtk warning);
  - `docs/reference/state-and-sync.md` (the `rtk-config.json` record, and the daily sync running the step);
  - the page that describes rtk's hook in `docs/explanation/the-toolset.md` (one sentence);
  - `docs/reference/cli.md`, if it lists the re-apply parts.
- Test: `tests/test_docs_links.py` (existing).

- [ ] **Step 1: Write the docs.**
- [ ] **Step 2: Run** `uv run --python 3.12 --with pytest pytest -q tests/test_docs_links.py --deselect "tests/test_docs_links.py::test_links_resolve[docs/examples/Niklas_Serena_Config.md]"`. Expected: pass.
- [ ] **Step 3: Commit** `docs: ADR 0043 and pages for silencing rtk's missing-hook warning`.
