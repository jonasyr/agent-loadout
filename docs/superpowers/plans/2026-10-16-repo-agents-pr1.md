# Repo agents, PR 1: preview, undo and the repo's agent choice — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every repo write by `loadout init`, `loadout profile` and `loadout configure new skill --to repo` is shown as a plan, applied only after a yes (or `--yes`), backed up and undoable with `loadout restore`; a committed `.loadout.json` decides which agents' files a repo gets and can switch loadout off for the repo (`manage: false`).

**Architecture:** A collector (`repo_writes.RepoWrites`) replaces direct file writes in the repo writers: in plan mode it records `Change`s, renders them, and later applies exactly those changes with a `Backup` that records the repo. The existing writer functions keep their signatures and write immediately when no collector is passed (library callers and old tests). `repo_config` reads and writes `.loadout.json`; the writers ask it for the repo's agents instead of `targets`. Repo JSON is rewritten only when loadout can reproduce the file's exact layout (`jsonio.json_style`).

**Tech Stack:** Python 3.11+ standard library (`json`, `difflib`, `shutil`, `os`), pytest.

**Spec:** `docs/superpowers/specs/2026-10-16-repo-agents-and-careful-ux-design.md` (Parts 0, 1, 7). Docs baseline: `docs/superpowers/plans/2026-10-16-repo-agents-docs-baseline.md`.

**Scope ruling:** `loadout explain <file>` (Part 0) needs the per-profile record that PR 2 adds to `.loadout.json`; it moves to PR 2. Profile `why` texts: PR 1 adds the optional field and renders it; the kit profiles get their texts in this PR (five files).

## Global Constraints

- Python 3.11+, standard library only in `cli/loadout/`.
- Tests use the `fake_home` and `fake_runner` fixtures; never the real `~/.claude`, `~/.claude.json`, `~/.codex` or `~/.config/loadout`. No real installers, no mutating `claude`/`codex` commands.
- External commands only through `runner.run` with argument lists.
- No plaintext secret in output: every rendered plan line goes through `secrets.redact`.
- Text the user wrote stays byte for byte; a write that can change or lose user entries is P1. Every destructive change is undoable.
- Conventional Commits; no Co-Authored-By or AI attribution. Use `/usr/bin/git`.
- Tests: `uv run --python 3.12 --with pytest pytest -q`.
- Spec values: file name `.loadout.json`; keys `agents` (list of `"claude"`, `"codex"`), `manage` (bool, default true); invalid file message starts `.loadout.json: `; the question `Apply these changes? [y/N]`; the manage header `manage is false in .loadout.json: nothing written`; the undo line `undo: loadout restore <dir>`.

## Review Focus

1. A `.loadout.json` that is a link leading outside the repo, unreadable, not an object, or with a bad `agents`/`manage` value: refused with its reason before any change (Task 2 tests).
2. A repo JSON file indented with 4 spaces or a tab, or with CRLF endings: after a profile run only the new keys differ, the rest byte for byte; a file in any other layout (compact arrays, comments) is left untouched and its entries printed (Tasks 1 and 4 tests).
3. A declined plan (`n`, Enter, or EOF from a closed stdin): nothing written, nothing run, exit 0 (Task 5 test).
4. Restore after `init` created `.claude/` and `docs/`: those folders go; a folder that existed before with the user's files stays with them (Task 3 test).
5. A Codex-only user in a repo whose `.loadout.json` names both agents: Claude Code's repo files are written, `claude plugin install` is not run, one line says why (Task 5 test).

---

### Task 1: Format-preserving JSON

**Files:**
- Modify: `cli/loadout/jsonio.py` (append after `save_json`)
- Test: `tests/test_json_style.py`

**Interfaces:**
- Produces: `json_style(text: str) -> JsonStyle | None`; `JsonStyle(indent: int | str, newline: str, final_newline: bool)`; `dumps_like(style: JsonStyle, data) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
"""Repo JSON is rewritten only in the exact layout it already has (spec Part 0)."""
import json

import pytest

from loadout.jsonio import dumps_like, json_style


@pytest.mark.parametrize("indent", [2, 4, "\t"])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_a_standard_layout_round_trips(indent, newline):
    data = {"b": 1, "a": {"x": [1, 2]}, "s": "ü"}
    text = (json.dumps(data, indent=indent, ensure_ascii=False) + "\n").replace("\n", newline)
    style = json_style(text)
    assert style is not None and dumps_like(style, json.loads(text)) == text


def test_new_keys_keep_the_style():
    text = '{\r\n    "a": 1\r\n}\r\n'
    style = json_style(text)
    assert dumps_like(style, {"a": 1, "b": [True]}) == '{\r\n    "a": 1,\r\n    "b": [\r\n        true\r\n    ]\r\n}\r\n'


def test_no_final_newline_is_kept():
    assert dumps_like(json_style('{\n  "a": 1\n}'), {"a": 2}) == '{\n  "a": 2\n}'


@pytest.mark.parametrize("text", [
    '{"a": [1, 2]}\n',                 # compact
    '{\n  "a": 1, "b": 2\n}\n',        # hand layout
    '{\n  // note\n  "a": 1\n}\n',     # comments (JSONC)
    '{\n  "a": 1\r\n}\n',              # mixed line endings
    'not json',
])
def test_any_other_layout_is_not_rewritten(text):
    assert json_style(text) is None


def test_an_empty_file_has_no_style():
    assert json_style("") is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_json_style.py`
Expected: FAIL with `ImportError: cannot import name 'dumps_like'`.

- [ ] **Step 3: Implement**

Append to `cli/loadout/jsonio.py` (it already imports `json`; add `from dataclasses import dataclass` at the top if missing):

```python
@dataclass(frozen=True)
class JsonStyle:
    indent: int | str
    newline: str
    final_newline: bool


def json_style(text: str) -> JsonStyle | None:
    """The layout of `text` when it is exactly what json.dumps(indent=2, 4 or a tab) writes, with one kind of line
    ending; None for any other layout, which loadout then never rewrites (the user's bytes stay theirs)."""
    newline = "\r\n" if "\r\n" in text else "\n"
    body = text.replace("\r\n", "\n")
    if newline == "\r\n" and body.count("\n") != text.count("\r\n"):  # mixed endings
        return None
    final = body.endswith("\n")
    core = body[:-1] if final else body
    try:
        data = json.loads(core)
    except ValueError:
        return None
    for indent in (2, 4, "\t"):
        if json.dumps(data, indent=indent, ensure_ascii=False) == core:
            return JsonStyle(indent, newline, final)
    return None


def dumps_like(style: JsonStyle, data) -> str:
    text = json.dumps(data, indent=style.indent, ensure_ascii=False) + ("\n" if style.final_newline else "")
    return text.replace("\n", style.newline)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_json_style.py`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
/usr/bin/git add cli/loadout/jsonio.py tests/test_json_style.py
/usr/bin/git commit -m "feat(jsonio): rewrite JSON only in the exact layout it already has"
```

---

### Task 2: `.loadout.json`, the repo's agent choice

**Files:**
- Create: `cli/loadout/repo_config.py`
- Test: `tests/test_repo_config.py`

**Interfaces:**
- Consumes: `jsonio.json_style`, `jsonio.dumps_like` (Task 1); `targets.claude_enabled()`, `targets.codex_enabled()`; `paths.inside`.
- Produces:
  - `FILE = ".loadout.json"`; `class Invalid(ValueError)`.
  - `RepoConfig(agents: frozenset[str] | None, manage: bool, data: dict, exists: bool)`.
  - `load(project: Path) -> RepoConfig` (raises `Invalid`).
  - `agents(project: Path) -> dict[str, bool]`: `{"claude": bool, "codex": bool}` from the file, else the user's agents.
  - `user_agents() -> dict[str, bool]`.
  - `new_text(project: Path, agents: frozenset[str]) -> str | None`: the file's new text with `agents` set (other keys kept), `None` when it would not change; raises `Invalid` when the existing file is in a layout loadout does not rewrite.
  - `parse_agents(value: str) -> frozenset[str]` for `--agents` (raises `ValueError`).

- [ ] **Step 1: Write the failing tests**

```python
"""`.loadout.json`: which agents a repo is for, and whether loadout may write there (spec Part 1)."""
import os

import pytest

from loadout import repo_config, targets


@pytest.fixture
def repo(fake_home, tmp_path):
    p = tmp_path / "repo"
    (p / ".git").mkdir(parents=True)
    return p


def test_without_the_file_the_users_agents_decide(repo):
    targets.set_agents({"claude": True, "codex": False})
    cfg = repo_config.load(repo)
    assert cfg.exists is False and cfg.agents is None and cfg.manage is True
    assert repo_config.agents(repo) == {"claude": True, "codex": False}


def test_the_file_wins_over_the_users_agents(repo):
    targets.set_agents({"claude": True, "codex": True})
    (repo / ".loadout.json").write_text('{\n  "agents": [\n    "codex"\n  ]\n}\n')
    assert repo_config.agents(repo) == {"claude": False, "codex": True}


def test_manage_false_is_read(repo):
    (repo / ".loadout.json").write_text('{"manage": false}')
    assert repo_config.load(repo).manage is False


