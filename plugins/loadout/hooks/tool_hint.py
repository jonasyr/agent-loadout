"""Docs hint (stdlib only, no network; always exit 0, silent on error; never blocks).

PreToolUse WebSearch|WebFetch on library docs (Claude Code): one fact naming Context7 and Microsoft Learn, at most
once per SPACING lookups. Code searches are Serena's own `remind` hook now (ADR 0039).
State: <state_dir>/tool-hint/<session_id>.json. See docs/reference/hooks.md."""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

SPACING = 10
MAX_CHARS = 300
KEEP_DAYS = 7
MAX_INPUT = 200_000

SESSION = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

DOCS_HOST = re.compile(r"(^|\.)(docs|developer|learn|api|reference)\.|readthedocs\.io|docs\.rs|pkg\.go\.dev|"
                       r"pypi\.org|npmjs\.com|developer\.mozilla\.org|docs\.python\.org|learn\.microsoft\.com",
                       re.I)
DOCS_WORDS = re.compile(r"\b(docs?|documentation|api|reference|sdk|library|package|framework|changelog|"
                        r"migration guide|usage example)\b", re.I)
DOCS_HINT = ("Library or API docs: Context7 first (`resolve-library-id`, then `query-docs`); Microsoft Learn for "
             ".NET, Azure and Windows; web search last.")

def state_dir() -> Path:
    """The same rule as loadout's paths.state_dir() (this hook cannot import loadout)."""
    home = os.environ.get("HOME") or os.environ.get("USERPROFILE") or str(Path.home())
    base = os.environ.get("XDG_STATE_HOME", "")
    root = Path(base) if base and Path(base).is_absolute() else Path(home) / ".local" / "state"
    return root / "loadout" / "tool-hint"


def _load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(path: Path, data: dict) -> None:
    # loadout's state folder is private (0700), like the CLI keeps it; created here when the hook runs first
    path.parent.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.mkdir(mode=0o700, exist_ok=True)
    import tempfile  # imported here: only a counted search writes state
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    os.replace(tmp, path)


def _clean(folder: Path) -> None:
    cutoff = time.time() - KEEP_DAYS * 86400
    try:
        for entry in os.scandir(folder):
            if entry.name.endswith(".json") and entry.stat().st_mtime < cutoff:
                os.unlink(entry.path)
    except OSError:
        pass


def _int(data: dict, key: str, default: int) -> int:
    v = data.get(key)
    return v if isinstance(v, int) and not isinstance(v, bool) else default


def _emit(event: str, text: str) -> None:
    out = {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text[:MAX_CHARS]}}
    sys.stdout.write(json.dumps(out))


def handle(payload: dict) -> None:
    session = payload.get("session_id")
    if not isinstance(session, str) or not SESSION.match(session):
        return
    if payload.get("hook_event_name") != "PreToolUse":
        return
    raw_input = payload.get("tool_input")
    if not docs_event(payload.get("tool_name") or "", raw_input if isinstance(raw_input, dict) else {}):
        return
    folder = state_dir()
    path = folder / f"{session}.json"
    fresh = not path.exists()
    state = _load(path)
    calls = _int(state, "calls", 0) + 1
    state["calls"] = calls
    text = None
    if calls - _int(state, "last_docs", -SPACING) >= SPACING:
        text, state["last_docs"] = DOCS_HINT, calls
        state["hint_at"] = time.time()  # when the last hint was shown: `loadout usage` counts it by this
    _save(path, state)
    if fresh:
        _clean(folder)
    if text:
        _emit("PreToolUse", text)


def docs_event(tool: str, tool_input: dict) -> bool:
    if tool == "WebFetch":
        url = tool_input.get("url")
        if not isinstance(url, str):
            return False
        host = re.sub(r"^[a-z]+://", "", url, flags=re.I).split("/", 1)[0]
        return bool(DOCS_HOST.search(host))
    if tool == "WebSearch":
        query = tool_input.get("query")
        return isinstance(query, str) and len(query) < 500 and bool(DOCS_WORDS.search(query))
    return False


def main() -> int:
    try:
        raw = sys.stdin.read(MAX_INPUT + 1)
        if len(raw) > MAX_INPUT:
            return 0
        payload = json.loads(raw)
        if isinstance(payload, dict):
            handle(payload)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
