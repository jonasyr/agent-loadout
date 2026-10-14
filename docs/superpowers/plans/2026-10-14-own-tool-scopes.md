# Own-tool scopes (hardening 4c) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A direct command to create a skill in each of the three scopes (personal layer, personal profile, one repo) for both agents, `project:<profile>` in adopt for tools only Codex has, and docs that explain the three scopes in one table.

**Architecture:** A new module `cli/loadout/new_skill.py` owns `create(name, to, description, cwd, bk)` and its refusals; `commands.py` wires it as `loadout configure new skill`. `own.options`/`own.record_project` and `adopt._remove_project_skill` learn Codex items. Docs and the `loadout:configure` skill follow.

**Tech Stack:** Python 3.11+ standard library, pytest with the `fake_home`/`fake_runner` fixtures.

**Spec:** `docs/superpowers/specs/2026-10-14-own-tool-scopes-design.md`

## Global Constraints

- Python 3.11+, standard library only in `cli/loadout/`.
- Tests use `fake_home` and `fake_runner`; never the real `~/.claude`, `~/.claude.json`, `~/.codex`, `~/.config/loadout`, `~/.local/state`; never real `claude`/`codex`.
- External commands only through `runner.run` with argument lists.
- With an agent off (`targets`), nothing of that agent's is read or written.
- Never overwrite: an existing target is refused and nothing is written.
- Every created folder, file and link is recorded in a backup so `loadout restore` undoes it.
- Run tests with `uv run --python 3.12 --with pytest pytest -q`.
- Git: `/usr/bin/git` in plain single commands (worktree guard); Conventional Commits; no AI attribution.
- `NAME` matches `^[a-z0-9][a-z0-9-]{0,63}$`; bad input exits 2, refusals exit 1.

## Review Focus

- A name that differs only in case from an existing entry (case-insensitive file systems): taken (Task 1 test `test_a_name_taken_in_another_case_is_refused`).
- `--to repo` from a subfolder or a worktree (`.git` is a file): the repo root is found (Task 3 test `test_repo_root_is_found_from_a_subfolder_and_a_worktree`).
- Damaged profile JSON or `skills` not a list: refused, the file stays as it is (Task 2 test `test_a_damaged_profile_is_refused_and_left_alone`).
- A Codex-only server already in the profile's `mcp` with another config: refused (Task 5 test `test_codex_server_already_in_the_profile_is_refused`).
- Running `new skill` twice: the second run is refused and changes nothing (Task 1 test `test_running_it_twice_refuses_the_second_time`).

---

### Task 1: `new_skill.create` for `--to global`, with validation and undo

**Files:**
- Create: `cli/loadout/new_skill.py`
- Test: `tests/test_new_skill.py`

**Interfaces:**
- Produces: `new_skill.create(name: str, to: str = "global", description: str | None = None, cwd: Path | None = None, bk: Backup | None = None) -> list[str]`; exceptions `new_skill.BadInput(ValueError)` (exit 2) and `new_skill.Refused(ValueError)` (exit 1); `new_skill.stub(name, description) -> str`; `new_skill.repo_root(start: Path) -> Path | None` (Task 3 fills `_repo`, Task 2 fills `_project`).

- [ ] **Step 1: Write the failing tests** in `tests/test_new_skill.py`:

