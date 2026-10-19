""""Now do this": the steps a person still has to do after a run, per agent. `derive` names them from what a run
changed; they are saved (open-steps.json in the state folder) and shown at that agent's next session start until
they are done. An agent that is off never gets or shows a step."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass

from . import paths
from .jsonio import get_dict, load_json, save_json

NAMES = {"claude": "Claude Code", "codex": "Codex"}
HOOKS_TEXT = "start codex and approve the changed hooks in /hooks"
BOOTSTRAP_ROWS = {"MCP servers on PATH", "secrets.env", "VS Code PATH"}  # rows only `loadout bootstrap` fixes
HOOK_FACTS = {"serena_hooks_added", "codex_plugins_installed", "codex_plugins_updated"}
CLAUDE_FACTS = {"claude_plugins_installed", "claude_plugins_updated", "claude_marketplace_added"}


@dataclass
class Step:
    id: str  # "<agent>/<what>", the key steps merge and clear by
    agent: str  # claude or codex
    text: str  # what to do, imperative
    reason: str  # why, for the person reading the file


def _path():
    return paths.state_dir() / "open-steps.json"


def _load() -> dict[str, list[dict]]:
    try:
        data = load_json(_path())
    except Exception:  # a broken file is no list of steps; the next save writes a fresh one
        return {}
    return {a: [e for e in data.get(a, []) if isinstance(e, dict) and isinstance(e.get("id"), str)
                and isinstance(e.get("text"), str)]
            for a in NAMES if isinstance(data.get(a), list)}


def save(new: list[Step]) -> None:
    """Merge into the saved steps by id (a step already open keeps its first time)."""
    if not new:
        return
    data = _load()
    for step in new:
        if step.agent not in NAMES:
            continue
        entries = data.setdefault(step.agent, [])
        for e in entries:
            if e["id"] == step.id:
                e.update(text=step.text, reason=step.reason)
                break
        else:
            entries.append({"id": step.id, "text": step.text, "reason": step.reason, "since": time.time()})
    _path().parent.mkdir(parents=True, exist_ok=True)
    save_json(_path(), data)


def pending(agent: str) -> list[Step]:
    return [Step(e["id"], agent, e["text"], str(e.get("reason", ""))) for e in _load().get(agent, [])]


def clear(agent: str, ids: set[str]) -> None:
    data = _load()
    if not ids or not any(e["id"] in ids for e in data.get(agent, [])):
        return
    data[agent] = [e for e in data[agent] if e["id"] not in ids]
    save_json(_path(), {a: v for a, v in data.items() if v})


def render(items: list[Step], claude_on: bool, codex_on: bool) -> list[str]:
    """Lines like "1. Claude Code: ...", numbered across the agents that are on."""
    on = {"claude": claude_on, "codex": codex_on}
    shown = [s for s in items if on.get(s.agent)]
    return [f"{n}. {NAMES[s.agent]}: {s.text}" for n, s in enumerate(shown, 1)]


def block(items: list[Step], claude_on: bool, codex_on: bool, indent: str = "  ") -> list[str]:
    lines = render(items, claude_on, codex_on)
    return ["Now do this", *(indent + line for line in lines)] if lines else []


# --- which MCP servers a binary starts ---------------------------------------------------------------------------

def _starts(table, binary_id: str) -> bool:
    if not isinstance(table, dict) or not isinstance(table.get("command"), str):
        return False
    base = re.split(r"[\\/]", table["command"])[-1].lower().removesuffix(".exe")
    if base == binary_id.lower():
        return True
    args = table.get("args")
    return base in ("uv", "uvx") and isinstance(args, list) and any(
        isinstance(a, str) and binary_id.lower() in a.lower() for a in args)


def _servers(file) -> dict:
    try:
        return get_dict(load_json(file), "mcpServers")
    except Exception:
        return {}


def _claude_wants_plugin() -> bool:
    from . import check, settings_merge
    try:
        return bool(get_dict(settings_merge.desired_settings(), "enabledPlugins").get(check.PLUGIN_ID))
    except Exception:
        return False


def mcp_servers_started_by(binary_id: str) -> dict[str, list[str]]:
    """The MCP servers whose command is this binary, per agent that is on, by the command's file name (without .exe;
    uv and uvx by their arguments): the loadout plugin's, Claude Code's own list and your personal servers for Claude
    Code; Codex's config.toml and the plugins Codex has for Codex. The loadout plugin's servers show as Claude Code
    lists them (plugin:loadout:<name>)."""
    from . import codex, targets
    found: dict[str, list[str]] = {"claude": [], "codex": []}
    plugin = _servers(paths.kit_root() / "plugins" / "loadout" / ".mcp.json")
    if targets.claude_enabled():
        if _claude_wants_plugin():
            found["claude"] += [f"plugin:loadout:{n}" for n, t in plugin.items() if _starts(t, binary_id)]
        for source in (_servers(paths.claude_json()), _servers(paths.personal_root() / "mcp.json")):
            found["claude"] += [n for n, t in source.items() if _starts(t, binary_id) and n not in found["claude"]]
    if targets.codex_enabled():
        found["codex"] += [n for n, t in plugin.items() if _starts(t, binary_id)]
        try:
            tl = codex._tomllib()
            cfg = paths.codex_home() / "config.toml"
            data = tl.loads(cfg.read_text(encoding="utf-8")) if cfg.exists() else {}
            found["codex"] += [n for n, t in get_dict(data, "mcp_servers").items() if _starts(t, binary_id)]
        except Exception:
            pass
        for root in (paths.codex_home() / "plugins" / "cache").glob("*/*/*"):
            found["codex"] += [n for n, t in _servers(root / ".mcp.json").items() if _starts(t, binary_id)]
        found["codex"] = list(dict.fromkeys(found["codex"]))
    return found


# --- the steps a run leaves ----------------------------------------------------------------------------------------

def _plugin_copy_differs() -> bool:
    """The loadout plugin Claude Code has installed differs from the kit's (an old copy runs old hooks)."""
    from . import check
    try:
        return any(not r.ok for r in check._plugin_copies() if r.name.startswith("loadout plugin (Claude Code"))
    except Exception:
        return False


