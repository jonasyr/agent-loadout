# Repo agents PR 4: VS Code in WSL, and restore picks a backup — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Codex-only on Windows/WSL with VS Code gets the VS Code switch through every bootstrap path (question, `--vscode-wsl`, or the printed manual step) and a `loadout check` row; `loadout restore` without a path offers a numbered list of recent backups with their age, then shows exactly what goes back and asks.

**Architecture:** Part 4 widens `bootstrap.codex_gate` with one helper `_vscode_step` used on every "Codex in WSL" path, a `vscode` flag from `bootstrap --vscode-wsl`, and a `check._vscode` row built from `wsl.codex_side()`'s existing `vscode_windows`. Part 6 adds read-only helpers in `backup.py` (`BackupInfo`, `backups`, `age`, `summary`, `where`, `contents`) and a new `restore_cmd.py` with the picker; `commands.py` delegates `loadout restore` to it.

**Tech Stack:** Python 3.11+ standard library (`cli/loadout/`), pytest with `fake_home`/`fake_runner`.

**Spec:** `docs/superpowers/specs/2026-10-16-repo-agents-and-careful-ux-design.md`, Part 4 (bootstrap and check bullets; the walkthrough and live tour are PR 5) and Part 6. Docs baseline category E: `docs/superpowers/plans/2026-10-16-repo-agents-docs-baseline.md`.

## Global Constraints

- Standard library only; external commands only through `runner.run`.
- `--vscode-wsl`: "the same edit as answering yes (only that key; copy saved first; `loadout restore` undoes it); for agents and scripts. Without the flag and without a terminal, bootstrap prints the manual step (also with `--codex-side wsl`)."
- `check` "in WSL with Codex set up in WSL: a `VS Code` row warns when `settings.json` exists and the setting is not `true` (or not set while the Codex extension is installed), with the fix (`--vscode-wsl`, or the manual step)."
- Restore picker (spec Part 6, verbatim): "In a terminal, `loadout restore` without a path shows the last 10 backups, numbered: age (`2 hours ago`) and date, the command that made it, where (`home` or `repo <path>`), what it holds (`3 files, 2 commands`), and `restored <date>` when restored. Prompt: `Restore which? [1-10, m = more, Enter = cancel]`. After the pick: exactly what will go back (each file, each undo command), then `Restore this? [y/N]`. The restore is backed up as today. `--repo PATH` filters to one repo's backups; `--last` takes the newest; `--list` prints the list (agents, scripts). Without a terminal nothing is picked: a path or `--last` is needed."
- No plaintext secret in the output: undo commands are shown through `secrets.redact`.
- Tests never touch the real `~/.claude`, `~/.codex`, `~/.config/loadout`, or a real Windows home; Conventional Commits, no AI attribution.

## Review Focus

1. `--vscode-wsl` then `loadout restore` of that run's backup: VS Code's `settings.json` back byte for byte (JSONC comments included). Test in Task 1.
2. `--vscode-wsl` where VS Code's `settings.json` does not exist or the Windows home is not found: a clear line with the manual step, nothing created. Test in Task 1.
3. The picker given `0`, `11` when only 10 are shown, `abc`, or `m` when there are no more: asked again (at most three wrong answers, then nothing restored), never a traceback. Test in Task 4.
4. A picked backup that was already restored: refused with the `--force` hint before the confirm question, nothing replayed. Test in Task 4.
5. A damaged manifest (steps not a list, an undo that is not an object, a `restore-file` that is not a pair): skipped from the list or shown as its label, never a crash. Test in Task 3.

---

### Task 1: `--vscode-wsl` and the VS Code step on every "Codex in WSL" path

**Files:**
- Modify: `cli/loadout/bootstrap.py` (`_vscode_step`, `codex_gate`, `bootstrap`, `_bootstrap`)
- Modify: `cli/loadout/commands.py` (`_register_bootstrap`)
- Test: `tests/test_vscode_wsl.py`

**Interfaces:**
- Produces: `bootstrap.codex_gate(flag, ask, interactive, bk=None, vscode=False)`; `bootstrap.bootstrap(..., vscode_wsl: bool = False)`; `bootstrap.VSCODE_FLAG_HINT`.

- [ ] **Step 1: Write the failing tests**

