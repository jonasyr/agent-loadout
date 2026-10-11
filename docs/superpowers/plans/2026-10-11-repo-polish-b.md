# Repo Polish B (Small Code Items) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the known gaps before publication: WSL detection plus a WSL 2 CI job, a `/reload-plugins` notice, Wiley/connector duplicates, the `NO_AUTO_PULL` respawn, codebase-memory `--skip-config` and a Windows install, a Python ≥ 3.10 guard, and the execution-advisor follow-ups.

**Architecture:** Each item is a small change to an existing module or a new focused file: `cli/loadout/wsl.py` (new), `plugins/loadout/hooks/reload_check.py` (new, standalone stdlib like `advisor.py`), and edits to `check.py`, `maintenance.py`, `bootstrap.py`, `bin/loadout`, `catalog.json`, `settings.base.json`, `profiles/thesis.json`, `hooks.json`, `advisor.py`, the execution-advisor skill and `ci.yml`. Docs change in the same commit as the code they describe.

**Tech Stack:** Python 3.10+ standard library, pytest (run through uv), GitHub Actions, `Vampire/setup-wsl@v7`.

**Spec:** `docs/superpowers/specs/2026-10-11-repo-polish-b-design.md`

## Global Constraints

- Python 3.10+, standard library only in `cli/loadout/` and in the plugin's hook scripts.
- Tests use `fake_home` and `fake_runner` (see `tests/conftest.py`). Never touch the real `~/.claude`, `~/.claude.json` or `~/.config/loadout`. Never run real installers or mutating `claude` commands.
- Hook-script tests run the script as a subprocess with a temporary `HOME` and are skipped on Windows (`pytestmark = pytest.mark.skipif(os.name == "nt", ...)`), like `tests/test_advisor.py`.
- Hook scripts never block or fail: on any error they print nothing and exit 0.
- Conventional Commits (`type(scope): subject`), no `Co-Authored-By` or other attribution trailer.
- Docs: one home per fact; the page that owns a fact changes in the same commit as the code.
- Test command: `uv run --python 3.12 --with pytest pytest -q` (single file: append the path, e.g. `tests/test_wsl.py -q`).
- Skill evals only through `plugins/loadout/evals/run.sh`, and only after the user says yes.
- Reload notice text, verbatim: `loadout: the plugin was updated after this session started. Run /reload-plugins to load the new skills and hooks.`
- Python guard text, verbatim: `loadout needs Python 3.10 or newer (found X.Y)`.

## Review Focus

1. **A dev checkout of the plugin** (`claude --plugin-dir plugins/loadout`, so the running root is the repo, not the cache) must never get the reload notice. Rule: notify only when the running plugin root lies under `~/.claude/plugins/cache/` and matches no `installPath` of `loadout@agent-loadout`. Test in Task 7.
2. **A project-scope install** (entry with `scope: project`) whose `installPath` equals the running root must stay silent, even if the user-scope entry differs. Test in Task 7 (match against every entry, not only the user one).
3. **Windows path separators in WSL checks**: `problems()` compares POSIX strings (`Path.as_posix()`), so the tests pass on the Windows CI job too. `/mnt/cache/x` (a directory named `cache`, not a drive letter) is not a Windows drive. Tests in Task 4.
4. **`claudeAiMcpEverConnected` missing, not a list, or `~/.claude.json` invalid JSON** gives no duplicate warning and no crash of `loadout check`. Tests in Task 6.
5. **The ledger check in `advisor.py stop()`** for a plan outside `docs/superpowers/plans/` (the `*/plans/*.md` glob) must not crash and must not count as started. Test in Task 8.

---

### Task 1: `LOADOUT_NO_AUTO_PULL=1` no longer respawns maintenance every session

**Files:**
- Modify: `cli/loadout/maintenance.py` (`session_start`, around line 61)
- Test: `tests/test_maintenance.py`

**Interfaces:**
- Consumes: `maintenance.is_due(name, interval, now)`, `maintenance.touch(name, now)`.
- Produces: nothing new.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_maintenance.py`)

```python
def test_session_start_no_auto_pull_does_not_count_pull_as_due(fake_home, monkeypatch):
    spawned = []
    monkeypatch.setattr(m, "_spawn_background", lambda: spawned.append(1))
    monkeypatch.setenv("LOADOUT_NO_AUTO_PULL", "1")
    m.touch("last-update-check", 5.0)  # weekly check fresh, last-pull never stamped
    m.session_start(6.0)
    assert spawned == []


def test_session_start_no_auto_pull_still_spawns_for_weekly_check(fake_home, monkeypatch):
    spawned = []
    monkeypatch.setattr(m, "_spawn_background", lambda: spawned.append(1))
    monkeypatch.setenv("LOADOUT_NO_AUTO_PULL", "1")
    m.touch("last-update-check", 5.0)
    m.session_start(5.0 + m.WEEK)
    assert spawned == [1]
```

- [ ] **Step 2: Run them, expect the first to FAIL** (`spawned == [1]`)

Run: `uv run --python 3.12 --with pytest pytest tests/test_maintenance.py -q`

- [ ] **Step 3: Implement**

In `session_start`, replace the `if is_due("last-pull", ...) or ...` condition with:

```python
    pull_due = os.environ.get("LOADOUT_NO_AUTO_PULL") != "1" and is_due("last-pull", DAY, now)
    if pull_due or is_due("last-update-check", WEEK, now):
```

- [ ] **Step 4: Run the file, expect PASS**

- [ ] **Step 5: Commit**

```bash
git add cli/loadout/maintenance.py tests/test_maintenance.py
git commit -m "fix(maintenance): do not respawn every session under LOADOUT_NO_AUTO_PULL"
```

---

### Task 2: codebase-memory installs with `--skip-config`, on Windows too

**Files:**
- Modify: `catalog.json` (entry `codebase-memory-mcp`)
- Create: `docs/adr/0019-upstream-installers-without-agent-configuration.md`
- Modify: `docs/adr/README.md` (index row), `docs/reference/included-tools.md`, `docs/explanation/security-and-trust.md:20`, `AGENTS.md` (`decisions 0001-0018` → `0001-0019`)
- Test: `tests/test_repo_static.py`

**Interfaces:** none.

- [ ] **Step 1: Write the failing test** (append to `tests/test_repo_static.py`)

```python
def test_codebase_memory_installers_skip_agent_config():
    entry = next(e for e in _json("catalog.json")["entries"] if e["id"] == "codebase-memory-mcp")
    for key in ("install", "update"):
        for plat in ("posix", "windows"):
            cmds = entry[key][plat]
            assert cmds, (key, plat)
            for cmd in cmds:
                assert "--skip-config" in " ".join(cmd), (key, plat, cmd)
    assert "manual" not in entry  # Windows has a real install command now
