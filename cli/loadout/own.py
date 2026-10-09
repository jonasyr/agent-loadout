"""Your own tools: items loadout does not manage. Record them in the personal layer (global), in a
personal profile (project), leave them on this machine, or remove them.
Spec: docs/superpowers/specs/2026-10-10-adopt-own-tools-design.md
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from . import paths
from .jsonio import load_json, save_json

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
