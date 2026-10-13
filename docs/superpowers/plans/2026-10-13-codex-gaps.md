# Hardening 4b: Codex Gaps Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Six behaviours documented as Codex limits work for Codex: plugin switch-off, `autoUpdate`, instruction-block refresh, advisor on `apply_patch`, the plaintext-secret scan, the WSL `codex` check.

**Architecture:** Small changes in existing flows: `codex.py` (owned plugin keys, marketplace refresh, block refresh), `maintenance.session_start`, `hooks/advisor.py`, `secrets.py` + `adopt.py`, `wsl.py`; then docs.

**Tech Stack:** Python 3.11+ standard library, pytest.

**Spec:** `docs/superpowers/specs/2026-10-13-codex-gaps-design.md`

## Global Constraints

- Work only in the worktree `.claude/worktrees/codex-gaps` (branch `feat/codex-gaps`); the real launcher runs the main checkout.
- Tests: `uv run --python 3.12 --with pytest pytest -q`; `fake_home`/`fake_runner`; never the real `~/.claude`, `~/.codex`, `~/.config/loadout`, `~/.local/state`; never real `claude`/`codex`.
- loadout changes only what it recorded as its own in `~/.codex/config.toml` and `~/.codex/AGENTS.md`; no secret value printed or written.
- Conventional Commits; no AI attribution.

## Review Focus

1. A plugin switched off for Claude Code that you installed in Codex yourself, outside loadout's desired settings: untouched. (Task 1 test.)
2. You edited loadout's `enabled` line by hand: left as is, never overwritten. (Task 1 test.)
3. `~/.codex/AGENTS.md` with your own text around loadout's block: refresh changes only the block, byte for byte. (Task 3 test.)
4. An `apply_patch` adding a plan with a relative path and a `cwd`: recorded under the absolute path. (Task 4 test.)
5. A Codex server whose secret sits in `args`: reported, value never printed. (Task 5 test.)

---

### Task 1: Turning a plugin off reaches Codex

**Files:**
- Modify: `cli/loadout/codex.py` (`desired_keys`, new `_plugin_switches`)
- Test: `tests/test_codex_plugin_switch.py` (create)

**Interfaces:**
- Produces: `codex._plugin_switches() -> list[tuple[tuple, str, bool, bool]]`, used by `desired_keys()`.

- [ ] **Step 1: Write the failing tests**

```python
"""A plugin switched off for Claude Code is switched off in Codex too (owned `enabled` key)."""
import json

from loadout import backup, codex, paths, runner, settings_merge


def _setup(fake_runner, monkeypatch, enabled, installed):
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: {"enabledPlugins": enabled})
    fake_runner.responses[("codex", "plugin", "list")] = runner.Result(
        0, json.dumps({"installed": [{"pluginId": p} for p in installed], "available": []}), "")


def _config():
    p = paths.codex_home() / "config.toml"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _apply():
    return codex.apply_config(backup.Backup(description="t"))


def test_switched_off_and_installed_is_switched_off_in_codex(fake_home, fake_runner, monkeypatch):
    _setup(fake_runner, monkeypatch, {"x@m": False}, ["x@m"])
    _apply()
    assert '[plugins."x@m"]' in _config() and "enabled = false" in _config()
    assert 'plugins."x@m".enabled' in codex.read_record()["keys"]


def test_switched_on_again_the_owned_line_reads_true(fake_home, fake_runner, monkeypatch):
    _setup(fake_runner, monkeypatch, {"x@m": False}, ["x@m"])
    _apply()
    _setup(fake_runner, monkeypatch, {"x@m": True}, ["x@m"])
    _apply()
    assert "enabled = true" in _config() and "enabled = false" not in _config()


def test_your_own_edit_of_the_line_is_left_alone(fake_home, fake_runner, monkeypatch):
    _setup(fake_runner, monkeypatch, {"x@m": False}, ["x@m"])
    _apply()
    path = paths.codex_home() / "config.toml"
    path.write_text(_config().replace("enabled = false", "enabled = true # mine"), encoding="utf-8")
    lines = _apply()
    assert "enabled = true # mine" in _config()
    assert any("your value" in line for line in lines)


def test_not_installed_or_unknown_list_writes_nothing(fake_home, fake_runner, monkeypatch):
    _setup(fake_runner, monkeypatch, {"x@m": False}, [])
    _apply()
    assert "plugins" not in _config()
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: {"enabledPlugins": {"x@m": False}})
    fake_runner.responses[("codex", "plugin", "list")] = runner.Result(1, "", "boom")
    _apply()
    assert "plugins" not in _config()


def test_a_plugin_you_installed_yourself_is_untouched(fake_home, fake_runner, monkeypatch):
    _setup(fake_runner, monkeypatch, {"x@m": False}, ["x@m", "mine@else"])
    _apply()
    assert "mine@else" not in _config()
```

