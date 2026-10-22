#!/usr/bin/env python3
"""Run an MCP tool's own hook command only when it can help (stdlib only; always exit 0; silent on error).

    mcp_guard.py <server> <command...>      e.g. mcp_guard.py serena serena-hooks remind --client=claude-code

Skips when the command's program is not on PATH, when Claude Code has <server> switched off for this folder (and
the user has no server of that name of their own that is on), or when the user's or the project's Claude Code
settings already run the same program and subcommand for this event (two `remind`s would share one counter and
deny at half the threshold). Otherwise runs the command with the hook's input and passes its output on.
See docs/reference/hooks.md."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

MAX_INPUT = 200_000
PLUGIN = "loadout"
TIMEOUT = 60  # the hook's own timeout in hooks.json is shorter and wins


def _home() -> Path:
    return Path(os.environ.get("HOME") or os.environ.get("USERPROFILE") or str(Path.home()))


def _json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _dict(d: object, key: str) -> dict:
    v = d.get(key) if isinstance(d, dict) else None
    return v if isinstance(v, dict) else {}


def _list(d: object, key: str) -> list:
    v = d.get(key) if isinstance(d, dict) else None
    return v if isinstance(v, list) else []


def binary_on_path(program: str) -> bool:
    return shutil.which(program) is not None


def server_available(server: str, cwd: str, home: Path) -> bool:
    """False when Claude Code has the plugin's <server> off for this folder and the user has no <server> of their
    own that is on there (`disabledMcpServers` names plugin servers `plugin:<plugin>:<server>`)."""
    config = _json(home / ".claude.json")
    project = _dict(_dict(config, "projects"), cwd)
    off = {s for s in _list(project, "disabledMcpServers") if isinstance(s, str)}
    if f"plugin:{PLUGIN}:{server}" not in off and server not in off:
        return True
    own = server in _dict(config, "mcpServers") or server in _dict(project, "mcpServers") or \
        server in _dict(_json(Path(cwd) / ".mcp.json"), "mcpServers")
    return own and server not in off


def _words(hook: dict) -> list[str]:
    command = hook.get("command")
    words = command.split() if isinstance(command, str) else []
    return words + [a for a in _list(hook, "args") if isinstance(a, str)]


def users_hook_runs(event: str, argv: list[str], cwd: str, home: Path) -> bool:
    """A hook of the user's or the project's for <event> that runs the same program and subcommand as argv."""
    program, sub = os.path.basename(argv[0]), argv[1] if len(argv) > 1 else None
    files = (home / ".claude" / "settings.json", Path(cwd) / ".claude" / "settings.json",
             Path(cwd) / ".claude" / "settings.local.json")
    for path in files:
        for group in _list(_dict(_json(path), "hooks"), event):
            for hook in _list(group, "hooks"):
                words = _words(hook) if isinstance(hook, dict) else []
                for i, w in enumerate(words):
                    if os.path.basename(w.strip("'\"")) == program and (sub is None or words[i + 1:i + 2] == [sub]):
                        return True
    return False


def should_run(server: str, argv: list[str], payload: dict, home: Path) -> bool:
    raw_cwd = payload.get("cwd")
    cwd = raw_cwd if isinstance(raw_cwd, str) else os.getcwd()
    if not argv or not binary_on_path(argv[0]):
        return False
    if not server_available(server, cwd, home):
        return False
    event = payload.get("hook_event_name")
    return not (isinstance(event, str) and users_hook_runs(event, argv, cwd, home))


def main(args: list[str]) -> int:
    try:
        if len(args) < 2:
            return 0
        server, argv = args[0], args[1:]
        raw = sys.stdin.read(MAX_INPUT + 1)
        if len(raw) > MAX_INPUT:
            return 0
        payload = json.loads(raw)
        if not isinstance(payload, dict) or not should_run(server, argv, payload, _home()):
            return 0
        res = subprocess.run(argv, input=raw, capture_output=True, text=True, timeout=TIMEOUT)
        if res.returncode == 0:
            sys.stdout.write(res.stdout)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