```

- [ ] **Step 2: Run it, expect FAIL** (`KeyError: 'windows'` on install)

Run: `uv run --python 3.12 --with pytest pytest tests/test_repo_static.py -q`

- [ ] **Step 3: Change the catalog entry**

Set `install` and `update` of `codebase-memory-mcp` to the same two commands and delete its `manual` key (it only described the missing Windows install):

```json
"install": {
  "posix": [["sh", "-c", "curl -fsSL https://raw.githubusercontent.com/DeusData/codebase-memory-mcp/main/install.sh | bash -s -- --skip-config"]],
  "windows": [["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", "& ([scriptblock]::Create((irm https://raw.githubusercontent.com/DeusData/codebase-memory-mcp/main/install.ps1))) --skip-config"]]
},
"update": {
  "posix": [["sh", "-c", "curl -fsSL https://raw.githubusercontent.com/DeusData/codebase-memory-mcp/main/install.sh | bash -s -- --skip-config"]],
  "windows": [["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", "& ([scriptblock]::Create((irm https://raw.githubusercontent.com/DeusData/codebase-memory-mcp/main/install.ps1))) --skip-config"]]
}
```

- [ ] **Step 4: Run the full suite, expect PASS** (other tests read the catalog: `test_pkgmgr.py`, `test_update_dedupe.py`, `test_check.py`)

Run: `uv run --python 3.12 --with pytest pytest -q`

- [ ] **Step 5: Write ADR 0019** (`docs/adr/0019-upstream-installers-without-agent-configuration.md`)

```markdown
# 0019. Upstream installers run without agent configuration

