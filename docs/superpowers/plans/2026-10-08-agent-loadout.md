# agent-loadout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `agent-loadout`: a shareable, self-updating Claude Code setup (plugin marketplace + CLI + rules + profiles + skills), the author's personal layer, and cut the author's machine over to it.

**Architecture:**
- The kit repo is a Claude Code plugin marketplace that delivers `loadout` (hooks, MCP config, skills). Plugins update through marketplace auto-update.
- A stdlib-only Python CLI (`loadout`) does everything plugins can't do:
  - three-way merge of kit-managed keys into `~/.claude/settings.json`;
  - linking rule directories;
  - adopting existing configs against a catalog, with backup/restore;
  - project init and profiles;
  - checks, updates, and the daily/weekly maintenance triggered by a SessionStart hook.
- The personal layer is a separate folder/repo overlaid on the kit.

**Tech Stack:** Python ≥3.10 (stdlib only), pytest (via `uv run --with pytest`), bash + PowerShell shims, Claude Code plugin/marketplace JSON, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-08-agent-loadout-design.md`

## Global Constraints

- Repo root: `/home/jonas/Documents/Code/agent-loadout`. All paths below are relative to it unless absolute.
- Always invoke the CLI via `bin/loadout` (it imports `loadout.__main__` as a module; `python -m loadout` would load `__main__` twice and lose subcommand registrations).
- Python ≥3.10, **stdlib only** in `cli/loadout/`. Tests: `uv run --python 3.12 --with pytest pytest -q`.
- **Every subprocess goes through `loadout.runner.run` / `runner.have`**, called as `runner.run(...)` after `from . import runner`. Never use `from .runner import run`: tests monkeypatch the module attribute.
- Every path comes from `loadout.paths` functions, which read `HOME`/`USERPROFILE` at call time. No module-level path constants derived from home.
- Never delete user data: anything removed is moved into a `Backup` (`cli/loadout/backup.py`) with an undo step.
- JSON written by the kit: 2-space indent, trailing newline, `ensure_ascii=False`.
- Marketplace name `agent-loadout`, plugin `loadout`, GitHub repo `jonasyr/agent-loadout`. Plugin MCP tool prefix `mcp__plugin_loadout_serena__`.
- Pinned versions: `@bytebase/dbhub@1.4.0`, `chrome-devtools-mcp@1.10.1`.
- `loadout/.claude-plugin/plugin.json` has **no** `version` field.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Hooks must exit 0 silently when their binary is missing.

## Review Focus

1. **`~/.claude/settings.json` contains invalid JSON** (hand-edited). Expect: `apply-settings`, `check` and `adopt` stop with "invalid JSON in <path>: <error>" and write nothing. Test in Task 2.
2. **Bootstrap re-run after a partial failure.** Expect: no duplicate shell-rc lines, no second backup of already-linked paths, no duplicate plugin installs. Tests in Tasks 5 and 10.
3. **Home or repo path containing spaces** (e.g. a Windows user "Max Mustermann"). Expect: shims and hook commands are quoted and still work. Test in Task 5 (`link_bin` shim quoting).
4. **No network or a GitHub rate limit during version checks.** Expect: maintenance and `update` treat the latest version as unknown and never crash or print a traceback. Test in Task 9.
5. **User edited a kit-managed value directly in `settings.json`** (e.g. turned off a kit plugin). Expect: `check` reports drift with the hint "put overrides in <personal>/settings.json"; the merge re-applies the kit value. Test in Task 8.

---

### Task 1: Repo skeleton, paths, JSON helpers, runner, test harness

**Files:**
- Create: `cli/loadout/__init__.py`, `cli/loadout/paths.py`, `cli/loadout/jsonio.py`, `cli/loadout/runner.py`, `tests/conftest.py`, `tests/test_jsonio.py`, `pyproject.toml`, `.gitignore`

**Interfaces:**
- Produces:
  - `paths.kit_root() -> Path`, `paths.home() -> Path`, `paths.claude_home() -> Path`, `paths.claude_json() -> Path`, `paths.state_dir() -> Path`, `paths.backups_root() -> Path`, `paths.personal_root() -> Path`, `paths.secrets_file() -> Path`, `paths.bin_dir() -> Path`, `paths.platform_key() -> str` (`"windows"|"posix"`)
  - `jsonio.load_json(path: Path) -> dict` (raises `jsonio.InvalidJSON`), `jsonio.save_json(path: Path, data: dict) -> None`, `jsonio.deep_merge(base, overlay)`
  - `runner.Result(returncode, stdout, stderr)` with `.ok`; `runner.run(cmd: list[str], cwd: str|None=None, timeout: float=300) -> Result`; `runner.have(binary: str) -> bool`
  - fixtures `fake_home`, `fake_runner` (with `.calls`, `.responses`, `.missing`), `kit_root`

- [ ] **Step 1: Create skeleton files**

`pyproject.toml`:
```toml
[project]
name = "agent-loadout"
version = "0.0.0"
requires-python = ">=3.10"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["cli"]
```

`.gitignore`:
```
__pycache__/
.pytest_cache/
secrets.env
.loadout/
```

`cli/loadout/__init__.py`:
```python
"""loadout: shareable Claude Code setup manager."""
```

- [ ] **Step 2: Write the failing tests**

`tests/conftest.py`:
```python
import pytest

from loadout import runner


class FakeRunner:
    """Records commands; returns canned results matched by command prefix."""

    def __init__(self):
        self.calls = []
        self.responses = {}
        self.missing = set()

    def __call__(self, cmd, cwd=None, timeout=300):
        self.calls.append(list(cmd))
        for prefix, result in self.responses.items():
            if tuple(cmd[: len(prefix)]) == prefix:
                return result
        return runner.Result(0, "", "")

    def have(self, binary):
        return binary not in self.missing


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("LOADOUT_PERSONAL", raising=False)
    return home


@pytest.fixture
def fake_runner(monkeypatch):
    fake = FakeRunner()
    monkeypatch.setattr(runner, "run", fake)
    monkeypatch.setattr(runner, "have", fake.have)
    return fake


@pytest.fixture
def kit_root():
    from loadout import paths
    return paths.kit_root()
```

`tests/test_jsonio.py`:
```python
import pytest

from loadout import jsonio, paths


def test_deep_merge_nested_dicts_overlay_wins():
    base = {"a": {"x": 1, "y": 2}, "b": 1}
    overlay = {"a": {"y": 3, "z": 4}}
    assert jsonio.deep_merge(base, overlay) == {"a": {"x": 1, "y": 3, "z": 4}, "b": 1}


def test_deep_merge_lists_union_preserving_order():
    assert jsonio.deep_merge({"l": [1, 2]}, {"l": [2, 3]}) == {"l": [1, 2, 3]}


def test_deep_merge_does_not_mutate_inputs():
    base = {"a": {"x": 1}}
    jsonio.deep_merge(base, {"a": {"y": 2}})
    assert base == {"a": {"x": 1}}


def test_load_missing_and_empty_file_is_empty_dict(tmp_path):
    assert jsonio.load_json(tmp_path / "nope.json") == {}
    (tmp_path / "empty.json").write_text("  \n")
    assert jsonio.load_json(tmp_path / "empty.json") == {}


