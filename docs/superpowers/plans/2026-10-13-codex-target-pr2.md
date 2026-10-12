# Codex target PR 2: projects and adopt — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `loadout init`/`loadout profile` also set up Codex in the repo (MCP servers, skills, plugins), and
`loadout adopt` handles MCP servers and skills that only Codex has.

**Architecture:** One new module, `cli/loadout/codex_project.py`, writes the repo's `.codex/config.toml`. It only adds
tables and checks the result with the same semantic guard as `apply_config`. It links the repo's `.claude/skills/*`
into `.agents/skills/` and installs the profile's plugins through `codex plugin add`. `cli/loadout/codex.py` gains:
owned keys in quoted tables (`[plugins."x@m"] enabled = false`, so a profile plugin stays project-only), conversion of
Codex server tables back to the Claude format, and server removal. `inventory.py`, `own.py` and `adopt.py` treat Codex
items like Claude ones, but under their own decision keys.

**Tech Stack:** Python 3.10+ standard library (`tomllib` from 3.11 for every TOML read or edit), pytest with
`fake_home` and `fake_runner`.

**Spec:** `docs/superpowers/specs/2026-10-12-codex-target-design.md` (section "Projects and adopt (PR 2)"; Errors;
Undo).

## Global Constraints

- Standard library only in `cli/loadout/`; no TOML editing without `tomllib` (Python 3.10: skip with one line).
- Tests never touch the real `~/.claude`, `~/.claude.json`, `~/.codex` or `~/.config/loadout`; use `fake_home` and `fake_runner`.
- Agents never run real installers, mutating `claude` commands, or real `codex`.
- Conventional Commits; no AI attribution.
- Nothing the user wrote in a TOML file changes: the guard compares the parsed file before and after, minus what loadout owns or adds.
- The Codex-side work runs only when `targets.codex_enabled()`; the Claude-side behaviour stays unchanged.
- Never auto-approve Codex hooks or project trust; loadout prints the step instead.
- Run the tests with: `uv run --python 3.12 --with pytest pytest -q`.

## Facts this plan rests on (sandbox spikes, codex 0.162.1, 2026-10-13)

- Plugin installed + user `[plugins."x@m"] enabled = false` + project `.codex/config.toml` `[plugins."x@m"] enabled = true`
  in a trusted project: the plugin's skills appear only in that project. A plugin that is not installed (in the cache)
  is not seen, even with the marketplace known.
- `codex plugin add x@m` on an installed plugin whose user entry says `enabled = false` sets it back to `true`.
- A project `[mcp_servers.x]` with `enabled = false` is listed by `codex mcp list` as `"enabled": false`.
- `.agents/skills/<name>` as a relative symlink to `../../.claude/skills/<name>` is discovered by Codex.
- `codex mcp list` run inside a trusted project also lists that project's servers.

## Review Focus

1. loadout run from inside a repo (session hook, `loadout update`): drift must not report the repo's own Codex servers as "only in Codex". Expected: `codex mcp list` runs from the home folder (test in Task 1).
2. `loadout profile web` run twice: no duplicate tables, no warning on the second run (test in Task 2).
3. A repo `.codex/config.toml` with comments, multi-line strings or a same-named table the user wrote: the user's text stays byte-for-byte, and the conflict is reported (test in Task 2).
4. Python 3.10 (no tomllib): project setup prints one "skipped" line, skills and plugins still work, and adopt lists no Codex MCP servers (tests in Tasks 2 and 3).
5. A Codex server with keys Claude Code cannot express (e.g. `[mcp_servers.x.tools.y]`, `startup_timeout_sec`): adopt still offers leave/remove, and "global" says why it cannot record it (test in Task 4).

---

### Task 1: Owned keys in quoted tables; project-only plugins stay off at user level; drift ignores repo servers

**Files:**
- Modify: `cli/loadout/codex.py` (`desired_keys`, `apply_config` keys loop, `_without_owned`, `mcp_names`, new `_dotted`, `_key_path`, `project_plugins`, `add_project_plugin`)
- Modify: `tests/conftest.py` (FakeRunner records `cwd`)
- Test: `tests/test_codex_project_plugins.py` (new)

**Interfaces:**
- Produces: `codex.desired_keys() -> list[tuple[tuple[str, ...], str, object, bool]]` (table path, key, value, force);
  `codex.project_plugins() -> list[str]`; `codex.add_project_plugin(pid: str) -> None` (records pid in
  `codex-config.json` under `"project_plugins"`); `codex._without_owned(data, tables, keys, tl)` (keys are dotted
  TOML keys, e.g. `plugins."x@m".enabled`).
- Record format stays backward compatible: `"keys"` entries for the existing preferences keep their names
  (`model_reasoning_effort`, `tui.notifications`).

- [ ] **Step 1: FakeRunner records cwd**

In `tests/conftest.py`, `FakeRunner.__init__` add `self.cwds = []`; in `__call__` add `self.cwds.append(cwd)` after `self.envs.append(env)`.

- [ ] **Step 2: Write the failing tests**

