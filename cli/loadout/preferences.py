"""Structured working preferences (preferences.json at the kit root).

Answers live in the personal layer only: lines in a managed block of rules/me.md, or keys in
settings.json. Existing answers are detected (managed block, free text in me.md, personal
settings, kit defaults, then the user's own ~/.claude/settings.json via adopt), so a re-run
changes nothing the user already decided.
"""
from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import paths, runner, ui
from .backup import Backup
from .jsonio import load_json, save_json, write_atomic
from .settings_merge import MISSING, get_path

START = "<!-- loadout:preferences:start -->"
END = "<!-- loadout:preferences:end -->"
Ask = Callable[[str], str]
STACKS = [("package.json", "npm/node"), ("pyproject.toml", "uv/python"), ("requirements.txt", "uv/python"),
          ("Cargo.toml", "cargo"), ("go.mod", "go"), ("build.gradle", "gradle"), ("build.gradle.kts", "gradle"),
          ("pom.xml", "maven"), ("Dockerfile", "docker/docker compose"), ("compose.yaml", "docker/docker compose"),
          ("compose.yml", "docker/docker compose"), ("docker-compose.yml", "docker/docker compose"),
          ("docker-compose.yaml", "docker/docker compose")]
# host and owner of a git remote; credentials in an https URL are skipped, never printed
REMOTE = re.compile(r"^(?:[a-z][a-z0-9+.-]*://)?(?:[^@/]+@)?([^/:@]+)[:/](?:\d+/)?([^/]+)/[^/]+?(?:\.git)?/?$", re.I)


@dataclass
class State:
    value: str | None = None   # option value; None = not set, or a custom value (raw)
    text: str = ""             # free text of a free_text option
    source: str = ""           # where the answer was found
    raw: object = None         # a setting value that is none of the options (kept as is)
    lines: list = field(default_factory=list)  # me.md lines expressing it: (segment, index, line)

    @property
    def is_set(self) -> bool:
        return self.value is not None or self.raw is not None

    @property
    def outside(self) -> bool:
        return any(seg != "block" for seg, _, _ in self.lines)


def load() -> list[dict]:
    return load_json(paths.kit_root() / "preferences.json")["preferences"]


def by_id(pid: str) -> dict:
    prefs = load()
    for p in prefs:
        if p["id"] == pid:
            return p
    raise ValueError(f"no preference '{pid}' (available: {', '.join(p['id'] for p in prefs)})")


def by_id_in(prefs: list[dict], pid: str) -> dict:
    return next(p for p in prefs if p["id"] == pid)


def _me_path() -> Path:
    return paths.personal_root() / "rules" / "me.md"


def _settings_path() -> Path:
    return paths.personal_root() / "settings.json"


def _kit_settings() -> dict:
    return load_json(paths.kit_root() / "settings.base.json")


def _key(dotted: str) -> tuple:
    return tuple(dotted.split("."))


def _tilde(path: Path) -> str:
    home = str(paths.home())
    return "~" + str(path)[len(home):] if str(path).startswith(home) else str(path)


# --- me.md ---

def _split(text: str) -> tuple[list[str], list[str] | None, list[str]]:
    lines = text.splitlines()
    marks = [l.strip() for l in lines]
    if START in marks and END in marks[marks.index(START):]:
        s = marks.index(START)
        e = marks.index(END, s)
        return lines[:s], lines[s + 1:e], lines[e + 1:]
    return lines, None, []


def _match_line(pref: dict, line: str) -> tuple[str, str] | None:
    s = line.strip()
    templates = pref["target"]["me_md"]
    free = [o for o in pref["options"] if o.get("free_text")]
    for opt in pref["options"]:
        if not opt.get("free_text") and s == templates[opt["value"]]:
            return opt["value"], ""
    for opt in free:
        pattern = re.escape(templates[opt["value"]]).replace(re.escape("{text}"), "(.+)")
        m = re.fullmatch(pattern, s)
        if m:
            return opt["value"], m.group(1)
    for rule in pref.get("detect", {}).get("me_md", []):
        if re.search(rule["pattern"], s, re.I):
            return rule["value"], ""
    return None


def _me_states(prefs: list[dict], text: str) -> dict[str, State]:
    before, block, after = _split(text)
    me_prefs = [p for p in prefs if "me_md" in p["target"]]
    states: dict[str, State] = {}
    segments = [("block", block or [], "me.md")] + [(seg, lines, "me.md, free text") for seg, lines in (("before", before), ("after", after))]
    for seg, lines, source in segments:
        for i, line in enumerate(lines):
            if not line.strip():
                continue
            for p in me_prefs:
                hit = _match_line(p, line)
                if hit is None:
                    continue
                st = states.get(p["id"])
                if st is None:
                    st = states[p["id"]] = State(value=hit[0], text=hit[1], source=source)
                if (seg == "block") == (st.source == "me.md"):  # free text never adds to a block answer
                    st.lines.append((seg, i, line))
                break  # one line expresses one preference
    return states