def test_load_invalid_json_raises_with_path(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{ not json")
    with pytest.raises(jsonio.InvalidJSON) as err:
        jsonio.load_json(bad)
    assert str(bad) in str(err.value)


def test_save_json_format(tmp_path):
    target = tmp_path / "sub" / "x.json"
    jsonio.save_json(target, {"ü": 1})
    assert target.read_text(encoding="utf-8") == '{\n  "ü": 1\n}\n'


def test_paths_follow_home(fake_home):
    assert paths.claude_home() == fake_home / ".claude"
    assert paths.personal_root() == fake_home / ".config" / "loadout" / "personal"
    assert paths.secrets_file() == fake_home / ".config" / "loadout" / "secrets.env"


def test_personal_root_env_override(fake_home, monkeypatch, tmp_path):
    monkeypatch.setenv("LOADOUT_PERSONAL", str(tmp_path / "p"))
    assert paths.personal_root() == tmp_path / "p"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run --python 3.12 --with pytest pytest -q`
Expected: FAIL / errors with `ModuleNotFoundError: loadout.jsonio` (or `runner`).

- [ ] **Step 4: Implement**

`cli/loadout/paths.py`:
```python
"""Filesystem locations. Everything derives from HOME at call time so tests can redirect it."""
from __future__ import annotations

import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent


def kit_root() -> Path:
    env = os.environ.get("LOADOUT_ROOT")
    return Path(env).expanduser().resolve() if env else PACKAGE_DIR.parent.parent


def home() -> Path:
    return Path(os.environ.get("HOME") or os.environ.get("USERPROFILE") or Path.home())


def claude_home() -> Path:
    return home() / ".claude"


def claude_json() -> Path:
    return home() / ".claude.json"


def state_dir() -> Path:
    return claude_home() / ".loadout"


def backups_root() -> Path:
    return claude_home() / "backups"


def personal_root() -> Path:
    env = os.environ.get("LOADOUT_PERSONAL")
    return Path(env).expanduser() if env else home() / ".config" / "loadout" / "personal"


def secrets_file() -> Path:
    return home() / ".config" / "loadout" / "secrets.env"


def bin_dir() -> Path:
    return home() / ".local" / "bin"


def platform_key() -> str:
    return "windows" if os.name == "nt" else "posix"
```

`cli/loadout/jsonio.py`:
```python
"""JSON load/save and deep merge."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


class InvalidJSON(Exception):
    pass


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise InvalidJSON(f"invalid JSON in {path}: {exc}") from exc


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def deep_merge(base: Any, overlay: Any) -> Any:
    """Dicts merge recursively, lists union (order kept), anything else: overlay wins."""
    if isinstance(base, dict) and isinstance(overlay, dict):
        out = copy.deepcopy(base)
        for key, value in overlay.items():
            out[key] = deep_merge(out[key], value) if key in out else copy.deepcopy(value)
        return out
    if isinstance(base, list) and isinstance(overlay, list):
        return copy.deepcopy(base) + [copy.deepcopy(x) for x in overlay if x not in base]
    return copy.deepcopy(overlay)
```

`cli/loadout/runner.py`:
```python
"""The single place where loadout runs external commands (tests replace run/have)."""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


@dataclass
class Result:
    returncode: int
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def have(binary: str) -> bool:
    return shutil.which(binary) is not None


def run(cmd: list[str], cwd: str | None = None, timeout: float = 300) -> Result:
    exe = shutil.which(cmd[0])
    if exe is None:
        return Result(127, "", f"{cmd[0]}: not found")
    try:
        proc = subprocess.run([exe, *cmd[1:]], cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return Result(124, "", f"{cmd[0]}: timed out after {timeout}s")
    return Result(proc.returncode, proc.stdout, proc.stderr)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run --python 3.12 --with pytest pytest -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: CLI skeleton with paths, JSON helpers and runner

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Three-way settings merge

**Files:**
- Create: `cli/loadout/settings_merge.py`, `tests/test_settings_merge.py`

**Interfaces:**
- Consumes: `jsonio.load_json/save_json/deep_merge/InvalidJSON`, `paths.kit_root/personal_root/claude_home/state_dir`
- Produces:
  - `settings_merge.merge_settings(current: dict, desired: dict, previous: dict) -> dict`
  - `settings_merge.desired_settings() -> dict`
  - `settings_merge.apply_settings() -> tuple[dict, dict]` (before, after)
  - `settings_merge.drift() -> list[str]` (slash-joined key paths)
  - `settings_merge.leaves(d: dict) -> Iterator[tuple[tuple, Any]]`, `settings_merge.get_path(d, path)`, `settings_merge.MISSING`

- [ ] **Step 1: Write the failing tests**

`tests/test_settings_merge.py`:
```python
import json

import pytest

from loadout import jsonio, settings_merge as sm


def test_adds_desired_keys_and_keeps_user_keys():
    current = {"model": "opus", "enabledPlugins": {"mine@x": True}}
    desired = {"enabledPlugins": {"loadout@agent-loadout": True}}
    out = sm.merge_settings(current, desired, {})
    assert out == {"model": "opus", "enabledPlugins": {"mine@x": True, "loadout@agent-loadout": True}}


def test_removes_value_the_kit_dropped_when_unchanged_by_user():
    previous = {"enabledPlugins": {"old@m": True, "keep@m": True}}
    current = {"enabledPlugins": {"old@m": True, "keep@m": True}}
    desired = {"enabledPlugins": {"keep@m": True}}
    assert sm.merge_settings(current, desired, previous) == {"enabledPlugins": {"keep@m": True}}


def test_keeps_value_the_kit_dropped_when_user_changed_it():
    previous = {"effortLevel": "medium"}
    current = {"effortLevel": "high"}
    assert sm.merge_settings(current, {}, previous) == {"effortLevel": "high"}


def test_prunes_empty_parents_after_removal():
    previous = {"a": {"b": {"c": 1}}}
    assert sm.merge_settings({"a": {"b": {"c": 1}}}, {}, previous) == {}


def test_list_items_dropped_by_kit_are_removed_user_items_kept():
    previous = {"permissions": {"allow": ["Bash(a:*)", "Bash(b:*)"]}}
    current = {"permissions": {"allow": ["Bash(a:*)", "Bash(b:*)", "Bash(user:*)"]}}
    desired = {"permissions": {"allow": ["Bash(a:*)"]}}
    out = sm.merge_settings(current, desired, previous)
    assert out == {"permissions": {"allow": ["Bash(a:*)", "Bash(user:*)"]}}


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def test_apply_settings_writes_result_and_snapshot(fake_home, monkeypatch, tmp_path):
    kit = tmp_path / "kit"
    _write(kit / "settings.base.json", {"enabledPlugins": {"loadout@agent-loadout": True}})
    _write(fake_home / ".config/loadout/personal/settings.json", {"effortLevel": "medium"})
    _write(fake_home / ".claude/settings.json", {"model": "opus"})
    monkeypatch.setenv("LOADOUT_ROOT", str(kit))
    before, after = sm.apply_settings()
    assert before == {"model": "opus"}
    assert after == {"model": "opus", "enabledPlugins": {"loadout@agent-loadout": True}, "effortLevel": "medium"}
    snap = jsonio.load_json(fake_home / ".claude/.loadout/managed-settings.json")
    assert snap == {"enabledPlugins": {"loadout@agent-loadout": True}, "effortLevel": "medium"}


def test_apply_settings_refuses_invalid_json_and_writes_nothing(fake_home, monkeypatch, tmp_path):
    kit = tmp_path / "kit"
    _write(kit / "settings.base.json", {"a": 1})
    monkeypatch.setenv("LOADOUT_ROOT", str(kit))
    target = fake_home / ".claude/settings.json"
    target.parent.mkdir(parents=True)
    target.write_text("{ broken")
    with pytest.raises(jsonio.InvalidJSON):
        sm.apply_settings()
    assert target.read_text() == "{ broken"
    assert not (fake_home / ".claude/.loadout/managed-settings.json").exists()


def test_drift_lists_paths_differing_from_desired(fake_home, monkeypatch, tmp_path):
    kit = tmp_path / "kit"
    _write(kit / "settings.base.json", {"enabledPlugins": {"a@m": True, "b@m": True}, "permissions": {"allow": ["X"]}})
    _write(fake_home / ".claude/settings.json", {"enabledPlugins": {"a@m": True, "b@m": False}, "permissions": {"allow": ["X", "Y"]}})
    monkeypatch.setenv("LOADOUT_ROOT", str(kit))
    assert sm.drift() == ["enabledPlugins/b@m"]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_settings_merge.py`
Expected: FAIL with `ModuleNotFoundError: loadout.settings_merge`.

- [ ] **Step 3: Implement**

`cli/loadout/settings_merge.py`:
```python
"""Three-way merge of kit-managed keys into ~/.claude/settings.json (spec §6.3).

desired  = settings.base.json (kit) overlaid with <personal>/settings.json
previous = snapshot of what the kit applied last time
current  = the user's settings.json
Desired values win; values the kit applied before but no longer wants are removed
only if the user did not change them; everything else in current is left alone.
"""
from __future__ import annotations

import copy
from typing import Any, Iterator

from . import paths
from .jsonio import deep_merge, load_json, save_json

MISSING = object()


def leaves(d: dict, prefix: tuple = ()) -> Iterator[tuple[tuple, Any]]:
    for key, value in d.items():
        if isinstance(value, dict) and value:
            yield from leaves(value, prefix + (key,))
        else:
            yield prefix + (key,), value


def get_path(d: Any, path: tuple) -> Any:
    for key in path:
        if not isinstance(d, dict) or key not in d:
            return MISSING
        d = d[key]
    return d


def _set_path(d: dict, path: tuple, value: Any) -> None:
    for key in path[:-1]:
        d = d.setdefault(key, {})
    d[path[-1]] = value


def _delete_path(d: dict, path: tuple) -> None:
    chain = []
    node = d
    for key in path[:-1]:
        chain.append((node, key))
        node = node[key]
    del node[path[-1]]
    for parent, key in reversed(chain):
        if parent[key] == {}:
            del parent[key]
        else:
            break


def merge_settings(current: dict, desired: dict, previous: dict) -> dict:
    result = deep_merge(copy.deepcopy(current), desired)
    for path, prev_value in leaves(previous):
        if get_path(current, path) is MISSING:
            continue
        wanted = get_path(desired, path)
        now = get_path(result, path)
        if isinstance(prev_value, list) and isinstance(now, list):
            keep = wanted if isinstance(wanted, list) else []
            dropped = [x for x in prev_value if x not in keep]
            pruned = [x for x in now if x not in dropped]
            if pruned or wanted is not MISSING:
                _set_path(result, path, pruned)
            else:
                _delete_path(result, path)
        elif wanted is MISSING and get_path(current, path) == prev_value:
            _delete_path(result, path)
    return result


def desired_settings() -> dict:
    base = load_json(paths.kit_root() / "settings.base.json")
    personal = load_json(paths.personal_root() / "settings.json")
    return deep_merge(base, personal)


def _target():
    return paths.claude_home() / "settings.json"


def _snapshot():
    return paths.state_dir() / "managed-settings.json"


def apply_settings() -> tuple[dict, dict]:
    current = load_json(_target())  # raises InvalidJSON before anything is written
    desired = desired_settings()
    after = merge_settings(current, desired, load_json(_snapshot()))
    if after != current:
        save_json(_target(), after)
    save_json(_snapshot(), desired)
    return current, after


def drift() -> list[str]:
    current = load_json(_target())
    out = []
    for path, value in leaves(desired_settings()):
        now = get_path(current, path)
        if isinstance(value, list) and isinstance(now, list):
            if all(x in now for x in value):
                continue
        elif now == value:
            continue
        out.append("/".join(path))
    return out
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_settings_merge.py`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: three-way merge of kit-managed settings

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Static kit content (settings base, rules, profiles, templates, catalog)

**Files:**
- Create: `settings.base.json`, `rules/tooling.md`, `rules/docs-policy.md`, `rules/memory-policy.md`, `rules/workflow.md`, `rules/rtk.md`, `profiles/{thesis,sonar,db,web,android}.json`, `templates/project/AGENTS.md`, `templates/project/CLAUDE.md`, `templates/project/docs/README.md`, `templates/project/docs/adr/README.md`, `templates/personal/rules/me.md`, `templates/personal/settings.json`, `catalog.json`, `secrets.env.example`, `tests/test_repo_static.py`

**Interfaces:**
- Produces:
  - profile JSON schema `{description: str, settings?: dict, mcp?: dict, install?: [plugin-id], commands?: [[argv]], notes?: str}`
  - catalog schema `{"entries": [entry]}` with entry keys `id, kind, match{names[], contains[]}, status, profile?, by?, reason, required?, version?{cmd, github|npm|pypi}, install?{posix, windows}, update?{posix, windows}, manual?`
  - templates use `{{PROJECT_NAME}}` (project) and `{{NAME}} {{ROLE}} {{LANGUAGES}} {{PREFERENCES}}` (personal)

- [ ] **Step 1: Write the failing static tests**

`tests/test_repo_static.py`:
```python
import json
import re
import subprocess

from loadout import paths

ROOT = paths.kit_root()
STATUSES = {"core", "profile", "superseded", "deprecated", "recommended", "alternative", "system", "review"}
KINDS = {"mcp", "plugin", "marketplace", "skill", "hook", "binary"}


def _json(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def test_all_json_files_parse():
    for path in ROOT.rglob("*.json"):
        if ".git" in path.parts:
            continue
        json.loads(path.read_text(encoding="utf-8"))


def _declared_marketplaces():
    return set(_json("settings.base.json")["extraKnownMarketplaces"]) | {"claude-plugins-official"}


def test_settings_base_plugins_reference_declared_marketplaces():
    base = _json("settings.base.json")
    for plugin_id in base["enabledPlugins"]:
        assert plugin_id.split("@")[1] in _declared_marketplaces(), plugin_id
    for name, cfg in base["extraKnownMarketplaces"].items():
        assert cfg.get("autoUpdate") is True, name


def test_profiles_are_well_formed():
    for path in (ROOT / "profiles").glob("*.json"):
        prof = json.loads(path.read_text(encoding="utf-8"))
        assert prof["description"]
        assert set(prof) <= {"description", "settings", "mcp", "install", "commands", "notes"}, path
        for plugin_id in prof.get("install", []):
            assert plugin_id.split("@")[1] in _declared_marketplaces(), plugin_id
        for server in prof.get("mcp", {}).get("mcpServers", {}).values():
            for arg in server.get("args", []):
                assert "@latest" not in arg, f"unpinned version in {path}"


def test_catalog_entries_are_well_formed():
    entries = _json("catalog.json")["entries"]
    ids = [e["id"] for e in entries]
    assert len(ids) == len(set(ids)), "duplicate catalog ids"
    for e in entries:
        assert e["kind"] in KINDS, e["id"]
        assert e["status"] in STATUSES, e["id"]
        assert e["reason"], e["id"]
        assert e["match"].get("names") or e["match"].get("contains"), e["id"]
        if e["status"] == "profile":
            assert (ROOT / "profiles" / f"{e['profile']}.json").exists(), e["id"]
        if e["kind"] == "binary":
            assert "version" in e and "cmd" in e["version"], e["id"]


def test_rules_and_templates_exist():
    for name in ("tooling", "docs-policy", "memory-policy", "workflow", "rtk"):
        assert (ROOT / "rules" / f"{name}.md").read_text(encoding="utf-8").strip()
    assert "{{PROJECT_NAME}}" in (ROOT / "templates/project/AGENTS.md").read_text(encoding="utf-8")
    assert (ROOT / "templates/project/CLAUDE.md").read_text(encoding="utf-8").strip() == "@AGENTS.md"


SECRET_PATTERNS = [
    r"gh[pousr]_[A-Za-z0-9]{20,}", r"github_pat_[A-Za-z0-9_]{20,}", r"sk-[A-Za-z0-9_-]{20,}",
    r"apk_[A-Za-z0-9_=-]{16,}", r"xox[baprs]-[A-Za-z0-9-]{10,}", r"AKIA[0-9A-Z]{16}",
]


def test_no_secrets_in_tracked_files():
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    for rel in files:
        path = ROOT / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in SECRET_PATTERNS:
            assert not re.search(pattern, text), f"possible secret in {rel}"
    assert "secrets.env" not in files
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_repo_static.py`
Expected: FAIL (`FileNotFoundError: settings.base.json` etc.).

- [ ] **Step 3: Create the content files**

`settings.base.json`:
```json
{
  "$schema": "https://json.schemastore.org/claude-code-settings.json",
  "extraKnownMarketplaces": {
    "agent-loadout": { "source": { "source": "github", "repo": "jonasyr/agent-loadout" }, "autoUpdate": true },
    "impeccable": { "source": { "source": "github", "repo": "pbakaus/impeccable" }, "autoUpdate": true },
    "academic-research-skills": { "source": { "source": "github", "repo": "Imbad0202/academic-research-skills" }, "autoUpdate": true }
  },
  "enabledPlugins": {
    "loadout@agent-loadout": true,
    "superpowers@claude-plugins-official": true,
    "frontend-design@claude-plugins-official": true,
    "impeccable@impeccable": true,
    "commit-commands@claude-plugins-official": true,
    "security-guidance@claude-plugins-official": true,
    "claude-md-management@claude-plugins-official": true,
    "pyright-lsp@claude-plugins-official": true,
    "typescript-lsp@claude-plugins-official": true,
    "rust-analyzer-lsp@claude-plugins-official": true,
    "context7@claude-plugins-official": true,
    "microsoft-docs@claude-plugins-official": true
  }
}
```

`rules/tooling.md`:
```markdown
# Tool routing (loadout)

Pick the tool by the question, not by habit:

| Need | Use |
|---|---|
| Structure: who calls X, call chains, architecture, dead code, impact of a change | codebase-memory-mcp (`search_graph`, `trace_path`, `get_architecture`, `query_graph`). If the repo is not indexed yet, run `index_repository` first. |
| Exact symbol work: find a definition or its references, rename, replace a function body, insert next to a symbol | Serena symbolic tools |
| Type errors and diagnostics | LSP plugins report them automatically after edits; fix them before moving on |
| Text, config files, docs, non-code | Grep / Glob / Read |
| Library or framework documentation | Context7 first; Microsoft Learn for .NET/Azure/Windows/Microsoft APIs; web search last |
| UI verification and browser checks | `playwright-cli` (read `playwright-cli --help` first); screenshots and snapshots go to disk, open only what you need |
| Shell commands | rtk rewrites them automatically when installed; use `rtk proxy <cmd>` when you need raw output |

Before ending a task that touched UI, verify it in a browser with playwright-cli. Never claim it "looks right" without having looked.
```

`rules/docs-policy.md`:
```markdown
# Documentation layers (loadout)

Every fact has exactly one home. Other layers link to it instead of copying it.

| Layer | Holds | Rule |
|---|---|---|
| `docs/` | Everything a human may need: concepts, architecture, how-tos, reference; decisions as ADRs in `docs/adr/` | Single source of truth |
| `AGENTS.md` (and `CLAUDE.md` containing only `@AGENTS.md`) | Purpose, commands, hard conventions, and a map of `docs/` and memories | Short and hand-curated; never copy docs content into it |
| `.serena/memories/` | Agent working notes: per topic a 1–3 line summary plus a link into `docs/`; gotchas; debugging lessons; "to do X, touch these files"; current status | Never the only home of a fact a human would need |
| `README.md` | What the project is, how to install and run it | Human entry point; links into `docs/` |

When you change behaviour, update the layer that owns the fact (usually `docs/`), then fix links. At the end of a feature, run `/loadout:docs-sync`. For a full verification and cleanup, run `/loadout:docs-audit`.
```

`rules/memory-policy.md`:
```markdown
# Memory policy (loadout)

| Store | Use for | Never use for |
|---|---|---|
| Serena memories (in repo, committed) | Project working notes and an index into `docs/` (see docs-policy) | Copies of docs content |
| Claude Code auto memory (`~/.claude/projects/...`, this machine only) | Temporary or machine-specific notes | Project facts (they belong in the repo) or personal preferences |
| Personal layer (`~/.claude/rules/personal/`) | The user's preferences and working style | Project facts |

If you learn a durable project fact, write it to `docs/` and link it from a memory. If you learn a durable preference of the user, propose adding it to their personal layer rather than storing it in auto memory.
When Serena onboarding writes memories, keep each one a short summary plus links into `docs/`.
```

`rules/workflow.md`:
```markdown
# Workflow (loadout)

- Use the superpowers process skills: brainstorming before building, writing-plans for multi-step work, systematic-debugging for bugs, verification-before-completion before claiming success.
- One review pass per change: either `/code-review` or superpowers requesting-code-review, not both. Run `/security-review` before merging security-relevant changes (auth, input handling, secrets, network exposure).
- UI loop: frontend-design for direction → build → playwright-cli (render at 320, 768 and 1280 px wide, exercise the main flows, read the console) → `/impeccable audit` then `/impeccable polish`. UI is not done until it was checked in a browser.
- At the end of a feature run `/loadout:docs-sync`.
- Domain tools (academic research, SonarQube, databases, Android) are enabled per project with `loadout profile <name>`; do not install them globally.
- New repo or repo without AGENTS.md: suggest `loadout init` and `/loadout:onboard`.
```

`rules/rtk.md` (content of the current `~/.claude/RTK.md`, generalized):
```markdown
# rtk (loadout)

Applies only when the `rtk` command exists. rtk is a token-optimizing CLI proxy; a hook rewrites shell commands through it automatically.

- `rtk gain` shows token savings; `rtk gain --history` shows command history with savings.
- `rtk discover` analyses Claude Code history for missed opportunities.
- `rtk proxy <cmd>` runs a command without filtering (use it when you need raw, complete output).
- If `rtk gain` fails, the wrong `rtk` (Rust Type Kit) may be installed.
```

`profiles/thesis.json`:
```json
{
  "description": "Academic writing and ML/RAG research",
  "install": [
    "academic-research-skills@academic-research-skills",
    "deepeval@claude-plugins-official",
    "huggingface-skills@claude-plugins-official"
  ],
  "settings": {
    "enabledPlugins": {
      "academic-research-skills@academic-research-skills": true,
      "deepeval@claude-plugins-official": true,
      "huggingface-skills@claude-plugins-official": true
    }
  },
  "notes": "Prefer the targeted ARS modes (/ars-lit-review, /ars-citation-check, /ars-reviewer); a full /ars-full pipeline run costs a few dollars. Literature search: Scholar Gateway connector or the deep-research skill."
}
```

`profiles/sonar.json`:
```json
{
  "description": "SonarQube static analysis",
  "install": ["sonarqube@claude-plugins-official"],
  "settings": { "enabledPlugins": { "sonarqube@claude-plugins-official": true } },
  "notes": "Needs the sonar CLI logged in (`sonar auth login`) and a sonar-project.properties. Optional secret-scanning hooks for this repo: run `sonar integrate` here."
}
```

`profiles/db.json`:
```json
{
  "description": "Database access via DBHub MCP",
  "mcp": {
    "mcpServers": {
      "dbhub": {
        "type": "stdio",
        "command": "npx",
        "args": ["-y", "@bytebase/dbhub@1.4.0", "--transport", "stdio", "--dsn", "${DATABASE_URL}"]
      }
    }
  },
  "notes": "Set DATABASE_URL in your shell or ~/.config/loadout/secrets.env. Use a read-only database user."
}
```

`profiles/web.json`:
```json
{
  "description": "Web UI work: Playwright skills, Chrome DevTools MCP (off by default)",
  "mcp": {
    "mcpServers": {
      "chrome-devtools": { "type": "stdio", "command": "npx", "args": ["-y", "chrome-devtools-mcp@1.10.1"] }
    }
  },
  "settings": { "disabledMcpjsonServers": ["chrome-devtools"] },
  "commands": [["playwright-cli", "install", "--skills"]],
  "notes": "chrome-devtools is for performance/network debugging; enable it in /mcp when needed. For E2E tests in the project itself, add @playwright/test as a dev dependency."
}
```

`profiles/android.json`:
```json
{
  "description": "Android / Kotlin",
  "install": ["kotlin-lsp@claude-plugins-official"],
  "settings": { "enabledPlugins": { "kotlin-lsp@claude-plugins-official": true } },
  "notes": "Requires the kotlin-lsp binary (see the plugin README)."
}
```

`templates/project/AGENTS.md`:
```markdown
# {{PROJECT_NAME}}

> Agent entry point. Keep it short: facts live in `docs/`; this file maps them. Run `/loadout:onboard` to fill it in.

## Purpose

(One paragraph: what this project is and who it is for.)

## Commands

| Task | Command |
|---|---|
| Install | |
| Test | |
| Run | |

## Conventions

(Hard rules only: language/tool versions, formatting, branch and commit conventions.)

## Map

- `docs/README.md` — documentation index (single source of truth)
- `docs/adr/` — architecture decision records
- `.serena/memories/` — agent working notes; each links into `docs/`
```

`templates/project/CLAUDE.md`:
```
@AGENTS.md
```

`templates/project/docs/README.md`:
```markdown
# {{PROJECT_NAME}} documentation

Single source of truth for this project. Agent files (`AGENTS.md`, `.serena/memories/`) link here instead of copying.

| Section | Contents |
|---|---|
| [adr/](adr/README.md) | Architecture decision records |
```

`templates/project/docs/adr/README.md`:
```markdown
# Architecture decision records

One file per decision: `NNNN-short-title.md` with the sections Context, Decision, Consequences, Status.
```

`templates/personal/rules/me.md`:
```markdown
# About me ({{NAME}})

- Role: {{ROLE}}
- Main languages and stacks: {{LANGUAGES}}
- Working preferences: {{PREFERENCES}}
```

`templates/personal/settings.json`:
```json
{}
```

`secrets.env.example`:
```
# Copied to ~/.config/loadout/secrets.env (mode 600) by loadout bootstrap.
# Loaded by your shell; reference values in MCP configs as ${NAME}.
# DATABASE_URL=postgres://readonly:password@localhost:5432/app
# SONAR_TOKEN=
```

`catalog.json`: the full catalog. Reasons are from the 2026-10-08 research:
```json
{
  "entries": [
    { "id": "claude", "kind": "binary", "status": "core", "required": true, "match": { "names": ["claude"] }, "reason": "Claude Code CLI.", "version": { "cmd": ["claude", "--version"], "npm": "@anthropic-ai/claude-code" }, "manual": "https://code.claude.com/docs/en/setup" },
    { "id": "git", "kind": "binary", "status": "core", "required": true, "match": { "names": ["git"] }, "reason": "Needed for marketplaces and repo sync.", "version": { "cmd": ["git", "--version"] }, "manual": "Install git with your package manager (Windows: Git for Windows, which also provides Git Bash for hooks)." },
    { "id": "uv", "kind": "binary", "status": "core", "required": true, "match": { "names": ["uv"] }, "reason": "Installs Serena and runs the kit tests.", "version": { "cmd": ["uv", "--version"], "github": "astral-sh/uv" },
      "install": { "posix": [["sh", "-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"]], "windows": [["powershell", "-NoProfile", "-Command", "irm https://astral.sh/uv/install.ps1 | iex"]] },
      "update": { "posix": [["uv", "self", "update"]], "windows": [["uv", "self", "update"]] } },
    { "id": "node", "kind": "binary", "status": "core", "required": true, "match": { "names": ["node"] }, "reason": "Runs npx-based MCP servers, LSP servers and playwright-cli.", "version": { "cmd": ["node", "--version"] }, "manual": "Install Node.js LTS (e.g. via mise, nvm or your package manager)." },
    { "id": "gh", "kind": "binary", "status": "core", "required": true, "match": { "names": ["gh"] }, "reason": "GitHub access; credentials for private marketplace updates. Preferred over a GitHub MCP server.", "version": { "cmd": ["gh", "--version"], "github": "cli/cli" }, "manual": "Install GitHub CLI, then `gh auth login` and `gh auth setup-git`." },
    { "id": "serena", "kind": "binary", "status": "core", "required": true, "match": { "names": ["serena"] }, "reason": "LSP-backed symbolic code navigation and editing (MCP server provided by loadout).", "version": { "cmd": ["serena", "--version"], "github": "oraios/serena" },
      "install": { "posix": [["uv", "tool", "install", "-p", "3.12", "serena-agent"]], "windows": [["uv", "tool", "install", "-p", "3.12", "serena-agent"]] },
      "update": { "posix": [["uv", "tool", "upgrade", "serena-agent"]], "windows": [["uv", "tool", "upgrade", "serena-agent"]] } },
    { "id": "codebase-memory-mcp", "kind": "binary", "status": "core", "required": true, "match": { "names": ["codebase-memory-mcp"] }, "reason": "Code knowledge graph for structure and call-chain questions (MCP server provided by loadout).", "version": { "cmd": ["codebase-memory-mcp", "--version"], "github": "DeusData/codebase-memory-mcp" },
      "install": { "posix": [["sh", "-c", "curl -fsSL https://raw.githubusercontent.com/DeusData/codebase-memory-mcp/main/install.sh | bash"]] },
      "update": { "posix": [["codebase-memory-mcp", "update", "-y"]], "windows": [["codebase-memory-mcp", "update", "-y"]] },
      "manual": "Windows: download the release archive from https://github.com/DeusData/codebase-memory-mcp/releases and run its install.ps1." },
    { "id": "rtk", "kind": "binary", "status": "recommended", "match": { "names": ["rtk"] }, "reason": "Token-optimizing shell proxy (60-90% savings on dev command output).", "version": { "cmd": ["rtk", "--version"], "github": "rtk-ai/rtk" },
      "install": { "posix": [["sh", "-c", "curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh | sh"]] },
      "update": { "posix": [["sh", "-c", "curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh | sh"]] },
      "manual": "Windows: see https://github.com/rtk-ai/rtk#installation." },
    { "id": "playwright-cli", "kind": "binary", "status": "core", "required": true, "match": { "names": ["playwright-cli"] }, "reason": "Browser automation for UI verification; keeps snapshots on disk (far fewer tokens than the Playwright MCP).", "version": { "cmd": ["playwright-cli", "--version"], "npm": "@playwright/cli" },
      "install": { "posix": [["npm", "install", "-g", "@playwright/cli@latest"]], "windows": [["npm", "install", "-g", "@playwright/cli@latest"]] },
      "update": { "posix": [["npm", "install", "-g", "@playwright/cli@latest"]], "windows": [["npm", "install", "-g", "@playwright/cli@latest"]] } },
    { "id": "pyright", "kind": "binary", "status": "recommended", "match": { "names": ["pyright"] }, "reason": "Language server for the pyright-lsp plugin.", "version": { "cmd": ["pyright", "--version"], "npm": "pyright" },
      "install": { "posix": [["npm", "install", "-g", "pyright"]], "windows": [["npm", "install", "-g", "pyright"]] },
      "update": { "posix": [["npm", "install", "-g", "pyright@latest"]], "windows": [["npm", "install", "-g", "pyright@latest"]] } },
    { "id": "typescript-language-server", "kind": "binary", "status": "recommended", "match": { "names": ["typescript-language-server"] }, "reason": "Language server for the typescript-lsp plugin.", "version": { "cmd": ["typescript-language-server", "--version"], "npm": "typescript-language-server" },
      "install": { "posix": [["npm", "install", "-g", "typescript-language-server", "typescript"]], "windows": [["npm", "install", "-g", "typescript-language-server", "typescript"]] },
      "update": { "posix": [["npm", "install", "-g", "typescript-language-server@latest", "typescript@latest"]], "windows": [["npm", "install", "-g", "typescript-language-server@latest", "typescript@latest"]] } },
    { "id": "rust-analyzer", "kind": "binary", "status": "recommended", "match": { "names": ["rust-analyzer"] }, "reason": "Language server for the rust-analyzer-lsp plugin.", "version": { "cmd": ["rust-analyzer", "--version"] }, "manual": "Install with `rustup component add rust-analyzer` or your package manager." },

    { "id": "mcp-serena", "kind": "mcp", "status": "core", "match": { "names": ["serena"], "contains": ["start-mcp-server"] }, "reason": "loadout provides the Serena MCP server; a user-level copy duplicates it." },
    { "id": "mcp-codebase-memory", "kind": "mcp", "status": "core", "match": { "names": ["codebase-memory-mcp", "codebase-memory"] }, "reason": "loadout provides the codebase-memory MCP server; a user-level copy duplicates it." },
    { "id": "mcp-context7", "kind": "mcp", "status": "core", "match": { "names": ["context7"], "contains": ["mcp.context7.com", "@upstash/context7-mcp"] }, "reason": "The official context7 plugin (enabled by the kit) provides it." },
    { "id": "mcp-github-reference", "kind": "mcp", "status": "superseded", "by": "gh CLI", "match": { "names": ["github-server"], "contains": ["@modelcontextprotocol/server-github"] }, "reason": "Archived reference server; the gh CLI is cheaper in context and well known to the model." },
    { "id": "mcp-sequential-thinking", "kind": "mcp", "status": "superseded", "by": "native extended thinking", "match": { "names": ["sequential-thinking"], "contains": ["server-sequential-thinking"] }, "reason": "Current models think natively; the server only adds tool overhead." },
    { "id": "mcp-memory-reference", "kind": "mcp", "status": "superseded", "by": "native auto memory + docs model", "match": { "contains": ["@modelcontextprotocol/server-memory"] }, "reason": "Superseded by Claude Code auto memory and repo docs." },
    { "id": "mcp-filesystem", "kind": "mcp", "status": "superseded", "by": "built-in Read/Edit/Write tools", "match": { "contains": ["@modelcontextprotocol/server-filesystem"] }, "reason": "Duplicates built-in file tools." },
    { "id": "mcp-puppeteer", "kind": "mcp", "status": "superseded", "by": "playwright-cli", "match": { "contains": ["server-puppeteer"] }, "reason": "Archived; playwright-cli is maintained and cheaper in context." },
    { "id": "mcp-playwright", "kind": "mcp", "status": "alternative", "by": "playwright-cli", "match": { "names": ["playwright"], "contains": ["@playwright/mcp"] }, "reason": "Works, but pushes snapshots into context; playwright-cli is the kit default." },
    { "id": "mcp-sonarqube", "kind": "mcp", "status": "profile", "profile": "sonar", "match": { "names": ["sonarqube"], "contains": ["sonar run mcp"] }, "reason": "Only useful in repos with a Sonar project; enable via the sonar profile." },
    { "id": "mcp-dbhub", "kind": "mcp", "status": "profile", "profile": "db", "match": { "names": ["dbhub"], "contains": ["@bytebase/dbhub"] }, "reason": "Database access belongs to the projects that have a database." },
    { "id": "mcp-docker-gateway", "kind": "mcp", "status": "review", "match": { "names": ["MCP_DOCKER"], "contains": ["mcp gateway run"] }, "reason": "Docker MCP gateway exposes a broad tool catalog; keep only if you use it, otherwise add specific servers per project." },

    { "id": "plugin-superpowers", "kind": "plugin", "status": "core", "match": { "names": ["superpowers@claude-plugins-official"] }, "reason": "Process skills." },
    { "id": "plugin-auto-memory", "kind": "plugin", "status": "superseded", "by": "native auto memory + docs model", "match": { "names": ["auto-memory@severity1-marketplace"] }, "reason": "Runs a memory-updater agent after most turns and rewrites CLAUDE.md; duplicates native memory." },
    { "id": "plugin-claude-mem", "kind": "plugin", "status": "superseded", "by": "native auto memory + docs model", "match": { "contains": ["claude-mem"] }, "reason": "AI-compresses every tool observation (ongoing cost, data may leave the machine)." },
    { "id": "plugin-cct-testing-suite", "kind": "plugin", "status": "superseded", "by": "superpowers TDD + built-in review", "match": { "names": ["testing-suite@claude-code-templates"] }, "reason": "Unversioned snapshot from 2025, never updated." },
    { "id": "plugin-cct-documentation-generator", "kind": "plugin", "status": "superseded", "by": "loadout docs-sync/docs-audit", "match": { "names": ["documentation-generator@claude-code-templates"] }, "reason": "Unversioned snapshot of a whole repo; generic agents." },
    { "id": "plugin-code-review", "kind": "plugin", "status": "superseded", "by": "built-in /code-review", "match": { "names": ["code-review@claude-plugins-official", "pr-review-toolkit@claude-plugins-official"] }, "reason": "Built-in /code-review covers it." },
    { "id": "plugin-sonarqube", "kind": "plugin", "status": "profile", "profile": "sonar", "match": { "names": ["sonarqube@claude-plugins-official"] }, "reason": "Adds a 30s SessionStart hook and ~10 skills to every session; enable per project." },
    { "id": "plugin-ars", "kind": "plugin", "status": "profile", "profile": "thesis", "match": { "names": ["academic-research-skills@academic-research-skills"] }, "reason": "About 25 skill/command descriptions in every session; enable in research repos." },
    { "id": "plugin-cybersecurity-skills", "kind": "plugin", "status": "deprecated", "match": { "contains": ["Anthropic-Cybersecurity-Skills", "cybersecurity-skills@"] }, "reason": "817 skills in one plugin (about 25k tokens of descriptions per session); copy single skills into a project instead." },

    { "id": "marketplace-claude-code-templates", "kind": "marketplace", "status": "deprecated", "match": { "names": ["claude-code-templates"] }, "reason": "Only provided the superseded testing-suite/documentation-generator plugins." },
    { "id": "marketplace-severity1", "kind": "marketplace", "status": "deprecated", "match": { "names": ["severity1-marketplace"] }, "reason": "Only provided the superseded auto-memory plugin." },

    { "id": "skills-taste", "kind": "skill", "status": "superseded", "by": "frontend-design + impeccable", "match": { "names": ["brandkit", "design-taste-frontend", "find-skills", "full-output-enforcement", "gpt-taste", "high-end-visual-design", "image-to-code", "imagegen-frontend-mobile", "imagegen-frontend-web", "industrial-brutalist-ui", "minimalist-ui", "redesign-existing-projects", "stitch-design-taste"], "contains": ["/.agents/skills/"] }, "reason": "taste-skill: several skills target Codex or image generation, the core skill loads ~22k tokens per use, and there is no auto-update." },
    { "id": "skills-omarchy", "kind": "skill", "status": "system", "match": { "contains": ["/usr/share/omarchy/"] }, "reason": "Provided by the Omarchy distribution." },
    { "id": "skill-codebase-memory", "kind": "skill", "status": "core", "match": { "names": ["codebase-memory"] }, "reason": "Installed by codebase-memory-mcp; kit rules cover tool routing." },

    { "id": "hook-serena-remind", "kind": "hook", "status": "deprecated", "match": { "contains": ["serena-hooks remind"] }, "reason": "Fires on every tool call; kit rules route tools instead." },
    { "id": "hook-serena", "kind": "hook", "status": "core", "match": { "contains": ["serena-hooks activate", "serena-hooks cleanup", "serena-hooks auto-approve"] }, "reason": "loadout provides these hooks." },
    { "id": "hook-rtk", "kind": "hook", "status": "core", "match": { "contains": ["rtk hook"] }, "reason": "loadout provides the rtk hook." },
    { "id": "hook-codebase-memory", "kind": "hook", "status": "core", "match": { "contains": ["cbm-code-discovery-gate", "cbm-session-reminder", "cbm-subagent-reminder", "codebase-memory-mcp hook"] }, "reason": "loadout provides the codebase-memory hooks (with rule-aligned wording)." },
    { "id": "hook-auto-memory", "kind": "hook", "status": "superseded", "by": "native auto memory + docs model", "match": { "contains": ["auto-memory/"] }, "reason": "Belongs to the superseded auto-memory plugin." },
    { "id": "hook-sonar-secrets", "kind": "hook", "status": "profile", "profile": "sonar", "match": { "contains": ["sonar-secrets"] }, "reason": "Global 60s secret-scan hooks on every Read and prompt; install per repo with `sonar integrate`." }
  ]
}
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_repo_static.py`
Expected: PASS. (`test_no_secrets_in_tracked_files` needs `git add -A` first. If it fails only because files are untracked, run `git add -A` and re-run.)

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: kit content — settings base, rules, profiles, templates, catalog

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Profiles, detection, scaffolding, `init`/`profile` commands, CLI entry point

**Files:**
- Create: `cli/loadout/profiles.py`, `cli/loadout/detect.py`, `cli/loadout/scaffold.py`, `cli/loadout/project.py`, `cli/loadout/__main__.py`, `bin/loadout`, `bin/loadout.cmd`, `tests/test_project.py`

**Interfaces:**
- Consumes: `jsonio`, `paths`, `runner`
- Produces:
  - `profiles.Profile(name, description, settings, mcp, install, commands, notes)`, `profiles.list_profiles() -> list[str]`, `profiles.load_profile(name) -> Profile` (personal `profiles/<name>.json` overrides kit; raises `ValueError` for unknown), `profiles.apply_profile(profile, project: Path) -> list[Path]`
  - `detect.detect_profiles(project: Path) -> list[str]`
  - `scaffold.scaffold(project: Path, dry_run=False) -> tuple[list[Path], list[str]]` (created, notes); `scaffold.ensure_gitignore(project, dry_run=False) -> list[str]`; `scaffold.render(text: str, values: dict) -> str`
  - `project.init(project: Path, names: list[str], yes: bool, install: bool, dry_run: bool, ask) -> int`, `project.add_profile(project, name, install: bool) -> int`
  - `__main__.main(argv: list[str] | None = None) -> int` with subcommands added by later tasks via `COMMANDS` registration

- [ ] **Step 1: Write the failing tests**

`tests/test_project.py`:
```python
import json

from loadout import detect, profiles, project, scaffold


def test_detect_profiles(tmp_path):
    p = tmp_path / "my-thesis"
    (p / "app").mkdir(parents=True)
    (p / "sonar-project.properties").write_text("sonar.projectKey=x")
    (p / "app/build.gradle.kts").write_text('plugins { id("com.android.application") }')
    (p / "package.json").write_text(json.dumps({"dependencies": {"react": "19"}}))
    (p / ".env.example").write_text("DATABASE_URL=postgres://x\n")
    assert detect.detect_profiles(p) == ["sonar", "android", "web", "db", "thesis"]


def test_detect_ignores_vendored_dirs(tmp_path):
    (tmp_path / "node_modules/x").mkdir(parents=True)
    (tmp_path / "node_modules/x/build.gradle").write_text("com.android")
    (tmp_path / "node_modules/x/paper.tex").write_text("")
    assert detect.detect_profiles(tmp_path) == []


def test_apply_profile_merges_and_is_idempotent(tmp_path):
    proj = tmp_path / "p"
    (proj / ".claude").mkdir(parents=True)
    (proj / ".claude/settings.json").write_text(json.dumps({"permissions": {"allow": ["Bash(x)"]}}))
    prof = profiles.load_profile("web")
    changed = profiles.apply_profile(prof, proj)
    assert {c.name for c in changed} == {"settings.json", ".mcp.json"}
    settings = json.loads((proj / ".claude/settings.json").read_text())
    assert settings["permissions"] == {"allow": ["Bash(x)"]}
    assert settings["disabledMcpjsonServers"] == ["chrome-devtools"]
    assert profiles.apply_profile(prof, proj) == []


def test_personal_profile_overrides_kit(fake_home, tmp_path):
    pdir = fake_home / ".config/loadout/personal/profiles"
    pdir.mkdir(parents=True)
    (pdir / "web.json").write_text(json.dumps({"description": "mine"}))
    assert profiles.load_profile("web").description == "mine"


def test_unknown_profile_raises():
    try:
        profiles.load_profile("nope")
    except ValueError as err:
        assert "available" in str(err)
    else:
        raise AssertionError("expected ValueError")


def test_scaffold_creates_missing_never_overwrites(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/README.md").write_text("mine")
    created, notes = scaffold.scaffold(tmp_path)
    names = {c.relative_to(tmp_path).as_posix() for c in created}
    assert names == {"AGENTS.md", "CLAUDE.md", "docs/adr/README.md"}
    assert (tmp_path / "docs/README.md").read_text() == "mine"
    assert tmp_path.name in (tmp_path / "AGENTS.md").read_text()
    assert scaffold.scaffold(tmp_path)[0] == []


def test_scaffold_skips_agents_when_claude_md_exists(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# existing instructions")
    created, notes = scaffold.scaffold(tmp_path)
    names = {c.relative_to(tmp_path).as_posix() for c in created}
    assert "AGENTS.md" not in names and "CLAUDE.md" not in names
    assert any("onboard" in n for n in notes)


def test_gitignore_idempotent(tmp_path):
    (tmp_path / ".gitignore").write_text("node_modules")
    assert scaffold.ensure_gitignore(tmp_path) == [".claude/settings.local.json", ".serena/cache/"]
    assert scaffold.ensure_gitignore(tmp_path) == []
    assert (tmp_path / ".gitignore").read_text().startswith("node_modules\n")


def test_init_applies_profiles_installs_and_scaffolds(tmp_path, fake_runner):
    proj = tmp_path / "p"
    proj.mkdir()
    (proj / ".git").mkdir()
    rc = project.init(proj, ["sonar"], yes=True, install=True, dry_run=False, ask=lambda q: "")
    assert rc == 0
    assert ["claude", "plugin", "install", "sonarqube@claude-plugins-official", "--scope", "project"] in fake_runner.calls
    assert (proj / "AGENTS.md").exists()


def test_init_dry_run_changes_nothing(tmp_path, fake_runner):
    proj = tmp_path / "p"
    proj.mkdir()
    (proj / ".git").mkdir()
    project.init(proj, ["db"], yes=True, install=True, dry_run=True, ask=lambda q: "")
    assert list(proj.iterdir()) == [proj / ".git"]
    assert fake_runner.calls == []


def test_init_offers_git_init(tmp_path, fake_runner):
    proj = tmp_path / "p"
    proj.mkdir()
    project.init(proj, [], yes=False, install=False, dry_run=False, ask=lambda q: "y")
    assert ["git", "init"] in fake_runner.calls
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_project.py`
Expected: FAIL with `ModuleNotFoundError: loadout.detect`.

- [ ] **Step 3: Implement**

`cli/loadout/profiles.py`:
```python
"""Per-project profiles: settings/.mcp.json fragments plus plugins to install."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import paths
from .jsonio import deep_merge, load_json, save_json


@dataclass
class Profile:
    name: str
    description: str
    settings: dict = field(default_factory=dict)
    mcp: dict = field(default_factory=dict)
    install: list = field(default_factory=list)
    commands: list = field(default_factory=list)
    notes: str = ""


def _dirs() -> list[Path]:
    return [paths.personal_root() / "profiles", paths.kit_root() / "profiles"]


def list_profiles() -> list[str]:
    names = set()
    for d in _dirs():
        names.update(p.stem for p in d.glob("*.json"))
    return sorted(names)


def load_profile(name: str) -> Profile:
    for d in _dirs():
        path = d / f"{name}.json"
        if path.exists():
            data = load_json(path)
            return Profile(
                name=name,
                description=data.get("description", ""),
                settings=data.get("settings", {}),
                mcp=data.get("mcp", {}),
                install=data.get("install", []),
                commands=data.get("commands", []),
                notes=data.get("notes", ""),
            )
    raise ValueError(f"unknown profile '{name}' (available: {', '.join(list_profiles())})")


def apply_profile(profile: Profile, project: Path) -> list[Path]:
    changed = []
    for rel, overlay in ((Path(".claude/settings.json"), profile.settings), (Path(".mcp.json"), profile.mcp)):
        if not overlay:
            continue
        target = project / rel
        before = load_json(target)
        after = deep_merge(before, overlay)
        if after != before:
            save_json(target, after)
            changed.append(target)
    return changed
```

`cli/loadout/detect.py`:
```python
"""Suggest profiles from files in a project."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Iterator

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "build", "dist", "target", "__pycache__", ".gradle"}
WEB_FRAMEWORKS = ("react", "next", "vue", "svelte", "astro")


def _files(project: Path) -> Iterator[Path]:
    for root, dirs, files in os.walk(project):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            yield Path(root) / name


def detect_profiles(project: Path) -> list[str]:
    files = list(_files(project))
    found = []
    if (project / "sonar-project.properties").exists():
        found.append("sonar")
    if any(f.name.startswith("build.gradle") and "com.android" in f.read_text(errors="ignore") for f in files):
        found.append("android")
    pkg = project / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
        deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
        if any(name in deps for name in WEB_FRAMEWORKS):
            found.append("web")
    env_example = project / ".env.example"
    if env_example.exists() and re.search(r"^\s*DATABASE_URL\s*=", env_example.read_text(errors="ignore"), re.M):
        found.append("db")
    if any(f.suffix in {".tex", ".bib"} for f in files) or re.search(r"thesis|paper", project.name, re.I):
        found.append("thesis")
    return found
```

`cli/loadout/scaffold.py`:
```python
"""Create missing project files from templates/project; never overwrite."""
from __future__ import annotations

from pathlib import Path

from . import paths

GITIGNORE_LINES = [".claude/settings.local.json", ".serena/cache/"]


def render(text: str, values: dict) -> str:
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def scaffold(project: Path, dry_run: bool = False) -> tuple[list[Path], list[str]]:
    templates = paths.kit_root() / "templates" / "project"
    skip = set()
    notes = []
    if (project / "CLAUDE.md").exists() and not (project / "AGENTS.md").exists():
        skip = {"AGENTS.md", "CLAUDE.md"}
        notes.append("CLAUDE.md exists without AGENTS.md: /loadout:onboard will offer to migrate it.")
    created = []
    for src in sorted(templates.rglob("*")):
        if src.is_dir():
            continue
        rel = src.relative_to(templates)
        dest = project / rel
        if rel.as_posix() in skip or dest.exists():
            continue
        created.append(dest)
        if not dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(render(src.read_text(encoding="utf-8"), {"PROJECT_NAME": project.name}), encoding="utf-8")
    return created, notes


def ensure_gitignore(project: Path, dry_run: bool = False) -> list[str]:
    path = project / ".gitignore"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    existing = {line.strip() for line in text.splitlines()}
    missing = [line for line in GITIGNORE_LINES if line not in existing]
    if missing and not dry_run:
        if text and not text.endswith("\n"):
            text += "\n"
        text += "# loadout\n" + "\n".join(missing) + "\n"
        path.write_text(text, encoding="utf-8")
    return missing
```

`cli/loadout/project.py`:
```python
"""`loadout init` and `loadout profile`."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from . import detect, profiles, runner, scaffold

Ask = Callable[[str], str]


def _install(profile: profiles.Profile, project: Path, dry_run: bool) -> None:
    for plugin_id in profile.install:
        cmd = ["claude", "plugin", "install", plugin_id, "--scope", "project"]
        print(("would run: " if dry_run else "running: ") + " ".join(cmd))
        if not dry_run:
            res = runner.run(cmd, cwd=str(project))
            if not res.ok:
                print(f"  failed: {res.stderr.strip()}")
    for cmd in profile.commands:
        print(("would run: " if dry_run else "running: ") + " ".join(cmd))
        if not dry_run:
            res = runner.run(cmd, cwd=str(project))
            if not res.ok:
                print(f"  failed: {res.stderr.strip()}")


def add_profile(project: Path, name: str, install: bool = True, dry_run: bool = False) -> int:
    prof = profiles.load_profile(name)
    if dry_run:
        print(f"would apply profile {name}: {prof.description}")
    else:
        for path in profiles.apply_profile(prof, project):
            print(f"updated {path}")
    if install:
        _install(prof, project, dry_run)
    if prof.notes:
        print(f"note ({name}): {prof.notes}")
    return 0


def init(project: Path, names: list[str], yes: bool, install: bool, dry_run: bool, ask: Ask) -> int:
    project = project.resolve()
    if not (project / ".git").exists():
        if dry_run:
            print("would offer: git init")
        elif yes or ask(f"{project} is not a git repository. Run git init? [y/N] ").strip().lower() == "y":
            runner.run(["git", "init"], cwd=str(project))
    chosen = list(names)
    if not chosen:
        suggested = detect.detect_profiles(project)
        print(f"suggested profiles: {', '.join(suggested) or '(none)'} — available: {', '.join(profiles.list_profiles())}")
        if yes or dry_run:
            chosen = suggested
        else:
            answer = ask("profiles to apply (comma separated, empty = suggested, '-' = none): ").strip()
            chosen = suggested if answer == "" else [] if answer == "-" else [a.strip() for a in answer.split(",") if a.strip()]
    for name in chosen:
        add_profile(project, name, install=install, dry_run=dry_run)
    created, notes = scaffold.scaffold(project, dry_run=dry_run)
    for path in created:
        print(("would create " if dry_run else "created ") + str(path.relative_to(project)))
    for line in scaffold.ensure_gitignore(project, dry_run=dry_run):
        print(("would add to .gitignore: " if dry_run else "added to .gitignore: ") + line)
    for note in notes:
        print(f"note: {note}")
    print("next: start Claude Code here and run /loadout:onboard")
    return 0
```

`cli/loadout/__main__.py`:
```python
"""loadout command line."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import project
from .jsonio import InvalidJSON


def _ask(question: str) -> str:
    try:
        return input(question)
    except EOFError:
        return ""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="loadout")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="set up the current project")
    p.add_argument("profiles", nargs="*")
    p.add_argument("--yes", action="store_true")
    p.add_argument("--no-install", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=lambda a: project.init(Path.cwd(), a.profiles, a.yes, not a.no_install, a.dry_run, _ask))

    p = sub.add_parser("profile", help="add a profile to the current project")
    p.add_argument("name")
    p.add_argument("--no-install", action="store_true")
    p.set_defaults(func=lambda a: project.add_profile(Path.cwd(), a.name, install=not a.no_install))

    for register in EXTRA_COMMANDS:
        register(sub)
    return parser


EXTRA_COMMANDS: list = []  # later modules append register(subparsers) functions here


def main(argv: list[str] | None = None) -> int:
    from . import commands  # noqa: F401  (registers the remaining subcommands)

    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except (InvalidJSON, ValueError) as exc:
        print(f"loadout: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

Create `cli/loadout/commands.py`. Later tasks add their subcommands here:
```python
"""Registers subcommands implemented in other modules (kept separate to avoid import cycles)."""
from .__main__ import EXTRA_COMMANDS  # noqa: F401
```

`bin/loadout`:
```python
#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli"))
from loadout.__main__ import main  # noqa: E402

sys.exit(main())
```

`bin/loadout.cmd`:
```
@echo off
python "%~dp0loadout" %*
```

Then: `chmod +x bin/loadout`.

- [ ] **Step 4: Run to verify pass**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_project.py && ./bin/loadout init --help`
Expected: tests PASS; help lists `profiles`, `--yes`, `--no-install`, `--dry-run`.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: profiles, detection, scaffolding and init/profile commands

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Backups/restore and linking (rules dirs, bin shims, copy fallback)

**Files:**
- Create: `cli/loadout/backup.py`, `cli/loadout/link.py`, `tests/test_link_backup.py`
- Modify: `cli/loadout/commands.py`

**Interfaces:**
- Consumes: `paths`, `jsonio`, `runner`
- Produces:
  - `backup.Backup(root: Path | None = None)` with `.root`, `.move(path, label) -> Path`, `.save_copy(path, label) -> Path`, `.record_command(label, undo_cmd: list[str])`, `.empty -> bool`
  - `backup.restore(root: Path) -> list[str]`
  - `link.LINKS() -> list[tuple[Path, Path]]` (dest, src)
  - `link.link_all(bk: Backup) -> list[str]`, `link.link_bin(bk: Backup) -> list[str]`, `link.is_copy_mode() -> bool`
  - CLI `loadout restore <dir>`

- [ ] **Step 1: Write the failing tests**

`tests/test_link_backup.py`:
```python
import os

import pytest

from loadout import backup, link, paths


def test_backup_move_and_restore_roundtrip(fake_home):
    f = fake_home / "a.txt"
    f.write_text("hi")
    bk = backup.Backup()
    assert bk.empty
    bk.move(f, "move a")
    assert not f.exists()
    backup.restore(bk.root)
    assert f.read_text() == "hi"


def test_backup_save_copy_restores_original_content(fake_home):
    f = fake_home / "s.json"
    f.write_text("old")
    bk = backup.Backup()
    bk.save_copy(f, "settings")
    f.write_text("new")
    backup.restore(bk.root)
    assert f.read_text() == "old"


def test_restore_runs_undo_commands_in_reverse(fake_home, fake_runner):
    bk = backup.Backup()
    bk.record_command("one", ["echo", "1"])
    bk.record_command("two", ["echo", "2"])
    backup.restore(bk.root)
    assert fake_runner.calls == [["echo", "2"], ["echo", "1"]]


def _personal(fake_home):
    p = paths.personal_root() / "rules"
    p.mkdir(parents=True)
    (p / "me.md").write_text("me")


def test_link_all_creates_symlinks_and_is_idempotent(fake_home):
    _personal(fake_home)
    bk = backup.Backup()
    actions = link.link_all(bk)
    assert (fake_home / ".claude/rules/loadout/tooling.md").exists()
    assert (fake_home / ".claude/rules/personal/me.md").read_text() == "me"
    assert any("linked" in a for a in actions)
    assert link.link_all(backup.Backup()) == []
    assert bk.empty


def test_link_all_backs_up_existing_real_dir(fake_home):
    _personal(fake_home)
    existing = fake_home / ".claude/rules/kit"
    existing.mkdir(parents=True)
    (existing / "old.md").write_text("old")
    bk = backup.Backup()
    link.link_all(bk)
    assert not bk.empty
    assert (fake_home / ".claude/rules/kit").is_symlink()


def test_copy_fallback_when_symlinks_unavailable(fake_home, monkeypatch):
    _personal(fake_home)

    def no_symlink(*a, **k):
        raise OSError("symlinks not permitted")

    monkeypatch.setattr(os, "symlink", no_symlink)
    link.link_all(backup.Backup())
    assert link.is_copy_mode()
    assert (fake_home / ".claude/rules/loadout/tooling.md").exists()
    assert not (fake_home / ".claude/rules/kit").is_symlink()
    # re-running in copy mode refreshes without creating backups
    bk = backup.Backup()
    link.link_all(bk)
    assert bk.empty


def test_link_bin_posix_symlink(fake_home):
    if os.name == "nt":
        pytest.skip("posix only")
    link.link_bin(backup.Backup())
    target = fake_home / ".local/bin/loadout"
    assert target.is_symlink()
    assert target.resolve() == (paths.kit_root() / "bin/loadout").resolve()


def test_windows_shims_quote_paths_with_spaces(fake_home, monkeypatch, tmp_path):
    kit = tmp_path / "Max Mustermann" / "loadout"
    (kit / "bin").mkdir(parents=True)
    (kit / "bin/loadout").write_text("")
    monkeypatch.setenv("LOADOUT_ROOT", str(kit))
    link.write_windows_shims(fake_home / ".local/bin")
    cmd = (fake_home / ".local/bin/loadout.cmd").read_text()
    sh = (fake_home / ".local/bin/loadout").read_text()
    assert f'"{kit / "bin" / "loadout"}"' in cmd
    assert f'"{(kit / "bin" / "loadout").as_posix()}"' in sh
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_link_backup.py`
Expected: FAIL with `ModuleNotFoundError: loadout.backup`.

- [ ] **Step 3: Implement**

`cli/loadout/backup.py`:
```python
"""Timestamped backups with an undo manifest; nothing the kit removes is ever deleted."""
from __future__ import annotations

import shutil
import time
from pathlib import Path

from . import paths, runner
from .jsonio import load_json, save_json


class Backup:
    def __init__(self, root: Path | None = None):
        self.root = root or paths.backups_root() / time.strftime("loadout-%Y%m%d-%H%M%S")
        self.steps: list[dict] = []

    @property
    def empty(self) -> bool:
        return not self.steps

    def _slot(self, path: Path) -> Path:
        dest = self.root / "files" / f"{len(self.steps):03d}-{path.name}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        return dest

    def move(self, path: Path, label: str) -> Path:
        dest = self._slot(path)
        shutil.move(str(path), str(dest))
        self._add(label, {"move": [str(dest), str(path)]})
        return dest

    def save_copy(self, path: Path, label: str) -> Path:
        dest = self._slot(path)
        shutil.copy2(path, dest)
        self._add(label, {"restore-file": [str(dest), str(path)]})
        return dest

    def record_command(self, label: str, undo_cmd: list[str]) -> None:
        self._add(label, {"run": undo_cmd})

    def _add(self, label: str, undo: dict) -> None:
        self.steps.append({"label": label, "undo": undo})
        save_json(self.root / "manifest.json", {"steps": self.steps})


def restore(root: Path) -> list[str]:
    done = []
    for step in reversed(load_json(root / "manifest.json").get("steps", [])):
        undo = step["undo"]
        if "move" in undo:
            src, dst = map(Path, undo["move"])
            if dst.exists() or dst.is_symlink():
                done.append(f"skipped (exists): {dst}")
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
        elif "restore-file" in undo:
            src, dst = map(Path, undo["restore-file"])
            shutil.copy2(src, dst)
        elif "run" in undo:
            res = runner.run(undo["run"])
            if not res.ok:
                done.append(f"failed: {' '.join(undo['run'])}: {res.stderr.strip()}")
                continue
        done.append(f"restored: {step['label']}")
    return done
```

`cli/loadout/link.py`:
```python
"""Link kit/personal rules into ~/.claude/rules and put loadout on PATH."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from . import paths
from .backup import Backup


def LINKS() -> list[tuple[Path, Path]]:
    rules = paths.claude_home() / "rules"
    return [
        (rules / "loadout", paths.kit_root() / "rules"),
        (rules / "personal", paths.personal_root() / "rules"),
    ]


def _marker() -> Path:
    return paths.state_dir() / "copy-mode"


def is_copy_mode() -> bool:
    return _marker().exists()


def _points_to(dest: Path, src: Path) -> bool:
    return dest.is_symlink() and dest.resolve() == src.resolve()


def _replace_with_copy(src: Path, dest: Path) -> None:
    if dest.is_symlink() or dest.is_file():
        dest.unlink()
    elif dest.exists():
        shutil.rmtree(dest)
    if src.is_dir():
        shutil.copytree(src, dest)
    else:
        shutil.copy2(src, dest)


def _link_one(dest: Path, src: Path, bk: Backup) -> str | None:
    if not src.exists() or _points_to(dest, src):
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    if is_copy_mode() and not dest.is_symlink():
        _replace_with_copy(src, dest)
        return None  # refresh, not news
    if dest.exists() or dest.is_symlink():
        bk.move(dest, f"replaced {dest}")
    try:
        os.symlink(src, dest, target_is_directory=src.is_dir())
        return f"linked {dest} -> {src}"
    except OSError:
        _marker().parent.mkdir(parents=True, exist_ok=True)
        _marker().write_text("symlinks unavailable; files are copied and refreshed by maintenance\n")
        _replace_with_copy(src, dest)
        return f"copied {src} -> {dest} (symlinks unavailable)"


def link_all(bk: Backup) -> list[str]:
    return [a for dest, src in LINKS() if (a := _link_one(dest, src, bk))]


def write_windows_shims(target_dir: Path) -> None:
    script = paths.kit_root() / "bin" / "loadout"
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "loadout.cmd").write_text(f'@echo off\r\npython "{script}" %*\r\n', encoding="utf-8")
    # Git Bash (used for hooks on Windows) runs extensionless scripts
    (target_dir / "loadout").write_text(f'#!/bin/sh\nexec python "{script.as_posix()}" "$@"\n', encoding="utf-8")


def link_bin(bk: Backup) -> list[str]:
    target_dir = paths.bin_dir()
    if os.name == "nt":
        write_windows_shims(target_dir)
        return [f"wrote shims to {target_dir} (make sure it is on PATH)"]
    action = _link_one(target_dir / "loadout", paths.kit_root() / "bin" / "loadout", bk)
    return [action] if action else []
```

Append to `cli/loadout/commands.py`:
```python
from pathlib import Path

from . import backup


def _register_restore(sub):
    p = sub.add_parser("restore", help="undo a loadout backup")
    p.add_argument("backup_dir")

    def run(args):
        for line in backup.restore(Path(args.backup_dir).expanduser()):
            print(line)
        return 0

    p.set_defaults(func=run)


EXTRA_COMMANDS.append(_register_restore)
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run --python 3.12 --with pytest pytest -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: backups with undo manifest, rule/bin linking with copy fallback

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Catalog matching, inventory, classification, secret scan

**Files:**
- Create: `cli/loadout/catalog.py`, `cli/loadout/inventory.py`, `cli/loadout/secrets.py`, `cli/loadout/versions.py`, `tests/fixtures.py`, `tests/test_inventory.py`

**Interfaces:**
- Consumes: `paths`, `jsonio`, `runner`, `settings_merge.desired_settings`
- Produces:
  - `catalog.load() -> list[dict]`, `catalog.match(kind: str, name: str, detail: str) -> dict | None`, `catalog.binaries() -> list[dict]`, `catalog.platform_cmds(entry, key: "install"|"update") -> list[list[str]]`
  - `inventory.Item(kind, name, detail, location, extra: dict)` (frozen dataclass; `extra` holds raw config and is excluded from eq/hash)
  - `inventory.collect(with_versions: bool = True) -> list[Item]`
  - `inventory.Verdict(item, action, reason, entry_id)` with action ∈ `remove|migrate|scope-down|update|install|review|unknown|keep`
  - `inventory.classify(items) -> list[Verdict]`
  - `secrets.SECRET_PATTERNS`, `secrets.Finding(server, field, key, value, location, fixable)`, `secrets.scan(claude_json: dict) -> list[Finding]`, `secrets.var_name(server, key) -> str`
  - `versions.parse_version(text) -> tuple | None`, `versions.local_version(entry) -> tuple | None`, `versions.latest_version(entry) -> tuple | None`, `versions._fetch_json(url) -> dict` (patched in tests)
  - `tests/fixtures.author_machine(home: Path) -> None` (writes a fake of the author's 2026-10-08 config; secrets built at runtime)

- [ ] **Step 1: Write the fixture and failing tests**

`tests/fixtures.py`:
```python
"""A fake of the author's machine as of 2026-10-08 (secrets replaced by fakes built at runtime)."""
import json
from pathlib import Path

FAKE_PAT = "github_pat_" + "A" * 40
FAKE_DEVIN = "apk_user_" + "B" * 40


def _w(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data) if not isinstance(data, str) else data, encoding="utf-8")


def author_machine(home: Path) -> None:
    _w(home / ".claude.json", {
        "mcpServers": {
            "MCP_DOCKER": {"command": "docker", "args": ["mcp", "gateway", "run"], "env": {"DEVIN_API_KEY": FAKE_DEVIN}},
            "github-server": {"type": "stdio", "command": "npx", "args": ["@modelcontextprotocol/server-github@latest", f"GITHUB_PERSONAL_ACCESS_TOKEN={FAKE_PAT}"], "env": {}},
            "omarchy-kb": {"type": "stdio", "command": "docker", "args": ["exec", "-i", "omarchy-mcp-server", "python", "/app/mcp_server/main.py"]},
            "serena": {"type": "stdio", "command": "serena", "args": ["start-mcp-server", "--context=claude-code", "--project-from-cwd"]},
            "codebase-memory-mcp": {"command": "/home/x/.local/bin/codebase-memory-mcp"},
            "sonarqube": {"command": "sonar", "args": ["run", "mcp"]},
        },
        "projects": {"/home/x/code/gitray": {"mcpServers": {"serena": {"command": "serena"}}}},
    })
    _w(home / ".claude/.mcp.json", {"mcpServers": {"codebase-memory-mcp": {"command": "/home/x/.local/bin/codebase-memory-mcp"}}})
    _w(home / ".claude/plugins/installed_plugins.json", {"version": 2, "plugins": {
        pid: [{"scope": "user", "version": "1"}] for pid in [
            "testing-suite@claude-code-templates", "documentation-generator@claude-code-templates",
            "frontend-design@claude-plugins-official", "superpowers@claude-plugins-official",
            "auto-memory@severity1-marketplace", "academic-research-skills@academic-research-skills",
            "sonarqube@claude-plugins-official", "mystery@somewhere"]}})
    _w(home / ".claude/plugins/known_marketplaces.json", {
        "claude-code-templates": {"source": {"source": "git", "url": "https://github.com/davila7/claude-code-templates.git"}},
        "claude-plugins-official": {"source": {"source": "github", "repo": "anthropics/claude-plugins-official"}},
        "severity1-marketplace": {"source": {"source": "github", "repo": "severity1/severity1-marketplace"}},
    })
    _w(home / ".claude/settings.json", {"hooks": {
        "PreToolUse": [
            {"matcher": "Bash", "hooks": [{"type": "command", "command": "rtk hook claude"}]},
            {"matcher": "", "hooks": [{"type": "command", "command": "serena-hooks remind --client=claude-code"}]},
            {"matcher": "Read", "hooks": [{"type": "command", "command": "'/home/x/.claude/hooks/sonar-secrets/build-scripts/pretool-secrets.sh'"}]},
            {"matcher": "Edit", "hooks": [{"type": "command", "command": "my-own-linter"}]},
        ],
        "Stop": [{"hooks": [{"type": "command", "command": "python3 /home/x/.claude/plugins/cache/severity1-marketplace/auto-memory/0.9.2/scripts/trigger.py"}]}],
    }, "effortLevel": "medium"})
    skills = home / ".claude/skills"
    skills.mkdir(parents=True, exist_ok=True)
    agents = home / ".agents/skills/gpt-taste"
    agents.mkdir(parents=True)
    (agents / "SKILL.md").write_text("x")
    (skills / "gpt-taste").symlink_to(agents)
    (skills / "my-skill").mkdir()
    _w(home / ".claude/CLAUDE.md", "@RTK.md\n\n# Skill Check Rule\nAlways check skills.\n")
```

`tests/test_inventory.py`:
```python
import pytest

from loadout import catalog, inventory, secrets, versions
from fixtures import FAKE_DEVIN, FAKE_PAT, author_machine


@pytest.fixture
def machine(fake_home, fake_runner):
    author_machine(fake_home)
    return fake_home


def _by_name(verdicts):
    return {(v.item.kind, v.item.name): v for v in verdicts}


def test_catalog_match_by_name_and_contains():
    assert catalog.match("mcp", "github-server", "npx x")["id"] == "mcp-github-reference"
    assert catalog.match("mcp", "gh2", "npx @modelcontextprotocol/server-github")["id"] == "mcp-github-reference"
    assert catalog.match("mcp", "unknown-thing", "foo") is None


def test_classification_of_author_machine(machine):
    v = _by_name(inventory.classify(inventory.collect(with_versions=False)))
    assert v[("mcp", "github-server")].action == "remove"
    assert v[("mcp", "MCP_DOCKER")].action == "review"
    assert v[("mcp", "omarchy-kb")].action == "unknown"
    assert v[("mcp", "serena")].action == "migrate"
    assert v[("mcp", "codebase-memory-mcp")].action == "migrate"
    assert v[("mcp", "sonarqube")].action == "scope-down"
    assert v[("plugin", "auto-memory@severity1-marketplace")].action == "remove"
    assert v[("plugin", "academic-research-skills@academic-research-skills")].action == "scope-down"
    assert v[("plugin", "superpowers@claude-plugins-official")].action == "keep"
    assert v[("plugin", "mystery@somewhere")].action == "unknown"
    assert v[("marketplace", "claude-code-templates")].action == "remove"
    assert v[("marketplace", "claude-plugins-official")].action == "keep"
    assert v[("skill", "gpt-taste")].action == "remove"
    assert v[("skill", "my-skill")].action == "unknown"
    assert v[("hook", "PreToolUse:Bash")].action == "migrate"
    assert v[("hook", "PreToolUse:")].action == "remove"
    assert v[("hook", "PreToolUse:Read")].action == "scope-down"
    assert v[("hook", "PreToolUse:Edit")].action == "unknown"
    assert v[("hook", "Stop:")].action == "remove"
    assert v[("claude-md", "CLAUDE.md")].action == "review"


def test_project_scoped_mcp_is_not_touched(machine):
    names = [(i.name, i.location) for i in inventory.collect(with_versions=False) if i.kind == "mcp"]
    assert all("projects" not in loc for _, loc in names)


def test_secret_scan_finds_env_and_args():
    import json
    data = json.loads((__import__("pathlib").Path(__file__).parent / "fixtures.py").read_text()) if False else None
    claude_json = {"mcpServers": {
        "a": {"env": {"DEVIN_API_KEY": FAKE_DEVIN, "HARMLESS": "1"}},
        "b": {"args": [f"TOKEN={FAKE_PAT}"]},
        "c": {"headers": {"Authorization": "Bearer ${MY_TOKEN}"}},
    }}
    found = secrets.scan(claude_json)
    assert [(f.server, f.field, f.fixable) for f in found] == [("a", "env", True), ("b", "args", False)]
    assert found[0].key == "DEVIN_API_KEY"
    assert secrets.var_name("github-server", "x") == "GITHUB_SERVER_X"


def test_versions_parse_and_offline(monkeypatch):
    assert versions.parse_version("Serena 1.7.0") == (1, 7, 0)
    assert versions.parse_version("v0.11.0") == (0, 11, 0)
    assert versions.parse_version("nothing") is None

    def boom(url):
        raise OSError("offline")

    monkeypatch.setattr(versions, "_fetch_json", boom)
    assert versions.latest_version({"version": {"cmd": ["x"], "github": "o/r"}}) is None


def test_binary_outdated_and_missing(fake_home, fake_runner, monkeypatch):
    from loadout import runner
    fake_runner.responses[("serena", "--version")] = runner.Result(0, "Serena 1.7.0", "")
    fake_runner.missing.add("codebase-memory-mcp")
    monkeypatch.setattr(versions, "latest_version", lambda e: (1, 8, 0) if e["id"] == "serena" else None)
    v = {(x.item.kind, x.item.name): x for x in inventory.classify(inventory.collect(with_versions=True))}
    assert v[("binary", "serena")].action == "update"
    assert "1.7.0 -> 1.8.0" in v[("binary", "serena")].item.detail
    assert v[("binary", "codebase-memory-mcp")].action == "install"
```

Remove the leftover line `data = ...` in `test_secret_scan_finds_env_and_args` when you copy it; it is not needed:
```python
def test_secret_scan_finds_env_and_args():
    claude_json = {"mcpServers": {
        "a": {"env": {"DEVIN_API_KEY": FAKE_DEVIN, "HARMLESS": "1"}},
        "b": {"args": [f"TOKEN={FAKE_PAT}"]},
        "c": {"headers": {"Authorization": "Bearer ${MY_TOKEN}"}},
    }}
    found = secrets.scan(claude_json)
    assert [(f.server, f.field, f.fixable) for f in found] == [("a", "env", True), ("b", "args", False)]
    assert found[0].key == "DEVIN_API_KEY"
    assert secrets.var_name("github-server", "x") == "GITHUB_SERVER_X"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_inventory.py`
Expected: FAIL with `ModuleNotFoundError: loadout.catalog`.

- [ ] **Step 3: Implement**

`cli/loadout/catalog.py`:
```python
"""Tool knowledge from catalog.json."""
from __future__ import annotations

from functools import lru_cache

from . import paths
from .jsonio import load_json


@lru_cache(maxsize=None)
def _load(root: str) -> tuple:
    return tuple(load_json(paths.kit_root() / "catalog.json").get("entries", []))


def load() -> list[dict]:
    return list(_load(str(paths.kit_root())))


def match(kind: str, name: str, detail: str = "") -> dict | None:
    for entry in load():
        if entry["kind"] != kind:
            continue
        m = entry["match"]
        if name in m.get("names", []) or any(s in detail for s in m.get("contains", [])):
            return entry
    return None


def binaries() -> list[dict]:
    return [e for e in load() if e["kind"] == "binary"]


def platform_cmds(entry: dict, key: str) -> list[list[str]]:
    return entry.get(key, {}).get(paths.platform_key(), [])
```

`cli/loadout/versions.py`:
```python
"""Installed vs latest versions of catalog binaries. Every network failure means 'unknown'."""
from __future__ import annotations

import json
import re
import urllib.request

from . import runner


def parse_version(text: str) -> tuple | None:
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", text or "")
    return tuple(int(x) for x in m.groups()) if m else None


def local_version(entry: dict) -> tuple | None:
    res = runner.run(entry["version"]["cmd"], timeout=20)
    return parse_version(res.stdout + res.stderr) if res.ok else None


def _fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "loadout"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def latest_version(entry: dict) -> tuple | None:
    src = entry.get("version", {})
    try:
        if "github" in src:
            return parse_version(_fetch_json(f"https://api.github.com/repos/{src['github']}/releases/latest").get("tag_name", ""))
        if "npm" in src:
            return parse_version(_fetch_json(f"https://registry.npmjs.org/{src['npm']}/latest").get("version", ""))
        if "pypi" in src:
            return parse_version(_fetch_json(f"https://pypi.org/pypi/{src['pypi']}/json")["info"]["version"])
    except Exception:  # offline, rate-limited, malformed: unknown
        return None
    return None


def fmt(v: tuple | None) -> str:
    return ".".join(map(str, v)) if v else "?"
```

`cli/loadout/secrets.py`:
```python
"""Detect plaintext secrets in MCP server configs."""
from __future__ import annotations

import re
from dataclasses import dataclass

SECRET_PATTERNS = [
    r"gh[pousr]_[A-Za-z0-9]{20,}", r"github_pat_[A-Za-z0-9_]{20,}", r"sk-[A-Za-z0-9_-]{20,}",
    r"apk_[A-Za-z0-9_=-]{16,}", r"xox[baprs]-[A-Za-z0-9-]{10,}", r"AKIA[0-9A-Z]{16}",
]
SECRET_KEY = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|AUTH", re.I)


@dataclass
class Finding:
    server: str
    field: str      # env | headers | args
    key: str        # env/header name, or arg index
    value: str
    location: str
    fixable: bool   # env/headers can be rewritten to ${VAR}; args need manual handling


def looks_secret(key: str, value: str) -> bool:
    if not isinstance(value, str) or "${" in value:
        return False
    if any(re.search(p, value) for p in SECRET_PATTERNS):
        return True
    return bool(SECRET_KEY.search(key)) and len(value) >= 12


def var_name(server: str, key: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", f"{server}_{key}".upper()).strip("_")


def scan(claude_json: dict, location: str = "~/.claude.json") -> list[Finding]:
    found = []
    for server, cfg in claude_json.get("mcpServers", {}).items():
        for field in ("env", "headers"):
            for key, value in (cfg.get(field) or {}).items():
                if looks_secret(key, value):
                    found.append(Finding(server, field, key, value, location, True))
        for i, arg in enumerate(cfg.get("args") or []):
            key = arg.split("=", 1)[0] if "=" in arg else str(i)
            value = arg.split("=", 1)[1] if "=" in arg else arg
            if looks_secret(key, value):
                found.append(Finding(server, "args", key, value, location, False))
    return found
```

`cli/loadout/inventory.py`:
```python
"""Inventory of a machine's Claude Code setup and its classification against the catalog."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from . import catalog, paths, runner, versions
from .jsonio import load_json
from .settings_merge import desired_settings


@dataclass(frozen=True)
class Item:
    kind: str          # mcp | plugin | marketplace | skill | hook | binary | claude-md
    name: str
    detail: str = ""
    location: str = ""
    extra: dict = field(default_factory=dict, compare=False, hash=False)


@dataclass
class Verdict:
    item: Item
    action: str        # remove | migrate | scope-down | update | install | review | unknown | keep
    reason: str
    entry_id: str = ""


def _mcp_items() -> list[Item]:
    items = []
    sources = [(paths.claude_json(), "~/.claude.json"), (paths.claude_home() / ".mcp.json", "~/.claude/.mcp.json")]
    for path, label in sources:
        for name, cfg in load_json(path).get("mcpServers", {}).items():
            detail = " ".join([cfg.get("command", ""), *cfg.get("args", []), cfg.get("url", "")]).strip()
            items.append(Item("mcp", name, detail, label, {"config": cfg}))
    return items


def _plugin_items() -> list[Item]:
    installed = load_json(paths.claude_home() / "plugins" / "installed_plugins.json").get("plugins", {})
    return [Item("plugin", pid, entries[0].get("version", ""), "user", {})
            for pid, entries in installed.items() if any(e.get("scope") == "user" for e in entries)]


def _marketplace_items() -> list[Item]:
    known = load_json(paths.claude_home() / "plugins" / "known_marketplaces.json")
    out = []
    for name, cfg in known.items():
        src = cfg.get("source", {})
        out.append(Item("marketplace", name, src.get("repo") or src.get("url", ""), "user", {"source": src}))
    return out


def _skill_items() -> list[Item]:
    root = paths.claude_home() / "skills"
    if not root.exists():
        return []
    out = []
    for entry in sorted(root.iterdir()):
        if entry.name == "synced":
            continue
        target = os.readlink(entry) if entry.is_symlink() else str(entry)
        out.append(Item("skill", entry.name, str(target), str(entry), {}))
    return out


def _hook_items() -> list[Item]:
    hooks = load_json(paths.claude_home() / "settings.json").get("hooks", {})
    out = []
    for event, groups in hooks.items():
        for gi, group in enumerate(groups):
            for hi, hook in enumerate(group.get("hooks", [])):
                out.append(Item("hook", f"{event}:{group.get('matcher', '')}", hook.get("command", ""),
                                "~/.claude/settings.json", {"event": event, "group": gi, "hook": hi}))
    return out


def _claude_md_items() -> list[Item]:
    path = paths.claude_home() / "CLAUDE.md"
    if path.is_symlink() or not path.exists() or not path.read_text(encoding="utf-8").strip():
        return []
    first = path.read_text(encoding="utf-8").strip().splitlines()[0]
    return [Item("claude-md", "CLAUDE.md", first, str(path), {})]


def _binary_items(with_versions: bool) -> list[Item]:
    out = []
    for entry in catalog.binaries():
        name = entry["id"]
        if not runner.have(name):
            out.append(Item("binary", name, "missing", "PATH", {"entry": entry, "state": "missing"}))
            continue
        if not with_versions:
            out.append(Item("binary", name, "installed", "PATH", {"entry": entry, "state": "ok"}))
            continue
        local = versions.local_version(entry)
        latest = versions.latest_version(entry)
        state = "outdated" if local and latest and latest > local else "ok"
        detail = f"{versions.fmt(local)} -> {versions.fmt(latest)}" if state == "outdated" else versions.fmt(local)
        out.append(Item("binary", name, detail, "PATH", {"entry": entry, "state": state}))
    return out


def collect(with_versions: bool = True) -> list[Item]:
    return [*_mcp_items(), *_plugin_items(), *_marketplace_items(), *_skill_items(),
            *_hook_items(), *_claude_md_items(), *_binary_items(with_versions)]


def _why(entry: dict) -> str:
    return entry["reason"] + (f" Replacement: {entry['by']}." if entry.get("by") else "")


def classify(items: list[Item]) -> list[Verdict]:
    desired = desired_settings()
    kit_plugins = {p for p, on in desired.get("enabledPlugins", {}).items() if on}
    kit_markets = set(desired.get("extraKnownMarketplaces", {})) | {"claude-plugins-official"}
    out = []
    for item in items:
        if item.kind == "binary":
            entry, state = item.extra["entry"], item.extra["state"]
            if state == "missing":
                action = "install" if entry.get("required") or entry["status"] == "recommended" else "keep"
                out.append(Verdict(item, action, entry["reason"], entry["id"]))
            elif state == "outdated":
                out.append(Verdict(item, "update", entry["reason"], entry["id"]))
            else:
                out.append(Verdict(item, "keep", entry["reason"], entry["id"]))
            continue
        if item.kind == "claude-md":
            out.append(Verdict(item, "review", "Global CLAUDE.md content can move into your personal layer (rules/personal/me.md)."))
            continue
        if item.kind == "plugin" and item.name in kit_plugins:
            out.append(Verdict(item, "keep", "Enabled by the kit."))
            continue
        if item.kind == "marketplace" and item.name in kit_markets:
            out.append(Verdict(item, "keep", "Declared by the kit."))
            continue
        entry = catalog.match(item.kind, item.name, item.detail)
        if entry is None:
            out.append(Verdict(item, "unknown", "Not in the catalog; left untouched unless you choose otherwise."))
            continue
        status = entry["status"]
        if status == "core":
            action = "keep" if item.kind in ("plugin", "marketplace") else "migrate"
            reason = entry["reason"] if action == "keep" else f"Provided by loadout; this copy duplicates it. {entry['reason']}"
        elif status == "profile":
            action, reason = "scope-down", f"{entry['reason']} (`loadout profile {entry['profile']}` in the repos that need it)"
        elif status in ("superseded", "deprecated"):
            action, reason = "remove", _why(entry)
        elif status == "review":
            action, reason = "review", entry["reason"]
        else:
            action, reason = "keep", _why(entry)
        out.append(Verdict(item, action, reason, entry["id"]))
    return out
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run --python 3.12 --with pytest pytest -q`
Expected: all PASS. If `test_classification_of_author_machine` fails on `settings_merge.desired_settings` because there's no personal layer in `fake_home`, that's expected to work: `load_json` of a missing file returns `{}`.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: catalog matching, machine inventory, classification, secret scan

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: `adopt`: plan rendering, selection, apply, CLAUDE.md migration, secret fixes

**Files:**
- Create: `cli/loadout/adopt.py`, `tests/test_adopt.py`
- Modify: `cli/loadout/commands.py`

**Interfaces:**
- Consumes: `inventory.collect/classify/Item/Verdict`, `secrets.scan/var_name`, `backup.Backup`, `catalog.platform_cmds`, `runner`, `paths`, `jsonio`
- Produces:
  - `adopt.GROUP_ORDER = ["remove", "migrate", "scope-down", "update", "install", "review", "unknown", "keep"]`
  - `adopt.render_plan(verdicts, findings) -> str`
  - `adopt.select(verdicts, groups: set[str] | None, skip: set[str], ask) -> list[Verdict]`
  - `adopt.apply(selected, bk: Backup) -> list[str]`
  - `adopt.fix_secrets(findings, bk) -> list[str]`
  - `adopt.migrate_claude_md(bk) -> list[str]`
  - `adopt.run(apply_changes: bool, groups: set|None, skip: set, yes: bool, ask, with_versions: bool = True) -> int`
  - CLI `loadout adopt [--apply] [--groups g1,g2] [--skip name,...] [--yes] [--no-versions]`

Behaviour of `select`:
- `groups=None` with `yes=False`: interactive. Per group in `GROUP_ORDER` excluding `keep`, ask `"[a]ll / [n]one / [p]ick"`. Defaults:
  - `remove`, `migrate`, `scope-down`, `update` → all
  - `install` → none
  - `review`, `unknown` → none
- `groups` given: those groups minus `skip` names.

Apply semantics per (kind, action):

| kind | remove / migrate | scope-down | undo recorded |
|---|---|---|---|
| mcp (`~/.claude.json`) | `claude mcp remove -s user <name>` | same as remove | `claude mcp add-json -s user <name> '<json>'` |
| mcp (`~/.claude/.mcp.json`) | move the file to the backup (once) | n/a | move back |
| plugin | `claude plugin uninstall <id> --scope user` | `claude plugin disable <id> --scope user` | install / enable |
| marketplace | `claude plugin marketplace remove <name>` | n/a | `claude plugin marketplace add <repo or url>` |
| skill | move the entry; if it is a symlink into `~/.agents/skills/`, move the target too | n/a | move back |
| hook | delete the hook from `settings.json` (save a copy first, once per run); prune empty groups/events | same as remove | restore-file |
| binary update/install | run catalog commands after printing them | n/a | none |
| claude-md (`review` chosen) | `migrate_claude_md`: append content to `<personal>/rules/me.md` under `## Migrated from ~/.claude/CLAUDE.md`, replace CLAUDE.md with a one-line comment | n/a | restore-file |

- [ ] **Step 1: Write the failing tests**

`tests/test_adopt.py`:
```python
import json

import pytest

from loadout import adopt, backup, inventory, paths
from fixtures import FAKE_DEVIN, author_machine


@pytest.fixture
def machine(fake_home, fake_runner):
    author_machine(fake_home)
    return fake_home


def _verdicts():
    return inventory.classify(inventory.collect(with_versions=False))


def test_render_plan_groups_and_reasons(machine):
    text = adopt.render_plan(_verdicts(), [])
    assert text.index("REMOVE") < text.index("MIGRATE") < text.index("SCOPE-DOWN")
    assert "github-server" in text and "gh CLI" in text


def test_select_by_groups_with_skip(machine):
    chosen = adopt.select(_verdicts(), {"remove"}, {"gpt-taste"}, ask=lambda q: "")
    names = {v.item.name for v in chosen}
    assert "github-server" in names and "gpt-taste" not in names
    assert all(v.action == "remove" for v in chosen)


def test_select_interactive_defaults(machine):
    chosen = adopt.select(_verdicts(), None, set(), ask=lambda q: "")
    actions = {v.action for v in chosen}
    assert actions <= {"remove", "migrate", "scope-down", "update"}
    assert "unknown" not in actions


def test_apply_runs_cli_and_records_undo(machine, fake_runner):
    bk = backup.Backup()
    chosen = [v for v in _verdicts() if v.item.name in {"github-server", "auto-memory@severity1-marketplace",
                                                          "sonarqube@claude-plugins-official", "claude-code-templates"}]
    adopt.apply(chosen, bk)
    assert ["claude", "mcp", "remove", "-s", "user", "github-server"] in fake_runner.calls
    assert ["claude", "plugin", "uninstall", "auto-memory@severity1-marketplace", "--scope", "user"] in fake_runner.calls
    assert ["claude", "plugin", "disable", "sonarqube@claude-plugins-official", "--scope", "user"] in fake_runner.calls
    assert ["claude", "plugin", "marketplace", "remove", "claude-code-templates"] in fake_runner.calls
    manifest = json.loads((bk.root / "manifest.json").read_text())
    undo_cmds = [s["undo"].get("run") for s in manifest["steps"]]
    assert any(c and c[:4] == ["claude", "mcp", "add-json", "-s"] for c in undo_cmds)


def test_apply_removes_hooks_and_skills_restorably(machine):
    bk = backup.Backup()
    chosen = [v for v in _verdicts() if (v.item.kind, v.item.name) in {("hook", "PreToolUse:"), ("hook", "Stop:"), ("skill", "gpt-taste")}]
    adopt.apply(chosen, bk)
    settings = json.loads((machine / ".claude/settings.json").read_text())
    commands = [h["command"] for groups in settings["hooks"].values() for g in groups for h in g["hooks"]]
    assert not any("serena-hooks remind" in c for c in commands)
    assert "Stop" not in settings["hooks"]
    assert "my-own-linter" in commands
    assert not (machine / ".claude/skills/gpt-taste").exists()
    assert not (machine / ".agents/skills/gpt-taste").exists()
    backup.restore(bk.root)
    assert (machine / ".agents/skills/gpt-taste/SKILL.md").exists()
    restored = json.loads((machine / ".claude/settings.json").read_text())
    assert "Stop" in restored["hooks"]


def test_migrate_claude_md(machine):
    bk = backup.Backup()
    adopt.migrate_claude_md(bk)
    me = (paths.personal_root() / "rules/me.md").read_text()
    assert "Skill Check Rule" in me
    assert (machine / ".claude/CLAUDE.md").read_text().startswith("<!--")


def test_fix_secrets_moves_env_value_to_secrets_file(machine, fake_runner):
    from loadout import secrets
    found = secrets.scan(json.loads((machine / ".claude.json").read_text()))
    adopt.fix_secrets(found, backup.Backup())
    text = paths.secrets_file().read_text()
    assert f"MCP_DOCKER_DEVIN_API_KEY={FAKE_DEVIN}" in text
    add = [c for c in fake_runner.calls if c[:3] == ["claude", "mcp", "add-json"]][0]
    assert "${MCP_DOCKER_DEVIN_API_KEY}" in add[-1]


def test_run_dry_run_changes_nothing(machine, fake_runner, capsys):
    before = (machine / ".claude/settings.json").read_text()
    assert adopt.run(False, None, set(), False, ask=lambda q: "", with_versions=False) == 0
    assert (machine / ".claude/settings.json").read_text() == before
    assert [c for c in fake_runner.calls if c[:1] == ["claude"]] == []
    assert "dry run" in capsys.readouterr().out
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_adopt.py`
Expected: FAIL with `ModuleNotFoundError: loadout.adopt`.

- [ ] **Step 3: Implement**

`cli/loadout/adopt.py`:
```python
"""`loadout adopt`: migrate an existing machine onto the kit (spec §6.2)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable

from . import catalog, paths, runner, secrets
from .backup import Backup
from .inventory import Verdict, classify, collect
from .jsonio import load_json, save_json

GROUP_ORDER = ["remove", "migrate", "scope-down", "update", "install", "review", "unknown", "keep"]
DEFAULT_ALL = {"remove", "migrate", "scope-down", "update"}
Ask = Callable[[str], str]


def render_plan(verdicts: list[Verdict], findings: list) -> str:
    lines = []
    for group in GROUP_ORDER:
        members = [v for v in verdicts if v.action == group]
        if not members:
            continue
        lines.append(f"\n{group.upper()} ({len(members)})")
        for v in members:
            lines.append(f"  [{v.item.kind}] {v.item.name}  {v.item.detail}".rstrip())
            lines.append(f"      {v.reason}")
    if findings:
        lines.append("\nPLAINTEXT SECRETS")
        for f in findings:
            how = "can move to secrets.env" if f.fixable else "in command args: remove the server or fix manually"
            lines.append(f"  {f.server}.{f.field}.{f.key} ({f.location}) — {how}")
    return "\n".join(lines)


def select(verdicts: list[Verdict], groups: set[str] | None, skip: set[str], ask: Ask) -> list[Verdict]:
    if groups is not None:
        return [v for v in verdicts if v.action in groups and v.item.name not in skip]
    chosen = []
    for group in GROUP_ORDER[:-1]:
        members = [v for v in verdicts if v.action == group and v.item.name not in skip]
        if not members:
            continue
        default = "a" if group in DEFAULT_ALL else "n"
        answer = (ask(f"{group}: {len(members)} item(s). [a]ll / [n]one / [p]ick (default {default}): ").strip().lower() or default)
        if answer == "a":
            chosen += members
        elif answer == "p":
            chosen += [v for v in members if ask(f"  {v.item.kind} {v.item.name}? [y/N] ").strip().lower() == "y"]
    return chosen


def _claude(args: list[str]) -> str:
    res = runner.run(["claude", *args])
    return "ok" if res.ok else f"failed: {res.stderr.strip()}"


def _apply_mcp(v: Verdict, bk: Backup, moved: set) -> str:
    if v.item.location == "~/.claude/.mcp.json":
        path = paths.claude_home() / ".mcp.json"
        if str(path) not in moved and path.exists():
            bk.move(path, f"moved {path}")
            moved.add(str(path))
        return f"moved {path} to backup"
    cfg = json.dumps(v.item.extra.get("config", {}))
    bk.record_command(f"mcp {v.item.name}", ["claude", "mcp", "add-json", "-s", "user", v.item.name, cfg])
    return f"mcp {v.item.name}: " + _claude(["mcp", "remove", "-s", "user", v.item.name])


def _apply_plugin(v: Verdict, bk: Backup) -> str:
    if v.action == "scope-down":
        bk.record_command(f"plugin {v.item.name}", ["claude", "plugin", "enable", v.item.name, "--scope", "user"])
        return f"plugin {v.item.name} disabled globally: " + _claude(["plugin", "disable", v.item.name, "--scope", "user"])
    bk.record_command(f"plugin {v.item.name}", ["claude", "plugin", "install", v.item.name, "--scope", "user"])
    return f"plugin {v.item.name} uninstalled: " + _claude(["plugin", "uninstall", v.item.name, "--scope", "user"])


def _apply_marketplace(v: Verdict, bk: Backup) -> str:
    src = v.item.extra.get("source", {})
    origin = src.get("repo") or src.get("url")
    if origin:
        bk.record_command(f"marketplace {v.item.name}", ["claude", "plugin", "marketplace", "add", origin])
    return f"marketplace {v.item.name}: " + _claude(["plugin", "marketplace", "remove", v.item.name])


def _apply_skill(v: Verdict, bk: Backup) -> str:
    link = Path(v.item.location)
    target = None
    if link.is_symlink():
        resolved = Path(os.path.normpath(link.parent / os.readlink(link)))
        if "/.agents/skills/" in resolved.as_posix() and resolved.exists():
            target = resolved
    bk.move(link, f"skill {v.item.name}")
    if target is not None:
        bk.move(target, f"skill source {target}")
    return f"skill {v.item.name} moved to backup"


def _apply_hooks(hook_verdicts: list[Verdict], bk: Backup) -> list[str]:
    if not hook_verdicts:
        return []
    path = paths.claude_home() / "settings.json"
    bk.save_copy(path, "settings.json before hook removal")
    data = load_json(path)
    drop = {(v.item.extra["event"], v.item.extra["group"], v.item.extra["hook"]) for v in hook_verdicts}
    hooks = data.get("hooks", {})
    for event in list(hooks):
        new_groups = []
        for gi, group in enumerate(hooks[event]):
            kept = [h for hi, h in enumerate(group.get("hooks", [])) if (event, gi, hi) not in drop]
            if kept:
                new_groups.append({**group, "hooks": kept})
        if new_groups:
            hooks[event] = new_groups
        else:
            del hooks[event]
    if not hooks:
        data.pop("hooks", None)
    save_json(path, data)
    return [f"hook {v.item.name}: removed ({v.item.detail[:60]})" for v in hook_verdicts]


def _apply_binary(v: Verdict) -> str:
    key = "install" if v.action == "install" else "update"
    entry = v.item.extra["entry"]
    cmds = catalog.platform_cmds(entry, key)
    if not cmds:
        return f"{v.item.name}: no {key} command for this platform. {entry.get('manual', '')}".strip()
    results = []
    for cmd in cmds:
        print("running: " + " ".join(cmd))
        res = runner.run(cmd, timeout=900)
        results.append("ok" if res.ok else f"failed: {res.stderr.strip()[:200]}")
    return f"{v.item.name} {key}: " + ", ".join(results)


def migrate_claude_md(bk: Backup) -> list[str]:
    src = paths.claude_home() / "CLAUDE.md"
    content = src.read_text(encoding="utf-8").strip()
    me = paths.personal_root() / "rules" / "me.md"
    me.parent.mkdir(parents=True, exist_ok=True)
    if me.exists():
        bk.save_copy(me, "personal me.md before migration")
    existing = me.read_text(encoding="utf-8") if me.exists() else "# About me\n"
    me.write_text(existing.rstrip() + "\n\n## Migrated from ~/.claude/CLAUDE.md\n\n" + content + "\n", encoding="utf-8")
    bk.save_copy(src, "global CLAUDE.md")
    src.write_text("<!-- Global instructions live in ~/.claude/rules/ (loadout). -->\n", encoding="utf-8")
    return [f"moved ~/.claude/CLAUDE.md content into {me}"]


def fix_secrets(findings: list, bk: Backup) -> list[str]:
    out = []
    claude_json = load_json(paths.claude_json())
    secrets_path = paths.secrets_file()
    secrets_path.parent.mkdir(parents=True, exist_ok=True)
    for f in findings:
        if not f.fixable:
            out.append(f"{f.server}: secret in args, fix manually (or remove the server)")
            continue
        var = secrets.var_name(f.server, f.key)
        cfg = json.loads(json.dumps(claude_json["mcpServers"][f.server]))
        bk.record_command(f"secret {f.server}.{f.key}", ["claude", "mcp", "add-json", "-s", "user", f.server, json.dumps(cfg)])
        cfg[f.field][f.key] = cfg[f.field][f.key].replace(f.value, "${" + var + "}")
        with secrets_path.open("a", encoding="utf-8") as fh:
            fh.write(f"{var}={f.value}\n")
        if os.name != "nt":
            os.chmod(secrets_path, 0o600)
        _claude(["mcp", "remove", "-s", "user", f.server])
        out.append(f"{f.server}.{f.key} -> ${{{var}}}: " + _claude(["mcp", "add-json", "-s", "user", f.server, json.dumps(cfg)]))
    return out


def apply(selected: list[Verdict], bk: Backup) -> list[str]:
    out, moved = [], set()
    for v in selected:
        kind = v.item.kind
        if kind == "mcp":
            out.append(_apply_mcp(v, bk, moved))
        elif kind == "plugin":
            out.append(_apply_plugin(v, bk))
        elif kind == "marketplace":
            out.append(_apply_marketplace(v, bk))
        elif kind == "skill":
            out.append(_apply_skill(v, bk))
        elif kind == "binary":
            out.append(_apply_binary(v))
        elif kind == "claude-md":
            out += migrate_claude_md(bk)
    out += _apply_hooks([v for v in selected if v.item.kind == "hook"], bk)
    return out


def run(apply_changes: bool, groups: set | None, skip: set, yes: bool, ask: Ask, with_versions: bool = True) -> int:
    verdicts = classify(collect(with_versions=with_versions))
    findings = secrets.scan(load_json(paths.claude_json()))
    print(render_plan(verdicts, findings))
    if not apply_changes:
        print("\n(dry run — nothing changed. Re-run with --apply to choose and apply.)")
        return 0
    chosen = select(verdicts, groups if groups is not None else (DEFAULT_ALL if yes else None), skip, ask)
    if not chosen and not findings:
        print("nothing selected")
        return 0
    bk = Backup()
    for line in apply(chosen, bk):
        print(line)
    remaining = [f for f in findings if f.server not in {v.item.name for v in chosen if v.item.kind == "mcp"}]
    if remaining and (yes or ask("move detected plaintext secrets to secrets.env? [y/N] ").strip().lower() == "y"):
        for line in fix_secrets(remaining, bk):
            print(line)
    if not bk.empty:
        print(f"\nbackup: {bk.root}  (undo: loadout restore {bk.root})")
    return 0
```

Append to `cli/loadout/commands.py`:
```python
def _register_adopt(sub):
    from . import adopt
    from .__main__ import _ask

    p = sub.add_parser("adopt", help="review and migrate the existing Claude Code setup")
    p.add_argument("--apply", action="store_true", help="choose and apply changes (default: dry run)")
    p.add_argument("--groups", help="non-interactive: comma-separated groups to apply, e.g. remove,migrate")
    p.add_argument("--skip", default="", help="comma-separated item names to leave alone")
    p.add_argument("--yes", action="store_true")
    p.add_argument("--no-versions", action="store_true", help="skip network version checks")

    def run(a):
        groups = {g.strip() for g in a.groups.split(",") if g.strip()} if a.groups else None
        skip = {s.strip() for s in a.skip.split(",") if s.strip()}
        return adopt.run(a.apply, groups, skip, a.yes, _ask, with_versions=not a.no_versions)

    p.set_defaults(func=run)


EXTRA_COMMANDS.append(_register_adopt)
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run --python 3.12 --with pytest pytest -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: adopt — plan, selection, apply with undo, CLAUDE.md and secret migration

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: `check` and `apply-settings` commands

**Files:**
- Create: `cli/loadout/check.py`, `tests/test_check.py`
- Modify: `cli/loadout/commands.py`

**Interfaces:**
- Consumes: `link.LINKS/is_copy_mode`, `settings_merge.drift/desired_settings/apply_settings`, `catalog.binaries`, `runner`, `paths`, `jsonio`
- Produces:
  - `check.CheckResult(name, ok, detail, fix, severity)` where severity ∈ `error|warn`
  - `check.run_checks() -> list[CheckResult]`
  - `check.format_results(results) -> tuple[str, int]`
  - CLI `loadout check`, `loadout apply-settings`

- [ ] **Step 1: Write the failing tests**

`tests/test_check.py`:
```python
import json

from loadout import backup, check, link, paths, settings_merge


def _setup_ok(fake_home):
    (paths.personal_root() / "rules").mkdir(parents=True)
    link.link_all(backup.Backup())
    settings_merge.apply_settings()
    installed = {pid: [{"scope": "user"}] for pid, on in settings_merge.desired_settings()["enabledPlugins"].items() if on}
    p = fake_home / ".claude/plugins/installed_plugins.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"version": 2, "plugins": installed}))


def _by(results):
    return {r.name: r for r in results}


def test_check_passes_on_good_setup(fake_home, fake_runner):
    _setup_ok(fake_home)
    text, code = check.format_results(check.run_checks())
    assert code == 0, text


def test_check_reports_drift_with_personal_hint(fake_home, fake_runner):
    _setup_ok(fake_home)
    s = fake_home / ".claude/settings.json"
    data = json.loads(s.read_text())
    data["enabledPlugins"]["superpowers@claude-plugins-official"] = False
    s.write_text(json.dumps(data))
    r = _by(check.run_checks())["settings drift"]
    assert not r.ok
    assert "superpowers" in r.detail
    assert "personal" in r.fix


def test_check_missing_link_and_binary(fake_home, fake_runner):
    fake_runner.missing.add("serena")
    results = _by(check.run_checks())
    assert not results["link rules/loadout"].ok
    assert not results["binary serena"].ok
    assert results["binary serena"].severity == "error"
    text, code = check.format_results(list(results.values()))
    assert code == 1
    assert "loadout bootstrap" in text


def test_check_invalid_settings_json(fake_home, fake_runner):
    s = fake_home / ".claude/settings.json"
    s.parent.mkdir(parents=True)
    s.write_text("{ nope")
    r = _by(check.run_checks())["settings.json"]
    assert not r.ok and "invalid JSON" in r.detail
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_check.py`
Expected: FAIL with `ModuleNotFoundError: loadout.check`.

- [ ] **Step 3: Implement**

`cli/loadout/check.py`:
```python
"""`loadout check`: report problems, never fix them; every failure names its fix."""
from __future__ import annotations

import os
import stat
from dataclasses import dataclass

from . import catalog, link, paths, runner, settings_merge
from .jsonio import InvalidJSON, load_json


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""
    fix: str = ""
    severity: str = "error"


def _links() -> list[CheckResult]:
    out = []
    for dest, src in link.LINKS():
        name = f"link rules/{dest.name}"
        if link.is_copy_mode():
            ok = dest.exists()
        else:
            ok = dest.is_symlink() and dest.resolve() == src.resolve()
        out.append(CheckResult(name, ok, "" if ok else f"{dest} does not point to {src}", "loadout bootstrap"))
    return out


def _settings() -> list[CheckResult]:
    try:
        load_json(paths.claude_home() / "settings.json")
        drift = settings_merge.drift()
    except InvalidJSON as exc:
        return [CheckResult("settings.json", False, str(exc), "fix the JSON syntax, then run loadout apply-settings")]
    personal = paths.personal_root() / "settings.json"
    return [
        CheckResult("settings.json", True),
        CheckResult("settings drift", not drift, ", ".join(drift),
                    f"loadout apply-settings (to keep your own value instead, put the override in {personal})", "warn"),
    ]


def _plugins() -> list[CheckResult]:
    try:
        wanted = [p for p, on in settings_merge.desired_settings().get("enabledPlugins", {}).items() if on]
    except InvalidJSON as exc:
        return [CheckResult("plugins", False, str(exc), "fix the JSON syntax")]
    installed = load_json(paths.claude_home() / "plugins" / "installed_plugins.json").get("plugins", {})
    missing = [p for p in wanted if p not in installed]
    return [CheckResult("plugins installed", not missing, ", ".join(missing), "loadout bootstrap (or restart Claude Code to auto-install)")]


def _binaries() -> list[CheckResult]:
    out = []
    for entry in catalog.binaries():
        name = entry["id"]
        ok = runner.have(name)
        severity = "error" if entry.get("required") else "warn"
        fix = "loadout bootstrap --install" if catalog.platform_cmds(entry, "install") else entry.get("manual", "")
        out.append(CheckResult(f"binary {name}", ok, "" if ok else "not on PATH", fix, severity))
    return out


def _gh() -> list[CheckResult]:
    if not runner.have("gh"):
        return []
    res = runner.run(["gh", "auth", "status"], timeout=20)
    return [CheckResult("gh auth", res.ok, "" if res.ok else "not logged in", "gh auth login && gh auth setup-git", "warn")]


def _secrets() -> list[CheckResult]:
    path = paths.secrets_file()
    if not path.exists():
        return [CheckResult("secrets.env", False, f"{path} missing", "loadout bootstrap", "warn")]
    if os.name != "nt" and stat.S_IMODE(path.stat().st_mode) & 0o077:
        return [CheckResult("secrets.env", False, "permissions too open", f"chmod 600 {path}", "warn")]
    return [CheckResult("secrets.env", True)]


def _repos() -> list[CheckResult]:
    out = []
    for label, root in (("kit", paths.kit_root()), ("personal", paths.personal_root())):
        if not (root / ".git").exists():
            continue
        res = runner.run(["git", "-C", str(root), "status", "--porcelain"], timeout=20)
        clean = res.ok and not res.stdout.strip()
        out.append(CheckResult(f"{label} repo clean", clean, "" if clean else "uncommitted changes (daily sync paused)",
                               f"commit or discard changes in {root}", "warn"))
    return out


def run_checks() -> list[CheckResult]:
    return [*_links(), *_settings(), *_plugins(), *_binaries(), *_gh(), *_secrets(), *_repos()]


def format_results(results: list[CheckResult]) -> tuple[str, int]:
    lines, code = [], 0
    for r in results:
        mark = "ok  " if r.ok else ("FAIL" if r.severity == "error" else "warn")
        line = f"[{mark}] {r.name}"
        if not r.ok:
            line += f": {r.detail}" if r.detail else ""
            line += f"\n        fix: {r.fix}" if r.fix else ""
            if r.severity == "error":
                code = 1
        lines.append(line)
    return "\n".join(lines), code
```

Append to `cli/loadout/commands.py`:
```python
def _register_check(sub):
    from . import check, settings_merge

    p = sub.add_parser("check", help="verify this machine's loadout setup")

    def run_check(a):
        text, code = check.format_results(check.run_checks())
        print(text)
        return code

    p.set_defaults(func=run_check)

    p = sub.add_parser("apply-settings", help="merge kit + personal settings into ~/.claude/settings.json")

    def run_apply(a):
        before, after = settings_merge.apply_settings()
        print("settings updated" if before != after else "settings already up to date")
        return 0

    p.set_defaults(func=run_apply)


EXTRA_COMMANDS.append(_register_check)
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run --python 3.12 --with pytest pytest -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: check and apply-settings commands

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Session hook, background maintenance, `update`

**Files:**
- Create: `cli/loadout/maintenance.py`, `tests/test_maintenance.py`
- Modify: `cli/loadout/commands.py`

**Interfaces:**
- Consumes: `paths`, `runner`, `versions`, `catalog`, `link.link_all/is_copy_mode`, `backup.Backup`, `settings_merge.apply_settings`, `jsonio`
- Produces:
  - `maintenance.DAY`, `maintenance.WEEK`
  - `maintenance.is_due(name, interval, now) -> bool`, `maintenance.touch(name, now)`
  - `maintenance.session_start(now) -> str | None` (JSON to print)
  - `maintenance.maintain(now) -> None`
  - `maintenance.pull_if_clean(root: Path) -> bool`
  - `maintenance.find_outdated() -> list[tuple[dict, tuple, tuple]]`
  - `maintenance.update(yes: bool, ask) -> int`
  - CLI `hook-session-start`, `maintenance`, `update [--yes]`

- [ ] **Step 1: Write the failing tests**

`tests/test_maintenance.py`:
```python
import json

from loadout import maintenance as m, paths, runner, versions


def test_is_due_and_touch(fake_home):
    assert m.is_due("x", m.DAY, 1000.0)
    m.touch("x", 1000.0)
    assert not m.is_due("x", m.DAY, 1000.0 + 10)
    assert m.is_due("x", m.DAY, 1000.0 + m.DAY)


def test_session_start_prints_pending_notice_once(fake_home, monkeypatch):
    monkeypatch.setattr(m, "_spawn_background", lambda: None)
    notice = paths.state_dir() / "pending-notice"
    notice.parent.mkdir(parents=True)
    notice.write_text("updates available")
    out = m.session_start(0.0)
    assert json.loads(out) == {"systemMessage": "updates available"}
    assert m.session_start(0.0) is None


def test_session_start_spawns_only_when_due(fake_home, monkeypatch):
    spawned = []
    monkeypatch.setattr(m, "_spawn_background", lambda: spawned.append(1))
    m.session_start(5.0)
    assert spawned == [1]
    m.touch("last-pull", 5.0)
    m.touch("last-update-check", 5.0)
    m.session_start(6.0)
    assert spawned == [1]


def test_pull_skipped_when_dirty(fake_home, fake_runner, tmp_path):
    fake_runner.responses[("git", "-C", str(tmp_path), "status", "--porcelain")] = runner.Result(0, " M x\n", "")
    assert m.pull_if_clean(tmp_path) is False
    assert not any("pull" in c for c in fake_runner.calls)


def test_maintain_writes_notice_for_outdated(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(m, "pull_if_clean", lambda root: False)
    monkeypatch.setattr(m, "find_outdated", lambda: [({"id": "serena"}, (1, 7, 0), (1, 8, 0))])
    m.maintain(100.0)
    text = (paths.state_dir() / "pending-notice").read_text()
    assert "serena 1.7.0 -> 1.8.0" in text and "loadout update" in text


def test_maintain_survives_offline(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(m, "pull_if_clean", lambda root: False)

    def boom(url):
        raise OSError("offline")

    monkeypatch.setattr(versions, "_fetch_json", boom)
    m.maintain(100.0)  # must not raise
    assert not (paths.state_dir() / "pending-notice").exists()


def test_update_reverts_settings_modified_by_installer(fake_home, fake_runner, monkeypatch):
    s = fake_home / ".claude/settings.json"
    s.parent.mkdir(parents=True)
    s.write_text('{"a": 1}\n')
    entry = {"id": "tool", "update": {"posix": [["tool-installer"]], "windows": [["tool-installer"]]}}
    monkeypatch.setattr(m, "find_outdated", lambda: [(entry, (1, 0, 0), (2, 0, 0))])

    def installer(cmd, cwd=None, timeout=300):
        fake_runner.calls.append(list(cmd))
        s.write_text('{"a": 1, "hooks": {"X": []}}\n')
        return runner.Result(0, "", "")

    monkeypatch.setattr(runner, "run", installer)
    assert m.update(yes=True, ask=lambda q: "") == 0
    assert json.loads(s.read_text()) == {"a": 1}
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_maintenance.py`
Expected: FAIL with `ModuleNotFoundError: loadout.maintenance`.

- [ ] **Step 3: Implement**

`cli/loadout/maintenance.py`:
```python
"""SessionStart hook, detached daily/weekly maintenance, and `loadout update` (spec §6.4)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

from . import catalog, link, paths, runner, versions
from .backup import Backup
from .jsonio import load_json, save_json

DAY = 86400.0
WEEK = 7 * DAY
NOTICE = "pending-notice"


def _stamp(name: str) -> Path:
    return paths.state_dir() / name


def is_due(name: str, interval: float, now: float) -> bool:
    try:
        return now - float(_stamp(name).read_text()) >= interval
    except (OSError, ValueError):
        return True


def touch(name: str, now: float) -> None:
    _stamp(name).parent.mkdir(parents=True, exist_ok=True)
    _stamp(name).write_text(str(now))


def _spawn_background() -> None:
    kwargs = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen([sys.executable, str(paths.kit_root() / "bin" / "loadout"), "maintenance"], **kwargs)


def session_start(now: float) -> str | None:
    out = None
    notice = _stamp(NOTICE)
    if notice.exists():
        out = json.dumps({"systemMessage": notice.read_text(encoding="utf-8").strip()})
        notice.unlink()
    if is_due("last-pull", DAY, now) or is_due("last-update-check", WEEK, now):
        _spawn_background()
    return out


def pull_if_clean(root: Path) -> bool:
    if not (root / ".git").exists() and not root.is_dir():
        return False
    status = runner.run(["git", "-C", str(root), "status", "--porcelain"], timeout=30)
    if not status.ok or status.stdout.strip():
        return False
    return runner.run(["git", "-C", str(root), "pull", "--ff-only", "-q"], timeout=120).ok


def find_outdated() -> list[tuple[dict, tuple, tuple]]:
    out = []
    for entry in catalog.binaries():
        if not runner.have(entry["id"]):
            continue
        local, latest = versions.local_version(entry), versions.latest_version(entry)
        if local and latest and latest > local:
            out.append((entry, local, latest))
    return out


def maintain(now: float) -> None:
    from .settings_merge import apply_settings

    if is_due("last-pull", DAY, now):
        touch("last-pull", now)
        pulled = [pull_if_clean(root) for root in (paths.kit_root(), paths.personal_root()) if (root / ".git").exists()]
        if any(pulled):
            try:
                apply_settings()
            except Exception as exc:  # never crash in the background; surface next session
                _stamp(NOTICE).write_text(f"loadout: could not apply settings after sync: {exc}")
            if link.is_copy_mode():
                link.link_all(Backup())
    if is_due("last-update-check", WEEK, now):
        touch("last-update-check", now)
        outdated = find_outdated()
        if outdated:
            items = ", ".join(f"{e['id']} {versions.fmt(a)} -> {versions.fmt(b)}" for e, a, b in outdated)
            _stamp(NOTICE).write_text(f"loadout: updates available for {items} → run `loadout update`")


def update(yes: bool, ask: Callable[[str], str]) -> int:
    settings_path = paths.claude_home() / "settings.json"
    before = load_json(settings_path)
    outdated = find_outdated()
    if not outdated:
        print("all tools up to date")
    for entry, local, latest in outdated:
        cmds = catalog.platform_cmds(entry, "update")
        print(f"{entry['id']}: {versions.fmt(local)} -> {versions.fmt(latest)}")
        if not cmds:
            print(f"  no update command for this platform. {entry.get('manual', '')}")
            continue
        for cmd in cmds:
            print("  command: " + " ".join(cmd))
        if not yes and ask("  run it? [y/N] ").strip().lower() != "y":
            continue
        for cmd in cmds:
            res = runner.run(cmd, timeout=900)
            print("  ok" if res.ok else f"  failed: {res.stderr.strip()[:300]}")
    after = load_json(settings_path)
    if after != before:
        print("an installer modified ~/.claude/settings.json; reverting to the kit-merged version")
        save_json(settings_path, before)
    runner.run(["claude", "plugin", "marketplace", "update"], timeout=300)
    return 0
```

Append to `cli/loadout/commands.py`:
```python
def _register_maintenance(sub):
    import time

    from . import maintenance
    from .__main__ import _ask

    p = sub.add_parser("hook-session-start", help=argparse_hidden())

    def hook(a):
        try:
            out = maintenance.session_start(time.time())
        except Exception:
            return 0  # a hook must never break a session
        if out:
            print(out)
        return 0

    p.set_defaults(func=hook)

    p = sub.add_parser("maintenance", help=argparse_hidden())

    def maint(a):
        try:
            maintenance.maintain(time.time())
        except Exception:
            pass
        return 0

    p.set_defaults(func=maint)

    p = sub.add_parser("update", help="update outdated tool binaries")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=lambda a: maintenance.update(a.yes, _ask))


def argparse_hidden():
    import argparse
    return argparse.SUPPRESS


EXTRA_COMMANDS.append(_register_maintenance)
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run --python 3.12 --with pytest pytest -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: session hook, background maintenance and update with settings guard

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: `bootstrap` (prereqs, personal wizard, plugins, secrets) + shims + fresh-HOME test

**Files:**
- Create: `cli/loadout/bootstrap.py`, `bootstrap.sh`, `bootstrap.ps1`, `tests/test_bootstrap.py`
- Modify: `cli/loadout/commands.py`

**Interfaces:**
- Consumes: everything above
- Produces:
  - `bootstrap.check_prereqs(install: bool, ask) -> list[str]` (missing names)
  - `bootstrap.ensure_personal(ask) -> str`
  - `bootstrap.setup_plugins() -> list[str]`
  - `bootstrap.setup_secrets() -> list[str]`
  - `bootstrap.RC_LINE`
  - `bootstrap.bootstrap(install, yes, plugins, adopt_step, ask) -> int`
  - CLI `bootstrap [--install] [--yes] [--no-plugins] [--no-adopt]`

- [ ] **Step 1: Write the failing tests**

`tests/test_bootstrap.py`:
```python
import json
import os
import subprocess
import sys

from loadout import bootstrap as b, paths


def test_personal_wizard_renders_template(fake_home, fake_runner):
    answers = iter(["", "Max", "Student", "Python", "short answers"])
    b.ensure_personal(lambda q: next(answers))
    me = (paths.personal_root() / "rules/me.md").read_text()
    assert "Max" in me and "Python" in me and "{{" not in me
    assert json.loads((paths.personal_root() / "settings.json").read_text()) == {}


def test_personal_clone(fake_home, fake_runner):
    answers = iter(["git@github.com:me/loadout-personal.git"])
    b.ensure_personal(lambda q: next(answers))
    assert ["git", "clone", "git@github.com:me/loadout-personal.git", str(paths.personal_root())] in fake_runner.calls


def test_secrets_setup_idempotent(fake_home, fake_runner):
    (fake_home / ".bashrc").write_text("# mine\n")
    b.setup_secrets()
    b.setup_secrets()
    rc = (fake_home / ".bashrc").read_text()
    assert rc.count(b.RC_MARKER) == 1
    if os.name != "nt":
        assert oct(paths.secrets_file().stat().st_mode & 0o777) == "0o600"


def test_setup_plugins_adds_marketplaces_and_installs_missing(fake_home, fake_runner):
    (paths.personal_root()).mkdir(parents=True)
    from loadout import runner
    fake_runner.responses[("claude", "plugin", "marketplace", "list")] = runner.Result(0, "claude-plugins-official\nimpeccable\n", "")
    b.setup_plugins()
    assert ["claude", "plugin", "marketplace", "add", "jonasyr/agent-loadout"] in fake_runner.calls
    assert ["claude", "plugin", "marketplace", "add", "pbakaus/impeccable"] not in fake_runner.calls
    assert ["claude", "plugin", "install", "loadout@agent-loadout", "--scope", "user"] in fake_runner.calls


def test_fresh_home_bootstrap_end_to_end(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home)}
    script = paths.kit_root() / "bin" / "loadout"
    proc = subprocess.run([sys.executable, str(script), "bootstrap", "--yes", "--no-plugins", "--no-adopt"],
                          input="\nTester\nDev\nPython\nnone\n", env=env, capture_output=True, text=True, timeout=120)
    assert (home / ".claude/rules/loadout/tooling.md").exists(), proc.stdout + proc.stderr
    assert (home / ".claude/rules/personal/me.md").exists()
    settings = json.loads((home / ".claude/settings.json").read_text())
    assert settings["enabledPlugins"]["loadout@agent-loadout"] is True
    assert (home / ".config/loadout/secrets.env").exists()
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_bootstrap.py`
Expected: FAIL with `ModuleNotFoundError: loadout.bootstrap`.

- [ ] **Step 3: Implement**

`cli/loadout/bootstrap.py`:
```python
"""`loadout bootstrap` (spec §6.1). Safe to re-run."""
from __future__ import annotations

import os
from typing import Callable

from . import adopt, catalog, check, link, paths, runner, scaffold, settings_merge
from .backup import Backup
from .jsonio import load_json

Ask = Callable[[str], str]
RC_MARKER = "# loadout secrets"
RC_LINE = (f'{RC_MARKER}\n[ -f "$HOME/.config/loadout/secrets.env" ] && '
           'set -a && . "$HOME/.config/loadout/secrets.env" && set +a\n')
PS_BLOCK = (f"{RC_MARKER}\n$f = Join-Path $HOME '.config/loadout/secrets.env'\n"
            "if (Test-Path $f) { Get-Content $f | ForEach-Object { if ($_ -match '^\\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') "
            "{ [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2].Trim('\"'), 'Process') } } }\n")


def _step(title: str) -> None:
    print(f"\n== {title}")


def check_prereqs(install: bool, ask: Ask) -> list[str]:
    missing = []
    for entry in catalog.binaries():
        name = entry["id"]
        if runner.have(name) or not (entry.get("required") or entry["status"] == "recommended"):
            continue
        cmds = catalog.platform_cmds(entry, "install")
        if install and cmds:
            for cmd in cmds:
                print("installing: " + " ".join(cmd))
                res = runner.run(cmd, timeout=900)
                if not res.ok:
                    print(f"  failed: {res.stderr.strip()[:300]}")
        if not runner.have(name):
            hint = "re-run with --install" if cmds else entry.get("manual", "")
            print(f"missing {'(required) ' if entry.get('required') else ''}{name}: {hint}")
            missing.append(name)
    if runner.have("gh"):
        if runner.run(["gh", "auth", "status"], timeout=20).ok:
            runner.run(["gh", "auth", "setup-git"], timeout=20)
        else:
            print("gh is not logged in: run `gh auth login` (needed for private marketplaces)")
    return missing


def ensure_personal(ask: Ask) -> str:
    root = paths.personal_root()
    if root.exists():
        return f"personal layer: {root}"
    url = ask("Personal layer: git URL to clone (empty = create a starter one): ").strip()
    if url:
        res = runner.run(["git", "clone", url, str(root)], timeout=300)
        return f"cloned {url} -> {root}" if res.ok else f"clone failed: {res.stderr.strip()}"
    values = {
        "NAME": ask("Your name: ").strip() or "me",
        "ROLE": ask("Your role (e.g. backend developer, CS student): ").strip() or "developer",
        "LANGUAGES": ask("Main languages/stacks: ").strip() or "(not specified)",
        "PREFERENCES": ask("Working preferences (e.g. concise answers, ask before deleting): ").strip() or "(not specified)",
    }
    template = paths.kit_root() / "templates" / "personal"
    for src in template.rglob("*"):
        if src.is_file():
            dest = root / src.relative_to(template)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(scaffold.render(src.read_text(encoding="utf-8"), values), encoding="utf-8")
    return f"created starter personal layer at {root} (make it a git repo to sync it across machines)"


def setup_plugins() -> list[str]:
    out = []
    desired = settings_merge.desired_settings()
    listed = runner.run(["claude", "plugin", "marketplace", "list"], timeout=60).stdout
    for name, cfg in desired.get("extraKnownMarketplaces", {}).items():
        if name in listed:
            continue
        src = cfg["source"]
        origin = src.get("repo") or src.get("url")
        res = runner.run(["claude", "plugin", "marketplace", "add", origin], timeout=300)
        out.append(f"marketplace {name}: {'added' if res.ok else 'failed: ' + res.stderr.strip()}")
    installed = load_json(paths.claude_home() / "plugins" / "installed_plugins.json").get("plugins", {})
    for plugin_id, on in desired.get("enabledPlugins", {}).items():
        if on and plugin_id not in installed:
            res = runner.run(["claude", "plugin", "install", plugin_id, "--scope", "user"], timeout=600)
            out.append(f"plugin {plugin_id}: {'installed' if res.ok else 'failed: ' + res.stderr.strip()}")
    return out


def setup_secrets() -> list[str]:
    out = []
    path = paths.secrets_file()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text((paths.kit_root() / "secrets.env.example").read_text(encoding="utf-8"), encoding="utf-8")
        out.append(f"created {path}")
    if os.name != "nt":
        os.chmod(path, 0o600)
        targets = [paths.home() / ".bashrc", paths.home() / ".zshrc"]
        block = RC_LINE
    else:
        res = runner.run(["powershell", "-NoProfile", "-Command", "$PROFILE"], timeout=30)
        targets = [__import__("pathlib").Path(res.stdout.strip())] if res.ok and res.stdout.strip() else []
        block = PS_BLOCK
    for rc in targets:
        if os.name != "nt" and not rc.exists():
            continue
        text = rc.read_text(encoding="utf-8") if rc.exists() else ""
        if RC_MARKER in text:
            continue
        rc.parent.mkdir(parents=True, exist_ok=True)
        rc.write_text(text + ("" if text.endswith("\n") or not text else "\n") + block, encoding="utf-8")
        out.append(f"added secrets loading to {rc}")
    empty = [line.split("=", 1)[0] for line in path.read_text(encoding="utf-8").splitlines()
             if line and not line.startswith("#") and line.endswith("=")]
    if empty:
        out.append(f"empty secrets: {', '.join(empty)}")
    return out


def bootstrap(install: bool, yes: bool, plugins: bool, adopt_step: bool, ask: Ask) -> int:
    _step("Prerequisites")
    check_prereqs(install, ask)
    _step("Personal layer")
    print(ensure_personal(ask))
    _step("Links")
    bk = Backup()
    for line in link.link_all(bk) + link.link_bin(bk):
        print(line)
    _step("Settings")
    before, after = settings_merge.apply_settings()
    print("settings updated" if before != after else "settings already up to date")
    if plugins:
        _step("Marketplaces and plugins")
        for line in setup_plugins():
            print(line)
    if adopt_step:
        _step("Adopt existing setup")
        adopt.run(apply_changes=True, groups=None, skip=set(), yes=yes, ask=ask)
    _step("Secrets")
    for line in setup_secrets():
        print(line)
    if not bk.empty:
        print(f"\nbackup: {bk.root}  (undo: loadout restore {bk.root})")
    _step("Check")
    text, code = check.format_results(check.run_checks())
    print(text)
    print("\nRestart Claude Code to load plugins and rules.")
    return code
```

Append to `cli/loadout/commands.py`:
```python
def _register_bootstrap(sub):
    from . import bootstrap
    from .__main__ import _ask

    p = sub.add_parser("bootstrap", help="set up (or repair) this machine")
    p.add_argument("--install", action="store_true", help="install missing tool binaries")
    p.add_argument("--yes", action="store_true", help="accept defaults (adopt applies remove/migrate/scope-down/update)")
    p.add_argument("--no-plugins", action="store_true")
    p.add_argument("--no-adopt", action="store_true")
    p.set_defaults(func=lambda a: bootstrap.bootstrap(a.install, a.yes, not a.no_plugins, not a.no_adopt, _ask))


EXTRA_COMMANDS.append(_register_bootstrap)
```

`bootstrap.sh`:
```bash
#!/usr/bin/env bash
# Set up loadout on this machine. All logic lives in `loadout bootstrap`.
set -euo pipefail
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "loadout needs python3 (>= 3.10). Install it and re-run." >&2
  exit 1
fi
exec python3 bin/loadout bootstrap "$@"
```

`bootstrap.ps1`:
```powershell
# Set up loadout on this machine. All logic lives in `loadout bootstrap`.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  Write-Error 'loadout needs Python (>= 3.10). Install it (e.g. winget install Python.Python.3.12) and re-run.'
  exit 1
}
if (-not (Get-Command bash -ErrorAction SilentlyContinue)) {
  Write-Warning 'Git Bash not found: Claude Code hooks need Git for Windows.'
}
python bin/loadout bootstrap @args
exit $LASTEXITCODE
```

Then: `chmod +x bootstrap.sh`.

- [ ] **Step 4: Run to verify pass**

Run: `uv run --python 3.12 --with pytest pytest -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: bootstrap with personal wizard, plugins, secrets; sh/ps1 shims

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10b: Configure wizard (engine, CLI wizard, personal MCP servers, catalog offers)

