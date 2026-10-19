"""JSON load/save and deep merge."""
from __future__ import annotations

import copy
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class InvalidJSON(Exception):
    pass


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        text = path.read_text(encoding="utf-8-sig").strip()  # -sig: Windows editors add a BOM
    except UnicodeDecodeError as exc:
        raise InvalidJSON(f"invalid JSON in {path}: not UTF-8 text ({exc.reason})") from exc
    if not text:
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InvalidJSON(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise InvalidJSON(f"invalid JSON in {path}: expected an object at the top level")
    return data


def get_dict(data, key) -> dict:
    """data[key] when it is a dict, else {} (a null, list or scalar written by hand or by another tool)."""
    value = data.get(key) if isinstance(data, dict) else None
    return value if isinstance(value, dict) else {}


def get_list(data, key) -> list:
    """data[key] when it is a list, else []."""
    value = data.get(key) if isinstance(data, dict) else None
    return value if isinstance(value, list) else []


class WrongShape(InvalidJSON):
    """A container a write needs holds another shape; it may be the user's only copy, so it is never replaced."""


def ensure(data: dict, key: str, kind: type = dict):
    """data[key] as a `kind` container to write into, like setdefault. A missing or null value becomes an empty
    one; any other shape raises WrongShape instead of being wiped."""
    if data.get(key) is None:
        data[key] = kind()
    elif not isinstance(data[key], kind):
        raise WrongShape(f"{key} is not {'an object' if kind is dict else 'a list'}; fix it, then run this again")
    return data[key]


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


@dataclass(frozen=True)
class JsonStyle:
    indent: int | str
    newline: str
    final_newline: bool
    ensure_ascii: bool = False


def json_style(text: str) -> JsonStyle | None:
    """The layout of `text` when it is exactly what json.dumps(indent=2, 4 or a tab) writes, with one kind of line
    ending; None for any other layout, which loadout then never rewrites (the user's bytes stay theirs)."""
    newline = "\r\n" if "\r\n" in text else "\n"
    body = text.replace("\r\n", "\n")
    if newline == "\r\n" and body.count("\n") != text.count("\r\n"):  # mixed endings
        return None
    final = body.endswith("\n")
    core = body[:-1] if final else body
    try:
        data = json.loads(core)
    except ValueError:
        return None
    for indent in (2, 4, "\t", None):  # None: one line, as json.dumps writes it by default
        for ascii_ in (False, True):  # True: non-ASCII written as \\uXXXX escapes
            if json.dumps(data, indent=indent, ensure_ascii=ascii_) == core:
                return JsonStyle(indent, newline, final, ascii_)
    return None


def dumps_like(style: JsonStyle, data) -> str:
    text = json.dumps(data, indent=style.indent, ensure_ascii=style.ensure_ascii) + ("\n" if style.final_newline else "")
    return text.replace("\n", style.newline)