def _render_me(prefs: list[dict], text: str, states: dict[str, State], changes: dict) -> str:
    before, block, after = _split(text)
    claimed = {(seg, i) for st in states.values() for seg, i, _ in st.lines}
    new_block = []
    for p in prefs:
        if "me_md" not in p["target"]:
            continue
        if p["id"] in changes:
            value, free = changes[p["id"]]
            new_block.append(p["target"]["me_md"][value].replace("{text}", free))
        elif p["id"] in states:
            new_block += [line for _, _, line in states[p["id"]].lines]
    new_block += [l for i, l in enumerate(block or []) if l.strip() and ("block", i) not in claimed]  # lines we do not know: kept
    keep_before = [l for i, l in enumerate(before) if ("before", i) not in claimed]
    keep_after = [l for i, l in enumerate(after) if ("after", i) not in claimed]
    if block is None and not new_block:
        return text
    if block is None:
        while keep_before and not keep_before[-1].strip():
            keep_before.pop()
        out = keep_before + ([""] if keep_before else []) + [START, *new_block, END]
    else:
        out = keep_before + [START, *new_block, END] + keep_after
    return "\n".join(out) + "\n"


def _write_me(prefs: list[dict], states: dict[str, State], changes: dict, bk: Backup) -> bool:
    """Writes the managed block; free-text lines equivalent to a preference move into it."""
    path = _me_path()
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    new = _render_me(prefs, text, states, changes)
    if new == text:
        return False
    if path.exists():
        bk.save_copy(path, "personal me.md before preferences")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        bk.record_created(path, "created personal me.md")
    write_atomic(path, new)
    return True


# --- settings ---

def _setting_state(pref: dict, sources: list[tuple[str, dict]]) -> State:
    target = pref["target"]
    key = _key(target["setting"])
    for source, data in sources:
        now = get_path(data, key)
        if now is not MISSING:
            for opt, wanted in target.get("values", {}).items():
                if wanted is not None and now == wanted:
                    return State(value=opt, source=source)
        for rule in pref.get("detect", {}).get("settings", []):
            found = get_path(data, _key(rule["key"]))
            if found is MISSING:
                continue
            if rule.get("present") or ("equals" in rule and found == rule["equals"]):
                return State(value=rule["value"], source=source)
        if now is not MISSING:
            return State(raw=now, source=source)
    return State()


def _remove_path(data: dict, key: tuple) -> None:
    chain, node = [], data
    for part in key[:-1]:
        if not isinstance(node.get(part), dict):
            return
        chain.append((node, part))
        node = node[part]
    node.pop(key[-1], None)
    for parent, part in reversed(chain):
        if parent[part] == {}:
            del parent[part]


def _write_settings(changes: dict[str, object], bk: Backup) -> bool:
    """changes: dotted key -> value (None removes it). A value equal to the kit default needs no override."""
    path = _settings_path()
    data = load_json(path)
    new = copy.deepcopy(data)
    kit = _kit_settings()
    for dotted, value in changes.items():
        key = _key(dotted)
        if value is None or get_path(kit, key) == value:
            _remove_path(new, key)
        else:
            node = new
            for part in key[:-1]:
                if not isinstance(node.get(part), dict):
                    node[part] = {}
                node = node[part]
            node[key[-1]] = copy.deepcopy(value)
    if new == data:
        return False
    if path.exists():
        bk.save_copy(path, "personal settings.json before preferences")
    else:
        bk.record_created(path, "created personal settings.json")
    save_json(path, new)
    return True


# --- detection ---

def detect() -> dict[str, State]:
    from .adopt import prefill_settings

    prefs = load()
    me = _me_path()
    states = _me_states(prefs, me.read_text(encoding="utf-8") if me.exists() else "")
    sources = [("personal settings", load_json(_settings_path())), ("kit default", _kit_settings()),
               ("existing settings", prefill_settings())]
    for p in prefs:
        if "setting" in p["target"]:
            states[p["id"]] = _setting_state(p, sources)
        else:
            states.setdefault(p["id"], State())
    return states


def describe(state: State) -> str:
    if state.value is not None:
        shown = f"{state.value}:{state.text}" if state.text else state.value
        return f"{shown} ({state.source})"
    if isinstance(state.raw, list):
        return f"set, {len(state.raw)} entries ({state.source})"
    if state.raw is not None:
        raw = json.dumps(state.raw, ensure_ascii=False)
        return f"custom {raw[:50] + '…' if len(raw) > 50 else raw} ({state.source})"
    return "not set"


