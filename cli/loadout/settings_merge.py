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


def _group_key(group: Any) -> tuple | None:
    """(matcher, frozenset of commands) of a hook group, or None when it has no hooks or a hook without a
    string command (such a group is merged as a plain list item)."""
    if not isinstance(group, dict) or not isinstance(group.get("hooks"), list) or not group["hooks"]:
        return None
    cmds = [h.get("command") if isinstance(h, dict) else None for h in group["hooks"]]
    if not all(isinstance(c, str) for c in cmds):
        return None
    return group.get("matcher", ""), frozenset(cmds)


def _commands(groups: Any, matcher: str) -> set:
    out = set()
    for group in groups if isinstance(groups, list) else []:
        if isinstance(group, dict) and group.get("matcher", "") == matcher and isinstance(group.get("hooks"), list):
            out |= {h.get("command") for h in group["hooks"] if isinstance(h, dict) and isinstance(h.get("command"), str)}
    return out


def _hook_lists(d: dict) -> dict:
    hooks = d.get("hooks")
    return hooks if isinstance(hooks, dict) else {}


def _applied_keys(previous: dict, event: str) -> set:
    groups = _hook_lists(previous).get(event)
    return {k for g in (groups if isinstance(groups, list) else []) if (k := _group_key(g)) is not None}


def effective_desired(current: dict, desired: dict, previous: dict) -> dict:
    """`desired` without the hook groups that are the user's own copy (see merge_settings). This is also what
    the snapshot records, so a later removal from the personal layer never deletes the user's own copy."""
    hooks = desired.get("hooks")
    if not isinstance(hooks, dict):
        return desired
    cur_hooks = _hook_lists(current)
    kept = {}
    for event, groups in hooks.items():
        if not isinstance(groups, list):
            kept[event] = groups
            continue
        applied = _applied_keys(previous, event)
        out = []
        for group in groups:
            key = _group_key(group)
            if key is not None and key not in applied and key[1] <= _commands(cur_hooks.get(event), key[0]):
                continue
            out.append(group)
        if out or not groups:
            kept[event] = out
    result = {k: v for k, v in desired.items() if k != "hooks"}
    if kept:
        result["hooks"] = kept
    return result


def _update_applied_groups(current: dict, desired: dict, previous: dict) -> dict:
    """A copy of `current` where each hook group the kit applied before (same event, matcher and command set
    in `previous`) and still desires is replaced in place by the desired version."""
    out = copy.deepcopy(current)
    cur_hooks = _hook_lists(out)
    for event, groups in _hook_lists(desired).items():
        now = cur_hooks.get(event)
        if not isinstance(groups, list) or not isinstance(now, list):
            continue
        prev_groups = _hook_lists(previous).get(event)
        prev_groups = prev_groups if isinstance(prev_groups, list) else []
        for group in groups:
            key = _group_key(group)
            if key is None or group in now:
                continue
            prev = next((g for g in prev_groups if _group_key(g) == key), None)
            if prev is None:
                continue
            at = next((i for i, g in enumerate(now) if g == prev), None)
            if at is None:
                at = next((i for i, g in enumerate(now) if _group_key(g) == key), None)
            if at is not None:
                now[at] = copy.deepcopy(group)
    return out


def merge_settings(current: dict, desired: dict, previous: dict) -> dict:
    """Three-way merge. Hook groups (the lists under `hooks.<event>`) are matched by event + matcher + the set
    of their commands, not by dict equality:

    - A desired group whose commands all already exist under the same event and matcher in `current` is the
      user's own copy and is skipped, unless the kit applied a group with that key before (it is in
      `previous`). Adding it would run the hook twice. It is also left out of the snapshot, so the user's own
      copy survives a later removal from the personal layer.
    - A group the kit applied before and still desires is updated in place, even when another field (such as
      `timeout`) changed: it is neither duplicated nor dropped.
    - A group the kit applied before and no longer desires is removed only if the user did not change it.
    """
    desired = effective_desired(current, desired, previous)
    result = deep_merge(_update_applied_groups(current, desired, previous), desired)
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


def record_applied_hook(event: str, group: dict, bk) -> None:
    """Record `group` in the snapshot as applied by the kit (backed up first). Used after the hook was moved
    into exactly this group in settings.json on the recording machine: without it the merge would treat the
    group as the user's own copy, and a later removal from the personal layer would leave it there."""
    snap = _snapshot()
    data = load_json(snap)
    groups = data.setdefault("hooks", {}).setdefault(event, [])
    if not isinstance(groups, list) or group in groups:
        return
    if snap.exists():
        bk.save_copy(snap, "managed-settings.json before recording a hook")
    else:
        bk.record_created(snap, "managed-settings.json (created when recording a hook)")
    groups.append(copy.deepcopy(group))
    save_json(snap, data)


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