```python
"""bootstrap --vscode-wsl and the VS Code switch with --codex-side wsl (spec Part 4)."""
import pytest

from loadout import __main__ as cli, backup, bootstrap, wsl

OFF = '{\n  // mine\n  "chatgpt.runCodexInWindowsSubsystemForLinux": false\n}\n'


def _vscode(monkeypatch, tmp_path, text=OFF, side="wsl", vscode_windows=True):
    home = tmp_path / "winhome"
    p = wsl.vscode_settings(home)
    p.parent.mkdir(parents=True)
    p.write_text(text)
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)
    monkeypatch.setattr(wsl, "codex_side", lambda **k: wsl.CodexSide(side, ["r"], windows_home=home,
                                                                      vscode_windows=vscode_windows))
    return home


def test_codex_side_wsl_in_a_terminal_offers_the_switch(fake_home, fake_runner, monkeypatch, tmp_path):
    home = _vscode(monkeypatch, tmp_path)
    asked, bk = [], backup.Backup(description="t")
    assert bootstrap.codex_gate("wsl", ask=lambda q: asked.append(q) or "y", interactive=True, bk=bk) is None
    assert asked == [bootstrap.VSCODE_QUESTION] and wsl.vscode_wsl_mode(home) is True


def test_the_flag_switches_without_asking_and_restore_undoes_it(fake_home, fake_runner, monkeypatch, tmp_path):
    home = _vscode(monkeypatch, tmp_path)
    bk = backup.Backup(description="t")
    assert bootstrap.codex_gate("wsl", ask=lambda q: pytest.fail("asked"), interactive=False, bk=bk, vscode=True) is None
    assert wsl.vscode_wsl_mode(home) is True and "// mine" in wsl.vscode_settings(home).read_text()
    _, ok, _ = backup.restore(bk.root)
    assert ok and wsl.vscode_settings(home).read_text() == OFF


def test_the_flag_works_when_both_sides_were_found(fake_home, fake_runner, monkeypatch, tmp_path):
    home = _vscode(monkeypatch, tmp_path, side="both")
    assert bootstrap.codex_gate(None, ask=lambda q: pytest.fail("asked"), interactive=False,
                                bk=backup.Backup(description="t"), vscode=True) is None
    assert wsl.vscode_wsl_mode(home) is True


def test_without_a_terminal_and_flag_the_manual_step_is_printed(fake_home, fake_runner, monkeypatch, tmp_path, capsys):
    home = _vscode(monkeypatch, tmp_path)
    assert bootstrap.codex_gate("wsl", ask=lambda q: pytest.fail("asked"), interactive=False) is None
    printed = capsys.readouterr().out
    assert wsl.MANUAL in printed and "--vscode-wsl" in printed and wsl.vscode_wsl_mode(home) is False


def test_the_flag_without_settings_names_the_manual_step(fake_home, fake_runner, monkeypatch, tmp_path, capsys):
    home = tmp_path / "winhome"
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)
    monkeypatch.setattr(wsl, "codex_side", lambda **k: wsl.CodexSide("wsl", ["r"], windows_home=home))
    bootstrap.codex_gate("wsl", ask=lambda q: "", interactive=False, bk=backup.Backup(description="t"), vscode=True)
    assert wsl.MANUAL in capsys.readouterr().out and not wsl.vscode_settings(home).exists()


def test_the_flag_without_a_windows_home_names_the_manual_step(fake_home, fake_runner, monkeypatch, capsys):
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)
    monkeypatch.setattr(wsl, "codex_side", lambda **k: wsl.CodexSide("wsl", ["r"]))
    bootstrap.codex_gate("wsl", ask=lambda q: "", interactive=False, bk=backup.Backup(description="t"), vscode=True)
    assert wsl.MANUAL in capsys.readouterr().out


def test_the_cli_passes_the_flag(fake_home, monkeypatch):
    got = {}
    monkeypatch.setattr(bootstrap, "bootstrap", lambda *a, **k: got.update(k) or 0)
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)
    assert cli.main(["bootstrap", "--codex-side", "wsl", "--vscode-wsl"]) == 0
    assert got["vscode_wsl"] is True and got["codex_side"] == "wsl"


def test_the_flag_outside_wsl_says_it_changed_nothing(fake_home, monkeypatch, capsys):
    monkeypatch.setattr(bootstrap, "bootstrap", lambda *a, **k: 0)
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: None)
    cli.main(["bootstrap", "--vscode-wsl"])
    assert "--vscode-wsl" in capsys.readouterr().out
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_vscode_wsl.py`
Expected: FAIL (`codex_gate() got an unexpected keyword argument 'vscode'`; argparse rejects `--vscode-wsl`; the `--codex-side wsl` gate returns before any VS Code step).

- [ ] **Step 3: Implement in `bootstrap.py`**

After `_offer_vscode`, add:

```python
VSCODE_FLAG_HINT = "or run bootstrap again with --vscode-wsl"


def _vscode_step(cs, ask, interactive: bool, bk, vscode: bool) -> None:
    """Codex runs in WSL: switch VS Code's extension to it (--vscode-wsl), offer it (a terminal), or print the manual
    step (no terminal) when the extension still runs the Windows Codex (spec Part 4)."""
    home = cs.windows_home if cs is not None else None
    if vscode:
        if home is None:
            out.status("VS Code", f"Windows home not found; {wsl.MANUAL}", "warn")
        else:
            out.status("VS Code", wsl.set_vscode_wsl_mode(bk, home) if bk is not None else wsl.MANUAL)
        return
    if interactive:
        _offer_vscode(cs, ask, bk)
    elif cs is not None and cs.vscode_windows:
        out.status("VS Code", f"the Codex extension runs Codex on Windows; {wsl.MANUAL} ({VSCODE_FLAG_HINT})", "warn")
```

Change `codex_gate` to:

```python
def codex_gate(flag, ask, interactive: bool, bk: Backup | None = None, vscode: bool = False) -> str | None:
    """In WSL: None to set up this side's Codex, else the line that explains why not (one loadout per side, ADR 0029).
    vscode: --vscode-wsl, switch VS Code's Codex extension to WSL without asking."""
    if wsl.detect() is None:
        return None
    if flag == "wsl":
        _vscode_step(wsl.codex_side(), ask, interactive, bk, vscode)
        return None
    if flag == "windows":
        return SKIPPED + WINDOWS_WAY
    cs = wsl.codex_side()
    why = "; ".join(cs.reasons)
    if cs.shared_home:
        return (f"Codex step skipped: {why}. One config would be read by both sides, but its commands fit only one. "
                "Unset CODEX_HOME in WSL, or pass --codex-side wsl to set it up anyway")
    if cs.side != "windows":
        if vscode or (cs.side == "both" and cs.vscode_windows):  # Codex in WSL, VS Code's extension may run the other
            _vscode_step(cs, ask, interactive, bk, vscode)
        return None
    if interactive:
        answer = ask("\n" + CODEX_SIDE_QUESTION).strip() or "1"
        if answer == "2":
            return SKIPPED + WINDOWS_WAY
        if answer != "1":
            return (f"{SKIPPED}no such choice ({answer!r}). Re-run and answer 1 or 2, or pass "
                    "--codex-side wsl or --codex-side windows")
        _vscode_step(cs, ask, True, bk, vscode)
        return None
    return (f"Codex step skipped: {why}. Choose a side: --codex-side wsl (with --install, installs Codex in WSL), "
            f"or {WINDOWS_WAY}")
```

Thread the flag: `bootstrap(..., answers=None, vscode_wsl: bool = False)` passes `vscode_wsl` to `_bootstrap(..., answers, vscode_wsl)`; `_bootstrap(..., answers=None, vscode_wsl=False)`; the gate call becomes `codex_gate(codex_side, ask, interactive and not yes, bk, vscode=vscode_wsl)`. Right after that line add:

```python
    if vscode_wsl and not codex_gate_needed(chosen):
        out.status("VS Code", "--vscode-wsl: Codex is not set up in WSL in this run; nothing changed", "warn")
```

- [ ] **Step 4: The CLI flag in `commands.py`**

In `_register_bootstrap`, after `--codex-side`:

```python
    p.add_argument("--vscode-wsl", action="store_true",
                   help="in WSL with Codex: switch VS Code's Codex extension to WSL without asking (backup first)")
```

and in `run(a)`, before the `return`:

```python
        if a.vscode_wsl:
            from . import wsl
            if wsl.detect() is None:
                out.status("VS Code", "--vscode-wsl applies to loadout in WSL only; nothing changed", "warn")
```

and pass `vscode_wsl=a.vscode_wsl` to `bootstrap.bootstrap(...)`.

- [ ] **Step 5: Run the tests**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_vscode_wsl.py tests/test_wsl_codex_bootstrap.py`
Expected: PASS. `test_wsl_codex_bootstrap.py`'s `codex_gate("wsl", ...)` test now also reads the Codex side; if it fails because `codex_side` is not stubbed there, stub it with `wsl.CodexSide("wsl", [])` in that test and ledger the ruling.

- [ ] **Step 6: Whole suite, then commit**

Run: `uv run --python 3.12 --with pytest pytest -q > "$WS/suite1.txt" 2>&1; rc=$?; echo rc=$rc; tail -3 "$WS/suite1.txt"` — commit only when rc=0.

```bash
git add cli/loadout/bootstrap.py cli/loadout/commands.py tests/test_vscode_wsl.py tests/test_wsl_codex_bootstrap.py
git commit -m "feat(bootstrap): --vscode-wsl, and the VS Code switch on every Codex-in-WSL path"
```

---

### Task 2: the `VS Code` row in `loadout check`

**Files:**
- Modify: `cli/loadout/check.py` (`_vscode`, `run_checks`)
- Test: `tests/test_check_vscode.py`

**Interfaces:**
- Consumes: `wsl.CodexSide` (`side`, `windows_home`, `vscode_windows`), `wsl.vscode_wsl_mode`, `wsl.MANUAL`.
- Produces: `check._vscode(cs) -> list[CheckResult]`.

- [ ] **Step 1: Write the failing tests**

```python
"""loadout check in WSL: VS Code's Codex extension must run the WSL Codex (spec Part 4)."""
from loadout import check, wsl


def _home(tmp_path, text):
    home = tmp_path / "winhome"
    p = wsl.vscode_settings(home)
    p.parent.mkdir(parents=True)
    p.write_text(text)
    return home


def test_a_warning_when_the_extension_runs_the_windows_codex(tmp_path):
    home = _home(tmp_path, '{"chatgpt.runCodexInWindowsSubsystemForLinux": false}')
    rows = check._vscode(wsl.CodexSide("wsl", [], windows_home=home, vscode_windows=True))
    assert len(rows) == 1 and rows[0].name == "VS Code" and not rows[0].ok and rows[0].severity == "warn"
    assert "--vscode-wsl" in rows[0].fix and wsl.MANUAL in rows[0].fix


