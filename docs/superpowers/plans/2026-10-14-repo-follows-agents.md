# Repo files follow the agents that are on: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** With Codex only, `loadout profile`, `init` and `configure new skill --to repo` write nothing for Claude Code in a repo; repo skills live in `.agents/skills` and get linked into `.claude/skills` once Claude Code is on.

**Architecture:** One helper (`profiles.repo_skill_dirs`) decides where a repo skill's real folder goes; one linker (`profiles.link_skills`, moved out of `codex_project.skills`) links skills in both directions for the agents that are on; `apply_profile`, `scaffold` and `ensure_gitignore` skip Claude Code's files when it is off.

**Tech Stack:** Python 3.11+ standard library (`cli/loadout/`), pytest.

**Spec:** `docs/superpowers/specs/2026-10-14-repo-follows-agents-design.md`

## Global Constraints

- Python 3.11+, standard library only in `cli/loadout/`.
- Tests use `fake_home` (and `fake_runner` where commands run); set agents with `targets.set_agents({"claude": ..., "codex": ...})` after `fake_home`. Never touch the real `~/.claude`, `~/.codex`, `~/.config/loadout`.
- Files already in a repo are never moved or deleted.
- Relative links only: `../../.claude/skills/NAME` and `../../.agents/skills/NAME`.
- Today's Codex-direction lines stay word for word: `linked skill NAME for Codex -> .agents/skills/NAME`, `would link skill NAME for Codex -> .agents/skills/NAME`, `skill NAME: not linked for Codex (...)`, `skill NAME: .agents/skills/NAME is not a link to .claude/skills/NAME, left as is (Codex uses that one)`.
- Conventional Commits, no AI attribution. Run git as `/usr/bin/git`.
- Test command: `uv run --python 3.12 --with pytest pytest -q`.

## Review Focus

