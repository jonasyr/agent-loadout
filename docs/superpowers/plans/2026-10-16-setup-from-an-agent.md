# Setup from inside an agent Implementation Plan — PR C

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A user can ask Codex or Claude Code to set loadout up: the agent follows one docs page, asks the user, shows one bootstrap command and runs it after a yes; bootstrap needs no terminal for any answer and never waits for one.

**Architecture:** A new `answers.py` loads and validates `--answers FILE` (the starter layer's "about you" fields and working preferences) before bootstrap changes anything. `ensure_personal` takes `--personal new|<git URL>` and the answers; `configure._about_you` and `preferences.ask_all` take given answers instead of asking. Without a terminal (or with `--yes`), bootstrap never calls `ask`, so an agent's shell with an open stdin cannot hang it. A docs page written for agents, a README sentence and new configure-skill rows complete it.

**Tech Stack:** Python 3.11+ standard library, pytest; Markdown docs.

**Spec:** `docs/superpowers/specs/2026-10-15-codex-anywhere-design.md` (section "PR C"; decision 3)

## Global Constraints

- Tests use `fake_home` and `fake_runner`; never the real `~/.claude`, `~/.claude.json`, `~/.codex` or `~/.config/loadout`; no real `git clone`, installer or `claude`/`codex` command.
- `--answers` keys: unknown keys refused (spec: "unknown keys refused"), before any question, clone or file change.
- With all answers given, `--yes` asks nothing (spec).
- The agent page: plain steps, exact commands, one question at a time, never change anything before the user's yes, never touch `~/.claude`/`~/.codex` by hand (spec).
- No secret goes into the answers file, the personal layer, `me.md` or the output: the page tells the agent to put none there; loadout does not print the answers.
- Conventional Commits; git as `/usr/bin/git`; tests `uv run --python 3.12 --with pytest pytest -q`.

## Review Focus

- An agent's shell has no terminal but an open, silent stdin: bootstrap must never call `ask` then (it would wait forever). Test: `interactive=False` with an `ask` that fails the test (Task 3).
- `--answers` with a bad value (`answer_language: klingon`, `other` without text, a number, `automode_trust`) is refused with a message naming the key, before the personal layer exists (Task 1, Task 3).
- `--personal`/`--answers` given while a personal layer already exists: not used, and bootstrap says so in one line instead of ignoring them silently (Task 3).
- `--personal <URL>` whose clone fails: exit 1 and the same access hint as today (Task 3).
- `--yes` in a terminal with a fresh machine: no question at all (personal layer = starter, about-you defaults, preferences defaults) (Task 3).

---

### Task 1: `answers.py` — load and validate `--answers FILE`

**Files:** Create `cli/loadout/answers.py`; Test `tests/test_answers.py`

**Interfaces:** Produces `answers.Answers` (dataclass: `about: dict[str, str]` with keys among `name`, `role`, `languages`, `preferences`; `prefs: dict[str, tuple[str, str]]` pref id → `(value, free_text)`), `answers.load(path: str | Path) -> Answers` (raises `ValueError` with the problem), `answers.ABOUT_KEYS`.

File format (JSON object; every part optional):

```json
{
  "about": {"name": "Jonas", "role": "CS student", "languages": "Python, TypeScript", "preferences": "short answers"},
  "preferences": {"answer_language": "match", "commit_style": "conventional", "ai_attribution": "off"}
}
```

A free-text option is written as in `configure set pref-choice`: `"answer_language": "other:French"`.

- [ ] **Step 1: Write the failing tests**

```python
"""--answers FILE: the starter layer's answers, validated before bootstrap changes anything (spec PR C)."""
import json

import pytest

from loadout import answers


def _file(tmp_path, data):
    p = tmp_path / "answers.json"
    p.write_text(json.dumps(data) if not isinstance(data, str) else data, encoding="utf-8")
    return p


def test_a_full_file_loads(tmp_path, fake_home):
    a = answers.load(_file(tmp_path, {
        "about": {"name": "Jonas", "role": "student", "languages": "Python", "preferences": "short"},
        "preferences": {"answer_language": "other:French", "commit_style": "conventional"}}))
    assert a.about == {"name": "Jonas", "role": "student", "languages": "Python", "preferences": "short"}
    assert a.prefs == {"answer_language": ("other", "French"), "commit_style": ("conventional", "")}


def test_an_empty_object_is_no_answers(tmp_path, fake_home):
    a = answers.load(_file(tmp_path, {}))
    assert a.about == {} and a.prefs == {}


@pytest.mark.parametrize("data, word", [
    ({"abuot": {}}, "abuot"),
    ({"about": {"nmae": "x"}}, "nmae"),
    ({"preferences": {"no_such_pref": "x"}}, "no_such_pref"),
    ({"preferences": {"answer_language": "klingon"}}, "answer_language"),
    ({"preferences": {"answer_language": "other"}}, "answer_language"),
    ({"preferences": {"commit_style": 1}}, "commit_style"),
    ({"about": {"name": 3}}, "name"),
    ({"about": []}, "about"),
    ({"preferences": {"automode_trust": "generate"}}, "automode_trust"),
    ([], "object"),
])
def test_bad_answers_are_refused_with_the_key(tmp_path, fake_home, data, word):
    with pytest.raises(ValueError, match=word):
        answers.load(_file(tmp_path, data))


def test_a_file_that_is_not_json_is_refused(tmp_path, fake_home):
    with pytest.raises(ValueError, match="answers.json"):
        answers.load(_file(tmp_path, "{not json"))


def test_a_missing_file_is_refused(tmp_path, fake_home):
    with pytest.raises(ValueError, match="cannot read"):
        answers.load(tmp_path / "nope.json")
```

- [ ] **Step 2: Run** `uv run --python 3.12 --with pytest pytest -q tests/test_answers.py` → FAIL (`ImportError: cannot import name 'answers'`).

- [ ] **Step 3: Implement** `cli/loadout/answers.py`:

```python
"""--answers FILE: the starter layer's answers for bootstrap without a terminal (docs/how-to/install-with-an-agent.md)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

ABOUT_KEYS = ("name", "role", "languages", "preferences")
TOP_KEYS = ("about", "preferences")


@dataclass
class Answers:
    about: dict = field(default_factory=dict)
    prefs: dict = field(default_factory=dict)


def load(path) -> Answers:
    """The answers in path; ValueError names the first problem. Nothing is changed here."""
    from . import preferences
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"--answers: cannot read {path} ({exc.strerror or exc})") from None
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"--answers: {path.name} is not valid JSON ({exc})") from None
    if not isinstance(data, dict):
        raise ValueError(f"--answers: {path.name} must be a JSON object")
    unknown = [k for k in data if k not in TOP_KEYS]
    if unknown:
        raise ValueError(f"--answers: unknown key {unknown[0]!r} (allowed: {', '.join(TOP_KEYS)})")
    about = data.get("about", {})
    if not isinstance(about, dict):
        raise ValueError("--answers: about must be an object")
    for key, value in about.items():
        if key not in ABOUT_KEYS:
            raise ValueError(f"--answers: unknown key about.{key!r} (allowed: {', '.join(ABOUT_KEYS)})")
        if not isinstance(value, str):
            raise ValueError(f"--answers: about.{key} must be text")
    given = data.get("preferences", {})
    if not isinstance(given, dict):
        raise ValueError("--answers: preferences must be an object")
    known = {p["id"]: p for p in preferences.load()}
    prefs = {}
    for pid, raw in given.items():
        pref = known.get(pid)
        if pref is None:
            raise ValueError(f"--answers: unknown preference {pid!r} (ids: loadout configure show)")
        if pref.get("generator"):
            raise ValueError(f"--answers: {pid} needs a terminal; run `loadout configure prefs` after setup")
        if not isinstance(raw, str):
            raise ValueError(f"--answers: preferences.{pid} must be text, e.g. \"{pref['default']}\"")
        try:
            prefs[pid] = preferences.parse_choice(pref, raw)
        except ValueError as exc:
            raise ValueError(f"--answers: {exc}") from None
    return Answers({k: v.strip() for k, v in about.items()}, prefs)
```

- [ ] **Step 4: Run** the tests → PASS. **Step 5: Commit** — `feat(bootstrap): load and check the starter answers for --answers`

### Task 2: Given answers instead of questions in configure and preferences

**Files:** Modify `cli/loadout/configure.py` (`_about_you`, `ask_preferences`), `cli/loadout/preferences.py` (`ask_all`); Test `tests/test_answers.py`

**Interfaces:** Consumes `Answers` from Task 1. Produces `configure._about_you(ask, bk, given: dict | None = None, ask_missing: bool = True) -> bool`, `configure.ask_preferences(ask, fill_defaults, interactive, bk, quick=False, given: dict | None = None)`, `preferences.ask_all(ask, fill_defaults, interactive, bk=None, given: dict | None = None)`.

- [ ] **Step 1: Write the failing tests** (append):

```python
from loadout import backup, configure, paths, preferences


def test_given_about_answers_are_written_without_asking(fake_home):
    paths.personal_root().mkdir(parents=True)
    configure._about_you(lambda q: pytest.fail(f"asked: {q}"), backup.Backup(description="t"),
                         given={"name": "Jonas", "role": "student", "languages": "Python", "preferences": "short"})
    text = (paths.personal_root() / "rules" / "me.md").read_text()
    assert "Jonas" in text and "student" in text and "Python" in text


def test_missing_about_answers_take_defaults_without_asking_when_told(fake_home):
    paths.personal_root().mkdir(parents=True)
    configure._about_you(lambda q: pytest.fail(f"asked: {q}"), backup.Backup(description="t"),
                         given={"name": "Jonas"}, ask_missing=False)
    assert "Jonas" in (paths.personal_root() / "rules" / "me.md").read_text()


def test_missing_about_answers_are_asked_in_a_terminal(fake_home):
    paths.personal_root().mkdir(parents=True)
    asked = []
    configure._about_you(lambda q: asked.append(q) or "", backup.Backup(description="t"), given={"name": "Jonas"})
    assert len(asked) == 3 and not any("name" in q.lower() for q in asked)


def test_given_preferences_win_over_defaults_without_a_terminal(fake_home):
    paths.personal_root().mkdir(parents=True)
    (paths.personal_root() / "settings.json").write_text("{}\n")
    configure._about_you(lambda q: "", backup.Backup(description="t"), ask_missing=False)
    preferences.ask_all(lambda q: pytest.fail(q), fill_defaults=True, interactive=False,
                        bk=backup.Backup(description="t"), given={"answer_language": ("german", "")})
    assert "always answer in German" in (paths.personal_root() / "rules" / "me.md").read_text()


def test_given_preferences_are_not_asked_in_a_terminal(fake_home):
    paths.personal_root().mkdir(parents=True)
    (paths.personal_root() / "settings.json").write_text("{}\n")
    configure._about_you(lambda q: "", backup.Backup(description="t"), ask_missing=False)
    asked = []
    preferences.ask_all(lambda q: asked.append(q) or "", fill_defaults=True, interactive=True,
                        bk=backup.Backup(description="t"), given={"answer_language": ("german", "")})
    assert asked and not any(q.startswith("answer_language") for q in asked)
```

- [ ] **Step 2: Run** → FAIL (`TypeError: _about_you() got an unexpected keyword argument 'given'`).

- [ ] **Step 3: Implement.**

`configure._about_you`:

```python
ABOUT_QUESTIONS = (
    ("name", "NAME", "Your name: ", "me"),
    ("role", "ROLE", "Your role (e.g. backend developer, CS student): ", "developer"),
    ("languages", "LANGUAGES", "Main languages/stacks: ", "(not specified)"),
    ("preferences", "PREFERENCES", "Anything else about how you like to work (the next questions cover language, "
                                   "commits and answer style): ", "(not specified)"),
)


def _about_you(ask: Ask, bk: Backup, given: dict | None = None, ask_missing: bool = True) -> bool:
    """True when a new me.md was written (its preference answers are then asked with defaults).
    given: answers from --answers; ask_missing False (no terminal, or --yes): the rest take defaults unasked."""
    given = given or {}
    me = paths.personal_root() / "rules" / "me.md"
    if me.exists():
        if not ask_missing or not ui.confirm(ask, f"{me} already exists. Replace it with a new one? (the current one is backed up) [y/N] "):
            print(f"kept {me}")
            return False
    values = {}
    for key, slot, question, default in ABOUT_QUESTIONS:
        answer = given.get(key, "") or (ask(question).strip() if ask_missing and key not in given else "")
        values[slot] = answer or default
    ...  # template, backup and write unchanged
```

`preferences.ask_all` (the loop; `given` wins, and is never asked):

```python
def ask_all(ask: Ask, fill_defaults: bool, interactive: bool, bk: Backup | None = None,
            given: dict | None = None) -> list[str]:
    """... given: answers from --answers (id -> (value, text)); they are applied, not asked."""
    given = given or {}
    ...
    for pref in prefs:
        st = states[pref["id"]]
        if pref["id"] in given:
            answer = given[pref["id"]]
        elif interactive:
            answer = _ask_one(ask, pref, st, fill_defaults)
        else:
            answer = (pref["default"], "") if fill_defaults and not st.is_set else None
        ...
```

`configure.ask_preferences` gains `given: dict | None = None` and passes `given=given` to both `preferences.ask_all` calls.

- [ ] **Step 4: Run** `uv run --python 3.12 --with pytest pytest -q tests/test_answers.py tests/test_configure*.py tests/test_preferences*.py` → PASS. **Step 5: Commit** — `feat(configure): given answers replace the starter questions`

### Task 3: Bootstrap `--personal` and `--answers`; no question without a terminal

**Files:** Modify `cli/loadout/bootstrap.py` (`ensure_personal`, `bootstrap`, `_bootstrap`), `cli/loadout/commands.py` (`_register_bootstrap`); Test `tests/test_bootstrap_agent_flags.py` (create)

**Interfaces:** Consumes Tasks 1–2. Produces `bootstrap.bootstrap(..., personal: str | None = None, answers: str | None = None)`, `ensure_personal(ask, bk=None, interactive=None, before_starter=None, personal: str | None = None, given: answers.Answers | None = None, ask_missing: bool = True)`.

Behaviour:
- `--personal new` creates the starter layer; `--personal <URL>` clones it (same clone code, same failure hint and exit 1). An empty value or one starting with `-` is refused (`ValueError`) at the start.
- `--answers FILE` is loaded at the start of `_bootstrap` (before INTRO's side effects, next to the `--agents` check), so a bad file stops before any question, clone or write.
- A personal layer that already exists: `--personal` and `--answers` are not used, and bootstrap prints one line: `personal layer: <path> exists; --personal/--answers apply only to a new one (change answers with loadout configure prefs)`.
- Without a terminal, or with `--yes`, bootstrap never calls `ask`: `_bootstrap` replaces `ask` with a function that returns `""` (and records nothing). The personal layer is then `--personal`, else a starter; about-you and preferences take `--answers`, else defaults.

- [ ] **Step 1: Write the failing tests**

```python
"""Bootstrap needs no terminal: --personal and --answers, and no question without one (spec PR C)."""
import json

import pytest

from loadout import bootstrap, paths, runner


def _never(q):
    pytest.fail(f"asked without a terminal: {q}")


def _answers(tmp_path, data):
    p = tmp_path / "answers.json"
    p.write_text(json.dumps(data))
    return str(p)


def _run(**kw):
    kw.setdefault("ask", _never)
    kw.setdefault("interactive", False)
    return bootstrap.bootstrap(False, kw.pop("yes", False), False, False, agents="claude", **kw)


def test_no_terminal_never_asks_and_creates_a_starter(fake_home, fake_runner):
    _run()
    assert (paths.personal_root() / "rules" / "me.md").exists()


def test_yes_in_a_terminal_asks_nothing(fake_home, fake_runner):
    _run(interactive=True, yes=True)
    assert (paths.personal_root() / "settings.json").exists()


def test_personal_url_is_cloned(fake_home, fake_runner):
    _run(personal="git@github.com:me/personal.git")
    clone = [c for c in fake_runner.calls if c[:2] == ["git", "clone"]]
    assert clone and clone[0][-2:] == ["git@github.com:me/personal.git", str(paths.personal_root())]


def test_a_failed_clone_exits_1_with_the_access_hint(fake_home, fake_runner, capsys):
    fake_runner.responses[("git", "clone")] = runner.Result(128, "", "Permission denied (publickey)")
    assert _run(personal="git@github.com:me/personal.git") == 1
    assert "SSH URL" in capsys.readouterr().out


def test_personal_new_never_clones(fake_home, fake_runner):
    _run(personal="new", interactive=True, ask=lambda q: "")
    assert not [c for c in fake_runner.calls if c[:2] == ["git", "clone"]]


@pytest.mark.parametrize("value", ["", "-upload-pack=x", "--x"])
def test_a_bad_personal_value_is_refused_first(fake_home, fake_runner, value):
    with pytest.raises(ValueError, match="--personal"):
        _run(personal=value)
    assert not paths.personal_root().exists()


def test_answers_fill_the_starter(fake_home, fake_runner, tmp_path):
    _run(answers=_answers(tmp_path, {"about": {"name": "Jonas"}, "preferences": {"answer_language": "german"}}))
    me = (paths.personal_root() / "rules" / "me.md").read_text()
    assert "Jonas" in me and "always answer in German" in me


def test_bad_answers_stop_before_anything_changes(fake_home, fake_runner, tmp_path):
    with pytest.raises(ValueError, match="klingon|answer_language"):
        _run(answers=_answers(tmp_path, {"preferences": {"answer_language": "klingon"}}))
    assert not paths.personal_root().exists()


def test_an_existing_layer_says_the_flags_are_not_used(fake_home, fake_runner, tmp_path, capsys):
    paths.personal_root().mkdir(parents=True)
    _run(personal="new", answers=_answers(tmp_path, {"about": {"name": "Jonas"}}))
    out = capsys.readouterr().out
    assert "apply only to a new one" in out
    assert not (paths.personal_root() / "rules" / "me.md").exists()


def test_the_flags_reach_bootstrap_from_the_cli(fake_home, fake_runner, monkeypatch, tmp_path):
    from loadout import __main__ as main
    seen = {}
    monkeypatch.setattr(bootstrap, "bootstrap", lambda *a, **k: seen.update(k) or 0)
    main.main(["bootstrap", "--personal", "new", "--answers", "a.json"])
    assert seen["personal"] == "new" and seen["answers"] == "a.json"
```

- [ ] **Step 2: Run** `uv run --python 3.12 --with pytest pytest -q tests/test_bootstrap_agent_flags.py` → FAIL (`TypeError: bootstrap() got an unexpected keyword argument 'personal'`; the no-terminal test fails on the URL question).

- [ ] **Step 3: Implement.** Read `__main__.main` first to see how it takes argv (adapt the last test's call if it reads `sys.argv`; ruling).

`ensure_personal`:

```python
def ensure_personal(ask: Ask, bk: Backup | None = None, interactive: bool | None = None,
                    before_starter=None, personal: str | None = None, given=None,
                    ask_missing: bool = True) -> tuple[str, bool]:
    """... personal: --personal (new, or a git URL to clone); given: --answers for a starter layer;
    ask_missing False: nothing is asked (no terminal, or --yes)."""
    bk = bk if bk is not None else Backup(description="bootstrap")
    interactive = ui.is_interactive() if interactive is None else interactive
    root = paths.personal_root()
    if root.exists():
        if personal is not None or given is not None:
            return (f"personal layer: {root} exists; --personal/--answers apply only to a new one "
                    "(change answers with loadout configure prefs)"), True
        return f"personal layer: {root}", True
    if personal is not None:
        url = "" if personal == "new" else personal
    else:
        url = ask("Personal layer: git URL to clone (empty = create a starter one): ").strip() if ask_missing else ""
    ...  # clone branch unchanged
    if before_starter is not None:
        before_starter()
    ...  # settings.json unchanged
    from .configure import _about_you, ask_preferences
    _about_you(ask, bk, given=given.about if given else None, ask_missing=ask_missing)
    ask_preferences(ask, fill_defaults=True, interactive=interactive and ask_missing, bk=bk, quick=True,
                    given=given.prefs if given else None)
    return ...  # unchanged
```

`_bootstrap` (start, next to the `--agents` check):

```python
    if personal is not None and (not personal.strip() or personal.startswith("-")):
        raise ValueError("--personal: give `new` or the git URL of your personal layer")
    given = answers_mod.load(answers) if answers is not None else None
    if not interactive or yes:
        ask = _no_question  # an agent's shell may keep stdin open: never wait for an answer
```

with, at module level:

```python
def _no_question(question: str) -> str:
    """bootstrap without a terminal, or with --yes: every question takes its default, unasked."""
    return ""
```

and `from . import answers as answers_mod` inside `_bootstrap`. Pass `personal=personal, given=given, ask_missing=interactive and not yes` to `ensure_personal`. `bootstrap()` and `_bootstrap()` gain `personal: str | None = None, answers: str | None = None` and pass them through.

`commands._register_bootstrap`:

```python
    p.add_argument("--personal", metavar="new|URL",
                   help="the personal layer without asking: new (a starter) or the git URL to clone")
    p.add_argument("--answers", metavar="FILE",
                   help="JSON with the starter layer's answers (about, preferences; docs/how-to/install-with-an-agent.md)")
```

and pass `personal=a.personal, answers=a.answers`.

Existing tests that pass `interactive=False` with an `ask` that answers (for example a clone URL) now get no question: change them to pass `personal=` (the flag is the no-terminal way). List each changed test in the ledger.

- [ ] **Step 4: Run** the new file, then the full suite → PASS. **Step 5: Commit** — `feat(bootstrap): --personal and --answers, and no question without a terminal`

### Task 4: The agent page, the README sentence and the reference

**Files:** Create `docs/how-to/install-with-an-agent.md`; modify `README.md` (Quick start, after "Or clone it yourself"), `docs/README.md` (map), `docs/reference/cli.md` (bootstrap synopsis, `--personal`, `--answers`, the no-terminal paragraph), `docs/tutorials/getting-started.md` (one line linking the page); Test `tests/test_docs_links.py`, `tests/test_readme.py` (existing)

- [ ] **Step 1:** `docs/how-to/install-with-an-agent.md`, written to the agent. Sections:
  1. *Rules for you, the agent*: one question at a time; change nothing before the user's yes; never edit `~/.claude`, `~/.claude.json`, `~/.codex` or the personal layer by hand; no secret in the answers file or the chat; your shell has no terminal, so every answer goes in as a flag.
  2. *Look first* (read-only commands, show what you found): `uname -s`; on Linux `grep -qi microsoft /proc/sys/kernel/osrelease` (WSL); `command -v loadout claude codex serena uv python3 git`; in WSL `command -v codex.exe` and whether `codex` resolves under `/mnt/`; `ls ~/.config/loadout/personal` (an existing loadout); `loadout check` when loadout is there.
  3. *Ask* (one at a time): which agents (Claude Code, Codex, both); in WSL with only a Windows Codex, which side (`--codex-side`; link `wsl.md#codex`); the personal layer (a private git URL, or `new`); the four about-you answers and whether to keep the recommended preferences (show them with their defaults from `preferences.json` via `loadout configure show` once installed, or the table in `docs/reference/preferences-format.md`).
  4. *Write the answers file* to a temp path (format as in Task 1), show it.
  5. *Show the command and wait for a yes*: new machine `curl -fsSL https://raw.githubusercontent.com/jonasyr/agent-loadout/main/bootstrap.sh | bash -s -- --install --agents <list> --personal <new|URL> --answers <file> [--codex-side wsl|windows]` (PowerShell: the `bootstrap.ps1` one-liner from getting-started); loadout already installed: `loadout bootstrap --agents ... ` (repair). Say that `--install` runs installers without a further prompt (link security-and-trust). Do not add `--yes`: it also applies adopt's changes to an existing setup.
  6. *After the run*: bootstrap skips the adopt review without a terminal; run `loadout adopt` (dry run), explain it, and apply only agreed groups (the configure skill's row). Codex: the user approves hooks in `/hooks` once; project trust when Codex asks. Claude Code: restart or `/reload-plugins`; logins (`claude`, `gh auth login`) are the user's to type (`! <command>` in Claude Code).
  7. *Finish*: `loadout check`; for each warn/FAIL line, the fix from `troubleshooting.md`.
- [ ] **Step 2:** README: after the two install ways, one paragraph: "**Or let your agent do it**: paste this into Codex or Claude Code: `Set up loadout for me by following https://raw.githubusercontent.com/jonasyr/agent-loadout/main/docs/how-to/install-with-an-agent.md`". `cli.md`: synopsis `[--personal new|URL] [--answers FILE]`, two flag rows, and the sentence "Without a terminal, or with `--yes`, bootstrap asks nothing: `--personal` (else a starter layer) and `--answers` (else the defaults) give the answers." Replace the existing "Without a terminal and without `--yes` …" paragraph's "creates a starter personal layer with default preferences if none exists" with the same facts. `docs/README.md`: map line. getting-started: one line in Step 1.
- [ ] **Step 3: Run** `uv run --python 3.12 --with pytest pytest -q tests/test_docs_links.py tests/test_readme.py` → PASS. **Step 4: Commit** — `docs: set loadout up from inside Codex or Claude Code`

### Task 5: Configure skill rows

**Files:** Modify `plugins/loadout/skills/configure/SKILL.md` (table under "Other changes"); Test: `claude plugin validate plugins/loadout` and the full suite

- [ ] **Step 1:** Add rows:

| Request | Command |
|---|---|
| Set loadout up, or repair it | Follow `docs/how-to/install-with-an-agent.md` (in the folder `loadout kit-path` prints, or on GitHub when loadout is not installed): ask, write the answers file, show the bootstrap command with `--agents`, `--personal`, `--answers` (and `--codex-side` in WSL), run it after a yes, then `loadout adopt` as a dry run |
| Set up the other side (Windows and WSL) | Answer from `docs/how-to/wsl.md#codex`: each side runs its own loadout; on Windows `bootstrap.ps1` in PowerShell, in WSL `loadout bootstrap --codex-side wsl` |
| Serena is already set up | Answer from "Serena already set up?" in `docs/how-to/codex.md`: loadout uses the user's Serena and adds only missing hooks; nothing to change |

- [ ] **Step 2: Run** `claude plugin validate plugins/loadout` (read-only) and the full suite → PASS. **Step 3: Commit** — `feat(skills): configure sets loadout up from the agent page and answers the side and Serena questions`