- Status: Accepted
- Date: 2026-10-11
- Source: [Repo polish B design, section 6](../superpowers/specs/2026-10-11-repo-polish-b-design.md#6-small-fixes)

## Context
Some upstream install scripts also configure coding agents. codebase-memory-mcp's `install.sh` and `install.ps1` register its MCP server and hooks in Claude Code unless they get `--skip-config`. The loadout plugin already declares that server (`plugins/loadout/.mcp.json`) and its hook, so a default install creates a second copy of each. Its `update` subcommand only prints the command to re-run the install script.

## Decision
loadout runs upstream installers with their "do not configure agents" flag (`--skip-config` for codebase-memory-mcp). The plugin owns MCP and hook configuration. An update re-runs the same install command.

## Alternatives considered
- Let the installer configure agents and remove the duplicate afterwards: adopt can detect exact duplicates (`cli/loadout/duplicates.py`), but every install would create work to undo.
- Keep `codebase-memory-mcp update`: it does not update anything.

## Consequences
- A new catalog binary whose installer configures agents needs the same flag; `tests/test_repo_static.py` checks it for codebase-memory-mcp.
- Users who install the tool by hand without the flag get duplicates, which `loadout adopt` reports.
```

Add the index row to `docs/adr/README.md` after 0018:

```markdown
| [0019](0019-upstream-installers-without-agent-configuration.md) | Upstream installers run without agent configuration | Accepted |
```

- [ ] **Step 6: Update the docs that own the facts**

- `docs/reference/included-tools.md`: in the binaries table row for `serena`, `codebase-memory-mcp` (line 54) or right below the table, add one sentence: "codebase-memory-mcp is installed and updated with its install script and `--skip-config`, so it does not register a second MCP server next to the plugin's ([0019](../adr/0019-upstream-installers-without-agent-configuration.md)). On Windows, bootstrap uses `install.ps1`."
- `docs/explanation/security-and-trust.md:20`: after "(uv, codebase-memory-mcp, rtk)" add ", on Windows through `irm … | iex`-style PowerShell commands" only if the sentence does not already cover Windows; keep the rest.
- `AGENTS.md`: `decisions 0001-0018` → `decisions 0001-0019`.
- grep for other mentions of the old Windows manual text: `grep -rn "release archive\|install.ps1" docs README.md` and fix each hit.

- [ ] **Step 7: Run the suite (static link checks included), then commit**

```bash
git add catalog.json tests/test_repo_static.py docs/adr AGENTS.md docs/reference/included-tools.md docs/explanation/security-and-trust.md
git commit -m "fix(catalog): install codebase-memory-mcp with --skip-config, also on Windows"
```

---

### Task 3: Python ≥ 3.10 guard and a `Python X.Y` check line

**Files:**
- Modify: `bin/loadout`
- Modify: `cli/loadout/check.py` (new `_python`, add to `run_checks`)
- Modify: `docs/reference/cli.md` (check table), `docs/how-to/troubleshooting.md` (one row)
- Test: `tests/test_python_guard.py` (new), `tests/test_check.py`

**Interfaces:**
- Produces: `bin/loadout` function `require_python(version=None) -> None` (exits 1 below 3.10); `check._python() -> list[CheckResult]`.

- [ ] **Step 1: Write the failing tests** (`tests/test_python_guard.py`)

```python
import importlib.machinery
import importlib.util
import sys

import pytest

from loadout import check, paths


def _bin():
    path = paths.kit_root() / "bin" / "loadout"
    loader = importlib.machinery.SourceFileLoader("bin_loadout", str(path))
    spec = importlib.util.spec_from_loader("bin_loadout", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)  # must not run main(): the entry point is guarded by __name__
    return mod


def test_require_python_rejects_3_9(capsys):
    with pytest.raises(SystemExit) as exc:
        _bin().require_python((3, 9, 18))
    assert exc.value.code == 1
    assert "loadout needs Python 3.10 or newer (found 3.9)" in capsys.readouterr().err


def test_require_python_accepts_3_10_and_current():
    mod = _bin()
    mod.require_python((3, 10, 0))
    mod.require_python()


def test_bin_loadout_has_no_syntax_newer_than_3_6():
    import ast
    src = (paths.kit_root() / "bin" / "loadout").read_text(encoding="utf-8")
    ast.parse(src, feature_version=(3, 6))


def test_check_shows_python_version(fake_home, fake_runner):
    names = [r.name for r in check.run_checks()]
    assert f"Python {sys.version_info[0]}.{sys.version_info[1]}" in names
```

- [ ] **Step 2: Run, expect FAIL** (`AttributeError: require_python`, and importing `bin/loadout` currently runs `main()`)

Run: `uv run --python 3.12 --with pytest pytest tests/test_python_guard.py -q`

- [ ] **Step 3: Rewrite `bin/loadout`**

```python
#!/usr/bin/env python3
# Keep this file parseable by old Pythons: the version check must run before any newer syntax.
import sys


def require_python(version=None):
    version = version or sys.version_info
    if tuple(version[:2]) < (3, 10):
        sys.stderr.write("loadout needs Python 3.10 or newer (found %d.%d)\n" % (version[0], version[1]))
        sys.exit(1)


if __name__ == "__main__":
    require_python()
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli"))
    from loadout.__main__ import main  # noqa: E402

    sys.exit(main())
```

Check every caller still runs it as a script: `grep -rn "bin/loadout\|bin\" / \"loadout\|\"loadout\"" cli/loadout/link.py cli/loadout/maintenance.py bootstrap.sh bootstrap.ps1`. Callers that execute the file (`python bin/loadout ...`, a symlink, a `.cmd` shim) keep working; one that imports it would not, so report any importer.

- [ ] **Step 4: Add the check line** in `cli/loadout/check.py`

```python
import sys


def _python() -> list[CheckResult]:
    return [CheckResult(f"Python {sys.version_info[0]}.{sys.version_info[1]}", True)]
```

and put `*_python()` first in `run_checks()`.

- [ ] **Step 5: Run the full suite, expect PASS**

- [ ] **Step 6: Docs**

- `docs/reference/cli.md`, `loadout check` table: first row `| The Python version that runs loadout (an ok line; loadout needs 3.10 or newer and stops before this on older versions) | — |`.
- `docs/how-to/troubleshooting.md`: one row/entry: symptom `loadout needs Python 3.10 or newer (found 3.X)`, fix: install Python 3.10+ (for example `uv python install 3.12`) and make sure `python3` (Windows: `python`) runs it.

- [ ] **Step 7: Commit**

```bash
git add bin/loadout cli/loadout/check.py tests/test_python_guard.py docs/reference/cli.md docs/how-to/troubleshooting.md
git commit -m "feat(cli): require Python 3.10 with a clear message and show the version in check"
```

---

### Task 4: WSL detection (`wsl.py`), in `check` and in bootstrap

**Files:**
- Create: `cli/loadout/wsl.py`
- Modify: `cli/loadout/check.py` (new `_wsl`), `cli/loadout/bootstrap.py` (`bootstrap()`, before `_step("Prerequisites")`)
- Modify: `docs/how-to/wsl.md`, `docs/reference/cli.md`, `docs/how-to/troubleshooting.md`, `AGENTS.md` (map: add `wsl.py`)
- Test: `tests/test_wsl.py` (new)

**Interfaces:**
- Consumes: `runner.which(binary) -> str | None`, `runner.have(binary) -> bool` (faked by `fake_runner.paths` / `fake_runner.missing`), `paths.kit_root()`, `paths.personal_root()`.
- Produces:
  - `wsl.OSRELEASE: Path` = `Path("/proc/sys/kernel/osrelease")`
  - `wsl.detect(osrelease: Path = OSRELEASE, platform: str | None = None) -> int | None`
  - `wsl.problems(version: int, cwd: Path, mount: str = "/mnt/") -> list[tuple[str, str]]` (problem, fix)
  - `wsl.report_lines(version: int, cwd: Path) -> list[str]` (for bootstrap: a header line plus `problem` / `  fix: ...` lines)

- [ ] **Step 1: Write the failing tests** (`tests/test_wsl.py`)

```python
import pytest

from loadout import bootstrap as b, check, wsl


@pytest.mark.parametrize("text,expected", [
    ("5.15.153.1-microsoft-standard-WSL2\n", 2),
    ("6.6.36.3-microsoft-standard-wsl2", 2),
    ("4.4.0-19041-Microsoft\n", 1),
    ("6.10.5-arch1-1\n", None),
])
def test_detect(tmp_path, text, expected):
    f = tmp_path / "osrelease"
    f.write_text(text)
    assert wsl.detect(f, platform="linux") == expected


def test_detect_missing_file_and_other_platform(tmp_path):
    assert wsl.detect(tmp_path / "nope", platform="linux") is None
    f = tmp_path / "osrelease"
    f.write_text("5.15.153.1-microsoft-standard-WSL2")
    assert wsl.detect(f, platform="win32") is None


@pytest.fixture
def mnt(tmp_path):
    root = tmp_path / "mnt"
    (root / "c" / "Users" / "me").mkdir(parents=True)
    (root / "cache").mkdir()
    return root


def _prefix(mnt):
    return mnt.as_posix() + "/"


def test_no_problems_on_clean_wsl2(fake_home, fake_runner, mnt, tmp_path):
    assert wsl.problems(2, tmp_path, mount=_prefix(mnt)) == []


def test_wsl1_is_a_problem(fake_home, fake_runner, mnt, tmp_path):
    texts = [p for p, _ in wsl.problems(1, tmp_path, mount=_prefix(mnt))]
    assert any("WSL 1" in t for t in texts)
    fixes = [f for _, f in wsl.problems(1, tmp_path, mount=_prefix(mnt))]
    assert any("wsl --set-version <distro> 2" in f for f in fixes)


def test_cwd_on_windows_drive(fake_home, fake_runner, mnt):
    cwd = mnt / "c" / "Users" / "me"
    found = wsl.problems(2, cwd, mount=_prefix(mnt))
    assert len(found) == 1
    assert "Windows filesystem" in found[0][0] and cwd.as_posix() in found[0][0]
    assert "Linux home" in found[0][1]


def test_dir_named_like_mount_but_not_a_drive_letter_is_fine(fake_home, fake_runner, mnt):
    assert wsl.problems(2, mnt / "cache", mount=_prefix(mnt)) == []


def test_personal_root_on_windows_drive(fake_home, fake_runner, mnt, tmp_path, monkeypatch):
    monkeypatch.setenv("LOADOUT_PERSONAL", str(mnt / "c" / "Users" / "me" / "personal"))
    texts = [p for p, _ in wsl.problems(2, tmp_path, mount=_prefix(mnt))]
    assert any("personal" in t and "Windows filesystem" in t for t in texts)


def test_windows_tools_on_path(fake_home, fake_runner, mnt, tmp_path):
    fake_runner.paths["node"] = (mnt / "c" / "Program Files" / "nodejs" / "node").as_posix()
    fake_runner.paths["git"] = "/usr/bin/git"
    found = wsl.problems(2, tmp_path, mount=_prefix(mnt))
    assert [p for p, _ in found] == [f"node resolves to the Windows program {fake_runner.paths['node']}"]
    assert "appendWindowsPath = false" in found[0][1]


def test_sandbox_packages_missing_only_on_wsl2(fake_home, fake_runner, mnt, tmp_path):
    fake_runner.missing.update({"bwrap", "socat"})
    two = wsl.problems(2, tmp_path, mount=_prefix(mnt))
    assert ("sandbox packages missing: bubblewrap, socat", "`sudo apt-get install bubblewrap socat`") in two
    one = wsl.problems(1, tmp_path, mount=_prefix(mnt))
    assert not any("sandbox packages" in p for p, _ in one)


def test_check_lines_in_wsl(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)
    monkeypatch.setattr(wsl, "problems", lambda v, cwd, mount="/mnt/": [("repo is slow", "move it")])
    results = check.run_checks()
    names = [r.name for r in results]
    assert "WSL 2" in names
    warn = next(r for r in results if r.name == "WSL" and not r.ok)
    assert warn.severity == "warn" and warn.detail == "repo is slow" and warn.fix == "move it"


def test_check_has_no_wsl_lines_outside_wsl(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: None)
    assert not any(r.name.startswith("WSL") for r in check.run_checks())


def test_report_lines(fake_home, fake_runner, monkeypatch, tmp_path):
    monkeypatch.setattr(wsl, "problems", lambda v, cwd, mount="/mnt/": [("p1", "f1")])
    assert wsl.report_lines(1, tmp_path) == ["WSL 1 detected", "p1", "  fix: f1"]


def test_bootstrap_prints_wsl_problems_and_continues(fake_home, fake_runner, monkeypatch, capsys):
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 1)
    monkeypatch.setattr(wsl, "report_lines", lambda v, cwd: ["WSL 1 detected", "p1", "  fix: f1"])
    stop = RuntimeError("stop after the WSL step")

    def halt(*a, **k):
        raise stop

    monkeypatch.setattr(b, "check_prereqs", halt)
    with pytest.raises(RuntimeError):
        b.bootstrap(install=False, yes=True, plugins=False, adopt_step=False, ask=lambda q: "", interactive=False)
    out = capsys.readouterr().out
    assert "== WSL" in out and "p1" in out and "fix: f1" in out  # printed, then bootstrap went on to prerequisites
