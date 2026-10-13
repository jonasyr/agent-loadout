# Hardening 4a: State Out of `~/.claude` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** loadout's state and backups live in `$XDG_STATE_HOME/loadout` (default `~/.local/state/loadout`); existing machines migrate once; old backups still restore; a Codex-only machine has no `~/.claude`.

**Architecture:** `paths.state_dir()`/`backups_root()` change; a new `migrate.py` moves the legacy folders under a lock at the start of every CLI run; `backup.restore` maps legacy absolute paths in manifests to the new roots before its checks; the two hook scripts repeat the location rule.

**Tech Stack:** Python 3.11+ standard library, pytest.

**Spec:** `docs/superpowers/specs/2026-10-13-state-out-of-claude-design.md`

## Global Constraints

- Tests: `uv run --python 3.12 --with pytest pytest -q`; they use `fake_home`/`fake_runner`; never the real `~/.claude`, `~/.codex`, `~/.config/loadout` or `~/.local/state`.
- Never delete anything in `~/.claude` except the moved `.loadout` and `backups` folders, and `~/.claude` itself only when empty (`rmdir`) and Claude Code is off.
- Never lose a file in the move: on doubt keep the old copy and say so.
- Notices from the migration go to stderr (stdout of commands like `loadout kit-path` is parsed by skills).
- Standard library only; Conventional Commits; no AI attribution.

## Review Focus

1. A legacy state folder whose new location was already written by a newer hook before the CLI ran (e.g. `advisor-pending.json` exists in both) — the CLI's copy of shared files must not be lost; the old one is kept and named. Test in Task 2 (`test_both_locations_keep_the_new_and_name_the_old`).
2. A backup taken before the move whose `restore-file` target was a state file (`~/.claude/.loadout/codex-config.json`) — restore writes it to the new state dir and never recreates `~/.claude/.loadout`. Test in Task 3.
3. `loadout restore ~/.claude/backups/loadout-…` typed from an old message after the move — it works. Test in Task 3.
4. `XDG_STATE_HOME` set to a relative path or empty — ignored. Test in Task 1.
5. A damaged `targets.json` while deciding whether to remove the empty `~/.claude` — the folder stays, no crash. Test in Task 2.

---

### Task 1: New locations, hooks follow, tests isolated

**Files:**
- Modify: `cli/loadout/paths.py` (`state_dir`, `backups_root`, new `legacy_state_dir`, `legacy_backups_root`)
- Modify: `plugins/loadout/hooks/advisor.py` (`state_dir`), `plugins/loadout/hooks/reload_check.py` (the `reload-notified.json` path)
- Modify: `tests/conftest.py` (both HOME fixtures unset `XDG_STATE_HOME`)
- Modify: the six tests with hard-coded old paths: `tests/test_settings_merge.py`, `tests/test_advisor.py`, `tests/test_reload_check.py`, `tests/test_minors.py`, `tests/test_hook_merge_properties.py`, `tests/test_agent_choice_bootstrap.py` (replace `home / ".claude/.loadout"` with `paths.state_dir()` and `.claude/backups` with `paths.backups_root()`; for subprocess hook tests use `home / ".local/state/loadout"`)
- Create: `tests/test_state_location.py`

**Interfaces:**
- Produces: `paths.state_dir() -> Path`, `paths.backups_root() -> Path`, `paths.legacy_state_dir() -> Path` (`~/.claude/.loadout`), `paths.legacy_backups_root() -> Path` (`~/.claude/backups`).

- [ ] **Step 1: Write the failing tests** (`tests/test_state_location.py`)

