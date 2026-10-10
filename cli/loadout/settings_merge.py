"""Three-way merge of kit-managed keys into ~/.claude/settings.json (spec §6.3).

desired  = settings.base.json (kit) overlaid with <personal>/settings.json
previous = snapshot of what the kit applied last time
current  = the user's settings.json
Desired values win; values the kit applied before but no longer wants are removed
only if the user did not change them; everything else in current is left alone.
The `hooks` section is merged per hook (event + matcher + command), not per group or list
item; the rules are in merge_settings. The snapshot records exactly the hooks the kit applied (`hooks`) and
tombstones of desired hooks the user deleted (TOMBSTONES).
"""
from __future__ import annotations

import copy
import json
from typing import Any, Iterator

from . import paths
from .jsonio import deep_merge, load_json, save_json

MISSING = object()
# Snapshot key for the tombstones: desired hooks the kit applied and the user then deleted (see merge_settings).
TOMBSTONES = "loadoutDeletedHooks"


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


HookId = tuple  # (event, matcher, kind, value): see hook_id


def hook_id(event: str, group: Any, hook: Any) -> HookId | None:
    """Identity of one hook: event, matcher (a missing matcher equals ""), and its command; an exec-form hook
    (with `args`) is identified by its command plus the args list, any other hook by its whole dict."""
    if not isinstance(group, dict) or not isinstance(hook, dict):
        return None
    matcher = group.get("matcher", "")
    matcher = "" if matcher is None else matcher if isinstance(matcher, str) else json.dumps(matcher, sort_keys=True)
    cmd = hook.get("command")
    if "args" in hook:
        return event, matcher, "exec", json.dumps([cmd, hook.get("args")], sort_keys=True)
    if isinstance(cmd, str):
        return event, matcher, "command", cmd
    return event, matcher, "dict", json.dumps(hook, sort_keys=True)


def _hook_lists(d: Any) -> dict:
    hooks = d.get("hooks") if isinstance(d, dict) else None
    return hooks if isinstance(hooks, dict) else {}


def _iter_hooks(d: Any) -> Iterator[tuple[str, int, int, dict, dict, HookId]]:
    for event, groups in _hook_lists(d).items():
        for gi, group in enumerate(groups if isinstance(groups, list) else []):
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                continue
            for hi, hook in enumerate(group["hooks"]):
                if (hid := hook_id(event, group, hook)) is not None:
                    yield event, gi, hi, group, hook, hid


def _base(group: dict) -> dict:
    return {k: v for k, v in group.items() if k != "hooks"}


def _hook_map(d: Any) -> dict:
    """{identity: (hook dict, group fields without "hooks")} of every hook in a settings dict; a later duplicate
    wins. This reads the snapshot in both formats: whole desired groups (fix pass 2) and the applied hooks only."""
    out = {}
    for event, _, _, group, hook, hid in _iter_hooks(d):
        out.pop(hid, None)  # last wins, and takes the last position
        out[hid] = (hook, _base(group))
    return out


def _snapshot_hooks(applied: dict) -> dict:
    """The snapshot's `hooks` section for {identity: (hook, group fields)}: one group per event and group
    fields, holding the applied hooks in order."""
    out: dict = {}
    index: dict = {}
    for hid, (hook, base) in applied.items():
        event = hid[0]
        key = (event, json.dumps(base, sort_keys=True))
        if key not in index:
            index[key] = {**copy.deepcopy(base), "hooks": []}
            out.setdefault(event, []).append(index[key])
        index[key]["hooks"].append(copy.deepcopy(hook))
    return out


