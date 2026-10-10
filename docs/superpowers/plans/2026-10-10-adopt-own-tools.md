# Adopt: your own tools — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `loadout adopt` (and `loadout configure own`) let the user choose global / project / leave / remove for every plugin, marketplace, MCP server, skill and hook that loadout does not manage.

**Architecture:** A new module `cli/loadout/own.py` holds the personal-layer index, the leave decisions, choice parsing, prompts and the recorders that write the personal layer or a personal profile. `adopt.apply_own` orchestrates: record → existing removal paths in `adopt.apply` → deferred machine steps → `link.link_all` → `settings_merge.apply_settings`. `inventory.classify` becomes personal-layer aware and renames the action `unknown` to `own`.

**Tech Stack:** Python 3.12 stdlib only (`cli/loadout/`), pytest with `fake_home` / `fake_runner` fixtures (`tests/conftest.py`), the bash eval suite in `plugins/loadout/evals/`.

**Spec:** `docs/superpowers/specs/2026-10-10-adopt-own-tools-design.md`

## Global Constraints

- Stdlib only; no new dependencies. `requires-python = ">=3.10"` (pyproject.toml): no 3.11+ only syntax or modules; use `from __future__ import annotations` like the existing modules.
- Tests never touch the real `~/.claude`, `~/.claude.json` or `~/.config/loadout`: always the `fake_home` fixture (sets `HOME`, clears `LOADOUT_PERSONAL`) and `fake_runner` (no real `claude` calls).
- Default everywhere is **leave**: `--yes`, non-interactive runs and an empty answer change nothing about own tools.
- Every change goes through one `Backup`; `loadout restore` must undo it. Write the manifest step before the change (existing convention in `backup.py`).
- Every printed line that can contain a config goes through `secrets.redact`.
- Collisions are never overwritten: "skipped: <name> already exists in <file> with a different config".
- Unknown or ambiguous names in `--own` / `configure set own` exit with code **2** before anything changes.
- Commits: Conventional Commits (`type(scope): subject`), no `Co-Authored-By` or any attribution trailer.
- Run tests with `uv run --python 3.12 --with pytest pytest -q` (431+ passing before this work).

## Review Focus

1. **Hook index drift** — several hooks chosen in one run: removals (`adopt._apply_hooks`, index based) and global rewrites (content based) must not hit the wrong hook. Pinned in Task 7 (`test_apply_own_two_hooks_one_group`).
2. **List-union merge duplicates a hook** — a hook recorded globally while its original group has other hooks must not run twice after `apply_settings`. Pinned in Task 5 (`test_global_hook_no_duplicate_after_merge`).
3. **Secrets leak into the personal git repo** — a recorded MCP server must only ever contain `${VAR}`; a server with an unfixable secret (args/url) must be refused for global/project. Pinned in Task 5 (`test_global_mcp_unfixable_secret_blocked`) and Task 6 (`test_project_mcp_rewrites_secret`).
4. **Re-run asks again** — after any choice, a second classify must not list the item as `own`. Pinned in Task 7 (`test_rerun_asks_nothing`).
5. **Restore leaves a broken skill** — global skill: after `restore`, `~/.claude/skills/<name>` is the original directory again (not a dangling link), also in copy mode. Pinned in Task 5 (`test_global_skill_dir_restore`).

---

## File Structure

| File | Responsibility |
|---|---|
| `cli/loadout/own.py` (new) | Personal-layer index, leave decisions, `Choice` parsing, `options`, prompts, recorders (`record_global`, `record_project`), `candidate_repos`. No import of `adopt`. |
| `cli/loadout/secrets.py` | + `rewrite()` and `append_env()` (factored out of `adopt.fix_secrets`). |
| `cli/loadout/personal_mcp.py` | + `replace_user_server()` (factored out of `adopt.fix_secrets`). |
| `cli/loadout/inventory.py` | Personal-layer aware `classify`; action `own`. |
| `cli/loadout/link.py` | `LINKS()` adds personal skills, `skills.json` pointers, `hooks/`. |
| `cli/loadout/check.py` | `_links` labels and skips missing sources; new `_own` line. |
| `cli/loadout/profiles.py` | `skills` field, `copy_skills()`. |
| `cli/loadout/project.py` | `add_profile` copies profile skills. |
| `cli/loadout/adopt.py` | `own` group, keep-global pick, `apply_own`, `run(own_spec=...)`, repo offer. |
| `cli/loadout/configure.py` | `offer_commit()` (factored out of `apply_all`), `own_lines()`, `set_own()`. |
| `cli/loadout/commands.py` | `adopt --own`, `configure own [--all]`, `configure set own NAME CHOICE`. |
| `plugins/loadout/skills/configure/SKILL.md`, `plugins/loadout/evals/bin/loadout`, `plugins/loadout/evals/configure-own/` | Skill text, eval stub, new eval case. |
| `README.md`, `docs/superpowers/specs/2026-10-08-agent-loadout-design.md`, `plugins/loadout/skills/onboard/SKILL.md` | Docs. |
| `tests/test_own.py` (new), `tests/test_inventory.py`, `tests/test_adopt.py`, `tests/test_link_backup.py`, `tests/test_project.py`, `tests/test_check.py`, `tests/test_configure.py`, `tests/test_secrets.py` | Tests. |

---

### Task 1: Factor the secret rewrite and the user-server replace out of `fix_secrets`

**Files:**
- Modify: `cli/loadout/secrets.py` (append functions)
- Modify: `cli/loadout/personal_mcp.py` (append function)
- Modify: `cli/loadout/adopt.py` (`_open_secrets_file`, `fix_secrets`)
- Test: `tests/test_secrets.py`

**Interfaces:**
- Produces: `secrets.rewrite(server: str, cfg: dict, findings: list[Finding], known: dict[str, str]) -> tuple[dict, list[str], list[str]]` — returns (new config with `${VAR}`, new `NAME='value'\n` lines, var names); `known` is updated in place.
- Produces: `secrets.append_env(path: Path, lines: list[str], bk) -> None` — creates the file 0600 (recorded as created) or saves a copy first, then appends.
- Produces: `personal_mcp.replace_user_server(name: str, original: dict, new: dict, bk) -> str` — returns `"ok"`, `"failed: <stderr> (original re-added: ok|failed: ...)"`, or `"manual: <path of commands file>"`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_secrets.py`)

```python
def test_rewrite_returns_var_config_and_lines():
    from loadout import secrets
    cfg = {"command": "x", "env": {"API_KEY": "k" * 20}}
    found = secrets.scan({"mcpServers": {"srv": cfg}})
    known = {}
    new, lines, names = secrets.rewrite("srv", cfg, found, known)
    assert new["env"]["API_KEY"] == "${SRV_API_KEY}"
    assert cfg["env"]["API_KEY"] == "k" * 20          # original untouched
    assert lines == ["SRV_API_KEY='" + "k" * 20 + "'\n"] and names == ["SRV_API_KEY"]
    assert known == {"SRV_API_KEY": "k" * 20}


def test_rewrite_never_overwrites_a_different_value():
    from loadout import secrets
    cfg = {"command": "x", "env": {"API_KEY": "k" * 20}}
    found = secrets.scan({"mcpServers": {"srv": cfg}})
    new, lines, names = secrets.rewrite("srv", cfg, found, {"SRV_API_KEY": "other"})
    assert names == ["SRV_API_KEY_2"] and new["env"]["API_KEY"] == "${SRV_API_KEY_2}"


def test_append_env_creates_private_file_and_records_it(fake_home):
    import os, stat
    from loadout import backup, paths, secrets
    bk = backup.Backup()
    secrets.append_env(paths.secrets_file(), ["A='1'\n"], bk)
    assert paths.secrets_file().read_text() == "A='1'\n"
    if os.name != "nt":
        assert stat.S_IMODE(paths.secrets_file().stat().st_mode) == 0o600
    assert any("created" in s["undo"] for s in bk.steps)


def test_replace_user_server_records_undo_and_reports_ok(fake_home, fake_runner):
    from loadout import backup, personal_mcp
    bk = backup.Backup()
    assert personal_mcp.replace_user_server("srv", {"command": "a"}, {"command": "b"}, bk) == "ok"
    assert ["claude", "mcp", "remove", "-s", "user", "srv"] in fake_runner.calls
    assert [s["undo"]["run"][2] for s in bk.steps] == ["add-json", "remove"]


def test_replace_user_server_cmd_shim_removes_nothing(fake_home, fake_runner, monkeypatch):
    from loadout import backup, personal_mcp, runner
    monkeypatch.setattr(runner, "would_refuse", lambda cmd: True)
    res = personal_mcp.replace_user_server("srv", {"command": "a"}, {"command": "b"}, backup.Backup())
    assert res.startswith("manual: ")
    assert [c for c in fake_runner.calls if c[:1] == ["claude"]] == []
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_secrets.py`
Expected: FAIL with `AttributeError: module 'loadout.secrets' has no attribute 'rewrite'`

- [ ] **Step 3: Implement** — append to `cli/loadout/secrets.py`:

```python
def rewrite(server: str, cfg: dict, findings: list[Finding], known: dict[str, str]) -> tuple[dict, list[str], list[str]]:
    """Replace each fixable finding's value in a copy of cfg with ${VAR}. known (secrets.env) is updated in place.

    Returns (new config, new secrets.env lines, var names). A name that already holds a different value is
    never reused: _2, _3, ... is appended instead.
    """
    import json

    new = json.loads(json.dumps(cfg))
    lines, names = [], []
    for f in findings:
        var = var_name(f.server, f.key)
        n = 2
        while var in known and known[var] != f.value:
            var = f"{var_name(f.server, f.key)}_{n}"
            n += 1
        if var not in known:
            known[var] = f.value
            lines.append(f"{var}={quote(f.value)}\n")
        new[f.field][f.key] = new[f.field][f.key].replace(f.value, "${" + var + "}")
        names.append(var)
    return new, lines, names


