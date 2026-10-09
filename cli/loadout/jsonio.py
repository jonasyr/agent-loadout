"""JSON load/save and deep merge."""
from __future__ import annotations

import copy
import json
import os
import tempfile
from pathlib import Path
from typing import Any


class InvalidJSON(Exception):
    pass


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8-sig").strip()  # -sig: Windows editors add a BOM
    if not text:
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InvalidJSON(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise InvalidJSON(f"invalid JSON in {path}: expected an object at the top level")
    return data


def _default_mode() -> int:
    umask = os.umask(0)
    os.umask(umask)
    return 0o666 & ~umask


def write_atomic(path: Path, text: str, mode: int | None = None) -> None:
    """Write via a temp file in the same directory + os.replace, so readers never see a partial file.

    A symlinked target (dotfile setups) is followed, so the link itself stays in place.
    The existing file mode is kept; `mode` applies only to a new file.
    """
    write_atomic_bytes(path, text.encode("utf-8"), mode)


def write_atomic_bytes(path: Path, data: bytes, mode: int | None = None) -> None:
    path = Path(os.path.realpath(path)) if path.is_symlink() else path
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        mode = os.stat(path).st_mode & 0o7777
    elif mode is None:
        mode = _default_mode()
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        if os.name != "nt":
            os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def save_json(path: Path, data: dict, mode: int | None = None) -> None:
    write_atomic(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n", mode)


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