```python
"""loadout configure new skill: a SKILL.md stub in one of the three places a skill of yours can live."""
import json

import pytest

from loadout import backup, new_skill, paths, targets


def _agents(monkeypatch, claude=True, codex=True):
    monkeypatch.setattr(targets, "claude_enabled", lambda: claude)
    monkeypatch.setattr(targets, "codex_enabled", lambda: codex)


def _restore(bk):
    _, ok, _ = backup.restore(bk.root)
    assert ok


def test_global_writes_the_stub_and_links_it_for_both_agents(fake_home, monkeypatch):
    _agents(monkeypatch)
    bk = backup.Backup(description="t")
    lines = new_skill.create("notes", bk=bk)
    skill = paths.personal_root() / "skills" / "notes" / "SKILL.md"
    assert skill.read_text(encoding="utf-8").startswith("---\nname: notes\ndescription: TODO:")
    for dest in (paths.claude_home() / "skills" / "notes", paths.agents_skills() / "notes"):
        assert dest.is_symlink() and dest.resolve() == skill.parent.resolve()
    assert any("notes" in l and "created" in l for l in lines)


def test_only_the_agents_that_are_on_get_a_link(fake_home, monkeypatch):
    _agents(monkeypatch, claude=False, codex=True)
    new_skill.create("notes", bk=backup.Backup(description="t"))
    assert (paths.agents_skills() / "notes").is_symlink()
    assert not (paths.claude_home() / "skills").exists()


def test_restore_removes_the_folder_and_the_links(fake_home, monkeypatch):
    _agents(monkeypatch)
    bk = backup.Backup(description="t")
    new_skill.create("notes", bk=bk)
    _restore(bk)
    assert not (paths.personal_root() / "skills" / "notes").exists()
    for dest in (paths.claude_home() / "skills" / "notes", paths.agents_skills() / "notes"):
        assert not dest.exists() and not dest.is_symlink()


@pytest.mark.parametrize("name", ["Notes", "-x", "a/b", "..", "", "x" * 65, "a_b"])
def test_a_bad_name_is_bad_input_and_writes_nothing(fake_home, monkeypatch, name):
    _agents(monkeypatch)
    with pytest.raises(new_skill.BadInput):
        new_skill.create(name, bk=backup.Backup(description="t"))
    assert not (paths.personal_root() / "skills").exists()


def test_an_unknown_target_is_bad_input(fake_home, monkeypatch):
    _agents(monkeypatch)
    with pytest.raises(new_skill.BadInput):
        new_skill.create("notes", to="elsewhere", bk=backup.Backup(description="t"))


def test_an_existing_link_destination_is_refused_even_a_dangling_one(fake_home, monkeypatch):
    _agents(monkeypatch)
    dest = paths.agents_skills() / "notes"
    dest.parent.mkdir(parents=True)
    dest.symlink_to(fake_home / "gone", target_is_directory=True)
    with pytest.raises(new_skill.Refused, match="already exists"):
        new_skill.create("notes", bk=backup.Backup(description="t"))
    assert not (paths.personal_root() / "skills" / "notes").exists()


def test_a_name_taken_in_another_case_is_refused(fake_home, monkeypatch):
    _agents(monkeypatch)
    (paths.claude_home() / "skills" / "Notes").mkdir(parents=True)
    with pytest.raises(new_skill.Refused):
        new_skill.create("notes", bk=backup.Backup(description="t"))


def test_running_it_twice_refuses_the_second_time(fake_home, monkeypatch):
    _agents(monkeypatch)
    new_skill.create("notes", bk=backup.Backup(description="t"))
    before = (paths.personal_root() / "skills" / "notes" / "SKILL.md").read_bytes()
    with pytest.raises(new_skill.Refused):
        new_skill.create("notes", description="other", bk=backup.Backup(description="t"))
    assert (paths.personal_root() / "skills" / "notes" / "SKILL.md").read_bytes() == before


def test_a_secret_or_a_line_break_in_the_description_is_refused(fake_home, monkeypatch):
    _agents(monkeypatch)
    token = "ghp_" + "Z" * 36
    for text in (f"uses {token}", "two\nlines"):
        with pytest.raises(new_skill.Refused):
            new_skill.create("notes", description=text, bk=backup.Backup(description="t"))
    assert not (paths.personal_root() / "skills" / "notes").exists()


def test_the_description_lands_in_the_frontmatter(fake_home, monkeypatch):
    _agents(monkeypatch)
    new_skill.create("notes", description="Use when taking notes.", bk=backup.Backup(description="t"))
    text = (paths.personal_root() / "skills" / "notes" / "SKILL.md").read_text(encoding="utf-8")
    assert "description: Use when taking notes.\n" in text
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_new_skill.py`
Expected: FAIL at collection with `ImportError: cannot import name 'new_skill'`.

- [ ] **Step 3: Write `cli/loadout/new_skill.py`**