- A repo used with both agents where a skill exists as a real folder in both `.claude/skills` and `.agents/skills`: exactly one "left as is" line, nothing replaced (test in Task 2).
- `.claude/skills/x` is a link to `../../.agents/skills/x` made in an earlier run, then Claude Code is turned off: the Codex direction must stay silent, not report "left as is" (test in Task 2).
- `new skill --to repo` with Codex only in a repo whose `.claude/skills/NAME` exists (a teammate's): refused, nothing written (test in Task 3).
- `.agents` symlinked outside the repo with Codex only: `copy_skills` writes nothing outside (test in Task 1).
- Dry run with Codex only: no `.agents` folder created, `would copy skill` names `.agents/skills` (test in Task 1).

---

### Task 1: Where a repo skill's real folder goes; `copy_skills` uses it

**Files:**
- Modify: `cli/loadout/profiles.py` (add `repo_skill_dirs`, change `copy_skills`)
- Test: `tests/test_repo_follows_agents.py` (create)

**Interfaces:**
- Produces: `profiles.repo_skill_dirs(project: Path) -> tuple[Path, Path | None]` — (real folder, link folder or None). `profiles.REPO_SKILLS: tuple[str, str] = (".claude/skills", ".agents/skills")`.

- [ ] **Step 1: Write the failing tests** (create `tests/test_repo_follows_agents.py`)

```python
"""Repo files follow the agents that are on (ADR 0027)."""
import os
from pathlib import Path

import pytest

from loadout import profiles, targets


@pytest.fixture
def repo(fake_home, tmp_path):
    p = tmp_path / "repo"
    (p / ".git").mkdir(parents=True)
    return p


@pytest.fixture
def kit_skill(fake_home, monkeypatch, tmp_path):
    src = tmp_path / "personal" / "profiles" / "skills" / "pw"
    src.mkdir(parents=True)
    (src / "SKILL.md").write_text("---\nname: pw\n---\n")
    monkeypatch.setattr(profiles, "_skill_source", lambda name: src if name == "pw" else None)
    return profiles.Profile(name="web", description="", skills=["pw"])


@pytest.mark.parametrize("agents, real, link", [
    ({"claude": True, "codex": True}, ".claude/skills", ".agents/skills"),
    ({"claude": True, "codex": False}, ".claude/skills", None),
    ({"claude": False, "codex": True}, ".agents/skills", None),
])
def test_repo_skill_dirs_follow_the_agents(repo, agents, real, link):
    targets.set_agents(agents)
    got_real, got_link = profiles.repo_skill_dirs(repo)
    assert got_real == repo / real
    assert got_link == (repo / link if link else None)


def test_codex_only_copies_into_agents_skills_and_writes_no_claude(repo, kit_skill):
    targets.set_agents({"claude": False, "codex": True})
    lines = profiles.copy_skills(kit_skill, repo)
    assert (repo / ".agents" / "skills" / "pw" / "SKILL.md").is_file()
    assert not (repo / ".claude").exists()
    assert lines == [f"copied skill pw -> {repo / '.agents' / 'skills' / 'pw'}"]


def test_a_skill_in_the_other_folder_is_left_as_is(repo, kit_skill):
    targets.set_agents({"claude": False, "codex": True})
    (repo / ".claude" / "skills" / "pw").mkdir(parents=True)  # a teammate's
    lines = profiles.copy_skills(kit_skill, repo)
    assert lines == [f"skill pw: {repo / '.claude' / 'skills' / 'pw'} exists, left as is"]
    assert not (repo / ".agents").exists()


def test_codex_only_dry_run_creates_nothing(repo, kit_skill):
    targets.set_agents({"claude": False, "codex": True})
    lines = profiles.copy_skills(kit_skill, repo, dry_run=True)
    assert lines == [f"would copy skill pw -> {repo / '.agents' / 'skills' / 'pw'}"]
    assert not (repo / ".agents").exists()


def test_codex_only_agents_folder_outside_the_repo_is_refused(repo, kit_skill, tmp_path):
    targets.set_agents({"claude": False, "codex": True})
    (tmp_path / "elsewhere").mkdir()
    (repo / ".agents").symlink_to(tmp_path / "elsewhere")
    lines = profiles.copy_skills(kit_skill, repo)
    assert len(lines) == 1 and "points outside" in lines[0] and ".agents" in lines[0]
    assert list((tmp_path / "elsewhere").iterdir()) == []
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_repo_follows_agents.py`
Expected: FAIL — `AttributeError: module 'loadout.profiles' has no attribute 'repo_skill_dirs'`; the copy tests fail because the skill lands in `.claude/skills`.

- [ ] **Step 3: Implement** in `cli/loadout/profiles.py`, above `copy_skills`:

```python
REPO_SKILLS = (".claude/skills", ".agents/skills")  # Claude Code's and Codex's skill folder in a repo


def repo_skill_dirs(project: Path) -> tuple[Path, Path | None]:
    """(where a new repo skill's real folder goes, the other agent's folder that links to it, or None): Claude Code's
    .claude/skills whenever Claude Code is on, else Codex's .agents/skills (ADR 0027)."""
    from . import targets
    claude, agents = (project / rel for rel in REPO_SKILLS)
    if not targets.claude_enabled():
        return agents, None
    return claude, agents if targets.codex_enabled() else None
```

and replace the body of `copy_skills`:

```python
def copy_skills(profile: Profile, project: Path, dry_run: bool = False) -> list[str]:
    """Copy the profile's skills into the repo's real skill folder (repo_skill_dirs). A skill of that name in either
    agent's folder is never overwritten."""
    out = []
    skills_dir, _ = repo_skill_dirs(project)
    if not paths.inside(skills_dir, project):
        top = skills_dir.parent.name
        return [f"skills not copied: {skills_dir} points outside {project} (a symlinked {top} or {top}/skills)"]
    for name in profile.skills:
        if not isinstance(name, str) or not name or Path(name).name != name or name in (".", ".."):
            out.append(f"skill {name}: not a plain name, skipped")
            continue
        src, dest = _skill_source(name), skills_dir / name
        found = next((project / rel / name for rel in REPO_SKILLS
                      if (project / rel / name).exists() or (project / rel / name).is_symlink()), None)
        if src is None:
            out.append(f"skill {name}: not found in profiles/skills/ (personal layer or kit)")
        elif found is not None:
            out.append(f"skill {name}: {found} exists, left as is")
        elif dry_run:
            out.append(f"would copy skill {name} -> {dest}")
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(src, dest, symlinks=True)
            out.append(f"copied skill {name} -> {dest}")
    return out
```

- [ ] **Step 4: Run the new tests and the profile tests**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_repo_follows_agents.py tests/test_project.py tests/test_repo_writes_stay_inside.py`
Expected: all pass. If an old test asserted `a symlinked .claude or .claude/skills`, the wording is unchanged for Claude Code on (`top` is `.claude`).

- [ ] **Step 5: Commit**

```bash
/usr/bin/git add cli/loadout/profiles.py tests/test_repo_follows_agents.py
/usr/bin/git commit -m "feat(profile): with Codex only, profile skills go into .agents/skills"
```

### Task 2: `link_skills` links both ways for the agents that are on

**Files:**
- Modify: `cli/loadout/profiles.py` (add `link_skills`, `_link_into`; `import os` at the top)
- Modify: `cli/loadout/codex_project.py` (remove `skills`; `apply` no longer calls it)
- Modify: `cli/loadout/project.py` (`add_profile` calls `profiles.link_skills` after `_install`)
- Modify: `tests/test_codex_project.py` (calls of `codex_project.skills` become `profiles.link_skills` with Codex on)
- Test: `tests/test_repo_follows_agents.py`

**Interfaces:**
- Consumes: `profiles.REPO_SKILLS` (Task 1).
- Produces: `profiles.link_skills(project: Path, dry_run: bool) -> list[str]`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_repo_follows_agents.py`)