def derive(facts: set[str], upgraded: list[str], claude_on: bool, codex_on: bool, results: list | None = None) -> list[Step]:
    """The steps a run leaves, for the agents that are on. facts: the apply steps' facts and the plugin refresh's;
    upgraded: the tool ids a run updated or installed; results: the health check's rows (bootstrap-only needs)."""
    from . import codex
    out: list[Step] = []
    if claude_on and (facts & CLAUDE_FACTS or _plugin_copy_differs()):
        out.append(Step("claude/reload-plugins", "claude", "run /reload-plugins (or restart Claude Code)",
                        "Claude Code plugins were installed or updated"))
    restart = False
    for binary in dict.fromkeys(upgraded):
        found = mcp_servers_started_by(binary)
        if claude_on:
            for name in found["claude"]:
                out.append(Step(f"claude/mcp:{name}", "claude", f"run /mcp and reconnect {name} (it was upgraded)",
                                f"{binary} was upgraded and starts this MCP server"))
        restart = restart or bool(codex_on and found["codex"])
    if restart:
        out.append(Step("codex/restart", "codex", "restart Codex", "an upgraded binary starts one of its MCP servers"))
    if codex_on:
        status = None
        try:
            status = codex.hooks_status()
        except Exception:
            pass
        if facts & HOOK_FACTS or status in ("untrusted", "changed"):
            out.append(Step("codex/hooks", "codex", HOOKS_TEXT, "Codex runs a changed hook only after you approve it"))
    needs = [r for r in results or [] if not r.ok and r.name in BOOTSTRAP_ROWS]
    if needs:
        for agent, on in (("claude", claude_on), ("codex", codex_on)):
            if on:
                out.append(Step(f"{agent}/bootstrap", agent, "run loadout bootstrap", f"{needs[0].name}: {needs[0].fix}"))
    return out
