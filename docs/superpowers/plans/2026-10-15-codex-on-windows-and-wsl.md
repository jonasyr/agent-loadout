# Codex on Windows and WSL Implementation Plan — PR B

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In WSL, loadout knows which side the user's Codex runs on and never silently sets up a Codex home that the active Codex does not read; each side gets its own loadout, and each side's `loadout check` reports the other one read-only.

**Architecture:** A new `wsl.codex_side()` reads the signals (Linux or Windows `codex` on PATH, recent sessions in the Windows Codex home, the VS Code extension's WSL setting, `CODEX_HOME`). Bootstrap's Codex step asks it before `codex.apply_all` and stops with clear options when the active Codex is the Windows one (`--codex-side wsl|windows` decides without a terminal). An opt-in edit sets the VS Code setting. `loadout check` gets a "Codex (Windows side)" line; WSL checks follow the agents that are on; `init`/`profile` note repos on `/mnt/<drive>`.

**Tech Stack:** Python 3.11+ standard library, pytest.

**Spec:** `docs/superpowers/specs/2026-10-15-codex-anywhere-design.md` (section "PR B"; decision 2: option A, one loadout per side)

## Global Constraints

- One loadout per side: loadout in WSL configures only the WSL `~/.codex` (or `$CODEX_HOME`); it reads the Windows side only to report. It never writes the Windows Codex home.
- The VS Code setting `chatgpt.runCodexInWindowsSubsystemForLinux` is changed only after the user's yes, with a backup copy first; `loadout restore` reverts it.
- Tests use `fake_home` and `fake_runner`; never the real `/mnt/c`, `cmd.exe` or `~/.codex`. Windows-side paths in tests are folders under `tmp_path`.
- With Codex off, no Codex-side signal is read and nothing Codex-related is printed.
- Conventional Commits; git as `/usr/bin/git`; tests `uv run --python 3.12 --with pytest pytest -q`.

## Review Focus

- `cmd.exe` missing or failing (WSL without interop): `codex_side()` still answers from PATH and `CODEX_HOME`; no crash, no hang (Task 1 test).
- An extensionless Windows npm shim `codex` under `/mnt/c/.../npm` on PATH: counts as Windows, and `--install` installs a Linux Codex instead of accepting the shim (Task 2 test).
- VS Code `settings.json` with comments and trailing commas (JSONC): the setting is read and changed by a text edit that leaves every other byte alone (Task 3 test).
- Non-interactive bootstrap with only a Windows Codex and no `--codex-side`: Codex step stops with both options; the rest of bootstrap runs; exit code unchanged (Task 2 test).
- Codex off: `codex_side()` is never called by bootstrap or check (Task 2 and 4 tests).

---

### Task 1: `wsl.codex_side()`

**Files:** Modify `cli/loadout/wsl.py`; Test `tests/test_wsl_codex_side.py` (create)

**Interfaces:** Produces `wsl.CodexSide` (dataclass: `side: str` in {"wsl","windows","both","none"}, `reasons: list[str]`, `windows_home: Path | None`, `windows_used: bool`, `shared_home: bool`), `wsl.codex_side(mount: str = "/mnt/") -> CodexSide`, `wsl.windows_home() -> Path | None`, `wsl.vscode_settings(home: Path) -> Path`, `wsl.vscode_wsl_mode(home: Path) -> bool | None`, `wsl.WIN_SETTING`.

- [ ] **Step 1: Write the failing tests**

```python
"""Which side the user's Codex runs on, seen from WSL (spec PR B)."""
import os
import time

import pytest

from loadout import runner, wsl


@pytest.fixture
def win(tmp_path, fake_home, fake_runner, monkeypatch):
    home = tmp_path / "mnt" / "c" / "Users" / "u"
    home.mkdir(parents=True)
    monkeypatch.setattr(wsl, "windows_home", lambda: home)
    monkeypatch.delenv("CODEX_HOME", raising=False)
    return home


def _sessions(home, age_days=1):
    f = home / ".codex" / "sessions" / "2026" / "10" / "15" / "rollout.jsonl"
    f.parent.mkdir(parents=True)
    f.write_text("{}")
    t = time.time() - age_days * 86400
    os.utime(f, (t, t))


def _vscode(home, text):
    p = wsl.vscode_settings(home)
    p.parent.mkdir(parents=True)
    p.write_text(text)


def test_a_linux_codex_alone_is_the_wsl_side(win, fake_runner):
    fake_runner.paths["codex"] = "/home/u/.local/share/mise/shims/codex"
    assert wsl.codex_side(mount=str(win.parents[2]) + "/").side == "wsl"


def test_only_a_windows_codex_is_the_windows_side(win, fake_runner):
    fake_runner.paths["codex"] = str(win.parents[2] / "c" / "Users" / "u" / "AppData" / "Roaming" / "npm" / "codex")
    cs = wsl.codex_side(mount=str(win.parents[2]) + "/")
    assert cs.side == "windows" and any("Windows" in r for r in cs.reasons)


def test_recent_windows_sessions_next_to_a_linux_codex_is_both(win, fake_runner):
    fake_runner.paths["codex"] = "/usr/local/bin/codex"
    _sessions(win)
    cs = wsl.codex_side(mount=str(win.parents[2]) + "/")
    assert cs.side == "both" and cs.windows_used


def test_old_windows_sessions_do_not_count(win, fake_runner):
    fake_runner.paths["codex"] = "/usr/local/bin/codex"
    _sessions(win, age_days=90)
    assert wsl.codex_side(mount=str(win.parents[2]) + "/").side == "wsl"


@pytest.mark.parametrize("text, mode", [
    ('{\n  // mine\n  "chatgpt.runCodexInWindowsSubsystemForLinux": true,\n}\n', True),
    ('{"chatgpt.runCodexInWindowsSubsystemForLinux": false}', False),
    ('{"editor.tabSize": 2}', None),
])
def test_the_vscode_setting_is_read_from_jsonc(win, text, mode):
    _vscode(win, text)
    assert wsl.vscode_wsl_mode(win) is mode


def test_vscode_in_windows_mode_without_a_linux_codex_is_windows(win, fake_runner):
    _vscode(win, '{"chatgpt.runCodexInWindowsSubsystemForLinux": false}')
    assert wsl.codex_side(mount=str(win.parents[2]) + "/").side == "windows"


def test_codex_home_under_mnt_is_shared(win, fake_runner, monkeypatch):
    fake_runner.paths["codex"] = "/usr/local/bin/codex"
    monkeypatch.setenv("CODEX_HOME", str(win / ".codex"))
    assert wsl.codex_side(mount=str(win.parents[2]) + "/").shared_home


def test_no_codex_anywhere_is_none(win):
    assert wsl.codex_side(mount=str(win.parents[2]) + "/").side == "none"


def test_windows_home_survives_a_missing_cmd_exe(fake_home, fake_runner):
    fake_runner.responses[("cmd.exe",)] = runner.Result(127, "", "cmd.exe: not found")
    assert wsl.windows_home() is None


def test_windows_home_from_cmd_and_wslpath(tmp_path, fake_home, fake_runner):
    target = tmp_path / "c" / "Users" / "u"
    target.mkdir(parents=True)
    fake_runner.responses[("cmd.exe",)] = runner.Result(0, "C:\\Users\\u\r\n", "")
    fake_runner.responses[("wslpath",)] = runner.Result(0, f"{target}\n", "")
    assert wsl.windows_home() == target
```

- [ ] **Step 2: Run** `uv run --python 3.12 --with pytest pytest -q tests/test_wsl_codex_side.py` → FAIL (`AttributeError: module 'loadout.wsl' has no attribute 'vscode_settings'` / `codex_side`).

- [ ] **Step 3: Implement** in `cli/loadout/wsl.py` (add `import os, re, time` and `from dataclasses import dataclass, field`):

```python
WIN_SETTING = "chatgpt.runCodexInWindowsSubsystemForLinux"  # the Codex extension's choice (Windows only)
RECENT_DAYS = 30


@dataclass
class CodexSide:
    side: str  # "wsl", "windows", "both" or "none"
    reasons: list[str] = field(default_factory=list)
    windows_home: Path | None = None
    windows_used: bool = False
    shared_home: bool = False


def windows_home() -> Path | None:
    """The Windows user's home as a WSL path (/mnt/c/Users/<name>), via cmd.exe and wslpath; None without interop."""
    cwd = "/mnt/c" if Path("/mnt/c").is_dir() else None  # cmd.exe warns about a Linux (UNC) working folder
    res = runner.run(["cmd.exe", "/c", "echo", "%USERPROFILE%"], cwd=cwd, timeout=15)
    win = res.stdout.strip().splitlines()[-1].strip() if res.ok and res.stdout.strip() else ""
    if not win or "%" in win:
        return None
    conv = runner.run(["wslpath", "-u", win], timeout=15)
    path = Path(conv.stdout.strip()) if conv.ok and conv.stdout.strip() else None
    return path if path is not None and path.is_dir() else None


def vscode_settings(home: Path) -> Path:
    return home / "AppData" / "Roaming" / "Code" / "User" / "settings.json"


_SETTING_RX = re.compile(r'"chatgpt\.runCodexInWindowsSubsystemForLinux"\s*:\s*(true|false)')


def vscode_wsl_mode(home: Path) -> bool | None:
    """The extension's WSL switch from VS Code's settings.json (JSONC: read by text); None when not set."""
    try:
        m = _SETTING_RX.search(vscode_settings(home).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return None
    return None if m is None else m.group(1) == "true"


def _recent(folder: Path, days: int = RECENT_DAYS) -> bool:
    cutoff = time.time() - days * 86400
    try:
        return any(f.stat().st_mtime >= cutoff for f in folder.rglob("*.jsonl"))
    except OSError:
        return False


def codex_side(mount: str = "/mnt/") -> CodexSide:
    """Which side of WSL the user's Codex runs on, from read-only signals (docs/how-to/wsl.md#codex)."""
    found = runner.which("codex")
    linux = bool(found) and not _on_windows_drive(Path(found), mount)
    windows_bin = (bool(found) and not linux) or bool(runner.which("codex.exe"))
    home = windows_home()
    used = home is not None and _recent(home / ".codex" / "sessions")
    mode = vscode_wsl_mode(home) if home is not None else None
    codex_home = os.environ.get("CODEX_HOME", "")
    shared = bool(codex_home) and _on_windows_drive(Path(codex_home), mount)
    reasons = []
    if linux:
        reasons.append(f"Codex in WSL: {found}")
    if windows_bin:
        reasons.append(f"a Windows Codex is on PATH{f' ({found})' if found and not linux else ''}")
    if used:
        reasons.append(f"the Windows Codex home ({home / '.codex'}) has sessions from the last {RECENT_DAYS} days")
    if mode is True:
        reasons.append(f"VS Code runs Codex in WSL ({WIN_SETTING} = true)")
    elif mode is False:
        reasons.append(f"VS Code runs Codex on Windows ({WIN_SETTING} = false)")
    if shared:
        reasons.append(f"CODEX_HOME points into Windows ({codex_home})")
    wsl_side, win_side = linux or mode is True, windows_bin or used or mode is False
    side = "both" if wsl_side and win_side else "wsl" if wsl_side else "windows" if win_side else "none"
    return CodexSide(side, reasons, home, used, shared)
```

- [ ] **Step 4: Run** the tests → PASS. **Step 5: Commit** — `feat(wsl): tell which side of WSL the user's Codex runs on`

### Task 2: Bootstrap's Codex step follows the side

**Files:** Modify `cli/loadout/bootstrap.py` (`_choose_agents`, the Codex step, `check_prereqs` codex install), `cli/loadout/commands.py` (`--codex-side`); Test `tests/test_wsl_codex_bootstrap.py` (create)

**Interfaces:** Consumes Task 1. Produces `bootstrap.codex_gate(flag: str | None, ask, interactive: bool) -> str | None` (None = go on and set up this side; a string = the line to print, Codex step skipped) and `bootstrap(..., codex_side: str | None = None)`.

- [ ] **Step 1: Write the failing tests**

```python
"""Bootstrap in WSL never sets up a Codex home the active Codex does not read (spec PR B)."""
import pytest

from loadout import bootstrap, wsl


def _side(monkeypatch, side, **kw):
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)
    monkeypatch.setattr(wsl, "codex_side", lambda **k: wsl.CodexSide(side, [f"reason {side}"], **kw))


def test_outside_wsl_the_gate_is_open(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: None)
    assert bootstrap.codex_gate(None, ask=lambda q: "", interactive=False) is None


@pytest.mark.parametrize("side", ["wsl", "both", "none"])
def test_a_wsl_side_is_set_up(fake_home, fake_runner, monkeypatch, side):
    _side(monkeypatch, side)
    assert bootstrap.codex_gate(None, ask=lambda q: "", interactive=False) is None


def test_only_windows_without_a_terminal_stops_with_both_ways(fake_home, fake_runner, monkeypatch):
    _side(monkeypatch, "windows")
    line = bootstrap.codex_gate(None, ask=lambda q: "", interactive=False)
    assert "--codex-side wsl" in line and "bootstrap.ps1" in line and "reason windows" in line


def test_the_flag_decides(fake_home, fake_runner, monkeypatch):
    _side(monkeypatch, "windows")
    assert bootstrap.codex_gate("wsl", ask=lambda q: "", interactive=False) is None
    assert "bootstrap.ps1" in bootstrap.codex_gate("windows", ask=lambda q: "", interactive=False)


def test_the_question_decides(fake_home, fake_runner, monkeypatch):
    _side(monkeypatch, "windows")
    assert bootstrap.codex_gate(None, ask=lambda q: "1", interactive=True) is None
    assert "bootstrap.ps1" in bootstrap.codex_gate(None, ask=lambda q: "2", interactive=True)


def test_a_shared_codex_home_needs_the_flag(fake_home, fake_runner, monkeypatch):
    _side(monkeypatch, "wsl", shared_home=True)
    assert "CODEX_HOME" in bootstrap.codex_gate(None, ask=lambda q: "", interactive=True)
    assert bootstrap.codex_gate("wsl", ask=lambda q: "", interactive=True) is None


def test_a_windows_codex_on_path_still_gets_the_agent_question(fake_home, fake_runner, monkeypatch):
    (bootstrap.paths.personal_root()).mkdir(parents=True)  # an existing layer that never chose
    fake_runner.missing.add("codex")
    fake_runner.paths["codex.exe"] = "/mnt/c/Program Files/codex/codex.exe"
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)
    asked = []
    bootstrap._choose_agents(lambda q: asked.append(q) or "2", interactive=True, flag=None)
    assert asked


def test_codex_off_never_reads_the_side(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(wsl, "codex_side", lambda **k: pytest.fail("read the Codex side with Codex off"))
    # bootstrap with --agents claude must not call it; run the Codex-step helper the way _bootstrap does
    assert bootstrap.codex_gate_needed({"claude": True, "codex": False}) is False
```

- [ ] **Step 2: Run** → FAIL (`codex_gate` missing).

- [ ] **Step 3: Implement** in `cli/loadout/bootstrap.py`:

```python
CODEX_SIDE_QUESTION = ("Your Codex runs on Windows. Set loadout up for:  1) Codex in WSL (installs Codex here; switch the "
                       "VS Code extension to WSL)  2) Codex on Windows (run bootstrap.ps1 in PowerShell)  [1] ")
WINDOWS_WAY = ("Codex on Windows: run loadout's bootstrap.ps1 in PowerShell there, with the same personal layer "
               "(docs/how-to/wsl.md#codex)")


def codex_gate_needed(chosen: dict) -> bool:
    from . import wsl
    return bool(chosen.get("codex")) and wsl.detect() is not None


def codex_gate(flag, ask, interactive: bool) -> str | None:
    """In WSL: None to set up this side's Codex, else the line that explains why not (one loadout per side, ADR 0029)."""
    from . import wsl
    if wsl.detect() is None or flag == "wsl":
        return None
    if flag == "windows":
        return WINDOWS_WAY
    cs = wsl.codex_side()
    why = "; ".join(cs.reasons)
    if cs.shared_home:
        return (f"Codex step skipped: {why}. One config would be read by both sides, but its commands fit only one. "
                "Unset CODEX_HOME in WSL, or pass --codex-side wsl to set it up anyway")
    if cs.side != "windows":
        return None
    if interactive:
        return None if (ask("\n" + CODEX_SIDE_QUESTION).strip() or "1") == "1" else WINDOWS_WAY
    return (f"Codex step skipped: {why}. Choose a side: --codex-side wsl (with --install, installs Codex in WSL), "
            f"or {WINDOWS_WAY}")
```

In `_bootstrap`'s Codex step, before `codex.unavailable()`:

```python
    if chosen["codex"]:
        _step("Codex")
        gate = codex_gate(codex_side, ask, interactive) if codex_gate_needed(chosen) else None
        if gate is not None:
            out.status("Codex", gate, "warn")
        else:
            problem = codex.unavailable()
            ...  # unchanged
```

`_bootstrap` and `bootstrap` gain `codex_side: str | None = None`; `commands._register_bootstrap` adds `p.add_argument("--codex-side", choices=("wsl", "windows"), help="in WSL: set up Codex here (wsl) or leave it to bootstrap.ps1 on Windows (windows)")` and passes `codex_side=a.codex_side`.

`_choose_agents`: replace `runner.have("codex")` in the skip condition and the default with `_codex_seen()`:

```python
def _codex_seen() -> bool:
    """A Codex on PATH, or (in WSL) a Windows codex.exe: worth asking which agents to set up."""
    from . import wsl
    return runner.have("codex") or (wsl.detect() is not None and bool(runner.which("codex.exe")))
```

`check_prereqs` (read it first, around the `have()` at line ~185): in WSL, a `codex` that resolves under `/mnt/<drive>/` counts as missing, so `--install` installs a Linux Codex (`mise use -g codex`). Add the test:

```python
def test_install_replaces_a_windows_shim_with_a_linux_codex(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)
    fake_runner.paths["codex"] = "/mnt/c/Users/u/AppData/Roaming/npm/codex"
    assert bootstrap.missing_binary("codex") is True
```

with `bootstrap.missing_binary(name) -> bool` as the one place `check_prereqs` asks (`not runner.have(name)`, or in WSL for `codex` a resolution on a Windows drive via `wsl._on_windows_drive`). Adapt the name if `check_prereqs` already has such a helper (ruling).

- [ ] **Step 4: Run** `uv run --python 3.12 --with pytest pytest -q tests/test_wsl_codex_bootstrap.py tests/test_agent_choice_bootstrap.py tests/test_wsl.py` → PASS; then the full suite.
- [ ] **Step 5: Commit** — `feat(bootstrap): in WSL the Codex step follows the side Codex runs on (--codex-side)`

### Task 3: Switch the VS Code extension to WSL, on a yes

**Files:** Modify `cli/loadout/wsl.py` (`set_vscode_wsl_mode`), `cli/loadout/bootstrap.py` (offer after the gate chose WSL interactively); Test `tests/test_wsl_codex_side.py`

**Interfaces:** Produces `wsl.set_vscode_wsl_mode(bk, home: Path) -> str`.

- [ ] **Step 1: Write the failing tests** (append):

```python
from loadout import backup


def test_the_setting_is_flipped_by_a_text_edit(win):
    text = '{\n  // keep me\n  "editor.tabSize": 2,\n  "chatgpt.runCodexInWindowsSubsystemForLinux": false,\n}\n'
    _vscode(win, text)
    bk = backup.Backup(description="t")
    line = wsl.set_vscode_wsl_mode(bk, win)
    assert wsl.vscode_settings(win).read_text() == text.replace(": false,", ": true,")
    assert "VS Code" in line and bk.steps


def test_the_setting_is_added_when_missing(win):
    _vscode(win, '{\n  "editor.tabSize": 2\n}\n')
    wsl.set_vscode_wsl_mode(backup.Backup(description="t"), win)
    text = wsl.vscode_settings(win).read_text()
    assert wsl.vscode_wsl_mode(win) is True and '"editor.tabSize": 2' in text


def test_no_settings_file_gives_the_manual_step(win):
    line = wsl.set_vscode_wsl_mode(backup.Backup(description="t"), win)
    assert "Settings" in line and not wsl.vscode_settings(win).exists()
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement:**

```python
MANUAL = (f"in VS Code on Windows: Settings, search {WIN_SETTING}, tick it (VS Code reloads); then the Codex "
          "extension runs Codex in WSL")


def set_vscode_wsl_mode(bk, home: Path) -> str:
    """Set the extension's WSL switch by a text edit of VS Code's settings.json (JSONC), backup first."""
    from .jsonio import write_atomic
    path = vscode_settings(home)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return f"VS Code settings not found ({path}); {MANUAL}"
    m = _SETTING_RX.search(text)
    if m is not None and m.group(1) == "true":
        return "VS Code already runs Codex in WSL"
    if m is not None:
        new = text[:m.start(1)] + "true" + text[m.end(1):]
    else:
        brace = text.find("{")
        if brace < 0:
            return f"VS Code settings ({path}) are not an object; {MANUAL}"
        new = text[:brace + 1] + f'\n  "{WIN_SETTING}": true,' + text[brace + 1:]
    bk.save_copy(path, "VS Code settings.json before loadout switched the Codex extension to WSL")
    write_atomic(path, new)
    return f"VS Code: the Codex extension now runs Codex in WSL ({WIN_SETTING} = true; VS Code reloads)"
```

In `codex_gate`, when the interactive answer is 1 and `cs.windows_home` is set and `vscode_wsl_mode(...) is not True`, ask `"Switch the VS Code Codex extension to WSL now (settings.json, backup first)? [y/N] "`; on yes print `set_vscode_wsl_mode(bk, home)`. `codex_gate` takes `bk` for this (`codex_gate(flag, ask, interactive, bk=None)`); without `bk` it prints `MANUAL`. Add a test for the yes path through `codex_gate`.

- [ ] **Step 4: Run** → PASS. **Step 5: Commit** — `feat(wsl): switch the VS Code Codex extension to WSL on a yes`

### Task 4: `loadout check` in WSL: the Windows side, a shared CODEX_HOME, and checks that follow the agents

**Files:** Modify `cli/loadout/wsl.py` (`problems`), `cli/loadout/check.py` (`_wsl`); Test `tests/test_wsl_codex_check.py` (create)

- [ ] **Step 1: Write the failing tests**

```python
"""loadout check in WSL reports the Windows Codex side read-only and checks only the agents that are on."""
import pytest

from loadout import check, codex, targets, wsl


@pytest.fixture
def wsl2(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)
    return fake_runner


def test_claude_off_skips_claude_and_its_sandbox(wsl2):
    targets.set_agents({"claude": False, "codex": True})
    wsl2.paths["claude"] = "/mnt/c/Users/u/AppData/Roaming/npm/claude"
    wsl2.missing.update({"bwrap", "socat"})
    text = " ".join(p for p, _ in wsl.problems(2, None))
    assert "claude" not in text and "sandbox" not in text


def test_a_used_windows_side_without_loadout_is_reported(wsl2, tmp_path, monkeypatch):
    targets.set_agents({"claude": False, "codex": True})
    home = tmp_path / "winhome"
    (home / ".codex").mkdir(parents=True)
    monkeypatch.setattr(wsl, "codex_side", lambda **k: wsl.CodexSide("both", ["x"], home, True, False))
    (r,) = [r for r in check._codex_side() if r.name == "Codex (Windows side)"]
    assert not r.ok and "bootstrap.ps1" in r.fix


def test_a_windows_side_with_loadouts_block_is_ok(wsl2, tmp_path, monkeypatch):
    targets.set_agents({"claude": False, "codex": True})
    home = tmp_path / "winhome"
    (home / ".codex").mkdir(parents=True)
    (home / ".codex" / "AGENTS.md").write_text(f"{codex.START}\nx\n{codex.END}\n")
    monkeypatch.setattr(wsl, "codex_side", lambda **k: wsl.CodexSide("both", ["x"], home, True, False))
    (r,) = [r for r in check._codex_side() if r.name == "Codex (Windows side)"]
    assert r.ok


def test_a_shared_codex_home_is_a_warning(wsl2, monkeypatch):
    targets.set_agents({"claude": False, "codex": True})
    monkeypatch.setattr(wsl, "codex_side", lambda **k: wsl.CodexSide("wsl", ["CODEX_HOME points into Windows"], None, False, True))
    assert any(r.name == "Codex home" and not r.ok for r in check._codex_side())


def test_codex_off_reads_no_side(wsl2, monkeypatch):
    targets.set_agents({"claude": True, "codex": False})
    monkeypatch.setattr(wsl, "codex_side", lambda **k: pytest.fail("read with Codex off"))
    assert check._codex_side() == []
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** In `wsl.problems`: the tool list is `(("claude",) if claude on else ()) + ("node", "npm", "uv", "git") + (("codex",) if codex on)`, and the sandbox packages are checked only with Claude Code on (a `_claude_on()` like `_codex_on()`). In `check.py`, new `_codex_side() -> list[CheckResult]` (empty outside WSL or with Codex off), wired into `run_checks` next to `_wsl`:

```python
def _codex_side() -> list[CheckResult]:
    """WSL only: the Windows Codex side, read-only (one loadout per side, ADR 0029)."""
    from . import codex, targets, wsl
    if wsl.detect() is None or not targets.codex_enabled():
        return []
    cs = wsl.codex_side()
    out = []
    if cs.shared_home:
        out.append(CheckResult("Codex home", False, "CODEX_HOME points into Windows: one config serves both sides, "
                               "and its commands fit only one", "unset CODEX_HOME in WSL (docs/how-to/wsl.md#codex)", "warn"))
    if cs.windows_home is not None and cs.windows_used:
        agents = cs.windows_home / ".codex" / "AGENTS.md"
        try:
            ok = codex.START in agents.read_text(encoding="utf-8")
        except OSError:
            ok = False
        out.append(CheckResult("Codex (Windows side)", ok, "" if ok else
                               "you use Codex on Windows too, and loadout has not set it up there",
                               "in PowerShell on Windows: run loadout's bootstrap.ps1 with the same personal layer", "warn"))
    return out
```

- [ ] **Step 4: Run** → PASS; full suite. **Step 5: Commit** — `feat(check): in WSL, report the Windows Codex side and a shared CODEX_HOME; WSL checks follow the agents`

### Task 5: A note for repos on /mnt/<drive>

**Files:** Modify `cli/loadout/project.py` (`add_profile`); Test `tests/test_wsl_codex_check.py`

- [ ] **Step 1: Test** (append):

```python
def test_profile_notes_a_repo_on_the_windows_drive(wsl2, tmp_path, monkeypatch, capsys):
    from loadout import profiles, project
    repo = tmp_path / "mnt" / "d" / "git" / "thesis"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.setattr(wsl, "MOUNT", str(tmp_path / "mnt") + "/")
    monkeypatch.setattr(profiles, "load_profile", lambda name: profiles.Profile(name="web", description=""))
    assert project.add_profile(repo, "web", install=False) == 0
    assert "Windows drive" in capsys.readouterr().out
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement:** `wsl.MOUNT = "/mnt/"` (and `problems()`/`codex_side()` default to it); `wsl.repo_note(project: Path) -> str | None` returns, in WSL for a repo on a Windows drive, `"note: this repo is on the Windows drive (slower in WSL: Serena and codebase-memory index it more slowly; links in its skill folders are WSL links that a Windows-side Codex does not follow)"`; `add_profile` prints it once (info, calm mode: a step line), never as a problem.
- [ ] **Step 4: Run** → PASS. **Step 5: Commit** — `feat(profile): note a repo on the Windows drive in WSL`

### Task 6: Docs and ADR 0029

**Files:** Create `docs/adr/0029-codex-on-windows-and-wsl.md`; modify `docs/adr/README.md`, `AGENTS.md` (ADR range), `docs/how-to/wsl.md` (new section "Codex" with anchor `#codex`: the two homes, which side runs Codex, the VS Code setting, `--codex-side`, `CODEX_HOME`, login in WSL, `/mnt/d`), `docs/reference/cli.md` (`--codex-side`, the new check lines), `docs/how-to/troubleshooting.md` (rows for "Codex step skipped", "Codex (Windows side)", "Codex home"), `docs/how-to/codex.md` (link to the WSL section).

- [ ] **Step 1:** ADR 0029 (format of `docs/adr/0028-serena-codex-hooks-in-hooks-json.md`): context (two Codex homes; commands differ per side; extension setting), decision (spec decision 2), alternatives (B: one loadout writes both homes; C: shared CODEX_HOME), consequences.
- [ ] **Step 2:** The pages above; check links (`uv run --python 3.12 --with pytest pytest -q tests/test_docs_links.py tests/test_readme.py`).
- [ ] **Step 3: Commit** — `docs: Codex on Windows and WSL, one loadout per side (ADR 0029)`