@pytest.mark.parametrize("text, word", [
    ('{"agents": "codex"}', "agents"),
    ('{"agents": []}', "agents"),
    ('{"agents": ["codex", "codex"]}', "agents"),
    ('{"agents": ["cursor"]}', "agents"),
    ('{"manage": "no"}', "manage"),
    ('[1]', "object"),
    ('{', "parse"),
])
def test_an_invalid_file_is_refused_with_its_reason(repo, text, word):
    (repo / ".loadout.json").write_text(text)
    with pytest.raises(repo_config.Invalid) as exc:
        repo_config.load(repo)
    assert str(exc.value).startswith(".loadout.json: ") and word in str(exc.value)


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink")
def test_a_link_leading_outside_the_repo_is_refused(repo, tmp_path):
    outside = tmp_path / "elsewhere.json"
    outside.write_text('{"agents": ["codex"]}')
    (repo / ".loadout.json").symlink_to(outside)
    with pytest.raises(repo_config.Invalid, match="outside"):
        repo_config.load(repo)


def test_new_text_creates_and_keeps_other_keys(repo):
    assert repo_config.new_text(repo, frozenset({"codex", "claude"})) == '{\n  "agents": [\n    "claude",\n    "codex"\n  ]\n}\n'
    (repo / ".loadout.json").write_text('{\r\n    "team": "x",\r\n    "agents": [\r\n        "codex"\r\n    ]\r\n}\r\n')
    assert repo_config.new_text(repo, frozenset({"codex"})) is None
    assert repo_config.new_text(repo, frozenset({"claude", "codex"})) == (
        '{\r\n    "team": "x",\r\n    "agents": [\r\n        "claude",\r\n        "codex"\r\n    ]\r\n}\r\n')


def test_new_text_refuses_a_hand_laid_out_file(repo):
    (repo / ".loadout.json").write_text('{"agents": ["codex"], "team": "x"}\n')
    with pytest.raises(repo_config.Invalid, match="by hand"):
        repo_config.new_text(repo, frozenset({"claude", "codex"}))


@pytest.mark.parametrize("value, want", [
    ("codex", {"codex"}), ("claude,codex", {"claude", "codex"}), (" Codex , claude ", {"claude", "codex"}),
])
def test_parse_agents(value, want):
    assert repo_config.parse_agents(value) == frozenset(want)


@pytest.mark.parametrize("value", ["", "cursor", "codex,", ","])
def test_parse_agents_refuses(value):
    with pytest.raises(ValueError, match="--agents"):
        repo_config.parse_agents(value)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_repo_config.py`
Expected: FAIL with `ImportError: cannot import name 'repo_config'`.

- [ ] **Step 3: Implement `cli/loadout/repo_config.py`**

```python
"""`.loadout.json` in a repo: which agents the repo is for, and whether loadout may write there (ADR 0030)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import paths
from .jsonio import dumps_like, json_style

FILE = ".loadout.json"
AGENTS = ("claude", "codex")


class Invalid(ValueError):
    """The repo's .loadout.json cannot be used; the message starts with `.loadout.json: `."""


@dataclass
class RepoConfig:
    agents: frozenset | None = None
    manage: bool = True
    data: dict = field(default_factory=dict)
    exists: bool = False


def _path(project: Path) -> Path:
    return project / FILE


def load(project: Path) -> RepoConfig:
    path = _path(project)
    if not (path.exists() or path.is_symlink()):
        return RepoConfig()
    if not paths.inside(path, project):
        raise Invalid(f"{FILE}: it is a link that leads outside the repo; make it a plain file")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise Invalid(f"{FILE}: cannot read it ({exc.strerror or exc})") from None
    except (UnicodeDecodeError, ValueError) as exc:
        raise Invalid(f"{FILE}: does not parse ({exc}); fix it, then run this again") from None
    if not isinstance(data, dict):
        raise Invalid(f"{FILE}: must be a JSON object")
    agents = data.get("agents")
    if agents is not None:
        if (not isinstance(agents, list) or not agents or len(set(agents)) != len(agents)
                or not all(a in AGENTS for a in agents)):
            raise Invalid(f'{FILE}: agents must be a list of "claude" and "codex" (each once)')
        agents = frozenset(agents)
    manage = data.get("manage", True)
    if not isinstance(manage, bool):
        raise Invalid(f"{FILE}: manage must be true or false")
    return RepoConfig(agents, manage, data, True)


def user_agents() -> dict:
    from . import targets
    return {"claude": targets.claude_enabled(), "codex": targets.codex_enabled()}


def agents(project: Path) -> dict:
    """The repo's agents from .loadout.json, else the user's (a repo nobody chose for)."""
    chosen = load(project).agents
    if chosen is None:
        return user_agents()
    return {a: a in chosen for a in AGENTS}


def parse_agents(value: str) -> frozenset:
    parts = [p.strip().lower() for p in (value or "").split(",")]
    if not parts or any(p not in AGENTS for p in parts):
        raise ValueError("--agents: give claude, codex or claude,codex")
    return frozenset(parts)


def new_text(project: Path, chosen: frozenset) -> str | None:
    """The file's text with `agents` set to `chosen` (its other keys kept), or None when nothing changes."""
    cfg = load(project)
    ordered = [a for a in AGENTS if a in chosen]
    if cfg.exists and cfg.agents == frozenset(chosen):
        return None
    if not cfg.exists:
        return json.dumps({"agents": ordered}, indent=2) + "\n"
    style = json_style(_path(project).read_text(encoding="utf-8"))
    if style is None:
        raise Invalid(f'{FILE}: its layout is not one loadout rewrites; set "agents": {json.dumps(ordered)} by hand')
    return dumps_like(style, {**cfg.data, "agents": ordered})
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_repo_config.py`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
/usr/bin/git add cli/loadout/repo_config.py tests/test_repo_config.py
/usr/bin/git commit -m "feat(repo): .loadout.json chooses a repo's agents and can switch loadout off there"
```

---

### Task 3: The plan collector, its rendering, and undoable apply

**Files:**
- Create: `cli/loadout/repo_writes.py`
- Modify: `cli/loadout/backup.py` (`Backup.__init__` gains `repo: Path | None = None`; `_save` writes `"repo": str(repo)` when set)
- Test: `tests/test_repo_writes.py`

**Interfaces:**
- Consumes: `backup.Backup` (`save_copy`, `record_created`, `root`, `empty`), `backup.restore`, `jsonio.write_atomic`, `runner.run`, `secrets.redact`.
- Produces:
  - `Change(kind: str, path: Path | None, why: str, text: str | None = None, src: Path | None = None, target: str | None = None, cmd: list | None = None, touches: tuple = ())` with kinds `create`, `modify`, `copy`, `link`, `run`.
  - `RepoWrites(project: Path, now: bool = False, bk: Backup | None = None)` with methods `create(path, text, why)`, `modify(path, text, why)`, `copytree(src, dest, why)`, `link(dest, target, why)`, `run(cmd, why, touches=())`, property `changes: list[Change]`, `render() -> list[str]`, `apply(bk: Backup) -> list[str]` (returns problem lines; empty when all went well).
  - With `now=True` each method acts at once (the old direct-write behaviour; with `bk` it also records the undo step).

- [ ] **Step 1: Write the failing tests**

