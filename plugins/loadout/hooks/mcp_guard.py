#!/usr/bin/env python3
"""Run an MCP tool's own hook command only when it can help (stdlib only; always exit 0; silent on error).

    mcp_guard.py [--agent claude|codex] <server> <command...>
                                            e.g. mcp_guard.py serena serena-hooks remind --client=claude-code

Skips when the command's program is not on PATH, when Claude Code has <server> switched off for this folder (and
the user has no server of that name of their own that is on), or when the user's or the project's Claude Code
settings already run the same program and subcommand for this event (two `remind`s would share one counter and
deny at half the threshold). For `remind` it also skips a call that is only a harmless search (harmless.py: config
or doc files, piped output, files outside the project). With `--agent codex` it decides by Codex's files only
(config.toml's `[mcp_servers.<server>]` and the hooks in $CODEX_HOME/hooks.json, config.toml's `[hooks]` and
<cwd>/.codex/hooks.json; a regex matcher is searched, not matched whole). Otherwise runs the command with the hook's input and passes its output on.
See docs/reference/hooks.md."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

MAX_INPUT = 200_000
PLUGIN = "loadout"
# the inner command ends just before its hook's timeout in hooks.json (Serena's activate 15 s, cleanup and
# auto-approve 10 s, everything else 5 s), so a hung command ends silently instead of as a hook timeout
TIMEOUTS = {"activate": 14, "cleanup": 9, "auto-approve": 9}
TIMEOUT = 4
NOT_A_RUN = frozenset({"echo", "printf", "#"})  # `echo serena-hooks remind` mentions the command, it does not run it


def _home() -> Path:
    order = ("USERPROFILE", "HOME") if os.name == "nt" else ("HOME", "USERPROFILE")  # Claude Code: os.homedir()
    return Path(next((os.environ[k] for k in order if os.environ.get(k)), None) or str(Path.home()))


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


def _project(config: dict, cwd: str) -> dict:
    """The `projects` entry for cwd or its nearest parent; Claude Code keys them by path (forward slashes on
    Windows)."""
    projects = _dict(config, "projects")
    path = Path(cwd)
    for folder in (path, *path.parents):
        for key in (str(folder), folder.as_posix()):
            if key in projects:
                return _dict(projects, key)
    return {}


def _settings_files(cwd: str, home: Path) -> tuple[Path, ...]:
    return (home / ".claude" / "settings.json", Path(cwd) / ".claude" / "settings.json",
            Path(cwd) / ".claude" / "settings.local.json")


def server_available(server: str, cwd: str, home: Path) -> bool:
    """False when Claude Code has the plugin's <server> off for this folder and the user has no <server> of their
    own that is on there (`disabledMcpServers` names plugin servers `plugin:<plugin>:<server>`; a project
    `.mcp.json` server can also be off through `disabledMcpjsonServers` in the settings)."""
    config = _json(home / ".claude.json")
    project = _project(config, cwd)
    off = {s for s in _list(project, "disabledMcpServers") if isinstance(s, str)}
    if f"plugin:{PLUGIN}:{server}" not in off and server not in off:
        return True
    if server in _dict(config, "mcpServers") or server in _dict(project, "mcpServers"):
        return server not in off
    json_off = {s for path in _settings_files(cwd, home) for s in _list(_json(path), "disabledMcpjsonServers")}
    return server in _dict(_json(Path(cwd) / ".mcp.json"), "mcpServers") and server not in off | json_off


CBM = "codebase-memory-mcp"
LOADOUT_PLUGIN = "loadout@agent-loadout"


def is_cbm(table: dict) -> bool:
    """Same rule as loadout's codex.is_cbm (a test keeps them equal; hooks cannot import loadout)."""
    command, args = table.get("command"), table.get("args")
    if not isinstance(command, str):
        return False
    base = re.split(r"[\\/]", command)[-1].lower()
    base = base[:-4] if base.endswith(".exe") else base
    if base == CBM:
        return True
    return base in ("npx", "bunx", "uvx", "uv") and isinstance(args, list) and any(
        isinstance(a, str) and CBM in a for a in args)


