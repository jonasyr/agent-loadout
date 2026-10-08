"""Apply <personal>/mcp.json as user-scope MCP servers; remove only servers the kit applied before."""
from __future__ import annotations

import json

from . import paths, runner
from .jsonio import load_json, save_json


def apply_mcp() -> list[str]:
    desired = load_json(paths.personal_root() / "mcp.json").get("mcpServers", {})
    snap = paths.state_dir() / "managed-mcp.json"
    previous = load_json(snap).get("mcpServers", {})
    current = load_json(paths.claude_json()).get("mcpServers", {})
    out = []
    for name, cfg in desired.items():
        if current.get(name) == cfg:
            continue
        if name in current:
            runner.run(["claude", "mcp", "remove", "-s", "user", name])
        res = runner.run(["claude", "mcp", "add-json", "-s", "user", name, json.dumps(cfg)])
        out.append(f"mcp {name}: {'added' if res.ok else 'failed: ' + res.stderr.strip()}")
    for name, cfg in previous.items():
        if name not in desired and current.get(name) == cfg:
            res = runner.run(["claude", "mcp", "remove", "-s", "user", name])
            out.append(f"mcp {name}: {'removed' if res.ok else 'failed: ' + res.stderr.strip()}")
    save_json(snap, {"mcpServers": desired})
    return out