def _merge_hooks(current: Any, desired: Any, previous: Any, deleted: Any = None) -> tuple[dict | None, dict, dict]:
    """Per-hook three-way merge of the `hooks` sections. `deleted` holds the tombstones of the previous merge.
    Returns (the merged hooks section, or None when it is left empty and should be dropped; {identity: (hook,
    group fields)} of the hooks the kit applied; the same for the tombstones to keep)."""
    result = copy.deepcopy(current) if isinstance(current, dict) else {}
    want = _hook_map({"hooks": desired})
    prev = _hook_map({"hooks": previous})
    dead = _hook_map({"hooks": deleted})
    applied: dict = {}
    tombs: dict = {}

    def where(hid):
        return [(event, gi, hi) for event, gi, hi, _, _, h in _iter_hooks({"hooks": result}) if h == hid]

    def foreign(event):  # an event value loadout does not understand: never touched
        return event in result and not isinstance(result[event], list)

    for hid, (hook, base) in want.items():
        event = hid[0]
        if foreign(event):
            continue
        if hid in dead:  # the user deleted the kit's copy: never re-added; a copy in current is the user's
            tombs[hid] = dead[hid]
            continue
        found = where(hid)
        if found:
            if hid not in prev:
                continue  # the user's own copy: untouched and not recorded
            e, gi, hi = found[0]
            now = result[e][gi]["hooks"][hi]
            if now != prev[hid][0] and now != hook:
                continue  # the user edited the kit's hook: theirs from now on, and it leaves the snapshot
            if hook != now:  # the kit changed it: update in place, wherever it sits
                result[e][gi]["hooks"][hi] = copy.deepcopy(hook)
            applied[hid] = (hook, base)
            continue
        if hid in prev:  # applied before and deleted by the user: keep a tombstone while it stays desired
            tombs[hid] = prev[hid]
            continue
        groups = result.setdefault(event, [])
        target = next((g for g in groups if isinstance(g, dict) and isinstance(g.get("hooks"), list)
                       and hook_id(event, g, hook) == hid), None)
        if target is not None:
            target["hooks"].append(copy.deepcopy(hook))
        else:
            groups.append({**copy.deepcopy(base), "hooks": [copy.deepcopy(hook)]})
        applied[hid] = (hook, base)

    emptied = False
    for hid, (hook, _) in prev.items():
        if hid in want or hid in dead:
            continue
        for e, gi, hi in where(hid):
            group = result[e][gi]
            if group["hooks"][hi] != hook:
                continue  # changed by the user: theirs now
            del group["hooks"][hi]
            if not group["hooks"]:
                del result[e][gi]
                if not result[e]:
                    del result[e]
                emptied = True
            break
    if not result and (emptied or not isinstance(current, dict) or current):
        return None, applied, tombs
    return result, applied, tombs


def _plan(current: dict, desired: dict, previous: dict) -> tuple[dict, dict]:
    """(merged settings, snapshot). Non-hook keys: the plain three-way merge; `hooks`: per hook."""
    def strip(d):
        return {k: v for k, v in d.items() if k not in ("hooks", TOMBSTONES)} if isinstance(d, dict) else {}

    cur, want, prev = strip(current), strip(desired), strip(previous)
    result = deep_merge(cur, want)
    for path, prev_value in leaves(prev):
        if get_path(cur, path) is MISSING:
            continue
        wanted = get_path(want, path)
        now = get_path(result, path)
        if isinstance(prev_value, list) and isinstance(now, list):
            keep = wanted if isinstance(wanted, list) else []
            dropped = [x for x in prev_value if x not in keep]
            pruned = [x for x in now if x not in dropped]
            if pruned or wanted is not MISSING:
                _set_path(result, path, pruned)
            else:
                _delete_path(result, path)
        elif wanted is MISSING and get_path(cur, path) == prev_value:
            _delete_path(result, path)
    snapshot = copy.deepcopy(want)
    if "hooks" in current and not isinstance(current["hooks"], dict):
        result["hooks"] = copy.deepcopy(current["hooks"])  # not a hooks section loadout understands: left alone
    elif "hooks" in current or "hooks" in desired or "hooks" in previous:
        hooks, applied, tombs = _merge_hooks(current.get("hooks"), desired.get("hooks"), previous.get("hooks"),
                                             previous.get(TOMBSTONES))
        if hooks is not None:
            result["hooks"] = hooks
        if applied:
            snapshot["hooks"] = _snapshot_hooks(applied)
        if tombs:
            snapshot[TOMBSTONES] = _snapshot_hooks(tombs)
    return result, snapshot