- [ ] **Step 2: Run them** — `uv run --python 3.12 --with pytest pytest -q tests/test_codex_plugin_switch.py`. Expected: FAIL (no `[plugins."x@m"]`).

- [ ] **Step 3: Implement** in `cli/loadout/codex.py`, after `add_project_plugin`:

```python
def _plugin_switches() -> list[tuple[tuple, str, bool, bool]]:
    """`enabled` keys for plugins loadout manages: off in Codex when switched off for Claude Code and installed
    in Codex; back to true when switched on again and loadout owns the line. Never guesses: no list, no key."""
    from .settings_merge import desired_settings
    enabled = get_dict(desired_settings(), "enabledPlugins")
    projects = set(project_plugins())
    owned = read_record()["keys"]
    keys = [(("plugins", pid), "enabled", True, False) for pid, on in enabled.items()
            if on is True and isinstance(pid, str) and pid not in projects
            and _dotted(("plugins", pid), "enabled") in owned]
    off = [pid for pid, on in enabled.items() if on is False and isinstance(pid, str) and "@" in pid
           and pid not in projects]
    if off:
        listed = installed_plugins()
        if listed is not None:
            keys += [(("plugins", pid), "enabled", False, False) for pid in off if pid in listed]
    return keys
```

In `desired_keys()`, before `return keys`: `keys += _plugin_switches()`.

- [ ] **Step 4: Run** the new tests, then `tests/test_codex_config.py` and the full suite. Expected: PASS. If a test elsewhere counts `codex plugin list` calls or config lines, adjust only the test's expectation and ledger it.

- [ ] **Step 5: Commit** — `git add cli/loadout/codex.py tests/test_codex_plugin_switch.py && git commit -m "feat(codex): switching a plugin off reaches Codex as an owned enabled = false"`

---

### Task 2: `autoUpdate: false` holds for the Codex refresh

**Files:**
- Modify: `cli/loadout/codex.py` (`_install_routes`, `apply_plugins`, `apply_all`)
- Test: `tests/test_codex_plugins.py` (append)

**Interfaces:**
- Produces: `apply_plugins(bk, refresh=False, say=None, auto=False)`; `_install_routes(routes, bk, refresh, say, listed, frozen=frozenset())`.