def append_env(path: Path, lines: list[str], bk) -> None:
    """Append to secrets.env; a new file is created 0600 from the start and recorded as created."""
    import os

    if not lines:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_bytes() if path.exists() else b""
    if path.exists():
        bk.save_copy(path, "secrets.env before additions")
    else:
        os.close(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
        bk.record_created(path, "created secrets.env")
    if os.name != "nt":
        os.chmod(path, 0o600)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        if existing and not existing.endswith(b"\n"):
            fh.write("\n")
        fh.writelines(lines)
```

Append to `cli/loadout/personal_mcp.py`:

```python
def replace_user_server(name: str, original: dict, new: dict, bk) -> str:
    """Swap a user-scope server's config. Never leaves the user without the server."""
    remove = ["claude", "mcp", "remove", "-s", "user", name]
    add_new = ["claude", "mcp", "add-json", "-s", "user", name, json.dumps(new)]
    if runner.would_refuse(add_new):  # decide before removing anything
        bk._ensure_root()
        where = runner.write_manual_commands(bk.root, f"mcp {name} (full commands, contains secrets)", [remove, add_new])
        return f"manual: {where}"
    # reverse replay: remove the new server first, then re-add the original
    bk.record_command(f"mcp {name} (original)", ["claude", "mcp", "add-json", "-s", "user", name, json.dumps(original)])
    bk.record_command(f"mcp {name} (remove rewritten)", remove)
    runner.run(remove)
    res = runner.run(add_new)
    if res.ok:
        return "ok"
    back = _add(name, original)
    return redact(f"failed: {res.stderr.strip()} (original re-added: {'ok' if back.ok else 'failed: ' + back.stderr.strip()})")
```

In `cli/loadout/adopt.py`, delete `_open_secrets_file` and replace the body of `fix_secrets` with:

```python
def fix_secrets(findings: list, bk: Backup) -> list[str]:
    from .personal_mcp import replace_user_server

    out = []
    claude_json = load_json(paths.claude_json())
    secrets_path = paths.secrets_file()
    fixable: dict[str, list] = {}
    for f in findings:
        if f.fixable:
            fixable.setdefault(f.server, []).append(f)
        else:
            out.append(f"{f.server}: secret in {f.field} ({f.location}): move it to secrets.env by hand")
    known = secrets.load_env(secrets_path)
    for server, group in fixable.items():
        servers = claude_json.get("mcpServers")
        original = servers.get(server) if isinstance(servers, dict) else None
        if original is None:
            out.append(f"{server}: not found in ~/.claude.json, skipped")
            continue
        if any("\n" in f.value or "\r" in f.value for f in group):
            out.append(f"{server}: a secret value contains a newline; move it to secrets.env by hand (skipped)")
            continue
        cfg, lines, names = secrets.rewrite(server, original, group, known)
        secrets.append_env(secrets_path, lines, bk)
        refs = ", ".join("${" + n + "}" for n in names)
        res = replace_user_server(server, original, cfg, bk)
        if res.startswith("manual: "):
            out.append(f"{server} -> {refs}: not changed in claude (Windows .cmd shim cannot take JSON); "
                       f"secrets.env is updated, run the commands in {res[8:]}")
            continue
        out.append(f"{server} -> {refs}: {res}")
    return out
```

Remove `import os` from `adopt.py` only if nothing else uses it (check with grep).

- [ ] **Step 4: Run all tests**

Run: `uv run --python 3.12 --with pytest pytest -q`
Expected: PASS (existing `fix_secrets` tests in `tests/test_adopt.py` and `tests/test_secrets.py` unchanged and green).

- [ ] **Step 5: Commit**

```bash
git add cli/loadout/secrets.py cli/loadout/personal_mcp.py cli/loadout/adopt.py tests/test_secrets.py
git commit -m "refactor(secrets): share the \${VAR} rewrite and user-server swap with fix_secrets"
```

---

### Task 2: `own.py` foundation and personal-layer-aware `classify`

**Files:**
- Create: `cli/loadout/own.py`
- Modify: `cli/loadout/inventory.py` (`classify`)
- Modify: `cli/loadout/adopt.py` (`GROUP_ORDER`, `GROUP_HELP`, `VERB`, `render_plan`)
- Test: `tests/test_own.py` (new), `tests/test_inventory.py`, `tests/test_adopt.py`

**Interfaces:**
- Produces in `own.py`: `KINDS`, `PERSONAL_REASON`, `LEFT_REASON`, `OWN_REASON`, `decision_key(item) -> str`, `decisions() -> dict[str, str]`, `remember_leave(item) -> None`, `forget(item) -> None`, `is_left(item) -> bool`, `personal_index() -> dict[str, dict]`, `in_personal_layer(item, index) -> str | None` (returns the reason or None), `unmanaged(verdicts, include_left=False) -> list[Verdict]`.
- Produces: verdict action `"own"` (replaces `"unknown"`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_own.py`:

```python
import json

import pytest

from loadout import backup, inventory, own, paths
from fixtures import author_machine


@pytest.fixture
def machine(fake_home, fake_runner):
    author_machine(fake_home)
    return fake_home


def _verdicts():
    return inventory.classify(inventory.collect(with_versions=False))


def _by(verdicts):
    return {(v.item.kind, v.item.name): v for v in verdicts}


def _personal(name, data):
    path = paths.personal_root() / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return path


def test_own_action_replaces_unknown(machine):
    v = _by(_verdicts())
    assert v[("plugin", "mystery@somewhere")].action == "own"
    assert all(x.action != "unknown" for x in v.values())


def test_personal_layer_items_are_keep(machine):
    _personal("settings.json", {"enabledPlugins": {"mystery@somewhere": True},
                                "hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [{"type": "command", "command": "my-own-linter"}]}]}})
    cfg = json.loads((machine / ".claude.json").read_text())["mcpServers"]["omarchy-kb"]
    _personal("mcp.json", {"mcpServers": {"omarchy-kb": cfg}})
    (paths.personal_root() / "skills/my-skill").mkdir(parents=True)
    v = _by(_verdicts())
    for key in [("plugin", "mystery@somewhere"), ("mcp", "omarchy-kb"), ("skill", "my-skill"), ("hook", "PreToolUse:Edit")]:
        assert v[key].action == "keep" and v[key].reason == own.PERSONAL_REASON, key


def test_kit_plugin_reason_is_kit_not_personal(machine):
    assert _by(_verdicts())[("plugin", "superpowers@claude-plugins-official")].reason == "Enabled by the kit."


def test_personal_profile_items_are_keep(machine):
    _personal("profiles/mine.json", {"install": ["mystery@somewhere"]})
    v = _by(_verdicts())[("plugin", "mystery@somewhere")]
    assert v.action == "keep" and "mine" in v.reason


def test_left_items_are_keep_and_listed_with_all(machine):
    item = _by(_verdicts())[("skill", "my-skill")].item
    own.remember_leave(item)
    v = _by(_verdicts())
    assert v[("skill", "my-skill")].action == "keep" and v[("skill", "my-skill")].reason == own.LEFT_REASON
    assert item not in [x.item for x in own.unmanaged(_verdicts())]
    assert item in [x.item for x in own.unmanaged(_verdicts(), include_left=True)]
    own.forget(item)
    assert _by(_verdicts())[("skill", "my-skill")].action == "own"


def test_hook_decision_key_includes_command(machine):
    hook = _by(_verdicts())[("hook", "PreToolUse:Edit")].item
    assert own.decision_key(hook) == "hook:PreToolUse:Edit:my-own-linter"
```

In `tests/test_inventory.py` replace every `.action == "unknown"` with `.action == "own"`. In `tests/test_adopt.py`: line 36 `"unknown" not in actions` → `"own" not in actions`; `test_groups_unknown_removes_and_restores` → rename to `test_groups_own_removes_and_restores` and use `{"own"}`; line 197 `{"remove", "unknown"}` → `{"remove", "own"}`; any `"UNKNOWN"` text assertion → `"YOUR OWN TOOLS"`.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_own.py tests/test_inventory.py tests/test_adopt.py`
Expected: FAIL (`ModuleNotFoundError: loadout.own`, action still `unknown`).

- [ ] **Step 3: Implement**

Create `cli/loadout/own.py`:

```python
"""Your own tools: items loadout does not manage. Record them in the personal layer (global), in a
personal profile (project), leave them on this machine, or remove them.
Spec: docs/superpowers/specs/2026-10-10-adopt-own-tools-design.md
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from . import paths
from .jsonio import load_json, save_json

if TYPE_CHECKING:
    from .inventory import Item, Verdict

KINDS = ("plugin", "marketplace", "mcp", "skill", "hook")
PERSONAL_REASON = "From your personal layer."
LEFT_REASON = "Left on this machine (your choice); change it with `loadout configure set own`."
OWN_REASON = "Not managed by loadout. Choose: global, project, leave or remove."


def decision_key(item: Item) -> str:
    return f"hook:{item.name}:{item.detail}" if item.kind == "hook" else f"{item.kind}:{item.name}"


def _decisions_path():
    return paths.state_dir() / "own-decisions.json"


def decisions() -> dict[str, str]:
    return load_json(_decisions_path())


def remember_leave(item: Item) -> None:
    data = decisions()
    data[decision_key(item)] = "leave"
    save_json(_decisions_path(), data)


def forget(item: Item) -> None:
    data = decisions()
    if data.pop(decision_key(item), None) is not None:
        save_json(_decisions_path(), data)


def is_left(item: Item) -> bool:
    return decisions().get(decision_key(item)) == "leave"


def _hook_commands(settings: dict) -> set[str]:
    hooks = settings.get("hooks")
    out = set()
    for groups in (hooks.values() if isinstance(hooks, dict) else []):
        for group in groups if isinstance(groups, list) else []:
            for hook in group.get("hooks", []) if isinstance(group, dict) else []:
                if isinstance(hook, dict) and isinstance(hook.get("command"), str):
                    out.add(hook["command"])
    return out


def personal_index() -> dict[str, dict]:
    """What the personal layer already holds: {kind: {name: reason}} (hooks keyed by command)."""
    root = paths.personal_root()
    settings = load_json(root / "settings.json")
    index = {k: {} for k in KINDS}
    for pid, on in (settings.get("enabledPlugins") or {}).items():
        if on:
            index["plugin"][pid] = PERSONAL_REASON
    for name in settings.get("extraKnownMarketplaces") or {}:
        index["marketplace"][name] = PERSONAL_REASON
    for name in load_json(root / "mcp.json").get("mcpServers") or {}:
        index["mcp"][name] = PERSONAL_REASON
    skills = root / "skills"
    for entry in (skills.iterdir() if skills.is_dir() else []):
        if entry.is_dir():
            index["skill"][entry.name] = PERSONAL_REASON
    for name in load_json(root / "skills.json"):
        index["skill"][name] = PERSONAL_REASON
    for cmd in _hook_commands(settings):
        index["hook"][cmd] = PERSONAL_REASON
    for path in sorted((root / "profiles").glob("*.json")):
        prof, why = load_json(path), f"In your personal profile {path.stem} (`loadout profile {path.stem}`)."
        for pid in prof.get("install") or []:
            index["plugin"].setdefault(pid, why)
        for name in (prof.get("mcp") or {}).get("mcpServers") or {}:
            index["mcp"].setdefault(name, why)
        for name in prof.get("skills") or []:
            index["skill"].setdefault(name, why)
        for cmd in _hook_commands(prof.get("settings") or {}):
            index["hook"].setdefault(cmd, why)
    return index


def in_personal_layer(item: Item, index: dict[str, dict]) -> str | None:
    if item.kind not in index:
        return None
    return index[item.kind].get(item.detail if item.kind == "hook" else item.name)


def unmanaged(verdicts: list[Verdict], include_left: bool = False) -> list[Verdict]:
    return [v for v in verdicts if v.action == "own" or (include_left and v.action == "keep" and v.reason == LEFT_REASON)]
```

In `cli/loadout/inventory.py` `classify`, replace the setup lines and the `unknown` branch:

```python
def classify(items: list[Item]) -> list[Verdict]:
    from . import own

    kit = load_json(paths.kit_root() / "settings.base.json")
    kit_plugins = {p for p, on in kit.get("enabledPlugins", {}).items() if on}
    kit_markets = set(kit.get("extraKnownMarketplaces", {})) | {"claude-plugins-official"}
    index = own.personal_index()
    left = own.decisions()
    out = []
    for item in items:
        # ... binary and claude-md branches unchanged ...
        if item.kind == "plugin" and item.name in kit_plugins:
            out.append(Verdict(item, "keep", "Enabled by the kit."))
            continue
        if item.kind == "marketplace" and item.name in kit_markets:
            out.append(Verdict(item, "keep", "Declared by the kit."))
            continue
        personal = own.in_personal_layer(item, index)
        if personal:
            out.append(Verdict(item, "keep", personal))
            continue
        if left.get(own.decision_key(item)) == "leave":
            out.append(Verdict(item, "keep", own.LEFT_REASON))
            continue
        entry = catalog.match(item.kind, item.name, item.detail)
        if entry is None:
            out.append(Verdict(item, "own", own.OWN_REASON))
            continue
        # ... rest unchanged ...
```

Remove the now-unused `from .settings_merge import desired_settings` import if nothing else in `inventory.py` uses it.

In `cli/loadout/adopt.py`:

```python
GROUP_ORDER = ["remove", "migrate", "scope-down", "update", "install", "review", "own", "keep"]
# GROUP_HELP: replace the "unknown" entry with
    "own": "not managed by loadout; they stay only on this machine unless you choose.",
# VERB: replace "unknown": "remove" with
    "own": "remove",
```

In `render_plan`, replace the header line with:

```python
        title = "YOUR OWN TOOLS" if group == "own" else group.upper()
        lines.append(f"\n{title} ({len(members)}) — {GROUP_HELP[group]}")
```

- [ ] **Step 4: Run all tests**

Run: `uv run --python 3.12 --with pytest pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cli/loadout/own.py cli/loadout/inventory.py cli/loadout/adopt.py tests/test_own.py tests/test_inventory.py tests/test_adopt.py
git commit -m "feat(adopt): classify personal-layer items as kept and rename unknown to own"
```

---

### Task 3: Link personal skills and hook scripts

**Files:**
- Modify: `cli/loadout/link.py` (`LINKS`)
- Modify: `cli/loadout/check.py` (`_links`)
- Test: `tests/test_link_backup.py`, `tests/test_check.py`

**Interfaces:**
- Produces: `link.LINKS()` additionally returns `(~/.claude/skills/<name>, <personal>/skills/<name>)` for each directory, `(~/.claude/skills/<name>, <target>)` for each `skills.json` entry whose target exists, and `(~/.claude/hooks/personal, <personal>/hooks)`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_link_backup.py`)

```python
def test_links_personal_skills_pointers_and_hooks(fake_home):
    from loadout import backup, link, paths
    personal = paths.personal_root()
    (personal / "rules").mkdir(parents=True)
    (personal / "skills/notes").mkdir(parents=True)
    (personal / "skills/notes/SKILL.md").write_text("x")
    (personal / "hooks").mkdir()
    shared = fake_home / "shared/omarchy"
    shared.mkdir(parents=True)
    (personal / "skills.json").write_text(json.dumps({"omarchy": str(shared), "gone": str(fake_home / "nope")}))
    link.link_all(backup.Backup())
    skills = fake_home / ".claude/skills"
    assert (skills / "notes/SKILL.md").read_text() == "x"
    assert (skills / "omarchy").resolve() == shared.resolve()
    assert not (skills / "gone").exists()
    assert (fake_home / ".claude/hooks/personal").resolve() == (personal / "hooks").resolve()
```

Append to `tests/test_check.py`:

```python
def test_check_links_ignores_missing_personal_hooks_dir(fake_home, fake_runner):
    _setup_ok(fake_home)
    results = _by(check.run_checks())
    assert not any(name.startswith("link hooks/") for name in results)
    assert results["link rules/personal"].ok
```

(If `test_link_backup.py` does not import `json`, add `import json` at the top.)

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_link_backup.py tests/test_check.py`
Expected: FAIL (`~/.claude/skills/notes` missing).

- [ ] **Step 3: Implement** — replace `LINKS` in `cli/loadout/link.py`:

```python
def LINKS() -> list[tuple[Path, Path]]:
    from .jsonio import InvalidJSON, load_json

    rules = paths.claude_home() / "rules"
    personal = paths.personal_root()
    out = [
        (rules / "loadout", paths.kit_root() / "rules"),
        (rules / "personal", personal / "rules"),
    ]
    skills = paths.claude_home() / "skills"
    if (personal / "skills").is_dir():
        out += [(skills / p.name, p) for p in sorted((personal / "skills").iterdir()) if p.is_dir()]
    try:
        pointers = load_json(personal / "skills.json")
    except InvalidJSON:
        pointers = {}  # reported by loadout check via the personal layer's own files; never crash linking
    for name, target in sorted(pointers.items()):
        if isinstance(target, str) and Path(target).expanduser().is_dir():
            out.append((skills / name, Path(target).expanduser()))
    out.append((paths.claude_home() / "hooks" / "personal", personal / "hooks"))
    return out
```

In `cli/loadout/check.py` `_links`, skip pairs whose source does not exist and label by parent folder:

```python
def _links() -> list[CheckResult]:
    out = []
    for dest, src in link.LINKS():
        if not src.exists():
            continue  # nothing to link (e.g. no personal hooks/); _link_one skips it too
        name = f"link {dest.parent.name}/{dest.name}"
        ...  # rest unchanged
```

- [ ] **Step 4: Run all tests**

Run: `uv run --python 3.12 --with pytest pytest -q`
Expected: PASS (the existing names `link rules/loadout` and `link rules/personal` are unchanged by the new label format).

- [ ] **Step 5: Commit**

```bash
git add cli/loadout/link.py cli/loadout/check.py tests/test_link_backup.py tests/test_check.py
git commit -m "feat(link): link personal-layer skills and hook scripts into ~/.claude"
```

---

### Task 4: Profile `skills`

**Files:**
- Modify: `cli/loadout/profiles.py`
- Modify: `cli/loadout/project.py` (`add_profile`)
- Test: `tests/test_project.py`

**Interfaces:**
- Produces: `Profile.skills: list[str]`; `profiles.copy_skills(profile: Profile, project: Path, dry_run: bool = False) -> list[str]` (messages). Skill sources: `<personal>/profiles/skills/<name>/`, then `<kit>/profiles/skills/<name>/`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_project.py`; reuse its existing imports, add `json` and `paths` if missing)

```python
def test_profile_skills_are_copied_and_never_overwritten(fake_home, fake_runner, tmp_path):
    personal = paths.personal_root()
    (personal / "profiles/skills/notes").mkdir(parents=True)
    (personal / "profiles/skills/notes/SKILL.md").write_text("new")
    (personal / "profiles/mine.json").write_text(json.dumps({"description": "m", "skills": ["notes", "missing"]}))
    repo = tmp_path / "repo"
    (repo / ".claude/skills/kept").mkdir(parents=True)
    project.add_profile(repo, "mine", install=False)
    assert (repo / ".claude/skills/notes/SKILL.md").read_text() == "new"
    (repo / ".claude/skills/notes/SKILL.md").write_text("edited")
    project.add_profile(repo, "mine", install=False)
    assert (repo / ".claude/skills/notes/SKILL.md").read_text() == "edited"


def test_profile_skill_messages(fake_home, tmp_path):
    personal = paths.personal_root()
    (personal / "profiles").mkdir(parents=True)
    (personal / "profiles/mine.json").write_text(json.dumps({"skills": ["missing"]}))
    from loadout import profiles
    msgs = profiles.copy_skills(profiles.load_profile("mine"), tmp_path)
    assert msgs == ["skill missing: not found in profiles/skills/ (personal layer or kit)"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_project.py`
Expected: FAIL (`Profile` has no `skills`).

- [ ] **Step 3: Implement** — in `cli/loadout/profiles.py` add `import shutil`, the field `skills: list = field(default_factory=list)` to `Profile`, `skills=data.get("skills", []),` in `load_profile`, and:

```python
def _skill_source(name: str) -> Path | None:
    for d in _dirs():
        candidate = d / "skills" / name
        if candidate.is_dir():
            return candidate
    return None


def copy_skills(profile: Profile, project: Path, dry_run: bool = False) -> list[str]:
    """Copy the profile's skills into the repo. An existing skill folder is never overwritten."""
    out = []
    for name in profile.skills:
        src, dest = _skill_source(name), project / ".claude" / "skills" / name
        if src is None:
            out.append(f"skill {name}: not found in profiles/skills/ (personal layer or kit)")
        elif dest.exists() or dest.is_symlink():
            out.append(f"skill {name}: {dest} exists, left as is")
        elif dry_run:
            out.append(f"would copy skill {name} -> {dest}")
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(src, dest, symlinks=True)
            out.append(f"copied skill {name} -> {dest}")
    return out
```

In `cli/loadout/project.py` `add_profile`, after the `apply_profile` / dry-run block:

```python
    for line in profiles.copy_skills(prof, project, dry_run=dry_run):
        print(line)
```

- [ ] **Step 4: Run all tests**

Run: `uv run --python 3.12 --with pytest pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cli/loadout/profiles.py cli/loadout/project.py tests/test_project.py
git commit -m "feat(profiles): profiles can carry skills that are copied into the repo"
```

---

### Task 5: Record an item globally

**Files:**
- Modify: `cli/loadout/own.py` (append)
- Test: `tests/test_own.py` (append)

**Interfaces:**
- Consumes: `secrets.rewrite`, `secrets.append_env`, `personal_mcp.replace_user_server` (Task 1); `own.personal_index` (Task 2); `link.link_all` (Task 3).
- Produces:
  - `class Collision(Exception)`
  - `@dataclass Recorded: ok: bool; lines: list[str]; machine: Callable[[], list[str]] | None = None` — `machine` is the change to this machine, run by `adopt.apply_own` after all removals.
  - `record_global(v: Verdict, bk) -> Recorded`
  - helpers used again in Task 6: `_edit_json(path, bk, label, change, seed=None)`, `_add_market(data, name)`, `_secret_free(name, cfg) -> tuple[dict, list[str]]`, `_portable_hook(hook, bk) -> tuple[dict, list[str]]`, `_find_hook(data, event, matcher, command) -> tuple[int, int] | None`, `_same_tree(a, b) -> bool`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_own.py`)