```python
"""`loadout configure new skill`: a SKILL.md stub in one of the three places a skill of yours can live
(docs/how-to/your-own-tools.md#where-a-tool-of-yours-can-live)."""
from __future__ import annotations

import re
from pathlib import Path

from . import paths, secrets, targets
from .backup import Backup

NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
DEFAULT_DESCRIPTION = "TODO: say when an agent should use this skill."


class BadInput(ValueError):
    """Wrong name or target (exit 2); nothing was written."""


class Refused(ValueError):
    """The skill cannot be created there (exit 1); nothing was written."""


def stub(name: str, description: str) -> str:
    return f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n\nTODO: the instructions.\n"


def _taken(folder: Path, name: str) -> Path | None:
    """The entry in folder that has this name, also in another case (macOS and Windows ignore case) or as a
    dangling link."""
    try:
        entries = list(folder.iterdir()) if folder.is_dir() else []
    except OSError:
        return None
    return next((e for e in entries if e.name.lower() == name.lower()), None)


def _refuse_taken(name: str, folders: list[Path]) -> None:
    for folder in folders:
        hit = _taken(folder, name)
        if hit is not None:
            raise Refused(f"skill {name}: {hit} already exists; nothing written")


def _write(folder: Path, name: str, description: str, bk: Backup) -> Path:
    skill = folder / name
    folder.mkdir(parents=True, exist_ok=True)
    skill.mkdir()
    bk.record_created(skill, f"skill {name} (created by configure new skill)")
    (skill / "SKILL.md").write_text(stub(name, description), encoding="utf-8", newline="\n")
    return skill / "SKILL.md"


def _link(dest: Path, src: Path, name: str, bk: Backup) -> str:
    from . import link
    line = link._link_one(dest, src, bk)
    bk.record_created(dest, f"link for skill {name}")
    return line or f"linked {dest} -> {src}"


def _global(name: str, description: str, bk: Backup) -> list[str]:
    root = paths.personal_root() / "skills"
    dests = ([paths.claude_home() / "skills"] if targets.claude_enabled() else []) + \
            ([paths.agents_skills()] if targets.codex_enabled() else [])
    _refuse_taken(name, [root, *dests])
    skill_md = _write(root, name, description, bk)
    out = [f"skill {name}: created {skill_md}"]
    out += [_link(dest / name, skill_md.parent, name, bk) for dest in dests]
    return out


def create(name: str, to: str = "global", description: str | None = None, cwd: Path | None = None,
           bk: Backup | None = None) -> list[str]:
    """Write the stub where `to` says (global, project:<profile>, repo) and link it for the agents that are on."""
    if not NAME.match(name or ""):
        raise BadInput(f"skill name '{name}': use lowercase letters, digits and -, starting with a letter or "
                       "digit, at most 64 characters")
    text = DEFAULT_DESCRIPTION if description is None else description.strip()
    if "\n" in text or "\r" in text:
        raise Refused("--description: one line only")
    if secrets.redact(text) != text:
        raise Refused("--description looks like it contains a secret; secrets never belong in a skill")
    bk = bk or Backup(description=f"configure new skill {name}")
    if to == "global":
        return _global(name, text, bk)
    if to.startswith("project:"):
        return _project(name, to.split(":", 1)[1], text, bk)
    if to == "repo":
        return _repo(name, text, cwd or Path.cwd(), bk)
    raise BadInput(f"--to {to}: use global, project:<profile> or repo")


def _project(name: str, profile: str, description: str, bk: Backup) -> list[str]:
    raise BadInput("--to project: not available yet")


def _repo(name: str, description: str, cwd: Path, bk: Backup) -> list[str]:
    raise BadInput("--to repo: not available yet")


def repo_root(start: Path) -> Path | None:
    for folder in (start, *start.parents):
        if (folder / ".git").exists():
            return folder
    return None
```

- [ ] **Step 4: Run the tests**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_new_skill.py`
Expected: PASS (all tests of this task). If `test_restore_removes_the_folder_and_the_links` fails because restore cannot move a symlink, read `backup._undo` for `created` and fix the cause in `new_skill`, not in the test.

- [ ] **Step 5: Commit**

```bash
/usr/bin/git add cli/loadout/new_skill.py tests/test_new_skill.py
/usr/bin/git commit -m "feat(own): create a skill of your own in the personal layer, linked for both agents"
```

### Task 2: `--to project:<profile>`

**Files:**
- Modify: `cli/loadout/new_skill.py` (`_project`)
- Test: `tests/test_new_skill.py`

**Interfaces:**
- Consumes: `own.PROFILE_NAME`, `own._edit_profile(name, bk, change)`, `own._append_once`, `own.profile_note(name) -> str | None`, `jsonio.ensure`, `jsonio.load_json`.

- [ ] **Step 1: Write the failing tests** (append):

```python
def test_project_writes_into_the_profile_and_lists_it(fake_home, monkeypatch):
    _agents(monkeypatch)
    bk = backup.Backup(description="t")
    new_skill.create("notes", to="project:mine", bk=bk)
    assert (paths.personal_root() / "profiles" / "skills" / "notes" / "SKILL.md").is_file()
    data = json.loads((paths.personal_root() / "profiles" / "mine.json").read_text())
    assert data["skills"] == ["notes"]
    assert not (paths.claude_home() / "skills" / "notes").exists()  # reaches a repo through loadout profile
    _restore(bk)
    assert not (paths.personal_root() / "profiles" / "skills" / "notes").exists()
    assert not (paths.personal_root() / "profiles" / "mine.json").exists()