```python
"""Repo writes are collected, shown, then applied with a backup that restore undoes (spec Part 0)."""
import os

import pytest

from loadout import backup, repo_writes


@pytest.fixture
def repo(fake_home, tmp_path):
    p = tmp_path / "repo"
    (p / ".git").mkdir(parents=True)
    return p


def test_collecting_changes_nothing(repo):
    w = repo_writes.RepoWrites(repo)
    w.create(repo / "AGENTS.md", "# x\n", "init: instructions every agent reads")
    w.modify(repo / ".gitignore", "a\n", "init")
    assert not (repo / "AGENTS.md").exists() and [c.kind for c in w.changes] == ["create", "modify"]


def test_the_plan_names_each_change_with_its_reason(repo):
    (repo / ".claude").mkdir()
    (repo / ".claude" / "settings.json").write_text('{\n  "a": 1\n}\n')
    w = repo_writes.RepoWrites(repo)
    w.create(repo / "AGENTS.md", "l1\nl2\n", "init: instructions every agent reads")
    w.modify(repo / ".claude" / "settings.json", '{\n  "a": 2,\n  "b": [\n    "x"\n  ]\n}\n', "profile web")
    w.link(repo / ".agents" / "skills" / "pw", "../../.claude/skills/pw", "skill pw for Codex")
    w.run(["playwright-cli", "install", "--skills"], "profile web")
    text = "\n".join(w.render())
    assert "create  AGENTS.md (2 lines)" in text and "init: instructions every agent reads" in text
    assert "change  .claude/settings.json" in text and "~ a: 1 -> 2" in text and '+ b: ["x"]' in text
    assert "link    .agents/skills/pw -> ../../.claude/skills/pw" in text
    assert "run     playwright-cli install --skills" in text and "restore cannot undo" in text


def test_the_plan_redacts_secrets(repo):
    token = "ghp" + "_" + "a1b2c3d4e5" * 4
    w = repo_writes.RepoWrites(repo)
    w.create(repo / ".mcp.json", '{"k": "%s"}\n' % token, "profile x")
    w.run(["tool", f"--token={token}"], "profile x")
    assert token not in "\n".join(w.render())


def test_apply_writes_exactly_the_plan_and_restore_undoes_it(repo):
    (repo / "docs").mkdir()
    (repo / "docs" / "mine.md").write_text("my notes\n")
    (repo / ".gitignore").write_bytes(b"node_modules/\r\n")
    w = repo_writes.RepoWrites(repo)
    w.create(repo / ".claude" / "settings.json", "{}\n", "profile web")
    w.create(repo / "docs" / "README.md", "# docs\n", "init")
    w.modify(repo / ".gitignore", "node_modules/\r\n# loadout\r\n.serena/cache/\r\n", "init")
    bk = backup.Backup(description="t", repo=repo)
    assert w.apply(bk) == []
    assert (repo / ".claude" / "settings.json").read_text() == "{}\n"
    lines, ok, _ = backup.restore(bk.root)
    assert ok, lines
    assert not (repo / ".claude").exists()
    assert (repo / "docs" / "mine.md").read_text() == "my notes\n" and not (repo / "docs" / "README.md").exists()
    assert (repo / ".gitignore").read_bytes() == b"node_modules/\r\n"


def test_the_backup_names_the_repo(repo):
    from loadout.jsonio import load_json
    bk = backup.Backup(description="t", repo=repo)
    w = repo_writes.RepoWrites(repo)
    w.create(repo / "AGENTS.md", "x\n", "init")
    w.apply(bk)
    assert load_json(bk.root / "manifest.json")["repo"] == str(repo)


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink")
def test_a_link_and_a_copied_folder_are_undone(repo, tmp_path):
    src = tmp_path / "skill"
    src.mkdir()
    (src / "SKILL.md").write_text("s\n")
    w = repo_writes.RepoWrites(repo)
    w.copytree(src, repo / ".claude" / "skills" / "pw", "skill pw")
    w.link(repo / ".agents" / "skills" / "pw", "../../.claude/skills/pw", "skill pw for Codex")
    bk = backup.Backup(description="t", repo=repo)
    assert w.apply(bk) == []
    assert (repo / ".agents" / "skills" / "pw" / "SKILL.md").read_text() == "s\n"
    assert backup.restore(bk.root)[1]
    assert not (repo / ".claude").exists() and not (repo / ".agents").exists()


def test_a_run_saves_what_it_touches_first(repo, fake_runner):
    (repo / ".claude").mkdir()
    (repo / ".claude" / "settings.json").write_text("{}\n")
    w = repo_writes.RepoWrites(repo)
    w.run(["claude", "plugin", "install", "x@y", "--scope", "project"], "profile web",
          touches=(repo / ".claude" / "settings.json",))
    bk = backup.Backup(description="t", repo=repo)
    w.apply(bk)
    (repo / ".claude" / "settings.json").write_text('{"enabledPlugins": {"x@y": true}}\n')  # what claude wrote
    assert ["claude", "plugin", "install", "x@y", "--scope", "project"] in fake_runner.calls
    assert backup.restore(bk.root)[1]
    assert (repo / ".claude" / "settings.json").read_text() == "{}\n"


def test_now_mode_writes_at_once(repo):
    w = repo_writes.RepoWrites(repo, now=True)
    w.create(repo / "AGENTS.md", "x\n", "init")
    assert (repo / "AGENTS.md").read_text() == "x\n"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_repo_writes.py`
Expected: FAIL with `ImportError: cannot import name 'repo_writes'`.

- [ ] **Step 3: Give `Backup` the repo**

In `cli/loadout/backup.py`, `Backup.__init__`:

```python
    def __init__(self, root: Path | None = None, description: str = "", repo: Path | None = None):
        self._fixed = root is not None
        self._root = root or paths.backups_root() / time.strftime("loadout-%Y%m%d-%H%M%S")
        self.description = description
        self.repo = repo
        self.steps: list[dict] = []
```

and in `_save`:

```python
        manifest = {"description": self.description, "created_at": self._created_at, "steps": self.steps}
        if self.repo is not None:
            manifest["repo"] = str(self.repo)
```

- [ ] **Step 4: Implement `cli/loadout/repo_writes.py`**

```python
"""Repo writes as a plan: collected, shown, then applied with a backup (spec Part 0)."""
from __future__ import annotations

import difflib
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from . import runner
from .jsonio import write_atomic
from .secrets import redact


@dataclass
class Change:
    kind: str                 # create | modify | copy | link | run
    path: Path | None
    why: str
    text: str | None = None
    src: Path | None = None
    target: str | None = None
    cmd: list | None = None
    touches: tuple = ()


def _top_missing(path: Path, project: Path) -> Path:
    """The highest folder (or the path itself) that does not exist yet: what restore has to take away again."""
    top = path
    for parent in path.parents:
        if parent == project or parent.exists() or parent.is_symlink():
            break
        top = parent
    return top


def _flat(value, prefix=""):
    if isinstance(value, dict) and value:
        out = {}
        for k, v in value.items():
            out.update(_flat(v, f"{prefix}.{k}" if prefix else str(k)))
        return out
    return {prefix: value}


def _json_diff(old: str, new: str) -> list[str] | None:
    try:
        a, b = _flat(json.loads(old or "{}")), _flat(json.loads(new))
    except ValueError:
        return None
    lines = []
    for key in b:
        if key not in a:
            lines.append(f"+ {key}: {json.dumps(b[key], ensure_ascii=False)}")
        elif a[key] != b[key]:
            lines.append(f"~ {key}: {json.dumps(a[key], ensure_ascii=False)} -> {json.dumps(b[key], ensure_ascii=False)}")
    lines += [f"- {key}" for key in a if key not in b]
    return lines


def _text_diff(old: str, new: str) -> list[str]:
    return [l for l in difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=0)
            if not l.startswith(("---", "+++", "@@"))]


class RepoWrites:
    def __init__(self, project: Path, now: bool = False, bk=None):
        self.project, self.now, self.bk = project, now, bk
        self._changes: list[Change] = []

    @property
    def changes(self) -> list[Change]:
        return list(self._changes)

    def _add(self, change: Change) -> None:
        if self.now:
            problem = self._do(change, self.bk)
            if problem:
                raise OSError(problem)
        else:
            self._changes.append(change)

    def create(self, path: Path, text: str, why: str) -> None:
        self._add(Change("create", path, why, text=text))

    def modify(self, path: Path, text: str, why: str) -> None:
        self._add(Change("modify", path, why, text=text))

    def copytree(self, src: Path, dest: Path, why: str) -> None:
        self._add(Change("copy", dest, why, src=src))

    def link(self, dest: Path, target: str, why: str) -> None:
        self._add(Change("link", dest, why, target=target))

    def run(self, cmd: list, why: str, touches: tuple = ()) -> None:
        self._add(Change("run", None, why, cmd=list(cmd), touches=tuple(touches)))

    def _rel(self, path: Path) -> str:
        try:
            return path.relative_to(self.project).as_posix()
        except ValueError:
            return str(path)

    def render(self) -> list[str]:
        out = []
        for c in self._changes:
            if c.kind == "create":
                n = len(c.text.splitlines())
                out.append(f"  create  {self._rel(c.path)} ({n} line{'s' if n != 1 else ''})  {c.why}")
                if c.path.suffix == ".json":
                    out += [f"          {l}" for l in (_json_diff("", c.text) or [])]
            elif c.kind == "modify":
                out.append(f"  change  {self._rel(c.path)}  {c.why}")
                old = c.path.read_text(encoding="utf-8") if c.path.exists() else ""
                diff = _json_diff(old, c.text) if c.path.suffix == ".json" else None
                out += [f"          {l}" for l in (diff if diff is not None else _text_diff(old, c.text))]
            elif c.kind == "copy":
                files = sum(1 for p in c.src.rglob("*") if p.is_file())
                out.append(f"  copy    {self._rel(c.path)} ({files} file{'s' if files != 1 else ''})  {c.why}")
            elif c.kind == "link":
                out.append(f"  link    {self._rel(c.path)} -> {c.target}  {c.why}")
            else:
                out.append(f"  run     {' '.join(c.cmd)}  {c.why}; what it changes is its own, restore cannot undo it"
                           if not c.touches else f"  run     {' '.join(c.cmd)}  {c.why}")
        return [redact(l) for l in out]

    def apply(self, bk) -> list[str]:
        """Apply every collected change in order; each is recorded in `bk` before or as it happens."""
        problems = []
        for c in self._changes:
            problem = self._do(c, bk)
            if problem:
                problems.append(redact(problem))
        return problems

    def _do(self, c: Change, bk) -> str | None:
        if c.kind == "run":
            for path in c.touches:
                if bk is not None:
                    if path.exists():
                        bk.save_copy(path, f"{self._rel(path)} before {c.cmd[0]}")
                    else:
                        bk.record_created(_top_missing(path, self.project), f"{self._rel(path)} (created by {c.cmd[0]})")
            res = runner.run(c.cmd, cwd=str(self.project))
            return None if res.ok else f"{c.cmd[0]}: failed: {res.stderr.strip()}"
        if c.kind == "modify":
            if bk is not None:
                bk.save_copy(c.path, f"{self._rel(c.path)} before loadout changed it")
            write_atomic(c.path, c.text)
            return None
        top = _top_missing(c.path, self.project)
        c.path.parent.mkdir(parents=True, exist_ok=True)
        if c.kind == "create":
            write_atomic(c.path, c.text)
        elif c.kind == "copy":
            shutil.copytree(c.src, c.path, symlinks=True)
        else:
            try:
                os.symlink(c.target, c.path, target_is_directory=True)
            except OSError as exc:  # e.g. Windows without symlink rights
                return f"{self._rel(c.path)}: not linked ({exc.strerror or exc})"
        if bk is not None:
            bk.record_created(top, f"{self._rel(top)} (created by loadout)")
        return None
```