```python
def _real(repo, rel, name):
    (repo / rel / name).mkdir(parents=True)
    (repo / rel / name / "SKILL.md").write_text(f"---\nname: {name}\n---\n")


def test_both_on_links_each_way(repo):
    targets.set_agents({"claude": True, "codex": True})
    _real(repo, ".claude/skills", "pw")
    _real(repo, ".agents/skills", "mine")
    lines = profiles.link_skills(repo, dry_run=False)
    assert Path(os.readlink(repo / ".agents/skills/pw")) == Path("../../.claude/skills/pw")
    assert Path(os.readlink(repo / ".claude/skills/mine")) == Path("../../.agents/skills/mine")
    assert lines == ["linked skill pw for Codex -> .agents/skills/pw",
                     "linked skill mine for Claude Code -> .claude/skills/mine"]
    assert profiles.link_skills(repo, dry_run=False) == []


def test_codex_only_links_a_teammates_claude_skill_and_writes_nothing_under_claude(repo):
    _real(repo, ".claude/skills", "pw")
    targets.set_agents({"claude": False, "codex": True})
    before = sorted(p.name for p in (repo / ".claude" / "skills").iterdir())
    assert profiles.link_skills(repo, dry_run=False) == ["linked skill pw for Codex -> .agents/skills/pw"]
    assert sorted(p.name for p in (repo / ".claude" / "skills").iterdir()) == before


def test_turning_claude_code_on_later_links_codex_skills(repo):
    targets.set_agents({"claude": False, "codex": True})
    _real(repo, ".agents/skills", "notes")
    assert profiles.link_skills(repo, dry_run=False) == []
    assert not (repo / ".claude").exists()
    targets.set_agents({"claude": True, "codex": True})
    assert profiles.link_skills(repo, dry_run=False) == ["linked skill notes for Claude Code -> .claude/skills/notes"]
    assert (repo / ".claude/skills/notes/SKILL.md").is_file()


def test_the_other_agents_link_is_silent_after_claude_code_is_turned_off(repo):
    targets.set_agents({"claude": True, "codex": True})
    _real(repo, ".agents/skills", "notes")
    profiles.link_skills(repo, dry_run=False)  # .claude/skills/notes -> ../../.agents/skills/notes
    targets.set_agents({"claude": False, "codex": True})
    assert profiles.link_skills(repo, dry_run=False) == []


def test_two_real_folders_give_one_line(repo):
    targets.set_agents({"claude": True, "codex": True})
    _real(repo, ".claude/skills", "pw")
    _real(repo, ".agents/skills", "pw")
    assert profiles.link_skills(repo, dry_run=False) == [
        "skill pw: .agents/skills/pw is not a link to .claude/skills/pw, left as is (Codex uses that one)"]


def test_claude_only_links_nothing_into_agents(repo):
    targets.set_agents({"claude": True, "codex": False})
    _real(repo, ".claude/skills", "pw")
    assert profiles.link_skills(repo, dry_run=False) == []
    assert not (repo / ".agents").exists()


def test_a_claude_folder_outside_the_repo_gets_one_line(repo, tmp_path):
    targets.set_agents({"claude": True, "codex": True})
    _real(repo, ".agents/skills", "notes")
    (tmp_path / "elsewhere").mkdir()
    (repo / ".claude").symlink_to(tmp_path / "elsewhere")
    lines = profiles.link_skills(repo, dry_run=False)
    assert len(lines) == 1 and lines[0].startswith("skills not linked:") and ".claude" in lines[0]
    assert list((tmp_path / "elsewhere").iterdir()) == []


def test_link_dry_run_names_the_link_and_writes_nothing(repo):
    targets.set_agents({"claude": True, "codex": True})
    _real(repo, ".agents/skills", "notes")
    assert profiles.link_skills(repo, dry_run=True) == [
        "would link skill notes for Claude Code -> .claude/skills/notes"]
    assert not (repo / ".claude").exists()


def test_profile_links_skills_with_claude_code_only(repo, fake_runner, monkeypatch):
    from loadout import project
    targets.set_agents({"claude": True, "codex": False})
    _real(repo, ".agents/skills", "notes")
    monkeypatch.setattr(profiles, "load_profile", lambda name: profiles.Profile(name="web", description=""))
    assert project.add_profile(repo, "web", install=False) == 0
    assert (repo / ".claude/skills/notes").is_symlink()
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_repo_follows_agents.py`
Expected: FAIL — `AttributeError: ... no attribute 'link_skills'`.

