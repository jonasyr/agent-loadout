# Hardening 1: security and the Python 3.11 floor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the confirmed findings of the security audit and raise the minimum Python to 3.11.

**Architecture:** Small, local fixes at the places the audit named. Two shared helpers: `runner.which` resolves programs without the current folder, and `paths.inside(path, root)` replaces the private `codex_project._inside`. Restore trusts only manifests under `paths.backups_root()` and replays only the undo commands loadout records.

**Tech Stack:** Python 3.11+ standard library, pytest with `fake_home` / `fake_runner` (and the autouse `never_the_real_home`).

**Spec:** the design approved in conversation on 2026-10-13. Findings are in `.superpowers/handoff/2026-10-13-hardening-backlog.md` ("Security audit"), and the decision for the floor is ADR 0023 (written in Task 1).

## Global Constraints

- Standard library only in `cli/loadout/`; Python 3.11+ after Task 1.
- Tests never touch the real `~/.claude`, `~/.claude.json`, `~/.codex`, `~/.config/loadout`; never run real `claude`/`codex`/installers.
- Conventional Commits; no AI attribution.
- On Linux and macOS, program lookup behaves exactly as before (Task 2 changes Windows only, plus refusing a result inside the current folder).
- Run tests with: `uv run --python 3.12 --with pytest pytest -q`.

## Review Focus

1. A Windows `which` that returns `.\git.exe` from the project folder must never be executed, including by the type-check hook, which does not import loadout (Task 2 tests).
2. A repo whose `.claude`, `.mcp.json`, `AGENTS.md`, `docs/` or `.gitignore` is a symlink, dangling or not, pointing outside it: `init`/`profile` write nothing outside it and say which file they skipped (Task 3).
3. Restore of a real backup still works end to end (move, restore-file, created, the recorded `claude` and `codex` undo commands, a restore of a pre-restore backup). Only foreign manifests and shapes are refused (Task 4).
4. Existing kit profile names (`android`, `db`, `sonar`, `thesis`, `web`) and the personal profiles the user created through adopt (`PROFILE_NAME`) still load (Task 5).
5. Python 3.10 users get a clear message from `bin/loadout`, and the launcher or hooks fall back to uv's Python (Task 1).

---

### Task 1: Python 3.11 minimum

**Files:** `bin/loadout`, `cli/loadout/link.py` (`PY_OK`, `UV_FIND`, `UV_INSTALL`, launcher texts), `plugins/loadout/hooks/run.sh`, `bootstrap.sh`, `bootstrap.ps1`, `pyproject.toml`, `cli/loadout/codex.py` / `codex_project.py` / `own.py` (all `_tomllib() is None` branches), the tests that skip on 3.10 or patch `_tomllib` to `None`, `docs/how-to/troubleshooting.md`, `docs/reference/hooks.md`, `docs/reference/cli.md`, `docs/explanation/security-and-trust.md`, `docs/adr/0020-…` (no edit; ADRs are immutable), new `docs/adr/0023-python-3-11-minimum.md`, `AGENTS.md` ("Python 3.10+" → 3.11+, ADR range 0001-0023).

- [ ] Step 1: Failing test `tests/test_python_floor.py`:

```python
"""loadout needs Python 3.11 or newer everywhere it checks."""
import re

from loadout import link, paths

KIT = paths.kit_root()


def test_every_version_check_says_3_11():
    files = ["bin/loadout", "plugins/loadout/hooks/run.sh", "bootstrap.sh", "bootstrap.ps1", "pyproject.toml"]
    for rel in files:
        text = (KIT / rel).read_text(encoding="utf-8")
        assert "3.10" not in text and "(3, 10)" not in text, rel
    assert "(3, 11)" in link.PY_OK and ">=3.11" in link.UV_FIND and ">=3.11" in link.UV_INSTALL


def test_bin_loadout_refuses_3_10(capsys):
    import importlib.util
    spec = importlib.util.spec_from_file_location("binloadout", KIT / "bin/loadout")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    try:
        mod.require_python((3, 10, 0))
    except SystemExit as exc:
        assert exc.code == 1
    assert "3.11 or newer" in capsys.readouterr().err


def test_no_code_path_for_a_missing_tomllib():
    for rel in ("cli/loadout/codex.py", "cli/loadout/codex_project.py", "cli/loadout/own.py"):
        assert not re.search(r"_tomllib\(\) is None|needs Python 3\.11", (KIT / rel).read_text(encoding="utf-8")), rel
```