```

- [ ] **Step 2: Run, expect FAIL** (`ImportError: cannot import name 'wsl'`)

Run: `uv run --python 3.12 --with pytest pytest tests/test_wsl.py -q`

- [ ] **Step 3: Implement `cli/loadout/wsl.py`**

```python
"""WSL detection and the setup problems loadout can see from inside WSL (docs/how-to/wsl.md)."""
from __future__ import annotations

import sys
from pathlib import Path

from . import paths, runner

OSRELEASE = Path("/proc/sys/kernel/osrelease")
LINUX_TOOLS = ("claude", "node", "npm", "uv", "git")
SANDBOX = (("bwrap", "bubblewrap"), ("socat", "socat"))


def detect(osrelease: Path = OSRELEASE, platform: str | None = None) -> int | None:
    """2 for WSL 2, 1 for WSL 1, None outside WSL."""
    if not (platform or sys.platform).startswith("linux"):
        return None
    try:
        text = osrelease.read_text(encoding="utf-8", errors="replace").lower()
    except OSError:
        return None
    if "microsoft" not in text:
        return None
    return 2 if "wsl2" in text else 1


def _on_windows_drive(path: Path, mount: str) -> bool:
    s = Path(path).as_posix()
    if not s.startswith(mount):
        return False
    first = s[len(mount):].split("/", 1)[0]
    return len(first) == 1 and first.isalpha()


def problems(version: int, cwd: Path, mount: str = "/mnt/") -> list[tuple[str, str]]:
    out = []
    if version == 1:
        out.append(("WSL 1: Claude Code's sandbox needs WSL 2, and its native binary can fail with `Exec format error`",
                    "in PowerShell: `wsl --set-version <distro> 2`"))
    for label, path in (("the kit", paths.kit_root()), ("the personal layer", paths.personal_root()),
                        ("the current folder", cwd)):
        if _on_windows_drive(path, mount):
            out.append((f"{label} ({Path(path).as_posix()}) is on the Windows filesystem (slow, search can be incomplete)",
                        "move it into the Linux home, e.g. `~/code/...`"))
    for tool in LINUX_TOOLS:
        found = runner.which(tool)
        if found and Path(found).as_posix().startswith(mount):
            out.append((f"{tool} resolves to the Windows program {found}",
                        "install it inside WSL and put its directory first in PATH, "
                        "or set `appendWindowsPath = false` in `/etc/wsl.conf`"))
    if version == 2:
        missing = [pkg for binary, pkg in SANDBOX if not runner.have(binary)]
        if missing:
            out.append((f"sandbox packages missing: {', '.join(missing)}",
                        f"`sudo apt-get install {' '.join(missing)}`"))
    return out


def report_lines(version: int, cwd: Path) -> list[str]:
    lines = [f"WSL {version} detected"]
    for problem, fix in problems(version, cwd):
        lines += [problem, f"  fix: {fix}"]
    return lines
```

Note for `test_cwd_on_windows_drive`: the problem text contains `cwd.as_posix()` because the label includes the path. The test's exact-equality assertions in `test_windows_tools_on_path` and `test_sandbox_packages_missing_only_on_wsl2` pin the wording above.

- [ ] **Step 4: Wire into `check.py`**

```python
from pathlib import Path

from . import wsl


def _wsl() -> list[CheckResult]:
    version = wsl.detect()
    if version is None:
        return []
    return [CheckResult(f"WSL {version}", True),
            *(CheckResult("WSL", False, problem, fix, "warn") for problem, fix in wsl.problems(version, Path.cwd()))]
```

Add `*_wsl()` to `run_checks()` right after `*_python()`.

- [ ] **Step 5: Wire into bootstrap** — in `bootstrap()`, before `_step("Prerequisites")`:

```python
    version = wsl.detect()
    if version is not None:
        _step("WSL")
        for line in wsl.report_lines(version, Path.cwd()):
            print(line)