```python
def _v(kind, name):
    return _by(_verdicts())[(kind, name)]


def _run_machine(rec):
    return rec.machine() if rec.machine else []


def test_global_plugin_records_plugin_and_marketplace(machine):
    (machine / ".claude/plugins/known_marketplaces.json").write_text(json.dumps({
        "somewhere": {"source": {"source": "github", "repo": "me/somewhere"}}}))
    bk = backup.Backup()
    rec = own.record_global(_v("plugin", "mystery@somewhere"), bk)
    assert rec.ok
    data = json.loads((paths.personal_root() / "settings.json").read_text())
    assert data["enabledPlugins"]["mystery@somewhere"] is True
    assert data["extraKnownMarketplaces"]["somewhere"] == {"source": {"source": "github", "repo": "me/somewhere"}}
    assert _v("plugin", "mystery@somewhere").action == "keep"


def test_global_plugin_marketplace_collision_skips(machine):
    (machine / ".claude/plugins/known_marketplaces.json").write_text(json.dumps({
        "somewhere": {"source": {"source": "github", "repo": "me/somewhere"}}}))
    _personal("settings.json", {"extraKnownMarketplaces": {"somewhere": {"source": {"source": "github", "repo": "other/x"}}}})
    rec = own.record_global(_v("plugin", "mystery@somewhere"), backup.Backup())
    assert not rec.ok and "skipped" in rec.lines[0]
    assert "enabledPlugins" not in json.loads((paths.personal_root() / "settings.json").read_text())


def test_global_mcp_plain_server_is_recorded_and_managed(machine, fake_runner):
    from loadout import personal_mcp
    rec = own.record_global(_v("mcp", "omarchy-kb"), backup.Backup())
    assert rec.ok
    _run_machine(rec)
    cfg = json.loads((machine / ".claude.json").read_text())["mcpServers"]["omarchy-kb"]
    assert json.loads((paths.personal_root() / "mcp.json").read_text())["mcpServers"]["omarchy-kb"] == cfg
    assert json.loads((paths.state_dir() / "managed-mcp.json").read_text())["mcpServers"]["omarchy-kb"] == cfg
    fake_runner.calls.clear()
    assert personal_mcp.apply_mcp() == []           # no "skipped, not managed" and no re-add
    assert fake_runner.calls == []


def test_global_mcp_secret_goes_to_secrets_env(machine, fake_runner):
    cfg = json.loads((machine / ".claude.json").read_text())
    cfg["mcpServers"]["mine"] = {"command": "x", "env": {"API_KEY": "k" * 20}}
    (machine / ".claude.json").write_text(json.dumps(cfg))
    rec = own.record_global(_v("mcp", "mine"), backup.Backup())
    _run_machine(rec)
    recorded = (paths.personal_root() / "mcp.json").read_text()
    assert "k" * 20 not in recorded and "${MINE_API_KEY}" in recorded
    assert "MINE_API_KEY=" in paths.secrets_file().read_text()
    add = [c for c in fake_runner.calls if c[:3] == ["claude", "mcp", "add-json"]][-1]
    assert "${MINE_API_KEY}" in add[-1]


def _as_own(kind, name):
    return inventory.Verdict(_v(kind, name).item, "own", "")


def _hook(detail):
    return inventory.Verdict(next(x.item for x in _verdicts() if x.item.kind == "hook" and x.item.detail == detail), "own", "")


def test_global_mcp_unfixable_secret_blocked(machine, fake_runner):
    rec = own.record_global(_as_own("mcp", "github-server"), backup.Backup())
    assert not rec.ok and "by hand" in rec.lines[0]
    assert not (paths.personal_root() / "mcp.json").exists()


def test_global_skill_dir_restore(machine):
    (machine / ".claude/skills/my-skill/SKILL.md").write_text("mine")
    bk = backup.Backup()
    rec = own.record_global(_v("skill", "my-skill"), bk)
    _run_machine(rec)
    from loadout import link
    link.link_all(bk)
    assert (paths.personal_root() / "skills/my-skill/SKILL.md").read_text() == "mine"
    assert (machine / ".claude/skills/my-skill").is_symlink()
    backup.restore(bk.root)
    restored = machine / ".claude/skills/my-skill"
    assert not restored.is_symlink() and (restored / "SKILL.md").read_text() == "mine"


def test_global_skill_symlink_becomes_pointer(machine):
    skills = machine / ".claude/skills"
    shared = machine / "shared/omarchy"
    shared.mkdir(parents=True)
    (skills / "omarchy").symlink_to(shared)
    rec = own.record_global(_v("skill", "omarchy"), backup.Backup())
    assert rec.ok and rec.machine is None
    assert json.loads((paths.personal_root() / "skills.json").read_text()) == {"omarchy": str(shared)}


def _settings():
    return json.loads((paths.claude_home() / "settings.json").read_text())


def test_global_hook_plain_command(machine):
    rec = own.record_global(_v("hook", "PreToolUse:Edit"), backup.Backup())
    _run_machine(rec)
    groups = json.loads((paths.personal_root() / "settings.json").read_text())["hooks"]["PreToolUse"]
    assert groups == [{"matcher": "Edit", "hooks": [{"type": "command", "command": "my-own-linter"}]}]


def test_global_hook_local_script_copied_and_rewritten(machine):
    script = machine / "bin/notify.sh"
    script.parent.mkdir()
    script.write_text("#!/bin/sh\necho hi\n")
    data = _settings()
    data["hooks"]["Notification"] = [{"hooks": [{"type": "command", "command": f"bash '{script}' --loud"}]}]
    (paths.claude_home() / "settings.json").write_text(json.dumps(data))
    rec = own.record_global(_v("hook", "Notification:"), backup.Backup())
    _run_machine(rec)
    assert (paths.personal_root() / "hooks/notify.sh").read_text() == script.read_text()
    assert script.exists()   # original stays
    want = 'bash "$HOME/.claude/hooks/personal/notify.sh" --loud'
    personal = json.loads((paths.personal_root() / "settings.json").read_text())["hooks"]["Notification"]
    assert personal[0]["hooks"][0]["command"] == want
    assert _settings()["hooks"]["Notification"][0]["hooks"][0]["command"] == want


def test_global_hook_exec_form_recorded_as_is(machine):
    data = _settings()
    data["hooks"]["Stop"] = [{"hooks": [{"type": "command", "command": "x", "args": ["/opt/x"]}]}]
    (paths.claude_home() / "settings.json").write_text(json.dumps(data))
    rec = own.record_global(_hook("x"), backup.Backup())
    assert rec.ok and any("exec form" in line for line in rec.lines)


def test_global_hook_no_duplicate_after_merge(machine):
    from loadout import settings_merge
    data = _settings()
    data["hooks"]["PreToolUse"][3]["hooks"].append({"type": "command", "command": "other"})  # the Edit group
    (paths.claude_home() / "settings.json").write_text(json.dumps(data))
    rec = own.record_global(_hook("my-own-linter"), backup.Backup())
    _run_machine(rec)
    settings_merge.apply_settings()
    commands = [h["command"] for g in _settings()["hooks"]["PreToolUse"] for h in g["hooks"]]
    assert commands.count("my-own-linter") == 1
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_own.py`
Expected: FAIL with `AttributeError: module 'loadout.own' has no attribute 'record_global'`

