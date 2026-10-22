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


UNREADABLE = "unreadable"  # codebase-memory-mcp is there, but `config get auto_index` failed or said nothing


def query() -> bool | str | None:
    """codebase-memory's auto_index now; None when the binary is missing, UNREADABLE when it cannot be read."""
    if not runner.have(BINARY):
        return None
    res = runner.run([BINARY, "config", "get", "auto_index"], timeout=30)
    if res.returncode == 127:
        return None  # not found after all (runner's "command not found")
    words = re.findall(r"\b(true|false)\b", res.stdout.lower()) if res.ok else []
    return words[-1] == "true" if words else UNREADABLE


def current() -> bool | None:
    """codebase-memory's auto_index now; None when the binary is missing or its answer is not readable."""
    now = query()
    return now if isinstance(now, bool) else None


def _record() -> str | None:
    """loadout's record: "true" (loadout turned auto_index on) or "yours" (you changed it after that)."""
    try:
        data = load_json(record_path())
    except InvalidJSON:
        return None
    value = data.get("set") if isinstance(data, dict) else None
    return value if value in ("true", "yours") else None


def _ours() -> bool:
    return _record() == "true"


def _write_record(bk, value: str | None) -> None:
    """Change loadout's record with a backup first; None drops it."""
    if record_path().exists():
        bk.save_copy(record_path(), "loadout's codebase-memory auto_index record before it changed")
    else:
        bk.record_created(record_path(), "created loadout's codebase-memory auto_index record")
    if value is None:
        record_path().unlink(missing_ok=True)
    else:
        save_json(record_path(), {"set": value})


def apply_auto_index(bk, dry: bool = False) -> list[str]:
    given = answer()
    now, want = query(), given == "on"
    if given is None or now is None:
        return []
    if now == UNREADABLE:
        return ["codebase-memory: could not read auto_index (config get failed)"]
    record = _record()
    if now == want:
        if not want and record == "true" and not dry:
            _write_record(bk, None)  # the value is off anyway: nothing of loadout's is left to own
        return []
    if want:
        if record == "true" and not dry:
            _write_record(bk, "yours")  # we set it true and it is false now: you changed it, it stays yours
        if record:
            return [LINE_YOURS]
        if not dry:
            if not _set(bk, "true", "false"):
                return ["codebase-memory: could not set auto_index (config set failed)"]
            _write_record(bk, "true")
        return [LINE_ON]
    if record != "true":  # true, and not loadout's: your own value
        return []
    if not dry:
        if not _set(bk, "false", "true"):
            return ["codebase-memory: could not set auto_index (config set failed)"]
        _write_record(bk, None)
    return [LINE_OFF]


def _set(bk, value: str, old: str) -> bool:
    """The undo is in the backup before the command runs."""
    bk.record_command(f"codebase-memory auto_index set to {value}", [BINARY, "config", "set", "auto_index", old])
    if runner.run([BINARY, "config", "set", "auto_index", value], timeout=30).ok:
        return True
    bk.steps.pop()  # nothing changed: no undo may run later (as Backup.move does on a failed move)
    bk._save()
    return False