def test_a_bad_profile_name_is_bad_input(fake_home, monkeypatch):
    _agents(monkeypatch)
    with pytest.raises(new_skill.BadInput):
        new_skill.create("notes", to="project:../x", bk=backup.Backup(description="t"))


@pytest.mark.parametrize("text", ["{broken", '{"skills": "notes"}'])
def test_a_damaged_profile_is_refused_and_left_alone(fake_home, monkeypatch, text):
    _agents(monkeypatch)
    path = paths.personal_root() / "profiles" / "mine.json"
    path.parent.mkdir(parents=True)
    path.write_text(text)
    with pytest.raises(new_skill.Refused):
        new_skill.create("notes", to="project:mine", bk=backup.Backup(description="t"))
    assert path.read_text() == text
    assert not (paths.personal_root() / "profiles" / "skills" / "notes").exists()
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_new_skill.py -k project`
Expected: FAIL with `BadInput: --to project: not available yet` in the first and third tests.

- [ ] **Step 3: Replace `_project`**

```python
def _project(name: str, profile: str, description: str, bk: Backup) -> list[str]:
    from . import own
    from .jsonio import load_json
    if not own.PROFILE_NAME.match(profile):
        raise BadInput(f"profile name '{profile}': use lowercase letters, digits, - and _")
    path = paths.personal_root() / "profiles" / f"{profile}.json"
    if path.exists():
        try:
            data = load_json(path)
        except Exception as exc:
            raise Refused(f"{path} does not parse ({exc}); fix it, then run this again") from None
        if not isinstance(data, dict) or not isinstance(data.get("skills", []), list):
            raise Refused(f"{path}: skills is not a list; fix it, then run this again")
    root = paths.personal_root() / "profiles" / "skills"
    _refuse_taken(name, [root])
    skill_md = _write(root, name, description, bk)
    note = own.profile_note(profile)
    own._edit_profile(profile, bk, lambda d: own._append_once(own.ensure(d, "skills", list), name))
    return [*([note] if note else []), f"skill {name}: created {skill_md}; listed in profile {profile} "
            f"(apply it to a repo with `loadout profile {profile}`)"]
```

Check `own` exports `ensure` (it is imported there from `jsonio`); if not, import `ensure` from `.jsonio` here instead.

- [ ] **Step 4: Run the tests**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_new_skill.py`
Expected: PASS. `_edit_profile` must record the new profile file so restore removes it; if the restore assertion for `mine.json` fails, check `own._edit_json` for how a new file is recorded (`record_created`) and use that path.

- [ ] **Step 5: Commit**

```bash
/usr/bin/git add cli/loadout/new_skill.py tests/test_new_skill.py
/usr/bin/git commit -m "feat(own): create a skill in a personal profile"
```

### Task 3: `--to repo`

**Files:**
- Modify: `cli/loadout/new_skill.py` (`_repo`)
- Test: `tests/test_new_skill.py`

**Interfaces:**
- Consumes: `paths.inside(path, root) -> bool`, `repo_root` from Task 1.

- [ ] **Step 1: Write the failing tests** (append):

```python
def _repo(tmp_path, git_file=False):
    repo = tmp_path / "repo"
    repo.mkdir()
    if git_file:
        (repo / ".git").write_text("gitdir: /elsewhere/.git/worktrees/repo\n")
    else:
        (repo / ".git").mkdir()
    return repo


def test_repo_writes_claude_skills_and_links_agents_skills(fake_home, monkeypatch, tmp_path):
    _agents(monkeypatch)
    repo = _repo(tmp_path)
    bk = backup.Backup(description="t")
    new_skill.create("notes", to="repo", cwd=repo, bk=bk)
    assert (repo / ".claude" / "skills" / "notes" / "SKILL.md").is_file()
    link = repo / ".agents" / "skills" / "notes"
    assert link.is_symlink() and str(link.readlink()) == "../../.claude/skills/notes"
    _restore(bk)
    assert not (repo / ".claude" / "skills" / "notes").exists() and not link.is_symlink()


def test_repo_without_codex_writes_no_agents_link(fake_home, monkeypatch, tmp_path):
    _agents(monkeypatch, claude=True, codex=False)
    repo = _repo(tmp_path)
    new_skill.create("notes", to="repo", cwd=repo, bk=backup.Backup(description="t"))
    assert not (repo / ".agents").exists()


def test_repo_root_is_found_from_a_subfolder_and_a_worktree(fake_home, monkeypatch, tmp_path):
    _agents(monkeypatch)
    repo = _repo(tmp_path, git_file=True)
    (repo / "src" / "deep").mkdir(parents=True)
    new_skill.create("notes", to="repo", cwd=repo / "src" / "deep", bk=backup.Backup(description="t"))
    assert (repo / ".claude" / "skills" / "notes" / "SKILL.md").is_file()


def test_repo_outside_git_is_refused(fake_home, monkeypatch, tmp_path):
    _agents(monkeypatch)
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(new_skill.Refused, match="git repo"):
        new_skill.create("notes", to="repo", cwd=plain, bk=backup.Backup(description="t"))
    assert not (plain / ".claude").exists()


def test_repo_skills_folder_linking_outside_is_refused(fake_home, monkeypatch, tmp_path):
    _agents(monkeypatch)
    repo = _repo(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (repo / ".claude").symlink_to(outside, target_is_directory=True)
    with pytest.raises(new_skill.Refused, match="outside"):
        new_skill.create("notes", to="repo", cwd=repo, bk=backup.Backup(description="t"))
    assert not any(outside.iterdir())
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_new_skill.py -k repo`
Expected: FAIL with `BadInput: --to repo: not available yet`.

