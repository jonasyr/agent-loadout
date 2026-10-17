"""Three-way merge of a profile's entries into a repo JSON file (spec Part 2, ADR 0031).

base: this profile's record in .loadout.json (what it wrote, or offered, last time); theirs: the file now; new: the
profile now. A profile update applies when the file still has the recorded value; an entry a person changed stays and
is offered once (`take` uses the profile's value); a list entry a person removed stays removed; without a record only
missing entries are added. An MCP server's definition is one entry (its args are an ordered command, not a set)."""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from . import secrets

MISSING = object()
SHAPE = object()  # a part of the path is not an object in the file
HASH = "sha256:"


def pointer(path: tuple) -> str:
    return "/".join(str(k).replace("~", "~0").replace("/", "~1") for k in path)


def unpointer(text: str) -> tuple:
    return tuple(p.replace("~1", "/").replace("~0", "~") for p in text.split("/"))


def leaves(overlay: dict, prefix: tuple = ()):
    for key, value in overlay.items():
        path = prefix + (key,)
        if isinstance(value, dict) and value and not (prefix and prefix[-1] == "mcpServers"):
            yield from leaves(value, path)
        else:
            yield path, value


def _canon(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)  # default: TOML dates


def same(a, b) -> bool:
    """Equal as JSON: true is not 1, 1 is not 1.0 (Python's == says they are)."""
    return _canon(a) == _canon(b)


def _has(items: list, s) -> bool:
    return any(_canon(s) == _canon(x) for x in items)


def secretish(value, key: str = "") -> bool:
    if isinstance(value, dict):
        return any(secretish(v, str(k)) for k, v in value.items())
    if isinstance(value, list):
        return any(secretish(v, key) for v in value)
    return isinstance(value, str) and (secrets.redact(value) != value or secrets.looks_secret(key, value))


def stored(value, key: str = ""):
    """The value as the committed record keeps it: as is, or a hash when it looks like a secret."""
    if secretish(value, key) or (isinstance(value, str) and value.startswith(HASH)):
        return HASH + hashlib.sha256(_canon(value).encode("utf-8")).hexdigest()
    return copy.deepcopy(value)


def matches(record_value, value, key: str = "") -> bool:
    return value is not MISSING and value is not SHAPE and _canon(stored(value, key)) == _canon(record_value)


def held(others: tuple, ptr: str, s) -> bool:
    """Another profile's record for this file has the stored value s at ptr (or in its list)."""
    for rec in others:
        v = rec.get(ptr, MISSING)
        if isinstance(v, list) and _has(v, s) or (v is not MISSING and not isinstance(v, list) and _canon(v) == _canon(s)):
            return True
    return False


def show(value, key: str = "") -> str:
    if value is MISSING or value is SHAPE:
        return "nothing (removed)"
    if secretish(value, key) or (isinstance(value, str) and value.startswith(HASH)):
        return "(a secret value, not shown)"
    return json.dumps(value, ensure_ascii=False)


def get(data, path: tuple):
    node = data
    for key in path:
        if not isinstance(node, dict):
            return SHAPE
        if key not in node:
            return MISSING
        node = node[key]
    return node


def _set(data: dict, path: tuple, value) -> None:
    for key in path[:-1]:
        data = data.setdefault(key, {})
    data[path[-1]] = copy.deepcopy(value)


def _delete(data: dict, path: tuple) -> None:
    chain, node = [], data
    for key in path[:-1]:
        chain.append((node, key))
        node = node[key]
    node.pop(path[-1], None)
    for parent, key in reversed(chain):  # an object loadout emptied goes too
        if parent[key] != {}:
            break
        del parent[key]


@dataclass
class Differs:
    pointer: str
    theirs: Any  # MISSING when a person removed it
    new: Any


@dataclass
class Merge:
    after: dict
    record: dict = field(default_factory=dict)
    added: list = field(default_factory=list)
    updated: list = field(default_factory=list)
    removed: list = field(default_factory=list)
    differs: list = field(default_factory=list)
    kept: list = field(default_factory=list)
    offered: list = field(default_factory=list)  # Differs a person changed, the profile's value offered before
    kept_removed: list = field(default_factory=list)
    left: list = field(default_factory=list)
    blocked: list = field(default_factory=list)