- [ ] Step 2: Run, expect FAIL.
- [ ] Step 3: Implement. Replace every `3.10`/`(3, 10)`/`>=3.10` in the version checks and messages with 3.11. In `codex.py`, `_tomllib()` becomes `import tomllib; return tomllib`, and every `if tl is None` / `_tomllib() is None` branch is deleted with its message. The same goes for `codex_project.py` (`config`, `plugins`, `_trusted`) and `own.py` (`_global_mcp`). Delete the tests that patch `_tomllib` to `None`, and every `needs_tomllib` marker and definition.
- [ ] Step 4: Write ADR 0023 (Nygard format). Context: ADR 0020's uv fallback exists, Ubuntu 22.04 ships 3.10, and the 3.10 branches cost three review findings. Decision: "We will require Python 3.11." Consequences: one uv-managed Python download on 3.10-only machines, no TOML special cases. Update the docs lines that name 3.10.
- [ ] Step 5: Full suite green; commit `feat!: require Python 3.11 (ADR 0023)`, with a `BREAKING CHANGE:` footer naming the uv fallback.

### Task 2: Never run a program from the current folder

**Files:** `cli/loadout/runner.py` (`which`, `have`, `run`, `would_refuse`), `cli/loadout/maintenance.py` (`_spawn_background`), `plugins/loadout/hooks/typecheck.py`, tests `tests/test_safe_which.py`.

- [ ] Step 1: Failing tests:

```python
"""Programs are never taken from the current folder (Windows searches it first)."""
import os

from loadout import maintenance, runner


def test_which_drops_a_result_in_the_current_folder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner.shutil, "which", lambda name, path=None: str(tmp_path / "git.exe"))
    assert runner.which("git") is None
    assert runner.have("git") is False


def test_which_keeps_a_result_elsewhere(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner.shutil, "which", lambda name, path=None: "/usr/bin/git")
    assert runner.which("git") == "/usr/bin/git"


def test_windows_lookup_skips_the_current_folder(monkeypatch):
    monkeypatch.setattr(runner, "_is_windows", lambda: True)
    monkeypatch.delenv("NoDefaultCurrentDirectoryInExePath", raising=False)
    runner.which("git")
    assert os.environ.get("NoDefaultCurrentDirectoryInExePath") == "1"


def test_run_refuses_a_program_in_the_current_folder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner.shutil, "which", lambda name, path=None: str(tmp_path / "git.exe"))
    assert runner.run(["git", "status"]).returncode == 127


def test_maintenance_starts_from_home(monkeypatch, fake_home):
    seen = {}
    monkeypatch.setattr(maintenance.subprocess, "Popen", lambda cmd, **kw: seen.update(kw))
    maintenance._spawn_background()
    assert seen["cwd"] == str(fake_home)


def test_typecheck_hook_uses_the_absolute_path(tmp_path, monkeypatch):
    import importlib.util
    from loadout import paths
    spec = importlib.util.spec_from_file_location("tc", paths.kit_root() / "plugins/loadout/hooks/typecheck.py")
    tc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tc)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n")
    monkeypatch.setattr(tc.shutil, "which", lambda name, path=None: str(tmp_path / "pyright.cmd"))
    assert tc.checks([tmp_path / "a.py"]) == []  # a pyright in the project folder is not used
    monkeypatch.setattr(tc.shutil, "which", lambda name, path=None: "/opt/bin/pyright")
    assert tc.checks([tmp_path / "a.py"])[0][0][0] == "/opt/bin/pyright"
```

- [ ] Step 2: Run, expect FAIL.
- [ ] Step 3: Implement in `runner.py`:

```python
def _in_cwd(exe: str) -> bool:
    try:
        return os.path.dirname(os.path.abspath(exe)) == os.path.abspath(os.getcwd())
    except OSError:
        return False


def which(binary: str) -> str | None:
    """shutil.which without the current folder: Windows searches it before PATH, so a repo could ship git.exe."""
    if _is_windows():
        os.environ["NoDefaultCurrentDirectoryInExePath"] = "1"
    exe = shutil.which(binary)
    return None if exe is None or _in_cwd(exe) else exe


def have(binary: str) -> bool:
    return which(binary) is not None
```

`run` and `would_refuse` call `which` instead of `shutil.which`. In `maintenance._spawn_background`, pass `cwd=str(paths.home())`. In `typecheck.py`, add the same `_in_cwd` check and the environment variable (the hook does not import loadout). `checks()` stores the absolute path from `which` as the command's first element.
- [ ] Step 4: Full suite green; commit `fix(security): never run a program from the current folder`.