def effective_desired(current: dict, desired: dict, previous: dict) -> dict:
    """What the snapshot records after merging: the desired non-hook keys, and under `hooks` exactly the hooks
    the kit applied or updated (never the user's own copy, so a later removal from the personal layer leaves
    that copy alone)."""
    return _plan(current, desired, previous)[1]


def merge_settings(current: dict, desired: dict, previous: dict) -> dict:
    """Three-way merge. Keys other than `hooks`: desired values win; a value the kit applied before but no
    longer wants is removed only if the user did not change it; list items union.

    `hooks` is merged per hook, identified by event + matcher (missing = "") + command (an exec-form hook by
    command + args). An event whose value in current is not a list is left exactly as it is. For each identity:

    - desired, with a tombstone (the user deleted the kit's copy earlier): never added again; a copy in current
      is the user's. The tombstone stays as long as the identity is desired.
    - desired, not in current, applied before (in the snapshot): the user deleted it (or changed its matcher):
      not added again, and a tombstone is recorded.
    - desired, not in current, not applied before: added to the first group in current with the same event and
      matcher, or as a new group (with the desired group's other fields).
    - desired and in current: never added a second time. Applied before and unchanged in current: the kit's;
      updated in place if the desired hook changed (e.g. timeout). Applied before but changed in current (and
      not equal to desired): the user edited it, so it is theirs from now on: never overwritten or removed, and
      it leaves the snapshot. Not applied before: the user's own copy, untouched and not recorded.
    - applied before, no longer desired: removed if current still holds it unchanged; a group left empty is
      removed. A hook the user changed stays. Its tombstone, if any, goes.
    - in neither desired nor the snapshot: never touched.
    Duplicate identities in desired collapse (last wins). The snapshot records exactly the applied hooks and the
    tombstones.
    """
    return _plan(current, desired, previous)[0]


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
    """Record the hooks of `group` in the snapshot as applied by the kit (backed up first). Used after the
    hook was made exactly this hook in settings.json on the recording machine: without it the merge would
    treat it as the user's own copy, and a later removal from the personal layer would leave it there."""
    snap = _snapshot()
    data = load_json(snap)
    applied = _hook_map(data)
    added = {hid: (hook, _base(group)) for hook in group.get("hooks") or []
             if (hid := hook_id(event, group, hook)) is not None}
    tombs = _hook_map({"hooks": data.get(TOMBSTONES)})
    if all(applied.get(hid, (None,))[0] == hook and hid not in tombs for hid, (hook, _) in added.items()):
        return
    if snap.exists():
        bk.save_copy(snap, "managed-settings.json before recording a hook")
    else:
        bk.record_created(snap, "managed-settings.json (created when recording a hook)")
    applied.update(added)
    data["hooks"] = _snapshot_hooks(applied)
    tombs = {hid: v for hid, v in _hook_map({"hooks": data.get(TOMBSTONES)}).items() if hid not in added}
    if tombs:
        data[TOMBSTONES] = _snapshot_hooks(tombs)
    else:
        data.pop(TOMBSTONES, None)
    save_json(snap, data)


def would_change() -> bool:
    current = load_json(_target())
    return merge_settings(current, desired_settings(), load_json(_snapshot())) != current


def apply_settings() -> tuple[dict, dict]:
    current = load_json(_target())  # raises InvalidJSON before anything is written
    desired = desired_settings()
    previous = load_json(_snapshot())
    after, applied = _plan(current, desired, previous)
    if after != current:
        save_json(_target(), after)
    save_json(_snapshot(), applied)
    return current, after


def drift() -> list[str]:
    current = load_json(_target())
    desired, previous = desired_settings(), load_json(_snapshot())
    out = []
    for path, value in leaves({k: v for k, v in effective_desired(current, desired, previous).items()
                               if k not in ("hooks", TOMBSTONES)}):
        now = get_path(current, path)
        if isinstance(value, list) and isinstance(now, list):
            if all(x in now for x in value):
                continue
        elif now == value:
            continue
        out.append("/".join(path))
    merged = _hook_lists(merge_settings(current, desired, previous))
    have = _hook_lists(current)
    out += [f"hooks/{event}" for event in dict.fromkeys([*merged, *have]) if merged.get(event) != have.get(event)]
    return out