```python
"""loadout's own files live in $XDG_STATE_HOME/loadout (ADR 0025), never under ~/.claude."""
import importlib.util
import os

from loadout import paths

HOOKS = paths.kit_root() / "plugins" / "loadout" / "hooks"


def _hook(name):
    spec = importlib.util.spec_from_file_location(name, HOOKS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_default_location_is_xdg_state_under_home(fake_home):
    assert paths.state_dir() == fake_home / ".local" / "state" / "loadout"
    assert paths.backups_root() == paths.state_dir() / "backups"
    assert paths.legacy_state_dir() == fake_home / ".claude" / ".loadout"
    assert paths.legacy_backups_root() == fake_home / ".claude" / "backups"


def test_absolute_xdg_state_home_wins(fake_home, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "st"))
    assert paths.state_dir() == tmp_path / "st" / "loadout"


def test_relative_or_empty_xdg_state_home_is_ignored(fake_home, monkeypatch):
    for value in ("rel/state", ""):
        monkeypatch.setenv("XDG_STATE_HOME", value)
        assert paths.state_dir() == fake_home / ".local" / "state" / "loadout"


def test_tests_never_see_the_real_state_folder(fake_home):
    assert "XDG_STATE_HOME" not in os.environ
    assert paths.state_dir().is_relative_to(fake_home)


def test_hooks_use_the_same_folder(fake_home, tmp_path, monkeypatch):
    advisor = _hook("advisor")
    assert advisor.state_dir() == paths.state_dir()
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "st"))
    assert advisor.state_dir() == paths.state_dir()
    reload_check = _hook("reload_check")
    assert reload_check.state_dir(fake_home) == paths.state_dir()
```

- [ ] **Step 2: Run them**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_state_location.py`
Expected: FAIL (`AttributeError: legacy_state_dir`, old default path, `reload_check` has no `state_dir`).

- [ ] **Step 3: Implement**

`cli/loadout/paths.py` (replace `state_dir` and `backups_root`):

```python
def state_dir() -> Path:
    """loadout's own state: $XDG_STATE_HOME/loadout, else ~/.local/state/loadout (ADR 0025).
    A relative or empty XDG_STATE_HOME is ignored, as the XDG spec requires."""
    base = os.environ.get("XDG_STATE_HOME", "")
    root = Path(base).expanduser() if base and Path(base).expanduser().is_absolute() else home() / ".local" / "state"
    return root / "loadout"


def backups_root() -> Path:
    return state_dir() / "backups"


def legacy_state_dir() -> Path:
    """Where state lived before ADR 0025; read only by the migration and by restore's path mapping."""
    return claude_home() / ".loadout"


def legacy_backups_root() -> Path:
    return claude_home() / "backups"
```

`plugins/loadout/hooks/advisor.py` `state_dir()`:

```python
def state_dir() -> Path:
    """The same rule as loadout's paths.state_dir() (this hook cannot import loadout)."""
    home = os.environ.get("HOME") or os.environ.get("USERPROFILE") or str(Path.home())
    base = os.environ.get("XDG_STATE_HOME", "")
    root = Path(base).expanduser() if base and Path(base).expanduser().is_absolute() else Path(home) / ".local" / "state"
    return root / "loadout"
```

`plugins/loadout/hooks/reload_check.py`: add the same function as `state_dir(home: Path) -> Path` (taking the already-resolved home) and replace `home / ".claude" / ".loadout" / "reload-notified.json"` with `state_dir(home) / "reload-notified.json"`. Update both docstrings/comments that name `~/.claude/.loadout`.

`tests/conftest.py`: in `never_the_real_home` and `fake_home` add `monkeypatch.delenv("XDG_STATE_HOME", raising=False)`.

Then fix the six test files listed above (search `.claude/.loadout` and `.claude/backups`).

- [ ] **Step 4: Run all tests**

Run: `uv run --python 3.12 --with pytest pytest -q`
Expected: PASS (fix any remaining test that hard-codes the old location the same way; never change a production path back).

- [ ] **Step 5: Commit**

```bash
git add cli/loadout/paths.py plugins/loadout/hooks tests
git commit -m "feat: loadout's state and backups live in XDG state (~/.local/state/loadout)"
```

---

### Task 2: The one-time migration

**Files:**
- Create: `cli/loadout/migrate.py`
- Modify: `cli/loadout/__main__.py` (`main`: run the migration before dispatch)
- Modify: `cli/loadout/check.py` (new `_legacy_state()` in `run_checks`)
- Create: `tests/test_migrate_state.py`

**Interfaces:**
- Consumes: Task 1's `paths.state_dir`, `backups_root`, `legacy_state_dir`, `legacy_backups_root`.
- Produces: `migrate.migrate_state() -> list[str]` (notice lines; empty when nothing to do); `check._legacy_state() -> list[CheckResult]`.

- [ ] **Step 1: Write the failing tests** (`tests/test_migrate_state.py`)

```python
"""The one-time move of ~/.claude/.loadout and ~/.claude/backups to the XDG state folder (ADR 0025)."""
import errno
import json
import os