def test_ok_when_it_runs_in_wsl(tmp_path):
    home = _home(tmp_path, '{"chatgpt.runCodexInWindowsSubsystemForLinux": true}')
    rows = check._vscode(wsl.CodexSide("both", [], windows_home=home))
    assert len(rows) == 1 and rows[0].ok


def test_no_row_without_codex_in_wsl_or_vscode(tmp_path):
    home = _home(tmp_path, "{}")
    assert check._vscode(None) == []
    assert check._vscode(wsl.CodexSide("windows", [], windows_home=home, vscode_windows=True)) == []
    assert check._vscode(wsl.CodexSide("wsl", [], windows_home=home)) == []  # no extension, no setting
    assert check._vscode(wsl.CodexSide("wsl", [])) == []


def test_run_checks_includes_the_row(fake_home, fake_runner, monkeypatch, tmp_path):
    home = _home(tmp_path, '{"chatgpt.runCodexInWindowsSubsystemForLinux": false}')
    monkeypatch.setattr(check, "_wsl_codex_side", lambda: wsl.CodexSide("wsl", [], windows_home=home, vscode_windows=True))
    assert any(r.name == "VS Code" and not r.ok for r in check.run_checks())
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_check_vscode.py`
Expected: FAIL (`module 'loadout.check' has no attribute '_vscode'`).

- [ ] **Step 3: Implement**

In `cli/loadout/check.py`, after `_codex_side`:

```python
def _vscode(cs) -> list[CheckResult]:
    """In WSL with Codex in WSL: VS Code's Codex extension must run that Codex too (spec Part 4)."""
    if cs is None or cs.side not in ("wsl", "both") or cs.windows_home is None:
        return []
    if cs.vscode_windows:
        return [CheckResult("VS Code", False, "the Codex extension runs Codex on Windows, not the Codex in WSL",
                            f"loadout bootstrap --codex-side wsl --vscode-wsl, or {wsl.MANUAL}", "warn")]
    if wsl.vscode_wsl_mode(cs.windows_home) is True:
        return [CheckResult("VS Code", True, "the Codex extension runs Codex in WSL")]
    return []
```

In `run_checks`, after `*_codex_side(cs),` add `*_vscode(cs),`.

- [ ] **Step 4: Run, suite, commit**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_check_vscode.py tests/test_check.py` → PASS; then the whole suite into `$WS/suite2.txt`, commit only when rc=0.

```bash
git add cli/loadout/check.py tests/test_check_vscode.py
git commit -m "feat(check): a VS Code row in WSL when the Codex extension runs the Windows Codex"
```

---

### Task 3: backups as data (age, where, what they hold, what goes back)

**Files:**
- Modify: `cli/loadout/backup.py` (`BackupInfo`, `backups`, `age`, `summary`, `where`, `contents`, `_shown`; `list_backups` built on `backups`)
- Test: `tests/test_backup_info.py`

**Interfaces:**
- Produces: `@dataclass BackupInfo(path: Path, created: float, description: str, repo: str | None, steps: list, restored_at: float | None)`; `backups(repo: Path | None = None) -> list[BackupInfo]` (newest first; `repo` keeps only backups whose manifest `repo` is that folder); `age(created: float, now: float | None = None) -> str`; `summary(info) -> str`; `where(info) -> str`; `contents(info) -> list[str]`; `list_backups(repo: Path | None = None) -> list[str]` (format unchanged).

- [ ] **Step 1: Write the failing tests**

```python
"""Backups as data for the restore picker (spec Part 6)."""
import json

from loadout import backup, paths

NOW = 2_000_000_000.0


def make(desc, ago, repo=None, steps=()):
    bk = backup.Backup(description=desc, repo=repo)
    bk._created_at = NOW - ago
    for kind, arg in steps:
        if kind == "copy":
            bk.save_copy(arg, f"{arg.name} before")
        elif kind == "created":
            bk.record_created(arg, f"{arg.name} (created)")
        elif kind == "dir":
            bk.record_created_dir(arg, f"{arg.name}/")
        elif kind == "run":
            bk.record_command("plugin x", arg)
    if bk.empty:
        bk._ensure_root()  # its own folder: two backups in one second must not share one
        bk._save()
    return bk


def test_backups_are_newest_first_and_filtered_by_repo(fake_home, tmp_path):
    repo = tmp_path / "repo"
    make("old", 7200)
    make("new", 60, repo=repo)
    assert [b.description for b in backup.backups()] == ["new", "old"]
    assert [b.description for b in backup.backups(repo)] == ["new"]


def test_age_reads_like_a_person_says_it():
    assert backup.age(NOW - 5, NOW) == "just now"
    assert backup.age(NOW - 60, NOW) == "1 minute ago"
    assert backup.age(NOW - 7200, NOW) == "2 hours ago"
    assert backup.age(NOW - 3 * 86400, NOW) == "3 days ago"


def test_summary_and_where(fake_home, tmp_path):
    f = tmp_path / "a.json"
    f.write_text("{}")
    repo = tmp_path / "repo"
    make("x", 10, repo=repo, steps=[("copy", f), ("created", tmp_path / "b"), ("dir", tmp_path / "d"),
                                    ("run", ["claude", "plugin", "uninstall", "x"])])
    info = backup.backups()[0]
    assert backup.summary(info) == "2 files, 1 folder, 1 command"
    assert backup.where(info) == f"repo {repo}"
    make("y", 5)
    assert backup.where(backup.backups()[0]) == "home"


def test_contents_name_each_file_and_command_with_secrets_masked(fake_home, tmp_path):
    f = tmp_path / "a.json"
    f.write_text("{}")
    token = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
    make("x", 10, steps=[("copy", f), ("run", ["claude", "mcp", "add-json", "gh", '{"env":{"T":"' + token + '"}}'])])
    lines = backup.contents(backup.backups()[0])
    assert lines[0].startswith("run: claude mcp add-json gh") and token not in lines[0]
    assert lines[1].startswith(f"put back {f}")


def test_a_damaged_manifest_never_crashes(fake_home):
    root = paths.backups_root()
    for name, steps in (("loadout-1", "x"), ("loadout-2", [{"label": "odd", "undo": "x"}, {"label": "pair", "undo": {"restore-file": "x"}}])):
        (root / name).mkdir(parents=True)
        (root / name / "manifest.json").write_text(json.dumps({"description": name, "created_at": 1, "steps": steps}))
    infos = backup.backups()
    assert [b.description for b in infos] == ["loadout-2"]
    assert all(isinstance(l, str) for l in backup.contents(infos[0]))
    assert backup.summary(infos[0]) == "1 file"  # the damaged restore-file still counts; contents names it as unknown
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_backup_info.py`
Expected: FAIL (`module 'loadout.backup' has no attribute 'backups'`).