Note: `write_atomic` encodes the text as given, so CRLF in `text` stays CRLF.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_repo_writes.py tests/test_backup*.py`
Expected: PASS (all).

- [ ] **Step 6: Commit**

```bash
/usr/bin/git add cli/loadout/repo_writes.py cli/loadout/backup.py tests/test_repo_writes.py
/usr/bin/git commit -m "feat(repo): repo writes are collected as a plan, shown, and applied with a backup restore undoes"
```

---

### Task 4: The writers go through the collector and follow the repo's agents

**Files:**
- Modify: `cli/loadout/scaffold.py` (`scaffold`, `ensure_gitignore`)
- Modify: `cli/loadout/profiles.py` (`Profile.why`, `read_profile`, `claude_off_notes` → `repo_off_notes`, `apply_profile`, `repo_skill_dirs`, `copy_skills`, `link_skills`, `_link_into`)
- Modify: `cli/loadout/codex_project.py` (`config`)
- Modify: `profiles/*.json` (add `why`)
- Test: `tests/test_repo_writers_plan.py`; update `tests/test_repo_follows_agents.py`, `tests/test_project.py` where they assert the old `.gitignore` header or Claude-off note text.

**Interfaces:**
- Consumes: `repo_writes.RepoWrites` (Task 3), `repo_config.agents(project)` (Task 2), `jsonio.json_style/dumps_like` (Task 1).
- Produces (each keeps its old return value; `w=None` means write now as before):
  - `scaffold.scaffold(project, dry_run=False, w=None) -> (list[Path], list[str])`
  - `scaffold.ensure_gitignore(project, dry_run=False, w=None) -> list[str]`
  - `profiles.apply_profile(profile, project, w=None) -> (list[Path], list[str])`
  - `profiles.repo_off_notes(profile, project) -> list[str]` (replaces `claude_off_notes`; keep `claude_off_notes = lambda p: repo_off_notes(p, None)` only if a caller remains — none should)
  - `profiles.copy_skills(profile, project, dry_run=False, w=None) -> list[str]`
  - `profiles.link_skills(project, dry_run, w=None) -> list[str]`
  - `profiles.repo_skill_dirs(project) -> (Path, Path | None)` now from `repo_config.agents(project)`
  - `codex_project.config(prof, project, dry_run, skip=frozenset(), w=None) -> list[str]`
  - `Profile.why: dict` (entry path like `"settings.disabledMcpjsonServers"` → text); `profiles.reason(profile, entry=None) -> str`.

- [ ] **Step 1: Write the failing tests** (`tests/test_repo_writers_plan.py`)

```python
"""The repo writers plan their changes, keep the user's bytes, and follow the repo's agents (spec Parts 0, 1)."""
import json

import pytest

from loadout import profiles, repo_writes, scaffold, targets


@pytest.fixture
def repo(fake_home, tmp_path):
    p = tmp_path / "repo"
    (p / ".git").mkdir(parents=True)
    return p


def _web():
    return profiles.Profile(name="web", description="Web UI", settings={"disabledMcpjsonServers": ["cd"]},
                            mcp={"mcpServers": {"cd": {"command": "npx"}}}, why={"settings.disabledMcpjsonServers": "off until needed"})


def test_planning_writes_nothing(repo):
    targets.set_agents({"claude": True, "codex": True})
    w = repo_writes.RepoWrites(repo)
    scaffold.scaffold(repo, w=w)
    scaffold.ensure_gitignore(repo, w=w)
    profiles.apply_profile(_web(), repo, w=w)
    assert sorted(p.name for p in repo.iterdir()) == [".git"]
    kinds = {(c.kind, c.path.relative_to(repo).as_posix()) for c in w.changes}
    assert ("create", "AGENTS.md") in kinds and ("create", ".claude/settings.json") in kinds and ("create", ".gitignore") in kinds


def test_the_reason_names_the_profile_and_its_why(repo):
    targets.set_agents({"claude": True, "codex": False})
    w = repo_writes.RepoWrites(repo)
    profiles.apply_profile(_web(), repo, w=w)
    assert any("profile web" in c.why and "off until needed" in c.why for c in w.changes)


@pytest.mark.parametrize("indent, nl", [(4, "\r\n"), ("\t", "\n")])
def test_a_profile_keeps_the_files_layout(repo, indent, nl):
    targets.set_agents({"claude": True, "codex": False})
    (repo / ".claude").mkdir()
    before = (json.dumps({"model": "x"}, indent=indent) + "\n").replace("\n", nl)
    (repo / ".claude" / "settings.json").write_bytes(before.encode())
    profiles.apply_profile(_web(), repo)
    after = (repo / ".claude" / "settings.json").read_bytes().decode()
    assert after == (json.dumps({"model": "x", "disabledMcpjsonServers": ["cd"]}, indent=indent) + "\n").replace("\n", nl)


def test_a_hand_laid_out_file_is_left_and_its_entries_named(repo):
    targets.set_agents({"claude": True, "codex": False})
    (repo / ".claude").mkdir()
    (repo / ".claude" / "settings.json").write_text('{"model": "x"}\n')
    changed, skipped = profiles.apply_profile(_web(), repo)
    assert (repo / ".claude" / "settings.json").read_text() == '{"model": "x"}\n'
    assert any(".claude/settings.json" in l and "by hand" in l and "disabledMcpjsonServers" in l for l in skipped)


def test_a_no_op_run_does_not_touch_the_file(repo):
    targets.set_agents({"claude": True, "codex": False})
    profiles.apply_profile(_web(), repo)
    path = repo / ".claude" / "settings.json"
    stamp = path.stat().st_mtime_ns
    w = repo_writes.RepoWrites(repo)
    profiles.apply_profile(_web(), repo, w=w)
    assert not [c for c in w.changes if c.path == path] and path.stat().st_mtime_ns == stamp


def test_gitignore_gets_one_header(repo):
    targets.set_agents({"claude": False, "codex": True})
    scaffold.ensure_gitignore(repo)
    targets.set_agents({"claude": True, "codex": True})
    scaffold.ensure_gitignore(repo)
    text = (repo / ".gitignore").read_text()
    assert text.count("# loadout") == 1 and ".claude/settings.local.json" in text and text.index("# loadout") < text.index(".claude/")


def test_gitignore_keeps_crlf(repo):
    (repo / ".gitignore").write_bytes(b"node_modules/\r\n")
    scaffold.ensure_gitignore(repo)
    assert b"\n" not in (repo / ".gitignore").read_bytes().replace(b"\r\n", b"")


def test_the_repos_agents_win_over_the_users(repo):
    targets.set_agents({"claude": True, "codex": True})
    (repo / ".loadout.json").write_text('{\n  "agents": [\n    "codex"\n  ]\n}\n')
    w = repo_writes.RepoWrites(repo)
    scaffold.scaffold(repo, w=w)
    profiles.apply_profile(_web(), repo, w=w)
    written = {c.path.relative_to(repo).as_posix() for c in w.changes}
    assert "CLAUDE.md" not in written and ".claude/settings.json" not in written and ".mcp.json" not in written
    assert profiles.repo_off_notes(_web(), repo) == [
        ".claude/settings.json and .mcp.json: not written, this repo is for Codex only (.loadout.json; "
        "add Claude Code with loadout init --agents claude,codex)"]


def test_a_codex_only_user_writes_claude_files_in_a_both_agents_repo(repo):
    targets.set_agents({"claude": False, "codex": True})
    (repo / ".loadout.json").write_text('{\n  "agents": [\n    "claude",\n    "codex"\n  ]\n}\n')
    profiles.apply_profile(_web(), repo)
    assert (repo / ".claude" / "settings.json").is_file() and (repo / ".mcp.json").is_file()
    assert profiles.repo_skill_dirs(repo) == (repo / ".claude" / "skills", repo / ".agents" / "skills")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_repo_writers_plan.py`
Expected: FAIL (`TypeError: ... unexpected keyword argument 'w'` / `'why'`).

- [ ] **Step 3: Implement in `cli/loadout/scaffold.py`**

Replace `scaffold` and `ensure_gitignore`:

```python
def _writes(project: Path, w):
    from .repo_writes import RepoWrites
    return w if w is not None else RepoWrites(project, now=True)


def scaffold(project: Path, dry_run: bool = False, w=None) -> tuple[list[Path], list[str]]:
    from . import repo_config
    templates = paths.kit_root() / "templates" / "project"
    skip = set() if repo_config.agents(project)["claude"] else {"CLAUDE.md"}  # Claude Code's file (ADR 0030)
    notes = []
    if (project / "CLAUDE.md").exists() and not (project / "AGENTS.md").exists():
        skip = {"AGENTS.md", "CLAUDE.md"}
        notes.append("CLAUDE.md exists without AGENTS.md: /loadout:onboard will offer to migrate it.")
    writes = None if dry_run else _writes(project, w)
    created = []
    for src in sorted(templates.rglob("*")):
        if src.is_dir():
            continue
        rel = src.relative_to(templates)
        dest = project / rel
        if rel.as_posix() in skip or dest.exists():
            continue
        if dest.is_symlink():
            if not paths.inside(dest, project):
                notes.append(f"skipped {rel.as_posix()}: it points outside the repo")
            continue
        if not paths.inside(dest, project) or not paths.inside(dest.parent, project):
            notes.append(f"skipped {rel.as_posix()}: it points outside the repo")
            continue
        created.append(dest)
        if writes is not None:
            writes.create(dest, render(src.read_text(encoding="utf-8"), {"PROJECT_NAME": project.name}),
                          f"init: {WHY.get(rel.as_posix(), 'project scaffold')}")
    return created, notes


WHY = {"AGENTS.md": "instructions every agent reads", "CLAUDE.md": "points Claude Code at AGENTS.md",
       "docs/README.md": "the docs map", "docs/adr/README.md": "the decisions index"}


def ensure_gitignore(project: Path, dry_run: bool = False, w=None) -> list[str]:
    from . import repo_config
    path = project / ".gitignore"
    if not paths.inside(path, project):
        return []
    text = path.read_bytes().decode("utf-8") if path.exists() else ""
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.replace("\r\n", "\n").split("\n")
    existing = {line.strip() for line in lines}
    wanted = [l for l in GITIGNORE_LINES if repo_config.agents(project)["claude"] or not l.startswith(".claude/")]
    missing = [line for line in wanted if line not in existing]
    if not missing or dry_run:
        return missing
    if "# loadout" in existing:  # one header: new lines go under it
        at = next(i for i, l in enumerate(lines) if l.strip() == "# loadout") + 1
        while at < len(lines) and lines[at].strip() and not lines[at].startswith("#"):
            at += 1
        lines[at:at] = missing
        new = "\n".join(lines)
    else:
        body = "\n".join(lines).rstrip("\n")
        new = (body + "\n" if body else "") + "# loadout\n" + "\n".join(missing) + "\n"
    new = new.replace("\n", nl)
    writes = _writes(project, w)
    (writes.modify if path.exists() else writes.create)(path, new, "init: keep local agent files out of git")
    return missing
```

- [ ] **Step 4: Implement in `cli/loadout/profiles.py`**

Add `why: dict = field(default_factory=dict)` to `Profile`; in `read_profile` add `why=field_of("why", dict, {}),`. Add:

```python
def reason(profile: Profile, entry: str | None = None) -> str:
    text = profile.why.get(entry) if entry else None
    return f"profile {profile.name}" + (f": {text}" if isinstance(text, str) and text else
                                        f" ({profile.description})" if profile.description and entry is None else "")


def repo_off_notes(profile: Profile, project: Path) -> list[str]:
    """One line when the repo is not for Claude Code but the profile has Claude Code files (ADR 0030)."""
    from . import repo_config
    if repo_config.agents(project)["claude"]:
        return []
    files = [rel.as_posix() for attr, rel in CLAUDE_FILES if getattr(profile, attr)]
    if not files:
        return []
    chosen = repo_config.load(project).agents is not None
    why = ("this repo is for Codex only (.loadout.json; add Claude Code with loadout init --agents claude,codex)"
           if chosen else "Claude Code is off for you (turn it on and run loadout profile "
           f"{profile.name} again, or choose the repo's agents with loadout init --agents claude,codex)")
    return [f"{' and '.join(files)}: not written, {why}"]
```

Replace `apply_profile`:

```python
def apply_profile(profile: Profile, project: Path, w=None) -> tuple[list[Path], list[str]]:
    """Merge the profile into the repo's settings and .mcp.json when the repo is for Claude Code. A file is changed
    only in the layout it already has; any other file is left and its entries named. Returns (changed, skipped)."""
    import json as _json
    from . import repo_config
    from .jsonio import dumps_like, json_style
    from .repo_writes import RepoWrites
    changed, skipped = [], []
    if not repo_config.agents(project)["claude"]:
        return changed, skipped  # repo_off_notes says what was not written
    writes = w if w is not None else RepoWrites(project, now=True)
    for attr, rel in CLAUDE_FILES:
        overlay = getattr(profile, attr)
        if not overlay:
            continue
        target = project / rel
        if not paths.inside(target, project) or not paths.inside(target.parent, project):
            skipped.append(f"skipped {rel.as_posix()}: it points outside the repo")
            continue
        old = target.read_bytes().decode("utf-8") if target.exists() else None
        style = json_style(old) if old is not None else None
        if old is not None and style is None:
            entries = ", ".join(sorted(overlay))
            skipped.append(f"{rel.as_posix()}: left as is (its layout is not one loadout rewrites); add by hand: "
                           f"{_json.dumps(overlay, ensure_ascii=False)} ({entries})")
            continue
        before = _json.loads(old) if old is not None else {}
        after = deep_merge(before, overlay)
        if after == before and old is not None:
            continue
        keys = [f"{attr}.{k}" for k in overlay]
        why = next((reason(profile, k) for k in keys if k in profile.why), reason(profile))
        if old is None:
            writes.create(target, _json.dumps(after, indent=2, ensure_ascii=False) + "\n", why)
        else:
            writes.modify(target, dumps_like(style, after), why)
        changed.append(target)
    return changed, skipped
```

In `repo_skill_dirs`, replace the `targets` lookups:

```python
    from . import repo_config
    on = repo_config.agents(project)
    claude, agents = (project / rel for rel in REPO_SKILLS)
    if not on["claude"]:
        return agents, None
    return claude, agents if on["codex"] else None
```

In `copy_skills`, add `w=None` and replace the `copytree` branch:

```python
        else:
            from .repo_writes import RepoWrites
            (w if w is not None else RepoWrites(project, now=True)).copytree(src, dest, f"{reason(profile)}: skill {name}")
            out.append(f"copied skill {name} -> {dest}")
```

In `link_skills(project, dry_run, w=None)` use `on = repo_config.agents(project)` instead of `targets.*_enabled()` and pass `w` to `_link_into`; in `_link_into(..., w=None)` replace the `mkdir` + `os.symlink` block with:

```python
        if w is not None:
            w.link(dest, want, f"skill {name} for {agent}")
            out.append(f"linked skill {name} for {agent} -> {dest_rel}/{name}")
            continue
        dest_root.mkdir(parents=True, exist_ok=True)
        try:
            os.symlink(want, dest, target_is_directory=True)
        except OSError as exc:  # e.g. Windows without symlink rights
            out.append(f"skill {name}: not linked for {agent} ({exc.strerror or exc})")
            continue
        out.append(f"linked skill {name} for {agent} -> {dest_rel}/{name}")
```

Delete `claude_off_notes`; replace its one caller in `project.py` (Task 5 rewrites that block).

- [ ] **Step 5: Implement in `cli/loadout/codex_project.py`**

`config(prof, project, dry_run, skip=frozenset(), w=None)`: replace the final write

```python
    from .jsonio import write_atomic
    path.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(path, new)
    return lines
```

with

```python
    from .repo_writes import RepoWrites
    writes = w if w is not None else RepoWrites(project, now=True)
    (writes.modify if path.exists() else writes.create)(path, new, profiles.reason(prof))
    return lines
```

Keep `if not added or dry_run: return lines` as it is: planning passes a collector with `dry_run=False`.

- [ ] **Step 6: Add `why` to the kit profiles**

Add one `why` object per kit profile, keyed by the entries it sets. `profiles/web.json`:

```json
  "why": {
    "mcp.mcpServers": "Chrome DevTools for performance and network debugging",
    "settings.disabledMcpjsonServers": "keeps Chrome DevTools off until you enable it in /mcp"
  },
```

For `android.json`, `db.json`, `sonar.json`, `thesis.json`: read each file, and write one short reason per top-level entry of `settings` and `mcp` (`"settings.<key>"`, `"mcp.mcpServers"`) in the same form, taken from the profile's `description` and `notes`.

- [ ] **Step 7: Run the new and the touched tests**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_repo_writers_plan.py tests/test_repo_follows_agents.py tests/test_project.py tests/test_codex_project.py tests/test_repo_writes_stay_inside.py`
Expected: PASS. Where an old test asserts the per-run `# loadout` header or the `Claude Code is off: … not written` text, update it to the new rule (one header; the `repo_off_notes` line) and ledger a ruling naming the test.

- [ ] **Step 8: Run the whole suite**

Run: `uv run --python 3.12 --with pytest pytest -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
/usr/bin/git add cli/loadout/scaffold.py cli/loadout/profiles.py cli/loadout/codex_project.py profiles tests
/usr/bin/git commit -m "feat(repo): repo writers plan their changes, keep the file's layout and follow the repo's agents"
```

---

### Task 5: `init` and `profile` show the plan, ask, apply with a backup

**Files:**
- Modify: `cli/loadout/project.py` (`add_profile`, `init`, `_install`)
- Modify: `cli/loadout/__main__.py` (`init --agents`, `profile --dry-run --yes`)
- Modify: `cli/loadout/adopt.py:612` (pass `approve=lambda _: True`)
- Test: `tests/test_repo_plan_flow.py`; update `tests/test_project.py::test_init_non_interactive_applies_no_profiles` (it now also writes nothing)

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces:
  - `project.add_profile(project, name, install=True, dry_run=False, drive_note=True, approve=None) -> int`; `approve: Callable[[list[str]], bool] | None`; `None` applies without asking and without printing the plan (library callers, adopt, old tests).
  - `project.init(project, names, yes, install, dry_run, ask, interactive=None, agents=None) -> int`; `agents: frozenset | None` from `--agents`.
  - `project.approver(yes: bool, ask, interactive: bool) -> Callable[[list[str]], bool]`.
  - Message constants: `MANAGE_OFF = "manage is false in .loadout.json: nothing written"`, `NO_TERMINAL = "no terminal: nothing written (run it again with --yes to apply this plan)"`, `DECLINED = "nothing changed"`.

- [ ] **Step 1: Write the failing tests** (`tests/test_repo_plan_flow.py`)

```python
"""init and profile: plan, yes, write, undo (spec Parts 0, 1)."""
import pytest

from loadout import backup, profiles, project, targets


@pytest.fixture
def repo(fake_home, fake_runner, tmp_path, monkeypatch):
    p = tmp_path / "repo"
    (p / ".git").mkdir(parents=True)
    monkeypatch.setattr(profiles, "load_profile", lambda name: profiles.Profile(
        name=name, description="Web UI", settings={"disabledMcpjsonServers": ["cd"]}, install=["pw@market"]))
    targets.set_agents({"claude": True, "codex": False})
    return p


def _files(p):
    return sorted(x.relative_to(p).as_posix() for x in p.rglob("*") if ".git" not in x.parts)


def test_a_declined_plan_writes_and_runs_nothing(repo, fake_runner, capsys):
    rc = project.add_profile(repo, "web", approve=lambda plan: False)
    assert rc == 0 and _files(repo) == [] and fake_runner.calls == []
    out = capsys.readouterr().out
    assert "change" in out or "create" in out
    assert "nothing changed" in out


def test_no_terminal_without_yes_writes_nothing(repo, fake_runner, capsys):
    rc = project.add_profile(repo, "web", approve=project.approver(False, lambda q: "", interactive=False))
    assert rc == 0 and _files(repo) == [] and fake_runner.calls == []
    assert project.NO_TERMINAL in capsys.readouterr().out


def test_eof_from_a_closed_stdin_is_a_no(repo, fake_runner):
    approve = project.approver(False, lambda q: "", interactive=True)
    assert project.add_profile(repo, "web", approve=approve) == 0 and _files(repo) == []


def test_yes_applies_the_plan_and_restore_undoes_it(repo, fake_runner, capsys):
    rc = project.add_profile(repo, "web", approve=project.approver(True, lambda q: "", interactive=False))
    assert rc == 0 and ".claude/settings.json" in _files(repo) and ".loadout.json" in _files(repo)
    out = capsys.readouterr().out
    line = next(l for l in out.splitlines() if "undo: loadout restore " in l)
    lines, ok, _ = backup.restore(__import__("pathlib").Path(line.split("undo: loadout restore ", 1)[1].strip()))
    assert ok, lines
    assert _files(repo) == []


def test_the_plan_shown_is_what_is_written(repo, fake_runner, capsys):
    project.add_profile(repo, "web", dry_run=True)
    planned = capsys.readouterr().out
    project.add_profile(repo, "web", approve=lambda plan: True)
    for rel in _files(repo):
        if "/" not in rel or rel.startswith(".claude/"):
            assert rel.split("/")[0] in planned


def test_dry_run_shows_the_settings_diff_and_changes_nothing(repo, fake_runner, capsys):
    assert project.add_profile(repo, "web", dry_run=True) == 0
    out = capsys.readouterr().out
    assert '+ disabledMcpjsonServers: ["cd"]' in out and _files(repo) == [] and fake_runner.calls == []


def test_manage_false_writes_nothing_and_says_so(repo, fake_runner, capsys):
    (repo / ".loadout.json").write_text('{"manage": false}')
    assert project.add_profile(repo, "web", approve=lambda plan: True) == 0
    assert project.MANAGE_OFF in capsys.readouterr().out
    assert _files(repo) == [".loadout.json"] and fake_runner.calls == []


def test_an_invalid_loadout_json_stops_before_any_change(repo, fake_runner, capsys):
    (repo / ".loadout.json").write_text('{"agents": "codex"}')
    assert project.add_profile(repo, "web", approve=lambda plan: True) == 1
    assert ".loadout.json: agents" in capsys.readouterr().out and _files(repo) == [".loadout.json"]


def test_a_codex_only_user_in_a_both_agents_repo(repo, fake_runner, capsys):
    targets.set_agents({"claude": False, "codex": True})
    (repo / ".loadout.json").write_text('{\n  "agents": [\n    "claude",\n    "codex"\n  ]\n}\n')
    project.add_profile(repo, "web", install=True, approve=lambda plan: True)
    assert (repo / ".claude" / "settings.json").is_file()
    assert not [c for c in fake_runner.calls if c[:2] == ["claude", "plugin"]]
    assert "plugin pw@market: not installed for Claude Code, which is off for you" in capsys.readouterr().out


def test_init_agents_flag_writes_the_choice(repo, fake_runner):
    rc = project.init(repo, [], yes=True, install=False, dry_run=False, ask=lambda q: "", interactive=False,
                      agents=frozenset({"codex"}))
    assert rc == 0
    assert (repo / ".loadout.json").read_text() == '{\n  "agents": [\n    "codex"\n  ]\n}\n'
    assert not (repo / "CLAUDE.md").exists() and (repo / "AGENTS.md").exists()


def test_init_asks_which_agents_in_a_terminal(repo, fake_runner):
    targets.set_agents({"claude": True, "codex": True})
    answers = iter(["2", "-", "y"])  # Codex only; no profiles; apply
    project.init(repo, [], yes=False, install=False, dry_run=False, ask=lambda q: next(answers), interactive=True)
    assert '"codex"' in (repo / ".loadout.json").read_text() and '"claude"' not in (repo / ".loadout.json").read_text()


def test_changing_agents_removes_nothing_and_lists_what_is_left(repo, fake_runner, capsys):
    project.init(repo, [], yes=True, install=False, dry_run=False, ask=lambda q: "", interactive=False,
                 agents=frozenset({"claude", "codex"}))
    capsys.readouterr()
    project.init(repo, [], yes=True, install=False, dry_run=False, ask=lambda q: "", interactive=False,
                 agents=frozenset({"codex"}))
    assert (repo / "CLAUDE.md").exists()
    assert "no longer needed for this repo's agents (yours to remove): CLAUDE.md" in capsys.readouterr().out
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_repo_plan_flow.py`
Expected: FAIL (`unexpected keyword argument 'approve'`, `no attribute 'approver'`).

- [ ] **Step 3: Implement the flow in `cli/loadout/project.py`**

Add at module level:

```python
MANAGE_OFF = "manage is false in .loadout.json: nothing written"
NO_TERMINAL = "no terminal: nothing written (run it again with --yes to apply this plan)"
DECLINED = "nothing changed"
QUESTION = "Apply these changes? [y/N] "
AGENTS_QUESTION = ("Which agents is this repo for? 1 Claude Code, 2 Codex, 3 both "
                   "(Enter: {default}; it decides the repo's files for everyone who clones it) ")


def approver(yes: bool, ask: Ask, interactive: bool):
    def approve(plan: list[str]) -> bool:
        if yes:
            return True
        if not interactive:
            print(NO_TERMINAL)
            return False
        return ui.confirm(ask, QUESTION)
    return approve


def _show(project: Path, title: str, w, notes: list[str]) -> list[str]:
    from . import repo_config
    on = repo_config.agents(project)
    names = " and ".join(n for n, k in (("Claude Code", "claude"), ("Codex", "codex")) if on[k])
    plan = [f"Plan for {project} ({title}; this repo's agents: {names}):"] + (w.render() or ["  (no file changes)"])
    plan += [f"  note    {n}" for n in notes]
    print("\n".join(plan))
    return plan
```

Rewrite `add_profile` so that one function builds the plan and a second runs it:

```python
def add_profile(project: Path, name: str, install: bool = True, dry_run: bool = False, drive_note: bool = True,
                approve=None) -> int:
    from . import repo_config
    from .repo_writes import RepoWrites
    try:
        cfg = repo_config.load(project)
    except repo_config.Invalid as exc:
        print(exc)
        return 1
    prof = profiles.load_profile(name)
    w = RepoWrites(project)
    notes = _plan_profile(prof, project, w, install, ensure_config=not cfg.exists)
    show = approve is not None or dry_run or not cfg.manage
    if show:
        _show(project, f"profile {name}", w, notes)
    if not cfg.manage:
        print(MANAGE_OFF)
        return 0
    if dry_run:
        print("dry run: nothing changed")
        return 0
    if approve is not None and not approve(w.render()):
        print(DECLINED)
        return 0
    return _apply_profile_plan(prof, project, w, install, drive_note, notes)
```

`_plan_profile(prof, project, w, install, ensure_config) -> list[str]` (notes) collects, in this order:

1. `.loadout.json` with the user's agents when `ensure_config` (via `repo_config.new_text(project, frozenset(a for a, on in repo_config.user_agents().items() if on))`; `w.create(project / ".loadout.json", text, "loadout: which agents this repo is for (commit it)")`).
2. `profiles.apply_profile(prof, project, w=w)` (skipped lines become notes).
3. `profiles.repo_off_notes(prof, project)` → notes.
4. `profiles.copy_skills(prof, project, w=w)` (non-"copied skill" lines become notes).
5. When `install`: for each valid `prof.install` id: if the repo is for Claude Code and Claude Code is on for the user → `w.run(["claude","plugin","install",pid,"--scope","project"], profiles.reason(prof), touches=(project/".claude"/"settings.json",))`; if the repo is for Claude Code but it is off for the user → note `plugin {pid}: not installed for Claude Code, which is off for you (a Claude Code user installs it with loadout profile {name} here)`. Then each valid `prof.commands` entry → `w.run(cmd, profiles.reason(prof))`.
6. `profiles.link_skills(project, False, w=w)` (skills that exist now; "not linked"/"left as is" lines become notes).
7. When the repo is for Codex: `codex_project.config(prof, project, False, w=w)` lines that are not "added"/"enabled" become notes; when Codex is on for the user and `install`: one note per Codex plugin `Codex plugin {pid}: installed in your Codex (outside this repo, its own backup)`.

`_apply_profile_plan(prof, project, w, install, drive_note, notes) -> int`:

```python
def _apply_profile_plan(prof, project, w, install, drive_note, notes) -> int:
    from . import backup, codex_project, repo_config, targets, wsl
    from .repo_writes import RepoWrites
    bk = backup.Backup(description=f"loadout profile {prof.name} in {project}", repo=project)
    problems = w.apply(bk)
    after = RepoWrites(project, now=True, bk=bk)  # skills the commands just installed
    late = profiles.link_skills(project, False, w=after)
    problems += [l for l in late if "not linked" in l or "left as is" in l]
    on = repo_config.agents(project)
    if on["codex"] and targets.codex_enabled() and install:
        problems += [l for l in codex_project.plugins(prof, False)
                     if l.startswith("skipped") or any(s in l for s in (": failed", "not installed", "no Codex route"))]
        if not codex_project._trusted(project):
            notes.append(codex_project.TRUST_NOTE)
    note = wsl.repo_note(project) if drive_note else None
    if note:
        notes.append(note)
    if prof.notes:
        notes.append(f"note ({prof.name}): {prof.notes}")
    from . import out
    out.status(f"Profile {prof.name}", "applied" if not problems else "applied with problems (below)",
               "ok" if not problems else "warn")
    for line in problems + notes:
        out.problem(line)
    if not bk.empty:
        print(f"undo: loadout restore {bk.root}")
    return 1 if problems else 0
```

Rewrite `init` around the same pieces: validate names, git init (unchanged), choose profiles (unchanged), then the agents:

```python
    from . import repo_config
    try:
        cfg = repo_config.load(project)
    except repo_config.Invalid as exc:
        print(exc)
        return 1
    if agents is None and cfg.agents is None:
        mine = frozenset(a for a, on in repo_config.user_agents().items() if on)
        agents = mine
        if interactive and not yes and not dry_run:
            default = " and ".join("Claude Code" if a == "claude" else "Codex" for a in sorted(mine))
            answer = ask(AGENTS_QUESTION.format(default=default)).strip()
            agents = {"1": frozenset({"claude"}), "2": frozenset({"codex"}),
                      "3": frozenset({"claude", "codex"})}.get(answer, mine)
    w = RepoWrites(project)
    notes = []
    if agents is not None:
        text = repo_config.new_text(project, agents)  # Invalid for a hand-laid-out file: print it, return 1
        if text is not None:
            (w.modify if cfg.exists else w.create)(project / repo_config.FILE, text,
                                                   "init: which agents this repo is for (commit it)")
            dropped = (cfg.agents or frozenset()) - agents
            if "claude" in dropped:
                left = [r for r in ("CLAUDE.md", ".claude/settings.json", ".mcp.json") if (project / r).exists()]
                if left:
                    notes.append(f"no longer needed for this repo's agents (yours to remove): {', '.join(left)}")
            if "codex" in dropped and (project / ".codex" / "config.toml").exists():
                notes.append("no longer needed for this repo's agents (yours to remove): .codex/config.toml")
```

The planners read the repo's agents from disk, so while planning, `repo_config.agents(project)` must see the new choice: wrap the planning in `repo_config.pending(project, agents)` — add to `repo_config`:

```python
_PENDING: dict = {}


class pending:
    """While planning, the agents about to be written count as the repo's."""
    def __init__(self, project: Path, chosen: frozenset | None):
        self.key, self.chosen = str(project), chosen

    def __enter__(self):
        if self.chosen is not None:
            _PENDING[self.key] = self.chosen

    def __exit__(self, *exc):
        _PENDING.pop(self.key, None)
```

and at the top of `repo_config.agents`: `if str(project) in _PENDING: return {a: a in _PENDING[str(project)] for a in AGENTS}`. Add a test in `tests/test_repo_config.py`:

```python
def test_pending_agents_count_while_planning(repo):
    targets.set_agents({"claude": True, "codex": True})
    with repo_config.pending(repo, frozenset({"codex"})):
        assert repo_config.agents(repo) == {"claude": False, "codex": True}
    assert repo_config.agents(repo) == {"claude": True, "codex": True}
```

Inside `with repo_config.pending(project, agents):` init collects, into the same `w`: each chosen profile through `_plan_profile(..., ensure_config=False)`, `scaffold.scaffold(project, w=w)`, `scaffold.ensure_gitignore(project, w=w)`. Then the same order as `add_profile`: show (always), `manage` off → `MANAGE_OFF`, `dry_run` → stop, `approver(yes, ask, interactive)(plan)` → stop with `DECLINED` on no, apply once with one `Backup(description=f"loadout init in {project}", repo=project)`, run the post-command link pass and, per profile, the Codex plugin step of `_apply_profile_plan` (factor that block into `_after_apply(prof, project, bk, install, drive_note, notes, problems)` and call it from both). Keep the final `next:` line, choosing the agent from the repo's agents that are also on for the user.

- [ ] **Step 4: Wire the CLI in `cli/loadout/__main__.py`**

```python
    p = sub.add_parser("init", help="set up the current project",
                       description="Prepare the current project: .loadout.json, AGENTS.md, CLAUDE.md, docs/, .gitignore entries, profiles. "
                                   "Shows the plan and asks before it changes anything; never overwrites files.")
    p.add_argument("profiles", nargs="*", help="profiles to apply (default: suggest from the project and ask)")
    p.add_argument("--agents", metavar="claude|codex|claude,codex", help="which agents this repo is for (written to .loadout.json)")
    p.add_argument("--yes", action="store_true", help="no questions: git init if needed, the suggested profiles, apply the plan")
    ...
    p.set_defaults(func=lambda a: _verbose(a) or project.init(
        Path.cwd(), a.profiles, a.yes, not a.no_install, a.dry_run, _ask,
        agents=repo_config.parse_agents(a.agents) if a.agents else None))

    p = sub.add_parser("profile", help="add a profile to the current project")
    p.add_argument("name", ...)
    p.add_argument("--no-install", ...)
    p.add_argument("--dry-run", action="store_true", help="show the plan, change nothing")
    p.add_argument("--yes", action="store_true", help="apply the plan without asking (needed without a terminal)")
    p.add_argument("--verbose", ...)
    p.set_defaults(func=lambda a: _verbose(a) or project.add_profile(
        Path.cwd(), a.name, install=not a.no_install, dry_run=a.dry_run,
        approve=project.approver(a.yes, _ask, ui.is_interactive())))
```

(`from . import repo_config, ui` next to the existing `project` import.) A `ValueError` from `parse_agents` already reaches the CLI's error printing; check with `loadout init --agents cursor` → exit 2 and the `--agents:` message, as `bootstrap --agents` does.

In `cli/loadout/adopt.py:612`: `ok = project.add_profile(repo, name, approve=lambda plan: True) == 0` (adopt asked already).

- [ ] **Step 5: Run the new tests, then the suite**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_repo_plan_flow.py tests/test_repo_config.py`
Expected: PASS.
Run: `uv run --python 3.12 --with pytest pytest -q`
Expected: PASS. Update `test_init_non_interactive_applies_no_profiles` to also assert nothing was written (`not (tmp_path / "proj" / "AGENTS.md").exists()`) and `NO_TERMINAL` in the output; other output-pinning tests in `tests/test_project.py` move to the new lines; ledger a ruling per changed test.

- [ ] **Step 6: Commit**

```bash
/usr/bin/git add cli/loadout/project.py cli/loadout/__main__.py cli/loadout/adopt.py cli/loadout/repo_config.py tests
/usr/bin/git commit -m "feat(repo): init and profile show the plan, ask, and apply it with a backup; init --agents"
```

---

### Task 6: `configure new skill --to repo` follows the same rules

**Files:**
- Modify: `cli/loadout/new_skill.py` (`_repo`)
- Modify: `cli/loadout/commands.py` (`configure` gains `--yes`; the `new` branch asks for `--to repo`)
- Test: `tests/test_new_skill_repo_plan.py`

**Interfaces:**
- Consumes: `repo_config.load`, `repo_config.agents` (via `profiles.repo_skill_dirs`), `project.approver`, `project.MANAGE_OFF`.
- Produces: `new_skill.create(..., approve=None)`; for `to == "repo"`, `approve(plan_lines)` is asked before any write; a declined plan returns `["nothing changed"]` and writes nothing.

- [ ] **Step 1: Write the failing tests**

```python
"""`configure new skill --to repo`: the repo's agents, manage: false, a plan and a yes (spec Parts 0, 1)."""
import pytest

from loadout import new_skill, targets


@pytest.fixture
def repo(fake_home, tmp_path):
    p = tmp_path / "repo"
    (p / ".git").mkdir(parents=True)
    return p


def test_a_codex_only_repo_gets_the_skill_in_agents_skills(repo):
    targets.set_agents({"claude": True, "codex": True})
    (repo / ".loadout.json").write_text('{\n  "agents": [\n    "codex"\n  ]\n}\n')
    new_skill.create("notes", "repo", "Use when x", cwd=repo, approve=lambda plan: True)
    assert (repo / ".agents" / "skills" / "notes" / "SKILL.md").is_file() and not (repo / ".claude").exists()


def test_manage_false_refuses(repo):
    (repo / ".loadout.json").write_text('{"manage": false}')
    with pytest.raises(new_skill.Refused, match="manage is false"):
        new_skill.create("notes", "repo", "Use when x", cwd=repo, approve=lambda plan: True)
    assert not (repo / ".claude").exists() and not (repo / ".agents").exists()


def test_a_declined_plan_writes_nothing(repo):
    targets.set_agents({"claude": True, "codex": False})
    seen = []
    lines = new_skill.create("notes", "repo", "Use when x", cwd=repo, approve=lambda plan: seen.append(plan) or False)
    assert lines == ["nothing changed"] and not (repo / ".claude").exists()
    assert any("create  .claude/skills/notes/SKILL.md" in l for l in seen[0])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_new_skill_repo_plan.py`
Expected: FAIL (`unexpected keyword argument 'approve'`).

- [ ] **Step 3: Implement**

`create(..., approve=None)` passes `approve` to `_repo`. At the start of `_repo`, after `root` is found:

```python
    from . import project as project_mod, repo_config
    try:
        cfg = repo_config.load(root)
    except repo_config.Invalid as exc:
        raise Refused(str(exc)) from None
    if not cfg.manage:
        raise Refused(project_mod.MANAGE_OFF)
```

After the existing checks, build the plan with a `RepoWrites(root)`: `w.create(src_root / name / "SKILL.md", stub(name, description), "your new repo skill")` and, when `dest_root` is set, `w.link(dest_root / name, os.path.join("..", "..", ".claude", "skills", name), f"skill {name} for Codex")`. If `approve` is given and `approve(w.render())` is false, return `["nothing changed"]`. Otherwise `problems = w.apply(bk)`; return the same success lines as today (and the `not linked for Codex` line when `problems` names the link). Keep `_write` for the global and profile branches.

In `commands.py` add `p.add_argument("--yes", action="store_true", help="with new skill --to repo: create it without asking (needed without a terminal)")`, print the plan through the approver for `--to repo`:

```python
            approve = None
            if a.to == "repo":
                from . import project, ui
                ask_yes = project.approver(a.yes, _ask, ui.is_interactive())
                def approve(plan):
                    print("\n".join(plan))
                    return ask_yes(plan)
            lines = new_skill.create(a.name, a.to, a.description, bk=bk, approve=approve)
```

and print the backup/undo line only when `not bk.empty`.

- [ ] **Step 4: Run the tests, then the suite**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_new_skill_repo_plan.py tests/test_new_skill.py tests/test_new_skill_cli.py`
Expected: PASS (update CLI tests that ran `--to repo` without a terminal to pass `--yes`; ledger the ruling).
Run: `uv run --python 3.12 --with pytest pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
/usr/bin/git add cli/loadout/new_skill.py cli/loadout/commands.py tests
/usr/bin/git commit -m "feat(repo): a new repo skill follows the repo's agents, shows its plan and asks"
```

---

### Task 7: ADR 0030 and the docs for this PR

**Files:**
- Create: `docs/adr/0030-repo-files-follow-the-repos-agents.md`
- Modify (lines from the baseline, categories A, C, D, F, G): `README.md`, `AGENTS.md`, `CONTRIBUTING.md`, `docs/README.md`, `docs/tutorials/getting-started.md`, `docs/how-to/{setups,codex,write-a-profile,undo-and-restore,troubleshooting,your-own-tools,install-with-an-agent,ask-about-loadout,uninstall}.md`, `docs/reference/{cli,profile-format,personal-layer}.md`, `docs/explanation/{architecture,security-and-trust,documentation-strategy}.md`, `docs/adr/README.md`, `docs/adr/0027-…md` (status), `docs/adr/0012-…md` (status note), `plugins/loadout/skills/configure/SKILL.md` (rows 26, 33), `plugins/loadout/skills/onboard/SKILL.md:33`, `.serena/memories/architecture.md`
- Test: the existing docs tests (`tests/test_docs_links.py`, `tests/test_repo_static.py`)

**Interfaces:**
- Consumes: the messages and flags of Tasks 2–6, exactly as implemented.

- [ ] **Step 1: Write ADR 0030**

```markdown
# 0030. Repo files follow the repo's agents

- Status: Accepted
- Date: 2026-10-16
- Source: [Design: repos for chosen agents](../superpowers/specs/2026-10-16-repo-agents-and-careful-ux-design.md), Parts 0 and 1
- Supersedes: the decision line of [ADR 0027](0027-repo-files-follow-the-agents.md) ("A repo gets the files of the agents that are on")

## Context

ADR 0027 made a repo's files follow the agents that are on for whoever runs loadout. In a repo shared by a user with both agents and a teammate with Codex only, the teammate's runs never kept Claude Code's files current, and a user with both agents could not keep a repo Codex-only. Repo writes had no preview and no backup: `loadout restore` did not undo them, and `--dry-run` left out the settings.

## Decision

- A committed `.loadout.json` at the repo root names the repo's agents (`"agents": ["claude", "codex"]`). `init`, `profile` and `configure new skill --to repo` write the files of those agents, whichever agents are on for the user. Without the file, the user's agents decide, and the first `init` or `profile` adds the file to its plan.
- Commands and installs follow the user: a repo agent that is off for the user gets its files, not its installs; loadout says which.
- `"manage": false` makes every loadout command refuse to write in the repo; it prints the plan instead.
- Every repo write is a plan first. In a terminal loadout asks `Apply these changes? [y/N]`; without one it writes only with `--yes`. Applying saves a copy of every changed file and records every created one in a backup that names the repo; `loadout restore` undoes it.
- A repo JSON file is rewritten only in the exact layout it has (indentation, line endings); any other file is left and its entries printed.

## Alternatives considered

- Keep 0027: the teammate case and Codex-only repos stay impossible.
- A per-machine record of repo agents: each teammate's loadout knows only their own agents.
- Grow the committed list with every run: a Codex-only repo stops being Codex-only once a both-agents user runs loadout there.

## Consequences

- Narrowing a repo's agents removes nothing; loadout lists the files no longer needed.
- A profile's `commands` change what they change; the plan says restore cannot undo them.
- The rest of ADR 0027 stands (one real skill folder, links between them, nothing moved or deleted).

## In the code

- `cli/loadout/repo_config.py`, `cli/loadout/repo_writes.py`
- `cli/loadout/project.py` (`add_profile`, `init`, `approver`), `cli/loadout/profiles.py`, `cli/loadout/scaffold.py`, `cli/loadout/codex_project.py`, `cli/loadout/new_skill.py`
```

- [ ] **Step 2: Update each baseline line of categories A, C, D, F, G**

Walk `docs/superpowers/plans/2026-10-16-repo-agents-docs-baseline.md` top to bottom; for each row with A, C, D, F or G, change the line in place to the behaviour of Tasks 2–6 (one home per fact: the full rules go to `docs/reference/cli.md` (init, profile, `.loadout.json`) and `docs/reference/profile-format.md`; other pages state the one sentence they need and link there). Rows with only B (PR 2) or E (PR 4) stay. Mark ADR 0027's status `Accepted; its decision line is superseded by [0030](0030-repo-files-follow-the-repos-agents.md)` and add the 0030 row to `docs/adr/README.md`; ADR 0012 gets a status note that repo writes are previewed and backed up since 0030. `AGENTS.md`: ADR range 0001-0030, the map gains `repo_config.py` (`.loadout.json`) and `repo_writes.py` (repo writes as a plan, applied with a backup), and the "agent turned off" rule says "the user's agent folders (`~/.claude`, `~/.codex`); repo files follow `.loadout.json` (ADR 0030)". The configure and onboard skills: without a terminal run `--dry-run`, show the plan, then `--yes` after the user's yes; `--agents` for `init`. The agent page's last step: `loadout init --dry-run --agents …`, then `--yes` after a yes.

- [ ] **Step 3: Run the docs tests and the suite; validate the plugin**

Run: `uv run --python 3.12 --with pytest pytest -q`
Expected: PASS.
Run: `claude plugin validate . && claude plugin validate plugins/loadout`
Expected: `Validation passed` for both.

- [ ] **Step 4: Commit**

```bash
/usr/bin/git add docs README.md AGENTS.md CONTRIBUTING.md plugins .serena
/usr/bin/git commit -m "docs: repo files follow the repo's agents, and every repo write is previewed and undoable (ADR 0030)"
```
