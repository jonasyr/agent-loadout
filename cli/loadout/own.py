"""Your own tools: items loadout does not manage. Record them in the personal layer (global), in a
personal profile (project), leave them on this machine, or remove them.
Spec: docs/superpowers/specs/2026-10-10-adopt-own-tools-design.md
"""
from __future__ import annotations

import filecmp
import hashlib
import json
import os
import re
import shlex
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable
from urllib.parse import parse_qsl, urlsplit

from . import paths, personal_mcp, secrets
from .jsonio import InvalidJSON, load_json, save_json
from .secrets import redact

if TYPE_CHECKING:
    from .inventory import Item, Verdict

KINDS = ("plugin", "marketplace", "mcp", "skill", "hook")
PERSONAL_REASON = "From your personal layer."
LEFT_REASON = "Left on this machine (your choice); change it with `loadout configure set own`."
OWN_REASON = "Not managed by loadout. Choose: global, project, leave or remove."


def decision_key(item: Item) -> str:
    """Hooks are keyed by a hash of their command, so the decisions file never holds a command line."""
    if item.kind == "hook":
        digest = hashlib.sha256(str(item.detail).encode("utf-8")).hexdigest()[:16]
        return f"hook:{item.name}:{digest}"
    return f"{item.kind}:{item.name}"


def _keys(item: Item) -> list[str]:
    """The current key plus the legacy raw-command key for hooks (decisions written before the hash)."""
    keys = [decision_key(item)]
    if item.kind == "hook":
        keys.append(f"hook:{item.name}:{item.detail}")
    return keys


def _decisions_path():
    return paths.state_dir() / "own-decisions.json"


def decisions() -> dict[str, str]:
    return load_json(_decisions_path())


def decided(data: dict[str, str], item: Item) -> str | None:
    """The decision recorded for this item in `data`, under its current or legacy key."""
    return next((data[k] for k in _keys(item) if k in data), None)


def backup_decisions(bk) -> None:
    """Record the decisions file in the backup (copy if it exists, else mark it created) before a write."""
    path = _decisions_path()
    if path.exists():
        bk.save_copy(path, "own-decisions.json before change")
    else:
        bk.record_created(path, "own-decisions.json")


def remember_leave(item: Item, bk=None) -> None:
    if bk is not None:
        backup_decisions(bk)
    data = decisions()
    for key in _keys(item)[1:]:
        data.pop(key, None)
    data[decision_key(item)] = "leave"
    save_json(_decisions_path(), data)


def forget(item: Item, bk=None) -> None:
    data = decisions()
    if any(k in data for k in _keys(item)):
        if bk is not None:
            backup_decisions(bk)
        for key in _keys(item):
            data.pop(key, None)
        save_json(_decisions_path(), data)


def is_left(item: Item) -> bool:
    return decided(decisions(), item) == "leave"


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
    """What the personal layer already holds: {kind: {name: reason}} (hooks keyed by command).
    Personal profile members are kept apart under "_profile" and "_disabled" (plugins turned off in
    ~/.claude/settings.json): a profile only explains an item that is inactive globally."""
    root = paths.personal_root()
    settings = load_json(root / "settings.json")
    index = {k: {} for k in KINDS}
    index["_profile"] = {k: {} for k in KINDS}
    enabled = load_json(paths.claude_home() / "settings.json").get("enabledPlugins")
    index["_disabled"] = {pid for pid, on in (enabled if isinstance(enabled, dict) else {}).items() if on is False}
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
            index["_profile"]["plugin"].setdefault(pid, why)
        for name in (prof.get("mcp") or {}).get("mcpServers") or {}:
            index["_profile"]["mcp"].setdefault(name, why)
        for name in prof.get("skills") or []:
            index["_profile"]["skill"].setdefault(name, why)
        for cmd in _hook_commands(prof.get("settings") or {}):
            index["_profile"]["hook"].setdefault(cmd, why)
    return index


