# Agent Choice in Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bootstrap asks which coding agents to set up (Claude Code, Codex, both), installs and configures exactly those, and leaves every existing machine as it is.

**Architecture:** A small `cli/loadout/targets.py` reads and writes `<personal>/targets.json` (`claude`, `codex`). `catalog.binaries()` drops binaries whose `target` agent is off, so bootstrap, check, update and the inventory follow the choice in one place. Bootstrap decides the agents before Prerequisites (flag, existing personal layer, or the question), writes them after the personal-layer step, and skips the Claude-only steps when Claude Code is off; check and maintenance skip their Claude groups likewise.

**Tech Stack:** Python 3.10+ standard library, pytest with `fake_home`/`fake_runner`.

**Spec:** `docs/superpowers/specs/2026-10-12-agent-choice-design.md`

## Global Constraints

- `targets.json`: `{"claude": bool, "codex": bool}`; a missing `claude` key means `true`; at least one agent on.
- Question text: `Which coding agents should loadout set up?  1) Claude Code  2) Codex  3) both  [N]` with default 1, or 3 when `codex` is on PATH; asked only when the personal layer has neither key and the run is interactive and `--agents` was not given.
- Flag: `loadout bootstrap --agents claude|codex|claude,codex` (order and spaces ignored; anything else is a usage error).
- Catalog: new binary `codex` (`mise use -g codex`, needs mise, `version.cmd` `["codex","--version"]`, `version.npm` `@openai/codex`, `required: true`, `target: "codex"`); `claude` gets `target: "claude"`.
- Turning a target off uninstalls nothing.
- Tests never touch the real home; no real installers. Conventional Commits, no AI attribution; author Jonas Weirauch.

## Review Focus

1. **An existing machine (no `claude` key)** must behave byte-identically: bootstrap asks nothing new when `codex` is absent and the layer is decided by default. Pinned by `test_existing_machine_is_not_asked_and_keeps_claude` (Task 3).
2. **A cloned personal layer that chose differently than the question** must win and still get its agent installed. Pinned by `test_cloned_choice_wins_and_installs_what_is_missing` (Task 3).
3. **Codex only** must make no `claude` call and create nothing under `~/.claude` except loadout's state folder. Pinned by `test_codex_only_bootstrap_never_touches_claude` (Task 3).
4. **`loadout check` with Claude Code off** must not fail on a missing `claude` binary or its links. Pinned by `test_check_without_claude_has_no_claude_groups` (Task 4).
5. **Turning off the last agent** is refused. Pinned by `test_last_agent_cannot_be_turned_off` (Task 1).

---

### Task 1: `targets.py` and `configure set target claude`

**Files:**
- Create: `cli/loadout/targets.py`
- Modify: `cli/loadout/codex.py` (`targets_path`, `enabled`, `decided`, `set_enabled` delegate to `targets`), `cli/loadout/commands.py` (`set target claude|codex`), `cli/loadout/configure.py` (`show`)
- Test: `tests/test_targets.py`

**Interfaces:**
- Produces: `targets.path() -> Path`, `targets.claude_enabled() -> bool`, `targets.codex_enabled() -> bool`, `targets.decided() -> bool` (either key present), `targets.set_target(name: str, on: bool) -> str` (raises `ValueError` when it would turn the last agent off), `targets.parse_agents(text: str) -> dict[str, bool]` (raises `ValueError`), `targets.set_agents(choice: dict[str, bool]) -> None`.

- [ ] **Step 1: Write the failing tests** — `tests/test_targets.py`:

```python
"""Which coding agents loadout sets up: <personal>/targets.json."""
import json

import pytest

from loadout import codex, targets
from loadout.__main__ import main


def test_existing_layers_keep_claude_and_have_no_codex(fake_home):
    assert targets.claude_enabled() and not targets.codex_enabled() and not targets.decided()


def test_set_and_read_both_agents(fake_home):
    targets.set_agents({"claude": False, "codex": True})
    assert json.loads(targets.path().read_text()) == {"claude": False, "codex": True}
    assert not targets.claude_enabled() and targets.codex_enabled() and codex.enabled() and targets.decided()


def test_last_agent_cannot_be_turned_off(fake_home):
    targets.set_agents({"claude": True, "codex": False})
    with pytest.raises(ValueError, match="at least one"):
        targets.set_target("claude", False)
    targets.set_target("codex", True)
    assert targets.set_target("claude", False) == "claude: off"


@pytest.mark.parametrize("text,expected", [("claude", {"claude": True, "codex": False}),
                                           ("codex", {"claude": False, "codex": True}),
                                           ("codex, claude", {"claude": True, "codex": True})])
def test_parse_agents(text, expected):
    assert targets.parse_agents(text) == expected


@pytest.mark.parametrize("text", ["", "cursor", "claude,,codex x"])
def test_parse_agents_refuses_unknown(text):
    with pytest.raises(ValueError):
        targets.parse_agents(text)


def test_configure_set_target_claude_off_needs_codex(fake_home, fake_runner, monkeypatch, capsys):
    from loadout import configure
    monkeypatch.setattr(configure, "apply_all", lambda ask: None)
    monkeypatch.setattr(configure, "offer_commit", lambda ask: None)
    assert main(["configure", "set", "target", "claude", "off"]) == 1
    assert "at least one" in capsys.readouterr().err
```

- [ ] **Step 2: Run them to verify they fail** — Run: `uv run --python 3.12 --with pytest pytest -q tests/test_targets.py` — Expected: ImportError (`targets`).

- [ ] **Step 3: Implement** — `cli/loadout/targets.py`:

```python
"""Which coding agents loadout sets up, stored in the personal layer so it follows the user (docs/how-to/codex.md)."""
from __future__ import annotations

from pathlib import Path

from . import paths
from .jsonio import load_json, save_json

AGENTS = ("claude", "codex")


def path() -> Path:
    return paths.personal_root() / "targets.json"


def claude_enabled() -> bool:
    return load_json(path()).get("claude", True) is not False  # missing: every machine from before the choice


def codex_enabled() -> bool:
    return load_json(path()).get("codex") is True


def decided() -> bool:
    data = load_json(path())
    return "claude" in data or "codex" in data


def set_agents(choice: dict) -> None:
    if not any(choice.get(a) for a in AGENTS):
        raise ValueError("choose at least one coding agent (claude, codex)")
    data = load_json(path())
    data.update({a: bool(choice.get(a)) for a in AGENTS})
    path().parent.mkdir(parents=True, exist_ok=True)
    save_json(path(), data)


def set_target(name: str, on: bool) -> str:
    if name not in AGENTS:
        raise ValueError(f"unknown agent {name}; use claude or codex")
    choice = {"claude": claude_enabled(), "codex": codex_enabled(), name: on}
    if not any(choice.values()):
        raise ValueError("at least one coding agent must stay on; turn the other one on first")
    set_agents(choice)
    return f"{name}: {'on' if on else 'off'}"


def parse_agents(text: str) -> dict:
    names = [part.strip() for part in text.split(",")]
    if not names or any(n not in AGENTS for n in names):
        raise ValueError(f"--agents takes claude, codex or claude,codex (got '{text}')")
    return {a: a in names for a in AGENTS}
```

In `cli/loadout/codex.py`, replace `targets_path`, `enabled`, `decided`, `set_enabled` with:

```python
def targets_path() -> Path:
    from . import targets
    return targets.path()


def enabled() -> bool:
    from . import targets
    return targets.codex_enabled()


def decided() -> bool:
    from . import targets
    return "codex" in load_json(targets.path())


def set_enabled(on: bool) -> str:
    from . import targets
    return targets.set_target("codex", on)
```

In `cli/loadout/commands.py`, the `target` branch: accept `claude` and `codex`; call `targets.set_target(a.name, on)` (a `ValueError` reaches `main`'s handler: exit 1 with the message on stderr); keep the Codex setup that runs when `codex` is switched on; for `claude` on, run `configure.apply_all(_ask)` (Claude Code's setup); for any switch, `configure.offer_commit(_ask)`. Usage text: `loadout configure set target claude|codex on|off`. In `configure.show()`, replace the Codex line with `Agents: Claude Code on|off, Codex on|off (set with: loadout configure set target claude|codex on|off)`; update `test_configure_show_names_the_codex_switch` to the new text (ledger it).