import pytest

from loadout import check, migrate, paths


def _legacy(fake_home):
    old = paths.legacy_state_dir()
    old.mkdir(parents=True)
    (old / "managed-settings.json").write_text('{"a": 1}')
    (old / "codex-config.json").write_text('{"tables": {}}')
    b = paths.legacy_backups_root() / "loadout-1"
    (b / "files").mkdir(parents=True)
    (b / "manifest.json").write_text('{"steps": []}')
    (b / "files" / "x").write_text("copy")
    return old


def test_nothing_to_do_is_silent(fake_home):
    assert migrate.migrate_state() == []
    assert not paths.state_dir().exists()


def test_moves_state_and_backups(fake_home):
    _legacy(fake_home)
    lines = migrate.migrate_state()
    assert (paths.state_dir() / "managed-settings.json").read_text() == '{"a": 1}'
    assert (paths.backups_root() / "loadout-1" / "files" / "x").read_text() == "copy"
    assert not paths.legacy_state_dir().exists() and not paths.legacy_backups_root().exists()
    assert any("moved its state and backups" in line for line in lines)
    assert migrate.migrate_state() == []  # a second run does nothing


def test_cross_device_copies_then_deletes(fake_home, monkeypatch):
    _legacy(fake_home)
    real = os.replace

    def replace(src, dst):
        if ".partial" not in str(src):
            raise OSError(errno.EXDEV, "cross-device link")
        return real(src, dst)
    monkeypatch.setattr(migrate.os, "replace", replace)
    migrate.migrate_state()
    assert (paths.backups_root() / "loadout-1" / "files" / "x").read_text() == "copy"
    assert (paths.state_dir() / "codex-config.json").exists()
    assert not paths.legacy_backups_root().exists()


def test_a_leftover_partial_copy_is_redone(fake_home, monkeypatch):
    _legacy(fake_home)
    partial = paths.state_dir() / "backups.partial"
    partial.mkdir(parents=True)
    (partial / "junk").write_text("half")
    real = os.replace
    monkeypatch.setattr(migrate.os, "replace", lambda s, d: real(s, d) if ".partial" in str(s)
                        else (_ for _ in ()).throw(OSError(errno.EXDEV, "x")))
    migrate.migrate_state()
    assert not partial.exists() and not (paths.backups_root() / "junk").exists()
    assert (paths.backups_root() / "loadout-1" / "manifest.json").exists()


def test_both_locations_keep_the_new_and_name_the_old(fake_home):
    _legacy(fake_home)
    paths.state_dir().mkdir(parents=True)
    (paths.state_dir() / "codex-config.json").write_text('{"new": true}')
    lines = migrate.migrate_state()
    assert json.loads((paths.state_dir() / "codex-config.json").read_text()) == {"new": True}
    assert (paths.state_dir() / "managed-settings.json").exists()  # the rest moved
    assert (paths.legacy_state_dir() / "codex-config.json").exists()  # kept, not lost
    assert any("codex-config.json" in line and "by hand" in line for line in lines)


def test_another_run_holding_the_lock_is_left_alone(fake_home):
    _legacy(fake_home)
    paths.state_dir().mkdir(parents=True)
    (paths.state_dir() / migrate.LOCK).write_text("")
    assert migrate.migrate_state() == []
    assert paths.legacy_state_dir().exists()


def test_empty_claude_folder_removed_only_with_claude_code_off(fake_home):
    _legacy(fake_home)
    (paths.personal_root()).mkdir(parents=True)
    (paths.personal_root() / "targets.json").write_text('{"claude": false, "codex": true}')
    migrate.migrate_state()
    assert not (fake_home / ".claude").exists()


