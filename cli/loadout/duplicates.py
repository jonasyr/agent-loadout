"""Exact duplicates of what the loadout plugin ships: the only things `loadout update` removes unasked.

adopt's `migrate` verdict is a loose catalog match shown to a human first. Automatic removal needs
proof instead: the loadout plugin is enabled, and the item is the same server or hook it provides.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from . import paths, runner
from .inventory import Item
from .jsonio import get_dict, get_list, load_json

PLUGIN_ID = "loadout@agent-loadout"
# script files older codebase-memory-mcp installers put into ~/.claude/hooks (the kit replaces them)
LEGACY_SCRIPTS = {"cbm-code-discovery-gate", "cbm-session-reminder", "cbm-subagent-reminder"}
_RUN_SH = re.compile(r'^"?\$\{CLAUDE_PLUGIN_ROOT\}/hooks/run\.sh"?\s+(?:--soft\s+)?'
                     r'(?:--python\s+"?\$\{CLAUDE_PLUGIN_ROOT\}/hooks/mcp_guard\.py"?\s+\S+\s+)?')  # the guard's server


_OPERATORS = frozenset({"&&", "||", ";", "|", "&"})
_PREFIXES = frozenset({"exec", "env", "command", "nohup", "time", "sudo"})


def at_command(words: list, i: int) -> bool:
    """Whether words[i] is in a command's program position: the first word, after a shell operator, or after a
    prefix such as `env`/`exec` (and `VAR=value` assignments). A word anywhere else is an argument: `echo X`,
    `printf '%s' X` and `tool --server X` mention X, they do not run it."""
    j = i - 1
    while j >= 0 and ("=" in words[j] and not words[j].startswith("-") or words[j] in _PREFIXES):
        j -= 1
    return j < 0 or words[j] in _OPERATORS

def _plugin_dir():
    return paths.kit_root() / "plugins" / "loadout"


def plugin_enabled() -> bool:
    from .settings_merge import desired_settings
    return bool(get_dict(desired_settings(), "enabledPlugins").get(PLUGIN_ID))


def plugin_servers() -> dict:
    servers = load_json(_plugin_dir() / ".mcp.json").get("mcpServers")
    return servers if isinstance(servers, dict) else {}


def plugin_hooks() -> set[tuple[str, str, str]]:
    """(event, matcher, inner command) of each plugin hook, the command after run.sh (and the guard), e.g.
    ("PreToolUse", "Bash", "rtk hook claude")."""
    from .settings_merge import matcher_of
    out = set()
    hooks = get_dict(load_json(_plugin_dir() / "hooks" / "hooks.json"), "hooks")
    for event, groups in hooks.items() if isinstance(hooks, dict) else []:
        for group in groups if isinstance(groups, list) else []:
            for hook in get_list(group, "hooks"):
                cmd = hook.get("command", "") if isinstance(hook, dict) else ""
                if isinstance(group, dict) and _RUN_SH.match(cmd):
                    out.add((event, matcher_of(group), _norm(_RUN_SH.sub("", cmd))))
    return out


def plugin_hook_commands() -> set[str]:
    """The inner commands the plugin's hooks run (after run.sh), e.g. `rtk hook claude`."""
    return {cmd for _, _, cmd in plugin_hooks()}


def _norm(cmd: str) -> str:
    home = str(paths.home())
    words = [home + w[1:] if w == "~" or w.startswith("~/") else w for w in str(cmd).split()]
    return " ".join(w.strip("'\"") for w in words)


def _exe(command: str) -> str:
    base = os.path.basename(str(command).replace("\\", "/")).lower()
    return re.sub(r"\.(exe|cmd|bat)$", "", base)


def _personal_names() -> set[str]:
    names = set()
    for path in (paths.personal_root() / "mcp.json", paths.state_dir() / "managed-mcp.json"):
        try:
            servers = load_json(path).get("mcpServers")
        except Exception:
            continue
        names |= set(servers) if isinstance(servers, dict) else set()
    return names


def is_duplicate_mcp(item: Item) -> bool:
    cfg = item.extra.get("config", {})
    ours = plugin_servers().get(item.name)
    if not isinstance(ours, dict) or not isinstance(cfg, dict) or item.name in _personal_names():
        return False
    if cfg.get("url") or not cfg.get("command"):
        return False
    args = cfg.get("args") or []
    if not isinstance(args, list):
        return False
    # a command server's type is stdio whether or not it is written down; env: missing == empty
    return (_exe(cfg["command"]) == _exe(ours.get("command", ""))
            and sorted(map(str, args)) == sorted(map(str, ours.get("args") or []))
            and (cfg.get("type") or "stdio") == (ours.get("type") or "stdio")
            and (cfg.get("env") or {}) == (ours.get("env") or {}))


def _legacy_script(cmd: str) -> bool:
    """Exactly `<~/.claude/hooks>/cbm-x[.sh]`, optionally run by one bare `bash`/`sh` word."""
    words = cmd.split()
    if len(words) == 2 and words[0] in ("bash", "sh"):
        words = words[1:]
    if len(words) != 1:
        return False
    path = os.path.normpath(words[0])
    hooks_dir = os.path.normpath(str(paths.claude_home() / "hooks"))
    return os.path.dirname(path) == hooks_dir and is_legacy_script_file(os.path.basename(path))


