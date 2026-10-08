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


def merge_settings(current: dict, desired: dict, previous: dict) -> dict:
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


def apply_settings() -> tuple[dict, dict]:
    current = load_json(_target())  # raises InvalidJSON before anything is written
    desired = desired_settings()
    after = merge_settings(current, desired, load_json(_snapshot()))
    if after != current:
        save_json(_target(), after)
    save_json(_snapshot(), desired)
    return current, after


def drift() -> list[str]:
    current = load_json(_target())
    out = []
    for path, value in leaves(desired_settings()):
        now = get_path(current, path)
        if isinstance(value, list) and isinstance(now, list):
            if all(x in now for x in value):
                continue
        elif now == value:
            continue
        out.append("/".join(path))
    return out
