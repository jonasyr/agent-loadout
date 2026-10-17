# Repo agents PR 3: skill links a checkout broke — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A committed skill link that Git checked out as a plain file (Git without symlinks, usually Windows without Developer Mode) is detected by `loadout check`, `init` and `profile`, reported as one problem with the fix, never repaired, and no longer makes `profile` exit 1; a test pins what Git stores for a link loadout creates.

**Architecture:** A small module `skill_links.py` finds the plain files (`git ls-files -s -z`, mode `120000`, working-tree entry is a regular file) and words the report. `profiles._link_into` skips those entries instead of reporting `left as is`; `link_skills` appends the report lines (prefix `skill links: `), which `project` shows as notes. `check` gets one warn row for the repo of the current folder. git runs only when a plain file sits where a link belongs, so ordinary runs make no extra command.

**Tech Stack:** Python 3.11+ standard library (`cli/loadout/`), pytest with `fake_home`/`fake_runner`; real `git` only in tests that build throwaway repos in `tmp_path` with the user's git config switched off.

**Spec:** `docs/superpowers/specs/2026-10-16-repo-agents-and-careful-ux-design.md`, Part 3 (and Part 5's Part 3 tests).

## Global Constraints

- Standard library only in `cli/loadout/`. External commands only through `runner.run` with argument lists.
- loadout prints the fix and runs none of it; it never replaces the plain files and never changes the user's git config ("Not in scope: Repairing links or changing a user's git config").
- Report wording (spec): `N skill links in .agents/skills are plain files in this checkout (Git without symlinks), so Codex does not see these skills`, then the fix: best, Codex in WSL with the repo in the Linux home; otherwise turn on Windows Developer Mode, `git config core.symlinks true`, `git checkout -- .agents/skills .claude/skills`.
- "Such entries no longer make `profile` exit 1; they are reported as this one problem."
- Tests never touch the real `~/.claude`, `~/.codex`, `~/.config/loadout`; real git in tests uses `GIT_CONFIG_GLOBAL`/`GIT_CONFIG_SYSTEM` = a null file and runs only inside `tmp_path`.
- Conventional Commits; no AI attribution.

## Review Focus

1. A real clone with `core.symlinks=false` of a repo whose `.agents/skills/NAME` is a committed link: `profile` exits 0, prints the one report, and the plain file keeps its bytes. Test in Task 2 (real git).
2. A plain file at a link's place that Git does not record as a link (the user's own file): still `left as is` and exit 1, as before. Test in Task 2.
3. A repo without git, git missing, or `git ls-files` failing: no crash, no report, behaviour as before. Test in Task 1.
4. `init` with two profiles in such a repo: the report appears once, not per profile. Test in Task 2.
5. `loadout check` from the home folder of a dotfiles repo: no row (`~/.claude/skills` is Claude Code's own folder there). Test in Task 3.

---

### Task 1: `skill_links.py`

**Files:**
- Create: `cli/loadout/skill_links.py`
- Test: `tests/test_skill_links.py`

**Interfaces:**
- Produces: `FOLDERS = (".claude/skills", ".agents/skills")`; `PREFIX = "skill links: "`; `plain_files(project: Path) -> set[str]` (repo-relative POSIX paths like `.agents/skills/demo`); `report(found: set[str]) -> list[str]` (empty for an empty set; otherwise one line per folder with entries, then one fix line; every line starts with `PREFIX`).

- [ ] **Step 1: Write the failing tests**

```python
"""Committed skill links a checkout turned into plain files (spec Part 3)."""
from loadout import runner, skill_links


def _repo(tmp_path):
    p = tmp_path / "repo"
    (p / ".git").mkdir(parents=True)
    (p / ".agents" / "skills").mkdir(parents=True)
    (p / ".claude" / "skills" / "demo").mkdir(parents=True)
    return p


def test_no_plain_file_means_no_git_call(tmp_path, fake_runner):
    p = _repo(tmp_path)
    (p / ".agents" / "skills" / "real").mkdir()
    assert skill_links.plain_files(p) == set() and fake_runner.calls == []


def test_a_plain_file_git_records_as_a_link_is_found(tmp_path, fake_runner):
    p = _repo(tmp_path)
    (p / ".agents" / "skills" / "demo").write_text("../../.claude/skills/demo")
    (p / ".agents" / "skills" / "mine").write_text("my notes")
    fake_runner.responses[("git",)] = runner.Result(
        0, "120000 abc 0\t.agents/skills/demo\0" "100644 def 0\t.agents/skills/mine\0", "")
    assert skill_links.plain_files(p) == {".agents/skills/demo"}
    assert fake_runner.calls[0][:3] == ["git", "-C", str(p)] and "-z" in fake_runner.calls[0]


def test_git_failing_or_no_repo_finds_nothing(tmp_path, fake_runner):
    p = _repo(tmp_path)
    (p / ".agents" / "skills" / "demo").write_text("../../.claude/skills/demo")
    fake_runner.responses[("git",)] = runner.Result(128, "", "fatal: not a git repository")
    assert skill_links.plain_files(p) == set()
    (p / ".git").rmdir()
    assert skill_links.plain_files(p) == set()


def test_the_report_counts_per_folder_and_names_the_fix():
    lines = skill_links.report({".agents/skills/a", ".agents/skills/b", ".claude/skills/c"})
    assert lines[0] == ("skill links: 1 skill link in .claude/skills is a plain file in this checkout (Git without "
                        "symlinks), so Claude Code does not see this skill")
    assert lines[1] == ("skill links: 2 skill links in .agents/skills are plain files in this checkout (Git without "
                        "symlinks), so Codex does not see these skills")
    assert "git config core.symlinks true" in lines[2]
    assert "git checkout -- .claude/skills .agents/skills" in lines[2] and "Developer Mode" in lines[2]
    assert all(l.startswith(skill_links.PREFIX) for l in lines)


def test_the_fix_names_only_the_folders_with_plain_files():
    assert "git checkout -- .agents/skills`" in skill_links.report({".agents/skills/a"})[-1]
    assert skill_links.report(set()) == []
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_skill_links.py`
Expected: FAIL (`cannot import name 'skill_links'`).

- [ ] **Step 3: Write the module**

```python
"""Committed skill links a checkout turned into plain files (Git without symlinks, e.g. Windows without Developer
Mode): found and reported with the fix, never repaired (spec Part 3)."""
from __future__ import annotations

from pathlib import Path

from . import runner

FOLDERS = (".claude/skills", ".agents/skills")
AGENT = {".claude/skills": "Claude Code", ".agents/skills": "Codex"}
PREFIX = "skill links: "


def _candidates(project: Path) -> set[str]:
    """Regular files where a skill folder or link belongs."""
    out = set()
    for folder in FOLDERS:
        root = project / folder
        try:
            entries = list(root.iterdir()) if root.is_dir() and not root.is_symlink() else []
        except OSError:
            continue
        out.update(f"{folder}/{e.name}" for e in entries if e.is_file() and not e.is_symlink())
    return out


def plain_files(project: Path) -> set[str]:
    """The candidates Git records as links (mode 120000): a checkout without symlinks wrote them as files. git runs
    only when there is a candidate; without git, a repo or a readable index the answer is none."""
    candidates = _candidates(project)
    if not candidates or not (project / ".git").exists():
        return set()
    res = runner.run(["git", "-C", str(project), "ls-files", "-s", "-z", "--", *FOLDERS], timeout=20)
    if not res.ok:
        return set()
    linked = set()
    for record in res.stdout.split("\0"):
        meta, _, path = record.partition("\t")
        if meta.split(" ")[0] == "120000":
            linked.add(path)
    return candidates & linked


def report(found: set[str]) -> list[str]:
    lines, folders = [], []
    for folder in FOLDERS:
        n = sum(1 for p in found if p.startswith(folder + "/"))
        if not n:
            continue
        folders.append(folder)
        many = n != 1
        lines.append(f"{PREFIX}{n} skill link{'s' if many else ''} in {folder} {'are plain files' if many else 'is a plain file'} "
                     f"in this checkout (Git without symlinks), so {AGENT[folder]} does not see "
                     f"{'these skills' if many else 'this skill'}")
    if lines:
        lines.append(f"{PREFIX}fix: best, use Codex in WSL with the repo in the Linux home (docs/how-to/wsl.md); "
                     "otherwise turn on Windows Developer Mode, then in the repo run `git config core.symlinks true` "
                     f"and `git checkout -- {' '.join(folders)}`. loadout runs none of these and never replaces the files")
    return lines
```

- [ ] **Step 4: Run them to see them pass**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_skill_links.py`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add cli/loadout/skill_links.py tests/test_skill_links.py
git commit -m "feat(repo): find committed skill links a checkout turned into plain files"
```

---

### Task 2: `profile` and `init` report them and no longer fail on them

**Files:**
- Modify: `cli/loadout/profiles.py` (`link_skills`, `_link_into`)
- Modify: `cli/loadout/project.py` (`_plan_profile`, `_after_apply`, `_profile_now`, `init`)
- Test: `tests/test_broken_skill_links.py`

**Interfaces:**
- Consumes: Task 1 `skill_links.plain_files`, `report`, `PREFIX`.
- Produces: `link_skills` returns the report lines (each starts with `skill links: `) after its own lines; `_link_into` never reports `left as is` for an entry in `plain_files`.

- [ ] **Step 1: Write the failing tests**

```python
"""A checkout without symlinks: profile and init report the plain files once and exit 0 (spec Part 3).
Real git in throwaway repos; the user's git config is switched off."""
import os
import shutil
import subprocess

import pytest

from loadout import profiles, project, targets

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")


def git(cwd, *args):
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout


@pytest.fixture
def clone(fake_home, tmp_path, monkeypatch):
    """A both-agents repo with a committed .agents/skills/demo link, cloned with core.symlinks=false."""
    origin = tmp_path / "origin"
    (origin / ".claude" / "skills" / "demo").mkdir(parents=True)
    (origin / ".claude" / "skills" / "demo" / "SKILL.md").write_text("---\nname: demo\n---\n")
    (origin / ".agents" / "skills").mkdir(parents=True)
    try:
        os.symlink(os.path.join("..", "..", ".claude", "skills", "demo"), origin / ".agents" / "skills" / "demo",
                   target_is_directory=True)
    except OSError:
        pytest.skip("no symlink rights here")
    (origin / ".loadout.json").write_text('{\n  "agents": [\n    "claude",\n    "codex"\n  ]\n}\n')
    git(origin, "init", "-q")
    git(origin, "-c", "core.symlinks=true", "add", "-A")
    git(origin, "commit", "-qm", "init")
    dest = tmp_path / "clone"
    git(tmp_path, "-c", "core.symlinks=false", "clone", "-q", str(origin), str(dest))
    assert (dest / ".agents" / "skills" / "demo").is_file()
    targets.set_agents({"claude": True, "codex": True})
    monkeypatch.setattr(profiles, "load_profile", lambda n: profiles.Profile(name=n, description="d", settings={"x": 1}))
    return dest


def test_profile_reports_the_plain_file_once_and_exits_0(clone, capsys):
    before = (clone / ".agents" / "skills" / "demo").read_bytes()
    assert project.add_profile(clone, "web", install=False, approve=lambda plan: True) == 0
    printed = capsys.readouterr().out
    assert printed.count("1 skill link in .agents/skills is a plain file") == 1
    assert "core.symlinks true" in printed and "left as is" not in printed
    assert (clone / ".agents" / "skills" / "demo").read_bytes() == before


def test_init_with_two_profiles_reports_it_once(clone, capsys):
    assert project.init(clone, ["a", "b"], yes=True, install=False, dry_run=False, ask=lambda q: "",
                        interactive=False) == 0
    assert capsys.readouterr().out.count("is a plain file in this checkout") == 1


def test_the_library_path_reports_it_too(clone, capsys):
    assert project.add_profile(clone, "web", install=False) == 0
    assert "is a plain file in this checkout" in capsys.readouterr().out


def test_a_plain_file_git_does_not_record_as_a_link_still_fails(clone, capsys):
    mine = clone / ".agents" / "skills" / "other"
    (clone / ".claude" / "skills" / "other").mkdir()
    mine.write_text("my own file")
    assert project.add_profile(clone, "web", install=False, approve=lambda plan: True) == 1
    assert "left as is" in capsys.readouterr().out and mine.read_text() == "my own file"
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_broken_skill_links.py`
Expected: FAIL (exit 1 and `left as is` for the clone; no report line).

- [ ] **Step 3: Skip the plain files in `_link_into` and report them in `link_skills`**

In `cli/loadout/profiles.py`, `link_skills`, replace the final `return out` with:

```python
    from . import skill_links
    return out + skill_links.report(skill_links.plain_files(project))
```

In `_link_into`, before `out = []`, add `broken = None`, and replace

```python
            if ours or reverse:
                continue  # our link, or the entry is the other agent's link to this real folder
```

with

```python
            if ours or reverse:
                continue  # our link, or the entry is the other agent's link to this real folder
            if dest.is_file() and not dest.is_symlink():
                if broken is None:
                    from . import skill_links
                    broken = skill_links.plain_files(project)
                if f"{dest_rel}/{name}" in broken:
                    continue  # a committed link this checkout wrote as a file: link_skills reports it once
```

- [ ] **Step 4: Show the report as notes in `project.py`**

In `_plan_profile`, replace

```python
    failures += [l for l in profiles.link_skills(project, False, w=w) if "not linked" in l or "left as is" in l]
```

with

```python
    from . import skill_links
    links = profiles.link_skills(project, False, w=w)
    failures += [l for l in links if "not linked" in l or "left as is" in l]
    notes += [l for l in links if l.startswith(skill_links.PREFIX)]
```

In `_after_apply`, after `problems += [l for l in late if "not linked" in l or "left as is" in l]` add:

```python
    from . import skill_links
    notes += [l for l in late if l.startswith(skill_links.PREFIX) and l not in notes]
```

In `_profile_now`, in the `for line in profiles.link_skills(project, dry_run, w=w):` loop, replace `(warn if bad else info)(line)` with:

```python
        from . import skill_links
        if line.startswith(skill_links.PREFIX):
            (steps.append if calm else info)(line)
            continue
        (warn if bad else info)(line)
```

In `init`, the report must appear once: replace `notes += planned_notes` inside the profiles loop with

```python
            notes += [n for n in planned_notes if not (n.startswith(skill_links.PREFIX) and n in notes)]
```

and add `from . import skill_links` at the top of `init`. After the profiles loop (still inside the `pending` block), so that `init` without profiles reports it too, add:

```python
        notes += [l for l in skill_links.report(skill_links.plain_files(project)) if l not in notes]
```

Check where `_profile_now` prints `steps` in calm mode (they must reach the user); if `steps` are printed through `out.problem`, the report passes through `printable` with line breaks kept.

- [ ] **Step 5: Run the tests**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_broken_skill_links.py tests/test_skill_links.py`
Expected: PASS. If `test_the_library_path_reports_it_too` fails because calm `steps` are not printed for a run without problems, print them the way the trust note is printed (read `_profile_now`'s end) and ledger it.

- [ ] **Step 6: Whole suite, then commit**

Run: `uv run --python 3.12 --with pytest pytest -q > "$WS/suite2.txt" 2>&1; echo rc=$?; tail -5 "$WS/suite2.txt"`
Expected: rc=0. A test that asserted `left as is` for a plain file without git behind it still passes (Review Focus 2); any other failure: systematic-debugging.

```bash
git add cli/loadout/profiles.py cli/loadout/project.py tests/test_broken_skill_links.py
git commit -m "feat(profile): skill links a checkout turned into plain files are reported once, not a failure"
```

---

### Task 3: the `loadout check` row

**Files:**
- Modify: `cli/loadout/check.py` (`_repo_skill_links`, `run_checks`)
- Test: `tests/test_check_skill_links.py`

**Interfaces:**
- Consumes: Task 1 `plain_files`, `report`, `PREFIX`; `new_skill.repo_root(start)`.
- Produces: `check._repo_skill_links() -> list[CheckResult]`: no row without a finding; one `warn` row named `repo skill links` otherwise.

- [ ] **Step 1: Write the failing tests**

```python
"""loadout check names skill links a checkout turned into plain files (spec Part 3)."""
from loadout import check, runner


def _repo(tmp_path):
    p = tmp_path / "repo"
    (p / ".git").mkdir(parents=True)
    (p / ".agents" / "skills").mkdir(parents=True)
    (p / ".agents" / "skills" / "demo").write_text("../../.claude/skills/demo")
    return p


def test_check_warns_once_with_the_fix(tmp_path, fake_home, fake_runner, monkeypatch):
    p = _repo(tmp_path)
    (p / "sub").mkdir()
    monkeypatch.chdir(p / "sub")
    fake_runner.responses[("git",)] = runner.Result(0, "120000 abc 0\t.agents/skills/demo\0", "")
    rows = check._repo_skill_links()
    assert len(rows) == 1 and rows[0].severity == "warn" and not rows[0].ok
    assert "1 skill link in .agents/skills is a plain file" in rows[0].detail and str(p) in rows[0].detail
    assert "core.symlinks true" in rows[0].fix and not rows[0].fix.startswith("skill links: ")


def test_no_row_without_a_finding_or_outside_a_repo(tmp_path, fake_home, fake_runner, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert check._repo_skill_links() == []
    p = _repo(tmp_path)
    monkeypatch.chdir(p)
    assert check._repo_skill_links() == []  # git (fake) lists no link


def test_no_row_in_a_home_dotfiles_repo(fake_home, fake_runner, monkeypatch):
    (fake_home / ".git").mkdir()
    (fake_home / ".agents" / "skills").mkdir(parents=True)
    (fake_home / ".agents" / "skills" / "demo").write_text("x")
    fake_runner.responses[("git",)] = runner.Result(0, "120000 abc 0\t.agents/skills/demo\0", "")
    monkeypatch.chdir(fake_home)
    assert check._repo_skill_links() == []


def test_run_checks_includes_the_row(tmp_path, fake_home, fake_runner, monkeypatch):
    p = _repo(tmp_path)
    monkeypatch.chdir(p)
    fake_runner.responses[("git", "-C", str(p), "ls-files")] = runner.Result(0, "120000 abc 0\t.agents/skills/demo\0", "")
    assert any(r.name == "repo skill links" for r in check.run_checks())
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_check_skill_links.py`
Expected: FAIL (`module 'loadout.check' has no attribute '_repo_skill_links'`).

- [ ] **Step 3: Implement**

In `cli/loadout/check.py`, after `_repos`:

```python
def _repo_skill_links() -> list[CheckResult]:
    """The repo of the current folder: committed skill links this checkout wrote as plain files (spec Part 3)."""
    from . import skill_links
    from .new_skill import repo_root
    root = repo_root(Path(os.path.abspath(Path.cwd())))
    if root is None or Path(os.path.realpath(root)) == Path(os.path.realpath(paths.home())):
        return []  # outside a repo, or a dotfiles repo in the home folder (.claude/skills there is Claude Code's own)
    lines = skill_links.report(skill_links.plain_files(root))
    if not lines:
        return []
    text = [l[len(skill_links.PREFIX):] for l in lines]
    return [CheckResult("repo skill links", False, f"{root}: " + "; ".join(text[:-1]),
                        text[-1].removeprefix("fix: "), "warn")]
```

In `run_checks`, append `*_repo_skill_links()` after `*_repos()`.

- [ ] **Step 4: Run them to see them pass**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_check_skill_links.py tests/test_check.py`
Expected: PASS. If `test_check.py` has a test that compares the full list of row names, add `repo skill links` only where a finding exists (it has none there), so nothing should change; if one does, read it before changing it.

- [ ] **Step 5: Whole suite, then commit**

Run: `uv run --python 3.12 --with pytest pytest -q > "$WS/suite3.txt" 2>&1; echo rc=$?; tail -5 "$WS/suite3.txt"`
Expected: rc=0.

```bash
git add cli/loadout/check.py tests/test_check_skill_links.py
git commit -m "feat(check): warn about skill links this checkout wrote as plain files"
```

---

### Task 4: what Git stores for a link loadout creates

**Files:**
- Test: `tests/test_skill_link_target.py`
- Modify (only if CI shows `\`): `cli/loadout/profiles.py` (`_link_into`), after asking the user

**Interfaces:**
- Consumes: `profiles.link_skills(project, dry_run=False)` (creates links with `os.symlink`).

- [ ] **Step 1: Write the test**

```python
"""What Git stores for a skill link loadout creates (spec Part 3): every clone, on every platform, must get a target
with forward slashes. Runs on the Linux, Windows and WSL CI runners."""
import os
import shutil
import subprocess

import pytest

from loadout import profiles, targets

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")


def git(cwd, *args):
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
    return subprocess.run(["git", "-c", "core.symlinks=true", *args], cwd=cwd, env=env, check=True,
                          capture_output=True, text=True).stdout


def test_git_stores_the_link_target_with_forward_slashes(fake_home, tmp_path):
    repo = tmp_path / "repo"
    (repo / ".claude" / "skills" / "demo").mkdir(parents=True)
    (repo / ".claude" / "skills" / "demo" / "SKILL.md").write_text("---\nname: demo\n---\n")
    (repo / ".loadout.json").write_text('{\n  "agents": [\n    "claude",\n    "codex"\n  ]\n}\n')
    git(repo, "init", "-q")
    targets.set_agents({"claude": True, "codex": True})
    lines = profiles.link_skills(repo, False)
    if any("not linked" in l for l in lines):
        pytest.skip(f"no symlink rights here: {lines}")
    git(repo, "add", "-A")
    mode, sha = git(repo, "ls-files", "-s", "--", ".agents/skills/demo").split()[:2]
    assert mode == "120000"
    assert git(repo, "cat-file", "-p", sha) == "../../.claude/skills/demo"
```

- [ ] **Step 2: Run it locally**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_skill_link_target.py`
Expected: PASS on Linux (it pins `/` here). It never ran before this task because the test is new; it would fail if `link_skills` built the target with another separator (check by reading `_link_into`'s `want`).

- [ ] **Step 3: Commit; the Windows answer comes from CI on the PR**

```bash
git add tests/test_skill_link_target.py
git commit -m "test(repo): pin the link target Git stores for a repo skill link"
```

If the Windows CI job fails this test with a `\` in the stored target, stop and ask the user before changing `_link_into`: `_link_into` builds the target with `os.path.join` because "Windows resolves only its own separator" (the comment there), so switching to `/` trades a working local link for a portable stored one, and that trade is the user's to make.

---

### Task 5: docs

**Files:**
- Modify: `docs/how-to/troubleshooting.md`, `docs/how-to/setups.md`, `docs/reference/cli.md`

- [ ] **Step 1: Write the rows**

- `docs/how-to/troubleshooting.md`: in the section about repos (find it with `grep -n '^## ' docs/how-to/troubleshooting.md`; else the Codex section), add the row:
  `| \`N skill links in .agents/skills are plain files in this checkout (Git without symlinks)\` | Git checked the repo's skill links out as files (Windows without Developer Mode), so the agent does not see those skills. Best: use Codex in WSL with the repo in the Linux home ([WSL 2](wsl.md)). Otherwise turn on Windows Developer Mode, run \`git config core.symlinks true\` and \`git checkout -- .agents/skills .claude/skills\` in the repo. loadout reports this in \`loadout check\`, \`init\` and \`profile\` and changes nothing. |`
- `docs/how-to/setups.md`: in the second table, after the row "A repo shared with people who use the other agent", add:
  `| A repo shared with a teammate on Windows | The same as above. If the teammate's Git has no symlinks (Windows without Developer Mode), the committed skill links arrive as plain files. | Reports it once, with the fix, in \`loadout check\`, \`init\` and \`profile\`; never replaces the files ([Troubleshooting](troubleshooting.md)). |`
- `docs/reference/cli.md`: in the init/profile exit-code paragraph, after "(`not linked`, `left as is`)", add: "A committed skill link that this checkout wrote as a plain file (Git without symlinks) is not a problem: it is reported once with the fix." In the `loadout check` section, add one sentence: "Inside a git repo, a `repo skill links` warning names committed skill links that the checkout wrote as plain files, with the fix (loadout changes nothing)."

- [ ] **Step 2: Suite and validation**

Run: `uv run --python 3.12 --with pytest pytest -q > "$WS/suite5.txt" 2>&1; echo rc=$?; tail -3 "$WS/suite5.txt"; claude plugin validate . && claude plugin validate plugins/loadout`
Expected: rc=0; both validations pass.

- [ ] **Step 3: Commit**

```bash
git add docs
git commit -m "docs(repo): skill links a checkout turned into plain files"
```
