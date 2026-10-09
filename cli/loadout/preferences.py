"""Structured working preferences (preferences.json at the kit root).

Answers live in the personal layer only: lines in a managed block of rules/me.md, or keys in
settings.json (a preference may have both). Existing answers are detected (managed block, free
text in me.md, personal settings, kit defaults, then the user's own ~/.claude/settings.json via
adopt), so a re-run changes nothing the user already decided.

Free text in me.md is the user's: it is read to prefill answers, never moved or rewritten. Only a
line that equals a template line moves into the block, and only when the block is written anyway.
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
MAX_TEXT = 100
NOT_EFFECTIVE = "not effective"
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
    block: list = field(default_factory=list)   # me.md line indexes inside the managed block
    moves: list = field(default_factory=list)   # indexes of exact template lines outside the block
    stated: list = field(default_factory=list)  # indexes of free-text lines that state it (never touched)

    @property
    def is_set(self) -> bool:
        return self.value is not None or self.raw is not None


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


def _claude_settings_path() -> Path:
    return paths.claude_home() / "settings.json"


def _kit_settings() -> dict:
    return load_json(paths.kit_root() / "settings.base.json")


def _own_settings() -> dict:
    from .adopt import prefill_settings
    return prefill_settings()


def _key(dotted: str) -> tuple:
    return tuple(dotted.split("."))


def _tilde(path: Path) -> str:
    home = str(paths.home())
    return "~" + str(path)[len(home):] if str(path).startswith(home) else str(path)


def _norm(line: str) -> str:
    return " ".join(line.split())


# --- me.md ---

def _block_range(lines: list[str], strict: bool) -> tuple[int, int] | None:
    starts = [i for i, l in enumerate(lines) if l.strip() == START]
    ends = [i for i, l in enumerate(lines) if l.strip() == END]
    if not starts and not ends:
        return None
    if len(starts) == 1 and len(ends) == 1 and starts[0] < ends[0]:
        return starts[0], ends[0]
    if strict:
        raise ValueError(f"{_me_path()}: the loadout preference markers are unbalanced, duplicated or out of order "
                         f"(start at line(s) {[i + 1 for i in starts]}, end at line(s) {[i + 1 for i in ends]}); "
                         f"fix them by hand (one {START} followed by one {END}), nothing was written")
    return None


def _template_hit(pref: dict, norm: str) -> tuple[str, str] | None:
    templates = pref["target"]["me_md"]
    for opt in pref["options"]:
        tpl = templates.get(opt["value"])
        if tpl is None:
            continue
        if opt.get("free_text"):
            m = re.fullmatch(re.escape(_norm(tpl)).replace(re.escape("{text}"), "(.+)"), norm)
            if m:
                return opt["value"], m.group(1)
        elif norm == _norm(tpl):
            return opt["value"], ""
    return None


def _regex_hit(pref: dict, norm: str) -> str | None:
    for rule in pref.get("detect", {}).get("me_md", []):
        if re.search(rule["pattern"], norm, re.I):
            return rule["value"]
    return None


def _me_states(prefs: list[dict], lines: list[str]) -> dict[str, State]:
    rng = _block_range(lines, strict=False)
    inside = set(range(rng[0] + 1, rng[1])) if rng else set()
    markers = set(rng) if rng else set()
    me_prefs = [p for p in prefs if "me_md" in p["target"]]
    states: dict[str, State] = {}
    order = sorted(inside) + [i for i in range(len(lines)) if i not in inside and i not in markers]
    for i in order:
        norm = _norm(lines[i])
        if not norm:
            continue
        for p in me_prefs:
            hit = _template_hit(p, norm)
            stated = False
            if hit is None and i not in inside:
                value = _regex_hit(p, norm)
                hit, stated = ((value, ""), True) if value else (None, False)
            if hit is None:
                continue
            st = states.setdefault(p["id"], State())
            if not st.is_set:
                st.value, st.text = hit
                st.source = "me.md" if i in inside else "me.md, free text"
            if i in inside:
                st.block.append(i)
            elif stated or st.block:   # a template line repeating a block answer is left where it is
                st.stated.append(i)
            else:
                st.moves.append(i)
            break  # one line expresses one preference
    return states


def _read_me() -> tuple[str, list[str]]:
    path = _me_path()
    text = path.read_bytes().decode("utf-8") if path.exists() else ""  # bytes: keep CRLF visible
    return text, text.splitlines()


def _render_me(prefs: list[dict], lines: list[str], states: dict[str, State], changes: dict,
               remove: set[int]) -> tuple[list[str], list[tuple[int, str]]]:
    """New lines of me.md and the exact template lines moved into the block (1-based line, text)."""
    rng = _block_range(lines, strict=True)
    new_block, moved = [], []
    for p in prefs:
        if "me_md" not in p["target"]:
            continue
        st = states.get(p["id"], State())
        if p["id"] in changes:
            value, free = changes[p["id"]]
            tpl = p["target"]["me_md"].get(value)
            if tpl is not None:
                new_block.append(tpl.replace("{text}", free))
        else:
            new_block += [lines[i] for i in st.block]
            new_block += [_norm(lines[i]) for i in st.moves]
        moved += [(i + 1, lines[i].strip()) for i in st.moves]
    known = {i for st in states.values() for i in st.block}
    if rng:
        new_block += [lines[i] for i in range(rng[0] + 1, rng[1]) if lines[i].strip() and i not in known]
    drop = {i for st in states.values() for i in st.moves} | remove
    if rng:
        out = [l for i, l in enumerate(lines[:rng[0]]) if i not in drop]
        out += [START, *new_block, END]
        out += [l for i, l in enumerate(lines[rng[1] + 1:], rng[1] + 1) if i not in drop]
    elif new_block:
        out = [l for i, l in enumerate(lines) if i not in drop]
        while out and not out[-1].strip():
            out.pop()
        out += ([""] if out else []) + [START, *new_block, END]
    else:
        out = [l for i, l in enumerate(lines) if i not in drop]
    return out, moved


def _write_me(prefs, states, changes, bk: Backup, ask: Ask, interactive: bool) -> list[str]:
    text, lines = _read_me()
    _block_range(lines, strict=True)
    out, remove = [], set()
    for pid in changes:
        for i in states.get(pid, State()).stated:
            out.append(f"me.md line {i + 1} also states this ({pid}): {lines[i].strip()}")
            if interactive and ui.confirm(ask, f"  remove me.md line {i + 1}? (it is backed up) [y/N] "):
                remove.add(i)
                out.append(f"removed me.md line {i + 1}")
    new_lines, moved = _render_me(prefs, lines, states, changes, remove)
    newline = "\r\n" if "\r\n" in text else "\n"
    new = newline.join(new_lines) + newline
    if new == text:
        return out
    path = _me_path()
    if path.exists():
        bk.save_copy(path, "personal me.md before preferences")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        bk.record_created(path, "created personal me.md")
    write_atomic(path, new)
    out += [f"moved me.md line {n} into the managed preferences block: {line}" for n, line in moved]
    return out


# --- settings ---

def _rule_matches(rule: dict, found) -> bool:
    if rule.get("present"):
        return True
    if "equals" in rule:
        return found == rule["equals"]
    if "contains" in rule:
        return isinstance(found, dict) and all(found.get(k, MISSING) == v for k, v in rule["contains"].items())
    return False


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
            if found is not MISSING and _rule_matches(rule, found):
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


def _removes_key(pref: dict, value: str) -> bool:
    target = pref["target"]
    return "setting" in target and target.get("values", {}).get(value, MISSING) is None


def _blockers(pref: dict, value: str) -> list[tuple[Path, str, str]]:
    """For an answer that removes its key (e.g. ai_attribution on): keys the settings merge does not
    override that still state another answer, as (file, dotted key, their answer). Legacy keys (detect
    rules on other keys) count in the personal layer and in the user's own ~/.claude/settings.json;
    the target key itself only in the latter."""
    if not _removes_key(pref, value):
        return []
    target = pref["target"]["setting"]
    legacy = [r["key"] for r in pref.get("detect", {}).get("settings", []) if r["key"] != target]
    found = []
    for path, data, keys in ((_settings_path(), load_json(_settings_path()), legacy),
                             (_claude_settings_path(), _own_settings(), [target, *legacy])):
        for dotted in dict.fromkeys(keys):
            top = _key(dotted)[0]
            if get_path(data, _key(dotted)) is MISSING:
                continue
            st = _setting_state(pref, [("", {top: data[top]})])
            if st.value is not None and st.value != value:
                found.append((path, dotted, st.value))
    return found


def _remove_key_from(path: Path, dotted: str, bk: Backup) -> None:
    data = load_json(path)
    bk.save_copy(path, f"{path} before removing {dotted}")
    _remove_path(data, _key(dotted))
    save_json(path, data)


def _check_effective(pref: dict, value: str, bk: Backup, ask: Ask, interactive: bool) -> list[str]:
    out = []
    for path, dotted, theirs in _blockers(pref, value):
        if interactive and ui.confirm(ask, f"  {dotted} in {path} still sets {pref['id']} to {theirs}. "
                                           f"Remove it? (it is backed up) [y/N] "):
            _remove_key_from(path, dotted, bk)
            out.append(f"removed {dotted} from {path}")
    remaining = _blockers(pref, value)
    for path, dotted, theirs in remaining:
        out.append(f"{pref['id']}: {NOT_EFFECTIVE}: {dotted} in {path} still sets it to {theirs}; remove that key to finish")
    return out if remaining else out + [f"{pref['id']}: {value}"]


# --- detection ---

def detect() -> dict[str, State]:
    prefs = load()
    _, lines = _read_me()
    me = _me_states(prefs, lines)
    sources = [("personal settings", load_json(_settings_path())), ("kit default", _kit_settings()),
               ("existing settings", _own_settings())]
    states = {}
    for p in prefs:
        st = me.get(p["id"], State())
        if "setting" in p["target"]:
            setting = _setting_state(p, sources)
            if setting.is_set:
                setting.block, setting.moves, setting.stated = st.block, st.moves, st.stated
                st = setting
        states[p["id"]] = st
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


def _check_text(pref: dict, text: str) -> str:
    if "\n" in text or "\r" in text:
        raise ValueError(f"{pref['id']}: the text must be a single line")
    text = text.strip()
    if not text:
        raise ValueError(f"{pref['id']}: the text is empty")
    if "<!--" in text or "-->" in text:
        raise ValueError(f"{pref['id']}: the text must not contain HTML comment markers")
    if len(text) > MAX_TEXT:
        raise ValueError(f"{pref['id']}: the text is longer than {MAX_TEXT} characters")
    return text


def parse_choice(pref: dict, raw: str, ask: Ask | None = None) -> tuple[str, str]:
    options = pref["options"]
    name, sep, free = raw.partition(":")
    name = name.strip()
    if name.isdigit() and 1 <= int(name) <= len(options):
        name = options[int(name) - 1]["value"]
    opt = next((o for o in options if o["value"].lower() == name.lower()), None)
    if opt is None:
        raise ValueError(f"'{raw.strip()}' is not an option of {pref['id']} (options: {_options_hint(pref)})")
    if not opt.get("free_text"):
        if sep:
            raise ValueError(f"'{raw.strip()}': {opt['value']} takes no text (options: {_options_hint(pref)})")
        return opt["value"], ""
    if not sep and ask is not None:
        free = ask("  your text: ")
    elif not sep:
        raise ValueError(f"{pref['id']} {opt['value']} needs a text, e.g. {opt['value']}:French")
    return opt["value"], _check_text(pref, free)


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


def _pick_owners(ask: Ask, counts: dict[str, int]) -> list[str] | None:
    """The owners the user calls their own. One clear favourite is preselected; a tie needs an explicit choice."""
    print("  origin owners found: " + ", ".join(f"{o} ({n})" for o, n in counts.items()))
    top = max(counts.values())
    mine = [o for o, n in counts.items() if n == top]
    default = mine[0] if len(mine) == 1 else None
    hint = f"[{default}]" if default else "(several have the same count: type yours)"
    for _ in range(3):
        answer = ask(f"  Which are your own accounts or orgs? Only these are trusted (comma-separated) {hint}: ").strip()
        if not answer and default is None:
            print("  type at least one owner, e.g. " + mine[0])
            continue
        picked = [a.strip() for a in answer.split(",") if a.strip()] if answer else [default]
        return [next((o for o in counts if o.lower() == p.lower() or o.split("/", 1)[1].lower() == p.lower()), p)
                for p in picked]
    return None


def _run_generator(pref: dict, ask: Ask, bk: Backup) -> list[str]:
    default = paths.home() / "Documents" / "Code"
    answer = ask(f"  Code folder to scan for your git repos [{_tilde(default)}]: ").strip()
    folder = Path(answer).expanduser() if answer else default
    if not folder.is_dir():
        return [f"{pref['id']}: {folder} is not a folder; nothing generated"]
    scanned = scan_repos(folder)
    owners: list[str] = []
    if scanned[0]:
        picked = _pick_owners(ask, scanned[0])
        if picked is None:
            return [f"{pref['id']}: no owner chosen; nothing generated"]
        owners = picked
    lines = generate_automode(folder, owners, scanned)
    setting = pref["target"]["setting"]
    print(f"\nDraft auto mode environment (settings {setting}):")
    for line in lines:
        print(f"  {line}")
    current = get_path(load_json(_settings_path()), _key(setting))
    own = get_path(_own_settings(), _key(setting))
    if isinstance(current, list):
        question = f"This REPLACES your current {setting} ({len(current)} entries) in {_settings_path()}. Save? [y/N] "
    elif isinstance(own, list):
        question = (f"Save to your personal layer? Your own {setting} in {_claude_settings_path()} ({len(own)} entries) "
                    "is kept and these lines are added to it. [y/N] ")
    else:
        question = "Save this auto mode environment to your personal layer? [y/N] "
    if not ui.confirm(ask, question):
        return [f"{pref['id']}: draft not saved"]
    _write_settings({setting: lines}, bk)
    return [f"{pref['id']}: auto mode environment saved"]


# --- front-ends ---

def _apply(prefs: list[dict], states: dict[str, State], answers: dict[str, tuple[str, str]], bk: Backup,
           ask: Ask, interactive: bool) -> list[str]:
    me_changes, setting_changes, changed, out = {}, {}, [], []
    for pid, (value, free) in answers.items():
        pref = by_id_in(prefs, pid)
        st = states[pid]
        if st.value == value and st.text == free:
            continue
        changed.append((pref, value, free))
        if "me_md" in pref["target"]:
            me_changes[pid] = (value, free)
        if "setting" in pref["target"]:
            setting_changes[pref["target"]["setting"]] = pref["target"]["values"][value]
    if me_changes:
        _block_range(_read_me()[1], strict=True)  # refuse before anything is written
        out += _write_me(prefs, states, me_changes, bk, ask, interactive)
    if setting_changes:
        _write_settings(setting_changes, bk)
    for pref, value, free in changed:
        if _removes_key(pref, value):
            out += _check_effective(pref, value, bk, ask, interactive)
        else:
            out.append(f"{pref['id']}: {value}{':' + free if free else ''}")
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
    states = detect()
    if states[pid].value == value and states[pid].text == free:
        return [f"{pid}: already {value}"]
    return _apply(load(), states, {pid: (value, free)}, bk, ask, interactive)


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
    return _apply(prefs, states, answers, bk, ask, interactive) + out


def show_lines() -> list[str]:
    states = detect()
    lines = ["Preferences (change one with: loadout configure set pref-choice <id> <value>)"]
    for pref in load():
        lines.append(f"{describe(states[pref['id']])}  {pref['question']}  — id: pref-choice {pref['id']}")
        lines.append(f"      options: {_options_hint(pref)} (default {pref['default']})")
    return lines


def without_owned_settings(data: dict) -> dict:
    """data minus the exact keys a preference writes (e.g. autoMode.environment, not all of autoMode)."""
    rest = copy.deepcopy(data)
    for pref in load():
        if "setting" in pref["target"]:
            _remove_path(rest, _key(pref["target"]["setting"]))
    return rest