- [ ] **Step 4: Run** — Run: `uv run --python 3.12 --with pytest pytest -q tests/test_targets.py tests/test_codex_*.py` — Expected: all pass.

- [ ] **Step 5: Commit** — `git commit -m "feat(targets): choose the coding agents in targets.json; configure set target claude|codex"`

---

### Task 2: The `codex` binary and agent-specific binaries

**Files:**
- Modify: `catalog.json` (new `codex` binary entry; `"target": "claude"` on `claude`), `cli/loadout/catalog.py` (`binaries()` filters by target), `tests/test_repo_static.py` (`target` only on binaries, value `claude` or `codex`)
- Test: `tests/test_targets.py` (append)

**Interfaces:**
- Consumes: `targets.claude_enabled()`, `targets.codex_enabled()` (Task 1).
- Produces: `catalog.binaries()` returns only entries whose `target` agent is on (entries without `target` always).

- [ ] **Step 1: Failing tests** — append to `tests/test_targets.py`:

```python
def test_binaries_follow_the_chosen_agents(fake_home):
    from loadout import catalog
    ids = lambda: {e["id"] for e in catalog.binaries()}  # noqa: E731
    assert "claude" in ids() and "codex" not in ids()
    targets.set_agents({"claude": False, "codex": True})
    assert "claude" not in ids() and "codex" in ids()
    targets.set_agents({"claude": True, "codex": True})
    assert {"claude", "codex"} <= ids()


def test_codex_installs_through_mise():
    from loadout import catalog
    entry = catalog.by_id("codex")
    assert entry["install"]["posix"] == [["mise", "use", "-g", "codex"]] and entry["needs"] == ["mise"]
    assert entry["target"] == "codex" and entry["required"] is True
```

and in `tests/test_repo_static.py`:

```python
def test_target_field_only_on_binaries():
    for entry in _json("catalog.json")["entries"]:
        if "target" in entry:
            assert entry["kind"] == "binary" and entry["target"] in ("claude", "codex"), entry["id"]
```

- [ ] **Step 2: Run to fail** — Expected: `catalog.by_id("codex")` is None / `codex` never listed.

- [ ] **Step 3: Implement** — the catalog entry (place it after `claude`):

```json
{
  "id": "codex",
  "kind": "binary",
  "status": "core",
  "required": true,
  "target": "codex",
  "match": {"names": ["codex"]},
  "reason": "OpenAI's Codex CLI, set up by loadout like Claude Code when you choose it (docs/how-to/codex.md).",
  "short": "OpenAI's Codex CLI (when chosen)",
  "needs": ["mise"],
  "version": {"cmd": ["codex", "--version"], "npm": "@openai/codex"},
  "install": {"posix": [["mise", "use", "-g", "codex"]], "windows": [["mise", "use", "-g", "codex"]]},
  "update": {"posix": [["mise", "use", "-g", "codex@latest"]], "windows": [["mise", "use", "-g", "codex@latest"]]},
  "mise": "codex"
}
```

Add `"target": "claude"` to the `claude` entry. In `catalog.py`:

```python
def binaries() -> list[dict]:
    """Binary entries; one tied to a coding agent (target) only while that agent is chosen (targets.json)."""
    from . import targets
    on = {"claude": targets.claude_enabled(), "codex": targets.codex_enabled()}
    return [e for e in load() if e["kind"] == "binary" and on.get(e.get("target"), True)]
```

Check `docs/reference/catalog-format.md` field table: add `target` ("For a `binary`: `claude` or `codex`; the binary is installed, checked and updated only while that agent is chosen.").

- [ ] **Step 4: Run** — Run: `uv run --python 3.12 --with pytest pytest -q` — Expected: all pass (existing tests run with `claude` on and `codex` off, as before).

- [ ] **Step 5: Commit** — `git commit -m "feat(catalog): the codex binary; agent-specific binaries follow the chosen agents"`

---

### Task 3: Bootstrap: the question, `--agents`, Claude-only steps skipped