def test_claude_folder_stays_with_claude_code_on_or_when_not_empty(fake_home):
    _legacy(fake_home)
    migrate.migrate_state()  # Claude Code on (no targets.json)
    assert (fake_home / ".claude").is_dir()
    (paths.personal_root()).mkdir(parents=True)
    (paths.personal_root() / "targets.json").write_text('{"claude": false, "codex": true}')
    (fake_home / ".claude" / "keep.txt").write_text("mine")
    _legacy(fake_home)
    migrate.migrate_state()
    assert (fake_home / ".claude" / "keep.txt").read_text() == "mine"


def test_damaged_targets_keeps_the_claude_folder(fake_home):
    _legacy(fake_home)
    paths.personal_root().mkdir(parents=True)
    (paths.personal_root() / "targets.json").write_text("{broken")
    migrate.migrate_state()
    assert (fake_home / ".claude").is_dir()


def test_main_runs_the_migration_and_reports_on_stderr(fake_home, capsys):
    from loadout.__main__ import main
    _legacy(fake_home)
    assert main(["kit-path"]) == 0
    captured = capsys.readouterr()
    assert "moved its state" in captured.err and "moved" not in captured.out
    assert (paths.state_dir() / "managed-settings.json").exists()


def test_check_warns_while_a_legacy_folder_remains(fake_home):
    assert check._legacy_state() == [check.CheckResult("loadout state", True)]
    paths.legacy_state_dir().mkdir(parents=True)
    (paths.legacy_state_dir() / "codex-config.json").write_text("{}")
    [row] = check._legacy_state()
    assert not row.ok and row.severity == "warn" and "codex-config.json" in row.detail
```

- [ ] **Step 2: Run them**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_migrate_state.py`
Expected: FAIL (`ModuleNotFoundError: loadout.migrate`).

- [ ] **Step 3: Implement `cli/loadout/migrate.py`**

```python
"""One-time move of loadout's own files out of ~/.claude into the XDG state folder (ADR 0025)."""
from __future__ import annotations

import errno
import os
import shutil
import time
from pathlib import Path

from . import paths

LOCK = "migrate.lock"
STALE = 3600.0


def _files(root: Path) -> dict[str, int]:
    """Every file and link below root with its size (0 for a link): what a complete copy must match."""
    return {p.relative_to(root).as_posix(): 0 if p.is_symlink() else p.stat().st_size
            for p in root.rglob("*") if p.is_symlink() or p.is_file()}


def _move(old: Path, new: Path) -> None:
    """Move old to new (new does not exist): a rename, else a verified copy, then the old one goes."""
    new.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.replace(old, new)
        return
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
    if old.is_symlink() or not old.is_dir():
        shutil.copy2(old, new, follow_symlinks=False)
        old.unlink()
        return
    partial = new.with_name(new.name + ".partial")
    if partial.exists():
        shutil.rmtree(partial)  # an interrupted copy: start again
    shutil.copytree(old, partial, symlinks=True)
    if _files(partial) != _files(old):
        shutil.rmtree(partial)
        raise OSError(f"the copy of {old} is incomplete; it stays where it is")
    os.replace(partial, new)
    shutil.rmtree(old)


def _merge(old: Path, new: Path) -> list[Path]:
    """Both folders exist: move what the new one lacks; the new one wins; return the old entries kept."""
    kept = []
    for entry in sorted(old.iterdir()):
        target = new / entry.name
        if target.exists() or target.is_symlink():
            kept.append(entry)
        else:
            _move(entry, target)
    if not kept:
        old.rmdir()
    return kept


def _lock(state: Path) -> Path | None:
    lock = state / LOCK
    try:
        os.close(os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
        return lock
    except FileExistsError:
        try:
            if time.time() - lock.stat().st_mtime < STALE:
                return None  # another run is moving the files right now
            lock.unlink()
            os.close(os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
            return lock
        except OSError:
            return None


def _claude_code_off() -> bool:
    from . import targets
    try:
        return not targets.claude_enabled()
    except Exception:  # a damaged targets.json: keep the folder
        return False


def migrate_state() -> list[str]:
    """Returns notice lines; empty when there was nothing to move."""
    old_state, old_backups = paths.legacy_state_dir(), paths.legacy_backups_root()
    if not (old_state.exists() or old_backups.exists()):
        return []
    state = paths.state_dir()
    state.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        state.chmod(0o700)
    lock = _lock(state)
    if lock is None:
        return []
    lines, kept = [], []
    try:
        for old, new in ((old_state, state), (old_backups, paths.backups_root())):
            if not old.exists():
                continue
            if new.exists():
                kept += _merge(old, new)
            else:
                _move(old, new)
        lines.append(f"loadout: moved its state and backups from ~/.claude to {state}")
        lines += [f"loadout: kept {p} (the new location already has it); compare and delete it by hand" for p in kept]
    except OSError as exc:
        lines.append(f"loadout: could not move its state from ~/.claude ({exc}); it tries again next time")
    finally:
        lock.unlink(missing_ok=True)
    claude = paths.claude_home()
    if claude.is_dir() and not any(claude.iterdir()) and _claude_code_off():
        claude.rmdir()  # only an empty folder; only when Claude Code is off
    return lines
```