**Files:**
- Create: `cli/loadout/personal_mcp.py`, `cli/loadout/configure.py`, `tests/test_configure.py`, `scripts/add_catalog_offers.py` (one-off; deleted after use)
- Modify: `catalog.json` (via the script), `cli/loadout/commands.py`, `cli/loadout/bootstrap.py` (`bootstrap()`), `cli/loadout/maintenance.py` (`maintain()`)

**Interfaces:**
- Consumes: `settings_merge.desired_settings/apply_settings`, `catalog.load/match`, `profiles.list_profiles/load_profile`, `bootstrap.setup_plugins`, `runner`, `paths`, `jsonio`, `scaffold.render`
- Produces:
  - `personal_mcp.apply_mcp() -> list[str]`
  - `configure.Addon(key, label, category, reason, kind, target, default_on)`
  - `configure.addons() -> list[Addon]`, `configure.is_on(addon) -> bool`
  - `configure.set_plugin(plugin_id: str, on: bool) -> None`
  - `configure.set_mcp(catalog_id: str, on: bool) -> list[str]` (warnings, e.g. missing env vars)
  - `configure.set_pref(key: str, raw_json: str) -> None`
  - `configure.show() -> str`, `configure.apply_all(ask) -> None`, `configure.wizard(ask, first_run: bool) -> int`
  - CLI `loadout configure [--first-run]`, `loadout configure show`, `loadout configure set plugin|mcp|pref <name> <value>`

