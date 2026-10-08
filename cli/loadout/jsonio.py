"""JSON load/save and deep merge."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


class InvalidJSON(Exception):
    pass


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise InvalidJSON(f"invalid JSON in {path}: {exc}") from exc


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def deep_merge(base: Any, overlay: Any) -> Any:
    """Dicts merge recursively, lists union (order kept), anything else: overlay wins."""
    if isinstance(base, dict) and isinstance(overlay, dict):
        out = copy.deepcopy(base)
        for key, value in overlay.items():
            out[key] = deep_merge(out[key], value) if key in out else copy.deepcopy(value)
        return out
    if isinstance(base, list) and isinstance(overlay, list):
        return copy.deepcopy(base) + [copy.deepcopy(x) for x in overlay if x not in base]
    return copy.deepcopy(overlay)