```

with `from . import wsl` among the imports (and `Path` if not imported yet).

- [ ] **Step 6: Run the full suite, expect PASS**

- [ ] **Step 7: Docs**

- `docs/how-to/wsl.md`: replace the paragraph "loadout does not detect WSL yet and `loadout check` has no WSL checks. Everything below is a manual step." with: "loadout detects WSL. `loadout check` prints `WSL 1` or `WSL 2` and warns about the problems below that it can see: WSL 1, the kit, the personal layer or the current folder under `/mnt/<drive>/`, `claude`, `node`, `npm`, `uv` or `git` resolving to a Windows program, and (WSL 2) missing bubblewrap or socat. Bootstrap prints the same warnings at its start and continues. The steps below are the fixes." Keep steps 1–6. In step 5, change `which claude node uv` to `which claude node npm uv git`.
- `docs/reference/cli.md`, `loadout check` table: after the Python row, `| Inside WSL: the WSL version (an ok line), then one warning per problem from [WSL 2](../how-to/wsl.md) | warn |`.
- `docs/how-to/troubleshooting.md`: one entry linking `wsl.md` for any `WSL` warning from `loadout check`.
- `AGENTS.md` map: in the line with `detect.py`, or a new bullet, add `wsl.py` WSL detection and checks.

- [ ] **Step 8: Commit**

```bash
git add cli/loadout/wsl.py cli/loadout/check.py cli/loadout/bootstrap.py tests/test_wsl.py docs/how-to/wsl.md docs/reference/cli.md docs/how-to/troubleshooting.md AGENTS.md
git commit -m "feat(wsl): detect WSL and warn about setup problems in check and bootstrap"
```

---

### Task 5: WSL 2 CI job

**Files:**
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: `wsl.detect()` from Task 4; `bin/loadout check` output line `[ok  ] WSL 2`.

- [ ] **Step 1: Add the job** to `ci.yml` under `jobs:`

```yaml
  test-wsl2:
    name: test (wsl2)
    runs-on: windows-latest
    defaults:
      run:
        shell: wsl-bash {0}
    steps:
      - uses: actions/checkout@v4
      - uses: Vampire/setup-wsl@v7
        with:
          distribution: Ubuntu-24.04
          wsl-version: 2
          additional-packages: python3 git curl ca-certificates
      - name: install uv inside WSL
        run: curl -LsSf https://astral.sh/uv/install.sh | sh
      - name: tests
        run: ~/.local/bin/uv run --python 3.12 --with pytest pytest -q
      - name: smoke test (WSL 2 detected)
        run: |
          python3 -c "import sys; sys.path.insert(0, 'cli'); from loadout import wsl; v = wsl.detect(); print('detect:', v); assert v == 2"
          out="$(python3 bin/loadout check || true)"
          printf '%s\n' "$out"
          printf '%s\n' "$out" | grep -F '[ok  ] WSL 2'
          ! printf '%s\n' "$out" | grep -F 'WSL 1:'
```

Notes for the implementer:
- `wsl-bash` starts in the checkout (the Windows workspace under `/mnt/d/...`), so the job also exercises the "current folder on the Windows filesystem" warning; that is expected and is a `warn`, not a failure.
- The checkout is on the Windows filesystem, which can turn `\n` into `\r\n` in shell scripts with `core.autocrlf`. If hook tests fail with `$'\r'` errors, add a step before checkout: `git config --global core.autocrlf false` with `shell: pwsh`.

- [ ] **Step 2: Validate the YAML locally**

Run: `python3 -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml'))" 2>/dev/null || uv run --with pyyaml python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('ok')"`
Expected: `ok` (or no error).

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add a WSL 2 job running the suite and a detection smoke test"
```

- [ ] **Step 4: Verify on GitHub (needs the user's OK to push)**

This job only runs on GitHub. Ask the user before the first push of the branch. After the push: `gh run watch` / `gh run view --log-failed`. If WSL 2 cannot start on the runner (nested virtualization error from setup-wsl), stop and report to the user; do not switch to `wsl-version: 1`.

---

### Task 6: Wiley Scholar Gateway, the `connector` field and the duplicate check

**Files:**
- Modify: `settings.base.json` (`extraKnownMarketplaces.life-sciences`)
- Modify: `catalog.json` (new entries `plugin-wiley-scholar-gateway`, `plugin-context7`)
- Modify: `profiles/thesis.json` (`notes`)
- Modify: `cli/loadout/check.py` (new `_connectors`)
- Modify: `docs/reference/catalog-format.md`, `docs/reference/included-tools.md`, `docs/reference/cli.md`, `docs/reference/profile-format.md` only if it quotes the thesis notes
- Test: `tests/test_connectors.py` (new), `tests/test_repo_static.py`

**Interfaces:**
- Consumes: `paths.claude_home()`, `paths.claude_json()`, `catalog.load()`, `jsonio.load_json`, `InvalidJSON`.
- Produces: `check._connectors() -> list[CheckResult]`; catalog field `connector: str` on `kind: plugin` entries.

- [ ] **Step 1: Write the failing tests**

`tests/test_connectors.py`:

```python
import json

from loadout import check, paths, settings_merge


def _settings(home, enabled):
    p = home / ".claude/settings.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"enabledPlugins": enabled}))


def _claude_json(home, data):
    (home / ".claude.json").write_text(data if isinstance(data, str) else json.dumps(data))


def _dupes():
    return [r for r in check.run_checks() if r.name.startswith("duplicate ")]


def test_enabled_plugin_and_connected_connector_warn(fake_home, fake_runner):
    _settings(fake_home, {"context7@claude-plugins-official": True})
    _claude_json(fake_home, {"claudeAiMcpEverConnected": ["claude.ai Context7", "claude.ai Gmail"]})
    [r] = _dupes()
    assert r.name == "duplicate context7@claude-plugins-official"
    assert not r.ok and r.severity == "warn"
    assert "claude.ai Context7" in r.detail and "still connected" in r.detail
    assert '"enabledPlugins": {"context7@claude-plugins-official": false}' in r.fix
    assert "loadout apply-settings" in r.fix


def test_disabled_plugin_or_unconnected_connector_is_quiet(fake_home, fake_runner):
    _settings(fake_home, {"context7@claude-plugins-official": False, "wiley-scholar-gateway@life-sciences": True})
    _claude_json(fake_home, {"claudeAiMcpEverConnected": ["claude.ai Context7"]})
    assert _dupes() == []


def test_wiley_duplicate(fake_home, fake_runner):
    _settings(fake_home, {"wiley-scholar-gateway@life-sciences": True})
    _claude_json(fake_home, {"claudeAiMcpEverConnected": ["claude.ai Wiley Scholar Gateway"]})
    assert [r.name for r in _dupes()] == ["duplicate wiley-scholar-gateway@life-sciences"]


def test_missing_or_malformed_claude_json_is_quiet(fake_home, fake_runner):
    _settings(fake_home, {"context7@claude-plugins-official": True})
    assert _dupes() == []  # no ~/.claude.json
    for bad in ("{ broken", json.dumps({"claudeAiMcpEverConnected": "claude.ai Context7"}),
                json.dumps({"claudeAiMcpEverConnected": [1, None]}), json.dumps([1, 2])):
        _claude_json(fake_home, bad)
        assert _dupes() == []


def test_invalid_settings_json_is_quiet_here(fake_home, fake_runner):
    p = fake_home / ".claude/settings.json"
    p.parent.mkdir(parents=True)
    p.write_text("{ nope")
    _claude_json(fake_home, {"claudeAiMcpEverConnected": ["claude.ai Context7"]})
    assert _dupes() == []  # the settings.json check reports the syntax error


def test_personal_false_overrides_kit_true(fake_home, fake_runner):
    pers = paths.personal_root()
    pers.mkdir(parents=True)
    (pers / "settings.json").write_text(json.dumps({"enabledPlugins": {"context7@claude-plugins-official": False}}))
    assert settings_merge.desired_settings()["enabledPlugins"]["context7@claude-plugins-official"] is False
    settings_merge.apply_settings()
    data = json.loads((fake_home / ".claude/settings.json").read_text())
    assert data["enabledPlugins"]["context7@claude-plugins-official"] is False