def merge(current: dict, overlay: dict, base: dict, take: bool = False, others: tuple = (),
          take_offered: bool = False) -> Merge:
    """current: the file now (not changed); overlay: the profile's fragment; base: this profile's record for the file
    ({} without one); take: use the profile's value where a person changed an entry; others: the other profiles'
    records for the file; take_offered: also where the profile's value was offered before and declined (an explicit
    --take-profile)."""
    m = Merge(copy.deepcopy(current))
    seen = set()
    for path, new in leaves(overlay):
        ptr = pointer(path)
        seen.add(ptr)
        theirs = get(m.after, path)
        if theirs is SHAPE:
            m.blocked.append(f"{ptr}: not written, a part of its path is not an object in the file")
            if ptr in base:
                m.record[ptr] = base[ptr]
            continue
        if isinstance(new, list):
            _list(m, path, ptr, new, theirs, base.get(ptr, MISSING), others)
        else:
            _value(m, path, ptr, new, theirs, base.get(ptr, MISSING), take, others, take_offered)
    for ptr, old in base.items():
        if ptr not in seen:
            _drop(m, unpointer(ptr), ptr, old, others)
    return m


def _value(m: Merge, path, ptr, new, theirs, old, take, others, take_offered=False) -> None:
    key = str(path[-1])
    if theirs is not MISSING and _canon(theirs) == _canon(new):
        if old is not MISSING or held(others, ptr, stored(new, key)):
            m.record[ptr] = stored(new, key)
        return
    if old is MISSING:
        if theirs is MISSING:
            _set(m.after, path, new)
            m.added.append(ptr)
            m.record[ptr] = stored(new, key)
        else:
            m.left.append(f"{ptr}: left as is, the repo has {show(theirs, key)} (the profile: {show(new, key)})")
        return
    if matches(old, theirs, key):
        _set(m.after, path, new)
        m.updated.append(ptr)
        m.record[ptr] = stored(new, key)
    elif matches(old, new, key):  # offered before: not asked again, only an explicit take uses it
        m.offered.append(Differs(ptr, theirs, new))
        if take_offered:
            _set(m.after, path, new)
            m.updated.append(ptr)
        m.record[ptr] = old
    else:
        m.differs.append(Differs(ptr, theirs, new))
        if take:
            _set(m.after, path, new)
            m.updated.append(ptr)
        m.record[ptr] = stored(new, key)


def _list(m: Merge, path, ptr, new, theirs, old, others) -> None:
    key = str(path[-1])
    if theirs is not MISSING and not isinstance(theirs, list):
        m.blocked.append(f"{ptr}: not written, the file has {show(theirs, key)} there, not a list")
        if old is not MISSING:
            m.record[ptr] = old
        return
    have = list(theirs) if theirs is not MISSING else []
    ours = old if isinstance(old, list) else []
    wanted = [stored(e, key) for e in new]
    rec, add = [], []
    for entry, s in zip(new, wanted):
        if any(_canon(entry) == _canon(x) for x in have):
            if _has(ours, s) or held(others, ptr, s):
                rec.append(s)
        elif _has(ours, s):
            m.kept_removed.append(f"{ptr}: {show(entry, key)}")
            rec.append(s)
        else:
            add.append(entry)
            rec.append(s)
            m.added.append(f"{ptr}: {show(entry, key)}")
    keep = []
    for x in have:
        s = stored(x, key)
        if _has(ours, s) and not _has(wanted, s) and not held(others, ptr, s):
            m.removed.append(f"{ptr}: {show(x, key)}")
        else:
            keep.append(x)
    if add or len(keep) != len(have):
        _set(m.after, path, keep + add)
    if rec:
        m.record[ptr] = rec


def _drop(m: Merge, path, ptr, old, others) -> None:
    """An entry the record has and the profile no longer has."""
    key = str(path[-1])
    theirs = get(m.after, path)
    if isinstance(old, list):
        if isinstance(theirs, list):
            _list(m, path, ptr, [], theirs, old, others)
        return
    if theirs is MISSING or theirs is SHAPE:
        return
    if matches(old, theirs, key) and not held(others, ptr, old):
        _delete(m.after, path)
        m.removed.append(ptr)
    else:
        m.kept.append(f"{ptr}: no longer in the profile; the repo's value stays")
