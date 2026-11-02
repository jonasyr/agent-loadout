# Install readiness fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the confirmed findings of the 2026-11-02 install-readiness review that a friend would hit on a first install.

**Architecture:** Small, independent changes in `cli/loadout/bootstrap.py` (PATH for fish, the agent question's default, install-failure fix lines, "Still to do" logins), in `bootstrap.ps1` (Git Bash probe) and `bootstrap.sh` (git that cannot run), plus docs. No new modules.

**Tech Stack:** Python 3.11+ standard library, bash, PowerShell; pytest with `fake_home` / `fake_runner`.

**Spec:** `.superpowers/handoff/2026-11-02-install-readiness.md` (local, gitignored; findings 1, 2, 3, 5, 6, 7, 13, 17). The user approved this list on 2026-11-02. Not in scope: the undo line's `--list` (user decided to keep it, backlog), macOS CI (separate PR), stale clone re-use, `loadout uninstall`, Cursor/Insiders detection, zsh `.zprofile`.

## Global Constraints

- Standard library only in `cli/loadout/`; external commands only through `runner.run` with argument lists.
- Tests use `fake_home` and `fake_runner`; never the real home, never real `claude`/`codex`.
- A new or changed user file is recorded in the backup (`_add_block` already does: `record_created` or appends without re-encoding).
- Conventional Commits, no AI attribution.
- Output lines follow the existing `fix: …, then run this again` form (`LIBATOMIC_FIX`).

## Review Focus

1. A fish user who also has `.bashrc`: both get a block; a second run changes nothing (idempotent).
2. A fish config folder that exists although `$SHELL` is bash: the fish block is still written (the person may switch shells), never an error.
3. `codex login status` on a Codex that predates the subcommand (non-zero for another reason): the line says "log in", which is harmless; it must never crash or hang (timeout).
4. The Codex extension found only on the Windows side in WSL: still "seen" (worth asking), as a Windows `codex.exe` already is.
5. npm failing for a reason other than EACCES / missing npm: no fix line, only the existing tail.

---

### Task 1: PATH for fish

**Files:**
- Modify: `cli/loadout/bootstrap.py` (`setup_path`, new `_fish_path_block`)
- Test: `tests/test_toolchain.py`

**Interfaces:**
- Produces: `_fish_path_block(dirs: list[Path]) -> str` (starts with `PATH_MARKER`, ends with `PATH_END`).

- [ ] **Step 1: Write the failing tests** (next to `test_path_block_goes_to_rc_and_login_profile`)

```python
def test_fish_gets_its_own_path_file(fake_home, fake_runner, monkeypatch):
    _posix(monkeypatch)
    monkeypatch.setenv("SHELL", "/usr/bin/fish")
    (fake_home / ".local/bin").mkdir(parents=True)
    out, changed = b.setup_path(None)
    fish = fake_home / ".config/fish/conf.d/loadout.fish"
    text = fish.read_text()
    assert changed and str(fish) in "\n".join(out)
    assert text.startswith(b.PATH_MARKER + "\n") and b.PATH_END in text
    assert 'set -gx PATH "$HOME/.local/bin" $PATH' in text and "contains --" in text
    assert b.setup_path(None) == ([], False)


def test_an_existing_fish_config_gets_the_block_too(fake_home, fake_runner, monkeypatch):
    _posix(monkeypatch)
    monkeypatch.setenv("SHELL", "/bin/bash")
    (fake_home / ".local/bin").mkdir(parents=True)
    (fake_home / ".config/fish").mkdir(parents=True)
    b.setup_path(None)
    assert (fake_home / ".config/fish/conf.d/loadout.fish").is_file()
    assert b.PATH_MARKER in (fake_home / ".bashrc").read_text()


def test_no_fish_no_fish_file(fake_home, fake_runner, monkeypatch):
    _posix(monkeypatch)
    monkeypatch.setenv("SHELL", "/bin/bash")
    (fake_home / ".local/bin").mkdir(parents=True)
    b.setup_path(None)
    assert not (fake_home / ".config/fish").exists()
```

- [ ] **Step 2: Run** `uv run --python 3.12 --with pytest pytest -q tests/test_toolchain.py -k fish` — Expected: 2 FAIL (no fish file), `test_no_fish_no_fish_file` passes.

- [ ] **Step 3: Implement.** `_fish_path_block` mirrors `_path_block`: per folder, reversed, `contains -- "$HOME/{rel}" $PATH; or set -gx PATH "$HOME/{rel}" $PATH`. In `setup_path` (POSIX branch), when `shell == "fish"` or `~/.config/fish` is a directory, also handle `~/.config/fish/conf.d/loadout.fish` with the fish block, through the same `_refresh_path_block` / `_add_block` loop (pairs of (file, block)). `_add_block` creates the parent folder and records the created file.

- [ ] **Step 4: Run** the same command plus `-k path_block` — Expected: all PASS.

- [ ] **Step 5: Commit** `fix(bootstrap): add the tool folders to PATH for fish too`

### Task 2: The Codex extension counts at the agent question

**Files:**
- Modify: `cli/loadout/bootstrap.py` (`_codex_seen`)
- Test: `tests/test_wsl_codex_bootstrap.py`

- [ ] **Step 1: Write the failing test**

```python
def test_the_codex_extension_alone_makes_both_the_default(codex_ext, fake_runner):
    fake_runner.missing.add("codex")
    bootstrap.paths.personal_root().mkdir(parents=True)  # an existing layer: asked only when Codex is seen
    asked = []
    choice, store = bootstrap._choose_agents(lambda q: asked.append(q) or "", interactive=True, flag=None)
    assert asked and "[3]" in asked[0]
    assert choice == {"claude": True, "codex": True} and store
```

(Check `codex_ext` in `tests/conftest.py:188` puts the extension in `fake_home`; add `fake_runner.missing.add("codex")` only if the fixture does not.)

- [ ] **Step 2: Run** `... pytest -q tests/test_wsl_codex_bootstrap.py -k extension_alone` — Expected: FAIL (not asked).

- [ ] **Step 3: Implement.** `_codex_seen()` also returns True when `vscode.extensions({"codex": True}, look=False)` is non-empty (any side; no version check: the question only needs to know Codex is used). Update the docstring.

- [ ] **Step 4: Run** `... pytest -q tests/test_wsl_codex_bootstrap.py tests/test_codex_extension_mode.py` — Expected: PASS.

- [ ] **Step 5: Commit** `fix(bootstrap): VS Code's Codex extension makes "both" the default agent answer`

### Task 3: Fix lines for npm failures

**Files:**
- Modify: `cli/loadout/bootstrap.py` (`install_tool`, new constants next to `LIBATOMIC_FIX`)
- Test: `tests/test_apply_steps.py`

**Interfaces:**
- Produces: `NPM_PREFIX_FIX: str` (format field `name`), `NPM_MISSING_FIX: str` (format field `name`).

- [ ] **Step 1: Write the failing tests** (next to `test_a_missing_libatomic_names_the_package`; `_bin` helper exists there)

```python
def test_npm_eacces_names_the_prefix_fix(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(b.paths, "platform_key", lambda: "linux")
    fake_runner.missing.add("playwright-cli")
    fake_runner.responses[("npm",)] = runner.Result(
        243, "", "npm error code EACCES\nnpm error syscall mkdir\nnpm error path /usr/lib/node_modules/@playwright")
    _, lines = b.install_tool(_bin("playwright-cli"), [["npm", "install", "-g", "@playwright/cli@latest"]])
    assert any(l.startswith("fix: ") and "npm config set prefix ~/.local" in l for l in lines)


def test_missing_npm_says_install_npm(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(b.paths, "platform_key", lambda: "linux")
    fake_runner.missing.update({"playwright-cli", "npm"})
    _, lines = b.install_tool(_bin("playwright-cli"), [["npm", "install", "-g", "@playwright/cli@latest"]])
    assert any(l.startswith("fix: ") and "npm" in l and "sudo apt install npm" in l for l in lines)


def test_other_npm_failures_get_no_fix_line(fake_home, fake_runner):
    fake_runner.missing.add("playwright-cli")
    fake_runner.responses[("npm",)] = runner.Result(1, "", "npm error code ETIMEDOUT")
    _, lines = b.install_tool(_bin("playwright-cli"), [["npm", "install", "-g", "@playwright/cli@latest"]])
    assert not any(l.startswith("fix: ") for l in lines)
```

(Confirm how `fake_runner` answers a missing program: `runner.run` returns `Result(127, "", "npm: not found")` at `runner.py:228`.)

- [ ] **Step 2: Run** `... pytest -q tests/test_apply_steps.py -k npm` — Expected: first two FAIL.

- [ ] **Step 3: Implement.** In the failure branch, when `cmd[0] == "npm"` and the platform is not Windows: `"EACCES" in` output → `NPM_PREFIX_FIX` ("fix: npm cannot write its global folder (a system Node's npm): npm config set prefix ~/.local, then run this again"); return code 127 → `NPM_MISSING_FIX` ("fix: {name} needs npm, which this Node came without: sudo apt install npm (Fedora: sudo dnf install npm; Arch: sudo pacman -S npm), then run this again"). Keep `filter(None, found)`.

- [ ] **Step 4: Run** `... pytest -q tests/test_apply_steps.py` — Expected: PASS.

- [ ] **Step 5: Commit** `fix(bootstrap): name the fix when npm cannot install a tool`

### Task 4: Logins in "Still to do"

**Files:**
- Modify: `cli/loadout/bootstrap.py` (`still_to_do`)
- Test: `tests/test_toolchain.py`

**Interfaces:**
- Produces: `CODEX_LOGIN = "log in to Codex: codex login"`, `CODEX_LOGIN_EXTENSION = "sign in to Codex in VS Code's Codex extension (it asks when you open it)"`, `CLAUDE_LOGIN_EXTENSION = "sign in to Claude Code in VS Code's Claude Code extension (it asks when you open it)"`.

- [ ] **Step 1: Write the failing tests**

```python
def test_still_to_do_names_codex_login(fake_home, fake_runner, monkeypatch):
    from loadout import codex
    monkeypatch.setattr(codex, "open_steps", lambda plugins=True: [])
    monkeypatch.setattr(codex, "enabled", lambda: True)
    fake_runner.responses[("codex", "login", "status")] = runner.Result(1, "", "Not logged in")
    assert b.CODEX_LOGIN in b.still_to_do("linux")


def test_still_to_do_quiet_when_codex_is_logged_in(fake_home, fake_runner, monkeypatch):
    from loadout import codex
    monkeypatch.setattr(codex, "open_steps", lambda plugins=True: [])
    monkeypatch.setattr(codex, "enabled", lambda: True)
    fake_runner.responses[("codex", "login", "status")] = runner.Result(0, "", "Logged in using ChatGPT")
    assert not any("Codex" in l and "log in" in l for l in b.still_to_do("linux"))


def test_still_to_do_codex_extension_login(codex_ext, fake_runner, monkeypatch):
    from loadout import codex
    monkeypatch.setattr(codex, "open_steps", lambda plugins=True: [])
    monkeypatch.setattr(codex, "enabled", lambda: True)
    fake_runner.missing.add("codex")
    fake_runner.responses[(str(codex_ext), "login", "status")] = runner.Result(1, "", "Not logged in")
    assert b.CODEX_LOGIN_EXTENSION in b.still_to_do("linux")


def test_still_to_do_claude_extension_login(fake_home, fake_runner, monkeypatch):
    from loadout import vscode
    fake_runner.missing.add("claude")
    monkeypatch.setattr(vscode, "bundled_claude", lambda: "/x/claude")
    assert b.CLAUDE_LOGIN_EXTENSION in b.still_to_do("linux")


def test_codex_off_no_codex_login(fake_home, fake_runner, monkeypatch):
    from loadout import codex
    monkeypatch.setattr(codex, "enabled", lambda: False)
    assert not any("Codex" in l and "log in" in l for l in b.still_to_do("linux"))
    assert ("codex", "login", "status") not in map(tuple, fake_runner.calls)
```

- [ ] **Step 2: Run** `... pytest -q tests/test_toolchain.py -k "still_to_do or login"` — Expected: the 3 positive tests FAIL.

- [ ] **Step 3: Implement.** In `still_to_do`, only when `codex_here`: if `codex.enabled() and codex.has_codex()`, run `[codex.program(), "login", "status"]` (timeout 20); not ok → `CODEX_LOGIN` when `codex.mode() != "extension"`, else `CODEX_LOGIN_EXTENSION`. Claude: keep the CLI line; add `elif targets.claude_enabled() and not runner.have("claude") and vscode.bundled_claude() is not None and not _claude_logged_in()` → `CLAUDE_LOGIN_EXTENSION`. Place the Codex login before `codex.open_steps` lines.

- [ ] **Step 4: Run** `... pytest -q tests/test_toolchain.py tests/test_codex_open_points.py tests/test_personal_repo.py tests/test_codex_extension_mode.py` — Expected: PASS (fix older tests only if they assert an exact list; any change gets a Ruling).

- [ ] **Step 5: Commit** `fix(bootstrap): Still to do names the Codex login and the extensions' sign-in`

### Task 5: Install scripts: Git Bash probe and a git that cannot run

**Files:**
- Modify: `bootstrap.ps1:64-66`, `bootstrap.sh:64-68`
- Test: `tests/test_fix_pass_a.py` (text tests, as the existing ps1 tests)

- [ ] **Step 1: Write the failing tests**

```python
def test_ps1_finds_git_bash_next_to_git_not_wsl_bash():
    text = PS1.read_text()
    assert "Get-Command bash" not in text
    assert "bin\\bash.exe" in text and "CLAUDE_CODE_GIT_BASH_PATH" in text


def test_sh_stops_when_git_cannot_run():
    text = (PS1.parent / "bootstrap.sh").read_text()
    assert "git --version >/dev/null 2>&1" in text
```

- [ ] **Step 2: Run** `... pytest -q tests/test_fix_pass_a.py` — Expected: 2 FAIL.

- [ ] **Step 3: Implement.**
  - `bootstrap.ps1`: Git Bash is found when `$env:CLAUDE_CODE_GIT_BASH_PATH` points to a file, or `bin\bash.exe` exists two folders up from `(Get-Command git).Source` (`Git\cmd\git.exe` → `Git\bin\bash.exe`), or `$env:ProgramFiles\Git\bin\bash.exe` exists. Otherwise the same warning. Never `System32\bash.exe`.
  - `bootstrap.sh`: the git check becomes `if ! command -v git >/dev/null 2>&1 || ! git --version >/dev/null 2>&1; then` (a macOS `/usr/bin/git` without Command Line Tools fails `--version`), same message with `git_hint`.

- [ ] **Step 4: Run** `... pytest -q tests/test_fix_pass_a.py` and `bash -n bootstrap.sh` — Expected: PASS, no syntax error.

- [ ] **Step 5: Commit** `fix(install): find Git Bash next to git; stop early when git cannot run`

### Task 6: Docs

**Files:**
- Modify: `docs/tutorials/getting-started.md:3` (link to `../how-to/setups.md`), `README.md` step 2 "In VS Code" line (extension-only: sign in from the extension), `docs/how-to/troubleshooting.md` (rows: fish PATH now written to `conf.d/loadout.fish`; "Git Bash not found" on Windows; macOS "offline?" now "needs git" with `xcode-select --install`), `docs/how-to/vscode.md` (sign in inside the extension when there is no CLI), `docs/reference/cli.md` if it describes the PATH files.
- Test: `uv run --python 3.12 --with pytest pytest -q tests/test_docs_commands.py` and the docs link tests.

- [ ] **Step 1:** Make the edits; each fact in one place, others link.
- [ ] **Step 2: Run** the docs tests — Expected: PASS.
- [ ] **Step 3: Commit** `docs: fish PATH, extension sign-in, Git Bash and git-without-CLT rows`

### Final

- Full suite: `uv run --python 3.12 --with pytest pytest -q` — Expected: all pass.
- Whole-branch review (top tier), then `loadout:docs-sync`, then PR.