- [ ] **Step 3: Replace `_repo`**

```python
def _repo(name: str, description: str, cwd: Path, bk: Backup) -> list[str]:
    import os
    root = repo_root(Path(os.path.abspath(cwd)))
    if root is None:
        raise Refused(f"--to repo: {cwd} is not inside a git repo")
    src_root = root / ".claude" / "skills"
    dest_root = root / ".agents" / "skills" if targets.codex_enabled() else None
    for folder in (src_root, dest_root):
        if folder is not None and not (paths.inside(folder.parent, root) and paths.inside(folder, root)):
            raise Refused(f"--to repo: {folder} points outside {root} (a symlinked folder); nothing written")
    _refuse_taken(name, [f for f in (src_root, dest_root) if f is not None])
    skill_md = _write(src_root, name, description, bk)
    out = [f"skill {name}: created {skill_md} (commit it to share it with this repo)"]
    if dest_root is not None:
        dest = dest_root / name
        dest_root.mkdir(parents=True, exist_ok=True)
        try:
            os.symlink(f"../../.claude/skills/{name}", dest, target_is_directory=True)
        except OSError as exc:  # e.g. Windows without symlink rights
            return out + [f"skill {name}: not linked for Codex ({exc.strerror or exc})"]
        bk.record_created(dest, f"Codex link for skill {name}")
        out.append(f"linked {dest} -> ../../.claude/skills/{name}")
    return out
```

- [ ] **Step 4: Run the tests**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_new_skill.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
/usr/bin/git add cli/loadout/new_skill.py tests/test_new_skill.py
/usr/bin/git commit -m "feat(own): create a skill committed in one repo, linked for Codex"
```

### Task 4: CLI `loadout configure new skill NAME [--to WHERE] [--description TEXT]`

**Files:**
- Modify: `cli/loadout/commands.py` (configure parser and `run`, around lines 165-260)
- Test: `tests/test_new_skill_cli.py`

**Interfaces:**
- Consumes: `new_skill.create`, `new_skill.BadInput`, `new_skill.Refused`, `configure.offer_commit(ask)`, `targets.restart_hint()`.

- [ ] **Step 1: Write the failing tests**

```python
"""The CLI front of configure new skill: exit codes, backup line, commit offer only for the personal layer."""
from loadout import configure, paths, targets
from loadout.__main__ import main


def _on(monkeypatch):
    monkeypatch.setattr(targets, "claude_enabled", lambda: True)
    monkeypatch.setattr(targets, "codex_enabled", lambda: True)


def test_new_skill_prints_the_backup_and_offers_the_commit(fake_home, fake_runner, monkeypatch, capsys):
    _on(monkeypatch)
    offered = []
    monkeypatch.setattr(configure, "offer_commit", lambda ask: offered.append(1))
    assert main(["configure", "new", "skill", "notes", "--description", "Use when taking notes."]) == 0
    out = capsys.readouterr().out
    assert "created" in out and "loadout restore" in out and offered == [1]
    assert (paths.personal_root() / "skills" / "notes" / "SKILL.md").is_file()


def test_bad_name_exits_2_and_a_refusal_exits_1(fake_home, fake_runner, monkeypatch, capsys):
    _on(monkeypatch)
    monkeypatch.setattr(configure, "offer_commit", lambda ask: None)
    assert main(["configure", "new", "skill", "Bad"]) == 2
    assert main(["configure", "new", "skill", "notes"]) == 0
    assert main(["configure", "new", "skill", "notes"]) == 1
    assert "already exists" in capsys.readouterr().err