### Task 3: init and profile never write outside the repo

**Files:** `cli/loadout/paths.py` (new `inside`), `cli/loadout/codex_project.py` (use `paths.inside`, drop `_inside`), `cli/loadout/profiles.py` (`apply_profile`, `copy_skills` reuse), `cli/loadout/scaffold.py` (`scaffold`, `ensure_gitignore`), `cli/loadout/project.py` (print skipped lines), tests `tests/test_repo_writes_stay_inside.py`.

- [ ] Step 1: Failing tests:

```python
"""A repo's symlinks never make init/profile write outside the repo."""
from loadout import profiles, scaffold


def _repo(tmp_path):
    repo, outside = tmp_path / "repo", tmp_path / "outside"
    repo.mkdir(); outside.mkdir()
    return repo, outside


def test_profile_settings_through_a_symlinked_claude_folder(tmp_path):
    repo, outside = _repo(tmp_path)
    (repo / ".claude").symlink_to(outside)
    prof = profiles.Profile(name="t", description="", settings={"env": {"A": "1"}})
    changed, skipped = profiles.apply_profile(prof, repo)
    assert not (outside / "settings.json").exists()
    assert skipped and ".claude/settings.json" in skipped[0]


def test_mcp_json_symlink_is_not_followed(tmp_path):
    repo, outside = _repo(tmp_path)
    (repo / ".mcp.json").symlink_to(outside / "x.json")  # dangling
    prof = profiles.Profile(name="t", description="", mcp={"mcpServers": {"a": {"command": "x"}}})
    profiles.apply_profile(prof, repo)
    assert not (outside / "x.json").exists()


def test_scaffold_never_creates_through_a_dangling_symlink(tmp_path):
    repo, outside = _repo(tmp_path)
    (repo / "AGENTS.md").symlink_to(outside / "AGENTS.md")
    created, notes = scaffold.scaffold(repo)
    assert not (outside / "AGENTS.md").exists()
    assert repo / "AGENTS.md" not in created


def test_scaffold_skips_a_symlinked_docs_folder(tmp_path):
    repo, outside = _repo(tmp_path)
    (repo / "docs").symlink_to(outside)
    scaffold.scaffold(repo)
    assert list(outside.iterdir()) == []


def test_gitignore_symlink_outside_is_not_appended(tmp_path):
    repo, outside = _repo(tmp_path)
    (outside / "g").write_text("x\n")
    (repo / ".gitignore").symlink_to(outside / "g")
    assert scaffold.ensure_gitignore(repo) == []
    assert (outside / "g").read_text() == "x\n"
```

- [ ] Step 2: Run, expect FAIL (`apply_profile` returns a plain list today).
- [ ] Step 3: Implement. `paths.inside(path, root) -> bool` resolves `path` (following any symlink, including a dangling one, via `os.path.realpath`) and checks it is under `root.resolve()`. `apply_profile` returns `(changed, skipped)`: it skips a target when `not paths.inside(target, project) or not paths.inside(target.parent, project)`, with a line like `skipped .claude/settings.json: it points outside the repo`. Update its two callers (`project.add_profile` prints the skipped lines and counts them as problems, so it exits 1), plus the tests that unpack it. `scaffold` treats `dest.exists() or dest.is_symlink()` as present and skips a destination whose resolved path or parent is outside (noting it). `ensure_gitignore` returns `[]` and writes nothing when `.gitignore` resolves outside. `codex_project` uses `paths.inside`.
- [ ] Step 4: Full suite green; commit `fix(security): init and profile never write through symlinks out of the repo`.

### Task 4: Restore trusts only loadout's own backups

**Files:** `cli/loadout/backup.py` (`restore`, `_undo`, new `_allowed_run`), `cli/loadout/commands.py` (message), tests `tests/test_restore_trust.py`.

- [ ] Step 1: Failing tests:

```python
"""restore replays only loadout's own backups and only the undo commands loadout records."""
import json

import pytest

from loadout import backup, paths


def _manifest(root, steps):
    root.mkdir(parents=True)
    (root / "manifest.json").write_text(json.dumps({"steps": steps}))


def test_a_folder_outside_the_backup_directory_is_refused(fake_home, tmp_path):
    _manifest(tmp_path / "evil", [])
    lines, ok, _ = backup.restore(tmp_path / "evil")
    assert not ok and "only restores backups under" in lines[0]


@pytest.mark.parametrize("cmd", [
    ["claude", "mcp", "add-json", "-s", "user", "x", '{"command": "sh"}', "--extra"],
    ["claude", "config", "set", "x", "y"],
    ["claude", "plugin", "install", "-x"],
    ["codex", "plugin", "add", "x@y"],
])
def test_only_recorded_undo_shapes_run(fake_home, fake_runner, cmd):
    root = paths.backups_root() / "loadout-1"
    _manifest(root, [{"label": "x", "undo": {"run": cmd}}])
    lines, ok, _ = backup.restore(root)
    assert not ok and fake_runner.calls == []


@pytest.mark.parametrize("cmd", [
    ["claude", "mcp", "add-json", "-s", "user", "x", '{"command": "npx"}'],
    ["claude", "mcp", "remove", "-s", "user", "x"],
    ["claude", "plugin", "enable", "a@b", "--scope", "user"],
    ["claude", "plugin", "install", "a@b", "--scope", "user"],
    ["claude", "plugin", "marketplace", "add", "owner/repo"],
    ["codex", "plugin", "remove", "a@b"],
    ["codex", "plugin", "marketplace", "remove", "m"],
])
def test_recorded_undo_shapes_still_run(fake_home, fake_runner, cmd):
    root = paths.backups_root() / "loadout-2"
    _manifest(root, [{"label": "x", "undo": {"run": cmd}}])
    backup.restore(root)
    assert fake_runner.calls == [cmd]


def test_a_move_source_outside_the_backup_is_refused(fake_home, tmp_path):
    victim = tmp_path / "victim"
    victim.write_text("keep")
    root = paths.backups_root() / "loadout-3"
    _manifest(root, [{"label": "x", "undo": {"move": [str(victim), str(tmp_path / "dest")]}}])
    lines, ok, _ = backup.restore(root)
    assert not ok and victim.read_text() == "keep"


def test_a_real_backup_round_trips(fake_home):
    f = fake_home / "f.txt"
    f.write_text("old")
    bk = backup.Backup(description="t")
    bk.save_copy(f, "f")
    f.write_text("new")
    lines, ok, pre = backup.restore(bk.root)
    assert ok and f.read_text() == "old"
    assert backup.restore(pre)[1]  # a pre-restore backup is restorable too
```

- [ ] Step 2: Run, expect FAIL.
- [ ] Step 3: Implement. At the start of `restore`, if `root.resolve()` is not inside `paths.backups_root().resolve()`, return `[f"loadout only restores backups under {paths.backups_root()}; move it there first"], False, None`. `_allowed_run(cmd)` matches exactly these shapes, with no argument after the shape and no positional argument starting with `-`:
  - `claude mcp add-json -s user NAME JSON`, where JSON parses to a dict;
  - `claude mcp remove -s user NAME`;
  - `claude plugin enable|install ID --scope user`;
  - `claude plugin marketplace add ORIGIN`;
  - `codex plugin remove ID`;
  - `codex plugin marketplace remove NAME`.

  It replaces the current `cmd[0] == "claude" or codex_undo` check. In `_undo`, the source of `move` and `restore-file` must be inside `root / "files"`, otherwise `failed: {label}: its backup copy is not inside {root}`. Check `personal_mcp.replace_user_server` and the adopt undo commands against the shapes, and adjust a shape (not the recorder) if one differs.
- [ ] Step 4: Full suite green; commit `fix(security): restore trusts only loadout's backups and recorded undo commands`.

### Task 5: Names are checked; profile output is redacted

**Files:** `cli/loadout/profiles.py` (`load_profile`), `cli/loadout/link.py` (`LINKS` skills.json keys), `cli/loadout/project.py` (`_install`: plugin id check, redaction), `cli/loadout/codex_project.py` (`_wanted`: plugin id check), tests `tests/test_names_checked.py`.

- [ ] Step 1: Failing tests:

```python
"""Names from files become paths or arguments only when they are plain."""
import pytest

from loadout import codex_project, link, paths, profiles, project
from loadout.jsonio import save_json


@pytest.mark.parametrize("name", ["../x", "a/b", "-x", "X Y", ""])
def test_profile_names_must_be_plain(fake_home, name):
    with pytest.raises(ValueError, match="profile name"):
        profiles.load_profile(name)


def test_kit_profiles_still_load(fake_home):
    for name in ("android", "db", "sonar", "thesis", "web"):
        profiles.load_profile(name)


def test_skills_json_keys_must_be_plain(fake_home, tmp_path):
    target = tmp_path / "s"
    target.mkdir()
    save_json(paths.personal_root() / "skills.json", {"../agents": str(target), "ok": str(target)})
    names = [dest.name for dest, _ in link.LINKS() if dest.parent == paths.claude_home() / "skills"]
    assert names == ["ok"]


def test_plugin_ids_must_look_like_name_at_market(fake_home, fake_runner, tmp_path, capsys, monkeypatch):
    from loadout import targets
    monkeypatch.setattr(targets, "claude_enabled", lambda: True)
    prof = profiles.Profile(name="t", description="", install=["-rf@x", "ok@m"])
    project._install(prof, tmp_path, dry_run=False)
    assert ["claude", "plugin", "install", "ok@m", "--scope", "project"] in fake_runner.calls
    assert not any("-rf@x" in c for call in fake_runner.calls for c in call)
    assert codex_project._wanted(prof)[1] == ["ok@m"]


def test_profile_commands_are_printed_redacted(fake_home, fake_runner, tmp_path, capsys):
    from loadout import runner
    token = "ghp_" + "a" * 36
    fake_runner.responses[("tool",)] = runner.Result(1, "", f"bad token {token}")
    prof = profiles.Profile(name="t", description="", commands=[["tool", f"--token={token}"]])
    project._install(prof, tmp_path, dry_run=False)
    assert token not in capsys.readouterr().out
```

- [ ] Step 2: Run, expect FAIL.
- [ ] Step 3: Implement. `load_profile` checks `own.PROFILE_NAME` (move the regex to `profiles.NAME` and let `own` import it) and raises `ValueError(f"profile name {name!r}: use lowercase letters, digits, - and _")`. `LINKS` keeps a `skills.json` key only when `Path(name).name == name`, `name not in (".", "..")` and it does not start with `-`. Add `PLUGIN_ID = re.compile(r"^[A-Za-z0-9][\w.-]*@[A-Za-z0-9][\w.-]*$")` in `profiles.py`. `_install` and `_wanted` use only matching ids, and print `plugin {id!r}: not a name@marketplace id, skipped` for the others. `_install` wraps the printed command and stderr in `secrets.redact`.
- [ ] Step 4: Full suite green; commit `fix(security): plain names only; profile output redacted`.

### Task 6: Reusable stand-in Codex reviewer, and docs

**Files:** new `.claude/agents/codex-reviewer.md`, `CONTRIBUTING.md`, `docs/explanation/security-and-trust.md` (restore trust, program lookup, repo symlinks, cargo build scripts on untrusted repos), `docs/reference/cli.md` (restore refuses outside the backup directory; `profile` exits 1 on a skipped file), `docs/how-to/undo-and-restore.md`, tests `tests/test_codex_reviewer_agent.py`.

- [ ] Step 1: Failing test:

```python
from loadout import paths


def test_codex_reviewer_agent_carries_the_rubric_and_its_licence():
    text = (paths.kit_root() / ".claude/agents/codex-reviewer.md").read_text(encoding="utf-8")
    assert text.startswith("---\nname: codex-reviewer\n")
    assert "openai/codex" in text and "Apache License 2.0" in text
    assert "[P0]" in text and "overall_correctness" in text and "Code Review Rules" in text
    assert "codex-reviewer" in (paths.kit_root() / "CONTRIBUTING.md").read_text(encoding="utf-8")
```

- [ ] Step 2: Run, expect FAIL.
- [ ] Step 3: Write the agent:
  - Frontmatter: `name: codex-reviewer`, a description ("Stand-in for Codex's GitHub code review when its quota is exhausted: reviews a branch diff with Codex's open-source review rubric"), and `tools: Read, Grep, Glob, Bash`.
  - Body: an attribution line naming openai/codex `codex-rs/prompts/templates/review/rubric.md` under the Apache License 2.0, with a link. Then the rubric verbatim, re-fetched from that URL.
  - Then this repo's calibration: report P0–P2, apply AGENTS.md "Code Review Rules", trace call paths, read-only commands only, never real `claude`/`codex`/installers/evals.
  - In `CONTRIBUTING.md`, a short paragraph: when Codex's review quota is used up, ask Claude Code to "run the codex-reviewer agent on this branch", post its findings and fixes as PR comments, and repeat until it reports no findings.
  - Update the docs lines listed above.
- [ ] Step 4: Full suite green. Commit the agent and CONTRIBUTING as `chore(review): stand-in Codex reviewer agent`, and the docs as `docs: security hardening`.