def in_personal_layer(item: Item, index: dict) -> str | None:
    """Why the personal layer explains this item, or None. Global membership (settings.json, mcp.json,
    skills/, skills.json, hooks) always counts. Profile membership counts only for a plugin that is disabled
    globally: an MCP server from ~/.claude.json, a skill in ~/.claude/skills and a hook in settings.json are
    by definition still active, so a profile does not explain them (a failed removal must stay visible)."""
    if item.kind not in KINDS:
        return None
    if item.kind == "hook":
        if not isinstance(item.detail, str):
            return None
        key = item.detail
    else:
        key = item.name
    if key in index[item.kind]:
        return index[item.kind][key]
    if item.kind == "plugin" and key in index.get("_disabled", ()):
        return index.get("_profile", {}).get("plugin", {}).get(key)
    return None


def unmanaged(verdicts: list[Verdict], include_left: bool = False) -> list[Verdict]:
    return [v for v in verdicts if v.action == "own" or (include_left and v.action == "keep" and v.reason == LEFT_REASON)]


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
    _refuse_if_secret(f"marketplace {name}", json.dumps(src))
    for value in src.values():
        if isinstance(value, str) and "?" in value:
            if any(secrets.looks_secret(k, v, keyed_arg=True) for k, v in parse_qsl(urlsplit(value).query)):
                raise Collision(f"marketplace {name} looks like it contains a secret in its URL; "
                                f"remove it from the source, then try again")
    markets = data.setdefault("extraKnownMarketplaces", {})
    have = markets.get(name)
    if have is not None and (not isinstance(have, dict) or have.get("source") != src):
        raise Collision(f"marketplace {name} already exists with a different source")
    markets[name] = {"source": src}


def _secret_free(name: str, cfg: dict) -> tuple[dict, list[str]]:
    """The config with secrets as ${VAR}, plus the secrets.env lines to append. Refuses unfixable secrets."""
    url = cfg.get("url")
    if isinstance(url, str) and any(secrets.high_entropy(seg) for seg in urlsplit(url).path.split("/")):
        raise Collision(f"mcp {name}: its URL path looks like it contains a token; "
                        f"move it to {paths.secrets_file()} by hand first")
    found = secrets.scan({"mcpServers": {name: cfg}})
    blocked = [f for f in found if not f.fixable or "\n" in f.value or "\r" in f.value]
    if blocked:
        raise Collision(f"mcp {name}: a secret in {blocked[0].field} cannot be moved automatically; "
                        f"move it to {paths.secrets_file()} by hand first")
    new, lines, _ = secrets.rewrite(name, cfg, found, secrets.load_env(paths.secrets_file()))
    return new, lines


def _refuse_if_secret(label: str, text: str) -> None:
    if secrets.redact(text) != text:
        raise Collision(f"{label} looks like it contains a secret; move it to secrets.env and use ${{VAR}}, then try again")


def _decode(data: bytes) -> str:
    """Text of a file for the secret scan: UTF-16 with a UTF-16 BOM or when NUL bytes are over 30% of the
    first 4 KB, else UTF-8 (binary files are scanned by their text runs)."""
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16", errors="ignore")
    head = data[:4096]
    if head and head.count(0) / len(head) > 0.3:
        big_endian = head[0::2].count(0) > head[1::2].count(0)
        return data.decode("utf-16-be" if big_endian else "utf-16-le", errors="ignore").replace("\0", "\n")
    return data.decode("utf-8", errors="ignore").replace("\0", "\n")


def _scan_tree(src: Path, label: str) -> None:
    """Fail closed: every regular file is scanned (binary files too, by their text runs); unreadable files,
    private files (keys, credentials) and git checkouts refuse."""
    for f in sorted(src.rglob("*")):
        rel = f.relative_to(src)
        if ".git" in rel.parts:
            raise Collision(f"skill {src.name} contains a git checkout (.git); copy it without .git first")
        if secrets.private_path(rel):
            raise Collision(f"skill {src.name} contains a private file ({rel}); not recorded")
        if f.is_symlink() or not f.is_file():
            continue  # symlinks are copied as links (symlinks=True), never their target's content
        try:
            data = f.read_bytes()
        except OSError:
            raise Collision(f"{label} ({rel}) could not be read, so it was not checked for secrets") from None
        _refuse_if_secret(f"{label} ({rel})", _decode(data))