- [ ] **Step 3: Implement** — add to the imports of `cli/loadout/own.py`:

```python
import filecmp
import os
import shlex
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import paths, personal_mcp, secrets
from .secrets import redact
```

Append:

```python
class Collision(Exception):
    """The personal layer already holds something different under this name: skip, never overwrite."""


@dataclass
class Recorded:
    ok: bool
    lines: list[str] = field(default_factory=list)
    machine: Callable[[], list[str]] | None = None  # run by adopt.apply_own after all removals


def _edit_json(path: Path, bk, label: str, change: Callable[[dict], None], seed: dict | None = None) -> None:
    """Load (or start from seed), apply change (which may raise Collision before anything is written), back up, save."""
    exists = path.exists()
    data = load_json(path) if exists else json.loads(json.dumps(seed or {}))
    before = json.dumps(data, sort_keys=True)
    change(data)
    if json.dumps(data, sort_keys=True) == before and exists:
        return
    if exists:
        bk.save_copy(path, label)
    else:
        bk.record_created(path, label)
    save_json(path, data)


def _personal_settings() -> Path:
    return paths.personal_root() / "settings.json"


def _kit_markets() -> set[str]:
    kit = load_json(paths.kit_root() / "settings.base.json")
    return set(kit.get("extraKnownMarketplaces", {})) | {"claude-plugins-official"}


def _market_source(name: str) -> dict | None:
    cfg = load_json(paths.claude_home() / "plugins" / "known_marketplaces.json").get(name)
    src = cfg.get("source") if isinstance(cfg, dict) else None
    return src if isinstance(src, dict) and src else None


def _add_market(data: dict, name: str) -> None:
    """Declare a marketplace in a settings dict, unless the kit already declares it."""
    if not name or name in _kit_markets():
        return
    src = _market_source(name)
    if src is None:
        raise Collision(f"marketplace {name}: no source is known on this machine")
    markets = data.setdefault("extraKnownMarketplaces", {})
    have = markets.get(name)
    if have is not None and have.get("source") != src:
        raise Collision(f"marketplace {name} already exists with a different source")
    markets[name] = {"source": src}


def _secret_free(name: str, cfg: dict) -> tuple[dict, list[str]]:
    """The config with secrets as ${VAR}, plus the secrets.env lines to append. Refuses unfixable secrets."""
    found = secrets.scan({"mcpServers": {name: cfg}})
    blocked = [f for f in found if not f.fixable or "\n" in f.value or "\r" in f.value]
    if blocked:
        raise Collision(f"mcp {name}: a secret in {blocked[0].field} cannot be moved automatically; "
                        f"move it to {paths.secrets_file()} by hand first")
    new, lines, _ = secrets.rewrite(name, cfg, found, secrets.load_env(paths.secrets_file()))
    return new, lines


def _same_tree(a: Path, b: Path) -> bool:
    cmp = filecmp.dircmp(a, b)
    if cmp.left_only or cmp.right_only or cmp.funny_files:
        return False
    _, mismatch, errors = filecmp.cmpfiles(a, b, cmp.common_files, shallow=False)
    return not mismatch and not errors and all(_same_tree(a / d, b / d) for d in cmp.common_dirs)


def _copy_tree(src: Path, dest: Path, bk, label: str) -> None:
    if dest.exists():
        if not _same_tree(src, dest):
            raise Collision(f"{dest.name} already exists in {dest.parent} with different content")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    bk.record_created(dest, label)
    shutil.copytree(src, dest, symlinks=True)


def _under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


def _portable_hook(hook: dict, bk) -> tuple[dict, list[str]]:
    """Copy a local script the hook runs into <personal>/hooks/ and point the command at the linked copy."""
    if "args" in hook:
        return hook, ["note: exec-form hook (args) recorded as is; it works only where its paths exist"]
    cmd = hook.get("command")
    if not isinstance(cmd, str):
        return hook, []
    try:
        tokens = shlex.split(cmd)
    except ValueError:
        return hook, []
    for tok in tokens:
        p = Path(os.path.expandvars(os.path.expanduser(tok)))
        if not p.is_absolute() or not p.is_file():
            continue
        if _under(p, paths.kit_root()) or _under(p, paths.personal_root()):
            return hook, []
        if not _under(p, paths.home()):
            return hook, [f"note: {tok} is outside your home folder; the hook works only where it exists"]
        dest = paths.personal_root() / "hooks" / p.name
        if dest.exists():
            if not filecmp.cmp(dest, p, shallow=False):
                raise Collision(f"hook script {p.name} already exists in {dest.parent} with different content")
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            bk.record_created(dest, f"hook script {p.name} copied into the personal layer")
            shutil.copy2(p, dest)
        new = f'"$HOME/.claude/hooks/personal/{p.name}"'
        for raw in (f"'{tok}'", f'"{tok}"', tok):
            if raw in cmd:
                cmd = cmd.replace(raw, new, 1)
                break
        return {**hook, "command": cmd}, [f"hook script {p.name} copied to {dest} (only this file; copy files it needs next to it by hand)"]
    return hook, []


def _find_hook(data: dict, event: str, matcher: str, command: str) -> tuple[int, int] | None:
    for gi, group in enumerate((data.get("hooks") or {}).get(event) or []):
        if not isinstance(group, dict) or group.get("matcher", "") != matcher:
            continue
        for hi, hook in enumerate(group.get("hooks") or []):
            if isinstance(hook, dict) and hook.get("command") == command:
                return gi, hi
    return None


def _hook_group(v: Verdict, bk) -> tuple[str, dict, list[str]]:
    """(event, single-hook group with a portable command, notes) for a hook verdict."""
    event = v.item.extra["event"]
    matcher = v.item.name[len(event) + 1:]
    data = load_json(paths.claude_home() / "settings.json")
    found = _find_hook(data, event, matcher, v.item.detail)
    if found is None:
        raise Collision(f"hook {v.item.name}: changed in ~/.claude/settings.json since the scan; run adopt again")
    gi, hi = found
    group = data["hooks"][event][gi]
    hook, notes = _portable_hook(group["hooks"][hi], bk)
    base = {k: val for k, val in group.items() if k != "hooks"}
    return event, {**base, "hooks": [hook]}, notes


def _regroup_machine_hook(v: Verdict, event: str, group: dict, bk) -> list[str]:
    """Take the hook out of its group in ~/.claude/settings.json and add it back as exactly `group`,
    so the list-union merge with the personal layer does not run it twice."""
    path = paths.claude_home() / "settings.json"
    matcher = v.item.name[len(event) + 1:]

    def change(data):
        found = _find_hook(data, event, matcher, v.item.detail)
        groups = data["hooks"][event]
        if found is not None:
            gi, hi = found
            rest = [h for i, h in enumerate(groups[gi]["hooks"]) if i != hi]
            if rest:
                groups[gi] = {**groups[gi], "hooks": rest}
            else:
                groups.pop(gi)
        if group not in groups:
            groups.append(group)

    _edit_json(path, bk, f"settings.json before regrouping hook {v.item.name}", change)
    return [f"hook {v.item.name}: now managed through your personal layer"]


def record_global(v: Verdict, bk) -> Recorded:
    item = v.item
    try:
        if item.kind == "plugin":
            def change(data):
                data.setdefault("enabledPlugins", {})[item.name] = True
                _add_market(data, item.name.split("@", 1)[1] if "@" in item.name else "")
            _edit_json(_personal_settings(), bk, f"personal settings.json before recording {item.name}", change)
            return Recorded(True, [f"plugin {item.name}: recorded in {_personal_settings()} (other machines install it at the next Claude Code start)"])
        if item.kind == "marketplace":
            _edit_json(_personal_settings(), bk, f"personal settings.json before recording {item.name}",
                       lambda data: _add_market(data, item.name))
            return Recorded(True, [f"marketplace {item.name}: recorded in {_personal_settings()}"])
        if item.kind == "mcp":
            return _global_mcp(v, bk)
        if item.kind == "skill":
            return _global_skill(v, bk)
        if item.kind == "hook":
            event, group, notes = _hook_group(v, bk)
            def change(data):
                groups = data.setdefault("hooks", {}).setdefault(event, [])
                if group not in groups:
                    groups.append(group)
            _edit_json(_personal_settings(), bk, f"personal settings.json before recording hook {item.name}", change)
            return Recorded(True, [f"hook {item.name}: recorded in {_personal_settings()}", *notes],
                            lambda: _regroup_machine_hook(v, event, group, bk))
    except Collision as exc:
        return Recorded(False, [redact(f"skipped: {exc}")])
    raise ValueError(f"{item.kind} {item.name}: global is not available for this kind")


def _global_mcp(v: Verdict, bk) -> Recorded:
    name, original = v.item.name, v.item.extra.get("config", {})
    if v.item.location != "~/.claude.json":
        raise Collision(f"mcp {name}: only user-scope servers in ~/.claude.json can be recorded")
    new, lines = _secret_free(name, original)
    path = paths.personal_root() / "mcp.json"

    def change(data):
        servers = data.setdefault("mcpServers", {})
        if name in servers and servers[name] != new:
            raise Collision(f"{name} already exists in {path} with a different config")
        servers[name] = new

    _edit_json(path, bk, f"personal mcp.json before recording {name}", change)
    secrets.append_env(paths.secrets_file(), lines, bk)

    def machine() -> list[str]:
        out = []
        if new != original:
            res = personal_mcp.replace_user_server(name, original, new, bk)
            out.append(redact(f"mcp {name}: " + (f"run the commands in {res[8:]} by hand (Windows .cmd shim)"
                                                 if res.startswith("manual: ") else res)))
        snap = paths.state_dir() / "managed-mcp.json"
        _edit_json(snap, bk, "managed-mcp.json before recording a server",
                   lambda d: d.setdefault("mcpServers", {}).__setitem__(name, new))
        return out

    return Recorded(True, [f"mcp {name}: recorded in {path}" + (" (secrets in secrets.env)" if lines else "")], machine)


def _global_skill(v: Verdict, bk) -> Recorded:
    name, src = v.item.name, Path(v.item.location)
    if src.is_symlink():
        target = os.readlink(src)
        path = paths.personal_root() / "skills.json"

        def change(data):
            if name in data and data[name] != target:
                raise Collision(f"{name} already exists in {path} with a different target")
            data[name] = target

        _edit_json(path, bk, f"skills.json before recording {name}", change)
        return Recorded(True, [f"skill {name}: recorded as a link to {target} (linked only where that folder exists)"])
    dest = paths.personal_root() / "skills" / name
    _copy_tree(src, dest, bk, f"skill {name} copied into the personal layer")

    def machine() -> list[str]:
        bk.move(src, f"skill {name} (replaced by a link to your personal layer)", replace=True)
        return [f"skill {name}: moved to {dest}; ~/.claude/skills/{name} links to it"]

    return Recorded(True, [f"skill {name}: recorded in {dest}"], machine)
```

