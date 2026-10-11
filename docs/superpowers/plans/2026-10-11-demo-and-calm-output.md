# Calm CLI Output and README Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `bootstrap`, `adopt` and `check` print one calm status line per step (details only on problems or with `--verbose`), and the README GIF tells a newcomer the whole story: an existing setup, the one-liner, the result, then real Claude Code.

**Architecture:** A new `cli/loadout/out.py` holds the verbose switch and the status/detail/problem printers. Verbose mode keeps today's exact output (so the existing tests keep covering every detail line, via an autouse fixture). Calm mode is new code with its own tests. The demo gets offline stubs for `curl` and `uv`, a shared style tape, title cards, and an ffmpeg join with a real Claude Code clip the maintainer records.

**Tech Stack:** Python 3.10+ standard library; pytest; VHS v0.12.1 in podman; ffmpeg (inside the VHS image); bash.

**Spec:** `docs/superpowers/specs/2026-10-11-demo-and-calm-output-design.md`

## Global Constraints

- Python 3.10+, standard library only in `cli/loadout/`.
- Tests use `fake_home` / `fake_runner`; never touch the real `~/.claude`, `~/.claude.json` or `~/.config/loadout`.
- Agents never run real installers, mutating `claude` commands, or real `claude` at all (the clip is recorded by the maintainer).
- Conventional Commits; no `Co-Authored-By` or other AI attribution.
- Calm output degrades to plain text: no colour when stdout is not a terminal, `NO_COLOR` is set or `TERM=dumb`; symbols fall back to ASCII when stdout cannot encode them.
- `loadout check` failures keep the exact `[FAIL] name: detail` format (CI greps `[FAIL]`); exit codes never change.
- `adopt --apply` keeps the final `Apply N change(s)? [y/N]` confirmation (ADR 0012).
- The demo renders with `--network=none`; stubs refuse to run without `~/.loadout-demo`.
- Short catalog reasons: one line, at most 60 characters, no trailing period.
- Demo look: JetBrains Mono 16, LineHeight 1.3, 1200×800, WindowBar Rings, BorderRadius 10, Margin 36, Padding 28, custom theme with violet accent `#a78bfa`; GIF under 5 MB (lower the framerate before speeding up).

## Review Focus

1. Calm mode hides a real problem (a failed install, a failed plugin, a manual-commands file) → every failure must still print in full. Tests: Task 4 `test_calm_apply_prints_details_when_something_failed`, Task 5 `test_calm_bootstrap_shows_failed_plugin_line`.
2. Piped / non-terminal output (CI logs, `| less`) gets ANSI codes or undecodable symbols → plain text. Tests: Task 1 `test_plain_when_not_a_terminal`, `test_ascii_symbols_when_stdout_cannot_encode`.
3. `adopt --apply --yes` (no questions) in calm mode prints nothing before acting → it must still show the plan. Test: Task 4 `test_calm_yes_still_prints_the_plan`.
4. A skipped binary update in calm mode reported as done → it is a NotDone and shows the details. Test: Task 4 `test_binary_skip_is_not_done`.
5. The demo tape drifts from the README one-liner → the test compares them. Test: Task 7 `test_tape_types_the_readme_one_liner`.

---

### Task 1: The `out` module

**Files:**
- Create: `cli/loadout/out.py`
- Modify: `tests/conftest.py` (autouse fixture)
- Test: `tests/test_out.py`

**Interfaces:**
- Produces: `out.VERBOSE: bool` (default False), `out.sym(name) -> str` (names: ok, warn, fail, bullet, arrow), `out.paint(text, kind) -> str` (kinds: ok, warn, fail, accent, muted), `out.status(name, summary, level="ok") -> None`, `out.detail(line) -> None`, `out.problem(line) -> None`, `out.WIDTH = 18`.

- [ ] **Step 1: Write the failing tests** (`tests/test_out.py`)

```python
import io
import sys

from loadout import out


class Stream(io.StringIO):
    def __init__(self, tty=False, encoding="utf-8"):
        super().__init__()
        self._tty, self._enc = tty, encoding

    def isatty(self):
        return self._tty

    @property
    def encoding(self):
        return self._enc


def test_plain_when_not_a_terminal(monkeypatch):
    monkeypatch.setattr(sys, "stdout", Stream(tty=False))
    out.status("Plugins", "14 kit plugins ready")
    assert sys.stdout.getvalue() == "✓ Plugins            14 kit plugins ready\n"


def test_colour_on_a_terminal_unless_no_color(monkeypatch):
    monkeypatch.setattr(sys, "stdout", Stream(tty=True))
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    assert out.paint("x", "ok") == "\033[32mx\033[0m"
    monkeypatch.setenv("NO_COLOR", "1")
    assert out.paint("x", "ok") == "x"


def test_ascii_symbols_when_stdout_cannot_encode(monkeypatch):
    monkeypatch.setattr(sys, "stdout", Stream(encoding="cp1252"))
    assert (out.sym("ok"), out.sym("bullet"), out.sym("arrow")) == ("ok", "-", "->")


def test_detail_only_when_verbose(monkeypatch, capsys):
    monkeypatch.setattr(out, "VERBOSE", False)
    out.detail("linked x")
    out.problem("plugin y: failed")
    assert capsys.readouterr().out == "  plugin y: failed\n"
    monkeypatch.setattr(out, "VERBOSE", True)
    out.detail("linked x")
    assert capsys.readouterr().out == "  linked x\n"
```

- [ ] **Step 2: Run them, expect FAIL** — `uv run --python 3.12 --with pytest pytest -q tests/test_out.py` → `ImportError: cannot import name 'out'`.

- [ ] **Step 3: Implement** `cli/loadout/out.py`

```python
"""Calm terminal output: one status line per step; details only with --verbose, problems always."""
from __future__ import annotations

import os
import sys

VERBOSE = False
WIDTH = 18
_FANCY = {"ok": "✓", "warn": "!", "fail": "✗", "bullet": "•", "arrow": "→"}
_PLAIN = {"ok": "ok", "warn": "!", "fail": "x", "bullet": "-", "arrow": "->"}
_COLOR = {"ok": "32", "warn": "33", "fail": "31", "accent": "35", "muted": "2"}


def sym(name: str) -> str:
    """The symbol, or its ASCII stand-in when stdout cannot encode it (e.g. a cp1252 console)."""
    try:
        "".join(_FANCY.values()).encode(getattr(sys.stdout, "encoding", None) or "ascii")
        return _FANCY[name]
    except (UnicodeEncodeError, LookupError):
        return _PLAIN[name]


def paint(text: str, kind: str) -> str:
    """ANSI colour only on a terminal, never with NO_COLOR (https://no-color.org) or TERM=dumb."""
    try:
        tty = sys.stdout.isatty()
    except (AttributeError, ValueError):
        tty = False
    if not tty or os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
        return text
    if os.name == "nt" and not (os.environ.get("WT_SESSION") or os.environ.get("TERM")):
        return text  # the legacy console shows escape codes literally
    return f"\033[{_COLOR[kind]}m{text}\033[0m"


def status(name: str, summary: str, level: str = "ok") -> None:
    print(f"{paint(sym(level), level)} {name.ljust(WIDTH)} {summary}".rstrip())


def detail(line: str) -> None:
    if VERBOSE:
        print(f"  {line}")


def problem(line: str) -> None:
    print(f"  {line}")
```