def _same_tree(a: Path, b: Path) -> bool:
    cmp = filecmp.dircmp(a, b)
    if cmp.left_only or cmp.right_only or cmp.funny_files:
        return False
    _, mismatch, errors = filecmp.cmpfiles(a, b, cmp.common_files, shallow=False)
    return not mismatch and not errors and all(_same_tree(a / d, b / d) for d in cmp.common_dirs)


def _copy_tree(src: Path, dest: Path, bk, label: str) -> None:
    _scan_tree(src, label)
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


_INTERPRETER = re.compile(r"^(?:sh|bash|zsh|dash|fish|python|python3(?:\.\d+)?|node|deno|bun|ruby|perl|pwsh|powershell)"
                          r"(?:\.exe)?$", re.I)
_ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_SCRIPT_EXT = {".sh", ".bash", ".zsh", ".py", ".js", ".mjs", ".ts", ".rb", ".pl", ".ps1", ".fish"}


def _script_index(tokens: list[str]) -> int | None:
    """Index of the token that is the hook's script: the first token, or the first one after
    `env [flags] [VAR=val]` and a known interpreter (and its flags)."""
    i = 0
    while i < len(tokens):
        base = re.split(r"[\\/]", tokens[i])[-1]
        if base.lower() in ("env", "env.exe"):
            i += 1
            while i < len(tokens) and (tokens[i].startswith("-") or _ENV_ASSIGN.match(tokens[i])):
                i += 1
            continue
        if _INTERPRETER.match(base):
            i += 1
            while i < len(tokens) and tokens[i].startswith("-"):
                i += 1
            if i < len(tokens) and base.lower() in ("deno", "bun") and tokens[i] == "run":
                i += 1
            return i if i < len(tokens) else None
        return i
    return None


def _expand(tok: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(tok)))


def _private_token(tok: str) -> Path | None:
    """The denylisted path a token names (also the value of opt=path), or None. Existence does not matter."""
    for cand in (tok, tok.split("=", 1)[1] if "=" in tok else ""):
        if not cand or not ("/" in cand or "\\" in cand or cand.startswith(("~", ".", "$"))):
            continue
        p = _expand(cand)
        home = paths.home()
        if secrets.private_path(p, home) or (p.is_absolute() and secrets.private_path(p.resolve(), home.resolve())):
            return p
    return None


_SHELL_SPLIT = re.compile(r"[\s'\"`;|&<>(){}=,]+")
_SHELL_META = re.compile(r"[$`;&|<>(){}*?\[\]\n\r\\]")
COMPLEX_NOTE = ("note: complex shell command recorded as is; only simple `<interpreter> <script> args` "
                "commands get their script copied")


def _private_in_raw(text: str) -> Path | None:
    """A denylisted path anywhere in the raw text, as written and with ~ and $HOME expanded. Claude Code runs the
    command through `sh -c`, so this does not rely on shlex seeing the same words as the shell."""
    home = str(paths.home())
    expanded = re.sub(r"(?<![\w/])~(?=/|$)", home, text)
    expanded = re.sub(r"\$\{?HOME\}?", home, expanded)
    for form in (text, expanded):
        for piece in _SHELL_SPLIT.split(form):
            if (bad := _private_token(piece)) is not None:
                return bad
    return None


def _is_script(p: Path) -> bool:
    if p.suffix.lower() in _SCRIPT_EXT or os.access(p, os.X_OK):
        return True
    try:
        with p.open("rb") as fh:
            return fh.read(2) == b"#!"
    except OSError:
        return False