def test_repo_target_offers_no_commit(fake_home, fake_runner, monkeypatch, tmp_path):
    _on(monkeypatch)
    offered = []
    monkeypatch.setattr(configure, "offer_commit", lambda ask: offered.append(1))
    repo = tmp_path / "r"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.chdir(repo)
    assert main(["configure", "new", "skill", "notes", "--to", "repo"]) == 0
    assert offered == []


def test_new_needs_skill_and_a_name(fake_home, fake_runner, monkeypatch):
    _on(monkeypatch)
    assert main(["configure", "new", "skill"]) == 1
    assert main(["configure", "new", "plugin", "x"]) == 1
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_new_skill_cli.py`
Expected: FAIL with exit code 2 from argparse (`invalid choice: 'new'`).

- [ ] **Step 3: Wire the command in `commands.py`**

Add `"new"` to the `action` choices and `"skill"` to the `kind` choices, add the example line `"  loadout configure new skill notes --description 'Use when ...'\n"` to the epilog, and two arguments next to `--all`:

```python
    p.add_argument("--to", default="global", help="with new skill: global (default), project:<profile> or repo")
    p.add_argument("--description", help="with new skill: one line saying when an agent should use the skill")
```

In `run(a)`, before the `if not (a.kind and a.name and a.value)` check:

```python
        if a.action == "new":
            if a.kind != "skill" or not a.name:
                raise ValueError("usage: loadout configure new skill NAME [--to global|project:<profile>|repo] "
                                 "[--description TEXT]")
            from . import new_skill
            from .backup import Backup
            from .secrets import redact
            bk = Backup(description=f"configure new skill {a.name}")
            try:
                lines = new_skill.create(a.name, a.to, a.description, bk=bk)
            except new_skill.BadInput as exc:
                print(f"loadout: {exc}", file=sys.stderr)
                return 2
            except new_skill.Refused as exc:
                print(f"loadout: {redact(str(exc))}", file=sys.stderr)
                return 1
            print("\n".join(lines))
            print(f"backup: {bk.root}  (undo: loadout restore {bk.root})")
            print(f"Fill in SKILL.md. {targets.restart_hint()}")
            if a.to != "repo":
                configure.offer_commit(_ask)
            return 0
```

Import `sys` and `targets` at the top of `commands.py` if they are not imported yet. Update the `action` help text to mention `new skill`.

- [ ] **Step 4: Run the tests and the CLI help tests**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_new_skill_cli.py tests/test_cli_help.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
/usr/bin/git add cli/loadout/commands.py tests/test_new_skill_cli.py
/usr/bin/git commit -m "feat(configure): loadout configure new skill NAME --to global|project:<p>|repo"
```

### Task 5: Adopt: `project:<profile>` for Codex-only skills and MCP servers

**Files:**
- Modify: `cli/loadout/own.py` (`options` around line 773, `record_project` around line 816)
- Modify: `cli/loadout/adopt.py` (`_remove_project_skill` around line 618; project branch around line 696)
- Test: `tests/test_codex_adopt_project.py`

**Interfaces:**
- Consumes: `own.is_codex(item)`, `codex.remove_server(name, bk) -> str` (saves `config.toml`, runs `codex mcp remove`), existing `record_project` paths for `mcp` and `skill`.

- [ ] **Step 1: Write the failing tests**

