# Serena as documented (Codex) Implementation Plan — PR A

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In Codex, loadout sets Serena up exactly like `serena setup codex` and never twice: one `serena` server (or the user's, under any name) and the six official Serena hooks exactly once, as owned entries in `~/.codex/hooks.json`.

**Architecture:** `codex.SERENA` matches Serena's documented table; a new `codex.user_serena()` spots a user's Serena server under any name and makes `desired_tables()` skip loadout's. A new module `cli/loadout/codex_hooks.py` owns Serena's entries in `~/.codex/hooks.json` with the config.toml contract (exact-text record, parse guard, backup, user bytes untouched); `apply_all` runs it. The plugin's `codex.json` drops its Serena hooks.

**Tech Stack:** Python 3.11+ standard library (`cli/loadout/`), pytest.

**Spec:** `docs/superpowers/specs/2026-10-15-codex-anywhere-design.md` (section "PR A")

## Global Constraints

- Standard library only in `cli/loadout/`; tests use `fake_home` and `fake_runner`; never the real `~/.codex`.
- loadout changes only what it recorded as its own; the user's text stays byte for byte; backup before the first change; `loadout restore` reverts it.
- Official Serena Codex config: `startup_timeout_sec = 15`, `command = "serena"`, `args = ["start-mcp-server", "--project-from-cwd", "--context=codex"]`.
- Official Serena Codex hooks (`--client=codex`): PreToolUse `Bash` → `remind` (timeout 5); PreToolUse `^mcp__serena__` → `plan-guard`; PostToolUse `^mcp__serena__.*$` → `reset`; SessionStart `startup|resume` → `activate`; UserPromptSubmit → `plan-context`; SessionEnd → `cleanup` (timeout 3). loadout requires Codex ≥ 0.161, so always SessionEnd; a user's `cleanup` under Stop also counts as present.
- With Codex off nothing reads or writes `~/.codex`. Claude Code is unchanged.
- Conventional Commits; git as `/usr/bin/git`. Tests: `uv run --python 3.12 --with pytest pytest -q`.

## Review Focus

- A user `hooks.json` that is valid JSON but not in loadout's own format (other indentation, comments are not JSON): loadout must not rewrite it; it reports the missing entries with the exact snippet (Task 3 test).
- A user table `[mcp_servers.serena-mine]` running `uvx --from git+https://github.com/oraios/serena serena start-mcp-server …`: counts as Serena, no second `serena` (Task 2 test).
- loadout wrote `[mcp_servers.serena]` on an earlier run, then the user adds their own Serena under another name: loadout's table is removed, not left as a duplicate (Task 2 test).
- `serena-hooks` not on PATH: no hook entries written, and loadout's earlier entries are removed (Task 3 test).
- The user edited one of loadout's hook entries: it becomes theirs (dropped from the record, never rewritten), like a changed config.toml table (Task 3 test).

---

### Task 1: Verify the two Codex facts PR A depends on

**Files:** none (findings go to the ledger as `Task 1: Ruling:` lines and into the docs in Task 5)

- [ ] **Step 1:** Read Codex's source or docs (Context7 `openai/codex`, or github.com/openai/codex `codex-rs/hooks` and `codex-rs/core` config loading; learn.chatgpt.com/docs/hooks) and answer:
  1. The exact JSON shape of `~/.codex/hooks.json` (top-level `hooks` object keyed by event name as in the plugin file? matcher field name? `timeout` in seconds?).
  2. The key format under `[hooks.state]` in `config.toml` for a hook from `~/.codex/hooks.json` (the plugin form is `plugin:file:event_snake:group:hook`, see `codex.HOOK_PLUGIN`).
  3. Whether Codex starts the MCP servers a plugin declares (`.codex-plugin/plugin.json` → `mcpServers: ./.mcp.json`), and under what name.
- [ ] **Step 2:** Rulings: if (1) differs from the plugin shape, Task 3's `_group()` and `_present()` follow Codex's shape. If (2) is found, Task 4 adds those keys to `hooks_status`; if not, Task 4 keeps `hooks_status` on the plugin keys and prints the `/hooks` step after every hooks.json change. If (3) is yes, Task 4 removes `serena` from the Codex route (a Codex-only `.mcp.json` without Serena, `plugins/loadout/.codex-mcp.json`, referenced from `.codex-plugin/plugin.json`).

### Task 2: Serena's server as documented, and a user's Serena under any name

**Files:**
- Modify: `cli/loadout/codex.py` (`SERENA`, `toml_value`, new `user_serena`, `desired_tables`, `checks`)
- Test: `tests/test_codex_serena.py` (create)

**Interfaces:**
- Produces: `codex.user_serena(data: dict, owned: set[str]) -> str | None` (name of a table not owned by loadout that runs Serena's MCP server); `codex.is_serena(table: dict) -> bool`.

- [ ] **Step 1: Write the failing tests**

```python
"""Codex: Serena's server as `serena setup codex` writes it, and never a second one (spec PR A)."""
import pytest

from loadout import backup, codex, settings_merge


@pytest.fixture
def cfg(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: {"enabledPlugins": {}})
    monkeypatch.setattr(codex, "installed_plugins", lambda: set())
    path = codex.paths.codex_home() / "config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def test_loadouts_serena_table_is_the_documented_one(cfg):
    codex.apply_config(backup.Backup(description="t"))
    text = cfg.read_text()
    assert ('[mcp_servers.serena]\ncommand = "serena"\n'
            'args = ["start-mcp-server", "--project-from-cwd", "--context=codex"]\nstartup_timeout_sec = 15\n') in text


@pytest.mark.parametrize("table", [
    '[mcp_servers.serena]\nstartup_timeout_sec = 15\ncommand = "serena"\nargs = ["start-mcp-server", "--project-from-cwd", "--context=codex"]\n',
    '[mcp_servers.serena-mine]\ncommand = "uvx"\nargs = ["--from", "git+https://github.com/oraios/serena", "serena", "start-mcp-server", "--context", "codex"]\n',
    '[mcp_servers.s]\ncommand = "/home/u/.local/bin/serena"\nargs = ["start-mcp-server"]\n',
])
def test_a_users_serena_is_used_and_no_second_one_is_added(cfg, table):
    cfg.write_text(table)
    lines = codex.apply_config(backup.Backup(description="t"))
    assert cfg.read_text().count("start-mcp-server") == 1
    assert not any("left as is" in l for l in lines)
    assert codex.apply_config(object(), dry_run=True) == []  # loadout check stays quiet


def test_loadouts_earlier_serena_goes_when_the_user_adds_their_own(cfg):
    codex.apply_config(backup.Backup(description="t"))
    cfg.write_text(cfg.read_text() + '\n[mcp_servers.my-serena]\ncommand = "serena"\nargs = ["start-mcp-server"]\n')
    codex.apply_config(backup.Backup(description="t"))
    text = cfg.read_text()
    assert "[mcp_servers.serena]" not in text and "[mcp_servers.my-serena]" in text


def test_a_serena_table_that_is_not_serena_names_the_rename_fix(cfg, monkeypatch):
    cfg.write_text('[mcp_servers.serena]\ncommand = "something-else"\n')
    lines = codex.apply_config(object(), dry_run=True)
    assert any("left as is" in l for l in lines)
    monkeypatch.setattr(codex, "unavailable", lambda: None)
    monkeypatch.setattr(codex, "hooks_status", lambda: "trusted")
    monkeypatch.setattr(codex, "logins_needed", lambda: [])
    monkeypatch.setattr(codex, "drift", lambda: [])
    (r,) = [r for r in codex.checks() if r.name == "Codex config"]
    assert not r.ok and "rename" in r.fix
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_codex_serena.py`
Expected: FAIL (no `startup_timeout_sec`; `serena-mine` gets a second `serena`; the fix says `loadout bootstrap`). If `checks()` needs more monkeypatching to run in a test, add it (ruling only if a production change is needed).

- [ ] **Step 3: Implement** in `cli/loadout/codex.py`:

```python
SERENA = {"command": "serena", "args": ["start-mcp-server", "--project-from-cwd", "--context=codex"],
          "startup_timeout_sec": 15}  # as `serena setup codex` writes it (oraios.github.io/serena, clients page)
```

`toml_value`: accept `int` (not `bool`) before the `str` branch: `if isinstance(value, int) and not isinstance(value, bool): return str(value)`. Check that `server()` (personal `mcp.json` mapping) still refuses what it refused: it builds its own dict and never passes ints, so nothing changes there.

```python
def is_serena(table: dict) -> bool:
    """A Codex server table that starts Serena's MCP server, whatever its name: serena, a full path to it, or uvx/uv."""
    command, args = table.get("command"), table.get("args")
    if not isinstance(command, str) or not isinstance(args, list) or "start-mcp-server" not in args:
        return False
    base = re.split(r"[\\/]", command)[-1].lower().removesuffix(".exe")
    return base == "serena" or (base in ("uvx", "uv") and any(isinstance(a, str) and "serena" in a for a in args))


def user_serena(data: dict, owned: set[str]) -> str | None:
    """The name of the user's own Serena server in config.toml (a table loadout did not write), or None."""
    for name, table in get_dict(data, "mcp_servers").items():
        if name not in owned and isinstance(table, dict) and is_serena(table):
            return name
    return None
```

`desired_tables()` gains a parameter: `def desired_tables(skip_serena: bool = False)`, and starts with `tables = {} if skip_serena else {"serena": table_text("serena", SERENA)}`. In `apply_config`, after `record = read_record()` and the parse of `before`: `tables, lines = desired_tables(skip_serena=user_serena(before, set(record["tables"])) is not None)`; the existing loop already removes an owned `serena` table that is no longer desired. A personal `mcp.json` entry named `serena` still overrides (it comes after, unchanged).

In `checks()`, the "Codex config" result: when every pending line contains `left as is`, its fix is `rename or remove that table in ~/.codex/config.toml if you want loadout's; loadout never changes your entries`; otherwise `loadout bootstrap` as today.

- [ ] **Step 4: Run the tests**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_codex_serena.py tests/test_codex_config.py tests/test_codex_final_fixes.py`
Expected: all pass. Old tests that asserted the old Serena table text get the new text (a ruling line per changed assertion is not needed: the spec mandates the text).

- [ ] **Step 5: Commit** — `feat(codex): Serena's server as serena setup codex writes it, and the user's Serena under any name`

### Task 3: Serena's hooks as owned entries in ~/.codex/hooks.json

**Files:**
- Create: `cli/loadout/codex_hooks.py`
- Modify: `cli/loadout/codex.py` (`apply_all` calls it; `checks` reports it)
- Test: `tests/test_codex_serena_hooks.py` (create)

**Interfaces:**
- Consumes: `codex.read_record()`, `codex.record_path()`, Task 1 rulings on the JSON shape.
- Produces: `codex_hooks.apply(bk, dry_run: bool = False) -> list[str]`; `codex_hooks.SERENA_HOOKS`; `codex_hooks.path() -> Path`.

- [ ] **Step 1: Write the failing tests**

```python
"""Codex: Serena's six documented hooks in ~/.codex/hooks.json, exactly once, the user's entries untouched."""
import json

import pytest

from loadout import backup, codex_hooks, runner


@pytest.fixture
def hooks(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(runner, "have", lambda b: b == "serena-hooks")
    p = codex_hooks.path()
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _commands(p):
    data = json.loads(p.read_text())
    return sorted(h["command"] for groups in data["hooks"].values() for g in groups for h in g["hooks"])


OFFICIAL = sorted(f"serena-hooks {s} --client=codex" for s in
                  ("remind", "plan-guard", "reset", "activate", "plan-context", "cleanup"))


def test_a_fresh_setup_gets_the_official_set(hooks):
    lines = codex_hooks.apply(backup.Backup(description="t"))
    assert _commands(hooks) == OFFICIAL
    data = json.loads(hooks.read_text())["hooks"]
    assert data["SessionStart"][0]["matcher"] == "startup|resume"
    assert data["SessionEnd"][0]["hooks"][0]["timeout"] == 3
    assert any("/hooks" in l for l in lines)
    assert codex_hooks.apply(backup.Backup(description="t")) == []  # second run: nothing


def test_the_users_official_set_is_left_alone(hooks):
    codex_hooks.apply(backup.Backup(description="t"))
    users = hooks.read_text()
    codex_hooks.paths.state_dir().joinpath("codex-config.json").unlink()  # as if the user wrote it (serena setup codex)
    assert codex_hooks.apply(backup.Backup(description="t")) == []
    assert hooks.read_text() == users


def test_only_missing_entries_are_added(hooks):
    hooks.write_text(json.dumps({"hooks": {"SessionStart": [{"matcher": "startup|resume", "hooks": [
        {"type": "command", "command": "/opt/bin/serena-hooks activate --client=codex", "timeout": 20}]}],
        "Stop": [{"hooks": [{"type": "command", "command": "serena-hooks cleanup --client=codex"}]}]}}, indent=2) + "\n")
    codex_hooks.apply(backup.Backup(description="t"))
    cmds = _commands(hooks)
    assert sum("activate" in c for c in cmds) == 1 and sum("cleanup" in c for c in cmds) == 1
    assert len(cmds) == 6


def test_a_file_in_another_format_is_not_rewritten(hooks):
    users = '{"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo hi"}]}]}}'  # one line
    hooks.write_text(users)
    lines = codex_hooks.apply(backup.Backup(description="t"))
    assert hooks.read_text() == users
    assert any("add these yourself" in l and "serena-hooks remind --client=codex" in l for l in lines)


def test_without_serena_hooks_nothing_is_written_and_ours_go(hooks, monkeypatch):
    codex_hooks.apply(backup.Backup(description="t"))
    monkeypatch.setattr(runner, "have", lambda b: False)
    codex_hooks.apply(backup.Backup(description="t"))
    assert _commands(hooks) == []


def test_an_entry_the_user_changed_becomes_theirs(hooks):
    codex_hooks.apply(backup.Backup(description="t"))
    data = json.loads(hooks.read_text())
    data["hooks"]["SessionEnd"][0]["hooks"][0]["timeout"] = 9
    hooks.write_text(json.dumps(data, indent=2) + "\n")
    before = hooks.read_text()
    assert codex_hooks.apply(backup.Backup(description="t")) == []  # cleanup still present (theirs now)
    assert hooks.read_text() == before


def test_restore_reverts_the_first_change(hooks):
    hooks.write_text(json.dumps({"hooks": {}}, indent=2) + "\n")
    bk = backup.Backup(description="t")
    codex_hooks.apply(bk)
    assert any(e.get("label", "").startswith("Codex hooks.json") for e in bk.manifest()["entries"])
```

Before writing the last test, read `cli/loadout/backup.py` for the real way to list a backup's entries (the name `manifest()["entries"]` may differ) and adapt the call, not the meaning.

- [ ] **Step 2: Run them to see them fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_codex_serena_hooks.py`
Expected: FAIL — `ModuleNotFoundError: loadout.codex_hooks`.

- [ ] **Step 3: Implement** `cli/loadout/codex_hooks.py`:

```python
"""Serena's documented Codex hooks (oraios.github.io/serena, clients page) as loadout-owned entries in
~/.codex/hooks.json: added when missing, never twice, the user's entries byte for byte (ADR 0029)."""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import paths, runner
from .jsonio import load_json, save_json, write_atomic

# (event, matcher or None, serena-hooks subcommand, timeout or None), exactly as Serena documents them
SERENA_HOOKS = (("PreToolUse", "Bash", "remind", 5), ("PreToolUse", "^mcp__serena__", "plan-guard", None),
                ("PostToolUse", "^mcp__serena__.*$", "reset", None), ("SessionStart", "startup|resume", "activate", None),
                ("UserPromptSubmit", None, "plan-context", None), ("SessionEnd", None, "cleanup", 3))
ALSO = {"cleanup": ("SessionEnd", "Stop")}  # Serena: cleanup under exactly one of these, never both


def path() -> Path:
    return paths.codex_home() / "hooks.json"


def _group(matcher, sub, timeout) -> dict:
    hook = {"type": "command", "command": f"serena-hooks {sub} --client=codex", **({"timeout": timeout} if timeout else {})}
    return {**({"matcher": matcher} if matcher is not None else {}), "hooks": [hook]}


def _canon(group) -> str:
    return json.dumps(group, sort_keys=True)


def _present(data: dict, event: str, sub: str) -> bool:
    rx = re.compile(rf"(?:^|[\s/\\\"'])serena-hooks(?:\.exe)?[\"']?\s+{re.escape(sub)}\b.*--client[= ]codex")
    for ev in ALSO.get(sub, (event,)):
        for group in data.get("hooks", {}).get(ev, []) or []:
            for hook in (group.get("hooks", []) if isinstance(group, dict) else []):
                if isinstance(hook, dict) and isinstance(hook.get("command"), str) and rx.search(hook["command"]):
                    return True
    return False


def _record() -> dict:
    from . import codex
    return codex.read_record()


def apply(bk, dry_run: bool = False) -> list[str]:
    from . import codex
    p = path()
    old = p.read_text(encoding="utf-8") if p.exists() else ""
    try:
        data = json.loads(old) if old.strip() else {}
    except ValueError as exc:
        return [f"skipped {p}: it is not valid JSON ({exc}); fix it, then run loadout bootstrap"]
    if not isinstance(data, dict) or not isinstance(data.get("hooks", {}), dict):
        return [f"skipped {p}: it has no hooks object; nothing written"]
    record = _record()
    owned = [o for o in record.get("hooks", []) if isinstance(o, dict)]
    wanted = SERENA_HOOKS if runner.have("serena-hooks") else ()
    events = data.setdefault("hooks", {})
    kept, changed = [], False
    for o in owned:  # loadout's entries: drop the unwanted ones, forget the ones the user changed
        groups = events.get(o.get("event"), [])
        hit = next((g for g in groups if _canon(g) == o.get("group")), None)
        if hit is None:
            continue  # changed or removed by the user: theirs now
        if not any(e == o["event"] and _canon(_group(m, s, t)) == o["group"] for e, m, s, t in wanted):
            groups.remove(hit)
            changed = True
            continue
        kept.append(o)
    missing = [(e, m, s, t) for e, m, s, t in wanted if not _present(data, e, s)]
    for e, m, s, t in missing:
        group = _group(m, s, t)
        events.setdefault(e, []).append(group)
        kept.append({"event": e, "group": _canon(group)})
        changed = True
    for ev in [ev for ev, groups in events.items() if groups == []]:
        if not any(ev == o.get("event") for o in owned):
            continue
        del events[ev]
    new = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    new_record = {**record, "hooks": kept}
    if not new_record["hooks"]:
        new_record.pop("hooks")
    if not changed:
        if new_record != record and not dry_run:
            save_json(codex.record_path(), new_record)
        return []
    if old and json.dumps(json.loads(old), indent=2, ensure_ascii=False) + "\n" != old:
        snippet = ", ".join(f"{e}: serena-hooks {s} --client=codex" for e, _, s, _ in missing)
        return [f"{p}: Serena hooks missing, add these yourself (loadout does not rewrite a file in another format): "
                f"{snippet}" if missing else f"{p}: loadout's old Serena hooks are still in it; remove them yourself"]
    if dry_run:
        return [f"{p}: Serena hooks pending"]
    if p.exists() and not record.get("hooks"):
        bk.save_copy(p, "Codex hooks.json before loadout's first change")
    elif not p.exists():
        bk.record_created(p, "created Codex hooks.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(p, new)
    codex.record_path().parent.mkdir(parents=True, exist_ok=True)
    save_json(codex.record_path(), new_record)
    added = [s for _, _, s, _ in missing]
    return [f"hooks.json: added Serena's hooks ({', '.join(added)}); approve them in Codex: /hooks"] if added else \
           ["hooks.json: removed loadout's Serena hooks"]
```

Note on the record: `codex.read_record()` returns `tables` and `keys` normalised; `hooks` rides along as an extra key (like `install_lines`), so `apply_config`'s own `save_json` of `{**record, ...}` keeps it. Check that `apply_config` reads the record fresh each run (it does: `read_record()` at its start) so the two writers do not overwrite each other within one `apply_all` — `apply_all` calls `apply_config` before `codex_hooks.apply`.

In `codex.apply_all`, after `*apply_config(bk)`: `*codex_hooks.apply(bk)` (import inside the function). In `codex.checks()`, after the "Codex config" result: `pending_hooks = codex_hooks.apply(object(), dry_run=True)` → `CheckResult("Codex Serena hooks", not pending_hooks, "; ".join(pending_hooks), "loadout bootstrap" unless every line says "add these yourself", in which case the fix is "add the listed entries to ~/.codex/hooks.json", "warn")`.

- [ ] **Step 4: Run the tests**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_codex_serena_hooks.py tests/test_codex_*.py`
Expected: all pass.

- [ ] **Step 5: Commit** — `feat(codex): Serena's documented hooks in ~/.codex/hooks.json, exactly once`

### Task 4: The plugin stops carrying Serena for Codex

**Files:**
- Modify: `plugins/loadout/hooks/codex.json` (remove the three `serena-hooks` hooks: SessionStart `activate`, SessionEnd `cleanup` group, PreToolUse `mcp__serena__.*` `auto-approve` group)
- Modify (only if Task 1 (3) is yes): `plugins/loadout/.codex-plugin/plugin.json` (`"mcpServers": "./.codex-mcp.json"`), create `plugins/loadout/.codex-mcp.json` with only `codebase-memory-mcp`
- Modify (only if Task 1 (2) found the format): `cli/loadout/codex.py` (`hooks_status` includes the hooks.json keys loadout owns)
- Test: `tests/test_codex_hooks.py` (existing), `tests/test_codex_serena_hooks.py`

- [ ] **Step 1: Write the failing test** (append to `tests/test_codex_serena_hooks.py`):

```python
def test_the_plugin_no_longer_runs_serena_hooks_in_codex():
    from loadout import paths
    text = (paths.kit_root() / "plugins/loadout/hooks/codex.json").read_text()
    assert "serena-hooks" not in text
    assert "loadout hook-session-start" in text and "tool_hint.sh" in text and "typecheck.py" in text
```

- [ ] **Step 2: Run** `uv run --python 3.12 --with pytest pytest -q tests/test_codex_serena_hooks.py -k plugin` → FAIL.
- [ ] **Step 3: Implement** the edits above; empty groups and an empty `SessionEnd` event are removed, not left empty. Then run `uv run --python 3.12 --with pytest pytest -q tests/test_codex_hooks.py` and update assertions there that listed the removed hooks (each change ledgered as a ruling: "spec PR A removes it").
- [ ] **Step 4: Run** the full suite: `uv run --python 3.12 --with pytest pytest -q` → all pass; `claude plugin validate plugins/loadout` → passes.
- [ ] **Step 5: Commit** — `feat(codex): the plugin no longer runs Serena's hooks in Codex (they live in hooks.json)`

### Task 5: Docs and ADR 0029

**Files:**
- Create: `docs/adr/0029-serena-codex-hooks-in-hooks-json.md`
- Modify: `docs/adr/README.md`, `AGENTS.md` (ADR range, module map: `codex_hooks.py`), `docs/reference/hooks.md` (Codex column: Serena rows now from `hooks.json`, no auto-approve), `docs/how-to/codex.md` (Serena already set up), `docs/explanation/security-and-trust.md` (loadout writes owned entries in `~/.codex/hooks.json`), `docs/how-to/undo-and-restore.md`, `docs/how-to/uninstall.md` (remove loadout's entries from `~/.codex/hooks.json`), `docs/how-to/troubleshooting.md` (the new lines), `docs/reference/personal-layer.md` or `included-tools.md` where the Serena table is shown.

- [ ] **Step 1:** ADR 0029: context (official Serena Codex setup, Codex combines hook layers, plugin hooks cannot step aside), decision (owned entries in hooks.json, presence by subcommand, never rewrite a file in another format, no auto-approve for Codex), consequences (`/hooks` review after a change; Claude Code unchanged).
- [ ] **Step 2:** Update each page; check every touched link resolves.
- [ ] **Step 3:** `uv run --python 3.12 --with pytest pytest -q tests/test_docs_links.py tests/test_readme.py` → pass.
- [ ] **Step 4: Commit** — `docs: Serena's Codex hooks live in hooks.json (ADR 0029)`
