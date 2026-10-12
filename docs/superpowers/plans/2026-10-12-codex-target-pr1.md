# Codex Target (PR 1: global setup) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** With Codex enabled, bootstrap and the daily sync give Codex the same rules, plugins, MCP servers, skills, hooks and settings as Claude Code (or the documented Codex-only replacement), and report drift between the two.

**Architecture:** A new `cli/loadout/codex.py` holds all Codex-specific code (switch, instructions block, owned `config.toml` tables and keys, plugin routes, skill links, drift, checks). The plugin gets a Codex manifest pointing to a Codex-only hooks file with Codex arguments and a type-check hook. Bootstrap, maintenance, check, configure and restore call into it.

**Tech Stack:** Python 3.10+ standard library (`tomllib` used when present), the `codex` CLI through `runner.py`, pytest with `fake_home`/`fake_runner`.

**Spec:** `docs/superpowers/specs/2026-10-12-codex-target-design.md`

## Global Constraints

- Standard library only in `cli/loadout/` and in hook scripts. `tomllib` only behind `try: import tomllib` (Python 3.11+).
- Tests use `fake_home` and `fake_runner`; never the real `~/.claude`, `~/.claude.json`, `~/.config/loadout`, `~/.codex` or `~/.agents`. Agents never run `codex` against the real `CODEX_HOME`; sandbox runs set `HOME` and `CODEX_HOME` to a scratch folder.
- Codex minimum version: 0.161. Codex markers in `AGENTS.md`: `<!-- loadout:start -->` / `<!-- loadout:end -->`.
- Switch: `<personal>/targets.json` `{"codex": true|false}`; CLI `loadout configure set target codex on|off`.
- Ownership record: `~/.claude/.loadout/codex-config.json` `{"tables": {name: text}, "keys": {"table.key": line}}`.
- Official Claude marketplace in Codex: `anthropics/claude-plugins-official` (Codex names it `claude-plugins-official`).
- Serena in Codex: `command = "serena"`, `args = ["start-mcp-server", "--context=codex", "--project-from-cwd"]`.
- Restore allowlist: exactly `claude` and `codex` as `cmd[0]`.
- Conventional Commits; no `Co-Authored-By` or AI attribution; author `Jonas Weirauch <jonas.weirauch@gmx.de>`. Push and PR need the user's OK.

## Rulings against the spec (made while planning, recorded in the spec in Task 9)

- **No catalog `codex` field.** Codex accepts Claude marketplaces, so every plugin enabled in the merged Claude settings maps through its marketplace's GitHub source (`claude-plugins-official` → `anthropics/claude-plugins-official`). A plugin whose marketplace is not on GitHub is reported by `check` as "no Codex route". playwright-cli installs no skills for Claude, so there is nothing to map.
- **The `/hooks` reminder lives in bootstrap's "Still to do"** (shown every run while Codex is enabled), not as a failing check: loadout cannot see whether hooks were approved.
- **`reload_check.py` is not in the Codex hooks:** it compares Claude's `installed_plugins.json`; Codex loads plugins per session and loadout refreshes them in the sync.

## Review Focus

1. **A user's own `[mcp_servers.x]` or key in `config.toml` that loadout never wrote** must never be overwritten or removed. Pinned by `test_foreign_table_and_key_are_left_alone` (Task 3).
2. **A `config.toml` loadout cannot parse after its edit** (odd user TOML) must stay byte-identical. Pinned by `test_unparseable_result_writes_nothing` (Task 3).
3. **A personal MCP server with a plaintext secret or `${VAR}` under another name** must never reach `config.toml` as plaintext. Pinned by `test_plaintext_secret_is_refused`, `test_renamed_variable_is_refused` (Task 3).
4. **Codex absent, too old, or disabled** must leave every Claude path byte-identical (bootstrap output, check results). Pinned by `test_bootstrap_without_codex_is_unchanged`, `test_check_without_codex_has_no_codex_group` (Task 7).
5. **A manifest replaying `codex` undo commands** must still refuse every other program. Pinned by `test_restore_runs_codex_but_refuses_others` (Task 1).

---

### Task 1: Paths, the switch, and restore for `codex` undos

**Files:**
- Modify: `cli/loadout/paths.py` (add `codex_home`, `agents_skills`)
- Create: `cli/loadout/codex.py` (switch and version only in this task)
- Modify: `cli/loadout/backup.py:188` (allowlist)
- Modify: `cli/loadout/commands.py` (`configure set target`), `cli/loadout/configure.py` (`show`)
- Test: `tests/test_codex_switch.py`

**Interfaces:**
- Produces: `paths.codex_home() -> Path` (`$CODEX_HOME` or `home()/.codex`), `paths.agents_skills() -> Path` (`home()/.agents/skills`); `codex.targets_path() -> Path`, `codex.enabled() -> bool`, `codex.decided() -> bool`, `codex.set_enabled(on: bool) -> str`, `codex.unavailable() -> str | None`, `codex.MIN_VERSION = (0, 161)`.

- [ ] **Step 1: Write the failing tests**

`tests/test_codex_switch.py`:

```python
"""Codex target: the switch in the personal layer, the version gate, restore of codex undo commands."""
import json

from loadout import backup, codex, paths, runner
from loadout.__main__ import main


def test_codex_home_follows_codex_home_env(fake_home, monkeypatch):
    assert paths.codex_home() == fake_home / ".codex"
    monkeypatch.setenv("CODEX_HOME", str(fake_home / "elsewhere"))
    assert paths.codex_home() == fake_home / "elsewhere"
    assert paths.agents_skills() == fake_home / ".agents" / "skills"


def test_switch_is_off_and_undecided_by_default(fake_home):
    assert not codex.enabled() and not codex.decided()


def test_configure_set_target_records_the_choice(fake_home, fake_runner, monkeypatch):
    from loadout import configure
    monkeypatch.setattr(configure, "apply_all", lambda ask: None)
    assert main(["configure", "set", "target", "codex", "on"]) == 0
    assert json.loads(codex.targets_path().read_text()) == {"codex": True}
    assert codex.enabled() and codex.decided()
    assert main(["configure", "set", "target", "codex", "off"]) == 0
    assert not codex.enabled() and codex.decided()


def test_configure_show_names_the_codex_switch(fake_home):
    from loadout import configure
    assert "Codex: off (set with: loadout configure set target codex on|off)" in configure.show()


def test_unavailable_names_missing_and_old_codex(fake_home, fake_runner):
    fake_runner.missing.add("codex")
    assert "not found" in codex.unavailable()
    fake_runner.missing.discard("codex")
    fake_runner.responses[("codex", "--version")] = runner.Result(0, "codex-cli 0.150.1\n", "")
    assert "0.150.1" in codex.unavailable() and "0.161" in codex.unavailable()
    fake_runner.responses[("codex", "--version")] = runner.Result(0, "codex-cli 0.162.1\n", "")
    assert codex.unavailable() is None


def test_restore_runs_codex_but_refuses_others(fake_home, fake_runner):
    bk = backup.Backup(description="test")
    bk.record_command("codex plugin x", ["codex", "plugin", "remove", "x@y"])
    bk.record_command("evil", ["sh", "-c", "rm -rf ~"])
    lines, ok, _ = backup.restore(bk.root)
    assert ["codex", "plugin", "remove", "x@y"] in fake_runner.calls
    assert not any(c[0] == "sh" for c in fake_runner.calls)
    assert any("refusing" in line for line in lines) and not ok
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_codex_switch.py`
Expected: ERROR `ImportError: cannot import name 'codex'`.

- [ ] **Step 3: Implement**

In `cli/loadout/paths.py`, after `claude_json()`:

```python
def codex_home() -> Path:
    """Codex's configuration folder: $CODEX_HOME, else ~/.codex."""
    env = os.environ.get("CODEX_HOME")
    return Path(env) if env else home() / ".codex"


def agents_skills() -> Path:
    """User skills read by Codex (and other agents following the Agent Skills layout)."""
    return home() / ".agents" / "skills"
```

(`os` is already imported in `paths.py`; if not, add `import os`.)

Create `cli/loadout/codex.py`:

```python
"""Codex CLI as a second target: the same kit and personal layer, mapped to Codex (docs/how-to/codex.md)."""
from __future__ import annotations

import re
from pathlib import Path

from . import paths, runner
from .jsonio import load_json, save_json

MIN_VERSION = (0, 161)


def targets_path() -> Path:
    return paths.personal_root() / "targets.json"


def enabled() -> bool:
    return load_json(targets_path()).get("codex") is True


def decided() -> bool:
    return "codex" in load_json(targets_path())


def set_enabled(on: bool) -> str:
    data = load_json(targets_path())
    data["codex"] = on
    targets_path().parent.mkdir(parents=True, exist_ok=True)
    save_json(targets_path(), data)
    return f"codex: {'on' if on else 'off'}"


def unavailable() -> str | None:
    """None when a usable codex is on PATH, else the reason in one line."""
    if not runner.have("codex"):
        return "codex not found on PATH"
    res = runner.run(["codex", "--version"], timeout=20)
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", res.stdout)
    if not m:
        return "could not read codex --version"
    if (int(m.group(1)), int(m.group(2))) < MIN_VERSION:
        return f"codex {m.group(0)} is too old; loadout needs 0.161 or newer (update it: mise upgrade codex)"
    return None
```

In `cli/loadout/backup.py`, replace

```python
        if not cmd or cmd[0] != "claude":
            return f"failed: refusing to run a non-claude command from a manifest: {' '.join(cmd)}"
```

with

```python
        if not cmd or cmd[0] not in ("claude", "codex"):  # only the agents' own CLIs; never a shell from a manifest
            return f"failed: refusing to run a command other than claude or codex from a manifest: {' '.join(cmd)}"
```

In `cli/loadout/commands.py`, add `"target"` to the `kind` choices and handle it before `a.kind == "plugin"`:

```python
    p.add_argument("kind", nargs="?", choices=["plugin", "mcp", "pref-choice", "pref", "own", "target"], help="what to set")
```

```python
        if a.kind == "target":
            if a.name != "codex":
                raise ValueError("usage: loadout configure set target codex on|off")
            from . import codex
            print(codex.set_enabled(configure.parse_switch(a.value, "target")))
            configure.apply_all(lambda q: "n")
            return 0
```