- [ ] **Step 1: Add catalog offers**

`scripts/add_catalog_offers.py`:
```python
"""One-off: add categories and global-add-on offers to catalog.json."""
import json
from pathlib import Path

path = Path(__file__).resolve().parent.parent / "catalog.json"
data = json.loads(path.read_text(encoding="utf-8"))
NEW = [
    {"id": "addon-playwright-mcp", "kind": "plugin", "status": "alternative", "category": "browser", "match": {"names": ["playwright@claude-plugins-official"]}, "reason": "Playwright as MCP server: richer tool surface, but snapshots land in context (playwright-cli is the cheaper default).", "offer": {"plugin": "playwright@claude-plugins-official"}},
    {"id": "addon-chrome-devtools", "kind": "plugin", "status": "alternative", "category": "browser", "match": {"names": ["chrome-devtools-mcp@claude-plugins-official"]}, "reason": "Performance traces, network and console debugging in Chrome. Heavy context per call; enable when you debug frontends often.", "offer": {"plugin": "chrome-devtools-mcp@claude-plugins-official"}},
    {"id": "addon-github", "kind": "plugin", "status": "alternative", "category": "workflow", "match": {"names": ["github@claude-plugins-official"]}, "reason": "Official GitHub MCP (Actions logs, security alerts). The gh CLI covers most needs with less context.", "offer": {"plugin": "github@claude-plugins-official"}},
    {"id": "addon-hookify", "kind": "plugin", "status": "recommended", "category": "workflow", "match": {"names": ["hookify@claude-plugins-official"]}, "reason": "Write guard-rail hooks as plain-language rules (e.g. block force-push to main).", "offer": {"plugin": "hookify@claude-plugins-official"}},
    {"id": "addon-exa", "kind": "plugin", "status": "alternative", "category": "research", "match": {"names": ["exa@claude-plugins-official"]}, "reason": "High-quality web/code/paper search (API key, paid per query). Built-in web search is usually enough.", "offer": {"plugin": "exa@claude-plugins-official"}},
    {"id": "addon-sentry", "kind": "plugin", "status": "alternative", "category": "data", "match": {"names": ["sentry@claude-plugins-official"]}, "reason": "Read Sentry issues and traces while debugging production errors.", "offer": {"plugin": "sentry@claude-plugins-official"}},
    {"id": "addon-dbhub-global", "kind": "mcp", "status": "alternative", "category": "data", "match": {"names": ["dbhub-global"]}, "reason": "DBHub for one database you use from every repo (otherwise use the db profile per project).", "offer": {"mcp": {"dbhub": {"type": "stdio", "command": "npx", "args": ["-y", "@bytebase/dbhub@1.4.0", "--transport", "stdio", "--dsn", "${DATABASE_URL}"]}}, "needs": ["DATABASE_URL"]}},
]
existing = {e["id"] for e in data["entries"]}
data["entries"] += [e for e in NEW if e["id"] not in existing]
path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"catalog now has {len(data['entries'])} entries")
```

