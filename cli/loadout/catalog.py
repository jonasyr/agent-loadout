"""Tool knowledge from catalog.json."""
from __future__ import annotations

from functools import lru_cache

from . import paths
from .jsonio import load_json


@lru_cache(maxsize=None)
def _load(root: str) -> tuple:
    return tuple(load_json(paths.kit_root() / "catalog.json").get("entries", []))


def load() -> list[dict]:
    return list(_load(str(paths.kit_root())))


def match(kind: str, name: str, detail: str = "") -> dict | None:
    for entry in load():
        if entry["kind"] != kind:
            continue
        m = entry["match"]
        if name in m.get("names", []) or any(s in detail for s in m.get("contains", [])):
            return entry
    return None


def binaries() -> list[dict]:
    return [e for e in load() if e["kind"] == "binary"]


def platform_cmds(entry: dict, key: str) -> list[list[str]]:
    return entry.get(key, {}).get(paths.platform_key(), [])