Also add `import json` at the top of `own.py`. `_as_own` wraps a catalog item (here `github-server`, a `remove` item with a secret in `args`) as an `own` verdict on purpose, to reach the blocked-secret path.

- [ ] **Step 4: Run all tests**

Run: `uv run --python 3.12 --with pytest pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cli/loadout/own.py tests/test_own.py
git commit -m "feat(own): record plugins, marketplaces, MCP servers, skills and hooks in the personal layer"
```

---

### Task 6: Record an item into a personal profile

**Files:**
- Modify: `cli/loadout/own.py` (append)
- Test: `tests/test_own.py` (append)

**Interfaces:**
- Consumes: Task 5 helpers.
- Produces: `PROFILE_NAME` (regex `^[a-z0-9][a-z0-9_-]*$`), `profile_note(name) -> str | None` (warning when a kit profile of that name exists and no personal one), `record_project(v: Verdict, profile: str, bk) -> Recorded` (personal layer only; the machine step is the existing removal, done by `adopt.apply_own`).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_own.py`)

```python
def _profile(name):
    return json.loads((paths.personal_root() / f"profiles/{name}.json").read_text())


def test_project_plugin(machine):
    (machine / ".claude/plugins/known_marketplaces.json").write_text(json.dumps({
        "somewhere": {"source": {"source": "github", "repo": "me/somewhere"}}}))
    rec = own.record_project(_v("plugin", "mystery@somewhere"), "mine", backup.Backup())
    assert rec.ok and rec.machine is None
    prof = _profile("mine")
    assert prof["install"] == ["mystery@somewhere"]
    assert prof["settings"]["enabledPlugins"] == {"mystery@somewhere": True}
    assert "somewhere" in prof["settings"]["extraKnownMarketplaces"]


def test_project_mcp_rewrites_secret(machine):
    cfg = json.loads((machine / ".claude.json").read_text())
    cfg["mcpServers"]["mine"] = {"command": "x", "env": {"API_KEY": "k" * 20}}
    (machine / ".claude.json").write_text(json.dumps(cfg))
    own.record_project(_v("mcp", "mine"), "mine", backup.Backup())
    text = (paths.personal_root() / "profiles/mine.json").read_text()
    assert "${MINE_API_KEY}" in text and "k" * 20 not in text


def test_project_skill_goes_to_profile_skills(machine):
    (machine / ".claude/skills/my-skill/SKILL.md").write_text("mine")
    own.record_project(_v("skill", "my-skill"), "mine", backup.Backup())
    assert (paths.personal_root() / "profiles/skills/my-skill/SKILL.md").read_text() == "mine"
    assert not (paths.personal_root() / "skills/my-skill").exists()   # not linked globally
    assert _profile("mine")["skills"] == ["my-skill"]


def test_project_hook(machine):
    own.record_project(_v("hook", "PreToolUse:Edit"), "mine", backup.Backup())
    assert _profile("mine")["settings"]["hooks"]["PreToolUse"] == [
        {"matcher": "Edit", "hooks": [{"type": "command", "command": "my-own-linter"}]}]


def test_project_on_kit_profile_name_starts_from_kit_copy(machine, kit_root):
    assert own.profile_note("db")
    own.record_project(_v("hook", "PreToolUse:Edit"), "db", backup.Backup())
    kit = json.loads((kit_root / "profiles/db.json").read_text())
    assert _profile("db")["mcp"] == kit["mcp"]


def test_project_bad_profile_name(machine):
    with pytest.raises(ValueError):
        own.record_project(_v("hook", "PreToolUse:Edit"), "../evil", backup.Backup())


def test_project_not_offered_for_marketplace(machine):
    with pytest.raises(ValueError):
        own.record_project(_as_own("marketplace", "severity1-marketplace"), "mine", backup.Backup())
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_own.py`
Expected: FAIL with `AttributeError: ... 'record_project'`

- [ ] **Step 3: Implement** — add `import re` to the imports and append to `cli/loadout/own.py`:

```python
PROFILE_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def _profile_path(name: str) -> Path:
    return paths.personal_root() / "profiles" / f"{name}.json"


def profile_note(name: str) -> str | None:
    kit = paths.kit_root() / "profiles" / f"{name}.json"
    if kit.exists() and not _profile_path(name).exists():
        return (f"note: '{name}' is a kit profile; your personal '{name}' starts as a copy of it "
                f"and replaces it for you")
    return None


def _edit_profile(name: str, bk, change: Callable[[dict], None]) -> None:
    kit = paths.kit_root() / "profiles" / f"{name}.json"
    seed = load_json(kit) if kit.exists() else {"description": f"Personal profile {name} (made by loadout adopt)"}
    _edit_json(_profile_path(name), bk, f"personal profile {name} before adding an item", change, seed=seed)


def _append_once(lst: list, value) -> None:
    if value not in lst:
        lst.append(value)


def record_project(v: Verdict, profile: str, bk) -> Recorded:
    item = v.item
    if not PROFILE_NAME.match(profile):
        raise ValueError(f"profile name '{profile}': use lowercase letters, digits, - and _")
    if "project" not in options(item):
        raise ValueError(f"{item.kind} {item.name}: project is not available for this item")
    where = f"personal profile {profile} ({_profile_path(profile)})"
    try:
        if item.kind == "plugin":
            def change(data):
                _append_once(data.setdefault("install", []), item.name)
                settings = data.setdefault("settings", {})
                settings.setdefault("enabledPlugins", {})[item.name] = True
                _add_market(settings, item.name.split("@", 1)[1] if "@" in item.name else "")
            _edit_profile(profile, bk, change)
        elif item.kind == "mcp":
            new, lines = _secret_free(item.name, item.extra.get("config", {}))

            def change(data):
                servers = data.setdefault("mcp", {}).setdefault("mcpServers", {})
                if item.name in servers and servers[item.name] != new:
                    raise Collision(f"{item.name} already exists in {where} with a different config")
                servers[item.name] = new
            _edit_profile(profile, bk, change)
            secrets.append_env(paths.secrets_file(), lines, bk)
        elif item.kind == "skill":
            _copy_tree(Path(item.location), paths.personal_root() / "profiles" / "skills" / item.name, bk,
                       f"skill {item.name} copied into the personal profiles")
            _edit_profile(profile, bk, lambda data: _append_once(data.setdefault("skills", []), item.name))
        elif item.kind == "hook":
            event, group, notes = _hook_group(v, bk)
            _edit_profile(profile, bk, lambda data: _append_once(
                data.setdefault("settings", {}).setdefault("hooks", {}).setdefault(event, []), group))
            return Recorded(True, [f"hook {item.name}: recorded in {where}", *notes])
    except Collision as exc:
        return Recorded(False, [redact(f"skipped: {exc}")])
    return Recorded(True, [f"{item.kind} {item.name}: recorded in {where}"])
```

`options` is defined in Task 7; to keep this task self-contained, add it now (Task 7 tests it further):

```python
def options(item: Item) -> list[str]:
    """Choices that apply to this item, in prompt order."""
    if item.kind == "mcp" and item.location != "~/.claude.json":
        return ["leave", "remove"]
    if item.kind == "marketplace" or (item.kind == "skill" and Path(item.location).is_symlink()):
        return ["global", "leave", "remove"]
    return ["global", "project", "leave", "remove"]