`cli/loadout/__main__.py` `main()`, after `args = build_parser().parse_args(argv)` and before the `try` that dispatches:

```python
    try:  # ADR 0025: loadout's files leave ~/.claude once; never let this stop a command
        from .migrate import migrate_state
        for line in migrate_state():
            print(line, file=sys.stderr)
    except Exception as exc:
        print(f"loadout: could not move its state from ~/.claude ({exc}); it tries again next time", file=sys.stderr)
```

`cli/loadout/check.py`:

```python
def _legacy_state() -> list[CheckResult]:
    """Files the migration kept in ~/.claude because the new location already had them (ADR 0025)."""
    left = [p for root in (paths.legacy_state_dir(), paths.legacy_backups_root()) if root.is_dir()
            for p in sorted(root.iterdir())]
    if not left:
        return [CheckResult("loadout state", True)]
    names = ", ".join(str(p) for p in left[:5]) + (" …" if len(left) > 5 else "")
    return [CheckResult("loadout state", False, f"left in ~/.claude: {names}",
                        f"compare with {paths.state_dir()} and delete them by hand", "warn")]
```

and add `*_legacy_state()` after `*_wsl()` in `run_checks`. Ensure `check.py` imports `paths` (it already does if `_links` uses it; otherwise add `from . import paths`).

- [ ] **Step 4: Run tests**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_migrate_state.py` then the full suite.
Expected: PASS. If a test that calls `main()` now sees an extra stderr line, it only happens with a legacy folder present; fix the test setup, never the notice.

- [ ] **Step 5: Commit**

```bash
git add cli/loadout/migrate.py cli/loadout/__main__.py cli/loadout/check.py tests/test_migrate_state.py
git commit -m "feat: move loadout's state and backups out of ~/.claude once, under a lock"
```

---

### Task 3: Old backups restore from the new place

**Files:**
- Modify: `cli/loadout/backup.py` (`_map_legacy`, used in `_undo` and `restore`)
- Modify: `cli/loadout/commands.py` (restore help example path)
- Create: `tests/test_restore_legacy.py`

**Interfaces:**
- Consumes: Task 1 paths; Task 2 `migrate.migrate_state()`.
- Produces: `backup._map_legacy(value: str) -> str`.

- [ ] **Step 1: Write the failing tests** (`tests/test_restore_legacy.py`)

```python
"""A backup taken before ADR 0025 restores after the move, and never recreates ~/.claude/.loadout."""
import json

from loadout import backup, migrate, paths


def _old_backup(fake_home):
    """A manifest exactly as an old run wrote it: absolute paths under ~/.claude/backups and ~/.claude/.loadout."""
    root = paths.legacy_backups_root() / "loadout-old"
    files = root / "files"
    files.mkdir(parents=True)
    (files / "codex-config.json").write_text('{"old": true}')
    (files / "settings.json").write_text('{"moved": true}')
    state = paths.legacy_state_dir()
    state.mkdir(parents=True)
    (state / "codex-config.json").write_text('{"current": true}')
    (state / "made.json").write_text("{}")
    target = fake_home / ".claude" / "settings.json"
    steps = [
        {"label": "codex-config", "undo": {"restore-file": [str(files / "codex-config.json"), str(state / "codex-config.json")]}},
        {"label": "made", "undo": {"created": str(state / "made.json")}},
        {"label": "settings", "undo": {"move": [str(files / "settings.json"), str(target)]}},
    ]
    (root / "manifest.json").write_text(json.dumps({"description": "old", "created_at": 1, "steps": steps}))
    return root