```python
"""Profile plugins stay project-only in Codex: loadout keeps their user-level entry switched off."""
import json
import sys

import pytest

from loadout import backup, codex, paths, runner, settings_merge

needs_tomllib = pytest.mark.skipif(sys.version_info < (3, 11), reason="config edits need tomllib")


def _settings(monkeypatch, enabled=None):
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: {"enabledPlugins": enabled or {}})


@needs_tomllib
def test_project_plugin_is_switched_off_at_user_level(fake_home, fake_runner, monkeypatch):
    _settings(monkeypatch)
    cfg = paths.codex_home() / "config.toml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text('[plugins."deepeval@claude-plugins-official"]\nenabled = true\n')
    codex.add_project_plugin("deepeval@claude-plugins-official")
    codex.apply_config(backup.Backup(description="t"))
    text = cfg.read_text()
    assert '[plugins."deepeval@claude-plugins-official"]\nenabled = false' in text
    assert text.count("deepeval") == 1


@needs_tomllib
def test_codex_plugin_add_turning_it_back_on_is_undone(fake_home, fake_runner, monkeypatch):
    _settings(monkeypatch)
    codex.add_project_plugin("deepeval@claude-plugins-official")
    bk = backup.Backup(description="t")
    codex.apply_config(bk)
    cfg = paths.codex_home() / "config.toml"
    cfg.write_text(cfg.read_text().replace("enabled = false", "enabled = true"))  # what `codex plugin add` does
    lines = codex.apply_config(bk)
    assert "enabled = false" in cfg.read_text()
    assert not any("your value" in l for l in lines)


@needs_tomllib
def test_a_project_plugin_enabled_globally_is_switched_on(fake_home, fake_runner, monkeypatch):
    codex.add_project_plugin("deepeval@claude-plugins-official")
    _settings(monkeypatch)
    codex.apply_config(backup.Backup(description="t"))
    _settings(monkeypatch, {"deepeval@claude-plugins-official": True})
    codex.apply_config(backup.Backup(description="t"))
    assert '[plugins."deepeval@claude-plugins-official"]\nenabled = true' in (paths.codex_home() / "config.toml").read_text()


@needs_tomllib
def test_existing_key_records_keep_working(fake_home, fake_runner, monkeypatch):
    _settings(monkeypatch)
    codex.apply_config(backup.Backup(description="t"))
    keys = json.loads(codex.record_path().read_text())["keys"]
    assert "model_reasoning_effort" in keys and "tui.notifications" in keys


def test_add_project_plugin_is_idempotent(fake_home):
    codex.add_project_plugin("a@m")
    codex.add_project_plugin("a@m")
    assert codex.project_plugins() == ["a@m"]


def test_mcp_list_runs_from_home_so_repo_servers_do_not_count(fake_home, fake_runner):
    fake_runner.responses[("codex", "mcp", "list")] = runner.Result(0, "[]", "")
    codex.mcp_names()
    i = next(i for i, c in enumerate(fake_runner.calls) if c[:3] == ["codex", "mcp", "list"])
    assert fake_runner.cwds[i] == str(paths.home())
```

- [ ] **Step 3: Run them to verify they fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_codex_project_plugins.py`
Expected: FAIL (`AttributeError: module 'loadout.codex' has no attribute 'add_project_plugin'`; the cwd test fails with `None != '…/home'`).

- [ ] **Step 4: Implement**

In `cli/loadout/codex.py`:

```python
def project_plugins() -> list[str]:
    """Plugins loadout installed for a project profile only: kept off at user level, on in that project."""
    value = load_json(record_path()).get("project_plugins", [])
    return [p for p in value if isinstance(p, str)] if isinstance(value, list) else []


def add_project_plugin(pid: str) -> None:
    data = load_json(record_path())
    plugins = project_plugins()
    if pid not in plugins:
        data["project_plugins"] = plugins + [pid]
        record_path().parent.mkdir(parents=True, exist_ok=True)
        save_json(record_path(), data)


def _dotted(path: tuple, key: str) -> str:
    return ".".join(toml_key(p) for p in (*path, key))


def _key_path(dotted: str, tl) -> tuple:
    """`plugins."x@m".enabled` -> ("plugins", "x@m", "enabled"), as TOML reads it."""
    data, out = tl.loads(f"{dotted} = 0\n"), []
    while isinstance(data, dict):
        key, data = next(iter(data.items()))
        out.append(key)
    return tuple(out)
```

Replace `desired_keys`:

```python
def desired_keys() -> list[tuple[tuple, str, object, bool]]:
    """(table path, key, value, force); path () is the top level. force: loadout's value wins even over a changed
    line, used for project-only plugins because `codex plugin add` switches them back on."""
    from . import preferences
    from .settings_merge import desired_settings
    state = preferences.detect()

    def answer(pid):
        return state[pid].value or preferences.by_id(pid)["default"]
    on = desired_settings().get("enabledPlugins", {})
    keys = [((), "model_reasoning_effort", answer("effort_level"), False),
            (("tui",), "notifications", answer("agent_push_notifications") == "yes", False)]
    keys += [(("plugins", pid), "enabled", on.get(pid) is True, True) for pid in project_plugins()]
    return keys
```

In `apply_config`, replace the keys loop head and the "your value" branch:

```python
    for table, key, value, force in desired_keys():
        dotted = _dotted(table, key)
        line = f"{key} = {toml_value(value)}"
        target = sections[0] if not table else find(table)
        if target is None:
            header = "[" + ".".join(toml_key(p) for p in table) + "]"
            sections.append([table, [header, line], []])
            owned_keys[dotted] = line
            continue
        # … (the flags / found / insert code stays as it is) …
        elif target[1][found].strip() == line:
            pass
        elif force or owned_keys.get(dotted) == target[1][found].strip():
            target[1][found] = line
            owned_keys[dotted] = line
        else:
            lines.append(f"{dotted}: left as is in config.toml (your value)")
            owned_keys.pop(dotted, None)
```

Note: a forced key whose table exists but has no `enabled` line takes the existing "found is None" branch (inserted
and owned), unchanged.

`_without_owned` takes `tl` and walks parsed key paths:

```python
def _without_owned(data: dict, tables, keys, tl) -> dict:
    data = json.loads(json.dumps(data, default=str))  # a deep copy; dates become strings on both sides alike
    servers = data.get("mcp_servers")
    if isinstance(servers, dict):
        for name in tables:
            servers.pop(name, None)
    for dotted in keys:
        *parents, last = _key_path(dotted, tl)
        cur = data
        for part in parents:
            cur = cur.get(part) if isinstance(cur, dict) else None
        if isinstance(cur, dict):
            cur.pop(last, None)
    return _prune(data)
```

Update its call in `apply_config` to pass `tl`. In `mcp_names` pass `cwd=str(paths.home())` to `runner.run`.

- [ ] **Step 5: Run the new tests and the Codex suite**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_codex_project_plugins.py tests/test_codex_config.py tests/test_codex_final_fixes.py`
Expected: PASS. (If an existing test calls `desired_keys()` expecting 3-tuples or `_without_owned` without `tl`, update the test to the new signature; record that as a ruling.)

- [ ] **Step 6: Commit**

```bash
git add cli/loadout/codex.py tests/conftest.py tests/test_codex_project_plugins.py
git commit -m "feat(codex): keep project-only plugins off at user level; drift ignores repo servers"
```

---

### Task 2: `loadout init`/`profile` set up Codex in the repo

**Files:**
- Create: `cli/loadout/codex_project.py`
- Modify: `cli/loadout/codex.py` (extract `_install_routes` from `apply_plugins`)
- Modify: `cli/loadout/project.py` (`add_profile`, `init` final line)
- Test: `tests/test_codex_project.py` (new)

