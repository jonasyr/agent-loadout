# Repo agents PR 2: three-way profile merge, the record, `loadout explain` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-running a profile in a shared repo applies the profile's updates by itself, keeps every entry a person changed (offering the profile's value once), keeps removed list entries removed, and `loadout explain <file>` shows which entries are loadout's.

**Architecture:** A pure module `repo_merge.py` merges one profile fragment into one file's data against a base (the profile's record for that file). The record lives in the committed `.loadout.json` under `"profiles"`; `repo_config.py` reads, validates and rewrites it, in the file's own layout, through the same `RepoWrites` plan as every other repo write. `profiles.apply_profile` (Claude Code's `.claude/settings.json`, `.mcp.json`) and `codex_project.config` (`.codex/config.toml`, still add-only owned text) use the merge and the record. `explain.py` reads the record and the files.

**Tech Stack:** Python 3.11+ standard library only (`cli/loadout/`), pytest with the `fake_home`/`fake_runner` fixtures.

**Spec:** `docs/superpowers/specs/2026-10-16-repo-agents-and-careful-ux-design.md` (Part 2; Part 0's "Explain"; Part 5's Part 2 tests and the two-user simulation). PR 1 (#44, ADR 0030) is merged; its engine (`repo_writes.py`, `repo_config.py`) is the base. Docs baseline: `docs/superpowers/plans/2026-10-16-repo-agents-docs-baseline.md` (category B is this PR's).

## Global Constraints

- Python 3.11+, standard library only in `cli/loadout/`.
- Tests use `fake_home` and `fake_runner`; never the real `~/.claude`, `~/.claude.json`, `~/.codex` or `~/.config/loadout`; never real `claude`/`codex`/installers.
- Conventional Commits (`type(scope): subject`); no `Co-Authored-By` or other AI attribution.
- No plaintext secret in the backup manifest, the output, or `.loadout.json` (it is committed): a secret-looking value is recorded as `sha256:<hex>` and shown as `(a secret value, not shown)`.
- Every repo write goes through `RepoWrites` (planned, shown, backed up; `loadout restore` undoes it). `.loadout.json` is rewritten only in its exact layout (`json_style`/`dumps_like`); otherwise the record is not written and the plan says so.
- A run that changes nothing touches no file (mtime unchanged), `.loadout.json` included.
- "no run reverses an entry a person changed without a yes" (spec Part 2).
- `.codex/config.toml` keeps its owned-text rule: tables are only added; its entries are recorded so `explain` covers them.
- Tests: `uv run --python 3.12 --with pytest pytest -q`.

## Merge rules (the spec's Part 2, made exact)

Per entry (leaf) of the profile fragment, with `base` = the record, `theirs` = the file, `new` = the profile:

| Case | Result | Record |
|---|---|---|
| theirs == new | nothing | new, if base existed or another profile recorded it |
| no base, theirs missing | add (`added`) | new |
| no base, theirs differs | left as is, noted (add-only) | none |
| theirs == base | update (`updated`) | new |
| theirs != base, new == base | kept silently (`kept`): the profile has nothing new | base |
| theirs != base, new != base (theirs may be missing) | `differs`: asked once; take → new | new (it was offered: the next run keeps theirs without asking) |

Lists are sets: each entry the profile has is added unless the record has it and the file does not (`kept_removed`, never re-added, also not with take). Only entries loadout added, or that another profile recorded, are recorded. An entry the record has and the profile no longer has is removed when the file still has loadout's value and no other profile recorded it; otherwise it stays (`kept`). An MCP server definition (`mcpServers/<name>`) is one entry, compared whole (its `args` are an ordered command). Pointers are JSON-pointer style: `/` between keys, `~0` for `~`, `~1` for `/`.

Rulings already taken here (from the spec's silence): "asked about once" = a declined offer is recorded as offered, so the same profile value is not asked again; a scalar a person removed counts as a change (asked); a profile that drops an entry removes loadout's unchanged value; `--take-profile` exists on `loadout profile` only (`init` asks in a terminal, keeps the repo's values otherwise); Codex tables are never replaced or removed (owned text), and the plan notes when the profile has a newer table.

## Review Focus

1. Two profiles in one `init` plan writing the same list (`disabledMcpjsonServers`): the second builds on the first's planned text and record, both record the shared entry, and dropping it from one profile does not remove it. Test in Task 3.
2. A secret-looking value in a profile (an MCP server `env` token): never in plain text in `.loadout.json`, the plan output or `explain`. Tests in Tasks 1, 3, 6.
3. Restore after a run that changed a repo file and `.loadout.json` twice (the plan, then the held Codex record write after the plugin installs): every file back byte for byte. Test in Task 4.
4. A no-op re-run (file and record current): no file touched, `.loadout.json` included, and the plan shows `(no file changes)`. Test in Task 3.
5. A hand-edited `.loadout.json`: `profiles` of the wrong shape stops with the reason before any change; a layout loadout cannot reproduce leaves `.loadout.json` byte for byte, writes the other files, and says the record was not written. Tests in Tasks 2 and 3.

---

### Task 1: `repo_merge.py`, the pure three-way merge

**Files:**
- Create: `cli/loadout/repo_merge.py`
- Test: `tests/test_repo_merge.py`

**Interfaces:**
- Produces: `MISSING`, `SHAPE`, `HASH = "sha256:"`; `pointer(path: tuple) -> str`; `unpointer(text: str) -> tuple`; `leaves(overlay: dict)` yields `(path, value)`; `get(data, path) -> value | MISSING | SHAPE`; `stored(value, key="")`; `matches(record_value, value, key="") -> bool`; `held(others: tuple, ptr: str, s) -> bool`; `show(value, key="") -> str`; `@dataclass Differs(pointer, theirs, new)`; `@dataclass Merge(after, record, added, updated, removed, differs, kept, kept_removed, left, blocked)`; `merge(current: dict, overlay: dict, base: dict, take=False, others: tuple = ()) -> Merge`.

- [ ] **Step 1: Write the failing tests**

```python
"""The three-way merge of a profile fragment into one repo JSON file (spec Part 2)."""
from loadout import repo_merge as rm

TOKEN = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"


def test_pointer_round_trips_slashes_and_tildes():
    assert rm.pointer(("mcpServers", "a/b~c")) == "mcpServers/a~1b~0c"
    assert rm.unpointer("mcpServers/a~1b~0c") == ("mcpServers", "a/b~c")


def test_an_mcp_server_is_one_entry():
    got = dict(rm.leaves({"mcpServers": {"x": {"command": "npx", "args": ["-y", "a@1"]}}, "env": {"A": "1"}}))
    assert got == {("mcpServers", "x"): {"command": "npx", "args": ["-y", "a@1"]}, ("env", "A"): "1"}


def test_a_missing_entry_without_a_record_is_added_and_recorded():
    m = rm.merge({}, {"a": {"b": 1}}, {})
    assert m.after == {"a": {"b": 1}} and m.added == ["a/b"] and m.record == {"a/b": 1}


def test_the_input_is_not_changed():
    current = {"a": {"b": 1}}
    rm.merge(current, {"a": {"c": 2}}, {})
    assert current == {"a": {"b": 1}}


def test_a_profile_update_applies_when_the_file_has_the_recorded_value():
    m = rm.merge({"a": 1}, {"a": 2}, {"a": 1})
    assert m.after == {"a": 2} and m.updated == ["a"] and m.record == {"a": 2}


def test_a_teammate_change_is_kept_and_offered_once():
    m = rm.merge({"a": 5}, {"a": 2}, {"a": 1})
    assert m.after == {"a": 5} and [d.pointer for d in m.differs] == ["a"]
    assert m.record == {"a": 2}
    again = rm.merge({"a": 5}, {"a": 2}, m.record)
    assert again.after == {"a": 5} and again.differs == [] and again.kept


def test_take_uses_the_profile_value():
    m = rm.merge({"a": 5}, {"a": 2}, {"a": 1}, take=True)
    assert m.after == {"a": 2} and m.record == {"a": 2} and m.updated == ["a"]


def test_a_value_a_person_removed_is_offered_not_added_back():
    m = rm.merge({}, {"a": 2}, {"a": 1})
    assert m.after == {} and m.differs[0].theirs is rm.MISSING


def test_an_unchanged_profile_keeps_a_changed_file_silently():
    m = rm.merge({"a": 5}, {"a": 1}, {"a": 1})
    assert m.after == {"a": 5} and m.differs == [] and m.kept and m.record == {"a": 1}


def test_without_a_record_another_value_stays_and_is_not_recorded():
    m = rm.merge({"a": 5}, {"a": 2}, {})
    assert m.after == {"a": 5} and m.left and m.record == {} and m.differs == []


def test_a_value_the_repo_already_had_is_not_recorded():
    m = rm.merge({"a": 2}, {"a": 2}, {})
    assert m.record == {} and m.after == {"a": 2}


def test_list_entries_are_added_and_only_those_are_recorded():
    m = rm.merge({"l": ["mine"]}, {"l": ["mine", "x"]}, {})
    assert m.after == {"l": ["mine", "x"]} and m.record == {"l": ["x"]}


def test_a_list_entry_a_person_removed_stays_removed_even_with_take():
    m = rm.merge({"l": []}, {"l": ["x"]}, {"l": ["x"]}, take=True)
    assert m.after == {"l": []} and m.kept_removed and m.record == {"l": ["x"]}


def test_an_entry_the_profile_dropped_is_removed_when_unchanged():
    m = rm.merge({"a": 1, "b": 2, "l": ["x", "mine"]}, {"b": 2}, {"a": 1, "l": ["x"]})
    assert m.after == {"b": 2, "l": ["mine"]} and sorted(m.removed) == ["a", 'l: "x"']


def test_a_dropped_entry_a_person_changed_stays():
    m = rm.merge({"a": 9}, {}, {"a": 1})
    assert m.after == {"a": 9} and m.removed == [] and m.record == {}


def test_a_dropped_entry_another_profile_recorded_stays():
    m = rm.merge({"a": 1, "l": ["x"]}, {}, {"a": 1, "l": ["x"]}, others=({"a": 1, "l": ["x"]},))
    assert m.after == {"a": 1, "l": ["x"]} and m.removed == []


def test_an_entry_another_profile_recorded_is_recorded_too():
    m = rm.merge({"l": ["x"]}, {"l": ["x"]}, {}, others=({"l": ["x"]},))
    assert m.record == {"l": ["x"]}


def test_a_parent_of_the_wrong_shape_blocks_the_entry():
    m = rm.merge({"a": [1]}, {"a": {"b": 1}}, {})
    assert m.after == {"a": [1]} and m.blocked and m.blocked[0].startswith("a/b: not written")


def test_a_list_where_the_file_has_a_scalar_is_blocked():
    m = rm.merge({"l": "x"}, {"l": ["y"]}, {})
    assert m.after == {"l": "x"} and m.blocked


def test_true_and_one_are_different_values():
    m = rm.merge({"a": 1}, {"a": True}, {"a": 1})
    assert m.after == {"a": True}


def test_a_secret_looking_value_is_recorded_as_a_hash():
    m = rm.merge({}, {"mcpServers": {"gh": {"env": {"GITHUB_TOKEN": TOKEN}}}}, {})
    s = m.record["mcpServers/gh"]
    assert isinstance(s, str) and s.startswith(rm.HASH) and TOKEN not in s
    assert rm.matches(s, {"env": {"GITHUB_TOKEN": TOKEN}})
    assert TOKEN not in rm.show({"env": {"GITHUB_TOKEN": TOKEN}})
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_repo_merge.py`
Expected: FAIL (collection error: `cannot import name 'repo_merge'`).

- [ ] **Step 3: Write the module**

```python
"""Three-way merge of a profile's entries into a repo JSON file (spec Part 2, ADR 0031).

base: this profile's record in .loadout.json (what it wrote, or offered, last time); theirs: the file now; new: the
profile now. A profile update applies when the file still has the recorded value; an entry a person changed stays and
is offered once (`take` uses the profile's value); a list entry a person removed stays removed; without a record only
missing entries are added. An MCP server's definition is one entry (its args are an ordered command, not a set)."""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from . import secrets

MISSING = object()
SHAPE = object()  # a part of the path is not an object in the file
HASH = "sha256:"


def pointer(path: tuple) -> str:
    return "/".join(str(k).replace("~", "~0").replace("/", "~1") for k in path)


def unpointer(text: str) -> tuple:
    return tuple(p.replace("~1", "/").replace("~0", "~") for p in text.split("/"))


def leaves(overlay: dict, prefix: tuple = ()):
    for key, value in overlay.items():
        path = prefix + (key,)
        if isinstance(value, dict) and value and not (prefix and prefix[-1] == "mcpServers"):
            yield from leaves(value, path)
        else:
            yield path, value


def _canon(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)  # default: TOML dates


def _has(items: list, s) -> bool:
    return any(_canon(s) == _canon(x) for x in items)


def secretish(value, key: str = "") -> bool:
    if isinstance(value, dict):
        return any(secretish(v, str(k)) for k, v in value.items())
    if isinstance(value, list):
        return any(secretish(v, key) for v in value)
    return isinstance(value, str) and (secrets.redact(value) != value or secrets.looks_secret(key, value))


def stored(value, key: str = ""):
    """The value as the committed record keeps it: as is, or a hash when it looks like a secret."""
    if secretish(value, key) or (isinstance(value, str) and value.startswith(HASH)):
        return HASH + hashlib.sha256(_canon(value).encode("utf-8")).hexdigest()
    return copy.deepcopy(value)


def matches(record_value, value, key: str = "") -> bool:
    return value is not MISSING and value is not SHAPE and _canon(stored(value, key)) == _canon(record_value)


def held(others: tuple, ptr: str, s) -> bool:
    """Another profile's record for this file has the stored value s at ptr (or in its list)."""
    for rec in others:
        v = rec.get(ptr, MISSING)
        if isinstance(v, list) and _has(v, s) or (v is not MISSING and not isinstance(v, list) and _canon(v) == _canon(s)):
            return True
    return False


def show(value, key: str = "") -> str:
    if value is MISSING or value is SHAPE:
        return "nothing (removed)"
    if secretish(value, key) or (isinstance(value, str) and value.startswith(HASH)):
        return "(a secret value, not shown)"
    return json.dumps(value, ensure_ascii=False)


def get(data, path: tuple):
    node = data
    for key in path:
        if not isinstance(node, dict):
            return SHAPE
        if key not in node:
            return MISSING
        node = node[key]
    return node


def _set(data: dict, path: tuple, value) -> None:
    for key in path[:-1]:
        data = data.setdefault(key, {})
    data[path[-1]] = copy.deepcopy(value)


def _delete(data: dict, path: tuple) -> None:
    chain, node = [], data
    for key in path[:-1]:
        chain.append((node, key))
        node = node[key]
    node.pop(path[-1], None)
    for parent, key in reversed(chain):  # an object loadout emptied goes too
        if parent[key] != {}:
            break
        del parent[key]


@dataclass
class Differs:
    pointer: str
    theirs: Any  # MISSING when a person removed it
    new: Any


@dataclass
class Merge:
    after: dict
    record: dict = field(default_factory=dict)
    added: list = field(default_factory=list)
    updated: list = field(default_factory=list)
    removed: list = field(default_factory=list)
    differs: list = field(default_factory=list)
    kept: list = field(default_factory=list)
    kept_removed: list = field(default_factory=list)
    left: list = field(default_factory=list)
    blocked: list = field(default_factory=list)


def merge(current: dict, overlay: dict, base: dict, take: bool = False, others: tuple = ()) -> Merge:
    """current: the file now (not changed); overlay: the profile's fragment; base: this profile's record for the file
    ({} without one); take: use the profile's value where a person changed an entry; others: the other profiles'
    records for the file."""
    m = Merge(copy.deepcopy(current))
    seen = set()
    for path, new in leaves(overlay):
        ptr = pointer(path)
        seen.add(ptr)
        theirs = get(m.after, path)
        if theirs is SHAPE:
            m.blocked.append(f"{ptr}: not written, a part of its path is not an object in the file")
            if ptr in base:
                m.record[ptr] = base[ptr]
            continue
        if isinstance(new, list):
            _list(m, path, ptr, new, theirs, base.get(ptr, MISSING), others)
        else:
            _value(m, path, ptr, new, theirs, base.get(ptr, MISSING), take, others)
    for ptr, old in base.items():
        if ptr not in seen:
            _drop(m, unpointer(ptr), ptr, old, others)
    return m


def _value(m: Merge, path, ptr, new, theirs, old, take, others) -> None:
    key = str(path[-1])
    if theirs is not MISSING and _canon(theirs) == _canon(new):
        if old is not MISSING or held(others, ptr, stored(new, key)):
            m.record[ptr] = stored(new, key)
        return
    if old is MISSING:
        if theirs is MISSING:
            _set(m.after, path, new)
            m.added.append(ptr)
            m.record[ptr] = stored(new, key)
        else:
            m.left.append(f"{ptr}: left as is, the repo has {show(theirs, key)} (the profile: {show(new, key)})")
        return
    if matches(old, theirs, key):
        _set(m.after, path, new)
        m.updated.append(ptr)
        m.record[ptr] = stored(new, key)
    elif matches(old, new, key):
        m.kept.append(f"{ptr}: the repo's {show(theirs, key)} stays (changed in this repo)")
        m.record[ptr] = old
    else:
        m.differs.append(Differs(ptr, theirs, new))
        if take:
            _set(m.after, path, new)
            m.updated.append(ptr)
        m.record[ptr] = stored(new, key)


def _list(m: Merge, path, ptr, new, theirs, old, others) -> None:
    key = str(path[-1])
    if theirs is not MISSING and not isinstance(theirs, list):
        m.blocked.append(f"{ptr}: not written, the file has {show(theirs, key)} there, not a list")
        if old is not MISSING:
            m.record[ptr] = old
        return
    have = list(theirs) if theirs is not MISSING else []
    ours = old if isinstance(old, list) else []
    wanted = [stored(e, key) for e in new]
    rec, add = [], []
    for entry, s in zip(new, wanted):
        if any(_canon(entry) == _canon(x) for x in have):
            if _has(ours, s) or held(others, ptr, s):
                rec.append(s)
        elif _has(ours, s):
            m.kept_removed.append(f"{ptr}: {show(entry, key)}")
            rec.append(s)
        else:
            add.append(entry)
            rec.append(s)
            m.added.append(f"{ptr}: {show(entry, key)}")
    keep = []
    for x in have:
        s = stored(x, key)
        if _has(ours, s) and not _has(wanted, s) and not held(others, ptr, s):
            m.removed.append(f"{ptr}: {show(x, key)}")
        else:
            keep.append(x)
    if add or len(keep) != len(have):
        _set(m.after, path, keep + add)
    if rec:
        m.record[ptr] = rec


def _drop(m: Merge, path, ptr, old, others) -> None:
    """An entry the record has and the profile no longer has."""
    key = str(path[-1])
    theirs = get(m.after, path)
    if isinstance(old, list):
        if isinstance(theirs, list):
            _list(m, path, ptr, [], theirs, old, others)
        return
    if theirs is MISSING or theirs is SHAPE:
        return
    if matches(old, theirs, key) and not held(others, ptr, old):
        _delete(m.after, path)
        m.removed.append(ptr)
    else:
        m.kept.append(f"{ptr}: no longer in the profile; the repo's value stays")
```

- [ ] **Step 4: Run them to see them pass**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_repo_merge.py`
Expected: PASS (23 passed). If `test_a_secret_looking_value_is_recorded_as_a_hash` fails because `secrets.looks_secret` takes other arguments, read its signature in `cli/loadout/secrets.py:72` and adapt the call in `secretish` (ledger the ruling).

- [ ] **Step 5: Commit**

```bash
git add cli/loadout/repo_merge.py tests/test_repo_merge.py
git commit -m "feat(repo): three-way merge of a profile's entries against its record"
```

---

### Task 2: the record in `.loadout.json`

**Files:**
- Modify: `cli/loadout/repo_config.py`
- Test: `tests/test_repo_record.py`

**Interfaces:**
- Consumes: `RepoWrites.planned(path)`, `.create`, `.modify` (PR 1).
- Produces: `repo_config.current_text(project, w=None) -> str | None`; `repo_config.records(project, w=None) -> dict` (`{profile: {file: {pointer: value}}}`, raises `Invalid`); `repo_config.record_text(project, text, profile, files) -> str | None` (raises `Invalid`); `repo_config.plan_record(project, w, profile, files, notes) -> None`; `RECORD_WHY` text. `load()` now refuses a wrong-shaped `profiles`.

- [ ] **Step 1: Write the failing tests**

```python
"""The record of what each profile wrote, in .loadout.json (spec Part 2)."""
import json

import pytest

from loadout import repo_config, targets
from loadout.repo_writes import RepoWrites


@pytest.fixture
def repo(fake_home, tmp_path):
    p = tmp_path / "repo"
    (p / ".git").mkdir(parents=True)
    targets.set_agents({"claude": True, "codex": False})
    return p


def test_a_wrong_shaped_record_stops_with_the_reason(repo):
    (repo / ".loadout.json").write_text('{\n  "profiles": []\n}\n')
    with pytest.raises(repo_config.Invalid, match="profiles must map"):
        repo_config.load(repo)


def test_without_the_file_the_record_comes_with_the_repos_agents(repo):
    text = repo_config.record_text(repo, None, "web", {".mcp.json": {"mcpServers/cd": {"command": "x"}}})
    assert json.loads(text) == {"agents": ["claude"], "profiles": {"web": {".mcp.json": {"mcpServers/cd": {"command": "x"}}}}}


def test_other_keys_indent_and_crlf_are_kept(repo):
    old = json.dumps({"agents": ["codex"], "note": "mine"}, indent=4).replace("\n", "\r\n") + "\r\n"
    text = repo_config.record_text(repo, old, "web", {".mcp.json": {"a": 1}})
    assert text.startswith('{\r\n    "agents"') and '"note": "mine"' in text and text.endswith("}\r\n")
    assert list(json.loads(text)) == ["agents", "note", "profiles"]


def test_an_empty_record_drops_the_file_the_profile_and_the_key(repo):
    old = json.dumps({"agents": ["claude"], "profiles": {"web": {".mcp.json": {"a": 1}}}}, indent=2) + "\n"
    assert json.loads(repo_config.record_text(repo, old, "web", {".mcp.json": {}})) == {"agents": ["claude"]}


def test_an_unchanged_record_is_no_change(repo):
    old = json.dumps({"agents": ["claude"], "profiles": {"web": {".mcp.json": {"a": 1}}}}, indent=2) + "\n"
    assert repo_config.record_text(repo, old, "web", {".mcp.json": {"a": 1}}) is None
    assert repo_config.record_text(repo, None, "web", {".mcp.json": {}}) is None


def test_a_layout_loadout_cannot_keep_is_refused(repo):
    with pytest.raises(repo_config.Invalid, match="record of profile web is not written"):
        repo_config.record_text(repo, '{"agents": ["claude"]}', "web", {".mcp.json": {"a": 1}})


def test_records_read_the_planned_text_first(repo):
    (repo / ".loadout.json").write_text(json.dumps({"agents": ["claude"]}, indent=2) + "\n")
    w = RepoWrites(repo)
    repo_config.plan_record(repo, w, "web", {".mcp.json": {"a": 1}}, [])
    assert repo_config.records(repo, w) == {"web": {".mcp.json": {"a": 1}}}
    assert repo_config.records(repo) == {}


def test_plan_record_notes_a_layout_it_cannot_keep(repo):
    (repo / ".loadout.json").write_text('{"agents": ["claude"]}')
    notes = []
    w = RepoWrites(repo)
    repo_config.plan_record(repo, w, "web", {".mcp.json": {"a": 1}}, notes)
    assert w.changes == [] and "not written" in notes[0]
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_repo_record.py`
Expected: FAIL (`AttributeError: module 'loadout.repo_config' has no attribute 'record_text'`, and the first test does not raise).

- [ ] **Step 3: Implement**

In `cli/loadout/repo_config.py`: change the import to `from .jsonio import JsonStyle, dumps_like, json_style`; in `load()`, call `_check_profiles(data)` right after the `manage` check; append:

```python
RECORD_WHY = "loadout: what profile {name} wrote here, so later runs can update it (commit it)"


def _check_profiles(data: dict) -> None:
    rec = data.get("profiles")
    if rec is None:
        return
    if not (isinstance(rec, dict) and all(
            isinstance(files, dict) and all(isinstance(entries, dict) for entries in files.values())
            for files in rec.values())):
        raise Invalid(f"{FILE}: profiles must map each profile to its files and their entries (loadout writes it; "
                      "take it back from git, or remove the profiles key to start a new record)")


def current_text(project: Path, w=None) -> str | None:
    """.loadout.json's text as the plan has it: planned in `w`, else on disk (CRLF kept), else None."""
    planned = w.planned(_path(project)) if w is not None and hasattr(w, "planned") else None
    if planned is not None:
        return planned
    if not _path(project).is_file():
        return None
    with open(_path(project), encoding="utf-8", newline="") as fh:
        return fh.read()


def records(project: Path, w=None) -> dict:
    """Every profile's record: {profile: {file: {pointer: value}}}."""
    text = current_text(project, w)
    if text is None:
        return {}
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise Invalid(f"{FILE}: does not parse ({exc}); fix it, then run this again") from None
    if not isinstance(data, dict):
        raise Invalid(f"{FILE}: must be a JSON object")
    _check_profiles(data)
    return data.get("profiles") or {}


def record_text(project: Path, text: str | None, profile: str, files: dict) -> str | None:
    """.loadout.json's text with `profile`'s record set for `files` ({file: entries}; empty entries drop the file),
    or None when nothing changes. Without the file: a new one naming the repo's agents."""
    if text is None:
        on = agents(project)
        data, style = {"agents": [a for a in AGENTS if on[a]] or list(AGENTS)}, JsonStyle(2, "\n", True)
    else:
        style = json_style(text)
        if style is None:
            raise Invalid(f"{FILE}: its layout is not one loadout rewrites, so the record of profile {profile} is not "
                          "written (later runs add only missing entries)")
        data = json.loads(text)
    rec = dict(data.get("profiles") or {})
    mine = dict(rec.get(profile) or {})
    for rel, entries in files.items():
        if entries:
            mine[rel] = entries
        else:
            mine.pop(rel, None)
    if mine:
        rec[profile] = mine
    else:
        rec.pop(profile, None)
    new = {**data, "profiles": rec} if rec else {k: v for k, v in data.items() if k != "profiles"}
    if (text is None and not rec) or (text is not None and new == data):
        return None
    return dumps_like(style, new)


def plan_record(project: Path, w, profile: str, files: dict, notes: list) -> None:
    """Put `profile`'s record for `files` into .loadout.json through the writer `w` (a plan or now)."""
    try:
        text = record_text(project, current_text(project, w), profile, files)
    except Invalid as exc:
        notes.append(str(exc))
        return
    if text is not None:
        (w.modify if _path(project).exists() else w.create)(_path(project), text, RECORD_WHY.format(name=profile))
```

- [ ] **Step 4: Run them to see them pass**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_repo_record.py tests/test_repo_config.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cli/loadout/repo_config.py tests/test_repo_record.py
git commit -m "feat(repo): .loadout.json records what each profile wrote"
```

---

### Task 3: `apply_profile` merges three-way and records

**Files:**
- Modify: `cli/loadout/profiles.py` (`apply_profile`, new `_merge_notes`)
- Modify: `cli/loadout/project.py` (`_plan_profile` passes `decide` and the notes list)
- Test: `tests/test_profile_three_way.py`
- Modify (deliberately, each with a ledger ruling): existing tests that encoded "the profile wins" (find them in Step 6)

**Interfaces:**
- Consumes: Task 1 `repo_merge.merge`, `show`, `unpointer`; Task 2 `repo_config.records`, `plan_record`.
- Produces: `profiles.apply_profile(profile, project, w=None, decide=None, notes=None) -> (changed, skipped)`; `decide(lines: list[str]) -> bool`, called at most once per profile, `lines[0]` is `This repo differs from profile NAME in N entr(y|ies):`; `project._plan_profile(prof, project, w, install, decide=None)`. Note texts: `"{file}: update {ptr} to profile {name}'s value"`, `"{file}: remove {ptr} (no longer in profile {name})"`, `"{file}: {entry} was removed in this repo; kept removed"`, `"{file}: {ptr}: kept the repo's {theirs} (profile {name} has {new}; loadout profile {name} --take-profile uses it)"`.

- [ ] **Step 1: Write the failing tests**

```python
"""loadout profile in a shared repo: updates, a teammate's changes, the record (spec Part 2)."""
import json
import os
from pathlib import Path

import pytest

from loadout import backup, jsonio, profiles, project, targets

TOKEN = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
YES = staticmethod(lambda plan: True)


@pytest.fixture
def repo(fake_home, fake_runner, tmp_path):
    p = tmp_path / "repo"
    (p / ".git").mkdir(parents=True)
    targets.set_agents({"claude": True, "codex": False})
    return p


def use(monkeypatch, settings=None, mcp=None, by_name=None):
    def load(n):
        s = (by_name or {}).get(n, settings)
        return profiles.Profile(name=n, description="d", settings=s or {}, mcp=mcp or {})
    monkeypatch.setattr(profiles, "load_profile", load)


def run(repo, name="web", **kw):
    return project.add_profile(repo, name, install=False, approve=lambda plan: True, **kw)


def settings(repo):
    return json.loads((repo / ".claude" / "settings.json").read_text())


def record(repo, name="web"):
    return json.loads((repo / ".loadout.json").read_text()).get("profiles", {}).get(name, {})


def edit(repo, change):
    path = repo / ".claude" / "settings.json"
    data = json.loads(path.read_text())
    change(data)
    path.write_text(json.dumps(data, indent=2) + "\n")


def test_the_first_run_records_what_it_added(repo, monkeypatch):
    use(monkeypatch, {"env": {"A": "1"}, "permissions": {"allow": ["Bash(npm test)"]}})
    assert run(repo) == 0
    assert record(repo) == {".claude/settings.json": {"env/A": "1", "permissions/allow": ["Bash(npm test)"]}}


def test_a_profile_update_applies_by_itself(repo, monkeypatch, capsys):
    use(monkeypatch, {"env": {"A": "1"}})
    run(repo)
    use(monkeypatch, {"env": {"A": "2"}})
    run(repo)
    assert settings(repo)["env"]["A"] == "2" and "update env/A" in capsys.readouterr().out


def test_a_teammate_change_is_kept_without_a_yes(repo, monkeypatch, capsys):
    use(monkeypatch, {"env": {"A": "1"}})
    run(repo)
    edit(repo, lambda d: d["env"].update(A="9"))
    use(monkeypatch, {"env": {"A": "2"}})
    run(repo)
    assert settings(repo)["env"]["A"] == "9" and "--take-profile" in capsys.readouterr().out


def test_decide_yes_takes_the_profile_values(repo, monkeypatch):
    use(monkeypatch, {"env": {"A": "1"}})
    run(repo)
    edit(repo, lambda d: d["env"].update(A="9"))
    use(monkeypatch, {"env": {"A": "2"}})
    asked = []
    run(repo, decide=lambda lines: asked.append(lines) or True)
    assert settings(repo)["env"]["A"] == "2"
    assert asked[0][0] == "This repo differs from profile web in 1 entry:" and '"9"' in asked[0][1]


def test_a_declined_offer_is_not_asked_again(repo, monkeypatch):
    use(monkeypatch, {"env": {"A": "1"}})
    run(repo)
    edit(repo, lambda d: d["env"].update(A="9"))
    use(monkeypatch, {"env": {"A": "2"}})
    asked = []
    run(repo, decide=lambda lines: asked.append(1) and False)
    run(repo, decide=lambda lines: asked.append(1) and False)
    assert asked == [1] and settings(repo)["env"]["A"] == "9"


def test_a_removed_list_entry_stays_removed(repo, monkeypatch, capsys):
    use(monkeypatch, {"permissions": {"allow": ["Bash(npm test)", "Bash(ls)"]}})
    run(repo)
    edit(repo, lambda d: d["permissions"]["allow"].remove("Bash(npm test)"))
    run(repo, decide=lambda lines: True)
    assert settings(repo)["permissions"]["allow"] == ["Bash(ls)"] and "kept removed" in capsys.readouterr().out


def test_without_a_record_only_missing_entries_are_added(repo, monkeypatch, capsys):
    (repo / ".claude").mkdir()
    (repo / ".claude" / "settings.json").write_text(json.dumps({"env": {"A": "5"}}, indent=2) + "\n")
    use(monkeypatch, {"env": {"A": "2", "B": "1"}})
    run(repo)
    assert settings(repo)["env"] == {"A": "5", "B": "1"}
    assert record(repo) == {".claude/settings.json": {"env/B": "1"}}
    assert "left as is" in capsys.readouterr().out


def test_an_entry_the_profile_dropped_is_removed(repo, monkeypatch):
    use(monkeypatch, {"env": {"A": "1"}, "x": 1})
    run(repo)
    use(monkeypatch, {"x": 1})
    run(repo)
    assert settings(repo) == {"x": 1} and record(repo) == {".claude/settings.json": {"x": 1}}


def test_a_dropped_settings_section_is_cleaned_up(repo, monkeypatch):
    use(monkeypatch, {"env": {"A": "1"}})
    run(repo)
    use(monkeypatch, {})
    run(repo)
    assert settings(repo) == {} and record(repo) == {}


def test_indent_four_and_crlf_are_kept(repo, monkeypatch):
    path = repo / ".claude" / "settings.json"
    path.parent.mkdir()
    path.write_bytes((json.dumps({"mine": 1}, indent=4).replace("\n", "\r\n") + "\r\n").encode())
    use(monkeypatch, {"env": {"A": "1"}})
    run(repo)
    use(monkeypatch, {"env": {"A": "2"}})
    run(repo)
    assert jsonio.json_style(path.read_bytes().decode()) == jsonio.JsonStyle(4, "\r\n", True)


def test_a_no_op_rerun_touches_nothing(repo, monkeypatch, capsys):
    use(monkeypatch, {"env": {"A": "1"}, "permissions": {"allow": ["x"]}})
    run(repo)
    files = [repo / ".claude" / "settings.json", repo / ".loadout.json"]
    for f in files:
        os.utime(f, (1_000_000, 1_000_000))
    capsys.readouterr()
    assert run(repo) == 0
    assert [f.stat().st_mtime for f in files] == [1_000_000, 1_000_000]
    assert "(no file changes)" in capsys.readouterr().out


def test_two_profiles_in_one_plan_share_a_list_entry(repo, monkeypatch):
    use(monkeypatch, by_name={"a": {"disabledMcpjsonServers": ["x"]}, "b": {"disabledMcpjsonServers": ["x", "y"]}})
    project.init(repo, ["a", "b"], yes=True, install=False, dry_run=False, ask=lambda q: "", interactive=False)
    assert settings(repo)["disabledMcpjsonServers"] == ["x", "y"]
    assert record(repo, "a") == {".claude/settings.json": {"disabledMcpjsonServers": ["x"]}}
    assert record(repo, "b") == {".claude/settings.json": {"disabledMcpjsonServers": ["x", "y"]}}
    use(monkeypatch, by_name={"a": {"other": 1}, "b": {"disabledMcpjsonServers": ["x", "y"]}})
    run(repo, "a")
    assert settings(repo)["disabledMcpjsonServers"] == ["x", "y"]


def test_a_secret_is_never_in_the_record_or_the_output(repo, monkeypatch, capsys):
    use(monkeypatch, mcp={"mcpServers": {"gh": {"command": "gh-mcp", "env": {"GITHUB_TOKEN": TOKEN}}}})
    run(repo)
    assert TOKEN not in (repo / ".loadout.json").read_text()
    assert TOKEN not in capsys.readouterr().out


def test_a_wrong_shaped_record_stops_before_any_change(repo, monkeypatch, capsys):
    (repo / ".loadout.json").write_text('{\n  "agents": [\n    "claude"\n  ],\n  "profiles": []\n}\n')
    use(monkeypatch, {"env": {"A": "1"}})
    assert run(repo) == 1
    assert not (repo / ".claude").exists() and "profiles must map" in capsys.readouterr().out


def test_a_record_it_cannot_write_leaves_loadout_json_and_writes_the_rest(repo, monkeypatch, capsys):
    (repo / ".loadout.json").write_text('{"agents": ["claude"]}')
    use(monkeypatch, {"env": {"A": "1"}})
    run(repo)
    assert (repo / ".loadout.json").read_text() == '{"agents": ["claude"]}'
    assert settings(repo)["env"]["A"] == "1" and "record of profile web is not written" in capsys.readouterr().out


def test_restore_undoes_an_update_and_its_record(repo, monkeypatch, capsys):
    use(monkeypatch, {"env": {"A": "1"}})
    run(repo)
    before = {p: p.read_bytes() for p in (repo / ".claude" / "settings.json", repo / ".loadout.json")}
    use(monkeypatch, {"env": {"A": "2"}})
    capsys.readouterr()
    run(repo)
    line = next(l for l in capsys.readouterr().out.splitlines() if "undo: loadout restore " in l)
    _, ok, _ = backup.restore(Path(line.split("undo: loadout restore ", 1)[1].strip()))
    assert ok and {p: p.read_bytes() for p in before} == before
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_profile_three_way.py`
Expected: FAIL (the record tests find no `profiles` key; `decide` is an unexpected keyword of `add_profile`, which Task 5 adds; until then those tests fail with a TypeError).

Note: `add_profile(..., decide=...)` is threaded in Task 5. In this task add only the parameter plumbing: `add_profile(..., decide=None)` passes `decide` to `_plan_profile`, and `_plan_profile(..., decide=None)` passes `decide=decide, notes=notes` to `apply_profile`. The CLI flag and the question come in Task 5.

- [ ] **Step 3: Implement `apply_profile`**

Replace `apply_profile` in `cli/loadout/profiles.py` with:

```python
def apply_profile(profile: Profile, project: Path, w=None, decide=None, notes: list | None = None) -> tuple[list[Path], list[str]]:
    """Merge the profile into the repo's settings and .mcp.json three-way against its record in .loadout.json
    (ADR 0031), when the repo is for Claude Code. A file is changed only in the layout it already has; any other
    file is left and its entries named. decide(lines) -> bool: whether to use the profile's values where a person
    changed an entry (None: keep theirs). notes collects the plan's lines about updated, kept and removed entries.
    With a collector `w` the changes are only planned. Returns (changed, skipped)."""
    import json as _json
    from . import repo_config, repo_merge
    from .jsonio import dumps_like, json_style
    from .repo_writes import RepoWrites, _flat
    changed, skipped = [], []
    notes = notes if notes is not None else []
    if not repo_config.agents(project)["claude"]:
        return changed, skipped  # repo_off_notes says what was not written
    writes = w if w is not None else RepoWrites(project, now=True)
    every = repo_config.records(project, writes)
    mine = every.get(profile.name, {})
    files = []
    for attr, rel in CLAUDE_FILES:
        overlay, key = getattr(profile, attr), rel.as_posix()
        if not overlay and not mine.get(key):
            continue
        target = project / rel
        if not paths.inside(target, project) or not paths.inside(target.parent, project):
            skipped.append(f"skipped {key}: it points outside the repo")
            continue
        planned = writes.planned(target)
        if planned is not None:  # an earlier profile in this plan already writes it: build on that
            before, old = _json.loads(planned), planned
        else:
            before = load_json(target)  # a file that does not parse raises InvalidJSON, as before
            old = target.read_bytes().decode("utf-8") if target.exists() else None
        if old is not None and not old.strip():
            old = None  # an empty file holds nothing of the user's: written like a new one
        others = tuple(r.get(key, {}) for n, r in every.items() if n != profile.name)
        files.append([attr, rel, target, before, old, overlay, others,
                      repo_merge.merge(before, overlay, mine.get(key, {}), others=others)])
    differs = [(f[1].as_posix(), d) for f in files for d in f[7].differs]
    if differs and decide is not None:
        lines = [f"This repo differs from profile {profile.name} in {len(differs)} "
                 f"entr{'y' if len(differs) == 1 else 'ies'}:"]
        for rel, d in differs:
            k = repo_merge.unpointer(d.pointer)[-1]
            lines.append(redact(f"  {rel}  {d.pointer}: the repo has {repo_merge.show(d.theirs, k)}, "
                                f"the profile has {repo_merge.show(d.new, k)}"))
        if decide(lines):
            for f in files:
                f[7] = repo_merge.merge(f[3], f[5], mine.get(f[1].as_posix(), {}), take=True, others=f[6])
    record = {}
    for attr, rel, target, before, old, overlay, others, m in files:
        key = rel.as_posix()
        skipped += [redact(f"{key}: {line}") for line in m.blocked]
        if m.after != before or old is None:
            style = json_style(old) if old is not None else None
            if old is not None and style is None:
                keys = ", ".join(_flat(overlay))  # key paths only: values can hold secrets
                skipped.append(redact(f"{key}: left as is (its layout is not one loadout rewrites); add by hand from "
                                      f"profile {profile.name}: {keys}"))
                continue  # nothing written, so the record for this file stays as it was
            if m.after or old is not None:
                keys = [f"{attr}.{k}" for k in overlay]
                why = next((reason(profile, k) for k in keys if k in profile.why), reason(profile))
                text = (_json.dumps(m.after, indent=2, ensure_ascii=False) + "\n" if old is None
                        else dumps_like(style, m.after))
                (writes.modify if target.exists() else writes.create)(target, text, why)
                changed.append(target)
        notes += _merge_notes(profile, key, m)
        record[key] = m.record
    if record and any(record[k] != mine.get(k, {}) for k in record):
        repo_config.plan_record(project, writes, profile.name, record, notes)
    return changed, skipped


def _merge_notes(profile: Profile, rel: str, m) -> list[str]:
    from . import repo_merge
    out = [f"{rel}: update {p} to profile {profile.name}'s value" for p in m.updated]
    out += [f"{rel}: remove {p} (no longer in profile {profile.name})" for p in m.removed]
    out += [f"{rel}: {line}" for line in m.kept + m.left]
    out += [f"{rel}: {line} was removed in this repo; kept removed" for line in m.kept_removed]
    for d in m.differs:
        if d.pointer not in m.updated:
            k = repo_merge.unpointer(d.pointer)[-1]
            out.append(f"{rel}: {d.pointer}: kept the repo's {repo_merge.show(d.theirs, k)} (profile {profile.name} "
                       f"has {repo_merge.show(d.new, k)}; loadout profile {profile.name} --take-profile uses it)")
    return [redact(line) for line in out]
```

Remove the now unused `deep_merge` import from `profiles.py` if nothing else there uses it (grep first).

- [ ] **Step 4: Thread `decide` and the notes through `project.py`**

In `_plan_profile`, change the signature to `_plan_profile(prof, project, w, install, decide=None)` and replace `_, skipped = profiles.apply_profile(prof, project, w=w)` with:

```python
    _, skipped = profiles.apply_profile(prof, project, w=w, decide=decide, notes=notes)
```

In `add_profile`, add the parameter `decide=None` (after `result`), and call `_plan_profile(prof, project, w, install, decide)`. In `add_profile`, the invalid-record case must stop before any change with exit 1: `_config_or_report` already calls `repo_config.load`, which now runs `_check_profiles`, so it returns `None` and `add_profile` returns 1 (no extra code; the test checks it).

In `_profile_now`, replace `changed, skipped = profiles.apply_profile(prof, project, w=w)` with:

```python
    merge_notes: list[str] = []
    changed, skipped = profiles.apply_profile(prof, project, w=w, notes=merge_notes)
    for line in merge_notes:
        (steps.append if calm else info)(line)
```

- [ ] **Step 5: Run the new tests**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_profile_three_way.py tests/test_repo_merge.py tests/test_repo_record.py`
Expected: PASS.

- [ ] **Step 6: Run the whole suite and settle the old tests**

Run: `uv run --python 3.12 --with pytest pytest -q > "$WS/suite3.txt" 2>&1; echo rc=$?; tail -30 "$WS/suite3.txt"` (`$WS` = this plan's workspace).
Expected: the only failures are tests that asserted the old rule (an existing different scalar replaced by the profile's value, or a re-run re-adding a list entry the record says was removed). For each: change the assertion to the new rule (the value stays; a `left as is` note), and ledger `Task 3: Ruling: <test> asserted "the profile wins"; now add-only/three-way per spec Part 2`. Any other failure is a bug: superpowers:systematic-debugging.

- [ ] **Step 7: Commit**

```bash
git add cli/loadout/profiles.py cli/loadout/project.py tests/
git commit -m "feat(profile): repo settings and .mcp.json merge three-way against the record"
```

---

### Task 4: `.codex/config.toml` entries are recorded

**Files:**
- Modify: `cli/loadout/codex_project.py` (`config`)
- Modify: `cli/loadout/project.py` (`_plan_profile` passes `record=not held`, plus the note)
- Test: `tests/test_codex_record.py`

**Interfaces:**
- Consumes: Task 1 `pointer`, `stored`, `matches`, `held`, `MISSING`; Task 2 `records`, `plan_record`.
- Produces: `codex_project.config(prof, project, dry_run, skip=frozenset(), w=None, record=True) -> list[str]`; record pointers `mcp_servers/<name>` (the parsed table) and `plugins/<id>/enabled` (`true`); `project.RECORD_LATER` (format with `name`). Line texts: `"mcp {name}: removed from {path} in this repo; kept removed"`, `"plugin {pid}: removed from {path} in this repo; kept removed"`, `"mcp {name}: profile {p} has a new definition; the table in {path} stays (loadout only adds tables there; change it by hand)"`, `"{ptr}: no longer in profile {p}; it stays in {path} (yours to remove)"`.

- [ ] **Step 1: Write the failing tests**

```python
"""The repo's .codex/config.toml: owned text only added, its entries recorded (spec Part 2)."""
import json
from pathlib import Path

import pytest

from loadout import backup, codex_project, profiles, project, targets

PROF = profiles.Profile(name="web", description="", mcp={"mcpServers": {"cd": {"command": "npx", "args": ["-y", "cd@1"]}}},
                        install=["pw@claude-plugins-official"])
CD = "mcp_servers/cd"
PW = "plugins/pw@claude-plugins-official/enabled"


@pytest.fixture
def repo(fake_home, fake_runner, tmp_path):
    p = tmp_path / "repo"
    (p / ".git").mkdir(parents=True)
    (p / ".loadout.json").write_text('{\n  "agents": [\n    "codex"\n  ]\n}\n')
    targets.set_agents({"claude": False, "codex": True})
    return p


def rec(repo):
    return json.loads((repo / ".loadout.json").read_text()).get("profiles", {}).get("web", {}).get(".codex/config.toml", {})


def test_config_records_what_it_added(repo):
    codex_project.config(PROF, repo, False)
    assert rec(repo) == {CD: {"command": "npx", "args": ["-y", "cd@1"]}, PW: True}


def test_a_table_a_person_removed_is_not_added_again(repo):
    codex_project.config(PROF, repo, False)
    cfg = repo / ".codex" / "config.toml"
    cfg.write_text("")
    lines = codex_project.config(PROF, repo, False)
    assert cfg.read_text() == "" and sum("kept removed" in l for l in lines) == 2


def test_a_table_the_user_already_had_is_not_recorded(repo):
    cfg = repo / ".codex" / "config.toml"
    cfg.parent.mkdir()
    cfg.write_text('[mcp_servers.cd]\ncommand = "npx"\nargs = ["-y", "cd@1"]\n')
    codex_project.config(PROF, repo, False)
    assert CD not in rec(repo) and PW in rec(repo)


def test_a_newer_table_in_the_profile_is_noted_not_written(repo):
    codex_project.config(PROF, repo, False)
    newer = profiles.Profile(name="web", description="", mcp={"mcpServers": {"cd": {"command": "npx", "args": ["-y", "cd@2"]}}},
                             install=PROF.install)
    lines = codex_project.config(newer, repo, False)
    assert "cd@1" in (repo / ".codex" / "config.toml").read_text()
    assert any("has a new definition" in l for l in lines) and not any("left as is" in l for l in lines)


def test_the_held_config_records_only_plugins_that_installed(repo, monkeypatch, capsys):
    monkeypatch.setattr(profiles, "load_profile", lambda n: PROF)
    monkeypatch.setattr(codex_project, "plugins", lambda p, dry_run: ["plugin pw@claude-plugins-official: failed: boom"])
    project.add_profile(repo, "web", install=True, approve=lambda plan: True)
    assert CD in rec(repo) and PW not in rec(repo)
    assert "written after the Codex plugin installs" in capsys.readouterr().out


def test_restore_after_the_held_record_write_returns_every_file(repo, monkeypatch, capsys):
    original = (repo / ".loadout.json").read_bytes()
    monkeypatch.setattr(profiles, "load_profile", lambda n: PROF)
    monkeypatch.setattr(codex_project, "plugins", lambda p, dry_run: [])
    project.add_profile(repo, "web", install=True, approve=lambda plan: True)
    assert PW in rec(repo)
    line = next(l for l in capsys.readouterr().out.splitlines() if "undo: loadout restore " in l)
    _, ok, _ = backup.restore(Path(line.split("undo: loadout restore ", 1)[1].strip()))
    assert ok and (repo / ".loadout.json").read_bytes() == original and not (repo / ".codex" / "config.toml").exists()
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_codex_record.py`
Expected: FAIL (`rec(repo) == {}`; `config()` got an unexpected keyword `record` is not hit yet; the removed-table test re-adds the tables).

- [ ] **Step 3: Implement in `codex_project.config`**

Replace the body of `config` from `tl = codex._tomllib()` to the end with:

```python
    from . import repo_config, repo_merge
    from .repo_writes import RepoWrites
    tl = codex._tomllib()
    tables, plugins, lines = _wanted(prof)
    plugins = [p for p in plugins if p not in skip]
    rel = ".codex/config.toml"
    writes = w if w is not None else RepoWrites(project, now=True)
    every = repo_config.records(project, writes)
    mine = every.get(prof.name, {}).get(rel, {})
    others = tuple(r.get(rel, {}) for n, r in every.items() if n != prof.name)
    if not tables and not plugins and not mine:
        return lines
    planned = writes.planned(path)
    old = planned if planned is not None else (path.read_bytes().decode("utf-8") if path.exists() else "")  # CRLF stays
    try:
        before = tl.loads(old)
    except Exception as exc:
        return lines + [f"skipped {path}: it does not parse now ({exc}); fix it, then run loadout profile again"]
    odd = [k for k in ("mcp_servers", "plugins") if not isinstance(before.get(k, {}), dict)]
    if odd:
        return lines + [f"skipped {path}: {', '.join(odd)} is not a table; fix it, then run loadout profile again"]
    added, keys, rec = [], [], {}
    for name, text in tables.items():
        ptr = repo_merge.pointer(("mcp_servers", name))
        want = tl.loads(text)["mcp_servers"][name]
        have = before.get("mcp_servers", {}).get(name, repo_merge.MISSING)
        if have is not repo_merge.MISSING:
            if have == want:
                if ptr in mine or repo_merge.held(others, ptr, repo_merge.stored(want, name)):
                    rec[ptr] = repo_merge.stored(want, name)
            elif ptr in mine and repo_merge.matches(mine[ptr], have, name):
                lines.append(f"mcp {name}: profile {prof.name} has a new definition; the table in {path} stays "
                             "(loadout only adds tables there; change it by hand)")
                rec[ptr] = mine[ptr]
            else:
                if ptr in mine:
                    rec[ptr] = mine[ptr]
                lines.append(f"mcp {name}: left as is in {path} (a server of that name is already there)")
            continue
        if ptr in mine:
            lines.append(f"mcp {name}: removed from {path} in this repo; kept removed")
            rec[ptr] = mine[ptr]
            continue
        added.append(text)
        rec[ptr] = repo_merge.stored(want, name)
        lines.append(("would add" if dry_run else "added") + f" mcp {name} to {path}")
    for pid in plugins:
        ptr = repo_merge.pointer(("plugins", pid, "enabled"))
        if pid in before.get("plugins", {}):
            entry = before["plugins"][pid]
            if not (isinstance(entry, dict) and entry.get("enabled", True) is True):
                lines.append(f"plugin {pid}: switched off in {path}, left as is (Codex will not load it here)")
                if ptr in mine:
                    rec[ptr] = mine[ptr]
            elif ptr in mine or repo_merge.held(others, ptr, True):
                rec[ptr] = True
            continue
        if ptr in mine:
            lines.append(f"plugin {pid}: removed from {path} in this repo; kept removed")
            rec[ptr] = mine[ptr]
            continue
        added.append(f"[plugins.{codex.toml_key(pid)}]\nenabled = true\n")
        keys.append(f"plugins.{codex.toml_key(pid)}.enabled")
        rec[ptr] = True
        lines.append(("would enable" if dry_run else "enabled") + f" plugin {pid} in {path}")
    for pid in skip:  # did not install: recorded only if it is in the file already
        ptr = repo_merge.pointer(("plugins", pid, "enabled"))
        if ptr in mine and pid in before.get("plugins", {}):
            rec[ptr] = mine[ptr]
    for ptr in mine:
        if ptr not in rec and repo_merge.get(before, repo_merge.unpointer(ptr)) is not repo_merge.MISSING \
                and not any(ptr == repo_merge.pointer(("plugins", p, "enabled")) for p in skip):
            lines.append(f"{ptr}: no longer in profile {prof.name}; it stays in {path} (yours to remove)")
    if dry_run:
        return lines
    if added:
        nl = "\r\n" if "\r\n" in old else "\n"  # the new tables take the file's line endings
        new = (old.rstrip("\r\n") + nl + nl if old.strip() else "") + "\n".join(added).replace("\n", nl)
        try:
            after = tl.loads(new)
        except Exception as exc:
            return lines + [f"skipped {path}: the result would not parse ({exc}); nothing written"]
        if codex._without_owned(before, set(tables), keys, tl) != codex._without_owned(after, set(tables), keys, tl):
            return lines + [f"skipped {path}: the edit would change entries loadout does not own; nothing written"]
        (writes.modify if path.exists() else writes.create)(path, new, profiles.reason(prof))
    if record and rec != mine:
        repo_config.plan_record(project, writes, prof.name, {rel: rec}, lines)
    return lines
```

Add `record: bool = True` to the signature and the docstring: "record False: the record is written later (after the Codex plugin installs, by the call that writes the file)".

- [ ] **Step 4: Hold the record with the file in `_plan_profile`**

In `cli/loadout/project.py` add after `CODEX_BAD`:

```python
RECORD_LATER = (".loadout.json: the record of profile {name}'s .codex/config.toml entries is written after the Codex "
                "plugin installs, naming only what was added")
```

In `_plan_profile`, replace the `codex_project.config(prof, project, False, w=w)` call with:

```python
        held = _codex_after_installs(project, install)
        for line in codex_project.config(prof, project, False, w=w, record=not held):
```

and after that loop: `if held and (codex_project._wanted(prof)[0] or codex_project._wanted(prof)[1]): notes.append(RECORD_LATER.format(name=prof.name))`. The `.loadout.json:` line contains none of `CODEX_BAD`, so it stays a note. The call in `_after_apply` keeps `record=True` (the default) and its `RepoWrites(project, now=True, bk=bk)`.

- [ ] **Step 5: Run the tests**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_codex_record.py tests/test_codex_project.py tests/test_codex_review_pr44.py`
Expected: PASS. If the restore test fails because two copies of `.loadout.json` restore in the wrong order, read `backup.restore`'s step order and fix it so the first copy wins (the file as it was before the run); this is the Review Focus 3 failure, fix it with this test RED→GREEN.

- [ ] **Step 6: Whole suite, then commit**

Run: `uv run --python 3.12 --with pytest pytest -q > "$WS/suite4.txt" 2>&1; echo rc=$?; tail -5 "$WS/suite4.txt"`
Expected: rc=0.

```bash
git add cli/loadout/codex_project.py cli/loadout/project.py tests/test_codex_record.py
git commit -m "feat(codex): the repo's .codex/config.toml entries are recorded; a removed table stays removed"
```

---

### Task 5: `--take-profile` and the one question

**Files:**
- Modify: `cli/loadout/project.py` (`TAKE_QUESTION`, `chooser`, `init` passes a chooser)
- Modify: `cli/loadout/__main__.py` (`profile --take-profile`)
- Test: `tests/test_take_profile.py`

**Interfaces:**
- Consumes: Task 3 `add_profile(..., decide=)`, `_plan_profile(..., decide)`.
- Produces: `project.TAKE_QUESTION = "Use the profile's values for these? [y/N] "`; `project.chooser(take: bool, ask, interactive: bool, dry_run: bool = False)` returning `decide(lines) -> bool`; `project.KEPT_NO_TERMINAL`.

- [ ] **Step 1: Write the failing tests**

```python
"""The question about a teammate's changes, and --take-profile (spec Part 2)."""
import json

import pytest

from loadout import __main__ as cli, profiles, project, targets

LINES = ["This repo differs from profile web in 1 entry:", '  .claude/settings.json  env/A: the repo has "9", the profile has "2"']


def test_take_profile_takes_without_asking(capsys):
    assert project.chooser(True, lambda q: pytest.fail("asked"), True)(LINES) is True
    assert LINES[0] in capsys.readouterr().out


def test_without_a_terminal_the_repo_values_stay_and_the_flag_is_named(capsys):
    assert project.chooser(False, lambda q: pytest.fail("asked"), False)(LINES) is False
    assert "--take-profile" in capsys.readouterr().out


def test_a_dry_run_does_not_ask():
    assert project.chooser(False, lambda q: pytest.fail("asked"), True, dry_run=True)(LINES) is False


def test_in_a_terminal_it_asks_once():
    asked = []
    assert project.chooser(False, lambda q: asked.append(q) or "y", True)(LINES) is True
    assert asked == [project.TAKE_QUESTION]


@pytest.fixture
def shared(fake_home, fake_runner, tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    targets.set_agents({"claude": True, "codex": False})
    value = {"A": "1"}
    monkeypatch.setattr(profiles, "load_profile", lambda n: profiles.Profile(name=n, description="d", settings={"env": dict(value)}))
    project.add_profile(repo, "web", install=False, approve=lambda plan: True)
    path = repo / ".claude" / "settings.json"
    path.write_text(json.dumps({"env": {"A": "9"}}, indent=2) + "\n")
    value["A"] = "2"
    monkeypatch.chdir(repo)
    return path


def test_the_cli_flag_takes_the_profile_values(shared):
    assert cli.main(["profile", "web", "--yes", "--take-profile", "--no-install"]) == 0
    assert json.loads(shared.read_text())["env"]["A"] == "2"


def test_yes_alone_keeps_the_repo_values(shared):
    assert cli.main(["profile", "web", "--yes", "--no-install"]) == 0
    assert json.loads(shared.read_text())["env"]["A"] == "9"


def test_the_question_comes_before_the_plan(shared, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_ask", lambda q: "y")
    monkeypatch.setattr("loadout.ui.is_interactive", lambda: True)
    cli.main(["profile", "web", "--no-install"])
    out = capsys.readouterr().out
    assert out.index("This repo differs") < out.index("Plan for")
    assert json.loads(shared.read_text())["env"]["A"] == "2"
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_take_profile.py`
Expected: FAIL (`module 'loadout.project' has no attribute 'chooser'`; argparse rejects `--take-profile`).

- [ ] **Step 3: Implement**

In `cli/loadout/project.py`, after `approver`:

```python
TAKE_QUESTION = "Use the profile's values for these? [y/N] "
KEPT_NO_TERMINAL = "  kept the repo's values (run it again with --take-profile to use the profile's)"


def chooser(take: bool, ask: Ask, interactive: bool, dry_run: bool = False):
    """Whether to use the profile's values where a person changed an entry: --take-profile, else the question in a
    terminal; without one (and in a dry run) the repo's values stay. The entries are printed in every case."""
    def decide(lines: list[str]) -> bool:
        print("\n".join(lines))
        if take:
            return True
        if dry_run:
            return False
        if not interactive:
            print(KEPT_NO_TERMINAL)
            return False
        return ui.confirm(ask, TAKE_QUESTION)
    return decide
```

In `init`, pass a chooser to `_plan_profile`: `_plan_profile(prof, project, w, install, chooser(False, ask, interactive and not yes, dry_run))`.

In `cli/loadout/__main__.py`, in the `profile` parser, add before `--verbose`:

```python
    p.add_argument("--take-profile", action="store_true",
                   help="where someone changed an entry the profile set, use the profile's value")
```

and pass `decide=project.chooser(a.take_profile, _ask, ui.is_interactive(), a.dry_run)` to `project.add_profile` in its `set_defaults` lambda. Check that `_ask` is the module-level name the lambda uses (it is used by `init` the same way); if it is bound differently, adapt the test's monkeypatch target and ledger it.

- [ ] **Step 4: Run them to see them pass**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_take_profile.py tests/test_profile_three_way.py`
Expected: PASS.

- [ ] **Step 5: Whole suite, then commit**

Run: `uv run --python 3.12 --with pytest pytest -q > "$WS/suite5.txt" 2>&1; echo rc=$?; tail -5 "$WS/suite5.txt"`
Expected: rc=0.

```bash
git add cli/loadout/project.py cli/loadout/__main__.py tests/test_take_profile.py
git commit -m "feat(profile): ask once about entries a teammate changed; --take-profile uses the profile's values"
```

---

### Task 6: `loadout explain <file>`

**Files:**
- Create: `cli/loadout/explain.py`
- Modify: `cli/loadout/commands.py` (register `explain`), `cli/loadout/__main__.py` (`EXEMPT` gets `"explain"`)
- Test: `tests/test_explain.py`

**Interfaces:**
- Consumes: Task 1 `get`, `matches`, `show`, `unpointer`, `MISSING`, `SHAPE`; Task 2 records via `repo_config.load(root).data`; `new_skill.repo_root`.
- Produces: `explain.explain(target: str, cwd: Path | None = None) -> int`. States: `loadout's value`, `changed in this repo (now X)`, `removed in this repo`, `cannot compare, the file does not parse`.

- [ ] **Step 1: Write the failing tests**

```python
"""loadout explain: which entries in a repo file are loadout's (spec Part 0)."""
import json

import pytest

from loadout import __main__ as cli, explain, profiles, project, targets

TOKEN = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"


@pytest.fixture
def repo(fake_home, fake_runner, tmp_path, monkeypatch):
    p = tmp_path / "repo"
    (p / ".git").mkdir(parents=True)
    targets.set_agents({"claude": True, "codex": True})
    monkeypatch.setattr(profiles, "load_profile", lambda n: profiles.Profile(
        name=n, description="d", settings={"env": {"A": "1"}, "permissions": {"allow": ["x", "y"]}},
        mcp={"mcpServers": {"gh": {"command": "gh-mcp", "env": {"GITHUB_TOKEN": TOKEN}}}}))
    (p / ".loadout.json").write_text('{\n  "agents": [\n    "claude",\n    "codex"\n  ]\n}\n')
    project.add_profile(p, "web", install=False, approve=lambda plan: True)
    return p


def test_it_lists_loadouts_entries_and_their_state(repo, capsys):
    path = repo / ".claude" / "settings.json"
    data = json.loads(path.read_text())
    data["env"]["A"] = "9"
    data["permissions"]["allow"].remove("x")
    path.write_text(json.dumps(data, indent=2) + "\n")
    capsys.readouterr()
    assert explain.explain(".claude/settings.json", cwd=repo) == 0
    out = capsys.readouterr().out
    assert 'profile web  env/A: "1"  changed in this repo (now "9")' in out
    assert 'permissions/allow: "x"  removed in this repo' in out
    assert "permissions/allow: \"y\"  loadout's value" in out


def test_a_secret_is_never_shown(repo, capsys):
    capsys.readouterr()
    explain.explain(".mcp.json", cwd=repo)
    out = capsys.readouterr().out
    assert TOKEN not in out and "(a secret value, not shown)" in out


def test_codex_entries_are_listed(repo, capsys):
    capsys.readouterr()
    explain.explain(".codex/config.toml", cwd=repo)
    assert "mcp_servers/gh" in capsys.readouterr().out


def test_loadout_json_and_gitignore(repo, capsys):
    (repo / ".gitignore").write_text("node_modules\n\n# loadout\n.claude/settings.local.json\n.serena/cache/\n")
    capsys.readouterr()
    explain.explain(".loadout.json", cwd=repo)
    explain.explain(".gitignore", cwd=repo)
    out = capsys.readouterr().out
    assert "agents: claude, codex" in out and "profile web:" in out
    assert ".claude/settings.local.json" in out and "node_modules" not in out


def test_a_file_without_entries_says_so(repo, capsys):
    (repo / "README.md").write_text("hi\n")
    assert explain.explain("README.md", cwd=repo) == 0
    assert "recorded no entries" in capsys.readouterr().out


def test_outside_a_repo_is_an_error(tmp_path, fake_home, capsys):
    (tmp_path / "x.json").write_text("{}")
    assert explain.explain("x.json", cwd=tmp_path) == 1


def test_it_writes_nothing(repo, fake_home, monkeypatch):
    def snapshot():
        return {p: p.read_bytes() for root in (repo, fake_home) for p in root.rglob("*") if p.is_file()}
    before = snapshot()
    monkeypatch.chdir(repo)
    assert cli.main(["explain", ".claude/settings.json"]) == 0
    assert snapshot() == before
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_explain.py`
Expected: FAIL (`cannot import name 'explain'`).

- [ ] **Step 3: Write the module**

```python
"""`loadout explain FILE`: the entries loadout wrote in a repo file, from which profile, and whether each still has
loadout's value (read-only; spec Part 0, ADR 0031)."""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import repo_config, repo_merge
from .secrets import redact

BROKEN = object()


def _current(path: Path, rel: str):
    if not path.is_file():
        return None
    try:
        if rel == ".codex/config.toml":
            from . import codex
            return codex._tomllib().loads(path.read_bytes().decode("utf-8"))
        return json.loads(path.read_text(encoding="utf-8-sig") or "{}")
    except Exception:
        return BROKEN


def _states(stored, data, ptr: str) -> list[str]:
    path = repo_merge.unpointer(ptr)
    key = path[-1]
    if data is BROKEN:
        return [f"{ptr}: {repo_merge.show(stored, key)}  cannot compare, the file does not parse"]
    now = repo_merge.get(data, path) if data is not None else repo_merge.MISSING
    if isinstance(stored, list):
        return [f"{ptr}: {repo_merge.show(s, key)}  "
                + ("loadout's value" if isinstance(now, list) and any(repo_merge.matches(s, x, key) for x in now)
                   else "removed in this repo") for s in stored]
    if repo_merge.matches(stored, now, key):
        state = "loadout's value"
    elif now is repo_merge.MISSING or now is repo_merge.SHAPE:
        state = "removed in this repo"
    else:
        state = f"changed in this repo (now {repo_merge.show(now, key)})"
    return [f"{ptr}: {repo_merge.show(stored, key)}  {state}"]


def _own(cfg) -> int:
    if not cfg.exists:
        print(".loadout.json: not in this repo (loadout init or loadout profile adds it)")
        return 1
    agents = ", ".join(a for a in repo_config.AGENTS if a in (cfg.agents or ())) or "not set (each user's agents)"
    print(f".loadout.json: loadout's file for this repo (commit it). agents: {agents}; "
          f"manage: {str(cfg.manage).lower()}")
    for name, files in sorted((cfg.data.get("profiles") or {}).items()):
        n = sum(len(e) for e in files.values())
        print(f"  profile {name}: {n} recorded entr{'y' if n == 1 else 'ies'} in {', '.join(sorted(files))}")
    return 0


def _gitignore(path: Path) -> int:
    if not path.is_file():
        print(".gitignore: no such file")
        return 1
    lines = path.read_text(encoding="utf-8").splitlines()
    if "# loadout" not in [l.strip() for l in lines]:
        print(".gitignore: no lines from loadout (it adds them under a '# loadout' line)")
        return 0
    at = next(i for i, l in enumerate(lines) if l.strip() == "# loadout") + 1
    ours = []
    while at < len(lines) and lines[at].strip() and not lines[at].startswith("#"):
        ours.append(lines[at].strip())
        at += 1
    print(".gitignore: loadout added the lines under '# loadout': " + (", ".join(ours) or "(none)"))
    print("  every other line is yours")
    return 0


def explain(target: str, cwd: Path | None = None) -> int:
    from .new_skill import repo_root
    path = Path(os.path.abspath(Path(cwd or Path.cwd()) / target))
    root = repo_root(path.parent)
    if root is None:
        print(f"{target}: not inside a git repo; loadout records entries only in repos")
        return 1
    try:
        cfg = repo_config.load(root)
    except repo_config.Invalid as exc:
        print(exc)
        return 1
    rel = path.relative_to(root).as_posix()
    if rel == repo_config.FILE:
        return _own(cfg)
    if rel == ".gitignore":
        return _gitignore(path)
    found = [(name, files[rel]) for name, files in sorted((cfg.data.get("profiles") or {}).items()) if rel in files]
    if not found:
        if not path.exists():
            print(f"{rel}: no such file in {root}")
            return 1
        print(f"{rel}: loadout recorded no entries in it. loadout records only what profiles write in "
              ".claude/settings.json, .mcp.json and .codex/config.toml; a file init created is yours once it exists")
        return 0
    data = _current(path, rel)
    print(f"{rel} in {root}: entries loadout wrote (recorded in .loadout.json)")
    for name, entries in found:
        for ptr, stored in entries.items():
            for line in _states(stored, data, ptr):
                print(redact(f"  profile {name}  {line}"))
    print("  everything else in this file is yours; loadout does not change it")
    return 0
```

- [ ] **Step 4: Register the command**

In `cli/loadout/commands.py`, after `_register_kit_path`'s `EXTRA_COMMANDS.append(...)`, in the file's style:

```python
def _register_explain(sub) -> None:
    p = sub.add_parser("explain", help="which entries in a repo file loadout wrote, and whether each is unchanged")
    p.add_argument("file", help="a file in the current repo, e.g. .claude/settings.json")

    def run(a):
        from .explain import explain
        return explain(a.file)
    p.set_defaults(func=run)


EXTRA_COMMANDS.append(_register_explain)
```

In `cli/loadout/__main__.py`, add `"explain"` to `EXEMPT` (it reads only).

- [ ] **Step 5: Run them to see them pass**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_explain.py`
Expected: PASS. If the codex test fails because `add_profile` with the user's Codex on and `install=False` did not write `.codex/config.toml`, check `_codex_after_installs` (it is False without installs, so the plan writes it) before changing anything.

- [ ] **Step 6: Commit**

```bash
git add cli/loadout/explain.py cli/loadout/commands.py cli/loadout/__main__.py tests/test_explain.py
git commit -m "feat(explain): loadout explain lists the entries loadout wrote in a repo file"
```

---

### Task 7: two users on one repo

**Files:**
- Test: `tests/test_two_users.py`
- Modify: whatever the test shows is wrong (each fix RED→GREEN, ledgered)

**Interfaces:**
- Consumes: everything above; `project.init(..., agents=)`, `project.add_profile(..., decide=)`.

- [ ] **Step 1: Write the simulation**

```python
"""Two loadout users on one repo (spec Parts 2 and 5): A has both agents, B has Codex only. After every step both
users' agents' files are complete and no entry a person changed was reversed without a yes."""
import json

import pytest

from loadout import profiles, project, targets


@pytest.fixture
def world(fake_home, fake_runner, tmp_path, monkeypatch):
    homes = {"a": tmp_path / "home-a", "b": tmp_path / "home-b"}
    for h in homes.values():
        h.mkdir()
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    state = {"settings": {"env": {"MODE": "fast"}, "permissions": {"allow": ["Bash(npm test)"]}},
             "mcp": {"mcpServers": {"cd": {"command": "npx", "args": ["-y", "cd@1"]}}}}
    monkeypatch.setattr(profiles, "load_profile", lambda n: profiles.Profile(
        name=n, description="Web", settings=json.loads(json.dumps(state["settings"])), mcp=state["mcp"]))

    def as_user(who):
        monkeypatch.setenv("HOME", str(homes[who]))
        monkeypatch.setenv("USERPROFILE", str(homes[who]))
        targets.set_agents({"claude": who == "a", "codex": True})
    return repo, state, as_user


def files(repo):
    return {p.relative_to(repo).as_posix(): p.read_bytes() for p in repo.rglob("*") if p.is_file() and ".git" not in p.parts}


def settings(repo):
    return json.loads((repo / ".claude" / "settings.json").read_text())


def complete(repo):
    assert "cd" in json.loads((repo / ".mcp.json").read_text())["mcpServers"]
    assert "[mcp_servers.cd]" in (repo / ".codex" / "config.toml").read_text()
    assert set(json.loads((repo / ".loadout.json").read_text())["agents"]) == {"claude", "codex"}


def profile(repo, **kw):
    return project.add_profile(repo, "web", install=False, approve=lambda plan: True, **kw)


def test_two_users_keep_each_other_whole(world):
    repo, state, as_user = world
    as_user("a")
    assert project.init(repo, ["web"], yes=True, install=False, dry_run=False, ask=lambda q: "", interactive=False,
                        agents=frozenset({"claude", "codex"})) == 0
    complete(repo)

    as_user("b")  # Codex only: the same profile again changes nothing
    before = files(repo)
    assert profile(repo) == 0
    assert files(repo) == before

    path = repo / ".claude" / "settings.json"  # B changes a value by hand
    data = settings(repo)
    data["env"]["MODE"] = "slow"
    path.write_text(json.dumps(data, indent=2) + "\n")

    as_user("a")
    assert profile(repo) == 0
    assert settings(repo)["env"]["MODE"] == "slow"
    complete(repo)

    state["settings"]["env"]["MODE"] = "safe"  # the profile is updated
    state["settings"]["permissions"]["allow"].append("Bash(npm run lint)")
    as_user("b")  # a Codex-only user still keeps Claude Code's repo files current
    assert profile(repo) == 0
    assert settings(repo)["permissions"]["allow"] == ["Bash(npm test)", "Bash(npm run lint)"]
    assert settings(repo)["env"]["MODE"] == "slow"
    complete(repo)

    data = settings(repo)  # A removes an entry by hand
    data["permissions"]["allow"].remove("Bash(npm test)")
    path.write_text(json.dumps(data, indent=2) + "\n")
    as_user("b")  # nothing differs any more (MODE "safe" was offered once and declined), so no question
    asked = []
    assert profile(repo, decide=lambda lines: asked.append(lines) or True) == 0
    assert asked == []
    assert settings(repo)["permissions"]["allow"] == ["Bash(npm run lint)"]  # the removal stays
    assert settings(repo)["env"]["MODE"] == "slow"
    complete(repo)

    as_user("a")
    before = files(repo)
    assert profile(repo) == 0
    assert files(repo) == before
```

- [ ] **Step 2: Run it**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_two_users.py`
Expected: PASS. If it fails, the failure is a real bug in Tasks 3–5 (or a test assumption to re-check against the merge rules table above): superpowers:systematic-debugging, fix with a focused test RED→GREEN, ledger it.

- [ ] **Step 3: Commit**

```bash
git add tests/test_two_users.py cli/
git commit -m "test(repo): two users with different agents keep one repo whole"
```

---

### Task 8: docs (category B, ADR 0031, explain, the record)

**Files:**
- Create: `docs/adr/0031-repo-profile-entries-merge-three-way.md`
- Modify: `docs/adr/README.md`, `docs/adr/0007-tiered-scoping-with-profiles.md` (status note), `docs/reference/profile-format.md`, `docs/reference/cli.md`, `docs/how-to/write-a-profile.md`, `docs/how-to/your-own-tools.md`, `docs/explanation/security-and-trust.md`, `AGENTS.md`, `docs/superpowers/plans/2026-10-16-repo-agents-docs-baseline.md` (mark B done)
- Test: `tests/` doc-link tests already in the suite

- [ ] **Step 1: Write ADR 0031**

```markdown
# 0031. Profile entries in repo files merge three-way against a record

- Status: Accepted
- Date: 2026-10-17
- Source: [Design: repos for chosen agents](../superpowers/specs/2026-10-16-repo-agents-and-careful-ux-design.md), Part 2
- Supersedes: the merge rule of [ADR 0007](0007-tiered-scoping-with-profiles.md) (settings and MCP servers "merged" with the profile's value winning)

## Context

`loadout profile` merged a profile into the repo's `.claude/settings.json` and `.mcp.json` with a deep merge in which the profile's value won. In a repo shared by two loadout users, a re-run reversed a value a teammate had changed, and an entry someone had removed came back. A profile update could not be told apart from a teammate's change, because loadout did not know what it had written.

## Decision

- `.loadout.json` (committed) records, per profile and file, the entries the profile wrote: `"profiles": {"web": {".claude/settings.json": {"env/MODE": "fast", "permissions/allow": ["Bash(npm test)"]}}}`. Paths are JSON-pointer style; lists record the entries loadout added; an MCP server definition is one entry; a value that looks like a secret is recorded as `sha256:<hex>`.
- A re-run compares the record, the file and the profile per entry. The file still has the recorded value: the profile's update applies. Someone changed it: the value stays; when the profile has a new value, loadout lists these entries and asks once (`Use the profile's values for these? [y/N]`; without a terminal they stay unless `--take-profile`). The offer is recorded, so the same value is not asked again. A list entry someone removed stays removed. An entry the profile dropped is removed only when the file still has loadout's value and no other profile recorded it.
- Without a record (a repo from before this change), only missing entries are added; an existing different value stays and is reported.
- `.codex/config.toml` keeps its owned-text rule (tables are only added); its entries are recorded the same way, so a removed table is not added back.
- `loadout explain <file>` reads the record and shows each entry's state.

## Alternatives considered

- Keep "the profile wins": simple, but a re-run silently undoes a teammate's change.
- Record in a local, uncommitted state file: the other user's runs would not see it, so their runs could not tell an update from a change.
- Ask about every differing entry on every run: safe, but a declined value would be asked again on every run.

## Consequences

- Two users with different agents can re-run profiles on one repo; neither run reverses the other's changes without a yes.
- `.loadout.json` changes when a profile writes new entries; it is committed with them.
- A `.loadout.json` whose layout loadout cannot reproduce gets no record (the plan says so); the repo then behaves as one without a record.

## In the code

- `cli/loadout/repo_merge.py` (`merge`, `stored`, `matches`)
- `cli/loadout/repo_config.py` (`records`, `record_text`, `plan_record`)
- `cli/loadout/profiles.py` (`apply_profile`), `cli/loadout/codex_project.py` (`config`), `cli/loadout/project.py` (`chooser`)
- `cli/loadout/explain.py`
```

- [ ] **Step 2: Update the pages**

Run first: `grep -rn "profile wins\|profile's value wins\|lists are joined\|Merged into the repo\|deep merge" README.md AGENTS.md docs plugins/loadout/skills .serena/memories --include=*.md | grep -v superpowers` and fix every hit, including these:

- `docs/reference/profile-format.md`, step 1 of "In this order": replace "Dicts merge recursively, lists are joined without duplicates, and for any other value the profile wins." with "The merge is three-way against the profile's record in [`.loadout.json`](cli.md#loadoutjson) ([ADR 0031](../adr/0031-repo-profile-entries-merge-three-way.md)): a missing entry is added; a profile update applies when the file still has the value loadout wrote; a value someone changed stays (loadout asks once when the profile has a new one, `--take-profile` takes it); a list entry someone removed stays removed; an entry the profile dropped is removed when it is unchanged. Without a record, only missing entries are added. An MCP server's definition is one entry." In the field table, `settings` and `mcp`: "Merged into" → "Merged (three-way, see below) into".
- `docs/reference/profile-format.md`, "In Codex": add one sentence that the `.codex/config.toml` tables are only added and are recorded, so a table someone removed is not added back, and a newer table in the profile is noted, not written.
- `docs/reference/cli.md`, `loadout profile`: add the `--take-profile` row ("Where someone changed an entry the profile set, use the profile's value. Without it, a terminal asks once; without a terminal the repo's values stay."); in the `.loadout.json` table add the `profiles` row ("Written by loadout: per profile and file, the entries it wrote (JSON-pointer paths; lists: the entries loadout added; a secret-looking value as `sha256:…`). `loadout explain` reads it. Commit it."); add an invalid-`profiles` sentence to the invalid-file paragraph; add a `## loadout explain` section (what it prints, the four states, `.loadout.json` and `.gitignore`, read-only, exit 0, exit 1 outside a repo, for a missing file without a record, and for an invalid `.loadout.json`); add `explain` to the command list at the top of the page.
- `docs/how-to/write-a-profile.md` (line ~28): "merges `settings` into … and `mcp` into …" → add "three-way against what it wrote last time, so a teammate's changes stay ([Applying a profile](../reference/profile-format.md#what-applying-a-profile-does))".
- `docs/how-to/your-own-tools.md` (line ~27): "merges servers and settings into" → "merges servers and settings (three-way, keeping a teammate's changes) into".
- `docs/explanation/security-and-trust.md` (line ~57): "(the profile's value wins on the same key)" → "(three-way against a record in `.loadout.json`: a value someone changed is kept unless they say yes; [ADR 0031](../adr/0031-repo-profile-entries-merge-three-way.md))"; add that `.loadout.json` records secret-looking values only as hashes.
- `AGENTS.md`: the map line for `repo_config.py` → "`.loadout.json` (the repo's agents, `manage`, the profiles' record)"; add "`repo_merge.py` the three-way merge of profile entries against the record; `explain.py` `loadout explain`"; the ADR range `0001-0030` → `0001-0031`; in Code Review Rules → User files, add: "A profile re-run that changes an entry a person changed in a repo file, without their yes, is P1 (ADR 0031)."
- `docs/adr/README.md`: add the 0031 row ("Profile entries in repo files merge three-way against a record", Accepted); 0007's status cell: "Accepted; merge rule superseded by 0031".
- `docs/adr/0007-tiered-scoping-with-profiles.md`: Status line → "Accepted; its merge rule is superseded by [0031](0031-repo-profile-entries-merge-three-way.md)".
- The docs baseline plan: under its header add "B: done in PR 2 (repo-agents PR 2)."

- [ ] **Step 3: Run the suite (doc-link tests) and validate**

Run: `uv run --python 3.12 --with pytest pytest -q > "$WS/suite8.txt" 2>&1; echo rc=$?; tail -5 "$WS/suite8.txt"; claude plugin validate . && claude plugin validate plugins/loadout`
Expected: rc=0; both validations pass. Then the grep from Step 2 prints nothing that states the old rule.

- [ ] **Step 4: Commit**

```bash
git add docs AGENTS.md
git commit -m "docs(repo): three-way profile merge, the record, loadout explain (ADR 0031)"
```