def test_old_backup_restores_into_the_new_state_dir(fake_home):
    old_root = _old_backup(fake_home)
    migrate.migrate_state()
    lines, ok, _ = backup.restore(paths.backups_root() / old_root.name)
    assert ok, lines
    assert json.loads((paths.state_dir() / "codex-config.json").read_text()) == {"old": True}
    assert not (paths.state_dir() / "made.json").exists()  # created file moved aside
    assert json.loads((fake_home / ".claude" / "settings.json").read_text()) == {"moved": True}
    assert not paths.legacy_state_dir().exists() and not paths.legacy_backups_root().exists()


def test_old_printed_restore_path_still_works(fake_home):
    old_root = _old_backup(fake_home)
    migrate.migrate_state()
    lines, ok, _ = backup.restore(old_root)  # ~/.claude/backups/loadout-old, as an old message printed it
    assert ok, lines


def test_paths_outside_both_roots_are_not_mapped(fake_home):
    other = str(fake_home / "elsewhere" / "x")
    assert backup._map_legacy(other) == other
    legacy = str(paths.legacy_backups_root() / "b" / "files" / "y")
    assert backup._map_legacy(legacy) == str(paths.backups_root() / "b" / "files" / "y")


def test_a_mapped_source_outside_files_is_still_refused(fake_home):
    root = paths.backups_root() / "b"
    (root / "files").mkdir(parents=True)
    escape = str(paths.legacy_backups_root() / "b" / "manifest.json")  # maps inside the backup, not inside files/
    (root / "manifest.json").write_text(json.dumps({"steps": [
        {"label": "x", "undo": {"move": [escape, str(fake_home / "t")]}}]}))
    lines, ok, _ = backup.restore(root)
    assert not ok and any("not inside" in line for line in lines)
```

- [ ] **Step 2: Run them**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_restore_legacy.py`
Expected: FAIL (`AttributeError: _map_legacy`; restore refuses the legacy root).

- [ ] **Step 3: Implement** in `cli/loadout/backup.py`

```python
def _map_legacy(value: str) -> str:
    """A path written before ADR 0025 (under ~/.claude/backups or ~/.claude/.loadout) moved with the migration:
    point it at the new location. Any other path stays as it is."""
    path = Path(value)
    for old, new in ((paths.legacy_backups_root(), paths.backups_root()),
                     (paths.legacy_state_dir(), paths.state_dir())):
        try:
            return str(new / path.relative_to(old))
        except ValueError:
            continue
    return value


def _mapped(undo: dict) -> dict:
    out = dict(undo)
    for key in ("move", "restore-file"):
        if isinstance(out.get(key), list):
            out[key] = [_map_legacy(str(v)) for v in out[key]]
    for key in ("created", "kept"):
        if isinstance(out.get(key), str):
            out[key] = _map_legacy(out[key])
    return out
```

In `_undo`, first line becomes `undo, label = _mapped(step["undo"]), step["label"]`.
In `restore`, before the `try` that resolves: `root = Path(_map_legacy(str(root)))`.

`cli/loadout/commands.py` restore help: replace `~/.claude/backups/loadout-<timest…` with `~/.local/state/loadout/backups/loadout-<timestamp>`.