**Files:**
- Modify: `cli/loadout/bootstrap.py` (`bootstrap(..., agents: str | None = None)`, `choose_agents`, step gating, `still_to_do`, final "Next" line), `cli/loadout/commands.py` (`--agents`)
- Test: `tests/test_agent_choice_bootstrap.py`

**Interfaces:**
- Consumes: `targets.*` (Task 1), `catalog.binaries()` (Task 2), `codex.apply_all`, `codex.open_steps` (PR 1).
- Produces: `bootstrap.choose_agents(ask, interactive: bool, flag: str | None) -> dict[str, bool]`, `bootstrap.AGENT_QUESTION`.

- [ ] **Step 1: Failing tests** — `tests/test_agent_choice_bootstrap.py`:

```python
"""Bootstrap asks which coding agents to set up and sets up exactly those."""
import json

import pytest

from loadout import bootstrap, codex, out, paths, runner, targets


def _run(**kw):
    args = dict(install=False, yes=True, plugins=True, adopt_step=True, ask=lambda q: "", interactive=False)
    args.update(kw)
    return bootstrap.bootstrap(**args)


def test_question_defaults(fake_home, fake_runner):
    fake_runner.missing.add("codex")
    assert bootstrap.choose_agents(lambda q: "", True, None) == {"claude": True, "codex": False}
    fake_runner.missing.discard("codex")
    assert bootstrap.choose_agents(lambda q: "", True, None) == {"claude": True, "codex": True}
    assert bootstrap.choose_agents(lambda q: "2", True, None) == {"claude": False, "codex": True}


def test_no_terminal_keeps_claude_and_flag_wins(fake_home, fake_runner):
    assert bootstrap.choose_agents(lambda q: "3", False, None) == {"claude": True, "codex": False}
    assert bootstrap.choose_agents(lambda q: "1", True, "codex") == {"claude": False, "codex": True}


def test_existing_machine_is_not_asked_and_keeps_claude(fake_home, fake_runner):
    (fake_home / ".config/loadout/personal").mkdir(parents=True)
    fake_runner.missing.add("codex")
    asked = []
    assert bootstrap.choose_agents(lambda q: asked.append(q) or "2", True, None) == {"claude": True, "codex": False}
    assert asked == []


def test_existing_machine_with_codex_is_asked(fake_home, fake_runner):
    (fake_home / ".config/loadout/personal").mkdir(parents=True)
    assert bootstrap.choose_agents(lambda q: "", True, None) == {"claude": True, "codex": True}


def test_codex_only_bootstrap_never_touches_claude(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(codex, "unavailable", lambda: None)
    monkeypatch.setattr(codex, "apply_all", lambda bk, refresh=False, **kw: ["instructions written"])
    monkeypatch.setattr(codex, "open_steps", lambda: [])
    _run(agents="codex")
    assert not any(c[0] == "claude" for c in fake_runner.calls)
    created = {p.relative_to(paths.claude_home()).parts[0] for p in paths.claude_home().rglob("*")} if paths.claude_home().exists() else set()
    assert created <= {".loadout", "backups"}, created
    assert json.loads(targets.path().read_text()) == {"claude": False, "codex": True}


def test_cloned_choice_wins_and_installs_what_is_missing(fake_home, fake_runner, monkeypatch):
    def cloned_layer(ask, bk, interactive):
        root = paths.personal_root()
        root.mkdir(parents=True)
        (root / "targets.json").write_text(json.dumps({"claude": True, "codex": True}))
        return "cloned", True
    monkeypatch.setattr(bootstrap, "ensure_personal", cloned_layer)
    calls = []
    monkeypatch.setattr(bootstrap, "check_prereqs", lambda install, ask, installed=None, notes=None: calls.append(
        {e["id"] for e in __import__("loadout").catalog.binaries()}) or [])
    monkeypatch.setattr(codex, "unavailable", lambda: None)
    monkeypatch.setattr(codex, "apply_all", lambda bk, refresh=False, **kw: [])
    monkeypatch.setattr(codex, "open_steps", lambda: [])
    _run(agents="claude", install=True)
    assert targets.codex_enabled(), "the cloned layer's choice wins"
    assert len(calls) == 2 and "codex" in calls[1], "prerequisites run again for the newly chosen agent"


def test_next_line_names_the_chosen_agent(fake_home, fake_runner, monkeypatch, capsys):
    monkeypatch.setattr(out, "VERBOSE", False)
    monkeypatch.setattr(codex, "unavailable", lambda: None)
    monkeypatch.setattr(codex, "apply_all", lambda bk, refresh=False, **kw: [])
    monkeypatch.setattr(codex, "open_steps", lambda: [])
    _run(agents="codex")
    assert "run `codex`" in capsys.readouterr().out
```