def codex_server_enabled(server: str, home: Path) -> bool:
    """False only when Codex's config.toml switches <server> off (`[mcp_servers.<server>] enabled = false`).
    codebase-memory is also on when the loadout plugin is off but a table of yours (any name) starts it, and when
    your table of the plugin's name is off but another of yours runs it."""
    root = Path(os.environ["CODEX_HOME"]) if os.environ.get("CODEX_HOME") else home / ".codex"
    try:
        import tomllib
        with open(root / "config.toml", "rb") as fh:
            data = tomllib.load(fh)
    except Exception:
        return True
    servers = _dict(data, "mcp_servers")
    table = _dict(servers, server)
    if server == CBM:
        plugin_on = _dict(_dict(data, "plugins"), LOADOUT_PLUGIN).get("enabled") is not False
        if plugin_on and table.get("enabled") is not False:
            return True
        return any(isinstance(t, dict) and is_cbm(t) and t.get("enabled") is not False for t in servers.values())
    return table.get("enabled") is not False


def available(server: str, agent: str, cwd: str, home: Path) -> bool:
    """The server's binary is on PATH and the agent has it on: Claude Code by its per-folder switch, Codex by its
    config.toml. Each agent reads only its own files."""
    if not binary_on_path(server):
        return False
    return codex_server_enabled(server, home) if agent == "codex" else server_available(server, cwd, home)


def _split(command: str) -> list[str]:
    """A hook command's words, a quoted path with spaces kept whole (shlex; plain split if it cannot parse)."""
    import shlex
    try:
        return shlex.split(command.replace("\\", "/"))
    except ValueError:
        return command.split()


def _program(word: str) -> str:
    """A word's program name: its basename without quotes, either slash, or a Windows .exe/.cmd/.bat suffix."""
    base = word.strip("'\"").replace("\\", "/").rsplit("/", 1)[-1]
    return base[:-4] if base.lower().endswith((".exe", ".cmd", ".bat")) else base


def _words(hook: dict) -> list[str]:
    command = hook.get("command")
    words = _split(command) if isinstance(command, str) else []
    return words + [a for a in _list(hook, "args") if isinstance(a, str)]


def _matches(matcher: object, tool: str | None, search: bool = False) -> bool:
    """Claude Code's matcher rule: none, "" or "*" matches every tool, else a regex over the tool name (Codex
    searches it, `search=True`)."""
    if tool is None or matcher in (None, "", "*"):
        return True
    if not isinstance(matcher, str):
        return False
    import re
    try:
        return (re.search if search else re.fullmatch)(matcher, tool) is not None
    except re.error:
        return matcher == tool


def _group_runs(groups: list, argv: list[str], tool: str | None, search: bool) -> bool:
    program, sub = os.path.basename(argv[0]), argv[1] if len(argv) > 1 else None
    for group in groups:
        if not _matches(group.get("matcher") if isinstance(group, dict) else None, tool, search):
            continue
        for hook in _list(group, "hooks"):
            words = _words(hook) if isinstance(hook, dict) else []
            for i, w in enumerate(words):
                if _program(w) != program or (i and words[i - 1] in NOT_A_RUN):
                    continue
                rest = [x for x in words[i + 1:] if not x.startswith("-")]  # flags may come first
                if sub is None or rest[:1] == [sub]:
                    return True
    return False


def users_hook_runs(event: str, argv: list[str], cwd: str, home: Path, tool: str | None = None) -> bool:
    """A hook of the user's or the project's for <event> (and, when given, a matcher that matches <tool>) that runs
    the same program and subcommand as argv."""
    return any(_group_runs(_list(_dict(_json(path), "hooks"), event), argv, tool, False)
               for path in _settings_files(cwd, home))


def _codex_groups(event: str, cwd: str, home: Path) -> list:
    """Codex's hook groups for <event>: $CODEX_HOME (or ~/.codex) hooks.json, <cwd>/.codex/hooks.json and the
    `[hooks]` tables of its config.toml."""
    root = Path(os.environ["CODEX_HOME"]) if os.environ.get("CODEX_HOME") else home / ".codex"
    groups = (_list(_dict(_json(root / "hooks.json"), "hooks"), event)
              + _list(_dict(_json(Path(cwd) / ".codex" / "hooks.json"), "hooks"), event))
    try:
        import tomllib
        with open(root / "config.toml", "rb") as fh:
            groups += _list(_dict(tomllib.load(fh), "hooks"), event)
    except Exception:
        pass
    return groups


