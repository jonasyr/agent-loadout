#!/usr/bin/env python3
"""SessionStart and Stop hook: tell the user once per session when the loadout plugin was updated
after the session started (stdlib only; always exit 0; silent on any error).

The running plugin is this file's plugin folder. Claude Code records the current install in
~/.claude/plugins/installed_plugins.json. When the running copy sits in the plugin cache and no
install entry points at it any more, the session still runs the old skills and hooks until
/reload-plugins. A dev checkout (claude --plugin-dir) is outside the cache and never notified.

When the running copy is the current install, a saved "/reload-plugins" step (open-steps.json in
loadout's state folder) that loadout marked loadout_plugin (its own plugin was the one updated) is
done: this session runs the new copy. A step without the mark stays (another plugin changed; this
hook cannot see whether it was reloaded) until the next session start clears it.
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


def _install_paths(root: Path, home: Path) -> list[Path] | None:
    """The install paths Claude Code records for loadout, or None when the running copy is outside the cache."""
    cache = _resolve(home / ".claude" / "plugins" / "cache")
    if cache not in root.parents:
        return None
    data = json.loads((home / ".claude" / "plugins" / "installed_plugins.json").read_text(encoding="utf-8"))
    entries = data["plugins"][PLUGIN]
    return [_resolve(e["installPath"]) for e in entries if isinstance(e, dict) and isinstance(e.get("installPath"), str)]


def outdated(root: Path, home: Path) -> bool:
    paths = _install_paths(root, home)
    return bool(paths) and root not in paths


def current(root: Path, home: Path) -> bool:
    paths = _install_paths(root, home)
    return bool(paths) and root in paths


def state_dir(home: Path) -> Path:
    """The same rule as loadout's paths.state_dir() (this hook cannot import loadout)."""
    base = os.environ.get("XDG_STATE_HOME", "")
    root = Path(base) if base and Path(base).is_absolute() else home / ".local" / "state"
    return root / "loadout"


def clear_reload_step(home: Path) -> None:
    """Remove the saved claude/reload-plugins step marked loadout_plugin; every other step stays as it was."""
    path = state_dir(home) / "open-steps.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    entries = data.get("claude") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return
    keep = [e for e in entries if not (isinstance(e, dict) and e.get("id") == "claude/reload-plugins"
                                       and e.get("loadout_plugin") is True)]
    if len(keep) == len(entries):
        return
    if keep:
        data["claude"] = keep
    else:
        del data["claude"]
    mode = os.stat(path).st_mode & 0o7777
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        if os.name != "nt":
            os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def main() -> int:
    try:
        home = _home()
        if current(_resolve(Path(__file__)).parent.parent, home):
            clear_reload_step(home)
    except Exception:  # a hook must never break a session
        pass
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
        state.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name != "nt":
            os.chmod(state.parent, 0o700)  # private, like the rest of loadout's state
        tmp = state.with_name(f".{state.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps({"sessions": (seen + [session])[-KEEP:]}) + "\n", encoding="utf-8")
        os.replace(tmp, state)  # record first: never repeat the notice when the state cannot be written
        sys.stdout.write(json.dumps({"systemMessage": NOTICE}) + "\n")
    except Exception:  # a hook must never break a session
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