Run: `python3 scripts/add_catalog_offers.py && git rm -q --cached scripts/add_catalog_offers.py 2>/dev/null; rm -r scripts`
Expected: `catalog now has N entries`. `tests/test_repo_static.py` still passes. Its `"offer"` and `"category"` keys aren't checked there, so extend `test_catalog_entries_are_well_formed` with:
```python
        if "offer" in e:
            assert set(e["offer"]) <= {"plugin", "mcp", "needs"}, e["id"]
            if "plugin" in e["offer"]:
                assert e["offer"]["plugin"].split("@")[1] in _declared_marketplaces(), e["id"]
            for server in e["offer"].get("mcp", {}).values():
                assert all("@latest" not in a for a in server.get("args", [])), e["id"]
```

- [ ] **Step 2: Write the failing tests**

`tests/test_configure.py`:
```python
import json

from loadout import configure, paths, personal_mcp, runner


def _personal_settings():
    p = paths.personal_root() / "settings.json"
    return json.loads(p.read_text()) if p.exists() else {}


def test_addons_include_kit_defaults_profile_plugins_and_offers(fake_home):
    keys = {a.key: a for a in configure.addons()}
    assert keys["plugin:superpowers@claude-plugins-official"].default_on is True
    assert keys["plugin:deepeval@claude-plugins-official"].default_on is False
    assert keys["plugin:hookify@claude-plugins-official"].category == "workflow"
    assert keys["mcp:addon-dbhub-global"].kind == "mcp"


def test_set_plugin_opt_out_and_back_keeps_personal_clean(fake_home):
    configure.set_plugin("superpowers@claude-plugins-official", False)
    assert _personal_settings()["enabledPlugins"] == {"superpowers@claude-plugins-official": False}
    configure.set_plugin("superpowers@claude-plugins-official", True)
    assert _personal_settings().get("enabledPlugins", {}) == {}


def test_set_plugin_opt_in_global(fake_home):
    configure.set_plugin("hookify@claude-plugins-official", True)
    assert _personal_settings()["enabledPlugins"]["hookify@claude-plugins-official"] is True


def test_set_pref_parses_json(fake_home):
    configure.set_pref("effortLevel", '"high"')
    configure.set_pref("alwaysThinkingEnabled", "false")
    assert _personal_settings()["effortLevel"] == "high"
    assert _personal_settings()["alwaysThinkingEnabled"] is False


def test_set_mcp_writes_personal_mcp_and_warns_missing_env(fake_home, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    warnings = configure.set_mcp("addon-dbhub-global", True)
    data = json.loads((paths.personal_root() / "mcp.json").read_text())
    assert "dbhub" in data["mcpServers"]
    assert any("DATABASE_URL" in w for w in warnings)
    configure.set_mcp("addon-dbhub-global", False)
    assert json.loads((paths.personal_root() / "mcp.json").read_text())["mcpServers"] == {}


def test_apply_mcp_adds_and_removes_only_managed(fake_home, fake_runner):
    (paths.personal_root()).mkdir(parents=True)
    (paths.personal_root() / "mcp.json").write_text(json.dumps({"mcpServers": {"dbhub": {"command": "npx"}}}))
    personal_mcp.apply_mcp()
    assert ["claude", "mcp", "add-json", "-s", "user", "dbhub", json.dumps({"command": "npx"})] in fake_runner.calls
    # simulate it is now present in ~/.claude.json alongside a user's own server
    paths.claude_json().write_text(json.dumps({"mcpServers": {"dbhub": {"command": "npx"}, "mine": {"command": "x"}}}))
    (paths.personal_root() / "mcp.json").write_text(json.dumps({"mcpServers": {}}))
    fake_runner.calls.clear()
    personal_mcp.apply_mcp()
    assert fake_runner.calls == [["claude", "mcp", "remove", "-s", "user", "dbhub"]]


def test_wizard_toggles_and_applies(fake_home, fake_runner, monkeypatch):
    applied = []
    monkeypatch.setattr(configure, "apply_all", lambda ask: applied.append(1))
    (paths.personal_root() / "rules").mkdir(parents=True)
    (paths.personal_root() / "rules/me.md").write_text("me")  # existing profile: wizard skips about-you
    menu = configure.addons()
    idx = [a.key for a in menu].index("plugin:hookify@claude-plugins-official") + 1
    answers = iter(["", "", str(idx), ""])  # keep effort, keep thinking, toggle hookify, done
    configure.wizard(lambda q: next(answers), first_run=False)
    assert _personal_settings()["enabledPlugins"]["hookify@claude-plugins-official"] is True
    assert applied == [1]


def test_show_marks_overrides(fake_home):
    configure.set_plugin("superpowers@claude-plugins-official", False)
    text = configure.show()
    assert "superpowers@claude-plugins-official" in text and "off (personal)" in text
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_configure.py`
Expected: FAIL with `ModuleNotFoundError: loadout.configure`.