Also extend the usage error text to `plugin|mcp|pref-choice|pref|own|target`.

In `cli/loadout/configure.py`, in `show()`, after the first line:

```python
    from . import codex
    lines.append(f"Codex: {'on' if codex.enabled() else 'off'} (set with: loadout configure set target codex on|off)")
```

- [ ] **Step 4: Run the tests**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_codex_switch.py tests/test_configure.py tests/test_link_backup.py`
Expected: all pass. If an existing test asserts the old refusal text, update its expected string to the new one (the meaning is unchanged); ledger it.

- [ ] **Step 5: Commit**

```bash
git add cli/loadout/paths.py cli/loadout/codex.py cli/loadout/backup.py cli/loadout/commands.py cli/loadout/configure.py tests/test_codex_switch.py
git commit -m "feat(codex): the Codex switch, version gate and restore of codex undo commands"
```

---

### Task 2: The instruction block in `~/.codex/AGENTS.md`

**Files:**
- Modify: `cli/loadout/codex.py`
- Test: `tests/test_codex_instructions.py`

**Interfaces:**
- Consumes: `paths.codex_home()` (Task 1).
- Produces: `codex.START`, `codex.END`, `codex.render_instructions() -> str`, `codex.splice(text: str, block: str) -> str | None`, `codex.apply_instructions(bk) -> str`.

- [ ] **Step 1: Write the failing tests**

`tests/test_codex_instructions.py`:

```python
"""The kit's and the personal layer's rules as one managed block in ~/.codex/AGENTS.md."""
from loadout import backup, codex, paths


def _personal_rules(fake_home, text="# About me\n\n- Answers: concise.\n"):
    rules = paths.personal_root() / "rules"
    rules.mkdir(parents=True)
    (rules / "me.md").write_text(text, encoding="utf-8")


def test_block_holds_kit_and_personal_rules(fake_home):
    _personal_rules(fake_home)
    block = codex.render_instructions()
    assert block.startswith(codex.START) and block.rstrip().endswith(codex.END)
    for f in sorted((paths.kit_root() / "rules").glob("*.md")):
        assert f.read_text(encoding="utf-8").strip() in block
    assert "- Answers: concise." in block
    assert block.index("docs-policy") < block.index("About me"), "kit rules first, then personal"


def test_creates_the_file_when_missing(fake_home):
    _personal_rules(fake_home)
    line = codex.apply_instructions(backup.Backup(description="t"))
    path = paths.codex_home() / "AGENTS.md"
    assert path.read_text(encoding="utf-8") == codex.render_instructions() and "written" in line


def test_appends_to_existing_text_and_backs_it_up_once(fake_home):
    _personal_rules(fake_home)
    path = paths.codex_home() / "AGENTS.md"
    path.parent.mkdir(parents=True)
    path.write_text("# My Codex notes\n\nUse tabs.\n", encoding="utf-8")
    bk = backup.Backup(description="t")
    codex.apply_instructions(bk)
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# My Codex notes\n\nUse tabs.\n") and codex.START in text
    assert not bk.empty
    bk2 = backup.Backup(description="t2")
    assert codex.apply_instructions(bk2) == "instructions up to date" and bk2.empty


def test_replaces_only_the_block(fake_home):
    _personal_rules(fake_home)
    path = paths.codex_home() / "AGENTS.md"
    path.parent.mkdir(parents=True)
    path.write_text(f"before\n\n{codex.START}\nold\n{codex.END}\n\nafter\n", encoding="utf-8")
    codex.apply_instructions(backup.Backup(description="t"))
    text = path.read_text(encoding="utf-8")
    assert text.startswith("before\n\n") and text.endswith("\n\nafter\n") and "\nold\n" not in text


def test_unbalanced_markers_leave_the_file_alone(fake_home):
    _personal_rules(fake_home)
    path = paths.codex_home() / "AGENTS.md"
    path.parent.mkdir(parents=True)
    broken = f"{codex.START}\nhalf a block\n"
    path.write_text(broken, encoding="utf-8")
    line = codex.apply_instructions(backup.Backup(description="t"))
    assert path.read_text(encoding="utf-8") == broken and line.startswith("skipped")


def test_splice_cases():
    block = f"{codex.START}\nnew\n{codex.END}\n"
    assert codex.splice("", block) == block
    assert codex.splice("mine\n", block) == "mine\n\n" + block
    assert codex.splice(f"{codex.END}\n{codex.START}\n", block) is None
    assert codex.splice(f"{codex.START}\n{codex.END}\n{codex.START}\n{codex.END}\n", block) is None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_codex_instructions.py`
Expected: FAIL with `AttributeError: module 'loadout.codex' has no attribute 'render_instructions'`.

- [ ] **Step 3: Implement** (append to `cli/loadout/codex.py`)

```python
START = "<!-- loadout:start -->"
END = "<!-- loadout:end -->"


def _tilde(path: Path) -> str:
    home = str(paths.home())
    return "~" + str(path)[len(home):] if str(path).startswith(home) else str(path)


def render_instructions() -> str:
    """Codex has no @include and no rules folder, so the rules are copied in; their files stay the only source."""
    kit, personal = paths.kit_root() / "rules", paths.personal_root() / "rules"
    parts = [START, f"<!-- Managed by loadout from {_tilde(kit)} and {_tilde(personal)}; "
                    "edit those files, not this block. -->"]
    for folder in (kit, personal):
        if folder.is_dir():
            parts += [f.read_text(encoding="utf-8").strip() for f in sorted(folder.glob("*.md"))]
    parts.append(END)
    return "\n\n".join(parts) + "\n"


def splice(text: str, block: str) -> str | None:
    """text with the block replaced or appended; None when the markers are unbalanced or duplicated."""
    starts, ends = text.count(START), text.count(END)
    if starts == ends == 0:
        return block if not text.strip() else text.rstrip("\n") + "\n\n" + block
    if starts == ends == 1 and text.index(START) < text.index(END):
        before, rest = text.split(START, 1)
        after = rest.split(END, 1)[1]
        return before + block.rstrip("\n") + after
    return None


