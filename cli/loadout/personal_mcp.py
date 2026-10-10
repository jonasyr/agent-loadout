"""Apply <personal>/mcp.json as user-scope MCP servers; touch only servers the kit manages.

managed-mcp.json records what the kit applied successfully. A same-named server the user
added themselves (not in that snapshot) with a different config is left alone.
"""
from __future__ import annotations

import json

from . import paths, runner
from .jsonio import load_json, save_json
from .secrets import redact


def _add(name: str, cfg: dict) -> runner.Result:
    return runner.run(["claude", "mcp", "add-json", "-s", "user", name, json.dumps(cfg)])


def apply_mcp() -> list[str]:
    desired = load_json(paths.personal_root() / "mcp.json").get("mcpServers", {})
    snap = paths.state_dir() / "managed-mcp.json"
    previous = load_json(snap).get("mcpServers", {})
    current = load_json(paths.claude_json()).get("mcpServers", {})
    managed, out = {}, []
    for name, cfg in desired.items():
        if current.get(name) == cfg:
            managed[name] = cfg
            continue
        if name in current and name not in previous:
            out.append(f"mcp {name}: skipped, a server with this name exists and is not managed by loadout "
                       f"(remove it with `claude mcp remove -s user {name}` to let loadout manage it)")
            continue
        add_cmd = ["claude", "mcp", "add-json", "-s", "user", name, json.dumps(cfg)]
        if runner.would_refuse(add_cmd):  # decide before removing anything: a refused add would lose the server
            cmds = ([["claude", "mcp", "remove", "-s", "user", name]] if name in current else []) + [add_cmd]
            where = runner.write_manual_commands(paths.state_dir(), f"mcp {name} (full commands, contains secrets)", cmds)
            out.append(f"mcp {name}: not changed, this claude (a Windows .cmd shim) cannot take JSON arguments; "
                       f"run the commands in {where} by hand, or install the native claude.exe")
            if name in current and name in previous:
                managed[name] = current[name]  # still ours: retry next time instead of calling it unmanaged
            continue
        if name in current:
            runner.run(["claude", "mcp", "remove", "-s", "user", name])
        res = _add(name, cfg)
        if res.ok:
            managed[name] = cfg
            out.append(f"mcp {name}: added")
            continue
        out.append(redact(f"mcp {name}: failed: {res.stderr.strip()}"))
        if name in current:  # never leave the user without the server they had
            back = _add(name, current[name])
            out.append(f"mcp {name}: previous config {'re-added' if back.ok else 'could not be re-added'}")
            if back.ok and name in previous:
                managed[name] = current[name]
    for name, cfg in previous.items():
        if name in desired:
            continue
        if current.get(name) != cfg:
            continue  # gone already, or changed by the user: no longer ours
        res = runner.run(["claude", "mcp", "remove", "-s", "user", name])
        if res.ok:
            out.append(f"mcp {name}: removed")
        else:
            managed[name] = cfg  # still installed, still ours
            out.append(redact(f"mcp {name}: failed: {res.stderr.strip()}"))
    save_json(snap, {"mcpServers": managed})
    return out


def replace_user_server(name: str, original: dict, new: dict, bk) -> str:
    """Swap a user-scope server's config. Never leaves the user without the server."""
    remove = ["claude", "mcp", "remove", "-s", "user", name]
    add_new = ["claude", "mcp", "add-json", "-s", "user", name, json.dumps(new)]
    if runner.would_refuse(add_new):  # decide before removing anything
        bk._ensure_root()
        where = runner.write_manual_commands(bk.root, f"mcp {name} (full commands, contains secrets)", [remove, add_new])
        return f"manual: {where}"
    # reverse replay: remove the new server first, then re-add the original
    bk.record_command(f"mcp {name} (original)", ["claude", "mcp", "add-json", "-s", "user", name, json.dumps(original)])
    bk.record_command(f"mcp {name} (remove rewritten)", remove)
    runner.run(remove)
    res = runner.run(add_new)
    if res.ok:
        return "ok"
    back = _add(name, original)
    return redact(f"failed: {res.stderr.strip()} (original re-added: {'ok' if back.ok else 'failed: ' + back.stderr.strip()})")