- [ ] **Step 3: Implement**

In `cli/loadout/profiles.py` add `import os` to the imports and, below `copy_skills`:

```python
AGENT_OF = {".claude/skills": "Claude Code", ".agents/skills": "Codex"}


def link_skills(project: Path, dry_run: bool) -> list[str]:
    """Link each repo skill into the skill folder of every other agent that is on (relative, so the link works in
    every clone): .claude/skills/NAME into .agents/skills for Codex, .agents/skills/NAME into .claude/skills for
    Claude Code (ADR 0027)."""
    from . import targets
    claude, agents = REPO_SKILLS
    out = []
    if targets.codex_enabled():
        out += _link_into(project, claude, agents, report=True)
    if targets.claude_enabled():
        out += _link_into(project, agents, claude, report=False)  # two real folders: the Codex direction says so
    return out


def _link_into(project: Path, src_rel: str, dest_rel: str, report: bool) -> list[str]:
    src_root, dest_root, agent = project / src_rel, project / dest_rel, AGENT_OF[dest_rel]
    if not src_root.is_dir():
        return []
    if not paths.inside(dest_root.parent, project) or not paths.inside(dest_root, project):
        top = dest_root.parent.name
        return [f"skills not linked: {dest_root} points outside {project} (a symlinked {top} or {top}/skills)"]
    out = []
    for entry in sorted(src_root.iterdir()):
        if entry.name.startswith(".") or not entry.is_dir():
            continue
        name, dest = entry.name, dest_root / entry.name
        if dest.exists() or dest.is_symlink():
            if os.path.realpath(dest) == os.path.realpath(entry):
                continue  # our link, or the other agent's link to this folder
            if report:
                out.append(f"skill {name}: {dest_rel}/{name} is not a link to {src_rel}/{name}, "
                           f"left as is ({agent} uses that one)")
            continue
        if dry_run:
            out.append(f"would link skill {name} for {agent} -> {dest_rel}/{name}")
            continue
        dest_root.mkdir(parents=True, exist_ok=True)
        try:
            os.symlink(f"../../{src_rel}/{name}", dest, target_is_directory=True)
        except OSError as exc:  # e.g. Windows without symlink rights
            out.append(f"skill {name}: not linked for {agent} ({exc.strerror or exc})")
            continue
        out.append(f"linked skill {name} for {agent} -> {dest_rel}/{name}")
    return out
```

In `cli/loadout/codex_project.py`: delete `def skills(...)` (the whole function) and change `apply`:

```python
def apply(prof: profiles.Profile, project: Path, install: bool, dry_run: bool) -> list[str]:
    lines = plugins(prof, dry_run) if install else []
    lines = config(prof, project, dry_run, skip=failed_plugins(prof, lines)) + lines  # skills: profiles.link_skills
```

(keep the rest of `apply` as is; drop `import os` there only if nothing else uses it).

In `cli/loadout/project.py` `add_profile`, right after `parts += [f"ran {what}" for what in ran]`:

```python
    links_ok = True
    for line in profiles.link_skills(project, dry_run):  # after the commands, which may install skills
        bad = "not linked" in line or "left as is" in line
        (warn if bad else info)(line)
        links_ok = links_ok and not bad
    if not links_ok:
        ok = False
```

and in the Codex block change `codex_ok = True` to `codex_ok = links_ok`.

In `tests/test_codex_project.py`, replace each `codex_project.skills(repo, dry_run=False)` with `profiles.link_skills(repo, dry_run=False)` and add `targets.set_agents({"claude": False, "codex": True})` as the first line of `test_repo_skills_are_linked_for_codex`, `test_a_symlinked_skills_folder_outside_the_repo_is_refused` and `test_a_different_skill_under_the_same_name_is_reported` (Codex only keeps the old single-direction expectations). In `test_failed_skill_links_make_profile_exit_1`, nothing changes.

- [ ] **Step 4: Run the tests**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_repo_follows_agents.py tests/test_codex_project.py tests/test_project.py`
Expected: all pass. Then grep for leftover callers: `grep -rn "codex_project.skills" cli tests` → nothing.

- [ ] **Step 5: Commit**

```bash
/usr/bin/git add cli/loadout/profiles.py cli/loadout/codex_project.py cli/loadout/project.py tests/test_codex_project.py tests/test_repo_follows_agents.py
/usr/bin/git commit -m "feat(profile): repo skills are linked both ways for the agents that are on"
```

### Task 3: `configure new skill --to repo` follows the agents

**Files:**
- Modify: `cli/loadout/new_skill.py` (`_repo`)
- Test: `tests/test_repo_follows_agents.py`

**Interfaces:**
- Consumes: `profiles.repo_skill_dirs`, `profiles.REPO_SKILLS` (Task 1).

- [ ] **Step 1: Write the failing tests** (append)

```python
def test_new_skill_codex_only_writes_agents_skills_and_no_claude(repo):
    from loadout import backup, new_skill
    targets.set_agents({"claude": False, "codex": True})
    lines = new_skill.create("notes", to="repo", cwd=repo, bk=backup.Backup(description="t"))
    assert (repo / ".agents/skills/notes/SKILL.md").is_file()
    assert not (repo / ".agents/skills/notes").is_symlink()
    assert not (repo / ".claude").exists()
    assert any(".agents/skills/notes/SKILL.md" in l.replace(os.sep, "/") for l in lines)


def test_new_skill_codex_only_refuses_a_name_in_claude_skills(repo):
    from loadout import backup, new_skill
    targets.set_agents({"claude": False, "codex": True})
    _real(repo, ".claude/skills", "notes")
    with pytest.raises(new_skill.Refused):
        new_skill.create("notes", to="repo", cwd=repo, bk=backup.Backup(description="t"))
    assert not (repo / ".agents").exists()
```

Before writing them, check `new_skill.create`'s real signature and return type in `cli/loadout/new_skill.py` and `tests/test_new_skill.py::test_repo_without_codex_writes_no_agents_link`; adapt the call (not the assertions' meaning) if it differs.

- [ ] **Step 2: Run them to see them fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_repo_follows_agents.py -k new_skill`
Expected: FAIL — the first writes `.claude/skills/notes`; the second creates `.agents/skills/notes` (no refusal), or passes only by accident of the old taken-check (then check it fails for the right reason after Step 3 by reverting temporarily).

- [ ] **Step 3: Implement** — in `_repo`, replace the two lines

```python
    src_root = root / ".claude" / "skills"
    dest_root = root / ".agents" / "skills" if targets.codex_enabled() else None
```

with

```python
    from . import profiles
    src_root, dest_root = profiles.repo_skill_dirs(root)  # the real folder, and the link folder (both agents on)
```

replace `_refuse_taken(name, [f for f in (src_root, dest_root) if f is not None])` with