- [ ] **Step 4: Run tests** — the new file, then the full suite. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cli/loadout/backup.py cli/loadout/commands.py tests/test_restore_legacy.py
git commit -m "feat(restore): backups from before the move restore from the new location"
```

---

### Task 4: A Codex-only machine has no `~/.claude`

**Files:**
- Test: `tests/test_state_location.py` (append)
- Modify: whatever the test shows still creates `~/.claude` on a Codex-only bootstrap (find it, gate it on `targets.claude_enabled()`)

- [ ] **Step 1: Write the failing test** (append)

```python
def test_codex_only_bootstrap_leaves_no_claude_folder(fake_home, fake_runner, monkeypatch):
    import json
    from loadout import bootstrap, codex, out
    monkeypatch.setattr(out, "VERBOSE", False)
    monkeypatch.setattr(codex, "unavailable", lambda: None)
    monkeypatch.setattr(codex, "apply_all", lambda bk, refresh=False, **kw: [])
    monkeypatch.setattr(codex, "open_steps", lambda: [])
    bootstrap.bootstrap(install=False, yes=True, plugins=True, adopt_step=True, ask=lambda q: "",
                        interactive=False, agents="codex")
    assert not (fake_home / ".claude").exists(), sorted(str(p) for p in (fake_home / ".claude").rglob("*"))
    assert json.loads((paths.personal_root() / "targets.json").read_text()) == {"claude": False, "codex": True}
```

- [ ] **Step 2: Run it**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_state_location.py -k codex_only`
Expected: either PASS (Tasks 1-3 were enough) or FAIL listing the files created under `~/.claude`. For each listed file, find its writer (`grep -rn "claude_home()" cli/loadout`) and gate it on `targets.claude_enabled()`; ledger each as a ruling. If it passes at once, ledger "Task 4: Ruling: no further writer found — the test pins it".

- [ ] **Step 3: Run the full suite.** Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add -A cli tests
git commit -m "test: a Codex-only bootstrap leaves no ~/.claude"
```

---

### Task 5: Docs and ADR 0025

**Files:**
- Create: `docs/adr/0025-state-in-xdg-state-home.md` (format of `docs/adr/0024-…`; read it first)
- Modify: `docs/adr/README.md` (index), `AGENTS.md` (ADR range 0001-0025)
- Modify: `docs/explanation/architecture.md` (`## loadout's own files`), `docs/reference/personal-layer.md` (machine-local state), `docs/how-to/undo-and-restore.md`, `docs/how-to/uninstall.md`, `docs/reference/cli.md` (restore example, `check` row "loadout state", `XDG_STATE_HOME` in the environment variables section), `docs/explanation/security-and-trust.md` (backups location)
- Modify: `.serena/memories/*` only if one names the old path

- [ ] **Step 1: Find every old path**

Run: `grep -rn "\.claude/\.loadout\|\.claude/backups\|claude/\.loadout" README.md AGENTS.md CONTRIBUTING.md docs rules plugins/loadout/skills .serena --include=*.md | grep -v "docs/superpowers\|docs/adr/00[01]"`
Expected: a list; each line is changed to the new location (`~/.local/state/loadout`, `~/.local/state/loadout/backups`, "or `$XDG_STATE_HOME/loadout`" once per page where locations are listed), except ADR bodies (history).

- [ ] **Step 2: Write ADR 0025** — Status: accepted. Context: state and backups lived under `~/.claude` for every user, so Codex-only users got a `~/.claude` folder; backups next to configuration. Decision: `$XDG_STATE_HOME/loadout` (default `~/.local/state/loadout`), backups in its `backups/`; a one-time migration under a lock at the start of every loadout run; restore maps old paths. Consequences: Codex-only machines have no `~/.claude`; a dotfile sync of `~/.config` never carries backups; an entry kept in `~/.claude` on a conflict is reported by the migration and by `loadout check` until deleted by hand.

- [ ] **Step 3: Update the pages** listed above; `architecture.md#loadouts-own-files` describes the new location and the migration (one paragraph) and links ADR 0025; remove its "Codex-only users still get `~/.claude`" statement. The `uninstall.md` steps that delete `~/.claude/.loadout` now delete `~/.local/state/loadout` (and say an old `~/.claude/.loadout` only exists if the migration kept something).

- [ ] **Step 4: Test**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_docs_links.py tests/test_readme.py` then the full suite.
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add docs AGENTS.md .serena
git commit -m "docs: loadout's own files live in XDG state (ADR 0025)"
```