def _portable_hook(hook: dict, bk, name: str) -> tuple[dict, list[str]]:
    """Copy the local script the hook runs into <personal>/hooks/ and point the command at the linked copy.
    Only the script itself is copied; a private file named anywhere in the command refuses the hook."""
    cmd = hook.get("command")
    args = hook.get("args")
    words = ([cmd] if isinstance(cmd, str) else []) + [a for a in (args if isinstance(args, list) else []) if isinstance(a, str)]
    for tok in words:
        if (bad := _private_in_raw(tok)) is not None:
            raise Collision(f"hook {name} refers to a private file ({bad}); not recorded")
    if "args" in hook:
        return hook, ["note: exec form hook (args) recorded as is; it works only where its paths exist"]
    if not isinstance(cmd, str):
        return hook, []
    try:
        tokens = shlex.split(cmd)
    except ValueError:
        return hook, []
    for tok in tokens:
        if (bad := _private_token(tok)) is not None:
            raise Collision(f"hook {name} refers to a private file ({bad}); not recorded")
    script_at = _script_index(tokens)
    notes: list[str] = []
    copy: tuple[str, Path] | None = None
    for i, tok in enumerate(tokens):
        p = _expand(tok)
        if not p.is_absolute() or not p.is_file():
            continue
        if _under(p, paths.kit_root()) or _under(p, paths.personal_root()):
            continue
        if script_at is not None and i < script_at:
            continue  # env / interpreter
        if not _under(p, paths.home()):
            notes.append(f"note: {tok} is outside your home folder; the hook works only where it exists")
        elif i == script_at and _is_script(p) and copy is None:
            copy = (tok, p)
        else:
            notes.append(f"note: {p} is a file under your home folder that is not the hook's script; recorded as is")
    if copy is None:
        _refuse_if_secret("hook command", cmd)
        return hook, [COMPLEX_NOTE] if _SHELL_META.search(cmd) else notes
    tok, p = copy
    raw = next((r for r in (f"'{tok}'", f'"{tok}"', tok) if r in cmd), None)
    if raw is None:
        _refuse_if_secret("hook command", cmd)
        return hook, [f"note: could not rewrite the path in the command; edit it in {_personal_settings()}", *notes]
    if _SHELL_META.search(cmd.replace(raw, "", 1)):
        _refuse_if_secret("hook command", cmd)
        return hook, [COMPLEX_NOTE]
    _refuse_if_secret(f"hook script {p.name}", _decode(p.read_bytes()))
    dest = paths.personal_root() / "hooks" / p.name
    if dest.exists() and not filecmp.cmp(dest, p, shallow=False):
        raise Collision(f"hook script {p.name} already exists in {dest.parent} with different content")
    cmd = cmd.replace(raw, f'"$HOME/.claude/hooks/personal/{p.name}"', 1)
    _refuse_if_secret("hook command", cmd)
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        bk.record_created(dest, f"hook script {p.name} copied into the personal layer")
        shutil.copy2(p, dest)
    return {**hook, "command": cmd}, [f"hook script {p.name} copied to {dest} (only this file; copy files it needs "
                                      f"next to it by hand)", *notes]


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
    hook, notes = _portable_hook(group["hooks"][hi], bk, v.item.name)
    base = {k: val for k, val in group.items() if k != "hooks"}
    out = {**base, "hooks": [hook]}
    _refuse_if_secret(f"hook {v.item.name}", json.dumps(out))  # every branch: exec form, unparsable, other fields
    return event, out, notes