- [ ] **Step 2: Run to fail** — Expected: `TypeError: bootstrap() got an unexpected keyword argument 'agents'` / missing `choose_agents`.

- [ ] **Step 3: Implement** — in `bootstrap.py`:

```python
AGENT_QUESTION = "Which coding agents should loadout set up?  1) Claude Code  2) Codex  3) both  [{default}] "
_ANSWERS = {"1": {"claude": True, "codex": False}, "2": {"claude": False, "codex": True},
            "3": {"claude": True, "codex": True}}


def choose_agents(ask, interactive: bool, flag) -> dict:
    """--agents first, then a decided personal layer, then the question (interactive), else Claude Code as before."""
    from . import targets
    if flag:
        return targets.parse_agents(flag)
    if targets.decided():
        return {"claude": targets.claude_enabled(), "codex": targets.codex_enabled()}
    existing = paths.personal_root().exists()
    if not interactive or (existing and not runner.have("codex")):
        return {"claude": True, "codex": False}  # as before this change: no new question without Codex
    default = "3" if runner.have("codex") else "1"
    while True:
        answer = ask("\n" + AGENT_QUESTION.format(default=default)).strip() or default
        if answer in _ANSWERS:
            return dict(_ANSWERS[answer])
        print("answer 1, 2 or 3")
```

`bootstrap(install, yes, plugins, adopt_step, ask, interactive=None, agents=None)`:
1. Before `_step("Prerequisites")`: `chosen = choose_agents(ask, interactive and not yes, agents)` and, before checking prerequisites, apply it in memory so `catalog.binaries()` sees it: write it with `targets.set_agents(chosen)` only when the personal root already exists; otherwise keep it and pass it through an override (add `targets.OVERRIDE: dict | None = None` read first by `claude_enabled`/`codex_enabled`; set it here, clear it in a `finally`).
2. After the personal-layer step: if `targets.decided()` (a cloned layer chose), compare with `chosen`; if it differs, take the layer's choice, set the override to it, and call `check_prereqs(install, ask, installed=installed, notes=notes)` once more. Else `targets.set_agents(chosen)`.
3. Claude-only steps run only when `targets.claude_enabled()`: Links' `link.link_all` (keep `link.link_bin`, the launcher), the Settings step, "Marketplaces and plugins", "Adopt existing setup". The configure prompt stays (preferences reach Codex through `me.md`).
4. The Codex step runs when `targets.codex_enabled()`; the old one-time "Codex found" question is removed (the agent question replaces it).
5. `still_to_do`: the Claude login line only when Claude Code is on; final line: `Next: run \`claude\`` / `\`codex\`` / `\`claude\` or \`codex\`` depending on the agents.

In `commands.py`, `bootstrap` parser: `p.add_argument("--agents", help="claude, codex or claude,codex (default: ask, or Claude Code without a terminal)")` and pass `agents=a.agents`.

Remove or update the PR-1 test `test_bootstrap_asks_once_when_codex_is_found` (the agent question replaces it): replace it by `test_question_defaults` above (ledger it).

- [ ] **Step 4: Run** — Run: `uv run --python 3.12 --with pytest pytest -q` — Expected: all pass. Calm-output tests unchanged for Claude-only runs.

- [ ] **Step 5: Commit** — `git commit -m "feat(bootstrap): ask which coding agents to set up; --agents; Codex only skips Claude Code"`

---

### Task 4: Check and the daily sync follow the agents

