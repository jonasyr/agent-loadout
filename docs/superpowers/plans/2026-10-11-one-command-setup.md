# One-Command Setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One command takes a bare machine to a green `loadout check`: bootstrap installs everything it can in user space (uv → Python, Claude Code, mise → Node/gh/rust-analyzer, the npm tools), fixes PATH, and lists the few manual steps per OS.

**Architecture:** The entry scripts `bootstrap.sh`/`bootstrap.ps1` become thin: detect a checkout (or clone one), ensure uv, then run `loadout bootstrap` through `uv run`. Inside, the catalog gains install commands plus `needs`/`helper` fields; `check_prereqs` installs in dependency order with an updated PATH; a marked PATH block goes into the shell profile; the `loadout` launcher and `run.sh --python` fall back to uv when there is no Python 3.10+. A new CI workflow proves it on fresh machines.

**Tech Stack:** Python 3.10+ stdlib, bash, PowerShell, pytest via uv, GitHub Actions (container `ubuntu:24.04`).

**Spec:** `docs/superpowers/specs/2026-10-11-one-command-setup-design.md`

## Global Constraints

- Ruling (plan writing): uv runs loadout with `--python ">=3.10"` instead of the spec's `3.12`, so an existing suitable Python is reused and 3.12 is downloaded only when none exists (the spec's intent: "if no suitable one exists").

- No step uses sudo or administrator rights. Installers write to the user's home only.
- A tool already on `PATH` (after the PATH update) is never installed again or replaced.
- Python 3.10+, standard library only in `cli/loadout/` and hook scripts.
- Tests use `fake_home` and `fake_runner`. Never touch the real `~/.claude`, `~/.claude.json`, `~/.config/loadout`. Agents never run real installers or mutating `claude` commands; real installers run only in the fresh-machine CI workflow.
- Native Windows is "experimental and not recommended"; WSL 2 is the recommended Windows setup. Exact warning text: `Native Windows is experimental and not recommended. WSL 2 is the recommended setup on Windows: docs/how-to/wsl.md`.
- Shell profile marker: `# loadout PATH` (separate from `# loadout secrets`).
- Conventional Commits; no `Co-Authored-By` or other attribution.
- Test command: `uv run --python 3.12 --with pytest pytest -q` (single file: append the path).

## Review Focus

1. **The one-liner's stdin is the script pipe** (`curl … | bash`): bootstrap's questions must read the terminal (`/dev/tty`) when one exists, and run non-interactively without one. Test in Task 7.
2. **macOS ships `python3` 3.9**: the `loadout` launcher and `run.sh --python` must treat it as missing and use uv, not fail with the 3.10 guard. Tests in Task 4 (a stub `python3` that reports 3.9).
3. **bash 3.2 on macOS** with `set -u`: an empty argument array must not abort the entry script. Test in Task 7 (no arguments at all).
4. **Ubuntu's `~/.bashrc` returns early for non-interactive shells**, so a PATH block only there is invisible to `bash -l`, Claude Code's hook shells and CI. The block must also go into `~/.profile` (or `~/.bash_profile` when that exists). Test in Task 3.
5. **The uv installer edits shell profiles by default**: run it with `UV_NO_MODIFY_PATH=1` so only loadout's marked block changes profiles. Test in Task 7 (stub curl records the environment).

---

### Task 1: Catalog: install commands, `needs`, `helper`, install order

**Files:**
- Modify: `catalog.json` (entries `claude`, `node`, `gh`, `rust-analyzer`, `serena`, `playwright-cli`, `pyright`, `typescript-language-server`; new entry `mise`)
- Modify: `cli/loadout/catalog.py` (new `install_order`)
- Modify: `cli/loadout/check.py` (`_binaries` skips helpers)
- Modify: `docs/reference/catalog-format.md` (fields `needs`, `helper`)
- Test: `tests/test_repo_static.py`, `tests/test_catalog_order.py` (new)

**Interfaces:**
- Produces: `catalog.install_order(entries: list[dict]) -> list[dict]` (stable topological order by `needs`; raises `ValueError` on a cycle or unknown id); catalog fields `needs: list[str]`, `helper: bool`.

- [ ] **Step 1: Write the failing tests**

`tests/test_catalog_order.py`:

```python
import pytest

from loadout import catalog


def _e(i, needs=()):
    return {"id": i, "kind": "binary", "needs": list(needs)}


def test_install_order_puts_needs_first_and_keeps_catalog_order_otherwise():
    entries = [_e("claude"), _e("playwright-cli", ["node"]), _e("uv"), _e("node", ["mise"]), _e("mise"), _e("serena", ["uv"])]
    assert [e["id"] for e in catalog.install_order(entries)] == ["claude", "uv", "mise", "node", "playwright-cli", "serena"]


def test_install_order_rejects_cycles_and_unknown_ids():
    with pytest.raises(ValueError):
        catalog.install_order([_e("a", ["b"]), _e("b", ["a"])])
    with pytest.raises(ValueError):
        catalog.install_order([_e("a", ["nope"])])


def test_real_catalog_orders_cleanly():
    ids = [e["id"] for e in catalog.install_order(catalog.binaries())]
    assert ids.index("uv") < ids.index("serena")
    assert ids.index("mise") < ids.index("node") < ids.index("playwright-cli")
```

Append to `tests/test_repo_static.py`:

```python
def test_toolchain_installs_in_user_space():
    entries = {e["id"]: e for e in _json("catalog.json")["entries"]}
    for tool in ("claude", "node", "gh", "rust-analyzer", "mise"):
        for plat in ("posix", "windows"):
            assert entries[tool]["install"][plat], (tool, plat)
    for cmds in (e.get("install", {}) for e in entries.values()):
        for cmd in (c for plat in cmds.values() for c in plat):
            assert "sudo" not in cmd and "sudo" not in " ".join(cmd), cmd
    assert entries["mise"]["helper"] is True
    assert entries["node"]["needs"] == ["mise"] and entries["serena"]["needs"] == ["uv"]
    for tool in ("playwright-cli", "pyright", "typescript-language-server"):
        assert entries[tool]["needs"] == ["node"]
    known = set(entries)
    for e in entries.values():
        assert set(e.get("needs", [])) <= known, e["id"]
```

- [ ] **Step 2: Run them, expect FAIL** (`AttributeError: install_order`, `KeyError: 'install'`)

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_catalog_order.py tests/test_repo_static.py`

- [ ] **Step 3: Implement `install_order`** in `cli/loadout/catalog.py`

```python
def install_order(entries: list[dict]) -> list[dict]:
    """Catalog order, except that every entry comes after the entries it `needs`."""
    by_id = {e["id"]: e for e in entries}
    out, done, active = [], set(), set()

    def visit(e: dict) -> None:
        if e["id"] in done:
            return
        if e["id"] in active:
            raise ValueError(f"catalog: dependency cycle at {e['id']}")
        active.add(e["id"])
        for dep in e.get("needs", []):
            if dep not in by_id:
                raise ValueError(f"catalog: {e['id']} needs unknown {dep}")
            visit(by_id[dep])
        active.discard(e["id"])
        done.add(e["id"])
        out.append(e)

    for e in entries:
        visit(e)
    return out