def is_duplicate_hook(item: Item) -> bool:
    """The same command under the same event and matcher as a plugin hook (item.name is `Event:matcher`, maybe
    with `#n`), or an old codebase-memory hook script. The same command under another matcher stays the user's."""
    cmd = _norm(item.detail)
    event, _, matcher = re.sub(r"#\d+$", "", item.name).partition(":")
    return (event, matcher, cmd) in plugin_hooks() or _legacy_script(cmd)


def is_legacy_script_file(name: str) -> bool:
    return (name[:-3] if name.endswith(".sh") else name) in LEGACY_SCRIPTS


def would_refuse_undo(item: Item) -> bool:
    """A user-scope MCP removal whose undo (add-json) could not run here (Windows .cmd shim)."""
    if item.kind != "mcp" or item.location != "~/.claude.json":
        return False
    cfg = json.dumps(item.extra.get("config", {}))
    return runner.would_refuse(["claude", "mcp", "add-json", "-s", "user", item.name, cfg])


NOT_A_RUN = frozenset({"echo", "printf", "#"})  # mirrors mcp_guard.NOT_A_RUN: `echo serena-hooks remind` mentions it


def user_settings_files(cwd: str | None = None) -> list[tuple[str, "Path"]]:
    """(label, path) of the Claude Code settings files whose hooks run next to the plugin's (mirrors mcp_guard)."""
    base = Path(cwd) if cwd else Path.cwd()
    return [("~/.claude/settings.json", paths.claude_home() / "settings.json"),
            (".claude/settings.json", base / ".claude" / "settings.json"),
            (".claude/settings.local.json", base / ".claude" / "settings.local.json")]


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


def _hook_words(hook: dict) -> list[str]:
    command = hook.get("command")
    words = _split(command) if isinstance(command, str) else []
    return words + [a for a in get_list(hook, "args") if isinstance(a, str)]


def user_hook_entries(cwd: str | None = None) -> list[tuple[str, str, list[str], str]]:
    """(event, matcher, words, file label) of every hook in the user's and the project's Claude Code settings."""
    from .settings_merge import matcher_of
    out = []
    for label, path in user_settings_files(cwd):
        try:
            data = load_json(path)
        except Exception:
            continue
        for event, groups in get_dict(data, "hooks").items():
            for group in get_list({"g": groups}, "g"):
                for hook in get_list(group, "hooks"):
                    if isinstance(hook, dict) and isinstance(group, dict):
                        out.append((event, matcher_of(group), _hook_words(hook), label))
    return out


def user_hooks(cwd: str | None = None) -> list[tuple[str, list[str], str]]:
    """(event, words, file label) of every hook in the user's and the project's Claude Code settings."""
    return [(event, words, label) for event, _, words, label in user_hook_entries(cwd)]


def runs_program(words: list[str], program: str, sub: str | None = None) -> bool:
    """mcp_guard.users_hook_runs for one hook: a word whose basename is program, not right after echo/printf/#,
    and the first non-flag word after it is sub (when given)."""
    for i, w in enumerate(words):
        if _program(w) != program or (i and words[i - 1] in NOT_A_RUN):
            continue
        rest = [x for x in words[i + 1:] if not x.startswith("-")]
        if sub is None or rest[:1] == [sub]:
            return True
    return False


def plugin_guarded_hooks(program: str) -> list[tuple[str, str]]:
    """(event, inner command) of the plugin's hooks that run <program> through the guard."""
    out = []
    hooks = get_dict(load_json(_plugin_dir() / "hooks" / "hooks.json"), "hooks")
    for event, groups in hooks.items():
        for group in get_list({"g": groups}, "g"):
            for hook in get_list(group, "hooks"):
                cmd = hook.get("command", "") if isinstance(hook, dict) else ""
                inner = _norm(_RUN_SH.sub("", cmd)) if _RUN_SH.match(cmd) else ""
                words = inner.split()
                if words and os.path.basename(words[0]) == program:
                    out.append((event, inner))
    return out


def equivalent_user_hooks(cwd: str | None = None) -> list[tuple[str, str, str]]:
    """(event, command, file) of the user's own Serena hooks that make the plugin's guarded copy go silent
    (mcp_guard.users_hook_runs). Exact duplicates of the plugin's are left out: `loadout update` removes them."""
    found = []
    for event, inner in plugin_guarded_hooks("serena-hooks"):
        words = inner.split()
        sub = next((w for w in words[1:] if not w.startswith("-")), None)
        for ev, matcher, hwords, label in user_hook_entries(cwd):
            if ev == event and runs_program(hwords, os.path.basename(words[0]), sub):
                command = " ".join(hwords)
                exact = label == "~/.claude/settings.json" and \
                    is_duplicate_hook(Item("hook", f"{event}:{matcher}", command, label, {}))
                if not exact:  # only the user file's exact copies go on update (ADR 0035)
                    found.append((event, command, label))
    return found


def plugin_server_off(server: str, cwd: str) -> bool:
    """Claude Code has the plugin's <server> switched off for cwd or its nearest parent project
    (`disabledMcpServers`; mirrors mcp_guard._project)."""
    from pathlib import Path
    try:
        projects = get_dict(load_json(paths.home() / ".claude.json"), "projects")
    except Exception:
        return False
    path = Path(cwd)
    for folder in (path, *path.parents):
        for key in (str(folder), folder.as_posix()):
            if key in projects:
                off = get_list(get_dict(projects, key), "disabledMcpServers")
                return f"plugin:loadout:{server}" in off
    return False