```python
    _refuse_taken(name, [root / rel for rel in profiles.REPO_SKILLS])  # whatever is on: one skill per name
```

and leave the link step as is (`dest_root` is only set with both agents on, and then `src_root` is `.claude/skills`, so `../../.claude/skills/{name}` stays right). The home-folder refusal, the link refusal for `dest_root` and the inside/not-a-folder loop over `(src_root, dest_root)` stay unchanged.

- [ ] **Step 4: Run the tests**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_repo_follows_agents.py tests/test_new_skill.py tests/test_new_skill_cli.py`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
/usr/bin/git add cli/loadout/new_skill.py tests/test_repo_follows_agents.py
/usr/bin/git commit -m "feat(configure): new skill --to repo writes .agents/skills with Codex only"
```

### Task 4: No Claude Code files with Claude Code off

**Files:**
- Modify: `cli/loadout/profiles.py` (`apply_profile`, new `claude_off_notes`)
- Modify: `cli/loadout/project.py` (`add_profile` prints the notes)
- Modify: `cli/loadout/scaffold.py` (`scaffold`, `ensure_gitignore`)
- Test: `tests/test_repo_follows_agents.py`

**Interfaces:**
- Produces: `profiles.claude_off_notes(profile: Profile) -> list[str]`.

- [ ] **Step 1: Write the failing tests** (append)

```python
WEB = profiles.Profile(name="web", description="",
                       mcp={"mcpServers": {"x": {"command": "x"}}}, settings={"disabledMcpjsonServers": ["x"]})


def test_codex_only_profile_writes_no_claude_files_and_says_so(repo, fake_runner, monkeypatch, capsys):
    from loadout import codex_project, project
    targets.set_agents({"claude": False, "codex": True})
    monkeypatch.setattr(profiles, "load_profile", lambda name: WEB)
    monkeypatch.setattr(codex_project, "apply", lambda *a, **k: [])
    assert project.add_profile(repo, "web", install=False) == 0
    assert not (repo / ".claude").exists() and not (repo / ".mcp.json").exists()
    out = capsys.readouterr().out
    assert "Claude Code is off: .claude/settings.json not written (turn it on and run loadout profile web again)" in out
    assert "Claude Code is off: .mcp.json not written" in out


def test_turning_claude_code_on_then_profile_writes_them(repo, fake_runner, monkeypatch):
    from loadout import codex_project, project
    targets.set_agents({"claude": False, "codex": True})
    monkeypatch.setattr(profiles, "load_profile", lambda name: WEB)
    monkeypatch.setattr(codex_project, "apply", lambda *a, **k: [])
    project.add_profile(repo, "web", install=False)
    targets.set_agents({"claude": True, "codex": True})
    project.add_profile(repo, "web", install=False)
    assert (repo / ".mcp.json").is_file() and (repo / ".claude/settings.json").is_file()


def test_codex_only_init_writes_no_claude_md_and_no_claude_gitignore_line(repo):
    from loadout import scaffold
    targets.set_agents({"claude": False, "codex": True})
    created, _ = scaffold.scaffold(repo)
    assert repo / "CLAUDE.md" not in created and not (repo / "CLAUDE.md").exists()
    assert (repo / "AGENTS.md").is_file()
    assert scaffold.ensure_gitignore(repo) == [".serena/cache/"]


def test_both_on_init_is_unchanged(repo):
    from loadout import scaffold
    targets.set_agents({"claude": True, "codex": True})
    scaffold.scaffold(repo)
    assert (repo / "CLAUDE.md").is_file()
    assert scaffold.ensure_gitignore(repo) == scaffold.GITIGNORE_LINES
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_repo_follows_agents.py -k "claude_files or claude_code_on_then or init"`
Expected: FAIL — `.mcp.json` and `CLAUDE.md` are written.

- [ ] **Step 3: Implement**

`cli/loadout/profiles.py`:

```python
CLAUDE_FILES = (("settings", Path(".claude/settings.json")), ("mcp", Path(".mcp.json")))


def claude_off_notes(profile: Profile) -> list[str]:
    """With Claude Code off: one line per Claude Code file the profile would have written (ADR 0027)."""
    from . import targets
    if targets.claude_enabled():
        return []
    return [f"Claude Code is off: {rel.as_posix()} not written (turn it on and run loadout profile {profile.name} again)"
            for attr, rel in CLAUDE_FILES if getattr(profile, attr)]
```

