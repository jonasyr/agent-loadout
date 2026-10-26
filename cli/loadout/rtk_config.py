"""rtk's config.toml: loadout's one line `suppress_hook_warning = true` under [hooks], set where loadout's plugin
provides rtk's Claude Code hook (rtk looks for it in settings.json, does not see it and warns "No hook installed").
Exact-text record, parse guard, the user's text byte for byte, a backup before every write (ADR 0043)."""
from __future__ import annotations

import copy
import re
import tomllib
from pathlib import Path

from . import duplicates, paths, runner, targets
from .jsonio import InvalidJSON, load_json, save_json, write_atomic

KEY = "suppress_hook_warning"
LINE = f"{KEY} = true"
NEW_FILE = f"[hooks]\n{LINE}\n"
_HEADER = re.compile(r"""^[ \t]*\[[ \t]*(?:hooks|"hooks"|'hooks')[ \t]*\][ \t]*(?:#[^\r\n]*)?\r?$""", re.M)


def record_path() -> Path:
    return paths.state_dir() / "rtk-config.json"


def wanted() -> bool:
    return bool(targets.claude_enabled() and duplicates.plugin_enabled()
                and duplicates.plugin_guarded_hooks("rtk") and runner.have("rtk"))


def _record() -> dict:
    try:
        rec = load_json(record_path())
    except InvalidJSON:
        return {}
    return rec if isinstance(rec, dict) else {}


def _span(text: str):
    """(header match, body start, body end) of the one [hooks] header table, else None."""
    headers = list(_HEADER.finditer(text))
    if len(headers) != 1:
        return None
    start = headers[0].end()
    nxt = re.compile(r"^[ \t]*\[", re.M).search(text, start)
    return headers[0], start, nxt.start() if nxt else len(text)


def _backup_record(bk) -> None:
    p = record_path()
    if p.exists():
        bk.save_copy(p, "loadout's rtk config record")
    else:
        bk.record_created(p, "created loadout's rtk config record")


def _store(bk, rec: dict, dry_run: bool, backed: bool = False) -> None:
    """Save the record (nothing left in it: the file goes), backed up first."""
    if dry_run:
        return
    rec = {k: v for k, v in rec.items() if v not in (None, [], "")}
    p = record_path()
    if p.exists():
        if _read_record_text(p) == _dump(rec):
            return
        if not backed:
            bk.save_copy(p, "loadout's rtk config record")
        if not rec:
            p.unlink()
            return
    elif not rec:
        return
    elif not backed:
        bk.record_created(p, "created loadout's rtk config record")
    p.parent.mkdir(parents=True, exist_ok=True)
    save_json(p, rec)


def _dump(rec: dict) -> str:
    import json
    return json.dumps(rec, indent=2, ensure_ascii=False) + "\n" if rec else ""


def _read_record_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _once(rec: dict, name: str) -> bool:
    """True the first time `name` is said; marks it in rec."""
    said = [s for s in rec.get("said", []) if isinstance(s, str)]
    if name in said:
        return False
    rec["said"] = [*said, name]
    return True


