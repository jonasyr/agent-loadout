"""Three-way merge of kit-managed keys into ~/.claude/settings.json (spec §6.3).

desired  = settings.base.json (kit) overlaid with <personal>/settings.json
previous = snapshot of what the kit applied last time
current  = the user's settings.json
Desired values win; values the kit applied before but no longer wants are removed
only if the user did not change them; everything else in current is left alone.
"""
from __future__ import annotations

import copy
from typing import Any, Iterator

from . import paths
from .jsonio import deep_merge, load_json, save_json

MISSING = object()


def leaves(d: dict, prefix: tuple = ()) -> Iterator[tuple[tuple, Any]]:
    for key, value in d.items():
        if isinstance(value, dict) and value:
            yield from leaves(value, prefix + (key,))
        else:
            yield prefix + (key,), value


def get_path(d: Any, path: tuple) -> Any:
    for key in path:
        if not isinstance(d, dict) or key not in d:
            return MISSING
        d = d[key]
    return d


def _set_path(d: dict, path: tuple, value: Any) -> None:
    for key in path[:-1]:
        d = d.setdefault(key, {})
    d[path[-1]] = value


def _delete_path(d: dict, path: tuple) -> None:
    chain = []
    node = d
    for key in path[:-1]:
        chain.append((node, key))
        node = node[key]
    del node[path[-1]]
    for parent, key in reversed(chain):
        if parent[key] == {}:
            del parent[key]
        else:
            break


def _commands(groups: Any, matcher: str) -> set:
    out = set()
    for group in groups if isinstance(groups, list) else []:
        if isinstance(group, dict) and group.get("matcher", "") == matcher and isinstance(group.get("hooks"), list):
            out |= {h.get("command") for h in group["hooks"] if isinstance(h, dict) and isinstance(h.get("command"), str)}
    return out


def effective_desired(current: dict, desired: dict, previous: dict) -> dict:
    """`desired` without the hook groups the user already has: every hook of the group exists (by command)
    under the same event and matcher in `current`, and the kit did not add it before. List union would add
    such a group as a duplicate and run the hook twice. Because it is left out here, it is also left out of
    the snapshot, so a later removal from the personal layer never deletes the user's own copy."""
    hooks = desired.get("hooks")
    if not isinstance(hooks, dict):
        return desired
    cur_hooks = current.get("hooks") if isinstance(current.get("hooks"), dict) else {}
    prev_hooks = previous.get("hooks") if isinstance(previous.get("hooks"), dict) else {}
    kept = {}
    for event, groups in hooks.items():
        if not isinstance(groups, list):
            kept[event] = groups
            continue
        out = []
        for group in groups:
            cmds = ({h.get("command") for h in group["hooks"] if isinstance(h, dict)}
                    if isinstance(group, dict) and isinstance(group.get("hooks"), list) and group["hooks"] else None)
            matcher = group.get("matcher", "") if isinstance(group, dict) else ""
            prev_list = prev_hooks.get(event)
            applied_before = isinstance(prev_list, list) and group in prev_list
            if cmds and not applied_before and all(isinstance(c, str) for c in cmds) \
                    and cmds <= _commands(cur_hooks.get(event), matcher):
                continue
            out.append(group)
        if out or not groups:
            kept[event] = out
    result = {k: v for k, v in desired.items() if k != "hooks"}
    if kept:
        result["hooks"] = kept
    return result


def merge_settings(current: dict, desired: dict, previous: dict) -> dict:
    desired = effective_desired(current, desired, previous)
    result = deep_merge(copy.deepcopy(current), desired)
    for path, prev_value in leaves(previous):
        if get_path(current, path) is MISSING:
            continue
        wanted = get_path(desired, path)
        now = get_path(result, path)
        if isinstance(prev_value, list) and isinstance(now, list):
            keep = wanted if isinstance(wanted, list) else []
            dropped = [x for x in prev_value if x not in keep]
            pruned = [x for x in now if x not in dropped]
            if pruned or wanted is not MISSING:
                _set_path(result, path, pruned)
            else:
                _delete_path(result, path)
        elif wanted is MISSING and get_path(current, path) == prev_value:
            _delete_path(result, path)
    return result


def desired_settings() -> dict:
    base = load_json(paths.kit_root() / "settings.base.json")
    personal = load_json(paths.personal_root() / "settings.json")
    return deep_merge(base, personal)


def _target():
    return paths.claude_home() / "settings.json"


def _snapshot():
    return paths.state_dir() / "managed-settings.json"


def backup_snapshot(bk) -> None:
    """Record the snapshot in the backup before apply_settings rewrites it. Without this a restore puts
    settings.json back but leaves a snapshot that says the kit applied the change, so the next merge deletes it."""
    snap = _snapshot()
    if not snap.exists():
        bk.record_created(snap, "managed-settings.json (created by the loadout merge)")
    elif load_json(snap) != effective_desired(load_json(_target()), desired_settings(), load_json(snap)):
        bk.save_copy(snap, "managed-settings.json before loadout merge")


def would_change() -> bool:
    current = load_json(_target())
    return merge_settings(current, desired_settings(), load_json(_snapshot())) != current


def apply_settings() -> tuple[dict, dict]:
    current = load_json(_target())  # raises InvalidJSON before anything is written
    desired = desired_settings()
    previous = load_json(_snapshot())
    applied = effective_desired(current, desired, previous)
    after = merge_settings(current, desired, previous)
    if after != current:
        save_json(_target(), after)
    save_json(_snapshot(), applied)
    return current, after


def drift() -> list[str]:
    current = load_json(_target())
    out = []
    for path, value in leaves(effective_desired(current, desired_settings(), load_json(_snapshot()))):
        now = get_path(current, path)
        if isinstance(value, list) and isinstance(now, list):
            if all(x in now for x in value):
                continue
        elif now == value:
            continue
        out.append("/".join(path))
    return out
