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
    if not isinstance(detail, str):
        detail = str(detail)  # a hook whose command is a list or a number
    for entry in load():
        if entry["kind"] != kind:
            continue
        m = entry["match"]
        if name in m.get("names", []) or any(s in detail for s in m.get("contains", [])):
            return entry
    return None


def by_id(entry_id: str) -> dict | None:
    return next((e for e in load() if e["id"] == entry_id), None)


def claude_only_plugins() -> frozenset[str]:
    """Plugin ids whose catalog entry is tied to Claude Code (`target: claude`): loadout never adds them to Codex."""
    return frozenset(n for e in load() if e["kind"] == "plugin" and e.get("target") == "claude"
                     for n in e["match"].get("names", []))


def binaries() -> list[dict]:
    """Binary entries; one tied to a coding agent (target) only while that agent is chosen (targets.json)."""
    from . import targets
    on = {"claude": targets.claude_enabled(), "codex": targets.codex_enabled()}
    return [e for e in load() if e["kind"] == "binary" and on.get(e.get("target"), True)]


def install_order(entries: list[dict]) -> list[dict]:
    """Catalog order, except that every entry comes after the entries it `needs`."""
    by_id = {e["id"]: e for e in entries}
    out, done, active = [], set(), set()

    def visit(e: dict) -> None:
        if e["id"] in done:
            return
        if e["id"] in active:
            raise ValueError(f"catalog: dependency cycle at {e['id']}")
        active.add(e["id"])
        for dep in e.get("needs", []):
            if dep not in by_id:
                raise ValueError(f"catalog: {e['id']} needs unknown {dep}")
            visit(by_id[dep])
        active.discard(e["id"])
        done.add(e["id"])
        out.append(e)

    for e in entries:
        visit(e)
    return out


def platform_cmds(entry: dict, key: str) -> list[list[str]]:
    return entry.get(key, {}).get(paths.platform_key(), [])