```python
"""adopt: a tool only Codex has goes into a personal profile, like a Claude Code one."""
import json

import pytest

from loadout import adopt, backup, codex, own, paths, targets
from loadout.inventory import Item, Verdict
from loadout.jsonio import load_json


@pytest.fixture
def codex_on(fake_home, monkeypatch):
    monkeypatch.setattr(targets, "codex_enabled", lambda: True)
    monkeypatch.setattr(targets, "claude_enabled", lambda: False)
    monkeypatch.setattr(codex, "apply_config", lambda bk, dry_run=False: [])
    monkeypatch.setattr(codex, "apply_skills", lambda bk: [])
    cfg = paths.codex_home() / "config.toml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text('[mcp_servers.mine]\ncommand = "m"\n')


def _skill(name="solo", link=False, tmp=None):
    path = paths.agents_skills() / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if link:
        path.symlink_to(tmp, target_is_directory=True)
    else:
        path.mkdir()
        (path / "SKILL.md").write_text("---\nname: solo\ndescription: x\n---\n")
    return Verdict(Item("skill", name, name, str(path), {}), "own", "")


def _mcp(cfg=None, problem=""):
    return Verdict(Item("mcp", "mine", "m", codex.CONFIG_LOCATION, {"config": cfg, "problem": problem}), "own", "")


def test_codex_skill_folder_and_server_offer_project(codex_on, tmp_path):
    assert "project" in own.options(_skill().item)
    assert "project" in own.options(_mcp({"type": "stdio", "command": "m"}).item)
    target = tmp_path / "shared"
    target.mkdir()
    assert "project" not in own.options(_skill("linked", link=True, tmp=target).item)


def test_codex_skill_to_project_is_copied_and_moved_out(codex_on, fake_runner):
    v = _skill()
    bk = backup.Backup(description="t")
    out, _ = adopt.apply_own([(v, own.Choice("project", "mine"))], bk)
    assert (paths.personal_root() / "profiles" / "skills" / "solo" / "SKILL.md").is_file()
    assert load_json(paths.personal_root() / "profiles" / "mine.json")["skills"] == ["solo"]
    assert not (paths.agents_skills() / "solo").exists()
    assert any("~/.agents/skills" in l for l in out)


def test_codex_server_to_project_goes_into_the_profile_and_out_of_codex(codex_on, fake_runner):
    v = _mcp({"type": "stdio", "command": "m"})
    bk = backup.Backup(description="t")
    adopt.apply_own([(v, own.Choice("project", "mine"))], bk)
    profile = load_json(paths.personal_root() / "profiles" / "mine.json")
    assert profile["mcp"]["mcpServers"]["mine"] == {"type": "stdio", "command": "m"}
    assert ["codex", "mcp", "remove", "mine"] in fake_runner.calls
    assert any("config.toml" in s.get("label", "") for s in bk.steps)


def test_codex_server_that_cannot_be_expressed_is_refused(codex_on, fake_runner):
    rec = own.record_project(_mcp(None, "mcp mine: startup_timeout_sec has no Claude Code equivalent"),
                             "mine", backup.Backup(description="t"))
    assert not rec.ok and "startup_timeout_sec" in rec.lines[0]
    assert not (paths.personal_root() / "profiles" / "mine.json").exists()


def test_codex_server_already_in_the_profile_is_refused(codex_on, fake_runner):
    path = paths.personal_root() / "profiles" / "mine.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"mcp": {"mcpServers": {"mine": {"type": "stdio", "command": "other"}}}}))
    rec = own.record_project(_mcp({"type": "stdio", "command": "m"}), "mine", backup.Backup(description="t"))
    assert not rec.ok and "already exists" in rec.lines[0]
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_codex_adopt_project.py`
Expected: FAIL: `'project' in ['global', 'leave', 'remove']` is false; `record_project` raises `ValueError: ... project is not available for this item`.

- [ ] **Step 3: Change `own.options`**

```python
def options(item: Item) -> list[str]:
    """Choices that apply to this item, in prompt order."""
    if is_codex(item):
        if item.kind == "skill" and Path(item.location).is_symlink():
            return ["global", "leave", "remove"]
        return ["global", "project", "leave", "remove"]
    ...  # the rest stays as it is
```

- [ ] **Step 4: Refuse an inexpressible Codex server in `record_project`**

At the start of the `elif item.kind == "mcp":` branch:

```python
        elif item.kind == "mcp":
            if is_codex(item) and item.extra.get("config") is None:
                raise Collision(item.extra.get("problem") or f"mcp {item.name}: cannot be recorded")
```

- [ ] **Step 5: Name the right folder when a Codex skill leaves global (`adopt._remove_project_skill`)**

```python
def _remove_project_skill(v: Verdict, profile: str, bk: Backup) -> list[str]:
    where = "~/.agents/skills" if own.is_codex(v.item) else "~/.claude/skills"
    bk.move(Path(v.item.location), f"skill {v.item.name} (kept in profile {profile})")
    return [f"skill {v.item.name}: removed from {where} (kept in profile {profile}; original in the backup)"]
```

Import `own` in `adopt.py` at module level if `_remove_project_skill` cannot see it (other functions import it locally).

The Codex server removal needs no new code: the project branch appends a `remove` verdict, and `adopt._apply_mcp` already calls `codex.remove_server` for Codex items.

