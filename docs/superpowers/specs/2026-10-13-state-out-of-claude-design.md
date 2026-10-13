# Hardening 4a: loadout's state and backups move out of `~/.claude`

Status: approved design, 2026-10-13. First of three hardening 4 PRs (4a state location, 4b Codex code gaps, 4c own-tool scopes).

## Goal

loadout keeps nothing of its own under `~/.claude`. A Codex-only user ends up with no `~/.claude` folder at all; a Claude Code user's `~/.claude` holds only what Claude Code and the kit's links need. Existing machines move their state and backups automatically, once, and every old backup still restores.

Success criteria:

1. `paths.state_dir()` is `$XDG_STATE_HOME/loadout` (default `~/.local/state/loadout`) and `paths.backups_root()` is `<state_dir>/backups`, on every OS.
2. No code path writes `~/.claude/.loadout` or `~/.claude/backups` again; the two hook scripts (`plugins/loadout/hooks/advisor.py`, `reload_check.py`) use the same location rule.
3. The first loadout run after the update moves the old folders; a second run does nothing; an interrupted run finishes next time.
4. A backup made before the move restores correctly afterwards and never recreates `~/.claude/.loadout` or `~/.claude/backups`.
5. A Codex-only bootstrap on a fresh home leaves no `~/.claude`. On a Codex-only machine migrated from the old layout, an empty `~/.claude` left behind is removed.
6. Tests never reach the real `~/.local/state`.

## Constraints

- The AGENTS.md "Code Review Rules" apply: user files byte for byte, every destructive change undoable, a turned-off agent's files untouched, no secrets in output, external commands only through `runner.run`, tests on `fake_home`.
- Moving the old folders is not a destructive change to user data (the same bytes move), but it must never lose a file: on any doubt, keep the old copy and say so.
- Never delete anything in `~/.claude` except the two folders loadout owns (`.loadout`, `backups`) after they were moved, and `~/.claude` itself only when it is empty.
- Standard library only; Python 3.11+.

## Design

### 1. Locations (`cli/loadout/paths.py`)

```python
def state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME")
    root = Path(base).expanduser() if base and Path(base).expanduser().is_absolute() else home() / ".local" / "state"
    return root / "loadout"

def backups_root() -> Path:
    return state_dir() / "backups"

def legacy_state_dir() -> Path:      # ~/.claude/.loadout (read only by the migration and restore's path mapping)
def legacy_backups_root() -> Path:   # ~/.claude/backups
```

A relative `XDG_STATE_HOME` is ignored, as the XDG spec requires. The hook scripts cannot import `loadout`; they repeat the same three-line rule (a test pins that both match `paths.state_dir()`).

### 2. Migration (`cli/loadout/migrate.py`, new)

`migrate_state() -> list[str]` returns notice lines (empty when nothing happened). It runs at the start of every CLI command (`__main__.main`, before dispatch) and of `hook-session-start`, and is cheap when there is nothing to do (two `exists()` checks).

For each pair (legacy state dir → state dir, legacy backups root → backups root):

1. Old folder missing: nothing to do.
2. New folder missing: `os.replace` (rename). On `OSError` with `EXDEV` (another filesystem): `shutil.copytree(symlinks=True)` into `<new>.partial`, compare the file list and sizes, rename `.partial` to the final name, then remove the old folder. A leftover `.partial` from an interrupted run is removed and the copy starts again.
3. Both exist: move each entry of the old folder whose name does not exist in the new one; for a name in both, keep the new one and leave the old one in place. Report the kept-old entries in one notice line (`loadout: kept <path> (the new location already has it); compare and delete it by hand`). The old folder is removed only when empty.
4. Backups first, then state, under a lock file in the new state dir (`migrate.lock`, `O_EXCL`, stale after an hour as for the maintenance lock); a second run that sees the lock does nothing.
5. Afterwards: if `~/.claude` exists, is empty, and the user's agents do not include Claude Code (`targets.claude_enabled()` false), remove it with `rmdir` (never recursive). With Claude Code on, an empty `~/.claude` stays (Claude Code will use it).

Private modes are kept (`copytree` copies modes; the new state dir gets `0o700` like the old one, see `backup.PRIVATE_DIR`).

One notice for the user, printed once: `loadout: moved its state and backups from ~/.claude to ~/.local/state/loadout`.

### 3. Restore maps old paths (`cli/loadout/backup.py`)

A new `_map_legacy(path: str) -> Path` replaces a leading legacy backups root with the backups root, and a leading legacy state dir with the state dir; any other path is unchanged. Restore applies it to every path it reads from a manifest step (`move`, `restore-file`, `created`, `kept`) before its existing checks (`backups_root` containment, `files/` sources, `_allowed_run`), so the checks see the new paths. A `backup_dir` argument under the legacy root is mapped the same way, so `loadout restore ~/.claude/backups/loadout-…` printed by an old run still works.

New manifests are unchanged in format (absolute paths); they are already under the new root.

### 4. Everything else

- `check.py`: a row "loadout state" warns when a legacy folder still exists after migration (with the kept-old path and the fix "compare and delete by hand").
- `commands.py` restore help text: the new example path.
- `tests/conftest.py`: `never_the_real_home` and `fake_home` unset `XDG_STATE_HOME` so `state_dir()` follows the fake HOME.

### 5. Docs

- New ADR `docs/adr/0025-state-in-xdg-state-home.md`: context (Codex-only users got a `~/.claude` folder), decision (`$XDG_STATE_HOME/loadout`), consequences (one-time migration, restore maps old paths, a dotfile sync of `~/.config` never carries backups).
- `docs/explanation/architecture.md#loadouts-own-files`: the new location, the migration; the "Codex-only users still get `~/.claude`" sentence is removed.
- `docs/reference/personal-layer.md` (machine-local state), `docs/how-to/undo-and-restore.md`, `docs/how-to/uninstall.md`, `docs/reference/cli.md` (restore, check row, `XDG_STATE_HOME` in the environment table), `docs/explanation/security-and-trust.md` (where backups live): every `~/.claude/.loadout` and `~/.claude/backups` becomes the new path; links to the ADR.
- `docs/adr/0022` and `0024` keep their bodies; `AGENTS.md` ADR range 0001-0025.

## Testing

- `paths`: default location; `XDG_STATE_HOME` absolute honoured, relative ignored.
- Migration: rename; cross-device copy (simulate `EXDEV` by monkeypatching `os.replace`); leftover `.partial` resumed; both locations present (new wins, old kept and named, old folder kept while not empty); lock held by another run; second run is a no-op; empty `~/.claude` removed only with Claude Code off; a non-empty `~/.claude` untouched.
- Restore: a backup written with legacy absolute paths (moved by the migration) restores every step kind; `created` and `restore-file` targets under the legacy state dir land in the new state dir; `loadout restore <legacy path>` works; the containment checks still refuse a path outside the backups root.
- Codex-only bootstrap on a fresh `fake_home`: `~/.claude` does not exist afterwards.
- Hooks: `advisor.py` and `reload_check.py` resolve the same folder as `paths.state_dir()` (with and without `XDG_STATE_HOME`).
- No test reads or writes the real `~/.local/state` (fixture unsets `XDG_STATE_HOME`; a guard test asserts `state_dir()` is under the fake HOME).

## Out of scope

- 4b (Codex code gaps) and 4c (own-tool scopes): own specs.
- Moving `~/.config/loadout` (personal layer, `secrets.env`): they are configuration and stay.