**Files:**
- Modify: `cli/loadout/check.py` (skip Claude groups), `cli/loadout/maintenance.py` (skip Claude parts)
- Test: `tests/test_targets.py` (append)

- [ ] **Step 1: Failing tests** — append:

```python
def test_check_without_claude_has_no_claude_groups(fake_home, fake_runner, monkeypatch):
    from loadout import check
    targets.set_agents({"claude": False, "codex": True})
    monkeypatch.setattr(codex, "checks", lambda: [])
    fake_runner.missing.add("claude")
    names = [r.name for r in check.run_checks()]
    assert not any(n.startswith(("link ", "settings", "plugin", "duplicate", "own")) for n in names), names
    assert not any(n == "claude" for n in names)


def test_sync_without_claude_skips_claude_parts(fake_home, fake_runner, monkeypatch):
    from loadout import link, maintenance, personal_mcp, settings_merge
    targets.set_agents({"claude": False, "codex": True})
    called = []
    monkeypatch.setattr(settings_merge, "apply_settings", lambda: called.append("settings") or (None, None))
    monkeypatch.setattr(personal_mcp, "apply_mcp", lambda: called.append("mcp") or [])
    monkeypatch.setattr(link, "link_all", lambda bk, retry_symlinks=False: called.append("links") or [])
    monkeypatch.setattr(maintenance, "pull_if_clean", lambda root: True)
    monkeypatch.setattr(maintenance, "find_outdated", lambda: [])
    monkeypatch.setattr(codex, "unavailable", lambda: None)
    monkeypatch.setattr(codex, "apply_all", lambda bk, refresh=False, **kw: called.append("codex") or [])
    monkeypatch.setattr(codex, "drift", lambda: [])
    (__import__("loadout").paths.personal_root() / ".git").mkdir(parents=True)
    maintenance._maintain(0)
    assert called == ["codex"]
```

(`drift()` compares with Claude Code; with Claude Code off it returns `[]`: add that guard in Step 3 and a one-line test `assert codex.drift() == []` with Claude off.)

- [ ] **Step 2: Run to fail.**

- [ ] **Step 3: Implement** — `check.run_checks()`:

Keep today's order for Claude-on runs:

```python
def run_checks() -> list[CheckResult]:
    from . import targets
    on = targets.claude_enabled()
    return [*_python(), *_wsl(),
            *(_links() if on else []), *_skills_json(), *(_settings() if on else []), *(_plugins() if on else []),
            *_codex(), *(_connectors() if on else []), *(_own() if on else []),
            *_binaries(), *(_mcp_path() if on else []), *_gh(), *_secrets(), *_repos()]
```

`maintenance._maintain`: wrap the settings/MCP block and the links block in `if targets.claude_enabled():`. `codex.drift()`: `if not targets.claude_enabled(): return []` at the top.

- [ ] **Step 4: Run** — full suite; Expected: all pass.

- [ ] **Step 5: Commit** — `git commit -m "feat: loadout check and the daily sync follow the chosen agents"`

---

### Task 5: Docs

**Files:** `docs/tutorials/getting-started.md` ("What bootstrap asks": the agent question first; `--agents`), `docs/how-to/codex.md` ("Codex only", adding Claude Code later with `loadout configure set target claude on`), `docs/reference/cli.md` (`--agents`, `set target claude|codex`), `docs/reference/personal-layer.md` (`targets.json` keys), `docs/reference/catalog-format.md` (`target`), `README.md` (under Install: "Bootstrap first asks which coding agents to set up: Claude Code, Codex or both.").

- [ ] **Step 1:** Edit each page as listed, one home per fact (the how-to owns the agent explanation; others link to it).
- [ ] **Step 2:** Run: `uv run --python 3.12 --with pytest pytest -q tests/test_repo_static.py tests/test_readme.py` — Expected: pass.
- [ ] **Step 3: Commit** — `git commit -m "docs: choosing the coding agents in bootstrap"`

## After the tasks

docs-sync; one whole-branch review; PR with the user's OK; after merge, a fresh-machine check of "Codex only" in the sandbox (`dev/codex-sandbox.sh`-style, temporary HOME) if the network allows.
