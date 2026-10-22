"""codebase-memory's auto_index setting, from the cbm_auto_index preference.

codebase-memory-mcp keeps `auto_index` in its own configuration (`config get|set auto_index`). loadout sets it only
from `false` to `true`, records that it did (state_dir()/cbm-auto-index.json) and the undo command in the backup;
a value the user set stays theirs, in both directions."""
from __future__ import annotations

import re

from . import paths, preferences, runner
from .jsonio import InvalidJSON, load_json, save_json

BINARY = "codebase-memory-mcp"
PREF = "cbm_auto_index"
LINE_ON = "codebase-memory: auto_index on (new git repos are indexed at their first session)"
LINE_YOURS = "codebase-memory: auto_index off (yours)"
LINE_OFF = "codebase-memory: auto_index off"


def record_path():
    return paths.state_dir() / "cbm-auto-index.json"


def answer() -> str | None:
    """'on' or 'off': the person's answer, else the preference's default; None when loadout.json cannot be read
    (the answer is unknown, so nothing is changed against it)."""
    try:
        preferences._loadout_data()  # raises ValueError for a file that is not valid JSON; detect() reads it as unset
        value = preferences.detect()[PREF].value
    except (ValueError, InvalidJSON):
        return None
    return value or preferences.by_id(PREF)["default"]


def current() -> bool | None:
    """codebase-memory's auto_index now; None when the binary is missing or its answer is not readable."""
    if not runner.have(BINARY):
        return None
    res = runner.run([BINARY, "config", "get", "auto_index"], timeout=30)
    if not res.ok:
        return None
    words = re.findall(r"\b(true|false)\b", res.stdout.lower())
    return words[-1] == "true" if words else None


def _ours() -> bool:
    try:
        data = load_json(record_path())
    except InvalidJSON:
        return False
    return isinstance(data, dict) and data.get("set") == "true"


def apply_auto_index(bk, dry: bool = False) -> list[str]:
    given = answer()
    now, want = current(), given == "on"
    if given is None or now is None or now == want:
        return []
    ours = _ours()
    if want:
        if ours:  # we set it true and it is false now: the person changed it
            return [LINE_YOURS]
        if not dry:
            if not _set(bk, "true", "false"):
                return ["codebase-memory: could not set auto_index (config set failed)"]
            bk.record_created(record_path(), "created loadout's codebase-memory auto_index record")
            save_json(record_path(), {"set": "true"})
        return [LINE_ON]
    if not ours:  # true, and not loadout's: the person's own value
        return []
    if not dry:
        if not _set(bk, "false", "true"):
            return ["codebase-memory: could not set auto_index (config set failed)"]
        bk.save_copy(record_path(), "loadout's codebase-memory auto_index record before it was dropped")
        record_path().unlink()
    return [LINE_OFF]


def _set(bk, value: str, old: str) -> bool:
    """The undo is in the backup before the command runs."""
    bk.record_command(f"codebase-memory auto_index set to {value}", [BINARY, "config", "set", "auto_index", old])
    return runner.run([BINARY, "config", "set", "auto_index", value], timeout=30).ok