def _regroup_machine_hook(v: Verdict, event: str, group: dict, bk) -> list[str]:
    """Take the hook out of its group in ~/.claude/settings.json and add it back as exactly `group`,
    so the list-union merge with the personal layer does not run it twice."""
    path = paths.claude_home() / "settings.json"
    matcher = v.item.name[len(event) + 1:]

    gone = [False]

    def change(data):
        found = _find_hook(data, event, matcher, v.item.detail)
        if found is None:
            gone[0] = True
            return
        groups = data["hooks"][event]
        gi, hi = found
        rest = [h for i, h in enumerate(groups[gi]["hooks"]) if i != hi]
        if rest:
            groups[gi] = {**groups[gi], "hooks": rest}
        else:
            groups.pop(gi)
        if group not in groups:
            groups.append(group)

    _edit_json(path, bk, f"settings.json before regrouping hook {v.item.name}", change)
    if gone[0]:
        return [f"hook {v.item.name}: changed in ~/.claude/settings.json since the scan; left as is"]
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
    _refuse_if_secret(f"mcp {name}", json.dumps(new))
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
        target = os.path.normpath(src.parent / os.readlink(src))
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


def options(item: Item) -> list[str]:
    """Choices that apply to this item, in prompt order."""
    if item.kind == "mcp" and item.location != "~/.claude.json":
        return ["leave", "remove"]
    if item.kind == "marketplace" or (item.kind == "skill" and Path(item.location).is_symlink()):
        return ["global", "leave", "remove"]
    return ["global", "project", "leave", "remove"]


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
    """Record an item in a personal profile (personal layer only; the machine step is the removal in adopt)."""
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
            _refuse_if_secret(f"mcp {item.name}", json.dumps(new))

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
    pairs, seen = [], set()
    for kind, name, choice in entries:
        pool = own_items + (scope_down if choice.action == "global" else [])
        matches = [v for v in pool if v.item.name == name and (kind is None or v.item.kind == kind)]
        if not matches and choice.action != "global":
            if any(v.item.name == name and (kind is None or v.item.kind == kind) for v in scope_down):
                raise ValueError(f"{name}: only global is available for this catalog plugin (keep it global)")
        if not matches:
            raise ValueError(f"no unmanaged item named '{name}'" + (f" of kind {kind}" if kind else "")
                             + " (see: loadout configure own --all)")
        kinds = sorted({v.item.kind for v in matches})
        if len(kinds) > 1:
            raise ValueError(f"'{name}' matches several kinds; write it as " + " or ".join(f"{k}:{name}" for k in kinds))
        for v in matches:
            key = decision_key(v.item)
            if key in seen:
                raise ValueError(f"'{name}' is listed more than once")
            seen.add(key)
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
    first = ask("your own tools: [l]eave all / [c]hoose each (default: decide later): ").strip().lower()
    if first in ("l", "leave"):
        return [(v, Choice("leave")) for v in verdicts]
    if first not in ("c", "choose"):
        return []  # empty or unknown: nothing decided, nothing remembered
    pairs, last_profile = [], ""
    for v in verdicts:
        opts = options(v.item)
        prompt = f"  {v.item.kind} {v.item.name} — " + " / ".join(f"[{o[0]}]{o[1:]}" for o in opts) + " (default: skip): "
        action = ""
        for _ in range(3):
            answer = ask(prompt).strip().lower()
            if not answer:
                break
            hit = [o for o in opts if o == answer or o[0] == answer]
            if hit:
                action = hit[0]
                break
            print("  please answer " + ", ".join(f"{o[0]}({o[1:]})" for o in opts))
        if not action:
            continue  # empty or invalid: not decided
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
                continue  # no valid profile name: not decided
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
    if not isinstance(needle, str) or not needle:
        return []
    try:
        projects = load_json(paths.claude_json()).get("projects")
    except (OSError, InvalidJSON):
        return []
    out = []
    for path, cfg in sorted((projects if isinstance(projects, dict) else {}).items()):
        repo = Path(path)
        try:
            if not repo.is_dir():
                continue
        except OSError:
            continue
        in_cfg = isinstance(cfg, dict) and needle in json.dumps(cfg.get("mcpServers") or {})
        files = [repo / ".mcp.json", repo / ".claude/settings.json", repo / ".claude/settings.local.json"]
        if in_cfg or any(_mentions(f, needle) for f in files):
            out.append(repo)
    return out
