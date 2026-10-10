"""Your own tools: items loadout does not manage. Record them in the personal layer (global), in a
personal profile (project), leave them on this machine, or remove them.
Spec: docs/superpowers/specs/2026-10-10-adopt-own-tools-design.md
"""
from __future__ import annotations

import filecmp
import json
import os
import shlex
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from . import paths, personal_mcp, secrets
from .jsonio import load_json, save_json
from .secrets import redact

if TYPE_CHECKING:
    from .inventory import Item, Verdict

KINDS = ("plugin", "marketplace", "mcp", "skill", "hook")
PERSONAL_REASON = "From your personal layer."
LEFT_REASON = "Left on this machine (your choice); change it with `loadout configure set own`."
OWN_REASON = "Not managed by loadout. Choose: global, project, leave or remove."


def decision_key(item: Item) -> str:
    return f"hook:{item.name}:{item.detail}" if item.kind == "hook" else f"{item.kind}:{item.name}"


def _decisions_path():
    return paths.state_dir() / "own-decisions.json"


def decisions() -> dict[str, str]:
    return load_json(_decisions_path())


def remember_leave(item: Item) -> None:
    data = decisions()
    data[decision_key(item)] = "leave"
    save_json(_decisions_path(), data)


def forget(item: Item) -> None:
    data = decisions()
    if data.pop(decision_key(item), None) is not None:
        save_json(_decisions_path(), data)


def is_left(item: Item) -> bool:
    return decisions().get(decision_key(item)) == "leave"


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
    """What the personal layer already holds: {kind: {name: reason}} (hooks keyed by command)."""
    root = paths.personal_root()
    settings = load_json(root / "settings.json")
    index = {k: {} for k in KINDS}
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
            index["plugin"].setdefault(pid, why)
        for name in (prof.get("mcp") or {}).get("mcpServers") or {}:
            index["mcp"].setdefault(name, why)
        for name in prof.get("skills") or []:
            index["skill"].setdefault(name, why)
        for cmd in _hook_commands(prof.get("settings") or {}):
            index["hook"].setdefault(cmd, why)
    return index


def in_personal_layer(item: Item, index: dict[str, dict]) -> str | None:
    if item.kind not in index:
        return None
    return index[item.kind].get(item.detail if item.kind == "hook" else item.name)


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
    markets = data.setdefault("extraKnownMarketplaces", {})
    have = markets.get(name)
    if have is not None and (not isinstance(have, dict) or have.get("source") != src):
        raise Collision(f"marketplace {name} already exists with a different source")
    markets[name] = {"source": src}


def _secret_free(name: str, cfg: dict) -> tuple[dict, list[str]]:
    """The config with secrets as ${VAR}, plus the secrets.env lines to append. Refuses unfixable secrets."""
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


def _scan_tree(src: Path, label: str) -> None:
    for f in sorted(src.rglob("*")):
        if f.is_symlink() or not f.is_file() or f.stat().st_size > 1_000_000:
            continue
        data = f.read_bytes()
        if b"\0" in data:
            continue
        _refuse_if_secret(f"{label} ({f.relative_to(src)})", data.decode("utf-8", errors="ignore"))


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


def _portable_hook(hook: dict, bk) -> tuple[dict, list[str]]:
    """Copy a local script the hook runs into <personal>/hooks/ and point the command at the linked copy."""
    if "args" in hook:
        return hook, ["note: exec form hook (args) recorded as is; it works only where its paths exist"]
    cmd = hook.get("command")
    if not isinstance(cmd, str):
        return hook, []
    try:
        tokens = shlex.split(cmd)
    except ValueError:
        return hook, []
    outside: list[str] = []
    for tok in tokens:
        p = Path(os.path.expandvars(os.path.expanduser(tok)))
        if not p.is_absolute() or not p.is_file():
            continue
        if _under(p, paths.kit_root()) or _under(p, paths.personal_root()):
            continue
        if not _under(p, paths.home()):
            outside.append(f"note: {tok} is outside your home folder; the hook works only where it exists")
            continue
        _refuse_if_secret(f"hook script {p.name}", p.read_text(errors="ignore"))
        dest = paths.personal_root() / "hooks" / p.name
        if dest.exists():
            if not filecmp.cmp(dest, p, shallow=False):
                raise Collision(f"hook script {p.name} already exists in {dest.parent} with different content")
        new = f'"$HOME/.claude/hooks/personal/{p.name}"'
        replaced = False
        for raw in (f"'{tok}'", f'"{tok}"', tok):
            if raw in cmd:
                cmd = cmd.replace(raw, new, 1)
                replaced = True
                break
        if not replaced:
            return hook, [f"note: could not rewrite the path in the command; edit it in {_personal_settings()}"]
        _refuse_if_secret("hook command", cmd)
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            bk.record_created(dest, f"hook script {p.name} copied into the personal layer")
            shutil.copy2(p, dest)
        return {**hook, "command": cmd}, [f"hook script {p.name} copied to {dest} (only this file; copy files it needs next to it by hand)"]
    _refuse_if_secret("hook command", cmd)
    return hook, outside


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
    hook, notes = _portable_hook(group["hooks"][hi], bk)
    base = {k: val for k, val in group.items() if k != "hooks"}
    return event, {**base, "hooks": [hook]}, notes


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