**Interfaces:**
- Consumes: `codex.add_project_plugin`, `codex.apply_config`, `codex.server`, `codex.table_text`, `codex.toml_key`,
  `codex.Refused`, `codex._tomllib`, `codex._without_owned(data, tables, keys, tl)`, `codex.plugin_routes`,
  `codex.installed_plugins`.
- Produces: `codex_project.apply(prof: profiles.Profile, project: Path, install: bool, dry_run: bool) -> list[str]`;
  `codex_project.config(prof, project, dry_run) -> list[str]`; `codex_project.skills(project, dry_run) -> list[str]`;
  `codex_project.plugins(prof, dry_run) -> list[str]`; `codex_project.TRUST_NOTE: str`;
  `codex._install_routes(routes, bk, refresh, say, listed) -> tuple[list[str], set[str]]` (lines, plugin ids now installed).

- [ ] **Step 1: Write the failing tests**

```python
"""loadout init / profile also set up Codex in the repo."""
import sys

import pytest

from loadout import codex, codex_project, paths, profiles, project, runner, settings_merge, targets

needs_tomllib = pytest.mark.skipif(sys.version_info < (3, 11), reason="config edits need tomllib")

WEB = profiles.Profile(
    name="web", description="",
    mcp={"mcpServers": {"chrome-devtools": {"type": "stdio", "command": "npx", "args": ["-y", "chrome-devtools-mcp@1.10.1"]}}},
    settings={"disabledMcpjsonServers": ["chrome-devtools"]})
THESIS = profiles.Profile(name="thesis", description="", install=["deepeval@claude-plugins-official"],
                          settings={"enabledPlugins": {"deepeval@claude-plugins-official": True}})


@pytest.fixture
def repo(fake_home, tmp_path):
    p = tmp_path / "repo"
    (p / ".git").mkdir(parents=True)
    return p


@needs_tomllib
def test_profile_servers_become_project_tables(repo):
    lines = codex_project.config(WEB, repo, dry_run=False)
    text = (repo / ".codex" / "config.toml").read_text()
    assert '[mcp_servers.chrome-devtools]\ncommand = "npx"' in text
    assert "enabled = false" in text  # disabledMcpjsonServers
    assert any("chrome-devtools" in l for l in lines)


@needs_tomllib
def test_running_twice_changes_nothing_and_warns_nothing(repo):
    codex_project.config(WEB, repo, dry_run=False)
    before = (repo / ".codex" / "config.toml").read_text()
    assert codex_project.config(WEB, repo, dry_run=False) == []
    assert (repo / ".codex" / "config.toml").read_text() == before


@needs_tomllib
def test_user_text_stays_and_a_same_named_table_is_reported(repo):
    cfg = repo / ".codex" / "config.toml"
    cfg.parent.mkdir()
    user = '# mine\nnote = """\n[mcp_servers.fake]\n"""\n\n[mcp_servers.chrome-devtools]\ncommand = "other"\n'
    cfg.write_text(user)
    lines = codex_project.config(WEB, repo, dry_run=False)
    assert cfg.read_text() == user
    assert any("left as is" in l and "chrome-devtools" in l for l in lines)


@needs_tomllib
def test_plugins_are_enabled_in_the_project(repo):
    codex_project.config(THESIS, repo, dry_run=False)
    assert '[plugins."deepeval@claude-plugins-official"]\nenabled = true' in (repo / ".codex" / "config.toml").read_text()


@needs_tomllib
def test_a_server_codex_cannot_take_is_skipped_with_a_reason(repo):
    db = profiles.Profile(name="db", description="", mcp={"mcpServers": {"dbhub": {
        "command": "npx", "args": ["--dsn", "${DATABASE_URL}"]}}})
    lines = codex_project.config(db, repo, dry_run=False)
    assert any(l.startswith("skipped mcp dbhub") for l in lines)
    assert not (repo / ".codex" / "config.toml").exists()


def test_dry_run_writes_nothing(repo):
    lines = codex_project.config(WEB, repo, dry_run=True)
    assert not (repo / ".codex").exists()
    assert lines and all(l.startswith(("would", "skipped")) for l in lines)


def test_without_tomllib_one_line(repo, monkeypatch):
    monkeypatch.setattr(codex, "_tomllib", lambda: None)
    assert codex_project.config(WEB, repo, dry_run=False) == [
        f"skipped {repo / '.codex' / 'config.toml'}: editing it safely needs Python 3.11 or newer"]


def test_symlinked_codex_folder_outside_the_repo_is_refused(repo, tmp_path):
    (tmp_path / "elsewhere").mkdir()
    (repo / ".codex").symlink_to(tmp_path / "elsewhere")
    lines = codex_project.config(WEB, repo, dry_run=False)
    assert any("points outside" in l for l in lines)
    assert not (tmp_path / "elsewhere" / "config.toml").exists()


def test_repo_skills_are_linked_for_codex(repo):
    (repo / ".claude" / "skills" / "pw").mkdir(parents=True)
    (repo / ".agents" / "skills" / "mine").mkdir(parents=True)
    lines = codex_project.skills(repo, dry_run=False)
    link = repo / ".agents" / "skills" / "pw"
    assert link.is_symlink() and str(link.readlink()) == "../../.claude/skills/pw"
    assert (repo / ".agents" / "skills" / "mine").is_dir()  # never replaced
    assert codex_project.skills(repo, dry_run=False) == []  # second run: nothing to do
    assert lines == ["linked skill pw for Codex -> .agents/skills/pw"]


def test_profile_plugin_is_installed_and_recorded_project_only(repo, fake_runner, monkeypatch):
    import json
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: {"enabledPlugins": {}})
    monkeypatch.setattr(codex, "apply_config", lambda bk, dry_run=False: [])
    fake_runner.responses[("codex", "plugin", "list")] = runner.Result(0, json.dumps({"installed": []}), "")
    fake_runner.responses[("codex", "plugin", "marketplace", "add", codex.OFFICIAL)] = runner.Result(
        0, json.dumps({"marketplaceName": "claude-plugins-official", "alreadyAdded": True}), "")
    codex_project.plugins(THESIS, dry_run=False)
    assert ["codex", "plugin", "add", "deepeval@claude-plugins-official", "--json"] in fake_runner.calls
    assert codex.project_plugins() == ["deepeval@claude-plugins-official"]


def test_a_plugin_already_on_everywhere_is_not_made_project_only(repo, fake_runner, monkeypatch):
    import json
    monkeypatch.setattr(settings_merge, "desired_settings",
                        lambda: {"enabledPlugins": {"deepeval@claude-plugins-official": True}})
    monkeypatch.setattr(codex, "apply_config", lambda bk, dry_run=False: [])
    fake_runner.responses[("codex", "plugin", "list")] = runner.Result(
        0, json.dumps({"installed": [{"pluginId": "deepeval@claude-plugins-official"}]}), "")
    fake_runner.responses[("codex", "plugin", "marketplace", "add", codex.OFFICIAL)] = runner.Result(
        0, json.dumps({"marketplaceName": "claude-plugins-official", "alreadyAdded": True}), "")
    codex_project.plugins(THESIS, dry_run=False)
    assert codex.project_plugins() == []


def test_add_profile_runs_codex_only_when_codex_is_on(repo, fake_runner, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(codex_project, "apply", lambda prof, p, install, dry_run: calls.append(prof.name) or [])
    monkeypatch.setattr(profiles, "load_profile", lambda name: WEB)
    monkeypatch.setattr(targets, "codex_enabled", lambda: False)
    project.add_profile(repo, "web", install=False)
    assert calls == []
    monkeypatch.setattr(targets, "codex_enabled", lambda: True)
    project.add_profile(repo, "web", install=False)
    assert calls == ["web"]


def test_trust_note_unless_the_project_is_trusted(repo, monkeypatch):
    monkeypatch.setattr(codex_project, "config", lambda prof, p, dry_run: ["x"])
    monkeypatch.setattr(codex_project, "skills", lambda p, dry_run: [])
    assert codex_project.TRUST_NOTE in codex_project.apply(WEB, repo, install=False, dry_run=False)
    cfg = paths.codex_home() / "config.toml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(f'[projects."{repo.resolve()}"]\ntrust_level = "trusted"\n')
    if codex._tomllib() is not None:
        assert codex_project.TRUST_NOTE not in codex_project.apply(WEB, repo, install=False, dry_run=False)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_codex_project.py`