- [ ] **Step 4: Implement**

`cli/loadout/personal_mcp.py`:
```python
"""Apply <personal>/mcp.json as user-scope MCP servers; remove only servers the kit applied before."""
from __future__ import annotations

import json

from . import paths, runner
from .jsonio import load_json, save_json


def apply_mcp() -> list[str]:
    desired = load_json(paths.personal_root() / "mcp.json").get("mcpServers", {})
    snap = paths.state_dir() / "managed-mcp.json"
    previous = load_json(snap).get("mcpServers", {})
    current = load_json(paths.claude_json()).get("mcpServers", {})
    out = []
    for name, cfg in desired.items():
        if current.get(name) == cfg:
            continue
        if name in current:
            runner.run(["claude", "mcp", "remove", "-s", "user", name])
        res = runner.run(["claude", "mcp", "add-json", "-s", "user", name, json.dumps(cfg)])
        out.append(f"mcp {name}: {'added' if res.ok else 'failed: ' + res.stderr.strip()}")
    for name, cfg in previous.items():
        if name not in desired and current.get(name) == cfg:
            res = runner.run(["claude", "mcp", "remove", "-s", "user", name])
            out.append(f"mcp {name}: {'removed' if res.ok else 'failed: ' + res.stderr.strip()}")
    save_json(snap, {"mcpServers": desired})
    return out
```