- [ ] **Step 3: Implement in `backup.py`**

Add `from dataclasses import dataclass` to the imports (and `from .secrets import redact` if not imported; `redact` is used by `restore` already). Replace `list_backups` with:

```python
@dataclass
class BackupInfo:
    path: Path
    created: float
    description: str
    repo: str | None
    steps: list
    restored_at: float | None


def backups(repo: Path | None = None) -> list[BackupInfo]:
    """loadout's backups, newest first; with `repo`, only the ones made for that repo. A symlinked folder or a damaged
    manifest is left out (restore refuses it too)."""
    root = paths.backups_root()
    want = os.path.realpath(repo) if repo is not None else None
    found = []
    for d in root.iterdir() if root.is_dir() else []:
        if d.is_symlink() or not (d / "manifest.json").is_file():
            continue
        try:
            data = load_json(d / "manifest.json")
        except Exception:
            continue
        steps = data.get("steps", [])
        if not isinstance(steps, list):
            continue
        created = data.get("created_at")
        created = created if isinstance(created, (int, float)) and created > 0 else (d / "manifest.json").stat().st_mtime
        rep = data.get("repo") if isinstance(data.get("repo"), str) else None
        if want is not None and (rep is None or os.path.realpath(rep) != want):
            continue
        restored = data.get("restored_at")
        found.append(BackupInfo(d, created, str(data.get("description") or ""), rep,
                                [s for s in steps if isinstance(s, dict)],
                                restored if isinstance(restored, (int, float)) else (1.0 if restored else None)))
    return sorted(found, key=lambda b: (b.created, b.path.name), reverse=True)


def _shown(path) -> str:
    text, home = str(path), str(paths.home())
    return "~" + text[len(home):] if text.startswith(home) else text


def age(created: float, now: float | None = None) -> str:
    seconds = max(0, int((time.time() if now is None else now) - created))
    for unit, size in (("day", 86400), ("hour", 3600), ("minute", 60)):
        if seconds >= size:
            n = seconds // size
            return f"{n} {unit}{'s' if n != 1 else ''} ago"
    return "just now"


def _undo_of(step: dict) -> dict:
    undo = step.get("undo")
    return undo if isinstance(undo, dict) else {}


def summary(info: BackupInfo) -> str:
    kinds = [_undo_of(s) for s in info.steps]
    files = sum(1 for u in kinds if any(k in u for k in ("restore-file", "move", "created", "kept")))
    folders = sum(1 for u in kinds if "created-dir" in u)
    commands = sum(1 for u in kinds if "run" in u)
    parts = [f"{n} {word}{'s' if n != 1 else ''}" for n, word in ((files, "file"), (folders, "folder"),
                                                                  (commands, "command")) if n]
    return ", ".join(parts) or "nothing to undo"


def where(info: BackupInfo) -> str:
    return f"repo {_shown(info.repo)}" if info.repo else "home"


def _pair_target(value) -> str | None:
    return str(value[1]) if isinstance(value, list) and len(value) == 2 else None


def contents(info: BackupInfo) -> list[str]:
    """What a restore does, step by step in the order it runs (newest first); undo commands with secrets masked."""
    out = []
    for step in reversed(info.steps):
        undo, label = _undo_of(step), redact(str(step.get("label", "?")))
        done = " (already restored)" if step.get("restored") else ""
        if "restore-file" in undo and _pair_target(undo["restore-file"]):
            what = f"put back {_shown(_pair_target(undo['restore-file']))}"
        elif "move" in undo and _pair_target(undo["move"]):
            what = f"move back {_shown(_pair_target(undo['move']))}"
        elif "created" in undo:
            what = f"take away {_shown(undo['created'])} (loadout created it)"
        elif "created-dir" in undo:
            what = f"remove the folder {_shown(undo['created-dir'])} if it is empty"
        elif "run" in undo and isinstance(undo["run"], list):
            what = "run: " + redact(" ".join(map(str, undo["run"])))
        elif "kept" in undo:
            what = "nothing automatic: the old value is kept in the backup"
        else:
            what = "unknown step, left as is"
        out.append(f"{what}  [{label}]{done}")
    return out


def list_backups(repo: Path | None = None) -> list[str]:
    out = []
    for b in backups(repo):
        n = len(b.steps)
        state = "restored " + _stamp(b.restored_at) if b.restored_at else "not restored"
        desc = f"  {b.description}" if b.description else ""
        out.append(f"{_shown(b.path)}  {_stamp(b.created)}  {n} step{'s' if n != 1 else ''}  {state}{desc}")
    return out
```