Expected: FAIL with `ImportError: cannot import name 'codex_project'`.

- [ ] **Step 3: Extract `_install_routes` in `codex.py`**

Move the per-marketplace loop out of `apply_plugins` unchanged, so both callers share it:

```python
def _install_routes(routes: dict[str, list[str]], bk, refresh: bool, say, listed: set[str] | None
                    ) -> tuple[list[str], set[str]]:
    """Add each marketplace and install its plugins. Returns the lines and the plugin ids installed afterwards."""
    lines, installed = [], set(listed or ())
    for src, plugins in routes.items():
        say(f"  marketplace {src} (a git clone the first time; can take a few minutes)…")
        res = runner.run(["codex", "plugin", "marketplace", "add", src, "--json"], timeout=900)
        info = _json(res.stdout) if res.ok else None
        if not isinstance(info, dict) or "marketplaceName" not in info:
            lines.append(f"marketplace {src}: failed: {_tail(res)}")
            continue
        market = info["marketplaceName"]
        if not info.get("alreadyAdded") and listed is not None:
            bk.record_command(f"codex marketplace {market}", ["codex", "plugin", "marketplace", "remove", market])
        elif refresh:
            runner.run(["codex", "plugin", "marketplace", "upgrade", market], timeout=900)
        for name in plugins:
            pid = f"{name}@{market}"
            if pid in installed and not refresh:
                continue
            say(f"  plugin {pid}…")
            res = runner.run(["codex", "plugin", "add", pid, "--json"], timeout=600)
            if not res.ok:
                lines.append(f"plugin {pid}: failed: {_tail(res)}")
                continue
            if pid not in installed and listed is not None:
                bk.record_command(f"codex plugin {pid}", ["codex", "plugin", "remove", pid])
                lines.append(f"plugin {pid}: installed")
            installed.add(pid)
    return lines, installed


def apply_plugins(bk, refresh: bool = False, say=None) -> list[str]:
    """say: called with a progress line before each slow step (git clones of marketplaces, plugin installs)."""
    say = say or (lambda line: None)
    from .settings_merge import desired_settings
    routes, missing = plugin_routes(desired_settings())
    lines = [f"plugin {pid}: no Codex route (its marketplace is not on GitHub)" for pid in missing]
    return lines + _install_routes(routes, bk, refresh, say, installed_plugins())[0]
```

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_codex_plugins.py tests/test_codex_progress.py`
Expected: PASS (behaviour unchanged).

- [ ] **Step 4: Create `cli/loadout/codex_project.py`**

```python
"""The Codex side of `loadout init` and `loadout profile`: the repo's .codex/config.toml, .agents/skills and plugins."""
from __future__ import annotations

import os
from pathlib import Path

from . import codex, paths, profiles, runner
from .jsonio import load_json

TRUST_NOTE = ("Codex reads the repo's .codex/config.toml only in a trusted project: start `codex` here once and "
              "accept the trust question")


def _inside(path: Path, project: Path) -> bool:
    try:
        path.resolve().relative_to(project.resolve())
        return True
    except ValueError:
        return False


def _wanted(prof: profiles.Profile) -> tuple[dict[str, str], list[str], list[str]]:
    """(table text by name, plugin ids, skipped lines)."""
    servers = prof.mcp.get("mcpServers", {}) if isinstance(prof.mcp, dict) else {}
    off = set(prof.settings.get("disabledMcpjsonServers", []) or [])
    tables, skipped = {}, []
    for name, cfg in (servers if isinstance(servers, dict) else {}).items():
        try:
            text = codex.table_text(name, codex.server(name, cfg))
        except codex.Refused as exc:
            skipped.append(f"skipped {exc}")
            continue
        tables[name] = text + ("enabled = false\n" if name in off else "")
    plugins = [p for p in prof.install if isinstance(p, str) and "@" in p]
    return tables, plugins, skipped