and at the top of `apply_profile`'s body:

```python
    from . import targets
    if not targets.claude_enabled():
        return [], []  # claude_off_notes says what was not written
```

(also make the loop use `CLAUDE_FILES`: `for attr, rel in CLAUDE_FILES: overlay = getattr(profile, attr)`, keeping the rest of the loop).

`cli/loadout/project.py` `add_profile`, right after the `if dry_run: … else: …` block that applies the profile:

```python
    for line in profiles.claude_off_notes(prof):
        (steps.append if calm else info)(line)
```

`cli/loadout/scaffold.py`:

```python
def scaffold(project: Path, dry_run: bool = False) -> tuple[list[Path], list[str]]:
    from . import targets
    templates = paths.kit_root() / "templates" / "project"
    skip = set() if targets.claude_enabled() else {"CLAUDE.md"}  # Claude Code's file (ADR 0027)
    notes = []
    if (project / "CLAUDE.md").exists() and not (project / "AGENTS.md").exists():
        skip = {"AGENTS.md", "CLAUDE.md"}
        ...
```

and in `ensure_gitignore`:

```python
    from . import targets
    wanted = [l for l in GITIGNORE_LINES if targets.claude_enabled() or not l.startswith(".claude/")]
    ...
    missing = [line for line in wanted if line not in existing]
```

- [ ] **Step 4: Run the tests**

Run: `uv run --python 3.12 --with pytest pytest -q`
Expected: the whole suite passes (record the count).

- [ ] **Step 5: Commit**

```bash
/usr/bin/git add cli/loadout/profiles.py cli/loadout/project.py cli/loadout/scaffold.py tests/test_repo_follows_agents.py
/usr/bin/git commit -m "feat(profile): with Claude Code off, profile and init write no Claude Code files"
```

### Task 5: ADR 0027 and the docs

**Files:**
- Create: `docs/adr/0027-repo-files-follow-the-agents.md`
- Modify: `docs/adr/README.md`, `AGENTS.md` (ADR range `0001-0027`), `docs/reference/profile-format.md`, `docs/reference/cli.md`, `docs/how-to/write-a-profile.md`, `docs/how-to/uninstall.md`, `docs/how-to/undo-and-restore.md`, `docs/reference/personal-layer.md` (the `profiles/skills/<name>/` row)

- [ ] **Step 1:** Read `docs/explanation/documentation-strategy.md` section "ADRs: decisions with their reasons" and one existing ADR (`docs/adr/0026-tool-hints-never-block.md`) for the format.
- [ ] **Step 2:** Write ADR 0027 (Status: accepted, 2026-10-14). Context: Codex-only repos got Claude Code files (PR #35 thread 4265049172). Decision: the spec's §1 table and rules 1–3; with Claude Code off no `.claude/…`, `.mcp.json`, `CLAUDE.md` or `.claude/settings.local.json` ignore line. Why `.agents/skills` is the real folder with Codex only: Claude Code reads only `.claude/skills` but follows a link there (code.claude.com/docs/en/skills, "Symlinked folders"). Consequences: a rerun after turning an agent on adds its files; existing files are never moved; loadout keeps no list of repos. Supersedes the "With Codex only … still written" sentence of `profile-format.md`.
- [ ] **Step 3:** Update the docs listed above so each states the new rule once and links the ADR: `profile-format.md` (skills paragraph, "In Codex" table row and the replaced sentence), `cli.md` (`--to repo` row; the profile table "Profile skills" row), `write-a-profile.md` (what to commit, per agent), `uninstall.md` step 5 (also links in `.claude/skills` to `../../.agents/skills/NAME`), `undo-and-restore.md` (what a profile writes, per agent), `personal-layer.md` (`profiles/skills` row: copied into the repo's real skill folder).
- [ ] **Step 4:** Check every link you touched resolves (`grep -o '](\.\./[^)]*)' <file>` and test each path exists).
- [ ] **Step 5: Commit**

```bash
/usr/bin/git add docs AGENTS.md
/usr/bin/git commit -m "docs: repo files follow the agents that are on (ADR 0027)"
```