`cli/loadout/configure.py`:
```python
"""Configure wizard: defaults stay as the kit ships them; choices go into the personal layer (spec §6.4)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Callable

from . import catalog, paths, profiles, runner, scaffold
from .jsonio import load_json, save_json

Ask = Callable[[str], str]
PREFS = [("effortLevel", "Effort level (low/medium/high)", str),
         ("alwaysThinkingEnabled", "Always use extended thinking (true/false)", None)]


@dataclass
class Addon:
    key: str
    label: str
    category: str
    reason: str
    kind: str        # plugin | mcp
    target: str      # plugin id or catalog id
    default_on: bool


def _personal_settings_path():
    return paths.personal_root() / "settings.json"


def _kit_plugins() -> dict:
    return load_json(paths.kit_root() / "settings.base.json").get("enabledPlugins", {})


def addons() -> list[Addon]:
    out, seen = [], set()
    for pid, on in _kit_plugins().items():
        entry = catalog.match("plugin", pid) or {}
        out.append(Addon(f"plugin:{pid}", pid, entry.get("category", "kit default"), entry.get("reason", "Enabled by the kit."), "plugin", pid, bool(on)))
        seen.add(pid)
    for name in profiles.list_profiles():
        prof = profiles.load_profile(name)
        for pid in prof.install:
            if pid not in seen:
                out.append(Addon(f"plugin:{pid}", pid, f"profile {name}", prof.description, "plugin", pid, False))
                seen.add(pid)
    for entry in catalog.load():
        offer = entry.get("offer")
        if not offer:
            continue
        if "plugin" in offer and offer["plugin"] not in seen:
            out.append(Addon(f"plugin:{offer['plugin']}", offer["plugin"], entry.get("category", "other"), entry["reason"], "plugin", offer["plugin"], False))
            seen.add(offer["plugin"])
        elif "mcp" in offer:
            out.append(Addon(f"mcp:{entry['id']}", ", ".join(offer["mcp"]), entry.get("category", "other"), entry["reason"], "mcp", entry["id"], False))
    return out


def is_on(addon: Addon) -> bool:
    if addon.kind == "plugin":
        personal = load_json(_personal_settings_path()).get("enabledPlugins", {})
        return personal.get(addon.target, addon.default_on)
    entry = next(e for e in catalog.load() if e["id"] == addon.target)
    servers = load_json(paths.personal_root() / "mcp.json").get("mcpServers", {})
    return all(name in servers for name in entry["offer"]["mcp"])


def set_plugin(plugin_id: str, on: bool) -> None:
    data = load_json(_personal_settings_path())
    plugins = data.setdefault("enabledPlugins", {})
    if bool(_kit_plugins().get(plugin_id, False)) == on:
        plugins.pop(plugin_id, None)   # same as the kit default: no override needed
    else:
        plugins[plugin_id] = on
    if not plugins:
        data.pop("enabledPlugins")
    save_json(_personal_settings_path(), data)


def set_mcp(catalog_id: str, on: bool) -> list[str]:
    entry = next((e for e in catalog.load() if e["id"] == catalog_id and "mcp" in e.get("offer", {})), None)
    if entry is None:
        raise ValueError(f"no MCP add-on '{catalog_id}' in the catalog")
    path = paths.personal_root() / "mcp.json"
    data = load_json(path)
    servers = data.setdefault("mcpServers", {})
    for name, cfg in entry["offer"]["mcp"].items():
        if on:
            servers[name] = cfg
        else:
            servers.pop(name, None)
    save_json(path, data)
    return [f"{var} is not set: add it to {paths.secrets_file()}" for var in entry["offer"].get("needs", [])
            if on and not os.environ.get(var)]


def set_pref(key: str, raw_json: str) -> None:
    try:
        value = json.loads(raw_json)
    except json.JSONDecodeError:
        value = raw_json
    data = load_json(_personal_settings_path())
    data[key] = value
    save_json(_personal_settings_path(), data)


def show() -> str:
    lines = []
    for a in addons():
        on = is_on(a)
        source = "default" if on == a.default_on else "personal"
        lines.append(f"{'on' if on else 'off'} ({source})  [{a.category}] {a.label}")
    personal = load_json(_personal_settings_path())
    prefs = {k: v for k, v in personal.items() if k not in ("enabledPlugins", "extraKnownMarketplaces")}
    if prefs:
        lines.append("preferences: " + json.dumps(prefs, ensure_ascii=False))
    return "\n".join(lines)


def apply_all(ask: Ask) -> None:
    from .bootstrap import setup_plugins
    from .personal_mcp import apply_mcp
    from .settings_merge import apply_settings

    apply_settings()
    for line in setup_plugins() + apply_mcp():
        print(line)
    root = paths.personal_root()
    if (root / ".git").exists():
        status = runner.run(["git", "-C", str(root), "status", "--porcelain"])
        if status.stdout.strip() and ask("commit and push your personal layer? [y/N] ").strip().lower() == "y":
            runner.run(["git", "-C", str(root), "add", "-A"])
            runner.run(["git", "-C", str(root), "commit", "-m", "chore: update loadout preferences"])
            runner.run(["git", "-C", str(root), "push"])
    print("Restart Claude Code (or run /reload-plugins) to load the changes.")


def _about_you(ask: Ask) -> None:
    values = {
        "NAME": ask("Your name: ").strip() or "me",
        "ROLE": ask("Your role (e.g. backend developer, CS student): ").strip() or "developer",
        "LANGUAGES": ask("Main languages/stacks: ").strip() or "(not specified)",
        "PREFERENCES": ask("Working preferences (e.g. concise answers, ask before deleting): ").strip() or "(not specified)",
    }
    template = (paths.kit_root() / "templates/personal/rules/me.md").read_text(encoding="utf-8")
    me = paths.personal_root() / "rules" / "me.md"
    me.parent.mkdir(parents=True, exist_ok=True)
    me.write_text(scaffold.render(template, values), encoding="utf-8")


def wizard(ask: Ask, first_run: bool) -> int:
    if first_run or not (paths.personal_root() / "rules" / "me.md").exists():
        print("\n-- About you (stored in your personal layer, loaded every session)")
        _about_you(ask)
    print("\n-- Preferences (enter = keep current)")
    personal = load_json(_personal_settings_path())
    for key, label, _ in PREFS:
        answer = ask(f"{label} [{personal.get(key, 'kit default')}]: ").strip()
        if answer:
            set_pref(key, answer if answer in ("true", "false") else json.dumps(answer))
    menu = addons()
    while True:
        print("\n-- Global add-ons (toggle by number; enter = done)")
        category = None
        for i, a in enumerate(menu, 1):
            if a.category != category:
                category = a.category
                print(f"  {category}")
            print(f"   {i:2d}. [{'x' if is_on(a) else ' '}] {a.label} — {a.reason}")
        answer = ask("toggle: ").strip()
        if not answer:
            break
        for token in answer.replace(" ", "").split(","):
            if token.isdigit() and 1 <= int(token) <= len(menu):
                a = menu[int(token) - 1]
                if a.kind == "plugin":
                    set_plugin(a.target, not is_on(a))
                else:
                    for warning in set_mcp(a.target, not is_on(a)):
                        print(f"  note: {warning}")
    apply_all(ask)
    return 0
```

Append to `cli/loadout/commands.py`:
```python
def _register_configure(sub):
    from . import configure
    from .__main__ import _ask

    p = sub.add_parser("configure", help="choose preferences and global add-ons (personal layer)")
    p.add_argument("action", nargs="?", choices=["show", "set"])
    p.add_argument("kind", nargs="?", choices=["plugin", "mcp", "pref"])
    p.add_argument("name", nargs="?")
    p.add_argument("value", nargs="?")
    p.add_argument("--first-run", action="store_true")

    def run(a):
        if a.action is None:
            return configure.wizard(_ask, a.first_run)
        if a.action == "show":
            print(configure.show())
            return 0
        if not (a.kind and a.name and a.value):
            raise ValueError("usage: loadout configure set plugin|mcp|pref <name> <value>")
        if a.kind == "plugin":
            configure.set_plugin(a.name, a.value == "on")
        elif a.kind == "mcp":
            for warning in configure.set_mcp(a.name, a.value == "on"):
                print(f"note: {warning}")
        else:
            configure.set_pref(a.name, a.value)
        configure.apply_all(lambda q: "n")
        return 0

    p.set_defaults(func=run)


EXTRA_COMMANDS.append(_register_configure)
```

In `cli/loadout/bootstrap.py`:
- `ensure_personal`: replace the starter branch (from the `values = {` line to the end of the function) with a call to the wizard's about-you step, so the same questions aren't duplicated:
```python
    root.mkdir(parents=True, exist_ok=True)
    (root / "settings.json").write_text("{}\n", encoding="utf-8")
    from .configure import _about_you
    _about_you(ask)
    return f"created starter personal layer at {root} (make it a git repo to sync it across machines)"
```
- In `bootstrap()`, after the "Settings" step, add:
```python
    from .personal_mcp import apply_mcp
    for line in apply_mcp():
        print(line)
    if not yes and ask("Customize preferences and global add-ons now? [y/N] ").strip().lower() == "y":
        from .configure import wizard
        wizard(ask, first_run=False)
```

In `cli/loadout/maintenance.py` `maintain()`, right after the `apply_settings()` call inside `if any(pulled):`, add:
```python
                from .personal_mcp import apply_mcp
                apply_mcp()
```

Update `tests/test_bootstrap.py::test_personal_wizard_renders_template`. The answers are now: clone URL (empty), name, role, languages, preferences. That's the same order, so the test stays valid. The fresh-HOME test pipes `\nTester\nDev\nPython\nnone\n` and runs with `--yes`, so the customize prompt is skipped. No change needed.

- [ ] **Step 5: Run to verify pass**

Run: `uv run --python 3.12 --with pytest pytest -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: configure wizard and engine, personal MCP servers, catalog add-on offers

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: loadout plugin and marketplace (MCP config, hooks, hook smoke tests)

**Files:**
- Create: `.claude-plugin/marketplace.json`, `plugins/loadout/.claude-plugin/plugin.json`, `plugins/loadout/.mcp.json`, `plugins/loadout/hooks/hooks.json`, `plugins/loadout/hooks/run.sh`, `plugins/loadout/hooks/subagent-context.sh`, `tests/test_hooks.py`

**Interfaces:**
- Consumes: `loadout hook-session-start` (Task 9), binaries `serena-hooks`, `rtk`, `codebase-memory-mcp`
- Produces: plugin `loadout@agent-loadout` with MCP servers `serena` and `codebase-memory-mcp`; tool prefix `mcp__plugin_loadout_serena__`

- [ ] **Step 1: Write the failing tests**

`tests/test_hooks.py`:
```python
import json
import os
import subprocess

import pytest

from loadout import paths

PLUGIN = paths.kit_root() / "plugins" / "loadout"
pytestmark = pytest.mark.skipif(os.name == "nt", reason="hook scripts run under bash")


def _commands():
    hooks = json.loads((PLUGIN / "hooks/hooks.json").read_text())["hooks"]
    return [h["command"] for groups in hooks.values() for g in groups for h in g["hooks"]]


def test_every_hook_uses_plugin_root_and_has_timeout():
    hooks = json.loads((PLUGIN / "hooks/hooks.json").read_text())["hooks"]
    for groups in hooks.values():
        for g in groups:
            for h in g["hooks"]:
                assert "${CLAUDE_PLUGIN_ROOT}" in h["command"]
                assert h.get("timeout")


@pytest.mark.parametrize("args", [
    ["serena-hooks", "activate", "--client=claude-code"],
    ["rtk", "hook", "claude"],
    ["loadout", "hook-session-start"],
    ["--soft", "codebase-memory-mcp", "hook-augment"],
])
def test_run_sh_is_silent_noop_when_binary_missing(tmp_path, args):
    env = {"PATH": str(tmp_path), "HOME": str(tmp_path)}
    proc = subprocess.run(["/bin/bash", str(PLUGIN / "hooks/run.sh"), *args], env=env, capture_output=True, text=True, input="{}")
    assert proc.returncode == 0
    assert proc.stdout == "" and proc.stderr == ""


def test_soft_mode_swallows_failures(tmp_path):
    fake = tmp_path / "failing-tool"
    fake.write_text("#!/bin/sh\necho oops >&2\nexit 3\n")
    fake.chmod(0o755)
    env = {"PATH": f"{tmp_path}:/usr/bin:/bin"}
    proc = subprocess.run(["/bin/bash", str(PLUGIN / "hooks/run.sh"), "--soft", "failing-tool"], env=env, capture_output=True, text=True)
    assert proc.returncode == 0 and proc.stderr == ""


def test_subagent_context_is_valid_json(tmp_path):
    proc = subprocess.run(["/bin/bash", str(PLUGIN / "hooks/subagent-context.sh")], env={"PATH": str(tmp_path)}, capture_output=True, text=True)
    data = json.loads(proc.stdout)
    assert data["hookSpecificOutput"]["hookEventName"] == "SubagentStart"
    assert "codebase-memory" in data["hookSpecificOutput"]["additionalContext"]


def test_marketplace_lists_kit_core_without_version():
    market = json.loads((paths.kit_root() / ".claude-plugin/marketplace.json").read_text())
    assert market["name"] == "agent-loadout"
    assert market["plugins"][0]["source"] == "./plugins/loadout"
    plugin = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text())
    assert "version" not in plugin and "version" not in market["plugins"][0]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_hooks.py`
Expected: FAIL (`FileNotFoundError` for hooks.json).

- [ ] **Step 3: Create the plugin files**

`.claude-plugin/marketplace.json`:
```json
{
  "$schema": "https://anthropic.com/claude-code/marketplace.schema.json",
  "name": "agent-loadout",
  "owner": { "name": "Jonas Weirauch" },
  "metadata": { "description": "agent-loadout: shareable, self-updating Claude Code setup" },
  "plugins": [
    {
      "name": "loadout",
      "description": "Core of agent-loadout: Serena and codebase-memory MCP servers, tool hooks, onboarding and documentation skills.",
      "source": "./plugins/loadout",
      "category": "development"
    }
  ]
}
```

`plugins/loadout/.claude-plugin/plugin.json`:
```json
{
  "name": "loadout",
  "description": "Core of agent-loadout: Serena and codebase-memory MCP servers, tool hooks, onboarding and documentation skills.",
  "author": { "name": "Jonas Weirauch" },
  "homepage": "https://github.com/jonasyr/agent-loadout",
  "repository": "https://github.com/jonasyr/agent-loadout",
  "license": "MIT"
}
```

`plugins/loadout/.mcp.json`:
```json
{
  "mcpServers": {
    "serena": {
      "command": "serena",
      "args": ["start-mcp-server", "--context=claude-code", "--project-from-cwd"]
    },
    "codebase-memory-mcp": {
      "command": "codebase-memory-mcp"
    }
  }
}
```

`plugins/loadout/hooks/run.sh`:
```bash
#!/usr/bin/env bash
# Run a hook command only if its binary is installed, so a machine without a tool
# simply runs without that hook. With --soft, errors are swallowed (exit 0, no stderr).
soft=0
if [ "${1:-}" = "--soft" ]; then soft=1; shift; fi
command -v "$1" >/dev/null 2>&1 || exit 0
if [ "$soft" = 1 ]; then
  "$@" 2>/dev/null
  exit 0