def config(prof: profiles.Profile, project: Path, dry_run: bool) -> list[str]:
    """Add the profile's servers and plugin switches to the repo's .codex/config.toml. Only adds tables; a table of
    the same name is the user's and stays."""
    path = project / ".codex" / "config.toml"
    if not _inside(path.parent, project):
        return [f"skipped {path}: .codex points outside {project}"]
    tl = codex._tomllib()
    if tl is None:
        return [f"skipped {path}: editing it safely needs Python 3.11 or newer"]
    tables, plugins, lines = _wanted(prof)
    if not tables and not plugins:
        return lines
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    try:
        before = tl.loads(old)
    except Exception as exc:
        return lines + [f"skipped {path}: it does not parse now ({exc}); fix it, then run loadout profile again"]
    added, keys = [], []
    for name, text in tables.items():
        if name in before.get("mcp_servers", {}):
            if before["mcp_servers"][name] != tl.loads(text)["mcp_servers"][name]:
                lines.append(f"mcp {name}: left as is in {path} (a server of that name is already there)")
            continue
        added.append(text)
        lines.append(("would add" if dry_run else "added") + f" mcp {name} to {path}")
    for pid in plugins:
        if pid in before.get("plugins", {}):
            continue
        added.append(f"[plugins.{codex.toml_key(pid)}]\nenabled = true\n")
        keys.append(f"plugins.{codex.toml_key(pid)}.enabled")
        lines.append(("would enable" if dry_run else "enabled") + f" plugin {pid} in {path}")
    if not added or dry_run:
        return lines
    new = (old.rstrip("\n") + "\n\n" if old.strip() else "") + "\n".join(added)
    try:
        after = tl.loads(new)
    except Exception as exc:
        return lines + [f"skipped {path}: the result would not parse ({exc}); nothing written"]
    if codex._without_owned(before, set(tables), keys, tl) != codex._without_owned(after, set(tables), keys, tl):
        return lines + [f"skipped {path}: the edit would change entries loadout does not own; nothing written"]
    from .jsonio import write_atomic
    path.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(path, new)
    return lines


def skills(project: Path, dry_run: bool) -> list[str]:
    """Link each skill in the repo's .claude/skills into .agents/skills (relative, so the link works in every clone)."""
    src_root, dest_root = project / ".claude" / "skills", project / ".agents" / "skills"
    if not src_root.is_dir():
        return []
    if not _inside(dest_root.parent, project):
        return [f"skills not linked: {dest_root.parent} points outside {project}"]
    out = []
    for entry in sorted(src_root.iterdir()):
        if entry.name.startswith(".") or not entry.is_dir():
            continue
        dest = dest_root / entry.name
        if dest.exists() or dest.is_symlink():
            continue
        if dry_run:
            out.append(f"would link skill {entry.name} for Codex -> .agents/skills/{entry.name}")
            continue
        dest_root.mkdir(parents=True, exist_ok=True)
        os.symlink(f"../../.claude/skills/{entry.name}", dest, target_is_directory=True)
        out.append(f"linked skill {entry.name} for Codex -> .agents/skills/{entry.name}")
    return out


def plugins(prof: profiles.Profile, dry_run: bool) -> list[str]:
    """Install the profile's plugins in Codex; one that is not on everywhere stays switched off outside its projects."""
    from . import backup
    from .settings_merge import desired_settings
    _, wanted, _ = _wanted(prof)
    if not wanted:
        return []
    desired = desired_settings()
    markets = {**desired.get("extraKnownMarketplaces", {}), **prof.settings.get("extraKnownMarketplaces", {})}
    routes, missing = codex.plugin_routes({"enabledPlugins": {p: True for p in wanted}, "extraKnownMarketplaces": markets})
    lines = [f"plugin {pid}: no Codex route (its marketplace is not on GitHub)" for pid in missing]
    if dry_run:
        return lines + [f"would install plugin {name} for Codex (from {src})" for src, names in routes.items() for name in names]
    bk = backup.Backup(description=f"loadout profile {prof.name} (Codex)")
    out, installed = codex._install_routes(routes, bk, False, lambda line: None, codex.installed_plugins())
    lines += out
    on = desired.get("enabledPlugins", {})
    for pid in wanted:
        if pid in installed and on.get(pid) is not True:
            codex.add_project_plugin(pid)
    return lines + codex.apply_config(bk)


def _trusted(project: Path) -> bool:
    tl = codex._tomllib()
    path = paths.codex_home() / "config.toml"
    if tl is None or not path.exists():
        return False
    try:
        data = tl.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    entry = data.get("projects", {}).get(str(project.resolve()), {})
    return isinstance(entry, dict) and entry.get("trust_level") == "trusted"


def apply(prof: profiles.Profile, project: Path, install: bool, dry_run: bool) -> list[str]:
    lines = config(prof, project, dry_run) + skills(project, dry_run)
    if install:
        lines += plugins(prof, dry_run)
    if lines and not dry_run and not _trusted(project):
        lines.append(TRUST_NOTE)
    return lines
```

`Backup` writes its manifest on every step, so there is no finish call.

- [ ] **Step 5: Wire into `project.py`**

In `add_profile`, after `_install(...)` and before the notes:

```python
    from . import codex_project, targets
    if targets.codex_enabled():
        for line in codex_project.apply(prof, project, install=install, dry_run=dry_run):
            print(line)
```

Because `skills()` runs after `_install`, skills that a profile command installs into `.claude/skills` (e.g.
`playwright-cli install --skills`) are linked too.

In `init`, replace the last print:

```python
    from . import targets
    if targets.claude_enabled():
        print("next: start Claude Code here and run /loadout:onboard")
    else:
        print("next: start Codex here and ask it to use the loadout:onboard skill")
```

- [ ] **Step 6: Run the tests**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_codex_project.py tests/test_project.py`
Expected: PASS (if `tests/test_project.py` has another name, run `pytest -q -k "init or profile"`).

- [ ] **Step 7: Commit**

```bash
git add cli/loadout/codex.py cli/loadout/codex_project.py cli/loadout/project.py tests/test_codex_project.py
git commit -m "feat(codex): loadout init and profile set up Codex in the repo"
```

---

### Task 3: Codex-only MCP servers and skills appear in adopt

**Files:**
- Modify: `cli/loadout/codex.py` (new `CONFIG_LOCATION`, `user_servers`, `to_claude`, `codex_only_skills`)
- Modify: `cli/loadout/inventory.py` (`_codex_items`, `collect`, `classify`)
- Modify: `cli/loadout/own.py` (`is_codex`, `decision_key`, `options`)
- Test: `tests/test_codex_adopt.py` (new)