```

- [ ] **Step 4: Run all tests**

Run: `uv run --python 3.12 --with pytest pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cli/loadout/own.py tests/test_own.py
git commit -m "feat(own): record items into a personal profile"
```

---

### Task 7: Choices, prompts and `adopt.apply_own`

**Files:**
- Modify: `cli/loadout/own.py` (append)
- Modify: `cli/loadout/adopt.py` (`select`, new `apply_own`)
- Test: `tests/test_own.py`, `tests/test_adopt.py` (append)

**Interfaces:**
- Produces in `own.py`: `@dataclass(frozen=True) Choice(action: str, profile: str = "")`, `parse_choice(text) -> Choice`, `parse_spec(spec: str) -> list[tuple[str | None, str, Choice]]` (kind or None, name, choice), `resolve(entries, verdicts) -> list[tuple[Verdict, Choice]]`, `ask_choices(verdicts, ask) -> list[tuple[Verdict, Choice]]`, `candidate_repos(item) -> list[Path]`.
- Produces in `adopt.py`: `select(..., keep_global: list | None = None)`; `apply_own(pairs: list[tuple[Verdict, Choice]], bk, others: list[Verdict] = (), ask=..., confirm_cmds=True) -> tuple[list[str], dict[str, list[Item]]]` (lines, {profile: items recorded into it}).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_own.py`:

```python
def test_parse_spec_and_choice():
    assert own.parse_spec("foo@bar=global, hook:PreToolUse:Edit=project:mine,x=leave") == [
        (None, "foo@bar", own.Choice("global")),
        ("hook", "PreToolUse:Edit", own.Choice("project", "mine")),
        (None, "x", own.Choice("leave"))]
    for bad in ("x", "x=", "x=keep", "x=project", "x=project:../a"):
        with pytest.raises(ValueError):
            own.parse_spec(bad)


def test_resolve_errors(machine):
    vs = _verdicts()
    with pytest.raises(ValueError, match="no unmanaged item"):
        own.resolve(own.parse_spec("nothing=leave"), vs)
    with pytest.raises(ValueError, match="not available"):
        own.resolve(own.parse_spec("severity1-marketplace=project:x"), vs)


def test_resolve_ambiguous_needs_kind(machine):
    (machine / ".claude/skills/omarchy-kb").mkdir()
    vs = _verdicts()
    with pytest.raises(ValueError, match="mcp:omarchy-kb"):
        own.resolve(own.parse_spec("omarchy-kb=leave"), vs)
    assert len(own.resolve(own.parse_spec("skill:omarchy-kb=leave"), vs)) == 1


def test_resolve_allows_keep_global_for_scope_down_plugin(machine):
    pairs = own.resolve(own.parse_spec("sonarqube@claude-plugins-official=global"), _verdicts())
    assert pairs[0][1] == own.Choice("global")
    with pytest.raises(ValueError):
        own.resolve(own.parse_spec("sonarqube@claude-plugins-official=leave"), _verdicts())


def test_ask_choices_leave_all_is_default(machine):
    vs = own.unmanaged(_verdicts())
    pairs = own.ask_choices(vs, ask=lambda q: "")
    assert {c.action for _, c in pairs} == {"leave"} and len(pairs) == len(vs)


def test_ask_choices_each(machine):
    vs = [v for v in own.unmanaged(_verdicts()) if v.item.name in ("mystery@somewhere", "my-skill")]
    answers = iter(["c", "p", "mine", "g"])
    pairs = own.ask_choices(vs, ask=lambda q: next(answers))
    got = {v.item.name: c for v, c in pairs}
    assert got == {"mystery@somewhere": own.Choice("project", "mine"), "my-skill": own.Choice("global")}


def test_candidate_repos(machine):
    repo = machine / "code/app"
    repo.mkdir(parents=True)
    (repo / ".mcp.json").write_text(json.dumps({"mcpServers": {"omarchy-kb": {}}}))
    cfg = json.loads((machine / ".claude.json").read_text())
    cfg["projects"] = {str(repo): {}, str(machine / "code/gone"): {}}
    (machine / ".claude.json").write_text(json.dumps(cfg))
    assert own.candidate_repos(_v("mcp", "omarchy-kb").item) == [repo]
```

Append to `tests/test_adopt.py`:

```python
from loadout import own


def _own_pairs(spec):
    return own.resolve(own.parse_spec(spec), _verdicts())


def test_apply_own_project_disables_and_removes(machine, fake_runner):
    (machine / ".claude/plugins/known_marketplaces.json").write_text(json.dumps({
        "somewhere": {"source": {"source": "github", "repo": "me/somewhere"}}}))
    bk = backup.Backup()
    lines, profiles = adopt.apply_own(_own_pairs("mystery@somewhere=project:mine,omarchy-kb=project:mine"), bk)
    assert ["claude", "plugin", "disable", "mystery@somewhere", "--scope", "user"] in fake_runner.calls
    assert ["claude", "mcp", "remove", "-s", "user", "omarchy-kb"] in fake_runner.calls
    assert set(profiles) == {"mine"}
    assert any("loadout profile mine" in line for line in lines)


def test_apply_own_leave_and_remove(machine, fake_runner):
    adopt.apply_own(_own_pairs("my-skill=leave,omarchy-kb=remove"), backup.Backup())
    assert own.is_left([v for v in _verdicts() if v.item.name == "my-skill"][0].item)
    assert ["claude", "mcp", "remove", "-s", "user", "omarchy-kb"] in fake_runner.calls


def test_apply_own_two_hooks_one_group(machine):
    data = json.loads((machine / ".claude/settings.json").read_text())
    data["hooks"]["PreToolUse"][3]["hooks"].append({"type": "command", "command": "second-linter"})
    (machine / ".claude/settings.json").write_text(json.dumps(data))
    pairs = [(v, own.Choice("global") if v.item.detail == "my-own-linter" else own.Choice("remove"))
             for v in own.unmanaged(_verdicts()) if v.item.kind == "hook"]
    adopt.apply_own(pairs, backup.Backup())
    commands = [h["command"] for g in json.loads((machine / ".claude/settings.json").read_text())["hooks"]["PreToolUse"]
                for h in g["hooks"]]
    assert commands.count("my-own-linter") == 1 and "second-linter" not in commands
    assert "rtk hook claude" in commands


def test_rerun_asks_nothing(machine, fake_runner):
    (machine / ".claude/plugins/known_marketplaces.json").write_text(json.dumps({
        "somewhere": {"source": {"source": "github", "repo": "me/somewhere"}}}))
    pairs = [(v, own.Choice("global") if "global" in own.options(v.item) else own.Choice("leave"))
             for v in own.unmanaged(_verdicts())]
    adopt.apply_own(pairs, backup.Backup())
    assert own.unmanaged(_verdicts()) == []


def test_select_pick_keep_global(machine):
    keep = []
    answers = iter(["p", "k", "n"])
    adopt.select([v for v in _verdicts() if v.action == "scope-down" and v.item.kind == "plugin"], None, set(),
                 ask=lambda q: next(answers, ""), keep_global=keep)
    assert len(keep) == 1 and keep[0].item.kind == "plugin"
```

Also append:

```python
def test_apply_own_collision_skips_machine_step(machine, fake_runner):
    path = paths.personal_root() / "profiles/mine.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"mcp": {"mcpServers": {"omarchy-kb": {"command": "other"}}}}))
    # omarchy-kb is now "keep" (in a personal profile); wrap it as own to exercise the collision path
    v = [x for x in _verdicts() if x.item.name == "omarchy-kb"][0]
    lines, _ = adopt.apply_own([(inventory.Verdict(v.item, "own", ""), own.Choice("project", "mine"))], backup.Backup())
    assert any(line.startswith("skipped:") for line in lines)
    assert ["claude", "mcp", "remove", "-s", "user", "omarchy-kb"] not in fake_runner.calls
```

(`tests/test_adopt.py` needs `from loadout import paths` — already imported — and `inventory`, already imported.)

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_own.py tests/test_adopt.py`
Expected: FAIL (`own.Choice`, `adopt.apply_own` missing).

- [ ] **Step 3: Implement** — append to `cli/loadout/own.py`:

```python
CHOICES = ("global", "project", "leave", "remove")


@dataclass(frozen=True)
class Choice:
    action: str        # global | project | leave | remove
    profile: str = ""


def parse_choice(text: str) -> Choice:
    action, _, profile = text.strip().partition(":")
    if action not in CHOICES or (action == "project") != bool(profile):
        raise ValueError(f"choice '{text}': use global, project:<profile>, leave or remove")
    if profile and not PROFILE_NAME.match(profile):
        raise ValueError(f"profile name '{profile}': use lowercase letters, digits, - and _")
    return Choice(action, profile)


def parse_spec(spec: str) -> list[tuple[str | None, str, Choice]]:
    """'name=choice,kind:name=choice,...'. Only a known kind counts as a prefix (hook names contain ':')."""
    out = []
    for part in (p.strip() for p in spec.split(",")):
        if not part:
            continue
        name, sep, choice = part.rpartition("=")
        if not sep or not name.strip():
            raise ValueError(f"'{part}': use NAME=CHOICE (for example foo@bar=global)")
        kind, colon, rest = name.strip().partition(":")
        kind, name = (kind, rest) if colon and kind in KINDS else (None, name.strip())
        out.append((kind, name, parse_choice(choice)))
    return out


def resolve(entries: list[tuple[str | None, str, Choice]], verdicts: list[Verdict]) -> list[tuple[Verdict, Choice]]:
    """Match names to unmanaged (or left) items; scope-down plugins accept only global. Raises ValueError."""
    own_items = unmanaged(verdicts, include_left=True)
    scope_down = [v for v in verdicts if v.action == "scope-down" and v.item.kind == "plugin"]
    pairs = []
    for kind, name, choice in entries:
        pool = own_items + (scope_down if choice.action == "global" else [])
        matches = [v for v in pool if v.item.name == name and (kind is None or v.item.kind == kind)]
        if not matches:
            raise ValueError(f"no unmanaged item named '{name}'" + (f" of kind {kind}" if kind else "")
                             + " (see: loadout configure own --all)")
        kinds = sorted({v.item.kind for v in matches})
        if len(kinds) > 1:
            raise ValueError(f"'{name}' matches several kinds; write it as " + " or ".join(f"{k}:{name}" for k in kinds))
        for v in matches:
            allowed = ["global"] if v.action == "scope-down" else options(v.item)
            if choice.action not in allowed:
                raise ValueError(f"{v.item.kind} {name}: {choice.action} is not available (choose: {', '.join(allowed)})")
            pairs.append((v, choice))
    return pairs


def _existing_profiles() -> list[str]:
    from . import profiles
    return profiles.list_profiles()


def ask_choices(verdicts: list[Verdict], ask) -> list[tuple[Verdict, Choice]]:
    if not verdicts:
        return []
    first = ask("your own tools: [l]eave all / [c]hoose each (default leave): ").strip().lower()
    if first not in ("c", "choose"):
        return [(v, Choice("leave")) for v in verdicts]
    pairs, last_profile = [], ""
    for v in verdicts:
        opts = options(v.item)
        prompt = f"  {v.item.kind} {v.item.name} — " + " / ".join(f"[{o[0]}]{o[1:]}" for o in opts) + " (default l): "
        action = "leave"
        for _ in range(3):
            answer = ask(prompt).strip().lower()
            if not answer:
                break
            hit = [o for o in opts if o == answer or o[0] == answer]
            if hit:
                action = hit[0]
                break
            print("  please answer " + ", ".join(f"{o[0]}({o[1:]})" for o in opts))
        choice = Choice(action)
        if action == "project":
            profile = ""
            for _ in range(3):
                answer = ask(f"    profile (existing: {', '.join(_existing_profiles()) or 'none'}; or a new name)"
                             + (f" [{last_profile}]" if last_profile else "") + ": ").strip().lower() or last_profile
                if PROFILE_NAME.match(answer):
                    profile = answer
                    break
                print("    use lowercase letters, digits, - and _")
            if not profile:
                choice = Choice("leave")
            else:
                note = profile_note(profile)
                if note:
                    print("    " + note)
                last_profile, choice = profile, Choice("project", profile)
        pairs.append((v, choice))
    return pairs


