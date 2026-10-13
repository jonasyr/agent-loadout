#!/usr/bin/env python3
"""SessionStart and Stop hook: tell the user once per session when the loadout plugin was updated
after the session started (stdlib only; always exit 0; silent on any error).

The running plugin is this file's plugin folder. Claude Code records the current install in
~/.claude/plugins/installed_plugins.json. When the running copy sits in the plugin cache and no
install entry points at it any more, the session still runs the old skills and hooks until
/reload-plugins. A dev checkout (claude --plugin-dir) is outside the cache and never notified.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PLUGIN = "loadout@agent-loadout"
KEEP = 20
NOTICE = ("loadout: the plugin was updated after this session started. "
          "Run /reload-plugins to load the new skills and hooks.")


def _home() -> Path:
    return Path(os.environ.get("HOME") or os.environ.get("USERPROFILE") or str(Path.home()))


def _resolve(p: str | Path) -> Path:
    return Path(p).expanduser().resolve()


def outdated(root: Path, home: Path) -> bool:
    cache = _resolve(home / ".claude" / "plugins" / "cache")
    if cache not in root.parents:
        return False
    data = json.loads((home / ".claude" / "plugins" / "installed_plugins.json").read_text(encoding="utf-8"))
    entries = data["plugins"][PLUGIN]
    paths = [_resolve(e["installPath"]) for e in entries if isinstance(e, dict) and isinstance(e.get("installPath"), str)]
    return bool(paths) and root not in paths


def state_dir(home: Path) -> Path:
    """The same rule as loadout's paths.state_dir() (this hook cannot import loadout)."""
    base = os.environ.get("XDG_STATE_HOME", "")
    root = Path(base) if base and Path(base).is_absolute() else home / ".local" / "state"
    return root / "loadout"


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
        session = payload.get("session_id") if isinstance(payload, dict) else None
        if not isinstance(session, str) or not session:
            return 0
        home = _home()
        if not outdated(_resolve(Path(__file__)).parent.parent, home):
            return 0
        state = state_dir(home) / "reload-notified.json"
        try:
            seen = json.loads(state.read_text(encoding="utf-8")).get("sessions", [])
            seen = [s for s in seen if isinstance(s, str)] if isinstance(seen, list) else []
        except (OSError, ValueError, AttributeError):
            seen = []
        if session in seen:
            return 0
        state.parent.mkdir(parents=True, exist_ok=True)
        tmp = state.with_name(f".{state.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps({"sessions": (seen + [session])[-KEEP:]}) + "\n", encoding="utf-8")
        os.replace(tmp, state)  # record first: never repeat the notice when the state cannot be written
        sys.stdout.write(json.dumps({"systemMessage": NOTICE}) + "\n")
    except Exception:  # a hook must never break a session
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