def apply(bk, dry_run: bool = False) -> list[str]:
    cfg = paths.rtk_config()
    rec = _record()
    owned = rec.get("line") if isinstance(rec.get("line"), str) else None
    if rec.get("created") and not cfg.exists():  # a restore (or the user) removed the file loadout made
        rec = {"said": rec.get("said", [])}
        owned = None
        _store(bk, rec, dry_run)
    if not wanted() and owned is None:
        return []
    try:
        text = cfg.read_bytes().decode("utf-8") if cfg.exists() else ""
        data = tomllib.loads(text)
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        if not _once(rec, "unparseable"):  # said once, not on every run and every plan
            return []
        _store(bk, rec, dry_run)
        return ["skipped rtk config.toml: it does not parse now; left as is"]
    if "unparseable" in rec.get("said", []):  # it parses again: say it again if it breaks later
        rec["said"] = [s for s in rec["said"] if s != "unparseable"]
        _store(bk, rec, dry_run)
    hooks = data.get("hooks")
    if not wanted():
        return _remove(bk, dry_run, cfg, text, data, rec, owned)
    if owned is not None and _has_line(text, owned) and hooks_true(data):
        return []  # ours, still there
    if owned is not None:  # the user changed or removed loadout's line: theirs now
        rec = {"said": rec.get("said", [])}
        _store(bk, rec, dry_run)
    if hooks is not None and not isinstance(hooks, dict):
        return _unplaceable(bk, dry_run, rec)
    if isinstance(hooks, dict) and KEY in hooks:
        if hooks[KEY] is True:
            return []
        if hooks[KEY] is False:
            if not _once(rec, "user_false"):
                return []
            _store(bk, rec, dry_run)
            return ['rtk config.toml: suppress_hook_warning = false is yours; rtk\'s "No hook installed" '
                    "warning stays (left as is)"]
        return _unplaceable(bk, dry_run, rec)
    nl = "\r\n" if "\r\n" in text else "\n"
    header, prefix, lead = False, "", ""
    if not cfg.exists():
        new, header = NEW_FILE, True
    elif hooks is None:
        prefix = (nl + nl if text and not text.endswith("\n") else nl if text else "")
        new, header = text + prefix + f"[hooks]{nl}{LINE}{nl}", True
    else:
        span = _span(text)
        if span is None:
            return _unplaceable(bk, dry_run, rec)
        _, start, end = span
        region = text[start:end]
        cut = len(region.rstrip(" \t\r\n"))  # past the last non-blank line's content
        eol = region.find("\n", cut)
        if eol < 0:  # that line has no newline (end of file): loadout's line brings its own
            lead = nl
            new = text[:end] + lead + LINE
        else:
            pos = start + eol + 1
            new = text[:pos] + LINE + nl + text[pos:]
    expected = copy.deepcopy(data)
    expected.setdefault("hooks", {})[KEY] = True
    try:
        ok = tomllib.loads(new) == expected
    except tomllib.TOMLDecodeError:
        ok = False
    if not ok:
        return _unplaceable(bk, dry_run, rec)
    verb = "to silence" if dry_run else "silenced"
    out = [f"rtk config.toml: {verb} rtk's \"No hook installed\" warning (loadout's plugin provides the hook)"]
    if dry_run:
        return out
    created = not cfg.exists()
    _backup_record(bk)
    if created:
        bk.record_created(cfg, "created rtk config.toml")
    else:
        bk.save_copy(cfg, "rtk config.toml before loadout changed it")
    write_atomic(cfg, new)
    _store(bk, {**rec, "line": LINE, "header": header, "created": created, "prefix": prefix, "lead": lead},
           False, backed=True)
    return out


def hooks_true(data: dict) -> bool:
    hooks = data.get("hooks")
    return isinstance(hooks, dict) and hooks.get(KEY) is True


def _has_line(text: str, line: str) -> bool:
    span = _span(text)
    return span is not None and re.search(rf"^{re.escape(line)}(?:\r?\n|\Z)", text[span[1]:span[2]], re.M) is not None


def _unplaceable(bk, dry_run: bool, rec: dict) -> list[str]:
    if not _once(rec, "unplaceable"):
        return []
    _store(bk, rec, dry_run)
    return ["rtk config.toml: could not add suppress_hook_warning to your [hooks]; add it by hand to silence "
            "rtk's warning"]


def _remove(bk, dry_run: bool, cfg: Path, text: str, data: dict, rec: dict, owned: str | None) -> list[str]:
    keep = {"said": rec.get("said", [])}
    span = _span(text)
    m = None
    if span is not None and owned is not None:
        m = re.search(rf"^{re.escape(owned)}(?:\r?\n|\Z)", text[span[1]:span[2]], re.M)
    if m is None or span is None or not hooks_true(data):  # edited or gone: the user's now; only the record goes
        _store(bk, keep, dry_run)
        return []
    a, b = span[1] + m.start(), span[1] + m.end()
    lead = rec.get("lead") if isinstance(rec.get("lead"), str) else ""
    if lead and b == len(text) and text[:a].endswith(lead):
        a -= len(lead)  # the newline loadout added to end the user's last line
    new = text[:a] + text[b:]
    expected = copy.deepcopy(data)
    del expected["hooks"][KEY]
    if rec.get("header"):
        s2 = _span(new)
        if s2 is not None and not new[s2[1]:s2[2]].strip():
            h = s2[0]
            tail = h.end() + (1 if new[h.end():h.end() + 1] == "\n" else 0)
            prefix = rec.get("prefix") if isinstance(rec.get("prefix"), str) else ""
            head = new[:h.start()]
            if prefix and tail >= len(new) and head.endswith(prefix):
                head = head[:-len(prefix)]  # the blank line loadout put before its table
            new = head + new[tail:]
            if not expected["hooks"]:
                del expected["hooks"]
    try:
        if tomllib.loads(new) != expected:
            return ["rtk config.toml: could not remove loadout's suppress_hook_warning; remove it by hand"]
    except tomllib.TOMLDecodeError:
        return ["rtk config.toml: could not remove loadout's suppress_hook_warning; remove it by hand"]
    out = ["rtk config.toml: removed loadout's suppress_hook_warning (loadout no longer provides rtk's hook)"]
    if dry_run:
        return ["rtk config.toml: to remove loadout's suppress_hook_warning (loadout no longer provides rtk's hook)"]
    if record_path().exists():
        _backup_record(bk)
    bk.save_copy(cfg, "rtk config.toml before loadout changed it")
    if rec.get("created") and not new.strip():
        cfg.unlink()
    else:
        write_atomic(cfg, new)
    _store(bk, keep, False, backed=True)
    return out