fi
exec "$@"
```

`plugins/loadout/hooks/subagent-context.sh`:
```bash
#!/usr/bin/env bash
# SubagentStart: subagents get a one-line pointer to the kit's tool routing.
printf '%s\n' '{"hookSpecificOutput":{"hookEventName":"SubagentStart","additionalContext":"Tool routing (loadout): structure and call chains -> codebase-memory-mcp; exact symbol lookup or edits -> Serena; text/config -> Grep/Read; library docs -> Context7; UI checks -> playwright-cli."}}'
```

`plugins/loadout/hooks/hooks.json`:
```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [
          { "type": "command", "command": "\"${CLAUDE_PLUGIN_ROOT}/hooks/run.sh\" serena-hooks activate --client=claude-code", "shell": "bash", "timeout": 15 },
          { "type": "command", "command": "\"${CLAUDE_PLUGIN_ROOT}/hooks/run.sh\" loadout hook-session-start", "shell": "bash", "timeout": 10 }
        ]
      }
    ],
    "SessionEnd": [
      {
        "matcher": "",
        "hooks": [
          { "type": "command", "command": "\"${CLAUDE_PLUGIN_ROOT}/hooks/run.sh\" serena-hooks cleanup --client=claude-code", "shell": "bash", "timeout": 10 }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          { "type": "command", "command": "\"${CLAUDE_PLUGIN_ROOT}/hooks/run.sh\" rtk hook claude", "shell": "bash", "timeout": 10 }
        ]
      },
      {
        "matcher": "mcp__plugin_loadout_serena__.*",
        "hooks": [
          { "type": "command", "command": "\"${CLAUDE_PLUGIN_ROOT}/hooks/run.sh\" serena-hooks auto-approve --client=claude-code", "shell": "bash", "timeout": 10 }
        ]
      },
      {
        "matcher": "Grep|Glob",
        "hooks": [
          { "type": "command", "command": "\"${CLAUDE_PLUGIN_ROOT}/hooks/run.sh\" --soft codebase-memory-mcp hook-augment", "shell": "bash", "timeout": 5 }
        ]
      }
    ],
    "SubagentStart": [
      {
        "matcher": "*",
        "hooks": [
          { "type": "command", "command": "\"${CLAUDE_PLUGIN_ROOT}/hooks/subagent-context.sh\"", "shell": "bash", "timeout": 5 }
        ]
      }
    ]
  }
}
```

Then: `chmod +x plugins/loadout/hooks/*.sh`.

- [ ] **Step 4: Run tests and validate the manifests**

Run: `uv run --python 3.12 --with pytest pytest -q && claude plugin validate --strict . && claude plugin validate --strict plugins/loadout`
Expected: tests PASS. Both validations exit 0. If `--strict` flags a field name, fix the field as the validator says (e.g. remove `shell` if reported as unknown) and re-run.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: loadout plugin with MCP servers and guarded hooks; marketplace manifest

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: Skills: onboard, docs-sync, docs-audit

**Files:**
- Create: `plugins/loadout/skills/onboard/SKILL.md`, `plugins/loadout/skills/docs-sync/SKILL.md`, `plugins/loadout/skills/docs-audit/SKILL.md`, `plugins/loadout/skills/configure/SKILL.md`, `tests/test_skills.py`

**Interfaces:**
- Consumes: rules `docs-policy.md`, `memory-policy.md`; `loadout init/profile`; superpowers skills
- Produces: `/loadout:onboard`, `/loadout:docs-sync`, `/loadout:docs-audit`, `/loadout:configure`

- [ ] **Step 1: Write the failing test**

`tests/test_skills.py`:
```python
import re

from loadout import paths

SKILLS = paths.kit_root() / "plugins/loadout/skills"


def test_skills_have_frontmatter_and_short_descriptions():
    for name in ("onboard", "docs-sync", "docs-audit", "configure"):
        text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
        m = re.match(r"---\nname: (.+)\ndescription: (.+)\n---\n", text)
        assert m, name
        assert m.group(1) == name
        assert len(m.group(2)) <= 400, f"{name} description too long (loaded every session)"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_skills.py`
Expected: FAIL (`FileNotFoundError`).

- [ ] **Step 3: Write the skills**

`plugins/loadout/skills/onboard/SKILL.md`:
```markdown
---
name: onboard
description: Set up a repository for agent work — new/empty repos get a guided project definition (purpose, stack, structure, first ADR); existing repos get an accurate AGENTS.md, Serena memories and a codebase-memory index. Use after `loadout init`, or when a repo has no AGENTS.md.
---

# Onboard a repository

Read `~/.claude/rules/loadout/docs-policy.md` and `memory-policy.md` first; everything you write must follow them.

## 1. Detect the mode

List tracked files (`git ls-files`; if not a git repo, list the directory).
- **New project**: no source files; only README, LICENSE, .gitignore, AGENTS.md/CLAUDE.md skeletons or docs skeletons.
- **Existing project**: anything else.

Say which mode you detected and why, and let the user correct you.

## 2a. New project

1. Invoke `superpowers:brainstorming` to settle what the project should become: purpose, users, success criteria, constraints, stack. Ask one question at a time.
2. When the design is agreed:
   - write `docs/README.md` (index) and `docs/adr/0001-<stack-decision>.md` (Context, Decision, Consequences, Status: accepted);
   - write `AGENTS.md`: purpose (one paragraph), commands (install/test/run for the chosen stack), hard conventions, map.
3. Suggest profiles for the stack (`loadout profile <name>`: web, db, android, thesis, sonar) and run the ones the user accepts. For a web stack, suggest `@playwright/test` for E2E tests.
4. Create the minimal directory skeleton the stack's conventions call for, such as package manifest, `src/`, `tests/` and a first passing test. Stop there; feature work goes through the normal superpowers flow.
5. Show the diff and commit after approval.

## 2b. Existing project

1. If the repo is not indexed, index it with codebase-memory-mcp (`index_repository`) and use `get_architecture` for the overview.
2. Commands: find how to install, test, lint and run (manifests, Makefile/justfile, CI config). Verify each with a harmless form (`--help`, `--version`, `--collect-only`, dry run). Never run something that deploys, deletes or writes outside the repo.
3. AGENTS.md:
   - **Missing:** write it.
   - **Exists:** repair it. Fix wrong commands and paths, remove content that duplicates `docs/` (link instead), keep it short.
   - **CLAUDE.md** with real content and no AGENTS.md: propose moving that content into AGENTS.md and replacing CLAUDE.md with `@AGENTS.md`; do it only after the user agrees.
4. Leave an existing `.mcp.json` and `.claude/settings.json` unchanged; mention what they configure.
5. Serena:
   - **No memories:** run Serena onboarding, but keep each memory a short summary plus links into `docs/`.
   - **Memories or docs already exist:** recommend `/loadout:docs-audit` instead of rewriting them here.
6. Show the diff and commit after approval (`docs: onboard repository for agents`).
```

`plugins/loadout/skills/docs-sync/SKILL.md`:
```markdown
---
name: docs-sync
description: Cheap end-of-feature documentation pass — find which doc layers (docs/, AGENTS.md, Serena memories, README) the current change affects and update only those, then verify links. Use after finishing a feature or before merging.
---

# Docs sync

Follow `~/.claude/rules/loadout/docs-policy.md`.

1. Determine the change: `git diff --stat <base>...HEAD` (base: the merge base with the default branch) plus uncommitted changes.
2. For each changed area, decide which facts changed (commands, behaviour, configuration, architecture, decisions) and which layer owns each fact.
3. Update the owning layer, normally `docs/`:
   - a new decision becomes an ADR in `docs/adr/`;
   - update AGENTS.md only if commands, conventions or the map changed;
   - update a Serena memory only if its summary or link became wrong, or if a gotcha was learned.
4. Check every link and path in the files you touched: relative links resolve, referenced files and symbols exist.
5. Show the diff. Commit separately from code (`docs: ...`) after approval.

Keep it proportional: a small change usually touches zero or one doc file. If you find widespread rot, stop and recommend `/loadout:docs-audit`.
```

`plugins/loadout/skills/docs-audit/SKILL.md`:
```markdown
---
name: docs-audit
description: Full, expensive audit of all docs and memories in a repo — verifies every claim against the current code, asks about anything unclear, and rewrites everything into the loadout docs structure (docs/ as single source of truth). Resumable. Use when docs or memories may be stale, wrong or duplicated.
---

# Docs audit

Thorough by design: it may take long and use many tokens. Correctness over speed. Follow `~/.claude/rules/loadout/docs-policy.md` and `memory-policy.md`.

## 0. Resume or start

- If `.loadout/docs-audit/` contains a checklist, resume it from the first unchecked item.
- Otherwise create `.loadout/docs-audit/<YYYY-MM-DD>.md` and make sure `.loadout/` is in `.gitignore` while the audit runs.
- Update the checklist after every step, so the audit survives context compaction or a new session.

## 1. Inventory

List every documentation artifact: `README*`, `AGENTS.md`, `CLAUDE.md`, `docs/**`, ADRs, `.serena/memories/*`, other `*.md` outside dependency dirs, and doc comments only where docs reference them. Record each in the checklist with its size.

## 2. Extract claims

For each artifact, extract atomic claims into the checklist:
- commands
- file paths
- symbols (functions, classes, config keys)
- parameters and defaults
- behaviour and architecture statements
- decisions and their rationale
- status claims ("implemented", "TODO", "deprecated")

Note where each claim lives (file and line).

## 3. Verify against the current code

Dispatch parallel subagents (superpowers:dispatching-parallel-agents), one per doc area or about 30 claims. Give each its claim list and these rules:
- **Symbols and structure:** codebase-memory-mcp (`search_graph`, `trace_path`, `get_code_snippet`) and Serena (`find_symbol`). Index first if needed.
- **Paths:** check existence.
- **Commands:** verify with harmless forms only (`--help`, `--version`, dry run, `--collect-only`). Ask the user before running tests or builds. Never run anything that deploys, deletes or writes outside the repo.
- **Behaviour:** read the implementing code; quote the lines that confirm or refute the claim.
- **Classification**, with evidence for each claim: `correct` | `stale` | `wrong` | `unclear` | `contradictory` (with the other claim's location) | `duplicated` | `misplaced` (wrong layer) | `unverifiable`.

Then find **missing** documentation: modules, entry points, CLI commands, config options and env vars that no doc mentions but that a user or contributor would need.

Record all results in the checklist.

## 4. Ask

Collect everything the code cannot settle:
- intent ("which of these two behaviours is intended?");
- open decisions;
- contradictions between docs;
- `unverifiable` claims;
- planned-but-unimplemented features.

Ask in batches of related questions (multiple choice where possible). Never guess intent. Record the answers in the checklist.

## 5. Plan the target structure

Propose the target layout before rewriting:
- `docs/` sections (Diátaxis where it fits: tutorials, how-to, reference, explanation; `docs/adr/` for decisions);
- what moves where;
- which memories shrink to a summary plus a link;
- which content is deleted as duplicate.

Get approval.

## 6. Rewrite

- Facts go into their single home in `docs/`; corrected per the verification and answers.
- Decisions found in prose become ADRs.
- `AGENTS.md`: short and accurate (purpose, verified commands, hard conventions, map).
- Serena memories: a 1–3 line summary plus link per topic, plus genuine agent notes (gotchas, task recipes, status). Delete memories that only duplicated docs.
- `README.md`: human entry point linking into `docs/`.

## 7. Validate

- Every relative link and referenced path resolves.
- Every symbol mentioned exists.
- Every remaining claim is either verified or confirmed by the user.

Re-run the checks on the rewritten files.

## 8. Report and commit

Present:
- counts per classification;
- the list of corrections (wrong → right, with evidence);
- open items the user deferred;
- the diff grouped by layer.

After approval, commit per layer (`docs: ...`, `docs(agents): ...`, `docs(memories): ...`). Delete the checklist and the temporary `.gitignore` entry.
```

`plugins/loadout/skills/configure/SKILL.md`:
```markdown
---
name: configure
description: Conversationally adjust the user's loadout setup — preferences, global add-ons (plugins, MCP servers) and opt-outs of kit defaults — stored in their personal layer. Use when the user wants to add, remove or change tools or preferences globally.
---

# Configure loadout

The kit's defaults stay untouched; every choice goes into the user's personal layer through the `loadout configure` engine.

1. Run `loadout configure show` to see the current state: each add-on on/off, whether that is the kit default or a personal override, and the preferences.
2. Ask what the user wants in their own words ("I do a lot of frontend debugging", "I never use Rust", "I want database access everywhere"). Ask one question at a time.
3. Map the answers to concrete changes, using the reasons in `catalog.json` (in the kit repo, `loadout` resolves it). Prefer the kit's scoping: suggest a project profile (`loadout profile <name>`) when something is only needed in some repos, and global only when it is needed almost everywhere. Mention context cost for heavy add-ons (e.g. chrome-devtools, many-skill plugins).
4. Present the planned changes as a short list and get a yes.
5. Apply each with `loadout configure set plugin <id> on|off`, `loadout configure set mcp <catalog-id> on|off` or `loadout configure set pref <key> <json>`. Relay any notes, e.g. missing environment variables and where to put them.
6. Tell the user to restart Claude Code or run `/reload-plugins`. If their personal layer is a git repo, offer to commit and push it.

Never edit `~/.claude/settings.json` or `~/.claude.json` directly; the engine keeps kit-managed and personal values apart.
```

- [ ] **Step 4: Run tests and validate**

Run: `uv run --python 3.12 --with pytest pytest -q && claude plugin validate --strict plugins/loadout`
Expected: PASS; validation exit 0.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: onboard, docs-sync, docs-audit and configure skills

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 13: README and CI

**Files:**
- Create: `README.md`, `.github/workflows/ci.yml`, `LICENSE` (MIT, copyright "Jonas Weirauch")

**Interfaces:**
- Consumes: everything above

- [ ] **Step 1: Write `README.md`**

README rules: lead with what it is and why; first success within 5 minutes; plain words, no jargon without a one-line explanation; tasks organized by what the reader wants to do; every command copy-pasteable; troubleshooting and uninstall included.

````markdown
# agent-loadout

**One command turns any machine's Claude Code into a clean, current, well-configured setup — and keeps it that way.**

Claude Code gets much better with the right plugins, MCP servers and instructions. But setups drift: every machine ends up different, old tools linger, versions go stale, and half of what is installed never gets used. loadout fixes that:

- **Curated defaults.** A small, researched set of tools that complement each other instead of overlapping. Every keep/drop decision is explained in [`catalog.json`](catalog.json).
- **Works on existing setups.** It shows what it would change and why, asks you first, and backs everything up. Undo is one command.
- **Stays up to date by itself.** Plugins auto-update; the kit and your personal settings sync daily; you get a notice when tool binaries have updates.
- **Yours on top.** Your preferences live in a separate *personal layer*. Change them with a wizard, in the terminal or by asking Claude.
- **Projects too.** One command prepares any repo, whether empty or years old, for agent work. One skill audits and fixes its documentation.

> Works on Linux, macOS and Windows. Needs Claude Code, git, Python 3.10+, Node.js and uv; `--install` installs what it can.

## Quick start (5 minutes)

```bash
git clone https://github.com/jonasyr/agent-loadout ~/agent-loadout
cd ~/agent-loadout
./bootstrap.sh --install          # Windows (PowerShell): .\bootstrap.ps1 --install
```

Answer a few questions:
- **Personal layer:** clone your personal repo, or answer four questions about yourself.
- **Existing setup:** review the plan for your current tools.
- **Add-ons:** optionally pick extras.

Then **restart Claude Code**. Check everything with:

```bash
loadout check
```

## How it works

```
┌──────────────── loadout (this repo, shared) ───────────────┐   ┌──── personal layer (yours) ────┐
│ loadout plugin  hooks · MCP servers · skills  (auto-updated) │   │ rules/me.md   who you are      │
│ rules/           how Claude should use the tools              │ + │ settings.json your overrides   │
│ catalog.json     what is good, superseded, optional — and why │   │ mcp.json      extra servers    │
│ profiles/        per-project add-ons (thesis, web, db, …)     │   │ profiles/     your own presets │
└───────────────────────────────────────────────────────────────┘   └────────────────────────────────┘
                                   │  loadout merges both
                                   ▼
            ~/.claude/  (your existing settings are kept; the kit only manages its own keys)
```

## Common tasks

| I want to… | Run |
|---|---|
| Set up a new machine | `./bootstrap.sh --install` |
| Clean up a machine that already has a Claude Code setup | `loadout adopt` (shows the plan) → `loadout adopt --apply` |
| Undo what loadout changed | `loadout restore ~/.claude/backups/loadout-<timestamp>` |
| Change preferences or add tools globally | `loadout configure`, or ask Claude: `/loadout:configure` |
| See what is on and why | `loadout configure show` |
| Start a new project | `mkdir app && cd app && loadout init`, then in Claude Code: `/loadout:onboard` |
| Prepare an existing repo | `loadout init` (never overwrites), then `/loadout:onboard` |
| Add a domain tool to one repo | `loadout profile thesis` (also: `web`, `db`, `sonar`, `android`) |
| Fix outdated or wrong docs in a repo | `/loadout:docs-audit` (thorough; asks when something is unclear) |
| Keep docs current after a feature | `/loadout:docs-sync` |
| Update tool binaries | `loadout update` |
| Check that everything is healthy | `loadout check` |

## What you get

**Global plugins:**

| Plugin | What it does for you |
|---|---|
| loadout | Code-navigation servers (Serena, codebase-memory), tool hooks, the onboard/configure/docs skills, update notices |
| superpowers | A disciplined workflow: brainstorm → plan → test-driven build → verify |
| frontend-design + impeccable | Distinctive UI, then audit and polish it |
| security-guidance | Warns about security mistakes while code is written |
| pyright / typescript / rust-analyzer LSP | Claude sees type errors right after each edit |
| context7 + microsoft-docs | Up-to-date library documentation instead of outdated training data |
| commit-commands, claude-md-management | Commits/PRs; keeping CLAUDE.md/AGENTS.md healthy |

**Command-line tools:** `playwright-cli` (Claude checks UIs in a real browser), `rtk` (shrinks noisy command output to save tokens), `serena`, `codebase-memory-mcp`.

**Per-project profiles:** `thesis` (academic research, RAG evaluation), `web` (browser debugging), `db` (database access), `sonar` (SonarQube), `android` (Kotlin).

**Optional add-ons** (turn on with `loadout configure`): Playwright MCP, Chrome DevTools, GitHub MCP, hookify, Exa search, Sentry, a global database connection. Each lists what it costs in context.

## Your personal layer

Your preferences live at `~/.config/loadout/personal` (or wherever `LOADOUT_PERSONAL` points):

| File | Purpose |
|---|---|
| `rules/me.md` | Who you are and how you like to work; loaded in every session |
| `settings.json` | Your overrides, e.g. `"effortLevel": "high"` or `"enabledPlugins": {"impeccable@impeccable": false}` |
| `mcp.json` | Extra MCP servers you want everywhere |
| `profiles/*.json` | Your own project presets |

You rarely edit these by hand: `loadout configure` does it for you. **To sync them across machines, make the folder a private git repo**; loadout pulls it daily.

## Staying up to date

| What | How |
|---|---|
| Plugins (including loadout) | Claude Code auto-updates them |
| This kit and your personal layer | Pulled at most once a day in the background (only when you have no local changes) |
| Tool binaries | Checked weekly; Claude Code shows "updates available → `loadout update`" |

## Secrets

Never put API keys into config files. Put them in `~/.config/loadout/secrets.env` (created for you, readable only by you):

```bash
DATABASE_URL=postgres://readonly:…@localhost/app
```

Your shell loads this file. MCP configs reference values as `${DATABASE_URL}`. `loadout adopt` finds keys already sitting in plain text and offers to move them.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `loadout: command not found` | Add `~/.local/bin` to your `PATH` (Windows: `%USERPROFILE%\.local\bin`) and open a new terminal |
| A plugin or MCP server is missing in Claude Code | Restart Claude Code; then `loadout check` lists what is missing and how to fix it |
| `invalid JSON in …/settings.json` | Fix the syntax error at the reported position, then `loadout apply-settings` |
| "settings drift" warning | Something changed a kit-managed value. Run `loadout apply-settings`, or put your preferred value in your personal `settings.json` |
| Windows: links were copied instead of linked | Enable Developer Mode (Settings → For developers) and re-run bootstrap; copies still work and are refreshed daily |
| Something went wrong after adopt | `loadout restore <backup path printed by adopt>` |

## FAQ

**Will it delete my stuff?** No. Anything it removes is moved into `~/.claude/backups/`, and `loadout restore` puts it back. Tools it doesn't know are left alone.

**I already have my own CLAUDE.md, hooks and settings.** They stay. The kit only manages its own keys. adopt *offers* to move your global CLAUDE.md into your personal layer.

**Does it cost many tokens?** It's built to cost fewer: heavy tools are per-project, tool documentation loads only when used, and rtk compresses command output. Check with `/context` in Claude Code.

**Codex / Gemini CLI / Cursor?** Not yet. The rules, catalog and docs model are agent-neutral, and support for other agents is on the roadmap.

## Uninstall

```bash
claude plugin uninstall loadout@agent-loadout
rm ~/.claude/rules/loadout ~/.claude/rules/personal ~/.local/bin/loadout
```

Your `~/.claude/settings.json` keeps the merged values. Remove the kit's `enabledPlugins` and `extraKnownMarketplaces` entries if you want, or restore an older backup from `~/.claude/backups/`.

## Contributing / development

```bash
uv run --python 3.12 --with pytest pytest -q
claude plugin validate --strict . && claude plugin validate --strict plugins/loadout
```

To propose a tool, add or adjust its `catalog.json` entry with a `reason`; that's where the "why" lives.

License: MIT
````

- [ ] **Step 2: Write `.github/workflows/ci.yml`**

```yaml
name: ci
on: [push, pull_request]

jobs:
  test:
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - run: uv run --python 3.12 --with pytest pytest -q

  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
      - run: npm install -g @anthropic-ai/claude-code
      - run: claude plugin validate --strict .
      - run: claude plugin validate --strict plugins/loadout
```

- [ ] **Step 3: Run the full suite locally**

Run: `uv run --python 3.12 --with pytest pytest -q`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "docs: README; ci: tests on linux/windows and plugin validation

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 14: The author's personal layer

**Files:**
- Create (new repo `/home/jonas/Documents/Code/loadout-personal`): `rules/me.md`, `settings.json`, `README.md`, `.gitignore`

**Interfaces:**
- Consumes: personal layer format (Task 10, spec §3.2)

- [ ] **Step 1: Create the repo and `rules/me.md`**

```bash
mkdir -p /home/jonas/Documents/Code/loadout-personal/rules && cd /home/jonas/Documents/Code/loadout-personal && git init -q -b main
```

`rules/me.md`:
```markdown
# About me (Jonas)

- CS student (bachelor thesis on RAG chunking); also builds TypeScript web apps, Rust tools, Android/Kotlin apps and a self-hosted home server (Docker).
- Desktop: Linux (Omarchy/Hyprland, Arch). Occasionally Windows for work.
- Ask before removing or replacing anything I set up; explain trade-offs and give a recommendation backed by research or evidence.
- Before responding to any request, check the available skills and invoke one if there is even a small chance it applies.
```

- [ ] **Step 2: Create `settings.json` from the current settings (preferences, permission, autoMode verbatim)**

Run:
```bash
python3 - <<'EOF'
import json, pathlib
src = json.loads(pathlib.Path.home().joinpath(".claude/settings.json").read_text())
out = {k: src[k] for k in ("alwaysThinkingEnabled", "effortLevel", "tui", "agentPushNotifEnabled", "autoMode") if k in src}
out["permissions"] = {"allow": ["Bash(hyprctl keyword:*)"]}
pathlib.Path("settings.json").write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
EOF
python3 -c "import json;d=json.load(open('settings.json'));print(sorted(d))"
```
Expected: `['agentPushNotifEnabled', 'alwaysThinkingEnabled', 'autoMode', 'effortLevel', 'permissions', 'tui']`

- [ ] **Step 3: README, .gitignore, commit**

`README.md`:
```markdown
# loadout-personal

Jonas's personal layer for [loadout](https://github.com/jonasyr/agent-loadout): `rules/me.md` (loaded every session) and a `settings.json` overlay. Linked in via `~/.config/loadout/personal`.
```

`.gitignore`:
```
*.local.*
```

```bash
git add -A
git commit -m "feat: personal layer for loadout

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 15: Publish both repos (requires the user)

**Files:** none

- [ ] **Step 1: Ask the user to log in to GitHub**

Ask the user to run `! gh auth login`, then `! gh auth setup-git`. Wait for confirmation. Remind them to rotate the GitHub PAT and the Devin API key (spec §13) if not done yet.

- [ ] **Step 2: Confirm visibility with the user**

The name is decided: repo `agent-loadout`, CLI/plugin `loadout`. Ask: "Publish agent-loadout as **public** (recommended: no personal data, easiest for your colleague, auto-updates without credentials) or private? loadout-personal will be private." Wait for the answer.

- [ ] **Step 3: Create and push**

```bash
cd /home/jonas/Documents/Code/agent-loadout && gh repo create jonasyr/agent-loadout --<public|private> --source . --push
cd /home/jonas/Documents/Code/loadout-personal && gh repo create jonasyr/loadout-personal --private --source . --push
```
Expected: both URLs printed. Then check that CI passes: `gh run watch --repo jonasyr/agent-loadout`. If the `validate` job fails because `claude plugin validate` needs auth in CI, replace those two steps with `python3 -c "import json; json.load(open('.claude-plugin/marketplace.json')); json.load(open('plugins/loadout/.claude-plugin/plugin.json'))"` and push the fix.

---

### Task 16: Cut over the author's machine

**Files:** none in the repos, except fixes found here (each committed separately)

- [ ] **Step 1: Baseline**

Run:
```bash
mkdir -p ~/agent-loadout-baseline && cp ~/.claude/settings.json ~/.claude/CLAUDE.md ~/.claude/RTK.md ~/agent-loadout-baseline/ && claude mcp list > ~/agent-loadout-baseline/mcp.txt 2>&1; claude plugin list > ~/agent-loadout-baseline/plugins.txt 2>&1
```
Ask the user to start a fresh `claude` session in `~/Documents/Code/bachelor-rag-chunking`, run `/context`, and paste the numbers (baseline).

- [ ] **Step 2: Verify the spec §15 open questions**

For each, record the answer in `docs/notes/2026-10-08-verification.md` in the kit repo:
1. **Rules subdirectories:** put a test rule `~/.claude/rules/kit-test/probe.md` containing "If asked for the probe word, answer PELICAN". Run `claude -p "What is the probe word?"`. If it answers PELICAN, subdirectories load. Delete the probe afterwards. If they don't load, change `link.LINKS()` to per-file links named `kit-<name>.md` / `personal-<name>.md`, update the tests, and commit.
2. **User-level `settings.local.json`:** check `https://code.claude.com/docs/en/settings` (via the claude-code-guide agent). If it is not honored, the hyprctl permission already lives in the personal overlay; adopt leaves the file alone.
3. **`autoMode` in project settings:** same docs check. If supported, offer the user to move the stormcut-specific lines into `stormcut/.claude/settings.json`.
4. **Tool prefix:** after cutover, in a session, confirm the Serena tools are named `mcp__plugin_loadout_serena__*`. If they differ, fix the matcher in `hooks.json`.
5. **security-guidance cost:** read `~/.claude/plugins/cache/claude-plugins-official/security-guidance/*/README.md` for the Stop-hook LLM review configuration. If it calls a model on every Stop, report the cost and how to switch it off, and ask the user.
6. **`codebase-memory-mcp update -y`:** run it inside `loadout update` (Step 4) and confirm the settings guard reverted any settings change.

- [ ] **Step 3: Link the personal layer and run bootstrap without adopt**

```bash
mkdir -p ~/.config/loadout && ln -sfn ~/Documents/Code/loadout-personal ~/.config/loadout/personal
cd ~/Documents/Code/agent-loadout && ./bootstrap.sh --no-adopt
```
Expected: links created, settings merged, marketplaces added, plugins installed, check output. Fix any FAIL lines before continuing.

- [ ] **Step 4: Adopt, with the user deciding**

Run `loadout adopt` (dry run) and show the full plan to the user. Ask which groups or items to apply. Per the spec, the user already decided:
- remove github-server, MCP_DOCKER, omarchy-kb;
- migrate serena and codebase-memory;
- scope-down sonarqube and ARS;
- remove auto-memory, testing-suite, documentation-generator and the taste skills;
- move CLAUDE.md into the personal layer.

Then apply non-interactively, e.g.:
```bash
loadout adopt --apply --groups remove,migrate,scope-down,review --skip <names the user wants kept>
```
Then `loadout update` for outdated binaries (codebase-memory 0.9.0 → 0.11.0) after the user confirms. Then `loadout check` must show no FAIL.

- [ ] **Step 5: Verify in a fresh session**

Ask the user to restart Claude Code in `bachelor-rag-chunking` and check:
- `/context` (compare with the baseline);
- `/mcp` (serena and codebase-memory connected via loadout; no failing kit servers);
- that the session-start hook produced no error.

Record the before/after numbers in `docs/notes/2026-10-08-verification.md`, commit and push.

- [ ] **Step 6: Apply profiles to the obvious repos (with user confirmation)**

Propose to the user:
- `cd ~/Documents/Code/bachelor-rag-chunking && loadout init thesis --dry-run`, then the real run;
- `loadout profile sonar` in gitray and sonarqube-issues-export-to-excel.

Run only the ones they approve.

---

### Task 17: Acceptance runs for project setup

**Files:** none (findings become fixes with their own commits)

- [ ] **Step 1: Empty repo**

```bash
d=$(mktemp -d)/demo-app && mkdir -p "$d" && cd "$d" && loadout init --yes --no-install
```
Expected:
- git initialized;
- AGENTS.md, CLAUDE.md, `docs/README.md`, `docs/adr/README.md` and `.gitignore` entries created;
- "next: /loadout:onboard" printed.

Ask the user to open Claude Code there and run `/loadout:onboard`. It must detect *new project* mode and start brainstorming.

- [ ] **Step 2: Existing repo dry run**

```bash
cd ~/Documents/Code/bachelor-rag-chunking && loadout init --dry-run
```
Expected:
- it suggests `thesis` (directory name contains "thesis"? No: the name is `bachelor-rag-chunking`, so detection relies on `.tex`/`.bib` files; if none exist it suggests nothing, which is correct);
- it would create nothing that already exists;
- it notes that AGENTS.md exists.

- [ ] **Step 3: Report**

Summarize for the user:
- the baseline vs after `/context` numbers;
- what adopt changed, with the backup path;
- the remaining manual items:
  - rotate the leaked credentials;
  - disconnect the claude.ai Context7 connector;
  - prune unused claude.ai connectors and Cowork plugins;
  - run `/loadout:docs-audit` on repos with old Serena memories, starting with bachelor-rag-chunking.