**Interfaces:**
- Produces: `codex.CONFIG_LOCATION = "~/.codex/config.toml"`; `codex.user_servers() -> dict[str, dict]` (the user's
  `[mcp_servers.*]` tables, without loadout's owned ones; `{}` without tomllib or when the file does not parse);
  `codex.to_claude(name: str, table: dict) -> dict` (raises `codex.Refused` for keys without a Claude equivalent);
  `codex.codex_only_skills() -> list[Path]`; `own.is_codex(item) -> bool`.
- Items: `Item("mcp", name, detail, codex.CONFIG_LOCATION, {"config": cfg_or_None, "problem": str})` and
  `Item("skill", name, target, str(path), {})` with `path.parent == paths.agents_skills()`.
- Decision keys: `mcp:codex:NAME`, `skill:codex:NAME`.

- [ ] **Step 1: Write the failing tests**

```python
"""adopt sees MCP servers and skills that only Codex has."""
import sys

import pytest

from loadout import codex, inventory, own, paths, targets
from loadout.jsonio import save_json

needs_tomllib = pytest.mark.skipif(sys.version_info < (3, 11), reason="config reads need tomllib")


@pytest.fixture
def codex_on(fake_home, monkeypatch):
    monkeypatch.setattr(targets, "codex_enabled", lambda: True)
    monkeypatch.setattr(codex, "_plugin_servers", lambda: {"codebase-memory-mcp"})


def _config(text):
    cfg = paths.codex_home() / "config.toml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(text)


def test_to_claude_maps_codex_keys():
    assert codex.to_claude("a", {"command": "x", "args": ["-y"], "env": {"K": "v"}, "env_vars": ["TOKEN"]}) == {
        "type": "stdio", "command": "x", "args": ["-y"], "env": {"K": "v", "TOKEN": "${TOKEN}"}}
    assert codex.to_claude("b", {"url": "https://h/mcp", "bearer_token_env_var": "T",
                                 "env_http_headers": {"X-Key": "XK"}, "http_headers": {"X-A": "1"}}) == {
        "type": "http", "url": "https://h/mcp",
        "headers": {"X-A": "1", "Authorization": "Bearer ${T}", "X-Key": "${XK}"}}


def test_to_claude_refuses_what_claude_cannot_express():
    with pytest.raises(codex.Refused, match="startup_timeout_sec"):
        codex.to_claude("a", {"command": "x", "startup_timeout_sec": 30})
    with pytest.raises(codex.Refused, match="tools"):
        codex.to_claude("a", {"command": "x", "tools": {"y": {"approval_mode": "approve"}}})


@needs_tomllib
def test_codex_only_servers_are_items(codex_on):
    _config('[mcp_servers.mine]\ncommand = "m"\n\n[mcp_servers.codebase-memory-mcp]\ncommand = "c"\n\n'
            '[mcp_servers.both]\ncommand = "b"\n\n[mcp_servers.odd]\ncommand = "o"\nstartup_timeout_sec = 9\n')
    save_json(paths.claude_json(), {"mcpServers": {"both": {"command": "b"}}})
    items = {i.name: i for i in inventory.collect(with_versions=False) if i.location == codex.CONFIG_LOCATION}
    assert set(items) == {"mine", "odd"}  # plugin servers and servers Claude Code also has are not Codex-only
    assert items["mine"].extra["config"] == {"type": "stdio", "command": "m"}
    assert items["odd"].extra["config"] is None and "startup_timeout_sec" in items["odd"].extra["problem"]


@needs_tomllib
def test_servers_loadout_wrote_are_not_items(codex_on):
    _config('[mcp_servers.serena]\ncommand = "serena"\n')
    save_json(codex.record_path(), {"tables": {"serena": '[mcp_servers.serena]\ncommand = "serena"\n'}, "keys": {}})
    assert not [i for i in inventory.collect(with_versions=False) if i.location == codex.CONFIG_LOCATION]


def test_codex_only_skills_are_items(codex_on):
    (paths.agents_skills() / "solo").mkdir(parents=True)
    (paths.agents_skills() / "shared").mkdir()
    (paths.claude_home() / "skills" / "shared").mkdir(parents=True)
    names = {i.name for i in inventory.collect(with_versions=False)
             if i.kind == "skill" and own.is_codex(i)}
    assert names == {"solo"}


def test_nothing_from_codex_when_it_is_off(fake_home, monkeypatch):
    monkeypatch.setattr(targets, "codex_enabled", lambda: False)
    (paths.agents_skills() / "solo").mkdir(parents=True)
    assert not [i for i in inventory.collect(with_versions=False) if own.is_codex(i)]


def test_codex_items_have_their_own_keys_and_choices(codex_on):
    mcp = inventory.Item("mcp", "mine", "m", codex.CONFIG_LOCATION, {"config": {"command": "m"}})
    skill = inventory.Item("skill", "solo", "x", str(paths.agents_skills() / "solo"), {})
    assert own.decision_key(mcp) == "mcp:codex:mine"
    assert own.decision_key(skill) == "skill:codex:solo"
    assert own.options(mcp) == ["global", "leave", "remove"]
    assert own.options(skill) == ["global", "leave", "remove"]


def test_codex_items_are_own_tools_not_catalog_matches(codex_on):
    item = inventory.Item("mcp", "serena", "serena", codex.CONFIG_LOCATION, {"config": {"command": "serena"}})
    (verdict,) = inventory.classify([item])
    assert verdict.action == "own"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_codex_adopt.py`
Expected: FAIL (`AttributeError: module 'loadout.codex' has no attribute 'to_claude'`).

- [ ] **Step 3: Implement in `codex.py`**

```python
CONFIG_LOCATION = "~/.codex/config.toml"
_CODEX_KEYS = {"command", "args", "env", "env_vars", "url", "bearer_token_env_var", "http_headers", "env_http_headers"}


def user_servers() -> dict[str, dict]:
    """The user's [mcp_servers.*] tables in ~/.codex/config.toml, without the ones loadout wrote."""
    tl = _tomllib()
    path = paths.codex_home() / "config.toml"
    if tl is None or not path.exists():
        return {}
    try:
        servers = tl.loads(path.read_text(encoding="utf-8")).get("mcp_servers", {})
    except Exception:
        return {}
    owned = set(load_json(record_path()).get("tables", {}))
    return {n: t for n, t in servers.items() if isinstance(t, dict) and n not in owned}


def to_claude(name: str, table: dict) -> dict:
    """A Codex server table in the Claude Code format of the personal mcp.json; variables stay variables."""
    extra = sorted(set(table) - _CODEX_KEYS)
    if extra:
        raise Refused(f"mcp {name}: {', '.join(extra)} has no Claude Code equivalent; leave it in Codex or remove it")
    if "url" in table:
        headers = dict(table.get("http_headers") or {})
        if table.get("bearer_token_env_var"):
            headers["Authorization"] = f"Bearer ${{{table['bearer_token_env_var']}}}"
        headers.update({k: f"${{{v}}}" for k, v in (table.get("env_http_headers") or {}).items()})
        return {"type": "http", "url": table["url"], **({"headers": headers} if headers else {})}
    if not isinstance(table.get("command"), str):
        raise Refused(f"mcp {name}: neither a command nor a url")
    out = {"type": "stdio", "command": table["command"]}
    if table.get("args"):
        out["args"] = list(table["args"])
    env = dict(table.get("env") or {})
    env.update({k: f"${{{k}}}" for k in table.get("env_vars") or []})
    if env:
        out["env"] = env
    return out


def codex_only_skills() -> list[Path]:
    """Skills in ~/.agents/skills that neither loadout linked nor Claude Code has."""
    root = paths.agents_skills()
    if not root.is_dir():
        return []
    ours = {dest.name for dest, _ in skill_links()}
    claude = _skill_names(paths.claude_home() / "skills")
    return [p for p in sorted(root.iterdir())
            if not p.name.startswith(".") and p.name != "synced" and p.name not in ours | claude]
```

- [ ] **Step 4: Implement in `inventory.py`**

```python
def _codex_items() -> list[Item]:
    from . import codex, targets
    if not targets.codex_enabled():
        return []
    items = []
    claude = load_json(paths.claude_json()).get("mcpServers", {})
    skip = codex._plugin_servers() | (set(claude) if isinstance(claude, dict) else set())
    for name, table in codex.user_servers().items():
        if name in skip:
            continue
        try:
            cfg, problem = codex.to_claude(name, table), ""
        except codex.Refused as exc:
            cfg, problem = None, str(exc)
        detail = " ".join([str(table.get("command") or ""), *map(str, table.get("args") or []), str(table.get("url") or "")]).strip()
        items.append(Item("mcp", name, detail, codex.CONFIG_LOCATION, {"config": cfg, "problem": problem}))
    for path in codex.codex_only_skills():
        target = os.readlink(path) if path.is_symlink() else str(path)
        items.append(Item("skill", path.name, str(target), str(path), {}))
    return items
```

Add `*_codex_items()` to `collect` after `*_skill_items()`. In `classify`, right after the "left" check
(`own.decided(left, item) == "leave"`), add:

```python
        if own.is_codex(item):
            out.append(Verdict(item, "own", own.own_reason(item)))
            continue
```

- [ ] **Step 5: Implement in `own.py`**

```python
def is_codex(item: Item) -> bool:
    """An item found in Codex's config (~/.codex/config.toml or ~/.agents/skills), not in Claude Code's."""
    from . import codex
    if item.kind == "mcp":
        return item.location == codex.CONFIG_LOCATION
    return item.kind == "skill" and bool(item.location) and Path(item.location).parent == paths.agents_skills()
```

In `decision_key`, before the final return: `if is_codex(item): return f"{item.kind}:codex:{item.name}"`.
In `options`, first line: `if is_codex(item): return ["global", "leave", "remove"]`.

- [ ] **Step 6: Run the tests**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_codex_adopt.py tests/test_inventory.py tests/test_own.py`
Expected: PASS (if those file names differ, run `pytest -q -k "inventory or own or adopt"`).

- [ ] **Step 7: Commit**

```bash
git add cli/loadout/codex.py cli/loadout/inventory.py cli/loadout/own.py tests/test_codex_adopt.py
git commit -m "feat(adopt): list MCP servers and skills that only Codex has"
```

---

### Task 4: adopt records or removes Codex-only items; drift points to adopt

**Files:**
- Modify: `cli/loadout/codex.py` (new `remove_server`; `drift` text)
- Modify: `cli/loadout/own.py` (`_global_mcp`, `_global_skill`)
- Modify: `cli/loadout/adopt.py` (`_apply_mcp` Codex branch)
- Test: `tests/test_codex_adopt_apply.py` (new)

**Interfaces:**
- Consumes: `codex.CONFIG_LOCATION`, `codex.to_claude`, `own.is_codex`, items from Task 3.
- Produces: `codex.remove_server(name: str, bk) -> str` (saves `config.toml` into the backup, then runs
  `codex mcp remove NAME`; returns the result line).

- [ ] **Step 1: Write the failing tests**

```python
"""adopt: record globally, leave or remove a Codex-only server or skill."""
import json

import pytest

from loadout import adopt, backup, codex, own, paths, runner, targets
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


def _mcp(cfg=None, problem=""):
    return Verdict(Item("mcp", "mine", "m", codex.CONFIG_LOCATION, {"config": cfg, "problem": problem}), "own", "")


def test_record_global_writes_personal_mcp_and_hands_the_table_to_loadout(codex_on, fake_runner):
    bk = backup.Backup(description="t")
    rec = own.record_global(_mcp({"type": "stdio", "command": "m"}), bk)
    assert load_json(paths.personal_root() / "mcp.json")["mcpServers"]["mine"] == {"type": "stdio", "command": "m"}
    rec.machine()
    assert ["codex", "mcp", "remove", "mine"] in fake_runner.calls
    assert any("config.toml" in s.get("label", "") for s in bk.steps)  # saved before the removal


def test_record_global_refuses_with_the_reason(codex_on):
    with pytest.raises(own.Collision, match="startup_timeout_sec"):
        own.record_global(_mcp(None, "mcp mine: startup_timeout_sec has no Claude Code equivalent"),
                          backup.Backup(description="t"))


def test_remove_saves_config_then_runs_codex_mcp_remove(codex_on, fake_runner):
    bk = backup.Backup(description="t")
    v = _mcp({"type": "stdio", "command": "m"})
    v.action = "remove"
    out = adopt.apply([v], bk, confirm_cmds=False)
    assert ["codex", "mcp", "remove", "mine"] in fake_runner.calls
    assert any("mine" in l for l in out)


def test_failed_removal_is_reported(codex_on, fake_runner):
    fake_runner.responses[("codex", "mcp", "remove")] = runner.Result(1, "", "boom")
    assert "failed" in codex.remove_server("mine", backup.Backup(description="t"))


def test_record_global_skill_copies_and_relinks(codex_on):
    src = paths.agents_skills() / "solo"
    src.mkdir(parents=True)
    (src / "SKILL.md").write_text("---\nname: solo\ndescription: d\n---\n")
    v = Verdict(Item("skill", "solo", str(src), str(src), {}), "own", "")
    rec = own.record_global(v, backup.Backup(description="t"))
    assert (paths.personal_root() / "skills" / "solo" / "SKILL.md").exists()
    lines = rec.machine()
    assert not src.exists() or src.is_symlink()
    assert any("~/.agents/skills/solo" in l for l in lines)


def test_drift_points_codex_only_items_to_adopt(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(targets, "claude_enabled", lambda: True)
    fake_runner.responses[("codex", "mcp", "list")] = runner.Result(0, json.dumps([{"name": "solo"}]), "")
    monkeypatch.setattr(codex, "_plugin_servers", lambda: set())
    lines = codex.drift()
    assert lines == ['MCP server "solo" only in Codex (record it with loadout adopt, then both get it)']
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_codex_adopt_apply.py`
Expected: FAIL (`Collision: mcp mine: only user-scope servers in ~/.claude.json can be recorded`, and `remove_server` missing).

- [ ] **Step 3: Implement `codex.remove_server` and the drift text**

```python
def remove_server(name: str, bk) -> str:
    """Remove a user's server from ~/.codex/config.toml through Codex itself; the file is saved first (restore
    puts it back)."""
    path = paths.codex_home() / "config.toml"
    if path.exists():
        bk.save_copy(path, f"Codex config.toml before removing mcp {name}")
    res = runner.run(["codex", "mcp", "remove", name], timeout=120)
    return f"mcp {name}: removed from Codex" if res.ok else f"mcp {name}: failed: {_tail(res)}"
```

In `drift`, change both Codex-only messages to `(record it with loadout adopt, then both get it)`.

- [ ] **Step 4: Implement in `own.py`**

`_global_mcp`: replace the location check and add the Codex machine step:

```python
def _global_mcp(v: Verdict, bk) -> Recorded:
    name, original = v.item.name, v.item.extra.get("config", {})
    if is_codex(v.item):
        if original is None:
            raise Collision(v.item.extra.get("problem") or f"mcp {name}: cannot be recorded")
    elif v.item.location != "~/.claude.json":
        raise Collision(f"mcp {name}: only user-scope servers in ~/.claude.json can be recorded")
    new, lines = _secret_free(name, original)
    # … (unchanged: _refuse_if_secret, path, change, _edit_json, secrets.append_env) …

    def codex_machine() -> list[str]:
        from . import codex, personal_mcp, targets
        out = [codex.remove_server(name, bk)]  # loadout writes its own table from the personal layer next
        out += codex.apply_config(bk)
        if targets.claude_enabled():
            out += personal_mcp.apply_mcp()
        return out

    # … (machine() unchanged) …
    return Recorded(True, [f"mcp {name}: recorded in {path}" + (" (secrets in secrets.env)" if lines else "")],
                    codex_machine if is_codex(v.item) else machine)
```

`_global_skill`: the machine step names the folder it came from and relinks for both agents:

```python
    def machine() -> list[str]:
        from . import codex, targets
        where = "~/.agents/skills" if is_codex(v.item) else "~/.claude/skills"
        bk.move(src, f"skill {name} (replaced by a link to your personal layer)", replace=True)
        out = [f"skill {name}: moved to {dest}; {where}/{name} links to it"]
        if targets.codex_enabled():
            out += codex.apply_skills(bk)  # adopt runs link.link_all for Claude Code after the machine steps
        return out
```

- [ ] **Step 5: Implement the remove branch in `adopt._apply_mcp`**

At the top of `_apply_mcp`:

```python
    from . import codex, own
    if own.is_codex(v.item):
        line = codex.remove_server(v.item.name, bk)
        return NotDone(line) if ": failed:" in line else line
```

- [ ] **Step 6: Run the tests**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_codex_adopt_apply.py tests/test_codex_skills_drift.py`
Expected: PASS. Update the existing drift test's expected "only in Codex" wording if it asserts the old text.

- [ ] **Step 7: Full suite and commit**

Run: `uv run --python 3.12 --with pytest pytest -q`
Expected: all pass (last baseline: 1453 passed, 2 skipped, plus the new tests).

```bash
git add cli/loadout/codex.py cli/loadout/own.py cli/loadout/adopt.py tests/
git commit -m "feat(adopt): record or remove Codex-only servers and skills"
```

---

### Task 5: Docs

**Files:**
- Modify: `docs/how-to/codex.md` (parity table rows for projects and adopt; "Projects" section with the trust step and project-only plugins; adopt section; the dbhub limit)
- Modify: the reference pages for `init`, `profile` and `adopt` (find them with `grep -rln "loadout profile\|loadout adopt" docs/reference`)
- Modify: `docs/superpowers/specs/2026-10-12-codex-target-design.md` (status line: PR 2 built; the rulings from this plan's ledger)
- Modify: `.serena/memories/` only if a summary or link became wrong

- [ ] **Step 1: Write the docs** — facts to state, each once:
  - `loadout profile <name>` with Codex on: servers go into `.codex/config.toml` (only added, never changed; a
    disabled server gets `enabled = false`); `.claude/skills/*` are linked into `.agents/skills/`; plugins are
    installed in Codex and switched on only in that project (`[plugins."x@m"] enabled = false` at user level, kept so
    even after `codex plugin add`; to have one everywhere, enable it in the personal layer's settings).
  - Codex loads a repo's `.codex/config.toml` only in a trusted project; loadout prints the step, never trusts for you.
  - A server whose args need `${VAR}` (dbhub) is skipped for Codex with the reason.
  - `loadout adopt` lists Codex-only servers and skills (global, leave, remove); "global" writes the personal layer
    and hands the table to loadout; servers with Codex-only keys (`tools`, timeouts) can only be left or removed;
    "remove" saves `config.toml` into the backup first, `loadout restore` puts it back.
- [ ] **Step 2: Check links** — every relative link in the touched files resolves (`uv run --python 3.12 --with pytest pytest -q tests/test_docs*.py` if such tests exist, else check by hand).
- [ ] **Step 3: Commit**

```bash
git add docs .serena
git commit -m "docs(codex): projects and adopt for Codex"
```