`backups()` keeps only dict steps, so the list's step count may be lower than before for a damaged manifest; check that no existing test asserts the old count for one (grep `list_backups` in `tests/`), and ledger it if one does.

- [ ] **Step 4: Run, suite, commit**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_backup_info.py tests/test_backup.py` → PASS (the existing `list_backups` tests keep their format); the whole suite into `$WS/suite3.txt`, commit only when rc=0.

```bash
git add cli/loadout/backup.py tests/test_backup_info.py
git commit -m "feat(restore): backups as data: age, where, what they hold, what goes back"
```

---

### Task 4: the picker

**Files:**
- Create: `cli/loadout/restore_cmd.py`
- Modify: `cli/loadout/commands.py` (`_register_restore`)
- Test: `tests/test_restore_picker.py`

**Interfaces:**
- Consumes: Task 3 `backups`, `age`, `summary`, `where`, `contents`, `list_backups`, `_stamp`, `_shown`; `backup.restore(root, force)`.
- Produces: `restore_cmd.run(path, list_only, last, repo, force, ask, interactive, now=None) -> int`; `QUESTION = "Restore which? [1-{n}, m = more, Enter = cancel] "`; `CONFIRM = "Restore this? [y/N] "`; `PAGE = 10`.

- [ ] **Step 1: Write the failing tests**

```python
"""loadout restore picks a backup (spec Part 6)."""
import pytest

from loadout import __main__ as cli, backup, restore_cmd

NOW = 2_000_000_000.0


def make(desc, ago, tmp_path, repo=None):
    f = tmp_path / f"{desc}.txt"
    f.write_text(desc)
    bk = backup.Backup(description=desc, repo=repo)
    bk._created_at = NOW - ago
    bk.record_created(f, f"{desc} (created)")
    return f


def answers(*values):
    it = iter(values)
    asked = []
    return asked, (lambda q: asked.append(q) or next(it))


def test_it_shows_ten_numbered_then_more_then_restores_the_pick(fake_home, fake_runner, tmp_path, capsys):
    files = [make(f"b{i}", 3600 * (i + 1), tmp_path) for i in range(12)]  # b0 newest
    asked, ask = answers("m", "12", "y")
    assert restore_cmd.run(None, False, False, None, False, ask, True, now=NOW) == 0
    printed = capsys.readouterr().out
    assert asked[0] == "Restore which? [1-10, m = more, Enter = cancel] "
    assert asked[1] == "Restore which? [1-12, m = more, Enter = cancel] " and asked[2] == restore_cmd.CONFIRM
    assert " 1  1 hour ago" in printed and "12  12 hours ago" in printed and "home" in printed and "1 file" in printed
    assert "take away" in printed and str(files[11]) in printed
    assert not files[11].exists() and files[0].exists()


def test_enter_cancels_and_no_restores_nothing(fake_home, fake_runner, tmp_path, capsys):
    f = make("a", 60, tmp_path)
    _, ask = answers("")
    assert restore_cmd.run(None, False, False, None, False, ask, True, now=NOW) == 0
    _, ask = answers("1", "n")
    assert restore_cmd.run(None, False, False, None, False, ask, True, now=NOW) == 0
    assert f.exists() and capsys.readouterr().out.count("nothing restored") == 2


@pytest.mark.parametrize("bad", ["0", "2", "abc"])
def test_a_wrong_answer_is_asked_again_three_times_at_most(fake_home, fake_runner, tmp_path, bad):
    f = make("a", 60, tmp_path)
    asked, ask = answers(bad, bad, bad)
    assert restore_cmd.run(None, False, False, None, False, ask, True, now=NOW) == 0
    assert len(asked) == 3 and f.exists()


def test_more_when_there_is_no_more_says_so(fake_home, fake_runner, tmp_path, capsys):
    make("a", 60, tmp_path)
    _, ask = answers("m", "")
    restore_cmd.run(None, False, False, None, False, ask, True, now=NOW)
    assert "no more backups" in capsys.readouterr().out