```

Append to `tests/test_repo_static.py`:

```python
def test_connector_field_only_on_plugins():
    entries = _json("catalog.json")["entries"]
    with_connector = {e["id"]: e for e in entries if "connector" in e}
    assert set(with_connector) >= {"plugin-wiley-scholar-gateway", "plugin-context7"}
    for e in with_connector.values():
        assert e["kind"] == "plugin" and e["connector"].startswith("claude.ai "), e["id"]
    wiley = with_connector["plugin-wiley-scholar-gateway"]
    assert wiley["status"] == "profile" and wiley["profile"] == "thesis"
    thesis = _json("profiles/thesis.json")
    assert "wiley-scholar-gateway@life-sciences" not in thesis["settings"]["enabledPlugins"]
    assert "wiley-scholar-gateway@life-sciences" in thesis["notes"]
```

- [ ] **Step 2: Run, expect FAIL**

Run: `uv run --python 3.12 --with pytest pytest tests/test_connectors.py tests/test_repo_static.py -q`
Expected: the duplicate tests and the static test fail; `test_personal_false_overrides_kit_true` passes (it verifies the spec's assumption; if it fails, stop and report, the fix text would be wrong).

- [ ] **Step 3: Settings, catalog, profile**

`settings.base.json`, in `extraKnownMarketplaces` after `academic-research-skills`:

```json
    "life-sciences": {
      "source": {
        "source": "github",
        "repo": "anthropics/life-sciences"
      },
      "autoUpdate": true
    }
```

`catalog.json`, after `plugin-ars`:

```json
{"id": "plugin-wiley-scholar-gateway", "kind": "plugin", "status": "profile", "profile": "thesis", "match": {"names": ["wiley-scholar-gateway@life-sciences"]}, "connector": "claude.ai Wiley Scholar Gateway", "reason": "Literature search across Wiley's peer-reviewed content. Use either this plugin or the claude.ai connector, not both."},
{"id": "plugin-context7", "kind": "plugin", "status": "core", "match": {"names": ["context7@claude-plugins-official"]}, "connector": "claude.ai Context7", "reason": "Library documentation (enabled by the kit). Use either this plugin or the claude.ai connector, not both."},
```

(Format them like the neighbouring entries in the file.)

`profiles/thesis.json` `notes`, replace the last sentence:

```
Literature search: the claude.ai Wiley Scholar Gateway connector, or the deep-research skill. Without a claude.ai login, enable the wiley-scholar-gateway@life-sciences plugin instead (not both).
```

- [ ] **Step 4: Implement `_connectors` in `check.py`**

```python
def _connectors() -> list[CheckResult]:
    """A kit-known plugin enabled next to the claude.ai connector with the same tools."""
    try:
        enabled = load_json(paths.claude_home() / "settings.json").get("enabledPlugins", {})
        connected = load_json(paths.claude_json()).get("claudeAiMcpEverConnected", [])
    except InvalidJSON:
        return []  # settings.json errors are reported by _settings; ~/.claude.json is Claude Code's
    if not isinstance(enabled, dict) or not isinstance(connected, list):
        return []
    out = []
    for entry in catalog.load():
        name = entry.get("connector")
        if entry["kind"] != "plugin" or not name or name not in connected:
            continue
        for plugin in entry["match"].get("names", []):
            if enabled.get(plugin) is True:
                out.append(CheckResult(
                    f"duplicate {plugin}", False,
                    f"the plugin and the claude.ai connector {name} provide the same tools "
                    "(if the connector is still connected)",
                    "disconnect the connector on claude.ai, or disable the plugin (for a plugin the kit enables: "
                    f'"enabledPlugins": {{"{plugin}": false}} in your personal settings.json, then loadout apply-settings)',
                    "warn"))
    return out
```

`jsonio.load_json` returns `{}` for a missing or empty file and raises `InvalidJSON` for bad JSON or a non-object top level (verified), so the `except` covers every malformed case. Add `*_connectors()` to `run_checks()` after `*_plugins()`.

- [ ] **Step 5: Run the full suite, expect PASS** (also `test_bootstrap.py`: `setup_plugins` now adds the `life-sciences` marketplace when missing; it installs no plugin from it)

- [ ] **Step 6: Docs**

- `docs/reference/catalog-format.md` fields table, after `offer`: `| connector | no | For a plugin: the name of the claude.ai connector with the same tools, as Claude Code lists it (for example "claude.ai Context7"). \`loadout check\` warns when the plugin is enabled and the connector has been connected. |`
- `docs/reference/included-tools.md`: add `life-sciences` to the list of known marketplaces (wherever the others are listed) and, under the thesis profile or plugins, one line: Wiley Scholar Gateway is known but not enabled; use the claude.ai connector or enable the plugin, not both.
- `docs/reference/cli.md` check table: `| An enabled plugin and a claude.ai connector with the same tools ("ever connected" in ~/.claude.json, an undocumented Claude Code field) | warn |`.

- [ ] **Step 7: Commit**

```bash
git add settings.base.json catalog.json profiles/thesis.json cli/loadout/check.py tests/test_connectors.py tests/test_repo_static.py docs/reference
git commit -m "feat(check): warn when a plugin duplicates a claude.ai connector; add Wiley Scholar Gateway"
```

---

### Task 7: `/reload-plugins` notice hook

**Files:**
- Create: `plugins/loadout/hooks/reload_check.py`
- Modify: `plugins/loadout/hooks/hooks.json` (SessionStart and Stop)
- Modify: `docs/reference/hooks.md`, `docs/how-to/troubleshooting.md`
- Test: `tests/test_reload_check.py` (new)

**Interfaces:**
- Produces: script `reload_check.py` reading the hook JSON on stdin; prints `{"systemMessage": "<notice>"}` or nothing; state `~/.claude/.loadout/reload-notified.json` = `{"sessions": [<id>, ...]}` (last 20).

Deviation from the spec, on purpose: the running plugin root is taken from the script's own location (`Path(__file__).resolve().parent.parent`), not from `CLAUDE_PLUGIN_ROOT`. The hook command is `${CLAUDE_PLUGIN_ROOT}/hooks/reload_check.py`, so both name the same folder, and the file location works even if Claude Code does not export the variable to the process.

- [ ] **Step 1: Write the failing tests** (`tests/test_reload_check.py`)