def _options_hint(pref: dict) -> str:
    return " | ".join(o["value"] + (":<text>" if o.get("free_text") else "") for o in pref["options"])


def parse_choice(pref: dict, raw: str, ask: Ask | None = None) -> tuple[str, str]:
    raw = raw.strip()
    options = pref["options"]
    name, _, free = raw.partition(":")
    if raw.isdigit() and 1 <= int(raw) <= len(options):
        name, free = options[int(raw) - 1]["value"], ""
    opt = next((o for o in options if o["value"].lower() == name.strip().lower()), None)
    if opt is None:
        raise ValueError(f"'{raw}' is not an option of {pref['id']} (options: {_options_hint(pref)})")
    if opt.get("free_text"):
        free = free.strip() or (ask("  your text: ").strip() if ask else "")
        if not free:
            raise ValueError(f"{pref['id']} {opt['value']} needs a text, e.g. {opt['value']}:French")
        return opt["value"], free
    return opt["value"], ""


# --- automode generator ---

def _repos(folder: Path) -> list[Path]:
    found = []
    try:
        children = sorted(d for d in folder.iterdir() if d.is_dir() and not d.name.startswith("."))
    except OSError:
        return []
    for d in children:
        if (d / ".git").exists():
            found.append(d)
            continue
        try:
            found += sorted(e for e in d.iterdir() if e.is_dir() and (e / ".git").exists())
        except OSError:
            pass
    return found


def scan_repos(folder: Path) -> tuple[dict[str, int], list[str]]:
    """Origin owners (host/owner -> repo count, most repos first) and stacks of the git repos under folder."""
    counts: dict[str, int] = {}
    stacks: list[str] = []
    for repo in _repos(folder):
        res = runner.run(["git", "-C", str(repo), "remote", "get-url", "origin"], timeout=20)
        m = REMOTE.match(res.stdout.strip()) if res.ok else None
        if m:
            owner = f"{m.group(1)}/{m.group(2)}"
            counts[owner] = counts.get(owner, 0) + 1
        for marker, stack in STACKS:
            if (repo / marker).exists() and stack not in stacks:
                stacks.append(stack)
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].lower()))), stacks


def generate_automode(folder: Path, owners: list[str] | None = None,
                      scanned: tuple[dict[str, int], list[str]] | None = None) -> list[str]:
    """owners: the user's own accounts/orgs (host/owner); None = every origin owner found."""
    counts, stacks = scanned if scanned is not None else scan_repos(folder)
    owners = list(counts) if owners is None else owners
    where = _tilde(folder)
    if owners:
        source = (f"**Source control**: my own repos on {', '.join(o + '/*' for o in owners)} — pushing a repo's own "
                  "work to its own origin is routine; other people's repos and orgs are outside the trust boundary")
    else:
        source = f"**Source control**: no git remotes found under {where} — treat every remote as outside the trust boundary"
    tools = ["git"] + (["gh"] if any(o.startswith("github.com/") for o in owners) else []) + stacks
    return [
        "### Org-wide",
        "**Repository visibility**: mixed — never commit secrets, .env contents, personal data or credentials "
        "to any repo regardless of visibility",
        "**Internal sharing / snippet hosting**: None configured — treat public paste/gist services as outside the trust boundary",
        "**Secrets management**: local .env files and ~/.config/loadout/secrets.env",
        source,
        "**Sensitive data locations & audiences**: any .env / secrets.env, ~/.claude.json, credentials files, and any "
        "file or store holding personal data, credentials or similarly sensitive material",
        "**Sensitive remote targets**: any namespace, host, or container whose name carries `prod` or `production` "
        "as a whole word or name segment (hyphen/underscore/dot-delimited — e.g. matches `prod-db`, not `producer`)",
        "**Protected IaC scopes**: IAM, RBAC, networking, quota, and node-pool resources; anything whose name or tag "
        "carries `prod` or `production` as a whole word or name segment",
        "### User-specific",
        f"**Primary use of Claude Code**: software development across my projects in {where}",
        f"**Routine**: under {where}/<project>/: {', '.join(tools)} and the project's own test/build commands",
    ]