def _mentions(path: Path, needle: str) -> bool:
    try:
        return path.is_file() and needle in path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def candidate_repos(item: Item) -> list[Path]:
    """Repos Claude Code knows (~/.claude.json projects) whose project config mentions the item. A hint only."""
    needle = item.detail if item.kind == "hook" else item.name
    projects = load_json(paths.claude_json()).get("projects")
    out = []
    for path, cfg in sorted((projects if isinstance(projects, dict) else {}).items()):
        repo = Path(path)
        if not repo.is_dir():
            continue
        in_cfg = isinstance(cfg, dict) and needle in json.dumps(cfg.get("mcpServers") or {})
        files = [repo / ".mcp.json", repo / ".claude/settings.json", repo / ".claude/settings.local.json"]
        if in_cfg or any(_mentions(f, needle) for f in files):
            out.append(repo)
    return out
```

In `cli/loadout/adopt.py`, extend `select` with the keyword `keep_global: list | None = None` and replace its `elif answer == "p":` branch:

```python
        elif answer == "p":
            for v in members:
                keepable = keep_global is not None and group == "scope-down" and v.item.kind == "plugin"
                hint = " [y/N/k=keep global] " if keepable else " [y/N] "
                reply = ask(f"  {_verb(v)} {v.item.kind} {v.item.name}?{hint}").strip().lower()
                if reply in ui.YES:
                    chosen.append(v)
                elif keepable and reply in ("k", "keep"):
                    keep_global.append(v)
```

Skip the `own` group inside `select`'s interactive loop (`for group in GROUP_ORDER[:-1]:` → add `if group == "own": continue` at the top of the loop body); `--groups own` keeps working (it removes, as before).

Add to `adopt.py` (`from . import own` at the top; `link`, `settings_merge` imported inside the function to avoid cycles):

```python
def apply_own(pairs: list, bk: Backup, others: list[Verdict] = (), ask: Ask = lambda q: "",
              confirm_cmds: bool = True) -> tuple[list[str], dict]:
    """Record own-tool choices, run every removal (others + converted choices), then the deferred
    machine steps (content-based, so earlier index-based hook removals cannot shift them)."""
    from . import link, settings_merge

    out, machine, removals, recorded_profiles, personal_changed = [], [], list(others), {}, False
    for v, choice in pairs:
        if choice.action == "leave":
            own.remember_leave(v.item)
            out.append(f"{v.item.kind} {v.item.name}: left on this machine (not asked again; loadout configure own --all)")
            continue
        own.forget(v.item)
        if choice.action == "remove":
            removals.append(Verdict(v.item, "remove", v.reason))
            continue
        rec = own.record_global(v, bk) if choice.action == "global" else own.record_project(v, choice.profile, bk)
        out += rec.lines
        if not rec.ok:
            continue
        personal_changed = True
        if rec.machine:
            machine.append(rec.machine)
        if choice.action == "project":
            recorded_profiles.setdefault(choice.profile, []).append(v.item)
            removals.append(Verdict(v.item, "scope-down" if v.item.kind == "plugin" else "remove", v.reason))
            out.append(f"{v.item.kind} {v.item.name}: enable it per project with `loadout profile {choice.profile}`")
    if removals:
        out += apply(removals, bk, ask, confirm_cmds)
    for step in machine:
        out += step()
    if personal_changed:
        out += link.link_all(bk)
        settings_merge.apply_settings()
    return out, recorded_profiles
```

Note: `apply()` already skips `keep`; a `scope-down` verdict for an own plugin has no `entry_id`, so no catalog hint is added.

- [ ] **Step 4: Run all tests**

Run: `uv run --python 3.12 --with pytest pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cli/loadout/own.py cli/loadout/adopt.py tests/test_own.py tests/test_adopt.py
git commit -m "feat(adopt): choose global, project, leave or remove for your own tools"
```

---

### Task 8: Wire `adopt.run`, `--own`, the repo offer and the commit offer

**Files:**
- Modify: `cli/loadout/adopt.py` (`run`)
- Modify: `cli/loadout/configure.py` (factor `offer_commit` out of `apply_all`)
- Modify: `cli/loadout/commands.py` (`_register_adopt`)
- Test: `tests/test_adopt.py`, `tests/test_cli_help.py` (if it lists flags)

**Interfaces:**
- Consumes: `own.parse_spec`, `own.resolve`, `own.ask_choices`, `own.unmanaged`, `own.candidate_repos` (Task 7); `adopt.apply_own` (Task 7).
- Produces: `adopt.run(apply_changes, groups, skip, yes, ask, with_versions=True, interactive=None, own_spec: str | None = None) -> int`; `configure.offer_commit(ask) -> None`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_adopt.py`)

```python
def test_run_yes_leaves_own_tools(machine, fake_runner):
    assert adopt.run(True, None, set(), True, ask=lambda q: "", with_versions=False, interactive=False) == 0
    assert ["claude", "mcp", "remove", "-s", "user", "omarchy-kb"] not in fake_runner.calls
    assert not own.decisions()   # --yes does not remember "leave" either


def test_run_own_spec_non_interactive(machine, fake_runner):
    code = adopt.run(True, None, set(), False, ask=lambda q: "", with_versions=False, interactive=False,
                     own_spec="omarchy-kb=project:mine")
    assert code == 0
    assert (paths.personal_root() / "profiles/mine.json").exists()
    assert ["claude", "mcp", "remove", "-s", "user", "github-server"] not in fake_runner.calls  # other groups untouched


def test_run_own_spec_error_exits_2_before_changes(machine, fake_runner, capsys):
    code = adopt.run(True, None, set(), False, ask=lambda q: "", with_versions=False, interactive=False,
                     own_spec="nothing=global")
    assert code == 2 and "no unmanaged item" in capsys.readouterr().err
    assert [c for c in fake_runner.calls if c[:1] == ["claude"]] == []


def test_run_interactive_offers_repo_for_new_profile(machine, fake_runner, monkeypatch):
    from loadout import project
    repo = machine / "code/app"
    repo.mkdir(parents=True)
    (repo / ".mcp.json").write_text(json.dumps({"mcpServers": {"omarchy-kb": {}}}))
    cfg = json.loads((machine / ".claude.json").read_text())
    cfg["projects"] = {str(repo): {}}
    (machine / ".claude.json").write_text(json.dumps(cfg))
    applied = []
    monkeypatch.setattr(project, "add_profile", lambda path, name, **kw: applied.append((path, name)) or 0)
    script = {"your own tools": "c", "mcp omarchy-kb": "p", "profile (": "mine", "Apply": "y", "repos": ""}

    def ask(q):
        return next((a for k, a in script.items() if k in q), "")
    adopt.run(True, None, set(), False, ask=ask, with_versions=False, interactive=True)
    assert applied == [(repo, "mine")]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_adopt.py`
Expected: FAIL (`run()` has no `own_spec`).

- [ ] **Step 3: Implement**

In `cli/loadout/configure.py`, move the git block of `apply_all` into a new function and call it from `apply_all`:

```python
def offer_commit(ask: Ask) -> None:
    root = paths.personal_root()
    if not (root / ".git").exists():
        return
    ...  # the existing status / env_files / commit-and-push block from apply_all, unchanged
```

(`apply_all` keeps its behaviour: `if setup: ...; offer_commit(ask); if setup: print(...)`.)

Replace `adopt.run` with:

```python
def run(apply_changes: bool, groups: set | None, skip: set, yes: bool, ask: Ask, with_versions: bool = True,
        interactive: bool | None = None, own_spec: str | None = None) -> int:
    import sys

    if interactive is None:
        interactive = ui.is_interactive()
    verdicts = inventory.classify(inventory.collect(with_versions=with_versions))
    findings = secrets.scan_all()
    try:
        own_pairs = own.resolve(own.parse_spec(own_spec), verdicts) if own_spec is not None else None
    except ValueError as exc:
        print(f"loadout: {exc}", file=sys.stderr)
        return 2
    print(render_plan(verdicts, findings))
    if not apply_changes:
        print("\n(dry run — nothing changed. Re-run with --apply to choose and apply.)")
        return 0
    if not interactive and not yes and groups is None and own_pairs is None:
        print("\nnon-interactive: re-run with --yes, --groups GROUP,... or --own NAME=CHOICE,... to apply (nothing changed).")
        return 2
    explicit = groups is not None
    keep_global: list = []
    if own_pairs is not None and not interactive and not yes and not explicit:
        chosen = []  # --own alone: only the named items
    else:
        chosen = select(verdicts, groups if explicit else (DEFAULT_ALL if yes else None), skip, ask,
                        keep_global=keep_global if interactive and not yes else None)
    if own_pairs is None:
        own_pairs = (own.ask_choices([v for v in own.unmanaged(verdicts) if v.item.name not in skip], ask)
                     if interactive and not yes else [])
    own_pairs += [(v, own.Choice("global")) for v in keep_global]
    acting = [p for p in own_pairs if p[1].action != "leave"]
    if (chosen or acting) and interactive and not yes:
        if not ui.confirm(ask, f"Apply {len(chosen) + len(acting)} change(s)? [y/N] "):
            print("nothing changed")
            return 0
    elif not chosen and not own_pairs and not findings:
        print("nothing selected")
        return 0
    bk = Backup(description="adopt")
    lines, new_profiles = apply_own(own_pairs, bk, chosen, ask if interactive else (lambda q: ""),
                                    confirm_cmds=not (yes and explicit))
    for line in lines:
        print(redact(line))
    remaining = [f for f in findings if f.fixable
                 and f.server not in {v.item.name for v in chosen if v.item.kind == "mcp"}
                 and f.server not in {v.item.name for v, c in acting if v.item.kind == "mcp"}]
    if remaining and (yes or (interactive and ui.confirm(ask, "move detected plaintext secrets to secrets.env? [y/N] "))):
        for line in fix_secrets(remaining, bk):
            print(redact(line))
    if interactive and own_spec is None:
        _offer_profiles(new_profiles, ask)
    if acting and interactive:
        from .configure import offer_commit
        offer_commit(ask)
    if not bk.empty:
        print(f"\nbackup: {bk.root}  (undo: loadout restore {bk.root}; it holds old configs, keep it private)")
    return 0


def _offer_profiles(new_profiles: dict, ask: Ask) -> None:
    from . import project

    for name, items in new_profiles.items():
        found = sorted({repo for item in items for repo in own.candidate_repos(item)})
        print(f"\nprofile {name} is in your personal layer. Apply it to repos now?")
        if found:
            print("  detected: " + ", ".join(str(r) for r in found))
        answer = ask("  repos (comma separated paths, empty = detected, '-' = none): ").strip()
        repos = found if answer == "" else [] if answer == "-" else [Path(a.strip()).expanduser() for a in answer.split(",") if a.strip()]
        for repo in repos:
            if repo.is_dir():
                project.add_profile(repo, name)
            else:
                print(f"  {repo}: not a folder, skipped")
```

In `cli/loadout/commands.py` `_register_adopt` add:

```python
    p.add_argument("--own", metavar="NAME=CHOICE,...",
                   help="decide for your own tools: global, project:<profile>, leave or remove "
                        "(e.g. foo@bar=global,my-db=project:db); others stay as they are")
```

and pass `own_spec=a.own` to `adopt.run`. Update the `--yes` help to: "no questions: apply --groups, or remove,migrate,scope-down, and move secrets; your own tools stay as they are".

- [ ] **Step 4: Run all tests**

Run: `uv run --python 3.12 --with pytest pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cli/loadout/adopt.py cli/loadout/configure.py cli/loadout/commands.py tests/test_adopt.py
git commit -m "feat(adopt): --own, per-item choices, profile-to-repo offer and personal-layer commit offer"
```