```

- [ ] **Step 4: Change `catalog.json`**

- `claude`: add `"install": {"posix": [["sh", "-c", "curl -fsSL https://claude.ai/install.sh | bash"]], "windows": [["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", "irm https://claude.ai/install.ps1 | iex"]]}`. Keep `manual` and `update`.
- New entry right after `uv`:

```json
{"id": "mise", "kind": "binary", "status": "core", "helper": true, "match": {"names": ["mise"]}, "reason": "Installs Node.js, gh and rust-analyzer in your home folder when they are missing (no sudo).", "version": {"cmd": ["mise", "--version"], "github": "jdx/mise"}, "install": {"posix": [["sh", "-c", "curl -fsSL https://mise.run | sh"]], "windows": [["winget", "install", "--id", "jdx.mise", "-e", "--scope", "user", "--accept-source-agreements", "--accept-package-agreements"]]}, "update": {"posix": [["mise", "self-update", "-y"]], "windows": [["winget", "upgrade", "--id", "jdx.mise", "-e"]]}}
```

- `node`: `"needs": ["mise"]`, `"install": {"posix": [["mise", "use", "-g", "node@lts"]], "windows": [["mise", "use", "-g", "node@lts"]]}`.
- `gh`: `"needs": ["mise"]`, install `["mise", "use", "-g", "gh"]` on both.
- `rust-analyzer`: `"needs": ["mise"]`, install `["mise", "use", "-g", "rust-analyzer"]` on both.
- `serena`: `"needs": ["uv"]`. `playwright-cli`, `pyright`, `typescript-language-server`: `"needs": ["node"]`.

Verify the mise tool names before committing: `mise registry | grep -E '^(node|gh|rust-analyzer) '` (read-only) if mise is installed locally; otherwise check https://mise.jdx.dev/registry.html with WebFetch. Record the result in the report; if `--scope user` is not accepted for `jdx.mise` (check `https://github.com/microsoft/winget-pkgs/tree/master/manifests/j/jdx/mise` for `Scope: user` or an `InstallerType` that supports it), drop `--scope user` and note it as a Ruling.

- [ ] **Step 5: `check._binaries` skips helpers** (a helper is only installed for others; its absence is not a problem)

```python
    for entry in catalog.binaries():
        if entry.get("helper"):
            continue
```

Add to `tests/test_check.py`:

```python
def test_helper_binaries_are_not_checked(fake_home, fake_runner):
    fake_runner.missing.add("mise")
    assert "binary mise" not in _by(check.run_checks())
```

- [ ] **Step 6: Docs** — `docs/reference/catalog-format.md` fields table, after `mise`:
  - `| needs | no | For a binary: ids of binaries it is installed with (for example "node" needs "mise"). Bootstrap installs those first and skips this one if they failed. |`
  - `| helper | no | For a binary: installed only when another binary needs it; \`loadout check\` does not report it. |`

- [ ] **Step 7: Run the full suite, expect PASS, commit**

```bash
git add catalog.json cli/loadout/catalog.py cli/loadout/check.py docs/reference/catalog-format.md tests/test_catalog_order.py tests/test_repo_static.py tests/test_check.py
git commit -m "feat(catalog): user-space install commands for the toolchain, with install order"
```

---

### Task 2: Install in order with an updated PATH

**Files:**
- Modify: `cli/loadout/paths.py` (new `tool_dirs`)
- Modify: `cli/loadout/bootstrap.py` (`check_prereqs`, new `_prepend_tool_dirs`)
- Test: `tests/test_toolchain.py` (new)

**Interfaces:**
- Consumes: `catalog.install_order`, entry fields `needs`, `helper` (Task 1); `pkgmgr.run_cwd(cmd)`.
- Produces: `paths.tool_dirs() -> list[Path]` (existing folders only, in priority order); `bootstrap.prepend_tool_dirs() -> None` (updates `os.environ["PATH"]`, no duplicates); `check_prereqs(install, ask) -> list[str]` keeps its signature and return value (names still missing).

- [ ] **Step 1: Write the failing tests** (`tests/test_toolchain.py`)

```python
import os
from pathlib import Path

from loadout import bootstrap as b, catalog, paths, runner


def _only(monkeypatch, entries):
    monkeypatch.setattr(catalog, "binaries", lambda: entries)


def _bin(i, needs=(), required=True, helper=False):
    e = {"id": i, "kind": "binary", "status": "core", "required": required, "needs": list(needs),
         "install": {"posix": [[f"install-{i}"]], "windows": [[f"install-{i}"]]}, "version": {"cmd": [i, "--version"]}}
    if helper:
        e["helper"] = True
    return e


def test_tool_dirs_lists_existing_user_folders(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(paths, "platform_key", lambda: "posix")
    (fake_home / ".local/bin").mkdir(parents=True)
    (fake_home / ".local/share/mise/shims").mkdir(parents=True)
    assert paths.tool_dirs() == [fake_home / ".local/bin", fake_home / ".local/share/mise/shims"]


def test_prepend_tool_dirs_is_idempotent(fake_home, fake_runner, monkeypatch):
    (fake_home / ".local/bin").mkdir(parents=True)
    monkeypatch.setenv("PATH", "/usr/bin")
    b.prepend_tool_dirs()
    b.prepend_tool_dirs()
    parts = os.environ["PATH"].split(os.pathsep)
    assert parts.count(str(fake_home / ".local/bin")) == 1 and parts[0] == str(fake_home / ".local/bin")


def test_installs_dependencies_first_and_only_what_is_missing(fake_home, fake_runner, monkeypatch):
    _only(monkeypatch, [_bin("playwright-cli", ["node"]), _bin("node", ["mise"]), _bin("mise", helper=True, required=False), _bin("uv")])
    fake_runner.missing.update({"playwright-cli", "node", "mise"})  # uv is already there

    def run(cmd, cwd=None, timeout=300, env=None):
        fake_runner.calls.append(list(cmd))
        fake_runner.missing.discard(cmd[0].removeprefix("install-"))  # the install worked
        return runner.Result(0, "", "")

    monkeypatch.setattr(runner, "run", run)
    assert b.check_prereqs(True, lambda q: "") == []
    assert fake_runner.calls == [["install-mise"], ["install-node"], ["install-playwright-cli"]]


def test_helper_is_not_installed_when_nothing_needs_it(fake_home, fake_runner, monkeypatch):
    _only(monkeypatch, [_bin("node", ["mise"]), _bin("mise", helper=True, required=False)])
    fake_runner.missing.add("mise")  # node is there: no mise
    b.check_prereqs(True, lambda q: "")
    assert ["install-mise"] not in fake_runner.calls


def test_failed_dependency_skips_dependants(fake_home, fake_runner, monkeypatch, capsys):
    _only(monkeypatch, [_bin("node", ["mise"]), _bin("mise", helper=True, required=False)])
    fake_runner.missing.update({"node", "mise"})
    fake_runner.responses[("install-mise",)] = runner.Result(1, "", "boom")
    missing = b.check_prereqs(True, lambda q: "")
    assert ["install-node"] not in fake_runner.calls
    assert "node" in missing
    assert "skipped: needs mise" in capsys.readouterr().out


def test_mise_commands_run_in_home(fake_home, fake_runner, monkeypatch):
    e = _bin("node", ["mise"])
    e["install"] = {"posix": [["mise", "use", "-g", "node@lts"]], "windows": [["mise", "use", "-g", "node@lts"]]}
    _only(monkeypatch, [e, _bin("mise", helper=True, required=False)])
    fake_runner.missing.add("node")
    seen = []
    monkeypatch.setattr(runner, "run", lambda cmd, cwd=None, timeout=300, env=None: seen.append((cmd, cwd)) or runner.Result(0, "", ""))
    b.check_prereqs(True, lambda q: "")
    assert (["mise", "use", "-g", "node@lts"], str(paths.home())) in seen


def test_without_install_flag_nothing_runs(fake_home, fake_runner, monkeypatch):
    _only(monkeypatch, [_bin("node", ["mise"]), _bin("mise", helper=True, required=False)])
    fake_runner.missing.update({"node", "mise"})
    assert b.check_prereqs(False, lambda q: "") == ["node"]
    assert not any(c[0].startswith("install-") for c in fake_runner.calls)
```

- [ ] **Step 2: Run, expect FAIL** (`AttributeError: tool_dirs`)

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_toolchain.py`

- [ ] **Step 3: Implement `paths.tool_dirs`**

```python
def tool_dirs() -> list[Path]:
    """Where user-space installers put commands (uv, Claude Code, mise shims, npm globals), existing ones only."""
    base = home()
    if platform_key() == "windows":
        local = Path(os.environ.get("LOCALAPPDATA") or base / "AppData" / "Local")
        dirs = [base / ".local" / "bin", local / "mise" / "shims"]
    else:
        dirs = [base / ".local" / "bin", base / ".local" / "share" / "mise" / "shims"]
    return [d for d in dirs if d.is_dir()]