def apply_instructions(bk) -> str:
    path = paths.codex_home() / "AGENTS.md"
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    new = splice(old, render_instructions())
    if new is None:
        return f"skipped {path}: its loadout markers are unbalanced or duplicated; fix them by hand"
    if new == old:
        return "instructions up to date"
    if path.exists() and START not in old:
        bk.save_copy(path, "Codex AGENTS.md before loadout added its block")
    elif not path.exists():
        bk.record_created(path, "created Codex AGENTS.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new, encoding="utf-8", newline="\n")
    return f"instructions written to {_tilde(path)}"
```

Note for `test_replaces_only_the_block`: the old file is `before\n\n<START>…<END>\n\nafter\n`; `splice` keeps `before\n\n`, inserts the block without its final newline, then the original `\n\nafter\n`. The assertion `text.endswith("\n\nafter\n")` holds.

- [ ] **Step 4: Run the tests**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_codex_instructions.py`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add cli/loadout/codex.py tests/test_codex_instructions.py
git commit -m "feat(codex): the kit's and personal rules as a managed block in ~/.codex/AGENTS.md"
```

---

### Task 3: Owned tables and keys in `~/.codex/config.toml`

**Files:**
- Modify: `cli/loadout/codex.py`
- Test: `tests/test_codex_config.py`

**Interfaces:**
- Consumes: `paths.codex_home()`, `paths.state_dir()`, `secrets.looks_secret(key, value)`, `preferences.detect()`, `preferences.by_id(pid)`.
- Produces: `codex.Refused(Exception)`, `codex.toml_value(v) -> str`, `codex.server(name: str, cfg: dict) -> dict`, `codex.table_text(name: str, server: dict) -> str`, `codex.SERENA: dict`, `codex.desired_tables() -> tuple[dict[str, str], list[str]]`, `codex.desired_keys() -> list[tuple[str, str, object]]`, `codex.apply_config(bk, dry_run: bool = False) -> list[str]`, `codex.record_path() -> Path`.

- [ ] **Step 1: Write the failing tests**

`tests/test_codex_config.py`:

```python
"""loadout's own tables and keys in ~/.codex/config.toml: written, updated, removed only while unchanged."""
import json
import sys

import pytest

from loadout import backup, codex, paths


def _personal_mcp(servers):
    path = paths.personal_root() / "mcp.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"mcpServers": servers}), encoding="utf-8")


def _config():
    return (paths.codex_home() / "config.toml").read_text(encoding="utf-8")


def _apply():
    return codex.apply_config(backup.Backup(description="t"))


def test_values_are_toml():
    assert codex.toml_value('a "quoted"\\path\n') == '"a \\"quoted\\"\\\\path\\n"'
    assert codex.toml_value(True) == "true" and codex.toml_value(["a", "b"]) == '["a", "b"]'
    assert codex.toml_value({"K": "v", "with.dot": "x"}) == '{ K = "v", "with.dot" = "x" }'
    with pytest.raises(codex.Refused):
        codex.toml_value(3)


def test_stdio_server_forwards_secrets_by_name():
    s = codex.server("gh", {"command": "gh-mcp", "args": ["--x"], "env": {"GITHUB_TOKEN": "${GITHUB_TOKEN}", "MODE": "ro"}})
    assert s == {"command": "gh-mcp", "args": ["--x"], "env": {"MODE": "ro"}, "env_vars": ["GITHUB_TOKEN"]}


def test_http_server_maps_bearer_and_headers():
    s = codex.server("api", {"type": "http", "url": "https://x.example/mcp",
                             "headers": {"Authorization": "Bearer ${API_TOKEN}", "X-Team": "${TEAM_ID}", "X-Mode": "ro"}})
    assert s == {"url": "https://x.example/mcp", "bearer_token_env_var": "API_TOKEN",
                 "http_headers": {"X-Mode": "ro"}, "env_http_headers": {"X-Team": "TEAM_ID"}}


def test_plaintext_secret_is_refused():
    with pytest.raises(codex.Refused, match="secrets.env"):
        codex.server("gh", {"command": "gh-mcp", "env": {"GITHUB_TOKEN": "ghp_" + "a1B2" * 9}})


def test_renamed_variable_is_refused():
    with pytest.raises(codex.Refused, match="own name"):
        codex.server("gh", {"command": "gh-mcp", "env": {"GITHUB_TOKEN": "${GH_PAT}"}})


def test_unsupported_keys_are_refused():
    with pytest.raises(codex.Refused, match="timeout"):
        codex.server("x", {"command": "x", "timeout": 5})


def test_writes_servers_serena_and_keys(fake_home):
    _personal_mcp({"gh": {"command": "gh-mcp", "env": {"GITHUB_TOKEN": "${GITHUB_TOKEN}"}}})
    _apply()
    text = _config()
    assert "[mcp_servers.gh]\ncommand = \"gh-mcp\"\nenv_vars = [\"GITHUB_TOKEN\"]\n" in text
    assert '[mcp_servers.serena]\ncommand = "serena"\nargs = ["start-mcp-server", "--context=codex", "--project-from-cwd"]\n' in text
    assert text.startswith('model_reasoning_effort = "medium"\n')
    assert "[tui]\nnotifications = true\n" in text
    record = json.loads(codex.record_path().read_text())
    assert set(record["tables"]) == {"gh", "serena"} and set(record["keys"]) == {"model_reasoning_effort", "tui.notifications"}


def test_second_run_changes_nothing(fake_home):
    _personal_mcp({"gh": {"command": "gh-mcp"}})
    _apply()
    before = _config()
    assert _apply() == [] and _config() == before


def test_removed_server_disappears_and_changed_one_is_replaced(fake_home):
    _personal_mcp({"a": {"command": "a"}, "b": {"command": "b"}})
    _apply()
    _personal_mcp({"b": {"command": "b2"}})
    _apply()
    text = _config()
    assert "[mcp_servers.a]" not in text and 'command = "b2"' in text and 'command = "b"\n' not in text


def test_foreign_table_and_key_are_left_alone(fake_home):
    path = paths.codex_home() / "config.toml"
    path.parent.mkdir(parents=True)
    mine = 'model_reasoning_effort = "high"\n\n[mcp_servers.gh]\ncommand = "my-own-gh"\n'
    path.write_text(mine, encoding="utf-8")
    _personal_mcp({"gh": {"command": "gh-mcp"}})
    lines = _apply()
    text = _config()
    assert 'model_reasoning_effort = "high"' in text and 'command = "my-own-gh"' in text and "gh-mcp" not in text
    assert any("gh" in l and "left as is" in l for l in lines)
    assert any("model_reasoning_effort" in l and "left as is" in l for l in lines)


def test_user_edit_of_an_owned_table_is_kept(fake_home):
    _personal_mcp({"gh": {"command": "gh-mcp"}})
    _apply()
    path = paths.codex_home() / "config.toml"
    path.write_text(_config().replace('command = "gh-mcp"', 'command = "gh-mcp"\nstartup_timeout_sec = 30'), encoding="utf-8")
    _personal_mcp({})
    lines = _apply()
    assert "startup_timeout_sec = 30" in _config() and any("changed by you" in l for l in lines)


def test_existing_tui_table_gets_the_key(fake_home):
    path = paths.codex_home() / "config.toml"
    path.parent.mkdir(parents=True)
    path.write_text('[tui]\ntheme = "dark"\n', encoding="utf-8")
    _apply()
    text = _config()
    assert text.count("[tui]") == 1 and "[tui]\ntheme = \"dark\"\nnotifications = true\n" in text


@pytest.mark.skipif(sys.version_info < (3, 11), reason="the parse check needs tomllib")
def test_unparseable_result_writes_nothing(fake_home):
    path = paths.codex_home() / "config.toml"
    path.parent.mkdir(parents=True)
    weird = 'tui.notifications = false\n'  # a dotted key: adding a [tui] table would redefine it
    path.write_text(weird, encoding="utf-8")
    lines = _apply()
    assert path.read_text(encoding="utf-8") == weird
    assert any(l.startswith("skipped") and "parse" in l for l in lines)


def test_dry_run_reports_pending_changes_without_writing(fake_home):
    _personal_mcp({"gh": {"command": "gh-mcp"}})
    assert codex.apply_config(backup.Backup(description="t"), dry_run=True) == ["config.toml: changes pending"]
    assert not (paths.codex_home() / "config.toml").exists()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_codex_config.py`
Expected: FAIL with `AttributeError: module 'loadout.codex' has no attribute 'toml_value'`.

- [ ] **Step 3: Implement** (append to `cli/loadout/codex.py`; add `import json` at the top)

```python
SERENA = {"command": "serena", "args": ["start-mcp-server", "--context=codex", "--project-from-cwd"]}
_BARE = re.compile(r"^[A-Za-z0-9_-]+$")
_VAR = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")
_BEARER = re.compile(r"^Bearer \$\{([A-Za-z_][A-Za-z0-9_]*)\}$")
_SUPPORTED = {"type", "command", "args", "env", "url", "headers"}


class Refused(Exception):
    """A server config loadout will not write into Codex, with the reason and the fix."""


def toml_key(key: str) -> str:
    return key if _BARE.match(key) else json.dumps(key, ensure_ascii=False)


def toml_value(value) -> str:
    """Strings, booleans, lists of strings, tables of strings. JSON's escapes are valid TOML basic-string escapes."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return "[" + ", ".join(toml_value(v) for v in value) + "]"
    if isinstance(value, dict) and all(isinstance(v, str) for v in value.values()):
        return "{ " + ", ".join(f"{toml_key(k)} = {toml_value(v)}" for k, v in value.items()) + " }" if value else "{}"
    raise Refused(f"unsupported value type {type(value).__name__}")


def _plain(name: str, key: str, value: str) -> None:
    if "${" in value:
        raise Refused(f"mcp {name}: {key} mixes text and a variable; Codex can forward only a whole value from a variable")
    from .secrets import looks_secret
    if looks_secret(key, value):
        raise Refused(f"mcp {name}: {key} holds a plaintext secret; move it to secrets.env and refer to it as ${{{key}}}")


def server(name: str, cfg: dict) -> dict:
    """A Claude-style MCP config as Codex keys; secrets only as variable names."""
    unknown = sorted(set(cfg) - _SUPPORTED)
    if unknown:
        raise Refused(f"mcp {name}: Codex mapping does not support {', '.join(unknown)}")
    out: dict = {}
    if isinstance(cfg.get("url"), str):
        out["url"] = cfg["url"]
        plain, env_headers = {}, {}
        for key, value in (cfg.get("headers") or {}).items():
            bearer = _BEARER.match(value) if key.lower() == "authorization" else None
            var = _VAR.match(value)
            if bearer:
                out["bearer_token_env_var"] = bearer.group(1)
            elif var:
                env_headers[key] = var.group(1)
            else:
                _plain(name, key, value)
                plain[key] = value
        if plain:
            out["http_headers"] = plain
        if env_headers:
            out["env_http_headers"] = env_headers
        return out
    if not isinstance(cfg.get("command"), str):
        raise Refused(f"mcp {name}: neither a command nor a url")
    out["command"] = cfg["command"]
    if cfg.get("args"):
        out["args"] = list(cfg["args"])
    plain, forwarded = {}, []
    for key, value in (cfg.get("env") or {}).items():
        var = _VAR.match(value)
        if var and var.group(1) != key:
            raise Refused(f"mcp {name}: env {key} refers to ${{{var.group(1)}}}; Codex forwards a variable only under "
                          f"its own name, so name it {key} in secrets.env")
        if var:
            forwarded.append(key)
        else:
            _plain(name, key, value)
            plain[key] = value
    if plain:
        out["env"] = plain
    if forwarded:
        out["env_vars"] = forwarded
    return out


def table_text(name: str, srv: dict) -> str:
    return "\n".join([f"[mcp_servers.{toml_key(name)}]", *(f"{toml_key(k)} = {toml_value(v)}" for k, v in srv.items())]) + "\n"


def record_path() -> Path:
    return paths.state_dir() / "codex-config.json"


def desired_tables() -> tuple[dict[str, str], list[str]]:
    """Table text per server name, and the lines for servers that cannot be mapped."""
    servers = load_json(paths.personal_root() / "mcp.json").get("mcpServers", {})
    tables, problems = {"serena": table_text("serena", SERENA)}, []
    for name, cfg in (servers if isinstance(servers, dict) else {}).items():
        try:
            tables[name] = table_text(name, server(name, cfg))
        except Refused as exc:
            problems.append(f"skipped {exc}")
    return tables, problems


def desired_keys() -> list[tuple[str, str, object]]:
    """(table, key, value); table "" is the top level. Only preferences with a Codex equivalent."""
    from . import preferences
    state = preferences.detect()

    def answer(pid):
        return state[pid].value or preferences.by_id(pid)["default"]
    return [("", "model_reasoning_effort", answer("effort_level")),
            ("tui", "notifications", answer("agent_push_notifications") == "yes")]


def _sections(lines: list[str]) -> list[list]:
    """[[header or None, [lines]]]: the top level first, then one entry per [table] or [[array]] header."""
    out = [[None, []]]
    for line in lines:
        s = line.strip()
        if s.startswith("[") and not s.startswith("[["):
            out.append([s[1:s.index("]")].strip(), [line]])
        elif s.startswith("[["):
            out.append([s, [line]])
        else:
            out[-1][1].append(line)
    return out


def _text(section_lines: list[str]) -> str:
    return "\n".join(section_lines).rstrip("\n").rstrip() + "\n"


def apply_config(bk, dry_run: bool = False) -> list[str]:
    path = paths.codex_home() / "config.toml"
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    record = load_json(record_path())
    owned_tables, owned_keys = dict(record.get("tables", {})), dict(record.get("keys", {}))
    sections = _sections(old.splitlines())
    tables, lines = desired_tables()

    # tables: drop or keep what loadout wrote, never touch anything else
    by_header = {s[0]: s for s in sections if s[0]}
    for name, text in list(owned_tables.items()):
        sec = by_header.get(f"mcp_servers.{toml_key(name)}")
        if sec is None:
            owned_tables.pop(name)
        elif _text(sec[1]) != text:
            lines.append(f"mcp {name}: left as is in config.toml (changed by you); loadout no longer manages it")
            owned_tables.pop(name)
        elif tables.get(name) != text:
            sections.remove(sec)
            owned_tables.pop(name)
    by_header = {s[0]: s for s in sections if s[0]}
    for name, text in tables.items():
        header = f"mcp_servers.{toml_key(name)}"
        if header in by_header:
            if owned_tables.get(name) != text:
                lines.append(f"mcp {name}: left as is, config.toml already has a server of that name")
            continue
        sections.append([header, text.rstrip("\n").splitlines()])
        owned_tables[name] = text

    # keys: one line each, in their table
    for table, key, value in desired_keys():
        dotted = f"{table}.{key}" if table else key
        line = f"{key} = {toml_value(value)}"
        target = next((s for s in sections if s[0] == (table or None)), None)
        if target is None:
            sections.append([table, [f"[{table}]", line]])
            owned_keys[dotted] = line
            continue
        found = next((i for i, l in enumerate(target[1]) if re.match(rf"^\s*{re.escape(key)}\s*=", l)), None)
        if found is None:
            insert = len(target[1])
            while insert > (1 if target[0] else 0) and not target[1][insert - 1].strip():
                insert -= 1
            target[1].insert(insert, line)
            owned_keys[dotted] = line
        elif target[1][found].strip() == line:
            owned_keys[dotted] = line
        elif owned_keys.get(dotted) == target[1][found].strip():
            target[1][found] = line
            owned_keys[dotted] = line
        else:
            lines.append(f"{dotted}: left as is in config.toml (your value)")
            owned_keys.pop(dotted, None)

    parts = ["\n".join(sections[0][1]).strip("\n")] if any(l.strip() for l in sections[0][1]) else []
    parts += ["\n".join(s[1]).strip("\n") for s in sections[1:]]
    new = "\n\n".join(p for p in parts if p) + "\n" if parts else ""
    if new == old or new.strip() == old.strip():
        return lines
    if dry_run:
        return lines + ["config.toml: changes pending"]
    try:
        import tomllib
        tomllib.loads(new)
    except ImportError:
        pass
    except Exception as exc:  # tomllib.TOMLDecodeError
        return lines + [f"skipped {path}: the result would not parse ({exc}); nothing written, fix the file by hand"]
    if path.exists() and not record:
        bk.save_copy(path, "Codex config.toml before loadout's first change")
    elif not path.exists():
        bk.record_created(path, "created Codex config.toml")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new, encoding="utf-8", newline="\n")
    record_path().parent.mkdir(parents=True, exist_ok=True)
    save_json(record_path(), {"tables": owned_tables, "keys": owned_keys})
    return lines
```

Notes for the implementer:
- `test_writes_servers_serena_and_keys` expects the top-level key first: the top section starts empty, the key line is inserted there, then tables follow, joined by blank lines.
- `test_second_run_changes_nothing` expects `[]`: with nothing to change, `new == old`.
- The spec says "refused for that server": `desired_tables` turns `Refused` into a `skipped …` line (matches `out.PROBLEM`).

- [ ] **Step 4: Run the tests**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_codex_config.py`
Expected: 14 passed. Then also with Python 3.10: `uv run --python 3.10 --with pytest pytest -q tests/test_codex_config.py` → 13 passed, 1 skipped.

- [ ] **Step 5: Commit**

```bash
git add cli/loadout/codex.py tests/test_codex_config.py
git commit -m "feat(codex): MCP servers, Serena's Codex context and settings as owned config.toml tables and keys"
```

---

### Task 4: Plugins through their marketplaces

**Files:**
- Modify: `cli/loadout/codex.py`
- Test: `tests/test_codex_plugins.py`

**Interfaces:**
- Consumes: `settings_merge.desired_settings() -> dict` (`enabledPlugins`, `extraKnownMarketplaces`), `runner.run`, `Backup.record_command`.
- Produces: `codex.OFFICIAL = "anthropics/claude-plugins-official"`, `codex.plugin_routes(settings: dict) -> tuple[dict[str, list[str]], list[str]]`, `codex.installed_plugins() -> set[str] | None`, `codex.apply_plugins(bk, refresh: bool = False) -> list[str]`.

- [ ] **Step 1: Write the failing tests**

`tests/test_codex_plugins.py`:

```python
"""Every plugin enabled for Claude Code goes into Codex through the same marketplace source."""
import json

from loadout import backup, codex, runner

SETTINGS = {
    "enabledPlugins": {"loadout@agent-loadout": True, "superpowers@claude-plugins-official": True,
                       "impeccable@impeccable": True, "hookify@claude-plugins-official": False,
                       "local-thing@my-dir": True},
    "extraKnownMarketplaces": {"agent-loadout": {"source": {"source": "github", "repo": "jonasyr/agent-loadout"}},
                               "impeccable": {"source": {"source": "github", "repo": "pbakaus/impeccable"}},
                               "my-dir": {"source": {"source": "directory", "path": "/x"}}},
}


def test_routes_follow_the_marketplace_source():
    routes, missing = codex.plugin_routes(SETTINGS)
    assert routes == {"jonasyr/agent-loadout": ["loadout"], codex.OFFICIAL: ["superpowers"],
                      "pbakaus/impeccable": ["impeccable"]}
    assert missing == ["local-thing@my-dir"]


def _fake(fake_runner, installed=()):
    def add(src, name, already=False):
        fake_runner.responses[("codex", "plugin", "marketplace", "add", src)] = runner.Result(
            0, json.dumps({"marketplaceName": name, "alreadyAdded": already}), "")
    add("jonasyr/agent-loadout", "agent-loadout")
    add(codex.OFFICIAL, "claude-plugins-official", already=True)
    add("pbakaus/impeccable", "impeccable")
    fake_runner.responses[("codex", "plugin", "list")] = runner.Result(
        0, json.dumps({"installed": [{"pluginId": p} for p in installed], "available": []}), "")


def test_installs_what_is_missing_and_records_undo(fake_home, fake_runner, monkeypatch):
    from loadout import settings_merge
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: SETTINGS)
    _fake(fake_runner, installed=["superpowers@claude-plugins-official"])
    bk = backup.Backup(description="t")
    lines = codex.apply_plugins(bk)
    adds = [c[3] for c in fake_runner.calls if c[:3] == ["codex", "plugin", "add"]]
    assert adds == ["loadout@agent-loadout", "impeccable@impeccable"]
    undo = [s["undo"]["run"] for s in bk.steps]
    assert ["codex", "plugin", "marketplace", "remove", "agent-loadout"] in undo
    assert ["codex", "plugin", "remove", "loadout@agent-loadout"] in undo
    assert ["codex", "plugin", "marketplace", "remove", "claude-plugins-official"] not in undo  # already there
    assert any("local-thing@my-dir" in l and "no Codex route" in l for l in lines)


def test_refresh_upgrades_marketplaces_and_reinstalls(fake_home, fake_runner, monkeypatch):
    from loadout import settings_merge
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: {"enabledPlugins": {"loadout@agent-loadout": True},
                                                                     "extraKnownMarketplaces": SETTINGS["extraKnownMarketplaces"]})
    _fake(fake_runner, installed=["loadout@agent-loadout"])
    fake_runner.responses[("codex", "plugin", "marketplace", "add", "jonasyr/agent-loadout")] = runner.Result(
        0, json.dumps({"marketplaceName": "agent-loadout", "alreadyAdded": True}), "")
    codex.apply_plugins(backup.Backup(description="t"), refresh=True)
    assert ["codex", "plugin", "marketplace", "upgrade", "agent-loadout"] in fake_runner.calls
    assert ["codex", "plugin", "add", "loadout@agent-loadout", "--json"] in fake_runner.calls


def test_failed_marketplace_is_reported_and_others_continue(fake_home, fake_runner, monkeypatch):
    from loadout import settings_merge
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: SETTINGS)
    _fake(fake_runner)
    fake_runner.responses[("codex", "plugin", "marketplace", "add", "pbakaus/impeccable")] = runner.Result(1, "", "network down")
    lines = codex.apply_plugins(backup.Backup(description="t"))
    assert any("pbakaus/impeccable" in l and "failed" in l for l in lines)
    assert ["codex", "plugin", "add", "loadout@agent-loadout", "--json"] in fake_runner.calls
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_codex_plugins.py`
Expected: FAIL with `AttributeError: … 'plugin_routes'`.

- [ ] **Step 3: Implement** (append to `cli/loadout/codex.py`)

```python
OFFICIAL = "anthropics/claude-plugins-official"


def _json(text: str):
    """codex prints warnings before its JSON on some setups; read from the first brace."""
    start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=-1)
    return json.loads(text[start:]) if start >= 0 else None


def _tail(res: runner.Result) -> str:
    return (res.stderr.strip() or res.stdout.strip())[-300:]


def plugin_routes(settings: dict) -> tuple[dict[str, list[str]], list[str]]:
    """{GitHub source: [plugin names]} for every plugin enabled for Claude Code, and those without a GitHub source."""
    markets = settings.get("extraKnownMarketplaces", {})
    routes: dict[str, list[str]] = {}
    missing = []
    for pid, on in settings.get("enabledPlugins", {}).items():
        if on is not True or "@" not in pid:
            continue
        name, market = pid.rsplit("@", 1)
        source = markets.get(market, {}).get("source", {})
        src = OFFICIAL if market == "claude-plugins-official" else (
            source.get("repo") if source.get("source") == "github" else None)
        if src is None:
            missing.append(pid)
        else:
            routes.setdefault(src, []).append(name)
    return routes, missing


def installed_plugins() -> set[str] | None:
    res = runner.run(["codex", "plugin", "list", "--json"], timeout=120)
    data = _json(res.stdout) if res.ok else None
    return {p.get("pluginId") for p in data.get("installed", [])} if isinstance(data, dict) else None


def apply_plugins(bk, refresh: bool = False) -> list[str]:
    from .settings_merge import desired_settings
    routes, missing = plugin_routes(desired_settings())
    lines = [f"plugin {pid}: no Codex route (its marketplace is not on GitHub)" for pid in missing]
    installed = installed_plugins() or set()
    for src, plugins in routes.items():
        res = runner.run(["codex", "plugin", "marketplace", "add", src, "--json"], timeout=900)
        info = _json(res.stdout) if res.ok else None
        if not isinstance(info, dict) or "marketplaceName" not in info:
            lines.append(f"marketplace {src}: failed: {_tail(res)}")
            continue
        market = info["marketplaceName"]
        if not info.get("alreadyAdded"):
            bk.record_command(f"codex marketplace {market}", ["codex", "plugin", "marketplace", "remove", market])
        elif refresh:
            runner.run(["codex", "plugin", "marketplace", "upgrade", market], timeout=900)
        for name in plugins:
            pid = f"{name}@{market}"
            if pid in installed and not refresh:
                continue
            res = runner.run(["codex", "plugin", "add", pid, "--json"], timeout=600)
            if not res.ok:
                lines.append(f"plugin {pid}: failed: {_tail(res)}")
            elif pid not in installed:
                bk.record_command(f"codex plugin {pid}", ["codex", "plugin", "remove", pid])
                lines.append(f"plugin {pid}: installed")
    return lines
```

- [ ] **Step 4: Run the tests**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_codex_plugins.py`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add cli/loadout/codex.py tests/test_codex_plugins.py
git commit -m "feat(codex): every plugin enabled for Claude Code through the same marketplace source"
```

---

### Task 5: Skills and drift

**Files:**
- Modify: `cli/loadout/codex.py`
- Test: `tests/test_codex_skills_drift.py`

**Interfaces:**
- Consumes: `link.LINKS() -> list[tuple[Path, Path]]`, `link._link_one(dest, src, bk) -> str | None`, `own.decisions() -> dict[str, str]`, `paths.claude_json()`, `paths.agents_skills()`, `codex.record_path()` (Task 3).
- Produces: `codex.skill_links() -> list[tuple[Path, Path]]`, `codex.apply_skills(bk) -> list[str]`, `codex.mcp_names() -> set[str] | None`, `codex.drift() -> list[str]`.

- [ ] **Step 1: Write the failing tests**

`tests/test_codex_skills_drift.py`:

```python
"""Personal skills linked for Codex; MCP servers and skills present in only one agent are reported."""
import json
import os

import pytest

from loadout import backup, codex, paths, runner


def _personal_skill(name):
    d = paths.personal_root() / "skills" / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: x\n---\n", encoding="utf-8")
    return d


@pytest.mark.skipif(os.name == "nt", reason="symlinks need Developer Mode on Windows; copy mode is covered by link tests")
def test_personal_skills_are_linked_for_codex(fake_home):
    src = _personal_skill("my-skill")
    lines = codex.apply_skills(backup.Backup(description="t"))
    dest = paths.agents_skills() / "my-skill"
    assert dest.is_symlink() and dest.resolve() == src.resolve() and lines


def _codex_mcp(fake_runner, names):
    fake_runner.responses[("codex", "mcp", "list")] = runner.Result(0, json.dumps([{"name": n} for n in names]), "")


def test_drift_names_servers_and_skills_in_only_one_agent(fake_home, fake_runner):
    paths.claude_json().write_text(json.dumps({"mcpServers": {"only-claude": {}, "both": {}}}), encoding="utf-8")
    _codex_mcp(fake_runner, ["both", "only-codex", "serena"])
    (paths.claude_home() / "skills" / "claude-skill").mkdir(parents=True)
    (paths.agents_skills() / "codex-skill").mkdir(parents=True)
    (paths.agents_skills() / ".system").mkdir()
    codex.record_path().parent.mkdir(parents=True, exist_ok=True)
    codex.record_path().write_text(json.dumps({"tables": {"serena": "x"}, "keys": {}}))
    lines = codex.drift()
    assert any('"only-claude" only in Claude Code' in l for l in lines)
    assert any('"only-codex" only in Codex' in l for l in lines)
    assert any('"claude-skill" only in Claude Code' in l for l in lines)
    assert any('"codex-skill" only in Codex' in l for l in lines)
    assert not any('"both"' in l or "serena" in l or ".system" in l for l in lines)


def test_drift_ignores_personal_layer_and_left_items(fake_home, fake_runner):
    paths.claude_json().write_text(json.dumps({"mcpServers": {"mine": {}, "left": {}}}), encoding="utf-8")
    (paths.personal_root()).mkdir(parents=True)
    (paths.personal_root() / "mcp.json").write_text(json.dumps({"mcpServers": {"mine": {"command": "x"}}}))
    paths.state_dir().mkdir(parents=True, exist_ok=True)
    (paths.state_dir() / "own-decisions.json").write_text(json.dumps({"mcp:left": "leave"}))
    _codex_mcp(fake_runner, [])
    assert codex.drift() == []


def test_drift_without_codex_answer_is_empty(fake_home, fake_runner):
    fake_runner.responses[("codex", "mcp", "list")] = runner.Result(1, "", "boom")
    paths.claude_json().write_text(json.dumps({"mcpServers": {"x": {}}}), encoding="utf-8")
    assert codex.drift() == []
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_codex_skills_drift.py`
Expected: FAIL with `AttributeError: … 'apply_skills'`.

- [ ] **Step 3: Implement** (append to `cli/loadout/codex.py`)

```python
def skill_links() -> list[tuple[Path, Path]]:
    """The same personal skills (folders and skills.json pointers) that link.py links for Claude Code."""
    from . import link
    claude_skills = paths.claude_home() / "skills"
    return [(paths.agents_skills() / dest.name, src) for dest, src in link.LINKS() if dest.parent == claude_skills]


def apply_skills(bk) -> list[str]:
    from . import link
    return [line for dest, src in skill_links() if (line := link._link_one(dest, src, bk))]


def mcp_names() -> set[str] | None:
    res = runner.run(["codex", "mcp", "list", "--json"], timeout=120)
    data = _json(res.stdout) if res.ok else None
    return {s.get("name") for s in data if isinstance(s, dict)} if isinstance(data, list) else None


def _skill_names(folder: Path) -> set[str]:
    return {p.name for p in folder.iterdir() if not p.name.startswith(".") and p.name != "synced"} if folder.is_dir() else set()


def drift() -> list[str]:
    """Names present in only one agent and accounted for by neither the kit, the personal layer nor a 'leave'."""
    from . import own
    in_codex = mcp_names()
    if in_codex is None:
        return []
    left = {key.split(":")[-1] for key in own.decisions()}
    personal = set(load_json(paths.personal_root() / "mcp.json").get("mcpServers", {}))
    owned = set(load_json(record_path()).get("tables", {}))
    in_claude = set(load_json(paths.claude_json()).get("mcpServers", {}))
    accounted = left | personal | owned
    out = [f'MCP server "{n}" only in Claude Code (record it with loadout adopt, then both get it)'
           for n in sorted(in_claude - in_codex - accounted)]
    out += [f'MCP server "{n}" only in Codex (add it to your personal layer\'s mcp.json, see docs/how-to/codex.md)'
            for n in sorted(in_codex - in_claude - accounted - _plugin_servers())]
    claude_skills, codex_skills = _skill_names(paths.claude_home() / "skills"), _skill_names(paths.agents_skills())
    personal_skills = {dest.name for dest, _ in skill_links()}
    out += [f'skill "{n}" only in Claude Code (record it with loadout adopt, then both get it)'
            for n in sorted(claude_skills - codex_skills - personal_skills - left)]
    out += [f'skill "{n}" only in Codex (copy it into your personal layer\'s skills/, see docs/how-to/codex.md)'
            for n in sorted(codex_skills - claude_skills - personal_skills - left)]
    return out


def _plugin_servers() -> set[str]:
    """MCP servers that Codex has from installed plugins (their .mcp.json), not from the user."""
    names: set[str] = set()
    for mcp in (paths.codex_home() / "plugins" / "cache").glob("*/*/*/.mcp.json"):
        names |= set(load_json(mcp).get("mcpServers", {}))
    return names
```

- [ ] **Step 4: Run the tests**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_codex_skills_drift.py`
Expected: 4 passed (1 skipped on Windows).

- [ ] **Step 5: Commit**

```bash
git add cli/loadout/codex.py tests/test_codex_skills_drift.py
git commit -m "feat(codex): personal skills in ~/.agents/skills and a drift report between the agents"
```

---

### Task 6: The plugin's Codex manifest, hooks and type check

**Files:**
- Create: `plugins/loadout/.codex-plugin/plugin.json`, `plugins/loadout/hooks/codex.json`, `plugins/loadout/hooks/typecheck.py`
- Test: `tests/test_codex_hooks.py`

**Interfaces:**
- Produces: `hooks/codex.json` (Codex hook config), `hooks/typecheck.py` with `changed_files(event: dict) -> list[Path]`, `checks(files: list[Path]) -> list[tuple[list[str], Path]]`, `main(stdin, stdout) -> int`; `tests/test_codex_hooks.OMITTED` (Claude hooks without a Codex counterpart and why).

- [ ] **Step 1: Write the failing tests**

`tests/test_codex_hooks.py`:

```python
"""The plugin's Codex hooks: every Claude hook has a Codex counterpart or a stated reason; the type check."""
import io
import json
import os
import sys

import pytest

from loadout import paths

PLUGIN = paths.kit_root() / "plugins" / "loadout"
sys.path.insert(0, str(PLUGIN / "hooks"))
import typecheck  # noqa: E402

# Claude hooks with no Codex counterpart, and why
OMITTED = {
    "codebase-memory-mcp hook-augment": "Codex has no Grep/Glob tools to augment",
    "reload_check.py": "compares Claude's installed_plugins.json; Codex loads plugins per session",
}
CODEX_ARGS = {"--client=claude-code": "--client=codex", "rtk hook claude": "rtk hook codex",
              "mcp__plugin_loadout_serena__": "mcp__serena__", "Write|Edit|MultiEdit": "Edit|Write"}


def _commands(path):
    hooks = json.loads(path.read_text(encoding="utf-8"))["hooks"]
    return {(event, g.get("matcher", ""), h["command"]) for event, groups in hooks.items() for g in groups for h in g["hooks"]}


def _codexify(text):
    for a, b in CODEX_ARGS.items():
        text = text.replace(a, b)
    return text


def test_manifest_points_codex_to_its_hooks():
    manifest = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "loadout" and manifest["hooks"] == "./hooks/codex.json"


def test_every_claude_hook_has_a_codex_counterpart_or_a_reason():
    codex_hooks = _commands(PLUGIN / "hooks" / "codex.json")
    for event, matcher, command in _commands(PLUGIN / "hooks" / "hooks.json"):
        if any(key in command for key in OMITTED):
            continue
        assert (event, _codexify(matcher), _codexify(command)) in codex_hooks, (event, matcher, command)
    assert not any("--client=claude-code" in c or "rtk hook claude" in c for _, _, c in codex_hooks)


def test_codex_hooks_add_the_type_check_after_edits():
    assert any(e == "PostToolUse" and m == "Edit|Write" and "typecheck.py" in c
               for e, m, c in _commands(PLUGIN / "hooks" / "codex.json"))


def test_changed_files_from_apply_patch_and_claude_edits(tmp_path):
    patch = "*** Begin Patch\n*** Update File: src/a.py\n@@\n-x\n+y\n*** Add File: b.ts\n+z\n*** End Patch\n"
    event = {"cwd": str(tmp_path), "tool_name": "apply_patch", "tool_input": {"command": patch}}
    assert typecheck.changed_files(event) == [tmp_path / "src/a.py", tmp_path / "b.ts"]
    absolute = tmp_path / "abs" / "c.rs"
    assert typecheck.changed_files({"cwd": "/elsewhere", "tool_input": {"file_path": str(absolute)}}) == [absolute]


def _fake_tool(bin_dir, name, exit_code, output):
    script = bin_dir / name
    script.write_text(f"#!/bin/sh\necho '{output}'\nexit {exit_code}\n", encoding="utf-8")
    script.chmod(0o755)


@pytest.mark.skipif(os.name == "nt", reason="fake checkers are shell scripts")
def test_errors_are_reported_and_clean_files_are_silent(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    (tmp_path / "a.py").write_text("x: int = 'no'\n")
    event = {"cwd": str(tmp_path), "tool_input": {"command": "*** Update File: a.py\n"}}
    _fake_tool(bin_dir, "pyright", 1, "a.py:1:10 - error: str is not int")
    out = io.StringIO()
    typecheck.main(io.StringIO(json.dumps(event)), out)
    reply = json.loads(out.getvalue())
    assert reply["decision"] == "block" and "str is not int" in reply["reason"]
    _fake_tool(bin_dir, "pyright", 0, "0 errors")
    out = io.StringIO()
    typecheck.main(io.StringIO(json.dumps(event)), out)
    assert out.getvalue() == ""


@pytest.mark.skipif(os.name == "nt", reason="fake checkers are shell scripts")
def test_slow_checker_is_reported_as_skipped(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    (bin_dir / "pyright").write_text("#!/bin/sh\nsleep 5\n", encoding="utf-8")
    (bin_dir / "pyright").chmod(0o755)
    monkeypatch.setattr(typecheck, "LIMIT", 0.5)
    (tmp_path / "a.py").write_text("x = 1\n")
    out = io.StringIO()
    typecheck.main(io.StringIO(json.dumps({"cwd": str(tmp_path), "tool_input": {"command": "*** Update File: a.py\n"}})), out)
    assert "skipped (timeout" in json.loads(out.getvalue())["reason"]


def test_missing_checker_and_bad_input_are_silent(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))  # no checkers at all
    (tmp_path / "a.py").write_text("x = 1\n")
    out = io.StringIO()
    typecheck.main(io.StringIO(json.dumps({"cwd": str(tmp_path), "tool_input": {"command": "*** Update File: a.py\n"}})), out)
    typecheck.main(io.StringIO("not json"), out)
    assert out.getvalue() == ""


def test_checks_pick_the_project_folder(tmp_path, monkeypatch):
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "tsconfig.json").write_text("{}")
    (tmp_path / "crate" / "src").mkdir(parents=True)
    (tmp_path / "crate" / "Cargo.toml").write_text("")
    monkeypatch.setattr(typecheck.shutil, "which", lambda name: f"/usr/bin/{name}")
    found = typecheck.checks([tmp_path / "web" / "x.ts", tmp_path / "crate" / "src" / "lib.rs"])
    assert (["tsc", "--noEmit", "-p", str(tmp_path / "web")], tmp_path / "web") in found
    assert (["cargo", "check", "--quiet", "--message-format=short"], tmp_path / "crate") in found
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_codex_hooks.py`
Expected: ERROR `ModuleNotFoundError: No module named 'typecheck'`.

- [ ] **Step 3: Implement**

`plugins/loadout/.codex-plugin/plugin.json`:

```json
{
  "name": "loadout",
  "description": "Core of agent-loadout for Codex: Serena and codebase-memory MCP servers, Codex hooks with a type check after edits, onboarding and documentation skills.",
  "author": { "name": "Jonas Weirauch" },
  "homepage": "https://github.com/jonasyr/agent-loadout",
  "repository": "https://github.com/jonasyr/agent-loadout",
  "license": "MIT",
  "skills": "./skills/",
  "mcpServers": "./.mcp.json",
  "hooks": "./hooks/codex.json"
}
```

`plugins/loadout/hooks/codex.json`: copy `hooks.json`, then apply exactly these changes:
- every `--client=claude-code` → `--client=codex`;
- `rtk hook claude` → `rtk hook codex`;
- the matcher `mcp__plugin_loadout_serena__.*` → `mcp__serena__.*` (in Codex the user-level `serena` server from Task 3 replaces the plugin's);
- remove the `Grep|Glob` group (`codebase-memory-mcp hook-augment`) and both `reload_check.py` entries;
- add to `PostToolUse` → the `Write|Edit|MultiEdit` group's matcher becomes `Edit|Write` (Codex's name for `apply_patch`), and add a second hook in that group: `"${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" --soft --python "${CLAUDE_PLUGIN_ROOT}/hooks/typecheck.py"` with `"timeout": 90`.

`plugins/loadout/hooks/typecheck.py`:

```python
"""Codex has no LSP plugins: after an edit, run the language's checker on the changed files and tell the agent.

Codex-only (hooks/codex.json). Python: pyright on the files; TypeScript: tsc --noEmit for the nearest tsconfig;
Rust: cargo check for the nearest Cargo.toml. Each check is capped at LIMIT seconds. Silent when clean or when the
checker is missing.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

LIMIT = 20
PATCH_FILE = re.compile(r"^\*\*\* (?:Add|Update) File: (.+?)\s*$", re.M)


def changed_files(event: dict) -> list:
    tool_input = event.get("tool_input") or {}
    cwd = Path(event.get("cwd") or ".")
    names = PATCH_FILE.findall(tool_input["command"]) if isinstance(tool_input.get("command"), str) else []
    if isinstance(tool_input.get("file_path"), str):
        names.append(tool_input["file_path"])
    return [cwd / name for name in names]  # an absolute name stays absolute


def _nearest(path: Path, marker: str):
    return next((d for d in path.parents if (d / marker).exists()), None)


def checks(files: list) -> list:
    """(command, folder) per checker that applies to the files and is installed."""
    found = []
    py = [str(f) for f in files if f.suffix in (".py", ".pyi")]
    if py and shutil.which("pyright"):
        found.append((["pyright", *py], Path(py[0]).parent))
    for project in dict.fromkeys(_nearest(f, "tsconfig.json") for f in files if f.suffix in (".ts", ".tsx", ".mts", ".cts")):
        if project is not None and shutil.which("tsc"):
            found.append((["tsc", "--noEmit", "-p", str(project)], project))
    for crate in dict.fromkeys(_nearest(f, "Cargo.toml") for f in files if f.suffix == ".rs"):
        if crate is not None and shutil.which("cargo"):
            found.append((["cargo", "check", "--quiet", "--message-format=short"], crate))
    return found


def _run(cmd: list, cwd: Path):
    try:
        res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=LIMIT)
    except subprocess.TimeoutExpired:
        return f"type check skipped (timeout after {LIMIT} s): {' '.join(cmd[:2])}"
    except OSError:
        return None
    if res.returncode == 0:
        return None
    return f"$ {' '.join(cmd)}\n" + (res.stdout + res.stderr).strip()[-4000:]


def main(stdin=sys.stdin, stdout=sys.stdout) -> int:
    try:
        event = json.load(stdin)
    except (ValueError, OSError):
        return 0
    files = [f for f in changed_files(event) if f.exists()]
    reports = [r for cmd, cwd in checks(files) if (r := _run(cmd, cwd))]
    if reports:
        stdout.write(json.dumps({"decision": "block",
                                 "reason": "Type check after your edit:\n\n" + "\n\n".join(reports)}) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests and the plugin validation**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_codex_hooks.py tests/test_hooks.py tests/test_repo_static.py`
Expected: all pass.
Run: `claude plugin validate plugins/loadout` is a read-only validation of the Claude manifest; per AGENTS.md it is the documented command. Expected: valid (the `.codex-plugin/` folder is ignored by Claude Code).

- [ ] **Step 5: Verify Codex reads the manifest (sandbox)**

```bash
S="$SCRATCH/codex-hooks"; rm -rf "$S"; mkdir -p "$S/home/.codex"; cp -r . "$S/kit"; rm -rf "$S/kit/.git"
HOME="$S/home" CODEX_HOME="$S/home/.codex" codex plugin marketplace add "$S/kit" --json
HOME="$S/home" CODEX_HOME="$S/home/.codex" codex plugin add loadout@agent-loadout --json
HOME="$S/home" CODEX_HOME="$S/home/.codex" codex mcp list --json
ls "$S/home/.codex/plugins/cache/agent-loadout/loadout/local/hooks"
rm -rf "$S"
```

Expected: the plugin installs; `mcp list` still shows `serena` and `codebase-memory-mcp` (so `mcpServers` in the Codex manifest works); the cache holds `codex.json` and `typecheck.py`. If `mcp list` loses the servers, remove `"mcpServers"` from the manifest and retry (Codex then discovers `.mcp.json` itself); ledger the outcome.

- [ ] **Step 6: Commit**

```bash
git add plugins/loadout/.codex-plugin plugins/loadout/hooks/codex.json plugins/loadout/hooks/typecheck.py tests/test_codex_hooks.py
git commit -m "feat(plugin): Codex manifest and hooks with Codex arguments and a type check after edits"
```

---

### Task 7: Wiring: bootstrap, sync, check

**Files:**
- Modify: `cli/loadout/codex.py` (`apply_all`, `checks`), `cli/loadout/bootstrap.py`, `cli/loadout/maintenance.py`, `cli/loadout/check.py`
- Test: `tests/test_codex_wiring.py`

**Interfaces:**
- Consumes: Tasks 1–6.
- Produces: `codex.apply_all(bk, refresh: bool = False) -> list[str]`, `codex.checks() -> list[CheckResult]`, `codex.HOOKS_TODO: str`.

- [ ] **Step 1: Write the failing tests**

`tests/test_codex_wiring.py`:

```python
"""Codex in bootstrap, the daily sync and the health check; nothing changes for Claude-only users."""
import json

from loadout import bootstrap, check, codex, maintenance, out, paths, runner


def _run(**kw):
    args = dict(install=False, yes=True, plugins=False, adopt_step=False, ask=lambda q: "", interactive=False)
    args.update(kw)
    return bootstrap.bootstrap(**args)


def _personal(fake_home):
    (fake_home / ".config/loadout/personal").mkdir(parents=True)


def test_bootstrap_without_codex_is_unchanged(fake_home, fake_runner, capsys):
    _personal(fake_home)
    fake_runner.missing.add("codex")
    _run()
    text = capsys.readouterr().out
    assert "Codex" not in text and not any(c[0] == "codex" for c in fake_runner.calls)


def test_bootstrap_asks_once_when_codex_is_found(fake_home, fake_runner, monkeypatch):
    _personal(fake_home)
    monkeypatch.setattr(codex, "apply_all", lambda bk, refresh=False: ["instructions written"])
    monkeypatch.setattr(codex, "unavailable", lambda: None)
    asked = []

    def ask(q):
        asked.append(q)
        return "y" if "Codex found" in q else ""
    _run(yes=False, interactive=True, ask=ask)
    assert sum("Codex found" in q for q in asked) == 1 and codex.enabled()
    asked.clear()
    _run(yes=False, interactive=True, ask=ask)
    assert not any("Codex found" in q for q in asked), "asked only once"


def test_bootstrap_sets_up_codex_and_lists_the_hooks_step(fake_home, fake_runner, monkeypatch, capsys):
    _personal(fake_home)
    codex.set_enabled(True)
    monkeypatch.setattr(codex, "unavailable", lambda: None)
    monkeypatch.setattr(codex, "apply_all", lambda bk, refresh=False: ["instructions written"])
    monkeypatch.setattr(out, "VERBOSE", False)
    _run()
    text = capsys.readouterr().out
    assert any(line.lstrip("✓! ").startswith("Codex") for line in text.splitlines())
    assert codex.HOOKS_TODO in text


def test_apply_all_runs_every_part(fake_home, fake_runner, monkeypatch):
    calls = []
    for name in ("apply_instructions", "apply_config", "apply_skills", "apply_plugins"):
        monkeypatch.setattr(codex, name, lambda *a, n=name, **k: calls.append(n) or ([] if n != "apply_instructions" else "ok"))
    codex.apply_all(object())
    assert calls == ["apply_instructions", "apply_config", "apply_skills", "apply_plugins"]


def test_check_without_codex_has_no_codex_group(fake_home, fake_runner):
    assert not any(r.name.startswith("Codex") for r in check.run_checks())


def test_check_reports_codex_state(fake_home, fake_runner, monkeypatch):
    codex.set_enabled(True)
    monkeypatch.setattr(codex, "unavailable", lambda: None)
    monkeypatch.setattr(codex, "installed_plugins", lambda: set())
    monkeypatch.setattr(codex, "drift", lambda: ['MCP server "x" only in Claude Code (record it with loadout adopt, then both get it)'])
    names = {r.name: r for r in check.run_checks() if r.name.startswith("Codex")}
    assert not names["Codex plugin"].ok and "loadout bootstrap" in names["Codex plugin"].fix
    assert names["Codex drift"].severity == "warn" and "only in Claude Code" in names["Codex drift"].detail


def test_sync_reapplies_codex_after_a_pull(fake_home, fake_runner, monkeypatch):
    codex.set_enabled(True)
    monkeypatch.setattr(codex, "unavailable", lambda: None)
    seen = []
    monkeypatch.setattr(codex, "apply_all", lambda bk, refresh=False: seen.append(refresh) or ["skipped mcp x: no"])
    monkeypatch.setattr(codex, "drift", lambda: ["skill \"y\" only in Codex (…)"])
    monkeypatch.setattr(maintenance, "pull_if_clean", lambda root: True)
    monkeypatch.setattr(maintenance, "apply_settings", lambda: None)
    (paths.personal_root() / ".git").mkdir(parents=True)  # the kit is a real clone; pull_if_clean is faked for both
    maintenance._maintain(0)
    notice = (paths.state_dir() / "pending-notice").read_text(encoding="utf-8")
    assert seen == [True] and "skipped mcp x" in notice and 'skill "y" only in Codex' in notice
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_codex_wiring.py`
Expected: FAIL with `AttributeError: … 'apply_all'` / missing `HOOKS_TODO`.

- [ ] **Step 3: Implement**

Append to `cli/loadout/codex.py`:

```python
HOOKS_TODO = "approve the loadout hooks in Codex once: start `codex`, then run /hooks"


def apply_all(bk, refresh: bool = False) -> list[str]:
    return [apply_instructions(bk), *apply_config(bk), *apply_skills(bk), *apply_plugins(bk, refresh=refresh)]


def checks() -> list:
    from .check import CheckResult
    if not enabled():
        return []
    problem = unavailable()
    if problem:
        return [CheckResult("Codex", False, problem, "install or update codex (mise use -g codex), or: loadout configure set target codex off", "warn")]
    results = [CheckResult("Codex", True)]
    installed = installed_plugins()
    ok = installed is not None and "loadout@agent-loadout" in installed
    results.append(CheckResult("Codex plugin", ok, "" if ok else "loadout plugin not installed in Codex", "loadout bootstrap"))
    path = paths.codex_home() / "AGENTS.md"
    current = splice(path.read_text(encoding="utf-8") if path.exists() else "", render_instructions())
    ok = path.exists() and current == path.read_text(encoding="utf-8")
    results.append(CheckResult("Codex instructions", ok, "" if ok else f"{_tilde(path)} lacks loadout's current block", "loadout bootstrap"))
    if (paths.codex_home() / "AGENTS.override.md").exists():
        results.append(CheckResult("Codex instructions", False, "AGENTS.override.md shadows AGENTS.md, so Codex ignores loadout's block",
                                   "merge it into AGENTS.md or remove it", "warn"))
    pending = apply_config(object(), dry_run=True)
    results.append(CheckResult("Codex config", not pending, "; ".join(pending), "loadout bootstrap", "warn"))
    from .settings_merge import desired_settings
    missing = plugin_routes(desired_settings())[1]
    if missing:
        results.append(CheckResult("Codex plugins", False, "no Codex route for " + ", ".join(missing), "", "warn"))
    lines = drift()
    results.append(CheckResult("Codex drift", not lines, "; ".join(lines), "loadout adopt (see docs/how-to/codex.md)", "warn"))
    return results
```

In `cli/loadout/check.py`, add to `run_checks()` after `*_plugins()`:

```python
def _codex() -> list[CheckResult]:
    from . import codex
    return codex.checks()
```

and `*_codex(),` in the list.

In `cli/loadout/bootstrap.py`, after the "Marketplaces and plugins" block and before `adopt.LAST_BACKUP = None`:

```python
    from . import codex
    if personal_ok and not yes and interactive and runner.have("codex") and not codex.decided():
        codex.set_enabled(ui.confirm(ask, "\nCodex found. Set it up with loadout too? [y/N] "))
    if codex.enabled():
        _step("Codex")
        problem = codex.unavailable()
        if problem:
            out.status("Codex", problem, "warn")
        else:
            lines = codex.apply_all(bk)
            failed = sum(1 for line in lines if PROBLEM.search(line))
            _report("Codex", "rules, plugins, MCP servers and skills set up" if not failed else f"{failed} problem(s) (below)", lines)
```

and in `still_to_do(key)`, before `return out`:

```python
    from . import codex
    if codex.enabled() and runner.have("codex"):
        out.append(codex.HOOKS_TODO)
```

In `cli/loadout/maintenance.py`, inside `if any(pulled):` after the links `try`, add:

```python
            try:
                from . import codex
                if codex.enabled() and codex.unavailable() is None:
                    bk = Backup(description="maintenance: Codex refreshed after a pull")
                    for line in codex.apply_all(bk, refresh=True):
                        if out_problem(line):
                            notify(f"loadout (Codex): {line}")
                    for line in codex.drift():
                        notify(f"loadout: {line}")
            except Exception as exc:  # never crash in the background; surface next session
                notify(f"loadout: could not refresh Codex after sync: {exc}")
```

with, near the top of `maintenance.py`:

```python
def out_problem(line: str) -> bool:
    from .out import PROBLEM
    return bool(PROBLEM.search(line))
```

`_maintain(0)` with an empty state folder finds the daily pull due; `pull_if_clean` is faked to report new commits.

- [ ] **Step 4: Run the tests and the full suite**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_codex_wiring.py`
Expected: 7 passed.
Run: `uv run --python 3.12 --with pytest pytest -q`
Expected: all pass. A Claude-only test that changes output means Codex leaked into a Claude path: fix the code, not the test.

- [ ] **Step 5: Commit**

```bash
git add cli/loadout/codex.py cli/loadout/bootstrap.py cli/loadout/maintenance.py cli/loadout/check.py tests/test_codex_wiring.py
git commit -m "feat(codex): Codex step in bootstrap, refresh in the daily sync, Codex group in loadout check"
```

---

### Task 8: Live sandbox check with the real Codex

**Files:**
- Create: `dev/codex-sandbox.sh` (maintainer tool; never run by CI)
- Modify: `tests/test_repo_static.py` only if a static test lists top-level folders (add `dev/`)

- [ ] **Step 1: Write the script**

`dev/codex-sandbox.sh`:

```bash
#!/usr/bin/env bash
# Runs the Codex part of loadout against the real codex CLI in a throwaway HOME and CODEX_HOME, then lists what Codex
# sees. Never touches your real ~/.codex. Needs codex on PATH and network access (marketplaces are git clones).
# Usage: dev/codex-sandbox.sh   (KEEP=1 keeps the sandbox folder)
set -euo pipefail
kit="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
sandbox="$(mktemp -d)"
[ -n "${KEEP:-}" ] || trap 'rm -rf "$sandbox"' EXIT
export HOME="$sandbox/home" CODEX_HOME="$sandbox/home/.codex" LOADOUT_PERSONAL="$sandbox/home/.config/loadout/personal"
mkdir -p "$CODEX_HOME" "$LOADOUT_PERSONAL/rules"
printf '# About me\n\n- Answers: concise.\n' > "$LOADOUT_PERSONAL/rules/me.md"
printf '{"codex": true}\n' > "$LOADOUT_PERSONAL/targets.json"
PYTHONPATH="$kit/cli" python3 - <<'PY'
from loadout import backup, codex
for line in codex.apply_all(backup.Backup(description="sandbox")):
    print(line)
PY
echo "--- plugins"; codex plugin list --json
echo "--- mcp"; codex mcp list --json
echo "--- AGENTS.md (head)"; head -5 "$CODEX_HOME/AGENTS.md"
echo "--- config.toml"; cat "$CODEX_HOME/config.toml"
echo "sandbox: $sandbox"
```

`chmod +x dev/codex-sandbox.sh`.

- [ ] **Step 2: Run it (agent may run it: it uses a temporary HOME and CODEX_HOME)**

Run: `KEEP=1 dev/codex-sandbox.sh 2>&1 | tail -60`
Expected:
- the instruction block written;
- the config with `serena` (`--context=codex`) and the two keys;
- plugins installed, at least `loadout@agent-loadout` and those from `claude-plugins-official` (a slow network may time out a marketplace: reported as `failed`, rerun once);
- `mcp list` shows `serena` once (Codex context), `codebase-memory-mcp`, `context7`, `microsoft-learn`.

Ledger the result, including which plugins installed and any failure. Then remove the kept folder.

- [ ] **Step 3: Commit**

```bash
git add dev/codex-sandbox.sh
git commit -m "chore(dev): sandbox run of the Codex target against the real codex CLI"
```

---

### Task 9: Docs, ADR, spec update

**Files:**
- Create: `docs/how-to/codex.md`, `docs/adr/0022-codex-as-a-second-target.md`
- Modify: `docs/explanation/architecture.md` (section "Other agents (planned)"), `docs/reference/cli.md`, `docs/reference/personal-layer.md`, `docs/reference/hooks.md`, `docs/explanation/security-and-trust.md`, `README.md`, `docs/README.md`, `docs/adr/README.md`, `AGENTS.md` (map: `codex.py`; ADR range 0001-0022), `CONTRIBUTING.md` (`dev/codex-sandbox.sh`), the spec (Rulings)

- [ ] **Step 1: How-to** `docs/how-to/codex.md`:

````markdown
# Use loadout with Codex

Use this page when you also work with OpenAI's Codex CLI and want it set up exactly like Claude Code: the same rules and preferences, plugins, MCP servers, skills and hooks, from the same kit and personal layer, kept current by the same daily sync.

## Switch it on

Bootstrap asks once when it finds `codex` on your PATH. To switch it on or off later:

```bash
loadout configure set target codex on
```

The choice is stored in your personal layer (`targets.json`), so it follows you to every machine. loadout needs codex 0.161 or newer.

Then approve loadout's hooks once in Codex: start `codex` and run `/hooks`. Codex runs plugin hooks only after you approve them, and again after they change.

## What Codex gets

| Kit part | In Codex |
|---|---|
| The kit's rules and your `me.md` | A block between `<!-- loadout:start -->` and `<!-- loadout:end -->` in `~/.codex/AGENTS.md`; your own text in that file stays as it is |
| The loadout plugin: skills, Serena, codebase-memory | The same plugin from the same marketplace; Serena runs in its Codex mode |
| The plugins you have enabled for Claude Code | The same plugins from the same marketplaces (Codex reads Claude Code marketplaces) |
| Type errors after each edit (Claude Code's LSP plugins) | A Codex-only hook runs pyright, `tsc --noEmit` or `cargo check` on the changed files and reports the errors; Serena's diagnostics tool works on request |
| Your personal MCP servers | Sections in `~/.codex/config.toml`; secrets only as variable names (`env_vars`) |
| Your personal skills | Links in `~/.agents/skills` |
| Effort and notifications | `model_reasoning_effort` and `tui.notifications` |

Preferences that live in `me.md` (answer language, commit style and so on) reach Codex through the instruction block. Claude Code settings without a Codex equivalent (thinking mode, auto mode, the permission list) have no effect on Codex.

## What stays different

- **Hooks need your approval once** in `/hooks` (see above).
- **Commit attribution.** Codex adds `Co-authored-by: Codex` to commits when your ChatGPT account has commit attribution turned on. That is an account setting, not a config key: turn it off in your ChatGPT account settings. loadout's rule against AI attribution reaches Codex through the instruction block, but cannot remove the trailer.
- **Type checks run per edit** instead of a language server that keeps running. Large TypeScript projects can take a few seconds; after 20 seconds the check reports itself as skipped.

## Keep both the same

Everything that comes from the kit and your personal layer reaches both agents. Something you add directly in one agent lives only there: the daily sync and `loadout check` report it, for example `MCP server "x" only in Claude Code`.

- **Only in Claude Code:** run `loadout adopt` and record it globally; the next sync puts it into both.
- **Only in Codex:** add it to your personal layer (`mcp.json` or `skills/`); the next sync puts it into both.

## What loadout changes in `~/.codex`

- `~/.codex/AGENTS.md`: only its own marked block.
- `~/.codex/config.toml`: only the `[mcp_servers.*]` sections and keys it wrote itself. It records what it wrote in `~/.claude/.loadout/codex-config.json` and never changes a section or key you edited or wrote yourself.
- Plugins and marketplaces through `codex plugin` commands.

The first change to an existing `AGENTS.md` or `config.toml` saves a copy in the backup; `loadout restore` brings it back and removes the plugins loadout installed. Turn it off with `loadout configure set target codex off`; what was set up stays until you remove it.
````

- [ ] **Step 2: ADR** `docs/adr/0022-codex-as-a-second-target.md`:

```markdown
# 0022. Codex as a second target

- Status: Accepted
- Date: 2026-10-12
- Source: [Codex target design](../superpowers/specs/2026-10-12-codex-target-design.md)

## Context
The user works with Claude Code and the Codex CLI on the same machine and wants Codex to work exactly as well with the kit. Codex reads Claude Code marketplaces and Agent Skills, and its hooks use the same JSON shape, but it has no rules folder, no `@include`, no LSP support and no `${VAR}` in its config, and its own writes drop comments in `config.toml`.

## Decision
`cli/loadout/codex.py` maps the same kit and personal layer to Codex: the rules as a marked block in `~/.codex/AGENTS.md`; every plugin enabled for Claude Code through the same marketplace source; personal MCP servers and Serena's Codex context as `config.toml` tables that loadout owns by recording their exact text (not by marker comments); personal skills linked into `~/.agents/skills`. The plugin's `.codex-plugin/plugin.json` points Codex to its own hooks file with Codex arguments and a type-check hook that replaces Claude Code's LSP plugins. One source: changes made directly in one agent are reported as drift, not copied.

## Alternatives considered
- Each tool's own Codex installer: no single source, no daily sync, nothing to undo.
- Codex's built-in importer of Claude Code settings: a one-time copy without sync.
- Two-way automatic sync between the agents: conflicts, removals and secrets would cross between the agents unchecked.

## Consequences
- Codex runs plugin hooks only after the user approves them in `/hooks`; commit attribution stays an account setting.
- `config.toml` sections the user edits stop being managed by loadout.
- Project profiles and adopt for Codex follow in a second step.
```

- [ ] **Step 3: The other pages** (edit each; keep one home per fact, link to the how-to):
- `docs/explanation/architecture.md`: replace the section "Other agents (planned)" with a section "Codex" of three sentences: loadout can also set up the Codex CLI from the same kit and personal layer (`cli/loadout/codex.py`); what is shared and what is mapped is in [Use loadout with Codex](../how-to/codex.md); the decision is [0022](../adr/0022-codex-as-a-second-target.md). Keep the sentence that other agents (Gemini CLI, Cursor) are not supported, and the heading anchor `#other-agents-planned` if the README links it (else update the README link).
- `docs/reference/cli.md`: under `loadout configure`, add `set target codex on|off`; under `loadout bootstrap`, the Codex step and its question; under `loadout check`, the Codex group (names `Codex`, `Codex plugin`, `Codex instructions`, `Codex config`, `Codex plugins`, `Codex drift`).
- `docs/reference/personal-layer.md`: `targets.json` in the file table; `codex-config.json` in the machine-local table.
- `docs/reference/hooks.md`: a section "In Codex" listing `hooks/codex.json`, the differences and the type check.
- `docs/explanation/security-and-trust.md`: in "What loadout touches", the three Codex items from the how-to; in "What runs when you ask", the `codex plugin` and `codex plugin marketplace add` commands.
- `README.md`: in "What you get", one bullet: `**Codex too.** Turn on Codex and it gets the same rules, tools and preferences, kept current the same way ([Use loadout with Codex](docs/how-to/codex.md)).` In the Docs table, a row `Use loadout with Codex | [Use loadout with Codex](docs/how-to/codex.md)`. Replace the "Other agents (Codex, Gemini CLI, Cursor) are not supported yet" sentence with "Gemini CLI and Cursor are not supported yet; the plan is in [Architecture](docs/explanation/architecture.md#codex)." (anchor as it exists after the edit).
- `docs/README.md`: the how-to in the How-to list.
- `docs/adr/README.md`: the 0022 row. `AGENTS.md`: `codex.py` in the module map ("Codex target"), ADR range 0001-0022.
- `CONTRIBUTING.md`: one sentence under Tests: `dev/codex-sandbox.sh` runs the Codex part against the real codex CLI in a temporary home (needs codex and network).
- The spec: replace its "Catalog" section with the first ruling of this plan, and add the other two rulings.

- [ ] **Step 4: Run the link check and the full suite**

Run: `uv run --python 3.12 --with pytest pytest -q`
Expected: all pass (`test_relative_links_resolve` covers every new link and anchor).

- [ ] **Step 5: Commit**

```bash
git add docs README.md AGENTS.md CONTRIBUTING.md
git commit -m "docs(codex): how-to, ADR 0022, references and the README"
```

---

## After the tasks

- `/loadout:docs-sync` over the branch.
- One whole-branch review on the most capable model, with this plan's Review Focus.
- With the user's OK: push, PR; after merge, the user enables Codex on the real machine (`loadout configure set target codex on`, then `loadout bootstrap`) and approves the hooks in `/hooks`.
- Then PR 2 (projects and adopt) gets its own plan from the same spec.