---

### Task 9: `loadout configure own` / `set own` and the `check` line

**Files:**
- Modify: `cli/loadout/configure.py` (append)
- Modify: `cli/loadout/commands.py` (`_register_configure`)
- Modify: `cli/loadout/check.py` (`_own`, `run_checks`)
- Test: `tests/test_configure.py`, `tests/test_check.py`

**Interfaces:**
- Consumes: `own.*`, `adopt.apply_own`.
- Produces: `configure.own_lines(include_left: bool) -> list[str]`; `configure.set_own(name: str, choice: str) -> int` (0, or 2 on a ValueError from parse/resolve).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_configure.py` (add `from fixtures import author_machine` and `json` if missing):

```python
def test_configure_own_lists_and_set_own(fake_home, fake_runner, capsys):
    from loadout import own, paths
    author_machine(fake_home)
    text = "\n".join(configure.own_lines(False))
    assert "mystery@somewhere" in text and "options: global, project, leave, remove" in text
    assert configure.set_own("my-skill", "leave") == 0
    assert "my-skill" not in "\n".join(configure.own_lines(False))
    assert "my-skill" in "\n".join(configure.own_lines(True))
    assert configure.set_own("nothing", "leave") == 2
    assert configure.set_own("mystery@somewhere", "keep") == 2


def test_cli_configure_own(fake_home, fake_runner, capsys):
    from loadout.__main__ import main
    author_machine(fake_home)
    assert main(["configure", "own"]) == 0
    assert "options:" in capsys.readouterr().out
    assert main(["configure", "set", "own", "nothing", "leave"]) == 2
```

Append to `tests/test_check.py`:

```python
def test_check_mentions_unmanaged_tools(fake_home, fake_runner):
    _setup_ok(fake_home)
    (fake_home / ".claude/skills/mine").mkdir(parents=True)
    r = _by(check.run_checks())["own tools managed"]
    assert not r.ok and r.severity == "warn" and r.fix == "loadout configure own"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_configure.py tests/test_check.py`
Expected: FAIL (`configure.own_lines` missing).

- [ ] **Step 3: Implement** — append to `cli/loadout/configure.py`:

```python
def _own_verdicts():
    from . import inventory
    return inventory.classify(inventory.collect(with_versions=False))


def own_lines(include_left: bool) -> list[str]:
    from . import own

    found = own.unmanaged(_own_verdicts(), include_left)
    if not found:
        return ["all your tools are managed by loadout" + ("" if include_left else " (left ones: loadout configure own --all)")]
    lines = ["Not managed by loadout (they stay on this machine only). Choose with:",
             "  loadout configure set own <name> global|project:<profile>|leave|remove"]
    for v in found:
        lines.append(redact(f"  [{v.item.kind}] {v.item.name}  {v.item.detail}".rstrip()))
        left = "  (left on this machine)" if own.is_left(v.item) else ""
        lines.append(f"      options: {', '.join(own.options(v.item))}{left}")
    return lines


def set_own(name: str, choice: str) -> int:
    import sys

    from . import adopt, own

    try:
        pairs = own.resolve(own.parse_spec(f"{name}={choice}"), _own_verdicts())
    except ValueError as exc:
        print(f"loadout: {exc}", file=sys.stderr)
        return 2
    bk = Backup(description="configure own")
    lines, profiles_changed = adopt.apply_own(pairs, bk)
    for line in lines:
        print(redact(line))
    for profile in profiles_changed:
        print(f"apply it in a repo: cd <repo> && loadout profile {profile}")
    if not bk.empty:
        print(f"backup: {bk.root}  (undo: loadout restore {bk.root})")
    return 0
```

In `cli/loadout/commands.py` `_register_configure`: `choices=["show", "set", "prefs", "own"]` for `action`; `choices=["plugin", "mcp", "pref-choice", "pref", "own"]` for `kind`; add `p.add_argument("--all", action="store_true", help="with own: also list the tools you left on this machine")`; add epilog lines `"  loadout configure own\n"` and `"  loadout configure set own foo@bar global\n"`; update `value` help to mention `global|project:<profile>|leave|remove for own`. In `run`:

```python
        if a.action == "own":
            print("\n".join(configure.own_lines(a.all)))
            return 0
        ...
        if a.kind == "own":
            return configure.set_own(a.name, a.value)
```

(The `own` branch of `set` returns before `configure.apply_all`, since `apply_own` already applied settings and links.)

In `cli/loadout/check.py` add:

```python
def _own() -> list[CheckResult]:
    from . import inventory, own

    try:
        n = len(own.unmanaged(inventory.classify(inventory.collect(with_versions=False))))
    except InvalidJSON as exc:
        return [CheckResult("own tools managed", False, str(exc), "fix the JSON syntax", "warn")]
    return [CheckResult("own tools managed", n == 0, f"{n} tool(s) not managed by loadout (they stay on this machine only)",
                        "loadout configure own", "warn")]
```

and add `*_own()` to `run_checks()` after `*_plugins()`.

- [ ] **Step 4: Run all tests**

Run: `uv run --python 3.12 --with pytest pytest -q`
Expected: PASS. `test_check_passes_on_good_setup` must still pass (its home has no own tools); if it fails because the kit's own skills or hooks show up, fix the classification, not the test.

- [ ] **Step 5: Commit**

```bash
git add cli/loadout/configure.py cli/loadout/commands.py cli/loadout/check.py tests/test_configure.py tests/test_check.py
git commit -m "feat(configure): list and decide unmanaged tools; check mentions them"
```

---

### Task 10: `/loadout:configure` skill, eval stub and eval case

**Files:**
- Modify: `plugins/loadout/skills/configure/SKILL.md`
- Modify: `plugins/loadout/evals/bin/loadout`
- Create: `plugins/loadout/evals/configure-own/{case.yaml,prompt.md,scaffold.sh,graders/*.md}`
- Test: `tests/test_evals_static.py` (runs automatically over every case)

- [ ] **Step 1: Skill text** — in `SKILL.md` step 1 add: "Also run `loadout configure own` (add `--all` when the user asks about tools they left) to see tools loadout does not manage." In step 5 add: "For one of the user's own tools: `loadout configure set own <name> global|project:<profile>|leave|remove` (write `<kind>:<name>` when the engine says the name is ambiguous). Explain the four choices in one line each before asking: global follows them to every machine, project keeps it out of other repos (a personal profile; apply it with `loadout profile <name>`), leave keeps it on this machine only, remove takes it away (restorable)."

- [ ] **Step 2: Stub** — in `plugins/loadout/evals/bin/loadout` add a `"configure own")` case before the `"configure "*)` fallback that prints:

```
Not managed by loadout (they stay on this machine only). Choose with:
  loadout configure set own <name> global|project:<profile>|leave|remove
  [plugin] notes-helper@my-marketplace  1.0.0
      options: global, project, leave, remove
  [mcp] my-postgres  npx -y my-postgres-mcp
      options: global, project, leave, remove
```

and accept `configure set own <name> <choice>` in the existing `"configure set")` case (print `<name>: recorded` and log the call like the other set calls).

- [ ] **Step 3: Case** — `configure-own/case.yaml` (copy the structure of `configure-propose/case.yaml`; name `configure-own`; description: "The user asks what loadout does with the tools they installed themselves. The skill must run `loadout configure own`, explain global/project/leave/remove, propose a choice per tool, ask for a yes, and make no `configure set` call."), `prompt.md` with the same frontmatter as `configure-propose/prompt.md` and the text "I installed a couple of my own Claude tools on this laptop (a notes plugin and a Postgres MCP server). I want them on my desktop too, but the Postgres one only in my work repos. What would you change?", `scaffold.sh` identical to `configure-propose/scaffold.sh`, and graders:
  - `skill-fired.md` (copy of `configure-propose/graders/skill-fired.md`)
  - `ran-own.md`: `type: regex`, `target: { source: file, path: .loadout-calls.log }`, `pattern: "^configure own"`, `weight: 2`
  - `no-set-without-yes.md` (copy of the configure-propose one)
  - `no-direct-settings-edit.md` (copy of the configure-propose one)
  - `proposes-choices.md`: `type: llm`, `focus: last_message`, `weight: 2`; PASS if the reply proposes global for `notes-helper@my-marketplace`, project (a personal profile, applied with `loadout profile`) for `my-postgres`, and asks for a yes; FAIL if it claims the change was applied or proposes editing settings files by hand.

- [ ] **Step 4: Run the static tests**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_evals_static.py`
Expected: PASS.

- [ ] **Step 5: Run the new eval case only** (costs about $1; only via the runner, which stubs browsers and uses a temp HOME)

Run: `plugins/loadout/evals/run.sh --case configure-own`
Expected: all graders pass (3/3 if the runner repeats). If a grader fails, fix the skill text, not the grader, unless the grader is wrong.

- [ ] **Step 6: Commit**

```bash
git add plugins/loadout/skills/configure/SKILL.md plugins/loadout/evals/bin/loadout plugins/loadout/evals/configure-own
git commit -m "feat(skills): configure offers global, project, leave or remove for the user's own tools"
```

---

### Task 11: Documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-10-08-agent-loadout-design.md` (§3.2, §6.2, §6.4)
- Modify: `plugins/loadout/skills/onboard/SKILL.md` (only if it describes adopt or unmanaged tools; check with grep)
- Test: `tests/test_repo_static.py` (link checks, if present), full suite

- [ ] **Step 1: README**
  - Line ~29 (bootstrap "Existing setup" bullet): add "and asks what to do with tools loadout does not manage: record them globally (they follow you to every machine), put them in a personal profile for some repos, leave them on this machine, or remove them. Without an answer they stay as they are."
  - Line ~81 (adopt row in the command table): add `--own NAME=CHOICE,...` to the flags column.
  - Add a row for `loadout configure own` / `configure set own` next to the configure rows.
  - Line ~205 FAQ "I already have my own CLAUDE.md, hooks and settings": append "Plugins, MCP servers, skills and hooks loadout doesn't know are listed under *Your own tools*; you decide per item."
  - New section `### Your own tools` (near the adopt section): the four choices table from spec §2, where each choice writes (spec §3 personal-layer tree), and **Known limits** (spec §6, verbatim bullets, including: plugins recorded on another machine install at the next Claude Code start, active after `/reload-plugins`; MCP same-name rule; profile copies drift; shared-source skill pointers; hook paths outside `$HOME` and exec-form hooks; only the hook script file is copied).
- [ ] **Step 2: Main spec** — §3.2 tree: add `mcp.json`, `skills/`, `skills.json`, `hooks/`, `profiles/skills/`. §6.2 step 3: replace "*unknown* (kept untouched)" with "*own* (not managed by loadout; the user chooses global / project / leave / remove, default leave; see `2026-10-10-adopt-own-tools-design.md`)", and add "items already in the personal layer or a personal profile are *keep*". §6.4: add `loadout configure own [--all]` and `configure set own NAME CHOICE`.
- [ ] **Step 3: Grep for stale wording**

Run: `grep -rn -i "unknown" README.md docs/superpowers/specs/2026-10-08-agent-loadout-design.md plugins/loadout/skills`
Expected: no hit that describes the old adopt group.

- [ ] **Step 4: Run all tests and validate the plugin**

Run: `uv run --python 3.12 --with pytest pytest -q && claude plugin validate . && claude plugin validate plugins/loadout`
Expected: PASS / validation OK.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/superpowers/specs/2026-10-08-agent-loadout-design.md plugins/loadout/skills/onboard/SKILL.md
git commit -m "docs: your own tools in adopt and configure, with known limits"
```
