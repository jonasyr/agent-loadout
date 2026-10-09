"""Exact duplicates of what the loadout plugin ships: the only things `loadout update` removes unasked.

adopt's `migrate` verdict is a loose catalog match shown to a human first. Automatic removal needs
proof instead: the loadout plugin is enabled, and the item is the same server or hook it provides.
"""
from __future__ import annotations

import json
import os
import re

from . import paths, runner
from .inventory import Item
from .jsonio import load_json

PLUGIN_ID = "loadout@agent-loadout"
# script files older codebase-memory-mcp installers put into ~/.claude/hooks (the kit replaces them)
LEGACY_SCRIPTS = {"cbm-code-discovery-gate", "cbm-session-reminder", "cbm-subagent-reminder"}
_RUN_SH = re.compile(r'^"?\$\{CLAUDE_PLUGIN_ROOT\}/hooks/run\.sh"?\s+(?:--soft\s+)?')


def _plugin_dir():
    return paths.kit_root() / "plugins" / "loadout"


def plugin_enabled() -> bool:
    from .settings_merge import desired_settings
    return bool(desired_settings().get("enabledPlugins", {}).get(PLUGIN_ID))


def plugin_servers() -> dict:
    servers = load_json(_plugin_dir() / ".mcp.json").get("mcpServers")
    return servers if isinstance(servers, dict) else {}


def plugin_hook_commands() -> set[str]:
    """The inner commands the plugin's hooks run (after run.sh), e.g. `rtk hook claude`."""
    out = set()
    hooks = load_json(_plugin_dir() / "hooks" / "hooks.json").get("hooks", {})
    for groups in hooks.values() if isinstance(hooks, dict) else []:
        for group in groups if isinstance(groups, list) else []:
            for hook in group.get("hooks", []) if isinstance(group, dict) else []:
                cmd = hook.get("command", "") if isinstance(hook, dict) else ""
                if _RUN_SH.match(cmd):
                    out.add(_norm(_RUN_SH.sub("", cmd)))
    return out


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
    return (_exe(cfg["command"]) == _exe(ours.get("command", ""))
            and sorted(map(str, args)) == sorted(map(str, ours.get("args") or [])))


def _legacy_script(cmd: str) -> bool:
    words = cmd.split()
    if not words:
        return False
    name = os.path.basename(words[-1])
    name = name[:-3] if name.endswith(".sh") else name
    hooks_dir = str(paths.claude_home() / "hooks")
    return name in LEGACY_SCRIPTS and words[-1].startswith(hooks_dir)


def is_duplicate_hook(item: Item) -> bool:
    cmd = _norm(item.detail)
    return cmd in plugin_hook_commands() or _legacy_script(cmd)


def is_legacy_script_file(name: str) -> bool:
    return (name[:-3] if name.endswith(".sh") else name) in LEGACY_SCRIPTS


def would_refuse_undo(item: Item) -> bool:
    """A user-scope MCP removal whose undo (add-json) could not run here (Windows .cmd shim)."""
    if item.kind != "mcp" or item.location != "~/.claude.json":
        return False
    cfg = json.dumps(item.extra.get("config", {}))
    return runner.would_refuse(["claude", "mcp", "add-json", "-s", "user", item.name, cfg])