```

The npm global folder is not listed: with mise-managed node, `mise reshim` (Step 4) exposes npm globals through the shims folder; with a system node, its global bin is already on PATH.

- [ ] **Step 4: Rewrite `check_prereqs`** in `cli/loadout/bootstrap.py`

```python
def prepend_tool_dirs() -> None:
    parts = os.environ.get("PATH", "").split(os.pathsep)
    new = [str(d) for d in paths.tool_dirs() if str(d) not in parts]
    if new:
        os.environ["PATH"] = os.pathsep.join(new + [p for p in parts if p])


def _wanted(entry: dict) -> bool:
    return bool(entry.get("required") or entry["status"] == "recommended")


def check_prereqs(install: bool, ask: Ask) -> list[str]:
    from . import pkgmgr
    prepend_tool_dirs()
    entries = catalog.install_order(catalog.binaries())
    # helpers are wanted only when a missing, wanted binary needs them
    needed = {d for e in entries if not e.get("helper") and _wanted(e) and not runner.have(e["id"])
              for d in e.get("needs", [])}
    missing, failed = [], set()
    for entry in entries:
        name = entry["id"]
        wanted = name in needed if entry.get("helper") else _wanted(entry)
        if not wanted or runner.have(name):
            continue
        cmds = catalog.platform_cmds(entry, "install")
        blocked = [d for d in entry.get("needs", []) if d in failed]
        if install and cmds and blocked:
            print(f"missing {name}: skipped: needs {', '.join(blocked)}")
        elif install and cmds:
            for cmd in cmds:
                print("installing: " + " ".join(cmd))
                res = runner.run(cmd, cwd=pkgmgr.run_cwd(cmd), timeout=900)
                if not res.ok:
                    print(f"  failed: {res.stderr.strip()[:300]}")
            prepend_tool_dirs()
            if name in ("playwright-cli", "pyright", "typescript-language-server") and runner.have("mise"):
                runner.run(["mise", "reshim"], cwd=pkgmgr.run_cwd(["mise"]), timeout=120)  # shims for npm globals
                prepend_tool_dirs()
        if not runner.have(name):
            failed.add(name)
            if not entry.get("helper"):
                hint = "re-run with --install" if cmds else entry.get("manual", "")
                print(f"missing {'(required) ' if entry.get('required') else ''}{name}: {hint}")
                missing.append(name)
    # keep the existing gh auth block that followed the old loop here, unchanged
```

Keep the existing `gh auth` lines after the loop and the `return missing` exactly as they were.

- [ ] **Step 5: Run the file and the full suite, expect PASS** (`tests/test_bootstrap.py` exercises `check_prereqs` through `bootstrap()`)

- [ ] **Step 6: Commit**

```bash
git add cli/loadout/paths.py cli/loadout/bootstrap.py tests/test_toolchain.py
git commit -m "feat(bootstrap): install missing tools in dependency order with an updated PATH"
```

---

### Task 3: PATH block in the shell profile (and the Windows user PATH)

**Files:**
- Modify: `cli/loadout/bootstrap.py` (generalise `_add_block`; new `setup_path`; call it in `bootstrap()`)
- Test: `tests/test_toolchain.py`

**Interfaces:**
- Consumes: `paths.tool_dirs()` (Task 2).
- Produces: `bootstrap.PATH_MARKER = "# loadout PATH"`; `bootstrap.setup_path(bk: Backup | None) -> list[str]` (lines to print; empty when nothing changed); `_add_block(rc, block, bk, windows, marker=RC_MARKER, what="secrets loading")`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_toolchain.py`)

```python
def test_path_block_goes_to_rc_and_login_profile(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(paths, "platform_key", lambda: "posix")
    monkeypatch.setenv("SHELL", "/bin/bash")
    (fake_home / ".local/bin").mkdir(parents=True)
    (fake_home / ".bashrc").write_text("case $- in *i*) ;; *) return;; esac\n")
    out = b.setup_path(None)
    assert out
    for f in (".bashrc", ".profile"):
        text = (fake_home / f).read_text()
        assert text.count(b.PATH_MARKER) == 1
        assert '"$HOME/.local/bin"' in text
    assert b.setup_path(None) == []  # idempotent: nothing changed, nothing to say


def test_path_block_prefers_existing_bash_profile(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(paths, "platform_key", lambda: "posix")
    monkeypatch.setenv("SHELL", "/bin/bash")
    (fake_home / ".local/bin").mkdir(parents=True)
    (fake_home / ".bash_profile").write_text("# mine\n")
    b.setup_path(None)
    assert b.PATH_MARKER in (fake_home / ".bash_profile").read_text()
    assert not (fake_home / ".profile").exists()


def test_path_block_skips_folders_outside_home_and_missing_ones(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(paths, "platform_key", lambda: "posix")
    monkeypatch.setattr(paths, "tool_dirs", lambda: [Path("/opt/elsewhere/bin")])
    assert b.setup_path(None) == []


def test_windows_user_path_is_extended_once(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(paths, "platform_key", lambda: "windows")
    (fake_home / ".local/bin").mkdir(parents=True)
    get = ("powershell", "-NoProfile", "-Command", "[Environment]::GetEnvironmentVariable('Path', 'User')")
    fake_runner.responses[get] = runner.Result(0, "C:\\Tools\r\n", "")
    out = b.setup_path(None)
    sets = [c for c in fake_runner.calls if "SetEnvironmentVariable" in " ".join(c)]
    assert len(sets) == 1 and str(fake_home / ".local/bin") in sets[0][-1] and "C:\\Tools" in sets[0][-1]
    assert out
```

- [ ] **Step 2: Run, expect FAIL** (`AttributeError: setup_path`)

- [ ] **Step 3: Generalise `_add_block`**: add parameters `marker: str = RC_MARKER, what: str = "secrets loading"`; replace every `RC_MARKER` inside the function with `marker`, and the messages `"... before adding secrets loading"`, `"added secrets loading to"`, `"created ... with secrets loading"` with `what`. Existing callers keep working (defaults).

- [ ] **Step 4: Implement `setup_path`**

```python
PATH_MARKER = "# loadout PATH"


def _path_block(dirs: list[Path]) -> str:
    home = paths.home()
    lines = [PATH_MARKER]
    for d in reversed(dirs):  # prepend in reverse, so the first folder ends up first
        rel = d.relative_to(home).as_posix()
        lines.append(f'case ":$PATH:" in *":$HOME/{rel}:"*) ;; *) PATH="$HOME/{rel}:$PATH" ;; esac')
    lines.append("export PATH")
    return "\n".join(lines) + "\n"


def setup_path(bk: Backup | None = None) -> list[str]:
    """Make the folders user-space installers use visible to new terminals (and to Claude Code)."""
    home = paths.home()
    dirs = [d for d in paths.tool_dirs() if d == home or home in d.parents]
    if not dirs:
        return []
    if paths.platform_key() == "windows":
        return _setup_windows_path(dirs)
    shell = os.path.basename(os.environ.get("SHELL", ""))
    targets = [r for r in (home / ".bashrc", home / ".zshrc") if r.exists()]
    own = {"zsh": home / ".zshrc", "bash": home / ".bashrc"}.get(shell)
    if own is not None and own not in targets:
        targets.append(own)
    # login shells (bash -l, hook shells, CI) skip an interactive-only .bashrc
    login = home / ".bash_profile" if (home / ".bash_profile").exists() else home / ".profile"
    targets.append(login)
    block = _path_block(dirs)
    return [line for rc in dict.fromkeys(targets)
            if (line := _add_block(rc, block, bk, False, marker=PATH_MARKER, what="the tool folders to PATH"))]


def _setup_windows_path(dirs: list[Path]) -> list[str]:
    get = ["powershell", "-NoProfile", "-Command", "[Environment]::GetEnvironmentVariable('Path', 'User')"]
    res = runner.run(get, timeout=30)
    if not res.ok:
        return [f"could not read your user PATH; add {', '.join(map(str, dirs))} to it by hand"]
    current = [p for p in res.stdout.strip().split(";") if p]
    new = [str(d) for d in dirs if str(d).lower() not in {p.lower() for p in current}]
    if not new:
        return []
    value = ";".join(new + current).replace("'", "''")
    runner.run(["powershell", "-NoProfile", "-Command",
                f"[Environment]::SetEnvironmentVariable('Path', '{value}', 'User')"], timeout=30)
    return [f"added {', '.join(new)} to your user PATH (was: {';'.join(current) or 'empty'})"]
```