```python
"""plugins/loadout/hooks/reload_check.py, run as a subprocess from a copy inside a fake plugin cache."""
import json
import os
import shutil
import subprocess

import pytest

from loadout import paths

SRC = paths.kit_root() / "plugins" / "loadout" / "hooks" / "reload_check.py"
NOTICE = ("loadout: the plugin was updated after this session started. "
          "Run /reload-plugins to load the new skills and hooks.")
pytestmark = pytest.mark.skipif(os.name == "nt", reason="hook scripts run under bash/python3 on POSIX")


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    h.mkdir()
    return h


def _plugin(root):
    """A plugin folder with the script in hooks/; returns the script path."""
    (root / "hooks").mkdir(parents=True)
    shutil.copy(SRC, root / "hooks" / "reload_check.py")
    return root / "hooks" / "reload_check.py"


def _cache(home, version):
    return home / ".claude/plugins/cache/agent-loadout/loadout" / version


def _installed(home, entries):
    p = home / ".claude/plugins/installed_plugins.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(entries if isinstance(entries, str) else json.dumps({"version": 2, "plugins": {"loadout@agent-loadout": entries}}))


def _run(home, script, session="s1", raw=None):
    stdin = raw if raw is not None else json.dumps({"session_id": session, "hook_event_name": "Stop"})
    r = subprocess.run(["python3", str(script)], input=stdin, env={"HOME": str(home), "PATH": os.environ["PATH"]},
                       capture_output=True, text=True)
    assert r.returncode == 0 and r.stderr == ""
    return r.stdout


def test_same_path_is_silent(home):
    script = _plugin(_cache(home, "aaa"))
    _installed(home, [{"scope": "user", "installPath": str(_cache(home, "aaa"))}])
    assert _run(home, script) == ""


def test_updated_plugin_notifies_once_per_session(home):
    script = _plugin(_cache(home, "aaa"))
    _installed(home, [{"scope": "user", "installPath": str(_cache(home, "bbb"))}])
    assert json.loads(_run(home, script)) == {"systemMessage": NOTICE}
    assert _run(home, script) == ""
    assert json.loads(_run(home, script, session="s2")) == {"systemMessage": NOTICE}


def test_state_keeps_last_20_sessions(home):
    script = _plugin(_cache(home, "aaa"))
    _installed(home, [{"scope": "user", "installPath": str(_cache(home, "bbb"))}])
    for i in range(25):
        _run(home, script, session=f"s{i}")
    data = json.loads((home / ".claude/.loadout/reload-notified.json").read_text())
    assert data["sessions"] == [f"s{i}" for i in range(5, 25)]


def test_any_matching_entry_is_silent(home):
    script = _plugin(_cache(home, "aaa"))
    _installed(home, [{"scope": "user", "installPath": str(_cache(home, "bbb"))},
                      {"scope": "project", "projectPath": "/x", "installPath": str(_cache(home, "aaa"))}])
    assert _run(home, script) == ""


def test_dev_checkout_outside_the_cache_is_silent(home, tmp_path):
    script = _plugin(tmp_path / "repo/plugins/loadout")
    _installed(home, [{"scope": "user", "installPath": str(_cache(home, "bbb"))}])
    assert _run(home, script) == ""


@pytest.mark.parametrize("content", [None, "{ broken", json.dumps({"version": 2, "plugins": {}}),
                                     json.dumps({"version": 2, "plugins": {"loadout@agent-loadout": "x"}}),
                                     json.dumps({"version": 2, "plugins": {"loadout@agent-loadout": [{"scope": "user"}]}})])
def test_missing_or_malformed_installed_plugins_is_silent(home, content):
    script = _plugin(_cache(home, "aaa"))
    if content is not None:
        _installed(home, content)
    assert _run(home, script) == ""


@pytest.mark.parametrize("raw", ["", "not json", "[]", json.dumps({"hook_event_name": "Stop"})])
def test_bad_stdin_is_silent(home, raw):
    script = _plugin(_cache(home, "aaa"))
    _installed(home, [{"scope": "user", "installPath": str(_cache(home, "bbb"))}])
    assert _run(home, script, raw=raw) == ""


def test_unwritable_state_is_silent(home):
    script = _plugin(_cache(home, "aaa"))
    _installed(home, [{"scope": "user", "installPath": str(_cache(home, "bbb"))}])
    (home / ".claude/.loadout").write_text("a file, not a folder")
    assert _run(home, script) == ""  # cannot record the session: say nothing rather than repeat every turn


def test_hooks_json_wires_reload_check_soft_on_session_start_and_stop():
    hooks = json.loads((paths.kit_root() / "plugins/loadout/hooks/hooks.json").read_text())["hooks"]
    for event in ("SessionStart", "Stop"):
        cmds = [h["command"] for g in hooks[event] for h in g["hooks"]]
        assert any("run.sh\" --soft python3" in c and "hooks/reload_check.py" in c for c in cmds), event
```

- [ ] **Step 2: Run, expect FAIL** (script missing)

Run: `uv run --python 3.12 --with pytest pytest tests/test_reload_check.py -q`

- [ ] **Step 3: Implement `plugins/loadout/hooks/reload_check.py`**