def _run_generator(pref: dict, ask: Ask, bk: Backup) -> list[str]:
    default = paths.home() / "Documents" / "Code"
    answer = ask(f"  Code folder to scan for your git repos [{_tilde(default)}]: ").strip()
    folder = Path(answer).expanduser() if answer else default
    if not folder.is_dir():
        return [f"{pref['id']}: {folder} is not a folder; nothing generated"]
    scanned = scan_repos(folder)
    counts = scanned[0]
    owners: list[str] = []
    if counts:
        print("  origin owners found: " + ", ".join(f"{o} ({n})" for o, n in counts.items()))
        top = max(counts.values())
        mine = [o for o, n in counts.items() if n == top]
        answer = ask(f"  Which are your own accounts or orgs? Only these are trusted (comma-separated) [{', '.join(mine)}]: ").strip()
        picked = [a.strip() for a in answer.split(",") if a.strip()] if answer else mine
        owners = [next((o for o in counts if o.lower() == p.lower() or o.split("/", 1)[1].lower() == p.lower()), p)
                  for p in picked]
    lines = generate_automode(folder, owners, scanned)
    print(f"\nDraft auto mode environment (settings {pref['target']['setting']}):")
    for line in lines:
        print(f"  {line}")
    if not ui.confirm(ask, "Save this auto mode environment to your personal layer? [y/N] "):
        return [f"{pref['id']}: draft not saved"]
    _write_settings({pref["target"]["setting"]: lines}, bk)
    return [f"{pref['id']}: auto mode environment saved"]


# --- front-ends ---

def _apply(prefs: list[dict], states: dict[str, State], answers: dict[str, tuple[str, str]], bk: Backup,
           migrate: bool) -> list[str]:
    me_changes, setting_changes, out = {}, {}, []
    for pid, (value, free) in answers.items():
        pref = by_id_in(prefs, pid)
        st = states[pid]
        if st.value == value and st.text == free:
            continue
        out.append(f"{pid}: {value}{':' + free if free else ''}")
        if "me_md" in pref["target"]:
            me_changes[pid] = (value, free)
        else:
            setting_changes[pref["target"]["setting"]] = pref["target"]["values"][value]
    if me_changes or migrate:
        _write_me(prefs, states, me_changes, bk)
    if setting_changes:
        _write_settings(setting_changes, bk)
    return out


def set_choice(pid: str, raw: str, ask: Ask = lambda q: "", interactive: bool = False, bk: Backup | None = None) -> list[str]:
    """Non-interactive engine: `loadout configure set pref-choice <id> <value>`."""
    bk = bk if bk is not None else Backup(description="configure preferences")
    pref = by_id(pid)
    value, free = parse_choice(pref, raw)
    if pref.get("generator"):
        if value == "skip":
            return [f"{pid}: skip (nothing changed)"]
        if not interactive:
            raise ValueError(f"{pid} {value} shows a draft that needs your confirmation: "
                             "run `loadout configure prefs` in a terminal")
        return _run_generator(pref, ask, bk)
    prefs = load()
    states = detect()
    if states[pid].value == value and states[pid].text == free:
        return [f"{pid}: already {value}"]
    return _apply(prefs, states, {pid: (value, free)}, bk, migrate="me_md" in pref["target"])


def _ask_one(ask: Ask, pref: dict, state: State, fill_defaults: bool) -> tuple[str, str] | None:
    """None = keep the current state."""
    take_default = fill_defaults and not state.is_set
    current = pref["default"] if take_default else ("keep " + describe(state) if state.is_set else "keep: not set")
    print(f"\n{pref['question']}")
    for i, o in enumerate(pref["options"], 1):
        print(f"  {i}. {o['value']} — {o['label']}{' (default)' if o['value'] == pref['default'] else ''}")
    for _ in range(3):
        answer = ask(f"{pref['id']} [{current}]: ").strip()
        if not answer:
            return (pref["default"], "") if take_default else None
        try:
            return parse_choice(pref, answer, ask)
        except ValueError as exc:
            print(f"  {exc}")
    return None


def ask_all(ask: Ask, fill_defaults: bool, interactive: bool, bk: Backup | None = None) -> list[str]:
    """All questions; Enter keeps the current or detected answer.

    fill_defaults (first run): an answer that is not set yet takes the default. Without a terminal
    nothing is asked: unset answers take the default (fill_defaults) and automode is skipped.
    """
    bk = bk if bk is not None else Backup(description="configure preferences")
    prefs = load()
    states = detect()
    answers, out = {}, []
    for pref in prefs:
        st = states[pref["id"]]
        if interactive:
            answer = _ask_one(ask, pref, st, fill_defaults)
        else:
            answer = (pref["default"], "") if fill_defaults and not st.is_set else None
        if answer is None:
            continue
        if pref.get("generator"):
            if answer[0] != "skip" and interactive:
                out += _run_generator(pref, ask, bk)
            continue
        answers[pref["id"]] = answer
    return _apply(prefs, states, answers, bk, migrate=True) + out


def show_lines() -> list[str]:
    states = detect()
    lines = ["Preferences (change one with: loadout configure set pref-choice <id> <value>)"]
    for pref in load():
        lines.append(f"{describe(states[pref['id']])}  {pref['question']}  — id: pref-choice {pref['id']}")
        lines.append(f"      options: {_options_hint(pref)} (default {pref['default']})")
    return lines


def owned_setting_keys() -> set[str]:
    return {p["target"]["setting"].split(".")[0] for p in load() if "setting" in p["target"]}