def test_an_already_restored_pick_is_refused_before_the_question(fake_home, fake_runner, tmp_path, capsys):
    make("a", 60, tmp_path)
    backup.restore(backup.backups()[0].path)
    asked, ask = answers("1")
    assert restore_cmd.run(None, False, False, None, False, ask, True, now=NOW) == 1
    assert len(asked) == 1 and "--force" in capsys.readouterr().out


def test_without_a_terminal_nothing_is_picked(fake_home, fake_runner, tmp_path, capsys):
    f = make("a", 60, tmp_path)
    assert restore_cmd.run(None, False, False, None, False, lambda q: pytest.fail("asked"), False, now=NOW) == 0
    printed = capsys.readouterr().out
    assert "--last" in printed and f.exists()


def test_last_restores_the_newest_and_shows_what_goes_back(fake_home, fake_runner, tmp_path, capsys):
    old, new = make("old", 7200, tmp_path), make("new", 60, tmp_path)
    assert restore_cmd.run(None, False, True, None, False, lambda q: pytest.fail("asked"), False, now=NOW) == 0
    assert not new.exists() and old.exists() and "take away" in capsys.readouterr().out


def test_repo_filters_and_list_prints(fake_home, fake_runner, tmp_path, capsys):
    repo = tmp_path / "repo"
    make("home-one", 60, tmp_path)
    make("repo-one", 120, tmp_path, repo=repo)
    assert restore_cmd.run(None, True, False, str(repo), False, lambda q: "", False, now=NOW) == 0
    printed = capsys.readouterr().out
    assert "repo-one" in printed and "home-one" not in printed


def test_the_cli_flags_reach_the_picker(fake_home, monkeypatch):
    got = {}
    monkeypatch.setattr(restore_cmd, "run", lambda *a, **k: got.update(args=a) or 0)
    assert cli.main(["restore", "--last", "--repo", "x"]) == 0
    path, list_only, last, repo, force = got["args"][:5]
    assert (path, list_only, last, repo, force) == (None, False, True, "x", False)
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_restore_picker.py`
Expected: FAIL (`cannot import name 'restore_cmd'`).

- [ ] **Step 3: Write `restore_cmd.py`**

```python
"""`loadout restore`: a path, --last, --list, or (in a terminal) a numbered pick of recent backups (spec Part 6)."""
from __future__ import annotations

from pathlib import Path

from . import backup, ui

PAGE = 10
QUESTION = "Restore which? [1-{n}, m = more, Enter = cancel] "
CONFIRM = "Restore this? [y/N] "
NO_TERMINAL = "no terminal: nothing picked. Restore one with `loadout restore <path>` or the newest with `loadout restore --last`"


def _restore(root: Path, force: bool) -> int:
    lines, ok, pre = backup.restore(root, force=force)
    for line in lines:
        print(line)
    if pre is not None:
        print(f"\nthe state this restore replaced is in {pre}  (undo this restore: loadout restore {pre})")
    return 0 if ok else 1


def _row(i: int, b: backup.BackupInfo, now) -> str:
    state = f"  restored {backup._stamp(b.restored_at)}" if b.restored_at else ""
    return (f"{i:>3}  {backup.age(b.created, now)} ({backup._stamp(b.created)})  {b.description or '(no description)'}"
            f"  {backup.where(b)}  {backup.summary(b)}{state}")


def _show(b: backup.BackupInfo) -> None:
    print(f"{backup._shown(b.path)} ({b.description or 'no description'}) does this:")
    for line in backup.contents(b) or ["nothing to undo"]:
        print(f"  {line}")


def run(path, list_only: bool, last: bool, repo, force: bool, ask, interactive: bool, now=None) -> int:
    if path:
        return _restore(Path(path).expanduser(), force)
    found = backup.backups(Path(repo).expanduser() if repo else None)
    if not found:
        print(f"no backups for repo {repo}" if repo else "no backups yet")
        return 0
    if list_only:
        print("\n".join(backup.list_backups(Path(repo).expanduser() if repo else None)))
        print("\nundo one: loadout restore <path from the first column>")
        return 0
    if last:
        _show(found[0])
        return _restore(found[0].path, force)
    if not interactive:
        print("\n".join(backup.list_backups(Path(repo).expanduser() if repo else None)))
        print(NO_TERMINAL)
        return 0
    shown, wrong = 0, 0
    pick = None
    while pick is None:
        if shown == 0:
            shown = min(PAGE, len(found))
            print("\n".join(_row(i + 1, b, now) for i, b in enumerate(found[:shown])))
        answer = ask(QUESTION.format(n=shown)).strip().lower()
        if answer == "":
            print("nothing restored")
            return 0
        if answer == "m":
            if shown >= len(found):
                print("no more backups")
            else:
                more = found[shown:shown + PAGE]
                print("\n".join(_row(shown + i + 1, b, now) for i, b in enumerate(more)))
                shown += len(more)
            continue
        if answer.isdigit() and 1 <= int(answer) <= shown:
            pick = found[int(answer) - 1]
            break
        wrong += 1
        if wrong >= 3:
            print("nothing restored")
            return 0
        print(f"answer a number from 1 to {shown}, m or Enter")
    _show(pick)
    if pick.restored_at and not force:
        print(f"already restored on {backup._stamp(pick.restored_at)}; replay it with "
              f"`loadout restore --force {backup._shown(pick.path)}`")
        return 1
    if not ui.confirm(ask, CONFIRM):
        print("nothing restored")
        return 0
    return _restore(pick.path, force)