The Windows message prints the old value, which is the undo record (the user PATH is not a file the backup can copy).

- [ ] **Step 5: Call it in `bootstrap()`** right after the "Secrets" step:

```python
    _step("PATH")
    path_lines = setup_path(bk)
    for line in path_lines or ["PATH already set up"]:
        print(line)
```

and at the end, replace `print("\nRestart Claude Code to load plugins and rules.")` with:

```python
    print("\nOpen a new terminal so the new PATH applies, then start Claude Code." if path_lines
          else "\nRestart Claude Code to load plugins and rules.")
```

- [ ] **Step 6: Run the full suite, expect PASS** (the hermetic end-to-end bootstrap test must still pass; it now also writes a PATH block into its temp HOME)

- [ ] **Step 7: Commit**

```bash
git add cli/loadout/bootstrap.py tests/test_toolchain.py
git commit -m "feat(bootstrap): add the tool folders to PATH for new terminals"
```

---

### Task 4: `loadout` launcher and `run.sh --python` fall back to uv

**Files:**
- Modify: `cli/loadout/link.py` (`link_bin`, `write_windows_shims`)
- Modify: `plugins/loadout/hooks/run.sh`, `plugins/loadout/hooks/hooks.json`
- Modify: `tests/test_link_backup.py` (the POSIX symlink test becomes a launcher test)
- Test: `tests/test_launcher.py` (new), `tests/test_hooks.py`, `tests/test_reload_check.py` (hooks.json assertion)

**Interfaces:**
- Produces: `link.LAUNCHER_MARKER = "# loadout launcher"`; `link.launcher_text(script: Path) -> str`; `run.sh [--soft] --python SCRIPT ARGS...`.

- [ ] **Step 1: Write the failing tests**

`tests/test_launcher.py` (POSIX only):

```python
import os
import subprocess

import pytest

from loadout import backup, link, paths

pytestmark = pytest.mark.skipif(os.name == "nt", reason="POSIX launcher and run.sh")
RUN_SH = paths.kit_root() / "plugins/loadout/hooks/run.sh"


def _stub(d, name, body):
    f = d / name
    f.write_text("#!/bin/sh\n" + body + "\n")
    f.chmod(0o755)


def _env(stub_dir):
    return {"PATH": f"{stub_dir}:/usr/bin:/bin", "HOME": str(stub_dir)}


def test_link_bin_writes_launcher_and_keeps_user_file_in_backup(fake_home):
    target = fake_home / ".local/bin/loadout"
    target.parent.mkdir(parents=True)
    target.write_text("user script")
    bk = backup.Backup()
    link.link_bin(bk)
    assert link.LAUNCHER_MARKER in target.read_text() and os.access(target, os.X_OK)
    assert not bk.empty
    again = backup.Backup()
    link.link_bin(again)
    assert again.empty  # our own launcher is refreshed without a backup


def test_launcher_uses_python3_when_new_enough(tmp_path):
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    _stub(stubs, "python3", 'case "$1" in -c) exit 0;; esac; echo "python3 $*"')
    _stub(stubs, "uv", 'echo "uv $*"')
    launcher = tmp_path / "loadout"
    launcher.write_text(link.launcher_text(tmp_path / "kit/bin/loadout"))
    launcher.chmod(0o755)
    out = subprocess.run([str(launcher), "check"], env=_env(stubs), capture_output=True, text=True).stdout
    assert out.startswith("python3 ") and out.rstrip().endswith("check")


def test_launcher_falls_back_to_uv_for_old_python(tmp_path):
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    _stub(stubs, "python3", 'case "$1" in -c) exit 1;; esac; echo "python3 $*"')  # 3.9 (macOS)
    _stub(stubs, "uv", 'echo "uv $*"')
    launcher = tmp_path / "loadout"
    launcher.write_text(link.launcher_text(tmp_path / "kit/bin/loadout"))
    launcher.chmod(0o755)
    out = subprocess.run([str(launcher), "check"], env=_env(stubs), capture_output=True, text=True).stdout
    assert out.startswith("uv run --no-project --python >=3.10 ")


@pytest.mark.parametrize("have,expected", [
    ({"python3": 'case "$1" in -c) exit 0;; esac; echo "python3 $*"'}, "python3 "),
    ({"python3": 'case "$1" in -c) exit 1;; esac; echo "python3 $*"', "uv": 'echo "uv $*"'}, "uv run --no-project --python >=3.10 "),
    ({}, ""),
])
def test_run_sh_python(tmp_path, have, expected):
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    for name, body in have.items():
        _stub(stubs, name, body)
    proc = subprocess.run(["/bin/bash", str(RUN_SH), "--soft", "--python", "x.py", "stop"],
                          env={"PATH": str(stubs), "HOME": str(tmp_path)}, capture_output=True, text=True, input="{}")
    assert proc.returncode == 0 and proc.stderr == ""
    assert proc.stdout.startswith(expected) if expected else proc.stdout == ""
```

In `tests/test_link_backup.py`, replace `test_link_bin_posix_symlink` with:

```python
def test_link_bin_posix_writes_launcher(fake_home):
    if os.name == "nt":
        pytest.skip("posix only")
    link.link_bin(backup.Backup())
    target = fake_home / ".local/bin/loadout"
    assert link.LAUNCHER_MARKER in target.read_text()
    assert str(paths.kit_root() / "bin" / "loadout") in target.read_text()
```

and delete `test_copy_mode_file_backed_up_only_when_not_kit_copy` only if it fails because `link_bin` no longer copies in copy mode; its intent (a user file is backed up once, ours is refreshed silently) is covered by `test_link_bin_writes_launcher_and_keeps_user_file_in_backup`. Record the deletion as a Ruling.

In `tests/test_reload_check.py::test_hooks_json_wires_reload_check_soft_on_session_start_and_stop`, change the assertion to `'run.sh" --soft --python' in c and "hooks/reload_check.py" in c`.

- [ ] **Step 2: Run, expect FAIL** (`AttributeError: LAUNCHER_MARKER`)

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_launcher.py tests/test_link_backup.py tests/test_reload_check.py`

- [ ] **Step 3: Implement the launcher** in `cli/loadout/link.py`

```python
LAUNCHER_MARKER = "# loadout launcher"
PY_OK = "import sys; sys.exit(sys.version_info < (3, 10))"


def launcher_text(script: Path) -> str:
    s = script.as_posix().replace("'", "'\\''")
    return (f"#!/bin/sh\n{LAUNCHER_MARKER} (written by loadout bootstrap; Python 3.10+ or uv runs it)\n"
            f"script='{s}'\n"
            f'if command -v python3 >/dev/null 2>&1 && python3 -c "{PY_OK}" 2>/dev/null; then exec python3 "$script" "$@"; fi\n'
            'if command -v uv >/dev/null 2>&1; then exec uv run --no-project --python ">=3.10" "$script" "$@"; fi\n'
            'echo "loadout needs Python 3.10 or newer, or uv, on PATH" >&2\nexit 1\n')


def link_bin(bk: Backup) -> list[str]:
    target_dir = paths.bin_dir()
    if os.name == "nt":
        write_windows_shims(target_dir)
        return [f"wrote shims to {target_dir} (make sure it is on PATH)"]
    dest = target_dir / "loadout"
    text = launcher_text(paths.kit_root() / "bin" / "loadout")
    ours = dest.is_file() and not dest.is_symlink() and LAUNCHER_MARKER in dest.read_text(encoding="utf-8", errors="replace")
    if ours and dest.read_text(encoding="utf-8") == text:
        return []
    dest.parent.mkdir(parents=True, exist_ok=True)
    kit_link = dest.is_symlink() and _points_to(dest, paths.kit_root() / "bin" / "loadout")
    if (dest.exists() or dest.is_symlink()) and not ours and not kit_link:
        bk.move(dest, f"replaced {dest}", replace=True)
    elif dest.is_symlink() or dest.exists():
        dest.unlink()
    dest.write_text(text, encoding="utf-8", newline="\n")
    dest.chmod(0o755)
    return [f"wrote launcher {dest}"]