- [ ] **Step 1: Write the failing tests** (append; reuse the module's `_fake` and `SETTINGS`)

```python
def _frozen_settings():
    markets = json.loads(json.dumps(SETTINGS["extraKnownMarketplaces"]))
    markets["agent-loadout"]["autoUpdate"] = False
    return {"enabledPlugins": {"loadout@agent-loadout": True, "fresh@agent-loadout": True},
            "extraKnownMarketplaces": markets}


def test_the_automatic_refresh_skips_a_marketplace_set_to_no_auto_update(fake_home, fake_runner, monkeypatch):
    from loadout import settings_merge
    monkeypatch.setattr(settings_merge, "desired_settings", _frozen_settings)
    _fake(fake_runner, installed=["loadout@agent-loadout"])
    fake_runner.responses[("codex", "plugin", "marketplace", "add", "jonasyr/agent-loadout")] = runner.Result(
        0, json.dumps({"marketplaceName": "agent-loadout", "alreadyAdded": True}), "")
    codex.apply_plugins(backup.Backup(description="t"), refresh=True, auto=True)
    assert ["codex", "plugin", "marketplace", "upgrade", "agent-loadout"] not in fake_runner.calls
    assert ["codex", "plugin", "add", "loadout@agent-loadout", "--json"] not in fake_runner.calls
    assert ["codex", "plugin", "add", "fresh@agent-loadout", "--json"] in fake_runner.calls, "a first install still happens"


def test_an_explicit_update_still_updates_it(fake_home, fake_runner, monkeypatch):
    from loadout import settings_merge
    monkeypatch.setattr(settings_merge, "desired_settings", _frozen_settings)
    _fake(fake_runner, installed=["loadout@agent-loadout"])
    fake_runner.responses[("codex", "plugin", "marketplace", "add", "jonasyr/agent-loadout")] = runner.Result(
        0, json.dumps({"marketplaceName": "agent-loadout", "alreadyAdded": True}), "")
    codex.apply_plugins(backup.Backup(description="t"), refresh=True)
    assert ["codex", "plugin", "marketplace", "upgrade", "agent-loadout"] in fake_runner.calls


def test_apply_all_refresh_honours_auto_update(fake_home, fake_runner, monkeypatch):
    seen = []
    monkeypatch.setattr(codex, "apply_plugins", lambda bk, refresh=False, say=None, auto=False: seen.append((refresh, auto)) or [])
    monkeypatch.setattr(codex, "apply_instructions", lambda bk: "ok")
    monkeypatch.setattr(codex, "apply_config", lambda bk: [])
    monkeypatch.setattr(codex, "apply_skills", lambda bk: [])
    codex.apply_all(backup.Backup(description="t"), refresh=True)
    assert seen == [(True, True)]
```

(If `apply_all` calls other helpers that need stubbing, stub them the same way; keep the assertion on `seen`.)

- [ ] **Step 2: Run** — `uv run --python 3.12 --with pytest pytest -q tests/test_codex_plugins.py`. Expected: FAIL (`unexpected keyword argument 'auto'`).

- [ ] **Step 3: Implement**

`_install_routes` signature gets `frozen: frozenset = frozenset()`; inside:

```python
        elif refresh and market not in frozen:
            runner.run(["codex", "plugin", "marketplace", "upgrade", market], timeout=900)
        for name in plugins:
            pid = f"{name}@{market}"
            if pid in installed and (not refresh or market in frozen):
                continue
```

(The progress `total` keeps counting as before; a skipped refresh just ends below it, which `min(step, total)` already allows.)

`apply_plugins`:

```python
def apply_plugins(bk, refresh: bool = False, say=None, auto: bool = False) -> list[str]:
    """say: called with a progress line before each slow step. auto: an automatic refresh (the daily sync), which
    leaves marketplaces set to `autoUpdate: false` as they are, as Claude Code does; `loadout update` passes False."""
    say = say or (lambda line: None)
    from .settings_merge import desired_settings
    desired = desired_settings()
    routes, missing = plugin_routes(desired)
    frozen = frozenset(name for name, cfg in get_dict(desired, "extraKnownMarketplaces").items()
                       if auto and get_dict(cfg).get("autoUpdate") is False)
    lines = [f"plugin {pid}: no Codex route (its marketplace is not on GitHub)" for pid in missing]
    return lines + _install_routes(routes, bk, refresh, say, installed_plugins(), frozen)[0]
```

(`get_dict(cfg)` on a non-dict returns `{}`; check its signature in `jsonio.py` and use `get_dict({"x": cfg}, "x")` if it requires a key.)

`apply_all`: pass `auto=refresh` in its `apply_plugins(...)` call.

- [ ] **Step 4: Run** the file, then the full suite. Expected: PASS.

- [ ] **Step 5: Commit** — `git add cli/loadout/codex.py tests/test_codex_plugins.py && git commit -m "feat(codex): the automatic refresh honours autoUpdate: false"`

---

### Task 3: The instruction block follows hand edits at the next session

**Files:**
- Modify: `cli/loadout/codex.py` (new `refresh_instructions`), `cli/loadout/maintenance.py` (`session_start`)
- Test: `tests/test_codex_block_refresh.py` (create)

**Interfaces:**
- Produces: `codex.refresh_instructions() -> str | None`.

- [ ] **Step 1: Write the failing tests**

```python
"""A hand edit of a rule or me.md reaches Codex's block at the next session start."""
import json

from loadout import codex, maintenance, paths


def _codex_on():
    paths.personal_root().mkdir(parents=True, exist_ok=True)
    (paths.personal_root() / "targets.json").write_text(json.dumps({"claude": True, "codex": True}))


def _agents():
    return paths.codex_home() / "AGENTS.md"


def _seed(text_before="my own notes\n", text_after="\nmore of mine\n"):
    _agents().parent.mkdir(parents=True, exist_ok=True)
    _agents().write_text(text_before + codex.START + "\nold block\n" + codex.END + text_after, encoding="utf-8")


def test_a_stale_block_is_rewritten_and_your_text_kept(fake_home, monkeypatch):
    _codex_on()
    _seed()
    monkeypatch.setattr(codex, "render_instructions", lambda: f"{codex.START}\nnew rules\n{codex.END}\n")
    maintenance.session_start(0)
    text = _agents().read_text(encoding="utf-8")
    assert "new rules" in text and "old block" not in text
    assert text.startswith("my own notes\n") and text.endswith("\nmore of mine\n")


def test_nothing_happens_with_codex_off_without_a_block_or_with_broken_markers(fake_home, monkeypatch):
    monkeypatch.setattr(codex, "render_instructions", lambda: f"{codex.START}\nnew\n{codex.END}\n")
    _seed()
    assert codex.refresh_instructions() is None  # Codex off (no targets.json)
    _codex_on()
    _agents().write_text("only mine\n", encoding="utf-8")
    assert codex.refresh_instructions() is None and _agents().read_text() == "only mine\n"
    _agents().write_text(codex.START + "\nx\n" + codex.START + "\n", encoding="utf-8")
    before = _agents().read_text()
    assert codex.refresh_instructions() is None and _agents().read_text() == before
    _agents().unlink()
    assert codex.refresh_instructions() is None and not _agents().exists()
```

- [ ] **Step 2: Run** — expected FAIL (`AttributeError: refresh_instructions`).

- [ ] **Step 3: Implement** in `cli/loadout/codex.py` after `apply_instructions`:

```python
def refresh_instructions() -> str | None:
    """At a session start: rewrite loadout's block in ~/.codex/AGENTS.md when a rule or me.md changed by hand.
    Only an existing, balanced block, only with Codex on; never creates the file or a block (bootstrap does)."""
    from . import targets
    if not targets.codex_enabled():
        return None
    path = paths.codex_home() / "AGENTS.md"
    try:
        old = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if START not in old:
        return None
    new = splice(old, render_instructions())
    if new is None or new == old:
        return None
    from .jsonio import write_atomic
    write_atomic(path, new)
    return f"refreshed loadout's block in {_tilde(path)}"
```

In `maintenance.session_start`, before `return out`:

```python
    try:  # a hand edit of a rule or me.md reaches Codex at the next session (Claude Code reads the files live)
        from . import codex
        codex.refresh_instructions()
    except Exception:  # never break a session start
        pass
```

- [ ] **Step 4: Run** the file and the full suite. Expected: PASS.

- [ ] **Step 5: Commit** — `git add cli/loadout/codex.py cli/loadout/maintenance.py tests/test_codex_block_refresh.py && git commit -m "feat(codex): hand edits of the rules reach Codex's block at the next session"`

---

### Task 4: The execution advisor sees Codex `apply_patch` edits

**Files:**
- Modify: `plugins/loadout/hooks/advisor.py` (`record`, new `PATCH_FILE`, `_edited`)
- Test: `tests/test_advisor.py` (append)

- [ ] **Step 1: Write the failing tests** (append; reuse the file's helpers for loading the hook module and the fake HOME, e.g. `fake_home_env` and the plan text it already uses; read the top of `tests/test_advisor.py` first)

```python
PLAN = "# X Implementation Plan\n\n- [ ] **Step 1: do it**\n"


def test_a_codex_apply_patch_plan_is_recorded(fake_home_env, tmp_path):
    advisor = _load_hook()  # the file's existing helper that imports plugins/loadout/hooks/advisor.py
    plan = tmp_path / "docs" / "superpowers" / "plans" / "2026-10-13-x.md"
    plan.parent.mkdir(parents=True)
    plan.write_text(PLAN)
    patch = f"*** Begin Patch\n*** Add File: docs/superpowers/plans/2026-10-13-x.md\n+{PLAN}*** End Patch\n"
    advisor.record({"session_id": "s", "cwd": str(tmp_path), "tool_input": {"command": patch}})
    data = json.loads((fake_home_env / ".local/state/loadout/advisor-pending.json").read_text())
    assert [p["path"] for p in data["plans"]] == [str(plan)]


def test_advisor_and_typecheck_read_the_same_patch_headers():
    import importlib.util
    hooks = paths.kit_root() / "plugins" / "loadout" / "hooks"
    mods = []
    for name in ("advisor", "typecheck"):
        spec = importlib.util.spec_from_file_location(name, hooks / f"{name}.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mods.append(mod)
    assert mods[0].PATCH_FILE.pattern == mods[1].PATCH_FILE.pattern
```

(If the file has no `_load_hook`, load it with `importlib` as in the second test; adapt names to the file's existing fixtures and ledger the choice.)

- [ ] **Step 2: Run** — expected FAIL (nothing recorded; `PATCH_FILE` missing).

- [ ] **Step 3: Implement** in `plugins/loadout/hooks/advisor.py`:

```python
PATCH_FILE = re.compile(r"^\*\*\* (?:Add|Update) File: (.+?)\s*$", re.M)  # the same headers as hooks/typecheck.py


def _edited(payload: dict, tool_input: dict) -> list[str]:
    """The files an edit wrote: Claude Code names one (file_path); a Codex apply_patch names them in its headers."""
    names = PATCH_FILE.findall(tool_input["command"]) if isinstance(tool_input.get("command"), str) else []
    if isinstance(tool_input.get("file_path"), str):
        names.append(tool_input["file_path"])
    cwd = payload.get("cwd")
    return [n if os.path.isabs(n) or not isinstance(cwd, str) else os.path.join(cwd, n) for n in names]
```

`record`: replace the single `path = tool_input.get("file_path")` … flow with a loop over `_edited(payload, tool_input)`; for each path keep the existing checks (`is_plan_path`, `_read`, `looks_like_plan`) and the existing entry update; save once at the end if any plan was recorded.

- [ ] **Step 4: Run** `tests/test_advisor.py`, then the full suite. Expected: PASS.

- [ ] **Step 5: Commit** — `git add plugins/loadout/hooks/advisor.py tests/test_advisor.py && git commit -m "feat(advisor): plans written through Codex apply_patch trigger the nudge"`

---

### Task 5: The plaintext-secret scan covers Codex

**Files:**
- Modify: `cli/loadout/secrets.py` (new `scan_codex`), `cli/loadout/adopt.py` (findings line)
- Test: `tests/test_codex_secret_scan.py` (create)

**Interfaces:**
- Produces: `secrets.scan_codex() -> list[Finding]`.

- [ ] **Step 1: Write the failing tests**

```python
"""adopt's plaintext-secret scan looks at ~/.codex/config.toml too (report only)."""
import json

from loadout import adopt, paths, secrets

TOKEN = "ghp_" + "Z" * 36  # built here so the repo's secret scan does not flag this file


def _config(text):
    p = paths.codex_home() / "config.toml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_a_plaintext_secret_in_a_codex_server_is_found(fake_home):
    _config(f'[mcp_servers.gh]\ncommand = "gh-mcp"\nargs = ["--token={TOKEN}"]\n[mcp_servers.gh.env]\nGITHUB_TOKEN = "{TOKEN}"\n')
    found = secrets.scan_codex()
    assert {(f.server, f.field) for f in found} == {("gh", "env"), ("gh", "args")}
    assert all(f.location == "~/.codex/config.toml" and not f.fixable for f in found)


def test_a_file_that_does_not_parse_gives_no_findings(fake_home):
    _config("[mcp_servers.gh\n")
    assert secrets.scan_codex() == []


def test_codex_only_adopt_reports_it_without_the_value(fake_home, fake_runner, capsys):
    paths.personal_root().mkdir(parents=True)
    (paths.personal_root() / "targets.json").write_text(json.dumps({"claude": False, "codex": True}))
    _config(f'[mcp_servers.gh]\ncommand = "gh-mcp"\n[mcp_servers.gh.env]\nGITHUB_TOKEN = "{TOKEN}"\n')
    adopt.run(False, None, set(), False, ask=lambda q: "", with_versions=False, interactive=False)
    text = capsys.readouterr().out
    assert "~/.codex/config.toml" in text and TOKEN not in text
```

(Check `adopt.run`'s signature in `cli/loadout/adopt.py` first and match it; if a dry run of adopt does not print findings without `--verbose`, set `out.VERBOSE = True` via `monkeypatch` and ledger it.)

- [ ] **Step 2: Run** — expected FAIL (`AttributeError: scan_codex`).

- [ ] **Step 3: Implement** in `cli/loadout/secrets.py` after `scan_all`:

```python
def scan_codex() -> list[Finding]:
    """Plaintext secrets in the user's own [mcp_servers.*] tables of ~/.codex/config.toml. Report only: those
    sections are not loadout's, so the fix is by hand (the value into secrets.env, its name into env_vars)."""
    from . import codex
    servers = {name: {"env": t.get("env"), "headers": t.get("http_headers"), "args": t.get("args"), "url": t.get("url")}
               for name, t in codex.user_servers().items()}
    return scan({"mcpServers": servers}, "~/.codex/config.toml", fixable=False)
```

`cli/loadout/adopt.py`, the findings line:

```python
    findings = (secrets.scan_all() if targets.claude_enabled() else []) \
        + (secrets.scan_codex() if targets.codex_enabled() else [])  # each agent's own files, only when it is on
```

In the two places that word an unfixable finding ("move it to secrets.env by hand"), append ` (Codex: name it in env_vars)` when `f.location == "~/.codex/config.toml"`.

- [ ] **Step 4: Run** the file, then the full suite. Expected: PASS.

- [ ] **Step 5: Commit** — `git add cli/loadout/secrets.py cli/loadout/adopt.py tests/test_codex_secret_scan.py && git commit -m "feat(adopt): the plaintext-secret scan covers ~/.codex/config.toml"`

---

### Task 6: WSL checks `codex` too

**Files:**
- Modify: `cli/loadout/wsl.py` (`problems`)
- Test: `tests/test_wsl.py` (append)

- [ ] **Step 1: Write the failing test** (append; reuse the `mnt` fixture and `_prefix`)

```python
def test_codex_from_windows_is_named_when_codex_is_on(fake_home, fake_runner, mnt, tmp_path):
    import json
    from loadout import paths
    fake_runner.paths["codex"] = str(mnt / "c" / "Users" / "me" / "codex.exe")
    assert not any("codex" in p for p, _ in wsl.problems(2, tmp_path, mount=_prefix(mnt)))  # Codex off
    paths.personal_root().mkdir(parents=True)
    (paths.personal_root() / "targets.json").write_text(json.dumps({"claude": True, "codex": True}))
    assert any("codex resolves to the Windows program" in p for p, _ in wsl.problems(2, tmp_path, mount=_prefix(mnt)))
```

- [ ] **Step 2: Run** — expected FAIL.

- [ ] **Step 3: Implement** in `wsl.problems`: replace `for tool in LINUX_TOOLS:` with `for tool in LINUX_TOOLS + (("codex",) if _codex_on() else ()):` and add

```python
def _codex_on() -> bool:
    from . import targets
    try:
        return targets.codex_enabled()
    except Exception:  # a damaged targets.json: the check stays as before
        return False
```

- [ ] **Step 4: Run** `tests/test_wsl.py` and the full suite. Expected: PASS.

- [ ] **Step 5: Commit** — `git add cli/loadout/wsl.py tests/test_wsl.py && git commit -m "feat(wsl): check codex for a Windows binary when Codex is on"`

---

### Task 7: Docs

**Files:** the pages listed in the spec §7, `docs/adr/0024-codex-parity-update-model.md`, `.superpowers/handoff/2026-10-13-hardening-backlog.md` (local, not committed).

- [ ] **Step 1:** `grep -rn -i "claude code only\|only in claude code\|reaches claude code only\|ignores it\|loadout configure set target codex on\|apply_patch\|does not see plans\|not ~/.codex/config.toml\|skips codex\|wsl.*codex" docs --include=*.md | grep -v superpowers` and read each hit.
- [ ] **Step 2:** For each of the six behaviours, rewrite the limit sentence to the new behaviour (one home per fact; link it from elsewhere): plugin off → `docs/reference/personal-layer.md` and `included-tools.md`; autoUpdate → `docs/explanation/security-and-trust.md` (opting out); block refresh → `personal-layer.md`, `set-preferences.md`, `included-tools.md`; advisor → `docs/explanation/execution-advisor.md`, `docs/reference/hooks.md`; secret scan → `security-and-trust.md`, `docs/how-to/your-own-tools.md`; WSL → `docs/how-to/wsl.md`. `docs/how-to/codex.md` and `troubleshooting.md` drop what no longer applies.
- [ ] **Step 3:** ADR 0024 Consequences: add "Switching a plugin off reaches Codex as an owned `enabled = false`" and "The automatic Codex refresh honours `autoUpdate: false`; `loadout update` updates all".
- [ ] **Step 4:** Remove the six entries from the backlog file.
- [ ] **Step 5:** `uv run --python 3.12 --with pytest pytest -q tests/test_docs_links.py tests/test_readme.py` then the full suite; commit `docs: the Codex gaps are closed`.