def codex_users_hook_runs(argv: list[str], cwd: str, home: Path, tool: str | None) -> bool:
    """The same for Codex's PreToolUse hooks: a matcher is a regex searched in the tool name. loadout's own
    `remind` entry in hooks.json counts, so the plugin's copy and that entry never both remind."""
    return _group_runs(_codex_groups("PreToolUse", cwd, home), argv, tool, True)


def _groups_run_any(groups: list, programs: set[str]) -> bool:
    """Some hook in <groups> runs one of <programs> (any subcommand; not right after echo/printf/#)."""
    for group in groups:
        for hook in _list(group, "hooks"):
            words = _words(hook) if isinstance(hook, dict) else []
            if any(_program(w) in programs and not (i and words[i - 1] in NOT_A_RUN) for i, w in enumerate(words)):
                return True
    return False


def runs_program(event: str, programs: set[str], cwd: str, home: Path, agent: str = "claude") -> bool:
    """The agent's own hooks (Claude Code: the settings files; Codex: its hook files) hold, for <event>, a hook
    that runs one of <programs>, whatever the matcher and subcommand."""
    if agent == "codex":
        return _groups_run_any(_codex_groups(event, cwd, home), programs)
    return any(_groups_run_any(_list(_dict(_json(path), "hooks"), event), programs)
               for path in _settings_files(cwd, home))


def should_run(server: str, argv: list[str], payload: dict, home: Path, agent: str = "claude") -> bool:
    raw_cwd = payload.get("cwd")
    cwd = raw_cwd if isinstance(raw_cwd, str) else os.getcwd()
    if not argv or not binary_on_path(argv[0]):
        return False
    if len(argv) > 1 and argv[1] == "remind":
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        try:
            from harmless import skips_remind  # lazily: only the reminder is filtered
        except ImportError:  # no classifier: Serena decides, as before the filter
            skips_remind = None
        if skips_remind is not None and skips_remind(payload):
            return False
    raw_tool = payload.get("tool_name")
    tool = raw_tool if isinstance(raw_tool, str) and raw_tool else None
    if agent == "codex":
        return codex_server_enabled(server, home) and not codex_users_hook_runs(argv, cwd, home, tool)
    if not server_available(server, cwd, home):
        return False
    event = payload.get("hook_event_name")
    return not (isinstance(event, str) and users_hook_runs(event, argv, cwd, home, tool))


def main(args: list[str]) -> int:
    if args[:1] == ["--available"]:  # `--available AGENT SERVER...`: exit 0 when the agent has them all here
        try:
            payload = json.loads(sys.stdin.read(MAX_INPUT))
            cwd = payload.get("cwd") if isinstance(payload, dict) and isinstance(payload.get("cwd"), str) else None
            ok = len(args) > 2 and all(available(srv, args[1], cwd or os.getcwd(), _home()) for srv in args[2:])
            return 0 if ok else 1
        except Exception:
            return 1
    try:
        agent = "claude"
        if args[:1] == ["--agent"] and len(args) > 1:
            agent, args = args[1], args[2:]
        if len(args) < 2:
            return 0
        server, argv = args[0], args[1:]
        raw = sys.stdin.read(MAX_INPUT + 1)
        if len(raw) > MAX_INPUT:
            return 0
        payload = json.loads(raw)
        if not isinstance(payload, dict) or not should_run(server, argv, payload, _home(), agent):
            return 0
        timeout = TIMEOUTS.get(argv[1], TIMEOUT) if len(argv) > 1 else TIMEOUT
        res = subprocess.run(argv, input=raw, capture_output=True, text=True, timeout=timeout)
        if res.returncode == 0:  # a hook's answer is JSON on exit 0 (Serena's deny too); other exits stay silent
            sys.stdout.write(res.stdout)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