```

`write_windows_shims`: the `.cmd` becomes

```python
    cmd = (f'@echo off\r\nwhere python >nul 2>nul && python -c "{PY_OK}" 2>nul && (python "{script}" %* & exit /b)\r\n'
           f'uv run --no-project --python ">=3.10" "{script}" %*\r\n')
```

and the Git Bash shim becomes `launcher_text(script)` (it already runs under `/bin/sh`). Keep the existing quoting test (`test_windows_shims_quote_paths_with_spaces`) passing; update `test_git_bash_shim_has_lf_only_and_uses_current_python` to assert `LAUNCHER_MARKER` instead of `sys.executable` (Ruling: the shim no longer pins the interpreter that ran bootstrap, so a removed uv Python version cannot break it).

- [ ] **Step 4: `run.sh --python`**

```bash
#!/usr/bin/env bash
# Run a hook command only if its binary is installed, so a machine without a tool
# simply runs without that hook. With --soft, errors are swallowed (exit 0, no stderr).
# With --python, the next argument is a Python script: run it with python3 (3.10+),
# else through uv, else skip the hook.
soft=0
if [ "${1:-}" = "--soft" ]; then soft=1; shift; fi
if [ "${1:-}" = "--python" ]; then
  shift
  if command -v python3 >/dev/null 2>&1 && python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
    set -- python3 "$@"
  elif command -v uv >/dev/null 2>&1; then
    set -- uv run --no-project --python '>=3.10' "$@"
  else
    exit 0
  fi
fi
command -v "$1" >/dev/null 2>&1 || exit 0
if [ "$soft" = 1 ]; then
  "$@" 2>/dev/null
  exit 0
fi
exec "$@"
```

`hooks.json`: replace `--soft python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/advisor.py\"` (record and stop) and `--soft python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/reload_check.py\"` (SessionStart and Stop) with `--soft --python \"${CLAUDE_PLUGIN_ROOT}/...\"`. Update `docs/reference/hooks.md`: the `Runs` cells become `--soft --python hooks/advisor.py record` etc., and the paragraph about `run.sh` gets: "With `--python` it runs a Python script with `python3` 3.10+, or through `uv` when there is none."

- [ ] **Step 5: Run the full suite, expect PASS**

- [ ] **Step 6: Commit**

```bash
git add cli/loadout/link.py plugins/loadout/hooks/run.sh plugins/loadout/hooks/hooks.json docs/reference/hooks.md tests/test_launcher.py tests/test_link_backup.py tests/test_reload_check.py tests/test_hooks.py
git commit -m "feat: run loadout and its Python hooks through uv when there is no Python 3.10+"
```

---

### Task 5: `loadout check`: MCP servers on PATH

**Files:**
- Modify: `cli/loadout/check.py` (new `_mcp_path`)
- Modify: `docs/reference/cli.md` (check table)
- Test: `tests/test_check.py`

**Interfaces:**
- Consumes: `paths.tool_dirs()` (Task 2), `runner.which`.
- Produces: `check._mcp_path() -> list[CheckResult]`, one result named `MCP servers on PATH`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_check.py`)

```python
def test_mcp_servers_on_path_ok(fake_home, fake_runner):
    fake_runner.paths.update({"serena": "/usr/bin/serena", "codebase-memory-mcp": "/usr/bin/codebase-memory-mcp"})
    r = _by(check.run_checks())["MCP servers on PATH"]
    assert r.ok


def test_mcp_server_only_in_tool_dir_warns_to_open_new_terminal(fake_home, fake_runner, monkeypatch):
    d = fake_home / ".local/bin"
    d.mkdir(parents=True)
    (d / "serena").write_text("")
    fake_runner.paths["codebase-memory-mcp"] = "/usr/bin/codebase-memory-mcp"  # serena not on the current PATH
    monkeypatch.setattr(check.paths, "tool_dirs", lambda: [d])
    r = _by(check.run_checks())["MCP servers on PATH"]
    assert not r.ok and r.severity == "warn"
    assert "serena" in r.detail and "open a new terminal" in r.fix and str(d) in r.fix


def test_mcp_server_missing_everywhere_is_left_to_the_binary_check(fake_home, fake_runner):
    fake_runner.missing.update({"serena", "codebase-memory-mcp"})
    r = _by(check.run_checks())["MCP servers on PATH"]
    assert r.ok  # "binary serena" already fails with the install hint
```

- [ ] **Step 2: Run, expect FAIL** (`KeyError: 'MCP servers on PATH'`)

- [ ] **Step 3: Implement** in `check.py`, and add `*_mcp_path()` after `*_binaries()` in `run_checks()`:

```python
def _mcp_path() -> list[CheckResult]:
    """Claude Code starts the plugin's servers by name, so a new terminal's PATH must find them."""
    hidden = {}
    for name in ("serena", "codebase-memory-mcp"):
        if runner.which(name):
            continue
        for d in paths.tool_dirs():
            if any((d / f).exists() for f in (name, name + ".exe", name + ".cmd")):
                hidden[name] = d
                break
    dirs = sorted({str(d) for d in hidden.values()})
    return [CheckResult("MCP servers on PATH", not hidden, ", ".join(hidden),
                        f"open a new terminal, or add {', '.join(dirs)} to PATH", "warn")]
```

`fake_runner.which` returns `fake_runner.paths.get(name)`; tests that do not set `paths` get `None`, so make sure `_mcp_path` still reports ok when the binary is in no tool dir (third test).

- [ ] **Step 4: Docs** — `docs/reference/cli.md` check table: `| \`serena\` and \`codebase-memory-mcp\` are on the PATH a new terminal gets (Claude Code starts them by name) | warn |`.

- [ ] **Step 5: Run the full suite, expect PASS, commit**

```bash
git add cli/loadout/check.py docs/reference/cli.md tests/test_check.py
git commit -m "feat(check): warn when the MCP servers are only reachable after a new terminal"
```

---

### Task 6: Bootstrap end summary: installed and still to do

**Files:**
- Modify: `cli/loadout/bootstrap.py` (new `still_to_do`, `MANUAL_STEPS`; print in `bootstrap()`)
- Modify: `cli/loadout/wsl.py` (sandbox wording)
- Test: `tests/test_toolchain.py`, `tests/test_wsl.py`

**Interfaces:**
- Produces: `bootstrap.still_to_do(os_key: str) -> list[str]` with `os_key` in `{"linux", "macos", "windows"}`; `bootstrap.os_key() -> str`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_toolchain.py`)

```python
def test_still_to_do_lists_only_what_applies(fake_home, fake_runner):
    fake_runner.missing.add("git")
    fake_runner.responses[("gh", "auth", "status")] = runner.Result(1, "", "not logged in")
    lines = b.still_to_do("macos")
    assert "xcode-select --install" in "\n".join(lines)
    assert "gh auth login" in "\n".join(lines)
    assert any("claude" in l and "log in" in l for l in lines)


def test_still_to_do_windows_git_line(fake_home, fake_runner):
    fake_runner.missing.add("git")
    assert any("winget install --id Git.Git -e" in l for l in b.still_to_do("windows"))


def test_still_to_do_empty_when_all_done(fake_home, fake_runner):
    (fake_home / ".claude.json").write_text('{"oauthAccount": {"emailAddress": "x"}}')
    assert b.still_to_do("linux") == []
```

Append to `tests/test_wsl.py`:

```python
def test_sandbox_problem_says_what_it_is_for(fake_home, fake_runner, mnt, tmp_path):
    fake_runner.missing.update({"bwrap", "socat"})
    [(problem, _)] = [p for p in wsl.problems(2, tmp_path, mount=_prefix(mnt)) if "sandbox" in p[0]]
    assert "Claude Code's sandbox" in problem
```

and update `test_sandbox_packages_missing_only_on_wsl2` to the new text.

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement**

```python
MANUAL_STEPS = {
    "git": {"linux": "sudo apt install git   (Debian/Ubuntu; other distros: their package manager)",
            "macos": "xcode-select --install",
            "windows": "winget install --id Git.Git -e   (Git Bash runs the hooks)"},
}


def os_key() -> str:
    import sys
    if paths.platform_key() == "windows":
        return "windows"
    return "macos" if sys.platform == "darwin" else "linux"