- [ ] **Step 4: Add the autouse fixture** at the end of `tests/conftest.py`

```python
@pytest.fixture(autouse=True)
def verbose_output(monkeypatch):
    """Existing tests assert today's detail lines (verbose mode); calm-mode tests set out.VERBOSE = False."""
    from loadout import out
    monkeypatch.setattr(out, "VERBOSE", True)
```

`test_plain_when_not_a_terminal` replaces stdout itself, so the fixture does not affect it.

- [ ] **Step 5: Run** `uv run --python 3.12 --with pytest pytest -q tests/test_out.py` → 4 passed; then the full suite → all pass (nothing uses `out` yet).

- [ ] **Step 6: Commit** — `git add cli/loadout/out.py tests/test_out.py tests/conftest.py && git commit -m "feat(cli): out module for calm status lines"`

---

### Task 2: `check` summary and `--verbose`

**Files:**
- Modify: `cli/loadout/check.py` (add `format_summary` after `format_results`)
- Modify: `cli/loadout/commands.py:63-73` (`_register_check`)
- Test: `tests/test_check.py`

**Interfaces:**
- Consumes: `out.VERBOSE`.
- Produces: `check.format_summary(results) -> tuple[str, int]` (Task 5 uses the same counting).

- [ ] **Step 1: Failing tests** (append to `tests/test_check.py`)

```python
from loadout.check import CheckResult, format_summary


def test_summary_counts_and_lists_only_problems():
    results = [CheckResult("a", True), CheckResult("b", False, "broken", "fix b"),
               CheckResult("c", False, "meh", "fix c", "warn")]
    text, code = format_summary(results)
    assert text.splitlines()[0] == "Health check: 1 of 3 OK"
    assert "[FAIL] b: broken" in text and "[warn] c: meh" in text and "[ok  ]" not in text
    assert code == 1


def test_summary_all_ok_is_one_line():
    text, code = format_summary([CheckResult("a", True), CheckResult("b", True)])
    assert (text, code) == ("Health check: 2 of 2 OK", 0)


def test_check_verbose_flag_prints_every_line(fake_home, fake_runner, monkeypatch, capsys):
    from loadout import __main__, check, out
    monkeypatch.setattr(out, "VERBOSE", False)
    monkeypatch.setattr(check, "run_checks", lambda: [CheckResult("a", True), CheckResult("b", True)])
    __main__.main(["check"])
    assert capsys.readouterr().out.strip() == "Health check: 2 of 2 OK"
    __main__.main(["check", "--verbose"])
    assert "[ok  ] a" in capsys.readouterr().out
```

Before writing the last test, read `cli/loadout/__main__.py` and use its real entry function (if it is not `main(argv)`, call it the way `tests/test_cli_help.py` does).

- [ ] **Step 2: Run, expect FAIL** — `ImportError: cannot import name 'format_summary'`.

- [ ] **Step 3: Implement.** In `check.py`, after `format_results`:

```python
def format_summary(results: list[CheckResult]) -> tuple[str, int]:
    """One count line, then only the warnings and failures (same lines as format_results)."""
    bad = [r for r in results if not r.ok]
    text, code = format_results(bad)
    head = f"Health check: {len(results) - len(bad)} of {len(results)} OK"
    return (f"{head}\n{text}" if bad else head), code
```

In `commands.py` `_register_check`:

```python
    from . import check, out, settings_merge

    p = sub.add_parser("check", help="verify this machine's loadout setup")
    p.add_argument("--verbose", action="store_true", help="list every check, not only the problems")

    def run_check(a):
        if a.verbose:
            out.VERBOSE = True
        text, code = (check.format_results if out.VERBOSE else check.format_summary)(check.run_checks())
        print(text)
        return code
```

- [ ] **Step 4: Run** `tests/test_check.py` → pass; full suite → pass.

- [ ] **Step 5: Commit** — `feat(check): one summary line plus only the problems; --verbose lists all`

---

### Task 3: Short reasons in the catalog

**Files:**
- Modify: `catalog.json` (add `short` to entries)
- Modify: `docs/reference/catalog-format.md` (document `short`)
- Test: `tests/test_repo_static.py`

**Interfaces:**
- Produces: optional entry field `short: str` (one line, ≤ 60 chars, no trailing period). Task 4 reads it with `catalog.by_id(v.entry_id).get("short")`.

- [ ] **Step 1: Failing test** (append to `tests/test_repo_static.py`; reuse how that file already loads the catalog)

```python
VERDICT_PREFIXES = ("mcp-", "plugin-", "marketplace-", "skill-", "skills-", "hook-")


def test_catalog_short_reasons():
    entries = json.loads((paths.kit_root() / "catalog.json").read_text(encoding="utf-8"))["entries"]
    for e in entries:
        if e["id"].startswith(VERDICT_PREFIXES):
            assert e.get("short"), f"{e['id']}: add a short reason"
        if "short" in e:
            s = e["short"]
            assert "\n" not in s and len(s) <= 60 and not s.endswith("."), e["id"]
```

(Add `import json` / `from loadout import paths` only if the file lacks them.)

- [ ] **Step 2: Run, expect FAIL** — `mcp-serena: add a short reason`.