- [ ] **Step 6: Run the tests and the existing adopt/own suites**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_codex_adopt_project.py tests/test_codex_adopt.py tests/test_codex_adopt_apply.py tests/test_own.py tests/test_adopt.py`
Expected: PASS. If an existing test pinned `options()` for a Codex item to `["global", "leave", "remove"]`, update it to the new list (that pin was the backlog gap) and say so in the commit body.

- [ ] **Step 7: Commit**

```bash
/usr/bin/git add cli/loadout/own.py cli/loadout/adopt.py tests/test_codex_adopt_project.py
/usr/bin/git commit -m "feat(adopt): project:<profile> for skills and MCP servers only Codex has"
```

### Task 6: Docs, the configure skill and the AGENTS.md map

**Files:**
- Modify: `docs/how-to/your-own-tools.md`
- Modify: `docs/reference/cli.md` (`## loadout configure`)
- Modify: `plugins/loadout/skills/configure/SKILL.md`
- Modify: `AGENTS.md` (module map: `new_skill.py`)

- [ ] **Step 1: `your-own-tools.md`**: after the intro paragraphs, add:

```markdown
## Where a tool of yours can live

| | Personal layer (`global`) | Personal profile (`project:<profile>`) | Committed in one repo |
|---|---|---|---|
| Files | `<personal>/skills/`, `mcp.json`, `settings.json` | `<personal>/profiles/<profile>.json` and `profiles/skills/` | the repo's `.claude/skills/`, `.mcp.json`, `.codex/config.toml` |
| Which machines | every machine with your personal layer | every machine, but only in repos you apply the profile to | every clone of that repo |
| Who else | nobody | nobody | everyone who clones the repo |
| Claude Code gets it | linked into `~/.claude/skills`, servers through `claude mcp`, settings merged | copied into the repo by `loadout profile <profile>` | reads the repo's files |
| Codex gets it | linked into `~/.agents/skills`, servers in `~/.codex/config.toml` | `loadout profile` links `.agents/skills` and writes `.codex/config.toml` | `.agents/skills` links (from `loadout init` or `new skill --to repo`) and `.codex/config.toml` |
| Undo | `loadout restore` | `loadout restore` (the repo's copy stays; it is a copy) | `loadout restore` for what loadout created; your commits are yours |

## Create a skill of your own

```bash
loadout configure new skill notes --description "Use when taking meeting notes."
loadout configure new skill db-tips --to project:db
loadout configure new skill release --to repo
```

The command writes a `SKILL.md` stub (name, description, a short body to fill in) and links it for the agents that are on. It refuses, writing nothing, when the name is taken in any of those places (also in another case, or as a dangling link). `--to repo` works in a git repo; commit the new folder yourself. Every folder and link it creates is in a backup, so `loadout restore` removes it. For the personal layer it ends with the commit offer, like adopt.
```

In the "Only in Codex" list, change "with the choices `global`, `leave` and `remove`" to "with the choices `global`, `project:<profile>`, `leave` and `remove` (a skill that is a link to a shared source: `global`, `leave`, `remove`)", and add a bullet:

```markdown
  - **project** writes the server into the profile's `mcp` (same conversion and refusals as `global`) or copies the skill into `profiles/skills/`, then removes it from Codex's global setup with a backup, as `remove` does.
```

- [ ] **Step 2: `cli.md`**: add `new skill NAME` to the `loadout configure [...]` usage line, a table row `| \`loadout configure new skill NAME [--to global\|project:<profile>\|repo] [--description TEXT]\` | Create a skill of your own: see [Create a skill of your own](../how-to/your-own-tools.md#create-a-skill-of-your-own). |`, the two flags in the flag table, the example, and in its exit-code table: `1` gains "`new skill`: the name is taken, the profile is damaged, `--to repo` outside a git repo, or the description is refused (nothing written)", `2` gains "`new skill` with a bad name, profile name or `--to`".

- [ ] **Step 3: configure skill**: in `plugins/loadout/skills/configure/SKILL.md`, in the changes table add a row `| Create a skill of their own | Ask where it should live (every machine: global; some repos: project:<profile>; this repo for everyone: repo), then \`loadout configure new skill NAME --to ... --description "..."\`; then fill in the SKILL.md it printed. Never write into the skills folders directly. |`.

- [ ] **Step 4: AGENTS.md**: in the module map line with `own.py`, add `` `new_skill.py` `configure new skill` (a SKILL.md stub in one of the three scopes) ``.

- [ ] **Step 5: Check links and run the doc tests**

Run: `uv run --python 3.12 --with pytest pytest -q` (the suite includes the docs link checks)
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
/usr/bin/git add docs/how-to/your-own-tools.md docs/reference/cli.md plugins/loadout/skills/configure/SKILL.md AGENTS.md
/usr/bin/git commit -m "docs: where a tool of yours can live, and creating a skill"
```