def _claude_logged_in() -> bool:
    try:
        return bool(load_json(paths.claude_json()).get("oauthAccount"))
    except Exception:
        return False


def still_to_do(key: str) -> list[str]:
    out = []
    if not runner.have("git"):
        out.append(f"install git: {MANUAL_STEPS['git'][key]}")
    if runner.have("claude") and not _claude_logged_in():
        out.append("log in to Claude Code: claude   (or set ANTHROPIC_API_KEY)")
    if runner.have("gh") and not runner.run(["gh", "auth", "status"], timeout=20).ok:
        out.append("log in to GitHub: gh auth login && gh auth setup-git")
    return out
```

Plan check for `oauthAccount`: confirm by reading the key list of a `~/.claude.json` written by a logged-in Claude Code (read-only: `python3 -c "import json,os; print('oauthAccount' in json.load(open(os.path.expanduser('~/.claude.json'))))"`). If the key name differs, use the real one and record a Ruling.

In `bootstrap()`, before the final "Open a new terminal…/Restart…" line:

```python
    todo = still_to_do(os_key())
    if todo:
        print("\nStill to do:")
        for line in todo:
            print(f"  - {line}")
```

`wsl.py`: the sandbox problem text becomes `f"sandbox packages missing: {', '.join(missing)} (needed for Claude Code's sandbox)"`.

- [ ] **Step 4: Run the full suite, expect PASS, commit**

```bash
git add cli/loadout/bootstrap.py cli/loadout/wsl.py tests/test_toolchain.py tests/test_wsl.py
git commit -m "feat(bootstrap): end with the remaining manual steps for this OS"
```

---

### Task 7: Entry scripts: checkout or one-liner, uv, `uv run`

**Files:**
- Modify: `bootstrap.sh`, `bootstrap.ps1`
- Test: `tests/test_entry_scripts.py` (new, POSIX only, no network: stubs on PATH)

**Interfaces:**
- Produces: `bootstrap.sh [--dir PATH] [loadout bootstrap flags...]`; test-only environment variables `LOADOUT_REPO_URL`, `LOADOUT_REF`.

- [ ] **Step 1: Write the failing tests** (`tests/test_entry_scripts.py`)

```python
"""bootstrap.sh: checkout detection, one-liner clone, uv install and hand-off (stubs only, no network)."""
import os
import shutil
import subprocess

import pytest

from loadout import paths

pytestmark = pytest.mark.skipif(os.name == "nt", reason="bash entry script")
SCRIPT = paths.kit_root() / "bootstrap.sh"


@pytest.fixture
def env(tmp_path):
    stubs, home = tmp_path / "stubs", tmp_path / "home"
    stubs.mkdir()
    home.mkdir()
    log = tmp_path / "log"

    def stub(name, body):
        f = stubs / name
        f.write_text(f'#!/bin/sh\necho "{name} $* [UV_NO_MODIFY_PATH=$UV_NO_MODIFY_PATH] [pwd=$(pwd)]" >> "{log}"\n{body}\n')
        f.chmod(0o755)

    for tool in ("dirname", "uname", "grep", "cat", "mkdir", "cp", "chmod"):
        if shutil.which(tool):
            (stubs / tool).symlink_to(shutil.which(tool))
    return {"stubs": stubs, "home": home, "log": log, "stub": stub,
            "vars": {"HOME": str(home), "PATH": str(stubs)}}


def _run(env, args, cwd, stdin=None):
    return subprocess.run(["/bin/bash", *args], cwd=cwd, env=env["vars"], input=stdin,
                          capture_output=True, text=True, timeout=60)


def test_checkout_hands_off_to_uv_run_without_dir(env, tmp_path):
    env["stub"]("uv", "exit 0")
    kit = tmp_path / "kit"
    (kit / "bin").mkdir(parents=True)
    (kit / "bin/loadout").write_text("")
    shutil.copy(SCRIPT, kit / "bootstrap.sh")
    p = _run(env, [str(kit / "bootstrap.sh"), "--install", "--dir", "/ignored"], cwd=tmp_path)
    assert p.returncode == 0, p.stderr
    log = env["log"].read_text()
    assert "uv run --no-project --python >=3.10 bin/loadout bootstrap --install" in log
    assert f"pwd={kit}" in log and "--dir" not in log


def test_no_arguments_work_on_old_bash(env, tmp_path):
    env["stub"]("uv", "exit 0")
    kit = tmp_path / "kit"
    (kit / "bin").mkdir(parents=True)
    (kit / "bin/loadout").write_text("")
    shutil.copy(SCRIPT, kit / "bootstrap.sh")
    assert _run(env, [str(kit / "bootstrap.sh")], cwd=tmp_path).returncode == 0


def test_installs_uv_without_touching_profiles(env, tmp_path):
    uv = env["home"] / ".local/bin/uv"
    env["stub"]("curl", f'printf "mkdir -p {uv.parent}; printf \'#!/bin/sh\\\\nexit 0\\\\n\' > {uv}; chmod +x {uv}\\n"')
    env["stub"]("sh", 'exec /bin/sh "$@"')
    kit = tmp_path / "kit"
    (kit / "bin").mkdir(parents=True)
    (kit / "bin/loadout").write_text("")
    shutil.copy(SCRIPT, kit / "bootstrap.sh")
    p = _run(env, [str(kit / "bootstrap.sh")], cwd=tmp_path)
    assert p.returncode == 0, p.stderr
    assert "curl -LsSf https://astral.sh/uv/install.sh" in env["log"].read_text()
    assert "[UV_NO_MODIFY_PATH=1]" in env["log"].read_text()
    assert uv.exists()


def test_one_liner_clones_into_cwd(env, tmp_path):
    fake_kit = tmp_path / "upstream"
    (fake_kit / "bin").mkdir(parents=True)
    (fake_kit / "bin/loadout").write_text("")
    env["stub"]("git", f'case "$1" in clone) cp -r "{fake_kit}" "$3";; esac; exit 0')
    env["stub"]("uv", "exit 0")
    work = tmp_path / "work"
    work.mkdir()
    p = _run(env, ["-s", "--", "--install"], cwd=work, stdin=SCRIPT.read_text())
    assert p.returncode == 0, p.stderr
    assert (work / "agent-loadout/bin/loadout").exists()
    assert f"pwd={work / 'agent-loadout'}" in env["log"].read_text()
    assert "--install" in env["log"].read_text()