```python
#!/usr/bin/env python3
"""SessionStart and Stop hook: tell the user once per session when the loadout plugin was updated
after the session started (stdlib only; always exit 0; silent on any error).

The running plugin is this file's plugin folder. Claude Code records the current install in
~/.claude/plugins/installed_plugins.json. When the running copy sits in the plugin cache and no
install entry points at it any more, the session still runs the old skills and hooks until
/reload-plugins. A dev checkout (claude --plugin-dir) is outside the cache and never notified.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PLUGIN = "loadout@agent-loadout"
KEEP = 20
NOTICE = ("loadout: the plugin was updated after this session started. "
          "Run /reload-plugins to load the new skills and hooks.")


def _home() -> Path:
    return Path(os.environ.get("HOME") or os.environ.get("USERPROFILE") or str(Path.home()))


def _resolve(p: str | Path) -> Path:
    return Path(p).expanduser().resolve()


def outdated(root: Path, home: Path) -> bool:
    cache = _resolve(home / ".claude" / "plugins" / "cache")
    if cache not in root.parents:
        return False
    data = json.loads((home / ".claude" / "plugins" / "installed_plugins.json").read_text(encoding="utf-8"))
    entries = data["plugins"][PLUGIN]
    paths = [_resolve(e["installPath"]) for e in entries if isinstance(e, dict) and isinstance(e.get("installPath"), str)]
    return bool(paths) and root not in paths


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
        session = payload.get("session_id") if isinstance(payload, dict) else None
        if not isinstance(session, str) or not session:
            return 0
        home = _home()
        if not outdated(_resolve(Path(__file__)).parent.parent, home):
            return 0
        state = home / ".claude" / ".loadout" / "reload-notified.json"
        try:
            seen = json.loads(state.read_text(encoding="utf-8")).get("sessions", [])
            seen = [s for s in seen if isinstance(s, str)] if isinstance(seen, list) else []
        except (OSError, ValueError, AttributeError):
            seen = []
        if session in seen:
            return 0
        state.parent.mkdir(parents=True, exist_ok=True)
        tmp = state.with_name(f".{state.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps({"sessions": (seen + [session])[-KEEP:]}) + "\n", encoding="utf-8")
        os.replace(tmp, state)  # record first: never repeat the notice when the state cannot be written
        sys.stdout.write(json.dumps({"systemMessage": NOTICE}) + "\n")
    except Exception:  # a hook must never break a session
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Wire `hooks.json`** — add as the last hook of the `SessionStart` group and of the `Stop` group:

```json
{ "type": "command", "command": "\"${CLAUDE_PLUGIN_ROOT}/hooks/run.sh\" --soft python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/reload_check.py\"", "shell": "bash", "timeout": 5 }
```

- [ ] **Step 5: Run the full suite, expect PASS** (`tests/test_hooks.py` checks every hook has `${CLAUDE_PLUGIN_ROOT}` and a timeout)

- [ ] **Step 6: Docs**

- `docs/reference/hooks.md` table: two rows, `SessionStart` and `Stop`, `all`, `--soft python3 hooks/reload_check.py`, `5 s`, "Tells you once per session to run `/reload-plugins` when Claude Code updated the plugin after the session started (the session keeps the old skills and hooks until then). State: `~/.claude/.loadout/reload-notified.json`."
- `docs/how-to/troubleshooting.md`: symptom "loadout skills or hooks are missing in a session that started before an update", fix "`/reload-plugins` (loadout reminds you once per session), or start a new session".

- [ ] **Step 7: Commit**

```bash
git add plugins/loadout/hooks/reload_check.py plugins/loadout/hooks/hooks.json tests/test_reload_check.py docs/reference/hooks.md docs/how-to/troubleshooting.md
git commit -m "feat(hooks): remind once per session to run /reload-plugins after a plugin update"
```

---

### Task 8: Execution-advisor follow-ups

**Files:**
- Modify: `plugins/loadout/skills/execution-advisor/SKILL.md` (§2 Risk row, §6)
- Modify: `plugins/loadout/hooks/advisor.py` (`stop`, new `_ledger_started`)
- Modify: `docs/explanation/execution-advisor.md` (the "When the hook nudges" section and, if it lists parallel work, the parallel rule)
- Test: `tests/test_advisor.py`

**Interfaces:**
- Produces: `advisor._ledger_started(plan_path: str) -> bool`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_advisor.py`; uses its `_record`, `_stop`, `_write`, `home`, `plan` helpers)

```python
def _ledger(plan, text):
    ledger = plan.parents[3] / ".superpowers/sdd" / plan.stem / "progress.md"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(text)


def test_stop_skips_plan_whose_ledger_records_progress(home, plan):
    _ledger(plan, "# progress\nTask 1: complete\n")
    _record(home, plan)
    assert _stop(home).stdout == ""


def test_stop_nudges_when_ledger_has_no_completed_task(home, plan):
    _ledger(plan, "# progress\nTask 1: started\nnotes: Task 2: complete is planned\n")
    _record(home, plan)
    assert json.loads(_stop(home).stdout)["decision"] == "block"


def test_stop_handles_plan_outside_docs_superpowers(home, tmp_path):
    other = _write(tmp_path / "x/plans/2026-10-09-export.md")
    _record(home, other)
    assert json.loads(_stop(home).stdout)["decision"] == "block"  # no ledger lookup, no crash
```

- [ ] **Step 2: Run, expect the first test to FAIL** (it blocks)

Run: `uv run --python 3.12 --with pytest pytest tests/test_advisor.py -q`

- [ ] **Step 3: Implement in `advisor.py`**

```python
LEDGER_DONE = re.compile(r"^Task \d+: complete", re.M)


def _ledger_started(plan_path: str) -> bool:
    """An sdd-workspace ledger (<repo>/.superpowers/sdd/<plan stem>/progress.md) records a finished task."""
    p = Path(plan_path)
    if p.parent.parts[-3:] != ("docs", "superpowers", "plans"):
        return False
    text = _read(str(p.parents[3] / ".superpowers" / "sdd" / p.stem / "progress.md"))
    return bool(text and LEDGER_DONE.search(text))
```

In `stop()`, change the skip condition to:

```python
            if text is None or not looks_like_plan(text) or TICKED.search(text) or _ledger_started(path):
                continue  # gone, not a plan, or execution has started
```

Update the module docstring's `advisor.py stop` paragraph: "(no ticked box and no `Task N: complete` line in its sdd-workspace ledger)".

- [ ] **Step 4: Run the file, expect PASS**

- [ ] **Step 5: Edit `SKILL.md`**

§2, Risk row, right column: `Per-task independent review is worth its cost (a Delegated or Inline row with per-task review)`.

§6, append a bullet under "Inline and Hybrid":

```markdown
  - **Parallel**: independent Delegated rows that touch disjoint files may be dispatched in parallel (one message, several implementer subagents); record each as its own `Task <N>: complete` line.
```

- [ ] **Step 6: Docs** — `docs/explanation/execution-advisor.md`: in "When the hook nudges", add that a plan counts as being executed when it has a ticked box or its sdd-workspace ledger records `Task N: complete`. If the page describes the run options, add the parallel rule in one sentence.

- [ ] **Step 7: Run the full suite (includes `tests/test_evals_static.py` and `tests/test_skills.py`), expect PASS, then commit**

```bash
git add plugins/loadout/hooks/advisor.py plugins/loadout/skills/execution-advisor/SKILL.md tests/test_advisor.py docs/explanation/execution-advisor.md
git commit -m "feat(advisor): honour sdd ledgers in the stop hook; allow parallel delegated rows"
```

- [ ] **Step 8: Eval decision (Inline, ask the user)**

The Risk-row wording affects no graded case. The parallel rule touches the scenario of `execution-advisor-sdd` (eight independent tasks); its grader accepts any all-delegated answer, so a regression is unlikely. Ask the user whether to run `plugins/loadout/evals/run.sh --case execution-advisor-sdd` (one case, plan usage) or skip. Do not run it without a yes.

---

### Task 9: Agent notes, docs-sync and re-index

**Files:**
- Modify: `.serena/memories/` (the Windows/WSL note; find it with `ls .serena/memories`)
- Modify: `AGENTS.md` only if Tasks 2 and 4 missed something

- [ ] **Step 1:** Update the Serena memory about Windows/WSL: 1–3 lines saying WSL is detected (`cli/loadout/wsl.py`, `loadout check`), with a link to `docs/how-to/wsl.md`; mention the WSL 2 CI job.
- [ ] **Step 2:** Run the full suite once more: `uv run --python 3.12 --with pytest pytest -q`. Expected: all pass.
- [ ] **Step 3:** Commit: `git commit -m "docs(memories): note WSL detection and the WSL 2 CI job"`.
- [ ] **Step 4 (after the final review):** `/loadout:docs-sync`, then re-index codebase-memory (`index_repository` for this repo).