- [ ] **Step 3: Add the field** with a one-off script (keeps `catalog.json` formatting: check `git diff` afterwards; if the file's indentation differs from `indent=2`, match it):

```python
import json, pathlib
SHORT = {
  "mcp-serena": "your copy would run twice",
  "mcp-codebase-memory": "your copy would run twice",
  "mcp-context7": "the kit's context7 plugin provides it",
  "mcp-github-reference": "the gh CLI does this with less context",
  "mcp-sequential-thinking": "current models think natively",
  "mcp-memory-reference": "Claude Code's built-in memory replaces it",
  "mcp-filesystem": "duplicates the built-in file tools",
  "mcp-puppeteer": "archived; playwright-cli replaces it",
  "mcp-playwright": "playwright-cli is cheaper in context",
  "mcp-sonarqube": "only for repos with a Sonar project",
  "mcp-dbhub": "only for repos with a database",
  "mcp-docker-gateway": "a broad tool catalog in every session",
  "plugin-superpowers": "process skills",
  "plugin-auto-memory": "duplicates Claude Code's built-in memory",
  "plugin-claude-mem": "ongoing cost; data may leave the machine",
  "plugin-cct-testing-suite": "a 2025 snapshot, never updated",
  "plugin-cct-documentation-generator": "an unversioned snapshot with generic agents",
  "plugin-code-review": "the built-in /code-review covers it",
  "plugin-sonarqube": "a 30 s startup hook in every session",
  "plugin-ars": "about 25 skills in every session",
  "plugin-wiley-scholar-gateway": "use this or the claude.ai connector, not both",
  "plugin-context7": "use this or the claude.ai connector, not both",
  "plugin-cybersecurity-skills": "817 skills, about 25k tokens per session",
  "marketplace-claude-code-templates": "only provided superseded plugins",
  "marketplace-severity1": "only provided auto-memory",
  "skills-taste": "about 22k tokens per use, no auto-update",
  "skills-omarchy": "provided by Omarchy",
  "skill-codebase-memory": "a useful how-to for graph queries",
  "hook-serena-remind": "fires on every tool call",
  "hook-serena": "loadout provides these hooks",
  "hook-rtk": "loadout provides the rtk hook",
  "hook-codebase-memory": "loadout provides these hooks",
  "hook-auto-memory": "belongs to the superseded auto-memory plugin",
  "hook-sonar-secrets": "60 s scans on every read; install per repo",
}
p = pathlib.Path("catalog.json")
data = json.loads(p.read_text(encoding="utf-8"))
for e in data["entries"]:
    if e["id"] in SHORT:
        e["short"] = SHORT[e["id"]]
p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
```

If the test still names an entry (an id this list missed), write a short for it in the same style.

- [ ] **Step 4: Document** in `docs/reference/catalog-format.md`, next to `reason`: "`short` (optional): the one-line reason shown by `loadout adopt` (at most 60 characters, no trailing period). `reason` stays the full explanation, shown with `--verbose`."

- [ ] **Step 5: Run** `tests/test_repo_static.py` → pass; full suite → pass.

- [ ] **Step 6: Commit** — `feat(catalog): short one-line reasons for adopt's calm view`

---

### Task 4: Calm `adopt`

**Files:**
- Modify: `cli/loadout/adopt.py` (new constants and `render_calm`, `calm_group`, `calm_secrets`, `calm_summary`; changes in `select`, `run`, `_apply_binary`)
- Modify: `cli/loadout/commands.py:36-55` (`--verbose`)
- Test: `tests/test_adopt_calm.py`

**Interfaces:**
- Consumes: `out.*` (Task 1), catalog `short` (Task 3).
- Produces: `adopt.render_calm(verdicts, findings, header_only=False) -> str`, `adopt.calm_group(group, members) -> str`, `adopt.calm_summary(chosen, acting) -> list[str]`, `select(..., calm=False)`.

- [ ] **Step 1: Failing tests** (`tests/test_adopt_calm.py`)

```python
import pytest

from loadout import adopt, inventory, out, runner
from loadout.inventory import Item, Verdict
from fixtures import author_machine


@pytest.fixture
def machine(fake_home, fake_runner, monkeypatch):
    author_machine(fake_home)
    monkeypatch.setattr(out, "VERBOSE", False)
    return fake_home


def _verdicts():
    return inventory.classify(inventory.collect(with_versions=False))


def test_render_calm_headings_short_reasons_and_keep_count(machine):
    v = _verdicts()
    text = adopt.render_calm(v, [])
    keep = sum(1 for x in v if x.action == "keep")
    assert f"other items are fine" in text and str(keep) in text.splitlines()[0]
    assert "Remove: superseded by something better" in text
    assert "REMOVE" not in text and "KEEP" not in text and "binaries:" not in text
    assert "the gh CLI does this with less context" in text  # short, not the long reason
    assert "Archived reference server" not in text


def test_calm_reason_falls_back_to_first_sentence():
    v = Verdict(Item("mcp", "x"), "remove", "First part. Second part.", "")
    assert "First part" in adopt.calm_group("remove", [v]) and "Second" not in adopt.calm_group("remove", [v])


def test_calm_apply_shows_each_group_before_its_question(machine, capsys):
    asked = []

    def ask(q):
        asked.append((q, capsys.readouterr().out))
        return "n"

    adopt.run(True, None, set(), False, ask, with_versions=False, interactive=True)
    question, shown_before = asked[0]
    assert "[a]ll / [n]one / [p]ick" in question
    assert "Remove: superseded by something better" in shown_before
    assert "Already provided by loadout" not in shown_before  # the next group comes with its own question


def test_calm_yes_still_prints_the_plan(machine, capsys):
    adopt.run(True, None, set(), True, lambda q: "", with_versions=False, interactive=False)
    text = capsys.readouterr().out
    assert "Remove: superseded by something better" in text
    assert "✓ Removed:" in text or "ok Removed:" in text
    assert "Undo any time: loadout restore --list" in text


def test_calm_apply_prints_details_when_something_failed(machine, fake_runner, capsys):
    fake_runner.responses[("claude", "mcp", "remove")] = runner.Result(1, "", "boom")
    adopt.run(True, {"remove"}, set(), True, lambda q: "", with_versions=False, interactive=False)
    text = capsys.readouterr().out
    assert "Some changes did not complete" in text and "failed: boom" in text


def test_binary_skip_is_not_done(machine, monkeypatch):
    entry = {"id": "rtk", "install": {"linux": [["echo", "x"]], "macos": [["echo", "x"]], "windows": [["echo", "x"]]}}
    v = Verdict(Item("binary", "rtk", extra={"entry": entry}), "install", "", "rtk")
    line = adopt._apply_binary(v, lambda q: "n", confirm_cmds=True)
    assert isinstance(line, adopt.NotDone)


def test_verbose_keeps_the_full_plan(machine, monkeypatch, capsys):
    monkeypatch.setattr(out, "VERBOSE", True)
    adopt.run(False, None, set(), False, lambda q: "", with_versions=False)
    assert "REMOVE (" in capsys.readouterr().out
```

Check `catalog.platform_cmds(entry, "install")` against the entry shape in `test_binary_skip_is_not_done`; if it reads a different key layout, build the entry the way `tests/test_pkgmgr.py` does.

- [ ] **Step 2: Run, expect FAIL** — `AttributeError: module 'loadout.adopt' has no attribute 'render_calm'`.

- [ ] **Step 3: Implement** in `adopt.py`. Add `out` to the `from . import ...` line. Constants after `RESTART_NOTE`:

```python
# calm view: plain-language heading, the question asked under it, and the summary verb after applying
CALM = {
    "remove": ("Remove: superseded by something better", "Remove them?"),
    "migrate": ("Already provided by loadout", "Remove your copy?"),
    "scope-down": ("Only useful in some projects", "Disable globally?"),
    "update": ("Updates available", "Update? (each command is shown first)"),
    "install": ("Not installed yet", "Install? (each command is shown first)"),
    "review": ("Worth a look", "Remove?"),
    "own": ("Your own tools: loadout doesn't know these", ""),
}
DONE = {"remove": "Removed", "migrate": "Removed your copy", "scope-down": "Disabled globally",
        "update": "Updated", "install": "Installed", "review": "Removed"}
KIND_LABEL = {"mcp": "MCP", "plugin": "plugin", "marketplace": "marketplace", "skill": "skill", "hook": "hook"}
UNDO_LINE = "Undo any time: loadout restore --list"
```

Functions after `render_plan`:

```python
def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def _calm_name(v: Verdict) -> str:
    return f"{own.display_name(v.item)} {KIND_LABEL.get(v.item.kind, '')}".strip()


def _calm_reason(v: Verdict) -> str:
    entry = catalog.by_id(v.entry_id) if v.entry_id else None
    if entry and entry.get("short"):
        reason = entry["short"]
    elif v.action == "own":
        return ""
    else:
        reason = v.reason.split(". ")[0].rstrip(".")
    if v.action == "scope-down" and entry and entry.get("profile"):
        reason += f" (loadout profile {entry['profile']})"
    return reason


def calm_group(group: str, members: list[Verdict]) -> str:
    width = max(len(_calm_name(v)) for v in members)
    lines = [f"\n  {out.paint(CALM[group][0], 'accent')}"]
    for v in members:
        reason = _calm_reason(v)
        tail = f"  {out.sym('arrow')} {reason}" if reason else ""
        lines.append(redact(f"    {out.sym('bullet')} {_calm_name(v).ljust(width)}{tail}".rstrip()))
    return "\n".join(lines)


def calm_secrets(findings: list) -> str:
    lines = [f"\n  {out.paint('Plaintext secrets (values hidden)', 'accent')}"]
    for f in findings:
        how = "can move to secrets.env" if f.fixable else "move it to secrets.env by hand"
        lines.append(f"    {out.sym('bullet')} {f.server} MCP: {f.key} in {f.location}  {out.sym('arrow')} {how}")
    return "\n".join(lines)


def render_calm(verdicts: list[Verdict], findings: list, header_only: bool = False) -> str:
    acting = [v for v in verdicts if v.action != "keep"]
    fine = len(verdicts) - len(acting)
    head = (f"Your existing setup: {_plural(len(acting), 'suggestion')} ({fine} other items are fine)" if acting
            else f"Your existing setup: nothing to change ({fine} items are fine)")
    if header_only:
        return head
    lines = [head]
    for group in GROUP_ORDER[:-1]:
        members = [v for v in verdicts if v.action == group]
        if members:
            lines.append(calm_group(group, members))
    if findings:
        lines.append(calm_secrets(findings))
    return "\n".join(lines)


def calm_summary(chosen: list[Verdict], acting: list) -> list[str]:
    ok = out.paint(out.sym("ok"), "ok")
    lines = []
    for group in GROUP_ORDER:
        members = [v for v in chosen if v.action == group]
        if members and group in DONE:
            lines.append(f"{ok} {DONE[group]}: " + ", ".join(_calm_name(v) for v in members))
    where = {"global": "every machine", "remove": "removed"}
    if acting:
        lines.append(f"{ok} Your own tools: " + ", ".join(
            f"{_calm_name(v)} {out.sym('arrow')} {where.get(c.action, f'profile {c.profile}')}" for v, c in acting))
    return lines
```

In `select`, add the parameter `calm: bool = False` and replace the question construction:

```python
        default = "a" if group in DEFAULT_ALL else "n"
        if calm:
            print(calm_group(group, members))
            question = (f"  {CALM[group][1]} [a]ll / [n]one / [p]ick "
                        f"(Enter: {'all' if default == 'a' else 'none'}) ")
        else:
            question = (f"{group}: {len(members)} item(s) — {GROUP_HELP[group]} "
                        f"[a]ll / [n]one / [p]ick (default {'all' if default == 'a' else 'none'}): ")
```

In `_apply_binary`, wrap the three not-done results:

```python
    if not cmds:
        return NotDone(f"{v.item.name}: no {key} command for this platform. {entry.get('manual', '')}".strip())
    ...
    if confirm_cmds and not ui.confirm(ask, "  run it? [y/N] "):
        return NotDone(f"{v.item.name} {key}: skipped")
    ...
    line = f"{v.item.name} {key}: " + ", ".join(results)
    return _done(line, all(r == "ok" for r in results))
```

In `run`, after resolving `own_pairs` from the spec:

```python
    calm = not out.VERBOSE
    asks_each_group = calm and apply_changes and interactive and not yes and groups is None
    if asks_each_group:
        print(render_calm(verdicts, findings, header_only=True))
    else:
        print(render_calm(verdicts, findings) if calm else render_plan(verdicts, findings))
```

pass `calm=asks_each_group` to `select(...)`; before `own.ask_choices(...)` (inside the same conditional expression's interactive branch) print the own block when calm:

```python
    if own_pairs is None:
        unmanaged = [v for v in own.unmanaged(verdicts) if v.item.name not in skip]
        if asks_each_group and unmanaged:
            print(calm_group("own", unmanaged))
        own_pairs = own.ask_choices(unmanaged, ask) if interactive and not yes else []
```

before the secrets confirm:

```python
        if remaining and asks_each_group:
            print(calm_secrets(remaining))
```

replace the result printing:

```python
        if calm and not not_done:
            for line in calm_summary(chosen, acting):
                print(line)
        else:
            if calm:
                print("\nSome changes did not complete; details:")
            for line in lines:
                print(redact(line))
```

and the `finally` block:

```python
    finally:
        if not bk.empty:
            if calm:
                print(f"\n{UNDO_LINE}")
                out.detail(f"backup: {bk.root} (it holds old configs, keep it private)")
            else:
                print(f"\nbackup: {bk.root}  (undo: loadout restore {bk.root}; it holds old configs, keep it private)")
```

`not_done` is filled by `apply_own` only for failures of acting items and removals; this is the list the summary trusts.

- [ ] **Step 4: Add `--verbose`** to `_register_adopt` in `commands.py`: `p.add_argument("--verbose", action="store_true", help="full detail: commands, long reasons, the items that stay")`, and at the start of its `run(a)`: `if a.verbose: out.VERBOSE = True` (import `out`).

- [ ] **Step 5: Run** `tests/test_adopt_calm.py` → pass; full suite → pass. A failing old test that asserts `_apply_binary`'s return type or text: keep the text, accept `NotDone` (it subclasses `str`).

- [ ] **Step 6: Commit** — `feat(adopt): calm view with plain headings, short reasons and a summary`

---

### Task 5: Calm `bootstrap`

**Files:**
- Modify: `cli/loadout/bootstrap.py` (`_step`, `check_prereqs`, `bootstrap`; new `INTRO`, `PROBLEM`, `_report`, `_tilde`, `_prereq_summary`)
- Modify: `cli/loadout/commands.py:126-135` (`--verbose`)
- Test: `tests/test_bootstrap_calm.py`

**Interfaces:**
- Consumes: `out.*`, `check.format_results`, `adopt.run` (calm by itself).
- Produces: `check_prereqs(install, ask, installed: list | None = None) -> list[str]`.

- [ ] **Step 1: Failing tests** (`tests/test_bootstrap_calm.py`). Read `tests/test_bootstrap.py` first and reuse its setup for a bootstrap run (fake_home, fake_runner, a personal layer that exists, `plugins=False` unless the test needs plugins); the snippets show the assertions:

```python
import pytest

from loadout import bootstrap, out, runner


@pytest.fixture
def calm(monkeypatch):
    monkeypatch.setattr(out, "VERBOSE", False)


def _run(**kw):
    args = dict(install=False, yes=True, plugins=False, adopt_step=False, ask=lambda q: "", interactive=False)
    args.update(kw)
    return bootstrap.bootstrap(**args)


def test_calm_bootstrap_is_one_line_per_step(fake_home, fake_runner, calm, capsys):
    (fake_home / ".config/loadout/personal").mkdir(parents=True)
    _run()
    text = capsys.readouterr().out
    assert text.startswith(bootstrap.INTRO)
    for name in ("Prerequisites", "Personal layer", "Rules and settings", "Secrets", "PATH", "Health check"):
        assert any(line.split(maxsplit=1)[-1].startswith(name) for line in text.splitlines()), name
    assert "== " not in text and "[ok  ]" not in text and "linked " not in text
    assert "Next: " in text


def test_calm_bootstrap_shows_failed_plugin_line(fake_home, fake_runner, calm, capsys, monkeypatch):
    (fake_home / ".config/loadout/personal").mkdir(parents=True)
    monkeypatch.setattr(bootstrap, "setup_plugins", lambda: ["plugin x@y: failed: no network"])
    _run(plugins=True)
    text = capsys.readouterr().out
    assert "plugin x@y: failed: no network" in text
    assert any("Plugins" in line and line.startswith(("!", "\033[33m!")) for line in text.splitlines())


def test_calm_bootstrap_lists_failed_checks(fake_home, fake_runner, calm, capsys, monkeypatch):
    from loadout import check
    (fake_home / ".config/loadout/personal").mkdir(parents=True)
    monkeypatch.setattr(check, "run_checks", lambda: [check.CheckResult("a", True), check.CheckResult("b", False, "bad", "fix")])
    _run()
    text = capsys.readouterr().out
    assert "1 of 2 OK" in text and "[FAIL] b: bad" in text
```

- [ ] **Step 2: Run, expect FAIL** — `AttributeError: module 'loadout.bootstrap' has no attribute 'INTRO'`.

- [ ] **Step 3: Implement** in `bootstrap.py`. Add `import re` and `out` to the imports. Replace `_step` and add helpers:

```python
INTRO = "loadout sets up Claude Code with a reviewed kit of plugins, rules and tools."
# lines that report something the user must see even in calm mode
PROBLEM = re.compile(r"failed|skipped|not changed|could not|cannot|do not run")


def _step(title: str) -> None:
    if out.VERBOSE:
        print(f"\n== {title}")


def _tilde(path: Path) -> str:
    home = str(paths.home())
    return "~" + str(path)[len(home):] if str(path).startswith(home) else str(path)


def _report(name: str, summary: str, lines: list[str] = (), level: str = "ok") -> None:
    """One status line; problem lines always follow it, the rest only with --verbose."""
    bad = [line for line in lines if PROBLEM.search(line)]
    out.status(name, summary, "warn" if bad and level == "ok" else level)
    for line in lines:
        (out.problem if line in bad else out.detail)(line)


def _prereq_summary(missing: list[str], installed: list[str]) -> tuple[str, str]:
    entries = [e for e in catalog.binaries() if not e.get("helper") and _wanted(e)]
    ready = sum(1 for e in entries if runner.have(e["id"]))
    text = f"{ready} tools ready"
    if installed:
        text += f", installed {', '.join(installed)}"
    if missing:
        text += f", missing {', '.join(missing)}"
    required = {e["id"] for e in entries if e.get("required")}
    return text, ("fail" if set(missing) & required else "warn" if missing else "ok")
```

In `check_prereqs`: add the `installed: list | None = None` parameter; replace `print("installing: " + " ".join(cmd))` with

```python
                if out.VERBOSE:
                    print("installing: " + " ".join(cmd))
                elif cmd is cmds[0]:
                    print(f"  installing {name}…")
```

replace `print(f"  failed: {_tail(res)}")` with `out.problem(f"failed: {_tail(res)}")` and `print(hint)` with `out.problem(hint)`; after the install loop, `if installed is not None and runner.have(name): installed.append(name)` (only inside the `if install and cmds:` branch); the two `missing …` prints become `out.problem(...)` with the same text; the `gh auth setup-git` success print becomes `out.detail(...)` and the "gh is not logged in" print becomes `out.problem(...)`.

Rewrite the body of `bootstrap()` from the WSL step to the end:

```python
    print(INTRO)
    version = wsl.detect()
    if version is not None:
        _step("WSL")
        out.status("WSL", f"WSL {version}")
        for line in wsl.report_lines(version, wsl.current_dir()):
            out.problem(line)
    _step("Prerequisites")
    installed: list[str] = []
    missing = check_prereqs(install, ask, installed=installed)
    summary, level = _prereq_summary(missing, installed)
    out.status("Prerequisites", summary, level)
    bk = Backup(description="bootstrap")
    _step("Personal layer")
    fresh = not paths.personal_root().exists()
    message, personal_ok = ensure_personal(ask, bk, interactive)
    starter = fresh and personal_ok and paths.personal_root().exists() and not (paths.personal_root() / ".git").exists()
    where = _tilde(paths.personal_root())
    if personal_ok:
        _report("Personal layer", f"created {where}" if starter else f"cloned into {where}" if fresh else f"using {where}",
                [message])
    else:
        out.status("Personal layer", "clone failed", "fail")
        out.problem(message)
    _step("Links")
    link_lines = link.link_all(bk, retry_symlinks=True) + link.link_bin(bk)
    if not yes and not interactive:
        out.detail("non-interactive: skipping the configure prompt (run `loadout configure` later)")
    elif not yes and ui.confirm(ask, "\nCustomize preferences and global add-ons now? [y/N] "):
        from .configure import wizard
        wizard(ask, first_run=False, setup=False, interactive=interactive, preferences_asked=starter)
    _step("Settings")
    settings_path = paths.claude_home() / "settings.json"
    if settings_path.exists() and settings_merge.would_change():
        bk.save_copy(settings_path, "settings.json before loadout merge")
    settings_merge.backup_snapshot(bk)
    before, after = settings_merge.apply_settings()
    from .personal_mcp import apply_mcp
    merged = "settings updated" if before != after else "settings already up to date"
    _report("Rules and settings", "linked, " + ("settings merged" if before != after else "settings up to date"),
            link_lines + [merged] + apply_mcp())
    if plugins:
        _step("Marketplaces and plugins")
        lines = setup_plugins()
        if any(line.endswith(": added") for line in lines):
            settings_merge.apply_settings()  # the CLI rewrites marketplace entries and drops autoUpdate
        total = sum(1 for on in settings_merge.desired_settings().get("enabledPlugins", {}).values() if on)
        failed = sum(1 for line in lines if PROBLEM.search(line))
        _report("Plugins", f"{total} kit plugins ready" if not failed else f"{failed} failed (below)", lines)
    if adopt_step:
        _step("Adopt existing setup")
        if not yes and not interactive:
            out.detail("non-interactive: skipping adopt (review with `loadout adopt`, apply with `loadout adopt --apply`)")
        else:
            print()
            adopt.run(apply_changes=True, groups=None, skip=set(), yes=yes, ask=ask, interactive=interactive)
            print()
    _step("Secrets")
    _report("Secrets", f"{_tilde(paths.secrets_file())} ready", setup_secrets(bk))
    _step("PATH")
    path_lines, path_changed = setup_path(bk)
    _report("PATH", "tool folders added (new terminals)" if path_changed else "already set up",
            path_lines or ["PATH already set up"])
    if not bk.empty:
        out.detail(f"backup: {bk.root}  (undo: loadout restore {bk.root})")
    _step("Check")
    results = check.run_checks()
    if out.VERBOSE:
        text, code = check.format_results(results)
        print(text)
    else:
        bad = [r for r in results if not r.ok]
        text, code = check.format_results(bad)
        out.status("Health check", f"{len(results) - len(bad)} of {len(results)} OK",
                   "fail" if code else "warn" if bad else "ok")
        if bad:
            print(text)
    todo = still_to_do(os_key())
    if not out.VERBOSE and not bk.empty:
        print(f"\n{adopt.UNDO_LINE}")
    if path_changed:
        print("\nOpen a new terminal so the new PATH applies.")
    if todo:
        print("\nStill to do (in a new terminal):" if path_changed else "\nStill to do:")
        for line in todo:
            print(f"  - {line}")
    if out.VERBOSE:
        print("\nThen start Claude Code." if path_changed else "\nRestart Claude Code to load plugins and rules.")
    else:
        print("\nNext: run `claude` in a new terminal." if path_changed
              else "\nNext: run `claude` (restart it if it is open). The kit loads automatically.")
    if not personal_ok:
        print("personal layer: the clone failed (see above); re-run bootstrap after fixing access")
        return 1
    return code
```

Old outputs that verbose tests assert stay reachable: `== Title` headers, `installing: …`, `settings updated`, `backup: …`, the full check list, the closing sentences. A verbose test that asserted the old "non-interactive: skipping …" lines still sees them (detail prints in verbose).

- [ ] **Step 4: Add `--verbose`** to `_register_bootstrap`: `p.add_argument("--verbose", action="store_true", help="print every detail of every step")` and change the default func to a function that sets `out.VERBOSE = True` when `a.verbose`, then calls `bootstrap.bootstrap(...)` as today.

- [ ] **Step 5: Run** `tests/test_bootstrap_calm.py` → pass; full suite → pass. Fix old tests only where they asserted text that moved (for example the `== ` headers when a test set `VERBOSE` false itself); never weaken a problem-line assertion.

- [ ] **Step 6: Commit** — `feat(bootstrap): one status line per step, a clear end with undo and next step`

---

### Task 6: Docs for the calm output

**Files:**
- Modify: `docs/reference/cli.md` (the `--verbose` flags; describe the calm output of bootstrap, adopt, check)
- Modify: every doc that quotes old output. Find them with `grep -rn "== Prereq\|\[ok  \]\|REMOVE (\|MIGRATE (\|SCOPE-DOWN (\|KEEP (\|backup: " docs README.md --include=*.md | grep -v docs/superpowers`
- Modify: `AGENTS.md` (map: add `out.py` calm output next to `ui.py`)

- [ ] **Step 1:** Update each hit to the new output (calm by default, today's detail with `--verbose`). Keep group keys (`remove`, `migrate`, `scope-down`) where docs explain `--groups`: they are unchanged.
- [ ] **Step 2:** Check every link and path in the touched files resolves (`grep -o "](\([^)]*\))"` and test each relative path exists).
- [ ] **Step 3:** Full suite → pass (repo-static tests read docs).
- [ ] **Step 4: Commit** — `docs: calm output and --verbose for bootstrap, adopt and check`

---

### Task 7: Demo sandbox runs the real one-liner offline

**Files:**
- Create: `demo/bin/curl`, `demo/bin/uv`
- Modify: `demo/bin/claude` (`mcp list`, `plugin list`)
- Modify: `demo/sandbox.sh` (copy the stubs; no bootstrap during setup)
- Test: `tests/test_demo.py`

**Interfaces:**
- Produces: env `LOADOUT_DEMO_KIT` (the kit path the curl stub serves `bootstrap.sh` from); the tape (Task 8) sets it with `LOADOUT_REPO_URL=/kit`.

- [ ] **Step 1: Failing tests** (append to `tests/test_demo.py`)

```python
import re

README_URL = "https://raw.githubusercontent.com/jonasyr/agent-loadout/main/bootstrap.sh"


@pytest.mark.skipif(os.name == "nt", reason="sh stubs")
@pytest.mark.parametrize("stub", ["curl", "uv"])
def test_demo_stubs_refuse_outside_the_sandbox(tmp_path, stub):
    p = subprocess.run(["sh", str(DEMO / "bin" / stub), "--version"], env={**os.environ, "HOME": str(tmp_path)},
                       capture_output=True, text=True, timeout=30)
    assert p.returncode != 0 and "sandbox" in p.stderr


@pytest.mark.skipif(os.name == "nt", reason="sh stubs")
def test_demo_curl_serves_only_the_readme_url(tmp_path):
    (tmp_path / ".loadout-demo").touch()
    env = {**os.environ, "HOME": str(tmp_path), "LOADOUT_DEMO_KIT": str(paths.kit_root())}
    ok = subprocess.run(["sh", str(DEMO / "bin/curl"), "-fsSL", README_URL], env=env, capture_output=True, text=True, timeout=30)
    assert ok.returncode == 0 and ok.stdout == (paths.kit_root() / "bootstrap.sh").read_text()
    bad = subprocess.run(["sh", str(DEMO / "bin/curl"), "-fsSL", "https://example.com/x"], env=env, capture_output=True, text=True, timeout=30)
    assert bad.returncode != 0 and bad.stdout == ""


@pytest.mark.skipif(os.name == "nt", reason="sh stubs")
def test_demo_uv_finds_the_real_python(tmp_path):
    (tmp_path / ".loadout-demo").touch()
    p = subprocess.run(["sh", str(DEMO / "bin/uv"), "python", "find", "--system", ">=3.10"],
                       env={**os.environ, "HOME": str(tmp_path)}, capture_output=True, text=True, timeout=30)
    assert p.returncode == 0 and "python3" in p.stdout


def test_tape_types_the_readme_one_liner():
    readme = (paths.kit_root() / "README.md").read_text()
    line = next(l for l in readme.splitlines() if l.startswith("curl -fsSL") and README_URL in l)
    assert f'Type "{line}"' in (DEMO / "loadout.tape").read_text()


def test_tape_never_runs_the_real_claude_clip_recorder():
    for f in ("render.sh", "loadout.tape", "sandbox.sh"):
        assert "record-claude" not in (DEMO / f).read_text()
```

`test_tape_types_the_readme_one_liner` stays red until Task 8 writes the tape; run it there.

- [ ] **Step 2: Run, expect FAIL** (stubs missing).

- [ ] **Step 3: Write the stubs.** `demo/bin/curl`:

```sh
#!/bin/sh
# A stand-in for curl in the demo sandbox: it serves only the README's bootstrap URL, from the kit itself.
# Never put it on a real PATH.
[ -f "$HOME/.loadout-demo" ] || { echo "demo curl: refusing to run outside the demo sandbox" >&2; exit 1; }
url=""
for a in "$@"; do case "$a" in -*) ;; *) url="$a" ;; esac; done
if [ "$url" != "https://raw.githubusercontent.com/jonasyr/agent-loadout/main/bootstrap.sh" ]; then
  echo "demo curl: the sandbox has no network ($url)" >&2
  exit 22
fi
exec cat "${LOADOUT_DEMO_KIT:?}/bootstrap.sh"
```

`demo/bin/uv`:

```sh
#!/bin/sh
# A stand-in for uv in the demo sandbox: `uv python find` returns the container's Python. Never put it on a real PATH.
[ -f "$HOME/.loadout-demo" ] || { echo "demo uv: refusing to run outside the demo sandbox" >&2; exit 1; }
if [ "$1" = "python" ] && [ "$2" = "find" ]; then
  command -v python3
  exit
fi
echo "uv 1.0.0"
```

In `demo/bin/claude`, before the final `elif` chain ends, add:

```python
elif args[:2] == ["mcp", "list"]:
    servers = json.loads((home / ".claude.json").read_text()).get("mcpServers", {})
    for name, cfg in servers.items():
        print(f"{name}: {' '.join([cfg.get('command', ''), *cfg.get('args', [])])}")
elif args[:2] == ["plugin", "list"]:
    print("\n".join(json.loads(plugins.read_text()).get("plugins", {})) if plugins.exists() else "")
```

- [ ] **Step 4: Change `demo/sandbox.sh`:** drop `uv` from the stub `for` loop, `cp "$kit/demo/bin/curl" "$kit/demo/bin/uv" "$home/.local/bin/"` next to the claude copy, update the header comment ("then the recording runs the one-liner"), and delete the last three lines (`export …`, the two `git config` stay but must run with `HOME="$home"`: write them as `HOME="$home" git config --global …`), removing the `loadout bootstrap` call.

- [ ] **Step 5: Run** `tests/test_demo.py` (all but the tape test) → pass; full suite (tape test excluded with `-k "not readme_one_liner"`) → pass.

- [ ] **Step 6: Commit** — `feat(demo): offline curl and uv stubs so the tape runs the real one-liner`

---

### Task 8: The styled tape, title cards and render pipeline

**Files:**
- Create: `demo/style.tape`, `demo/card.sh`
- Modify: `demo/loadout.tape` (rewrite), `demo/Containerfile` (font, locale), `demo/render.sh` (mp4 → join → gif)
- Test: `tests/test_demo.py` (existing tape tests adapted)

- [ ] **Step 1: `demo/style.tape`** (shared by both tapes)

```
# The README demo's look, shared by loadout.tape and claude.tape.
Set Shell bash
Set FontFamily "JetBrains Mono"
Set FontSize 16
Set LineHeight 1.3
Set Width 1200
Set Height 800
Set Padding 28
Set Margin 36
Set MarginFill "#181a24"
Set BorderRadius 10
Set WindowBar Rings
Set Framerate 20
Set TypingSpeed 55ms
Set Theme { "name": "loadout", "background": "#0f1117", "foreground": "#e6e6eb", "cursor": "#a78bfa", "selection": "#2a2d3a", "black": "#1c1f2b", "red": "#f87171", "green": "#4ade80", "yellow": "#fbbf24", "blue": "#93c5fd", "purple": "#a78bfa", "cyan": "#67e8f9", "white": "#d4d4dc", "brightBlack": "#6b7080", "brightRed": "#fca5a5", "brightGreen": "#86efac", "brightYellow": "#fde68a", "brightBlue": "#bfdbfe", "brightPurple": "#c4b5fd", "brightCyan": "#a5f3fc", "brightWhite": "#ffffff" }
```

- [ ] **Step 2: `demo/card.sh`**

```bash
#!/usr/bin/env bash
# A title card for the README demo: a cleared screen, the title in the accent colour and a muted subtitle, centred.
title="$1" sub="${2:-}"
cols=$(tput cols) rows=$(tput lines)
pad() { printf '%*s' $(( (cols - ${#1}) / 2 )) ''; }
tput civis; clear
for _ in $(seq $(( rows / 2 - 2 ))); do echo; done
printf '%s\033[1;35m%s\033[0m\n\n' "$(pad "$title")" "$title"
[ -z "$sub" ] || printf '%s\033[2m%s\033[0m\n' "$(pad "$sub")" "$sub"
```

(`tput cnorm` runs in the hidden command after each card, before the next scene.)

- [ ] **Step 3: `demo/Containerfile`**: install `fonts-jetbrains-mono` next to python3 and git, and add `ENV LANG=C.UTF-8` (so `${#1}` counts characters, and Python prints `✓`).

- [ ] **Step 4: Probe the prompts.** Write a first `demo/loadout.tape` with only the hidden setup and the one-liner, `Output demo.txt` (VHS writes the final screen as text) and long sleeps, render it with a temporary copy of render.sh's container command, and read the text output to list every question bootstrap asks in this sandbox (personal layer URL, "about you" questions, preferences, "Customize…?", the adopt groups, own tools, `Apply N change(s)?`, the secrets question). Write the list into the tape as comments, in order.

- [ ] **Step 5: Write `demo/loadout.tape`** in this shape (answers and Wait patterns from the probe; one `Wait+Screen` per question so timing never drifts):

```
# The README demo: an existing Claude Code setup, the one-liner, the result. Render with demo/render.sh
# (in a container, without network); it records the real CLI in a sandbox HOME with fake data.
Output demo.mp4
Output demo.txt
Require bash
Source demo/style.tape

Hide
Type "bash /kit/demo/sandbox.sh /home/demo && export HOME=/home/demo PATH=/home/demo/.local/bin:$PATH LOADOUT_NO_AUTO_PULL=1 LOADOUT_REPO_URL=/kit LOADOUT_DEMO_KIT=/kit && cd ~ && PS1='\[\e[35m\]~ ❯\[\e[0m\] ' && card() { bash /kit/demo/card.sh \"$@\"; } && clear"
Enter
Sleep 6s
Type "card loadout 'A reviewed Claude Code setup in one command'"
Enter
Show
Sleep 3s

Hide
Type "card '① An existing Claude Code setup' 'a few MCP servers and plugins, a token in plain text'"
Enter
Show
Sleep 2500ms
Hide
Type "tput cnorm; clear"
Enter
Show
Type "claude mcp list"
Enter
Sleep 2s
Type "claude plugin list"
Enter
Sleep 3s

Hide
Type "card '② One command' 'installs what is missing, then reviews what you already have'"
Enter
Show
Sleep 2500ms
Hide
Type "tput cnorm; clear"
Enter
Show
Type "curl -fsSL https://raw.githubusercontent.com/jonasyr/agent-loadout/main/bootstrap.sh | bash -s -- --install"
Sleep 600ms
Enter
# one block per question, from the probe, e.g.:
Wait+Screen@60s /git URL to clone/
Sleep 1200ms
Enter
# ...
Wait+Screen@60s /Remove them\?/
Sleep 1500ms
Type "a"
Enter
# ... (migrate a, scope-down a, own: c, g, g, Apply: y, secrets: y)
Wait+Screen@120s /Next: run/
Sleep 5s

Hide
Type "card '③ Done. Undo any time.' 'loadout restore --list shows every backup'"
Enter
Show
Sleep 2500ms

Hide
Type "card '④ Claude Code starts with the kit' 'plugins, rules and MCP servers, ready'"
Enter
Show
Sleep 2500ms
```

The one-liner line must equal the README's (the test compares them).

- [ ] **Step 6: `demo/render.sh`** — after `vhs demo/loadout.tape`, inside the container:

```bash
  W=1200 H=800 FILL=0x181a24
  if [ -f demo/claude-clip.mp4 ]; then
    ffmpeg -y -loglevel error -i demo.mp4 -i demo/claude-clip.mp4 -filter_complex \
      "[0:v]fps=20,setsar=1[a];[1:v]scale=$W:$H:force_original_aspect_ratio=decrease,pad=$W:$H:(ow-iw)/2:(oh-ih)/2:color=$FILL,fps=20,setsar=1[b];[a][b]concat=n=2:v=1[v]" \
      -map "[v]" joined.mp4
  else
    echo "no demo/claude-clip.mp4 yet: rendering the sandbox part alone (record it with demo/record-claude.sh)" >&2
    cp demo.mp4 joined.mp4
  fi
  ffmpeg -y -loglevel error -i joined.mp4 -vf "fps=20,split[s0][s1];[s0]palettegen=stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=5" demo.gif
  cp demo.gif /out/demo.gif && cp demo.txt /out/demo.txt
```

Write `demo.txt` to the scratchpad instead of `docs/assets` if it should not be committed: mount a second output, or delete it after reading (`docs/assets/demo.txt` must not be committed; add it to `.gitignore`).

- [ ] **Step 7: Adapt the existing tape tests**: `test_tape_records_only_the_sandbox_home` still holds (sandbox.sh between Hide and Show); add `assert "Source demo/style.tape" in tape and "--network=none" in render`. Run `tests/test_demo.py` → all pass, including `test_tape_types_the_readme_one_liner`.

- [ ] **Step 8: Render and look.** `bash demo/render.sh`; then extract frames to the scratchpad with ffmpeg in the same image (`ffmpeg -i demo.gif -vf "select='not(mod(n\,60))'" -vsync vfr frame%03d.png`) and read at least: the title card, scene 1, the adopt questions, the final summary. Check: text readable, nothing cut off at 1200×800, colours as the theme, no stray hidden commands visible, GIF size `< 5 MB` (`ls -l docs/assets/demo.gif`). If too big: `Set Framerate 15` and `fps=15`, render again.

- [ ] **Step 9: Commit** — `feat(demo): styled tape with title cards, one-liner storyline and clip join`

---

### Task 9: The Claude Code clip (maintainer records), README and CONTRIBUTING

**Files:**
- Create: `demo/claude.tape`, `demo/record-claude.sh`
- Modify: `README.md` (alt text and caption), `CONTRIBUTING.md` ("The README demo")

- [ ] **Step 1: `demo/claude.tape`**

```
# The real Claude Code at the end of the README demo. Recorded by the maintainer: demo/record-claude.sh
Output demo/claude-clip.mp4
Require claude
Source demo/style.tape

Hide
Type "cd \"$(mktemp -d)\" && git init -q && PS1='\[\e[35m\]~ ❯\[\e[0m\] ' && clear"
Enter
Sleep 1s
Show
Type "claude"
Sleep 400ms
Enter
Wait+Screen@30s /trust/
Sleep 1500ms
Enter
Sleep 4s
Type "/mcp"
Sleep 500ms
Enter
Sleep 5s
Escape
Sleep 800ms
Type "/exit"
Enter
Sleep 1s
```

- [ ] **Step 2: `demo/record-claude.sh`**

```bash
#!/usr/bin/env bash
# Records demo/claude-clip.mp4: the real Claude Code with your loadout setup, in a throwaway folder.
# Run it yourself (it uses your Claude Code login); review the clip before committing it, it shows your
# plugins and paths. No prompt is sent to the model. Needs vhs on this machine and the JetBrains Mono font.
set -euo pipefail
kit="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
command -v vhs >/dev/null || { echo "needs vhs (Arch: sudo pacman -S vhs; others: https://github.com/charmbracelet/vhs)" >&2; exit 1; }
fc-list 2>/dev/null | grep -qi "JetBrains Mono" || { echo "needs the JetBrains Mono font (Arch: sudo pacman -S ttf-jetbrains-mono)" >&2; exit 1; }
cd "$kit"
vhs demo/claude.tape
echo "wrote demo/claude-clip.mp4: watch it, then run demo/render.sh"
```

`chmod +x` both scripts (and `demo/card.sh`, the stubs).

- [ ] **Step 3: README**: new alt text ("loadout's one-liner on a machine with an existing Claude Code setup: it installs what is missing, reviews the setup with reasons, applies the choices with an undo, and Claude Code starts with the kit") and a one-line caption under the image: `<sub>One command on a machine that already has Claude Code. Recorded in a sandbox with fake data.</sub>`.

- [ ] **Step 4: CONTRIBUTING "The README demo"**: the storyline, `demo/render.sh` (offline, podman), `demo/record-claude.sh` (maintainer only, real login, review before commit), the shared `demo/style.tape`, and that the GIF must stay under 5 MB.

- [ ] **Step 5: Full suite** → pass. **Commit** — `feat(demo): Claude Code clip recorder; README caption and contributing notes`

- [ ] **Step 6: Hand-off to the maintainer** (not an agent step): ask them to run `! demo/record-claude.sh`, watch `demo/claude-clip.mp4`, then re-run `bash demo/render.sh`, look at the frames of the joined GIF, and commit `demo/claude-clip.mp4` and `docs/assets/demo.gif` (`chore(demo): record the Claude Code clip`).