def test_one_liner_without_git_explains_and_stops(env, tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    p = _run(env, ["-s"], cwd=work, stdin=SCRIPT.read_text())
    assert p.returncode == 1
    assert "git" in p.stderr and ("apt install git" in p.stderr or "xcode-select" in p.stderr)


def test_one_liner_refuses_foreign_target(env, tmp_path):
    env["stub"]("git", 'case "$*" in *"remote get-url origin"*) echo https://example.com/other.git;; esac; exit 0')
    work = tmp_path / "work"
    (work / "agent-loadout").mkdir(parents=True)
    p = _run(env, ["-s"], cwd=work, stdin=SCRIPT.read_text())
    assert p.returncode == 1 and "agent-loadout" in p.stderr
```

- [ ] **Step 2: Run, expect FAIL**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_entry_scripts.py`

- [ ] **Step 3: Rewrite `bootstrap.sh`**

```bash
#!/usr/bin/env bash
# Set up loadout on this machine. All logic lives in `loadout bootstrap`.
# From a clone:  ./bootstrap.sh --install
# Without one:   curl -fsSL https://raw.githubusercontent.com/jonasyr/agent-loadout/main/bootstrap.sh | bash -s -- --install
# Nothing here uses sudo. --dir PATH picks where the one-liner clones (default: ./agent-loadout).
set -euo pipefail
repo_url="${LOADOUT_REPO_URL:-https://github.com/jonasyr/agent-loadout}"  # LOADOUT_REPO_URL/LOADOUT_REF: tests only
ref="${LOADOUT_REF:-main}"

dir=""
args=()
while [ $# -gt 0 ]; do
  case "$1" in
    --dir) dir="${2:?--dir needs a path}"; shift 2 ;;
    --dir=*) dir="${1#--dir=}"; shift ;;
    *) args+=("$1"); shift ;;
  esac
done

git_hint() {
  case "$(uname -s)" in
    Darwin) echo "xcode-select --install" ;;
    *) echo "sudo apt install git   (Debian/Ubuntu; other distros: their package manager)" ;;
  esac
}

src="${BASH_SOURCE[0]:-}"
if [ -n "$src" ] && [ -f "$(dirname "$src")/bin/loadout" ]; then
  kit="$(cd "$(dirname "$src")" && pwd)"
else
  if ! command -v git >/dev/null 2>&1; then
    echo "loadout needs git to download itself. Install it, then run this command again:" >&2
    echo "  $(git_hint)" >&2
    exit 1
  fi
  kit="${dir:-$PWD/agent-loadout}"
  if [ -e "$kit" ]; then
    origin="$(git -C "$kit" remote get-url origin 2>/dev/null || true)"
    case "$origin" in
      *jonasyr/agent-loadout*|"$repo_url") echo "using the existing clone in $kit" ;;
      *) echo "$kit exists and is not a clone of agent-loadout; choose another folder with --dir PATH" >&2; exit 1 ;;
    esac
  else
    echo "cloning agent-loadout into $kit"
    git clone -q "$repo_url" "$kit"
    git -C "$kit" checkout -q "$ref"
  fi
fi

export PATH="$HOME/.local/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then
  echo "installing uv (it also provides Python for loadout)"
  curl -LsSf https://astral.sh/uv/install.sh | UV_NO_MODIFY_PATH=1 sh
fi

cd "$kit"
run=(uv run --no-project --python ">=3.10" bin/loadout bootstrap ${args[@]+"${args[@]}"})
if [ ! -t 0 ] && { : </dev/tty; } 2>/dev/null; then
  exec "${run[@]}" </dev/tty  # one-liner: stdin is the script pipe, so ask on the terminal
fi
exec "${run[@]}"
```

Note for the test stubs: `curl … | UV_NO_MODIFY_PATH=1 sh` sets the variable for `sh`, not for `curl`; the stub records the variable when `sh` runs it, which is why the test stubs `sh` too. If the recorded line does not show it, export `UV_NO_MODIFY_PATH=1` before the pipe instead and keep the test.

- [ ] **Step 4: Rewrite `bootstrap.ps1`**

```powershell
# Set up loadout on this machine (native Windows, experimental). All logic lives in `loadout bootstrap`.
# From a clone:  powershell -NoProfile -ExecutionPolicy Bypass -File .\bootstrap.ps1 --install
# Without one:   & ([scriptblock]::Create((irm https://raw.githubusercontent.com/jonasyr/agent-loadout/main/bootstrap.ps1))) --install
$ErrorActionPreference = 'Stop'
Write-Warning 'Native Windows is experimental and not recommended. WSL 2 is the recommended setup on Windows: docs/how-to/wsl.md'
$repoUrl = if ($env:LOADOUT_REPO_URL) { $env:LOADOUT_REPO_URL } else { 'https://github.com/jonasyr/agent-loadout' }
$ref = if ($env:LOADOUT_REF) { $env:LOADOUT_REF } else { 'main' }
$dir = $null; $rest = @()
for ($i = 0; $i -lt $args.Count; $i++) {
  if ($args[$i] -eq '--dir') { $dir = $args[$i + 1]; $i++ }
  elseif ($args[$i] -like '--dir=*') { $dir = $args[$i].Substring(6) }
  else { $rest += $args[$i] }
}
if ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot 'bin/loadout'))) {
  $kit = $PSScriptRoot
} else {
  if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Error 'loadout needs git to download itself. Install it, then run this command again: winget install --id Git.Git -e'
    exit 1
  }
  $kit = if ($dir) { $dir } else { Join-Path (Get-Location) 'agent-loadout' }
  if (Test-Path $kit) {
    $origin = git -C $kit remote get-url origin 2>$null
    if ($origin -notmatch 'jonasyr/agent-loadout' -and $origin -ne $repoUrl) {
      Write-Error "$kit exists and is not a clone of agent-loadout; choose another folder with --dir PATH"
      exit 1
    }
    Write-Host "using the existing clone in $kit"
  } else {
    Write-Host "cloning agent-loadout into $kit"
    git clone -q $repoUrl $kit
    git -C $kit checkout -q $ref
  }
}
if (-not (Get-Command bash -ErrorAction SilentlyContinue)) {
  Write-Warning 'Git Bash not found: Claude Code hooks need Git for Windows.'
}
$env:Path = "$HOME\.local\bin;$env:Path"
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Write-Host 'installing uv (it also provides Python for loadout)'
  $env:UV_NO_MODIFY_PATH = '1'
  Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
}
Set-Location $kit
uv run --no-project --python '>=3.10' bin/loadout bootstrap @rest
exit $LASTEXITCODE
```

- [ ] **Step 5: Run the file and the full suite, expect PASS.** Also check the PowerShell file parses if `pwsh` is installed locally: `pwsh -NoProfile -Command "[System.Management.Automation.Language.Parser]::ParseFile('bootstrap.ps1',[ref]$null,[ref]$null) | Out-Null"` (skip if `pwsh` is missing; the Windows CI jobs run it).

- [ ] **Step 6: Commit**

```bash
git add bootstrap.sh bootstrap.ps1 tests/test_entry_scripts.py
git commit -m "feat: bootstrap from a clone or as a one-liner, with Python provided by uv"
```

---

### Task 8: Fresh-machine CI

**Files:**
- Create: `.github/workflows/fresh-machine.yml`
- Modify: `.github/workflows/ci.yml` only if the existing Windows hook step still calls `python3` hooks directly

- [ ] **Step 1: Write the workflow**

```yaml
name: fresh-machine
on:
  pull_request:
    paths: ["bootstrap.sh", "bootstrap.ps1", "catalog.json", "cli/loadout/bootstrap.py", "cli/loadout/link.py",
            "cli/loadout/paths.py", "plugins/loadout/hooks/run.sh", ".github/workflows/fresh-machine.yml"]
  schedule:
    - cron: "17 4 * * 1"
  workflow_dispatch:

permissions:
  contents: read

jobs:
  linux:
    name: fresh-machine (linux)
    runs-on: ubuntu-latest
    container: ubuntu:24.04
    env:
      REPO_URL: https://github.com/${{ github.repository }}
      REF: ${{ github.head_ref || github.ref_name }}
    steps:
      - run: apt-get update && apt-get install -y --no-install-recommends git curl ca-certificates
      - uses: actions/checkout@v4
      - name: users with empty homes
        run: |
          useradd -m -s /bin/bash fromclone
          useradd -m -s /bin/bash oneliner
          cp -r "$GITHUB_WORKSPACE" /home/fromclone/agent-loadout
          chown -R fromclone: /home/fromclone/agent-loadout
          cp "$GITHUB_WORKSPACE/bootstrap.sh" /tmp/bootstrap.sh && chmod 644 /tmp/bootstrap.sh
      - name: bootstrap from a clone
        run: su - fromclone -c 'cd ~/agent-loadout && bash bootstrap.sh --install --yes --no-plugins'
      - name: a new login shell finds everything, check has no FAIL
        run: |
          su - fromclone -c 'claude --version && serena --version && codebase-memory-mcp --version && node --version && loadout --help >/dev/null'
          out="$(su - fromclone -c 'loadout check' || true)"; printf '%s\n' "$out"
          ! printf '%s\n' "$out" | grep -F '[FAIL]'
      - name: one-liner without a clone
        run: su - oneliner -c "mkdir -p work && cd work && LOADOUT_REPO_URL=$REPO_URL LOADOUT_REF=$REF bash -s -- --install --yes --no-plugins < /tmp/bootstrap.sh"
      - name: one-liner result
        run: |
          su - oneliner -c 'test -f ~/work/agent-loadout/bin/loadout && claude --version && serena --version'
          out="$(su - oneliner -c 'loadout check' || true)"; printf '%s\n' "$out"
          ! printf '%s\n' "$out" | grep -F '[FAIL]'

  windows:
    name: fresh-machine (windows, experimental)
    runs-on: windows-latest
    continue-on-error: true
    steps:
      - uses: actions/checkout@v4
      - name: bootstrap with Python, Node and gh hidden
        shell: pwsh
        run: |
          $env:Path = "C:\Windows\System32;C:\Windows;C:\Windows\System32\WindowsPowerShell\v1.0;C:\Program Files\Git\cmd;C:\Program Files\Git\bin;$env:LOCALAPPDATA\Microsoft\WindowsApps"
          powershell -NoProfile -ExecutionPolicy Bypass -File .\bootstrap.ps1 --install --yes --no-plugins
          $env:Path = [Environment]::GetEnvironmentVariable('Path','User') + ';' + $env:Path
          $out = (loadout check) -join "`n"; Write-Output $out
          if ($out -match '\[FAIL\]') { exit 1 }
```

Notes: `WindowsApps` keeps `winget` reachable (if the runner has it); if winget is missing, mise's install fails and node/gh are reported missing: that is a real finding for the experimental path, not a reason to change the Linux job.

- [ ] **Step 2: Validate the YAML locally**

Run: `uv run -q --with pyyaml python -c "import yaml; yaml.safe_load(open('.github/workflows/fresh-machine.yml')); print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/fresh-machine.yml
git commit -m "ci: prove the one-command setup on fresh Linux and Windows machines"
```

- [ ] **Step 4: Run on GitHub (Inline; needs the user's OK to push).** Push, open the PR, watch `fresh-machine (linux)`. Fix failures test-first where a unit test can reproduce them; CI-only facts (installer behaviour) become Rulings in the ledger.

---

### Task 9: Docs and ADR 0020

**Files:**
- Modify: `README.md`, `docs/tutorials/getting-started.md`, `docs/reference/included-tools.md`, `docs/explanation/security-and-trust.md`, `docs/how-to/wsl.md`, `docs/how-to/troubleshooting.md`, `docs/how-to/uninstall.md` (remove the PATH block and the launcher), `AGENTS.md` (ADR range 0001-0020)
- Create: `docs/adr/0020-bootstrap-installs-the-toolchain-in-user-space.md`; modify `docs/adr/README.md`

- [ ] **Step 1: README Quick start** (replace the section's opening and the two code blocks):

````markdown
## Quick start

**Linux, macOS and WSL 2** (WSL 2 is the recommended setup on Windows):

```bash
curl -fsSL https://raw.githubusercontent.com/jonasyr/agent-loadout/main/bootstrap.sh | bash -s -- --install
```

This clones the kit into `./agent-loadout` and installs everything that is missing, in your home folder, without sudo: uv (which also provides Python), Claude Code, Node.js, gh and every tool in [the toolset](#the-toolset). Prefer to read the code first? Clone it and run the same script:

```bash
git clone https://github.com/jonasyr/agent-loadout && cd agent-loadout && ./bootstrap.sh --install
```

**Before you start:** you need git; after bootstrap you log in to Claude Code and gh. The one line per OS is in [Before you start](docs/tutorials/getting-started.md#before-you-start), and bootstrap ends with the steps still open on your machine.

<details>
<summary>Experimental: native Windows (not recommended; use WSL 2)</summary>

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/jonasyr/agent-loadout/main/bootstrap.ps1))) --install
```

Git for Windows is required (Git Bash runs the hooks). Details: [Native Windows](docs/tutorials/getting-started.md#experimental-native-windows).
</details>
````

Keep the rest of Quick start (what bootstrap asks, `loadout check`, `loadout init`) but drop the old requirements sentence and the `Set-ExecutionPolicy` paragraph (move it into the tutorial's Windows section). Badge: `Platforms: Linux, macOS, Windows (WSL 2)` (URL-encode as today).

- [ ] **Step 2: Tutorial** `docs/tutorials/getting-started.md` owns the "Before you start" table (one home; the README links to it). Replace its requirements section with `## Before you start` holding this table and the sandbox line:

| | Linux / WSL | macOS | Windows (experimental) |
|---|---|---|---|
| git | `sudo apt install git` (Debian/Ubuntu; other distros: their package manager) | `xcode-select --install` | `winget install --id Git.Git -e` (Git Bash runs the hooks) |
| After bootstrap | `claude` (log in), `gh auth login` | same | same |

"Optional, only if you turn on Claude Code's sandbox (Linux, WSL 2): `sudo apt-get install bubblewrap socat`." Step 1 shows the one-liner first and the clone alternative below it. The native Windows section becomes `## Experimental: native Windows`, starts with the warning sentence from Global Constraints, shows the PowerShell one-liner and keeps the execution-policy notes. Fix every link to the old anchors (`#requirements`, `#native-windows`): `grep -rn "getting-started.md#" README.md docs`.

- [ ] **Step 3: Reference and explanation pages**
  - `included-tools.md`: Command-line tools table: `mise` row (helper: installs Node.js, gh and rust-analyzer when missing); the sentence about requirements: "Python is provided by uv; git is the only prerequisite ([Before you start](../tutorials/getting-started.md#before-you-start))".
  - `security-and-trust.md`, "What runs when you ask": add the one-liner (you trust this repo's `main`), uv's installer, Claude Code's installer (Anthropic), mise's installer and `mise use -g` (mise and the tools' upstreams); "to avoid them: run bootstrap without `--install`, or clone and read the code first".
  - `wsl.md`: step 6 says the sandbox packages are optional and needed only for Claude Code's sandbox; "open a new terminal" after bootstrap.
  - `troubleshooting.md`: rows "`loadout`/`claude` not found right after bootstrap → open a new terminal (bootstrap added `~/.local/bin` and the mise shims to your profile, block `# loadout PATH`)"; "`missing node: skipped: needs mise` → mise failed to install, see the line above it".
  - `uninstall.md`: remove the `# loadout PATH` block from your shell profiles (Windows: the folders from your user PATH), and `~/.local/bin/loadout`.

- [ ] **Step 4: ADR 0020**

```markdown
# 0020. Bootstrap installs the toolchain in user space

- Status: Accepted
- Date: 2026-10-11
- Source: [One-command setup design](../superpowers/specs/2026-10-11-one-command-setup-design.md)

## Context
A fresh machine needed Python, Node.js, gh and Claude Code before bootstrap could run, and tools installed during bootstrap were not on its PATH. Setup took several manual steps per OS and failed in confusing ways.

## Decision
Bootstrap installs every missing tool it can without sudo or administrator rights: uv first (it provides Python for loadout), then Claude Code with Anthropic's native installer, mise for Node.js, gh and rust-analyzer, then the npm-based tools. It installs only what is missing and never replaces a tool already on PATH. It adds the user-space tool folders to its own PATH while it runs and to the shell profile (block `# loadout PATH`). The `loadout` launcher and the plugin's Python hooks fall back to uv when there is no Python 3.10+. git and logging in stay manual and are listed per OS.

## Alternatives considered
- The system package manager (apt, brew, winget machine scope): needs sudo or administrator rights and differs per distribution.
- mise for everything, including Python and uv: makes mise mandatory even for users who do not want it.
- Keep the prerequisites manual: the main source of failed setups.

## Consequences
- More upstream installers run with `--install` (uv, Claude Code, mise); they are listed in [Security and trust](../explanation/security-and-trust.md).
- A fresh-machine CI workflow runs the real installers on throwaway machines.
- Native Windows remains experimental.
```

Index row in `docs/adr/README.md`. `AGENTS.md`: `decisions 0001-0020`.

- [ ] **Step 5: Run the suite (static link/anchor checks), commit**

```bash
git add README.md docs AGENTS.md
git commit -m "docs: one-command setup, before-you-start steps, native Windows experimental (ADR 0020)"
```

---

### Task 10: Agent notes

- [ ] **Step 1:** Update `.serena/memories/windows-and-wsl.md` (native Windows experimental) and add one line to `.serena/memories/architecture.md` or `testing-gotchas.md`: real installers run only in `.github/workflows/fresh-machine.yml`; entry-script tests use stubs on PATH.
- [ ] **Step 2:** Full suite; commit `docs(memories): one-command setup notes`.
- [ ] **Step 3 (after the final review):** `/loadout:docs-sync`, re-index codebase-memory.