```


- [ ] **Step 4: Wire `commands.py`**

Replace `_register_restore`'s arguments and `run` with:

```python
    p = sub.add_parser("restore", help="undo a loadout backup (without a path: pick one of the recent backups)")
    p.add_argument("backup_dir", nargs="?", help="backup directory printed by bootstrap/adopt, e.g. ~/.local/state/loadout/backups/loadout-<timestamp>")
    p.add_argument("--list", action="store_true", help="list backups, newest first")
    p.add_argument("--last", action="store_true", help="restore the newest backup (with --repo: the repo's newest)")
    p.add_argument("--repo", metavar="PATH", help="only the backups made for this repo")
    p.add_argument("--force", action="store_true", help="replay a backup that was already restored")

    def run(args):
        from . import restore_cmd, ui
        from .__main__ import _ask
        return restore_cmd.run(args.backup_dir, args.list, args.last, args.repo, args.force, _ask, ui.is_interactive())
```

- [ ] **Step 5: Run, suite, commit**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_restore_picker.py tests/test_backup.py` → PASS. Then the whole suite into `$WS/suite4.txt`; existing tests that ran `loadout restore` without a path and expected `usage: loadout restore DIR` now get the no-terminal list and `NO_TERMINAL`: update them, ledger the ruling. Commit only when rc=0.

```bash
git add cli/loadout/restore_cmd.py cli/loadout/commands.py tests/
git commit -m "feat(restore): pick one of the recent backups by number, see what goes back, then confirm"
```

---

### Task 5: docs (Part 4 lines and category E)

**Files:**
- Modify: `docs/reference/cli.md` (bootstrap `--vscode-wsl`; check `VS Code` row; restore section), `docs/how-to/undo-and-restore.md`, `docs/how-to/setups.md` (row "WSL 2, Codex in WSL"), `docs/how-to/wsl.md`, `docs/how-to/troubleshooting.md` (restore row), `plugins/loadout/skills/configure/SKILL.md` (restore line), `docs/superpowers/plans/2026-10-16-repo-agents-docs-baseline.md` (E done)

- [ ] **Step 1: Find every line**

Run: `grep -rn "restore --list\|copy the path\|loadout restore <\|restore DIR\|--codex-side wsl\|neither asks nor offers\|runCodexInWindowsSubsystemForLinux" README.md docs plugins/loadout/skills .serena/memories --include=*.md | grep -v superpowers`

- [ ] **Step 2: Update them**

- `cli.md`, bootstrap flags table: add `| --vscode-wsl | In WSL with Codex: switch VS Code's Codex extension to WSL without asking (only \`chatgpt.runCodexInWindowsSubsystemForLinux\`; a copy of settings.json is saved first, \`loadout restore\` undoes it). Without it and without a terminal, bootstrap prints the manual step. |`; in the bootstrap text, say that with `--codex-side wsl` in a terminal bootstrap also asks the VS Code question.
- `cli.md`, `loadout check`: a `VS Code` row in WSL with Codex in WSL: warns when the extension runs Codex on Windows, with the fix `loadout bootstrap --codex-side wsl --vscode-wsl` or the manual step.
- `cli.md`, `loadout restore`: the usage line `loadout restore [--list] [--last] [--repo PATH] [--force] [DIR]`; the picker (what each row shows, the prompt, `m`, Enter, three wrong answers, the confirm, already restored → `--force`); `--last`, `--repo`, `--list`; "Without a terminal nothing is picked"; exit codes unchanged (0, 1 when a step failed or a picked backup was already restored).
- `undo-and-restore.md`: the main path becomes `loadout restore` (pick by number) for people, `--last`/`--list`/a path for agents and scripts; keep the page's other facts.
- `setups.md` row "WSL 2, Codex in WSL": replace "Without a terminal add `--codex-side wsl`; bootstrap then neither asks nor offers the switch, so set the VS Code setting by hand" with "Without a terminal add `--codex-side wsl --vscode-wsl` (the switch, with a backup), or set the VS Code setting by hand".
- `wsl.md`: the same flag where the VS Code switch is described.
- `troubleshooting.md` and the configure skill: restore lines say `loadout restore` picks; `--last` for the newest.
- The docs baseline plan: under its header line "B: done in repo-agents PR 2." add "E: done in repo-agents PR 4."

- [ ] **Step 3: Suite, validation, commit**

Run: `uv run --python 3.12 --with pytest pytest -q > "$WS/suite5.txt" 2>&1; rc=$?; echo rc=$rc; tail -3 "$WS/suite5.txt"; claude plugin validate . && claude plugin validate plugins/loadout` — commit only when rc=0.

```bash
git add docs plugins
git commit -m "docs: --vscode-wsl, the VS Code check row, and restore picks a backup"
```
