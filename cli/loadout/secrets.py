"""Detect plaintext secrets in MCP server configs."""
from __future__ import annotations

import re
from dataclasses import dataclass

SECRET_PATTERNS = [
    r"gh[pousr]_[A-Za-z0-9]{20,}", r"github_pat_[A-Za-z0-9_]{20,}", r"sk-[A-Za-z0-9_-]{20,}",
    r"apk_[A-Za-z0-9_=-]{16,}", r"xox[baprs]-[A-Za-z0-9-]{10,}", r"AKIA[0-9A-Z]{16}",
]
SECRET_KEY = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|AUTH", re.I)


@dataclass
class Finding:
    server: str
    field: str      # env | headers | args
    key: str        # env/header name, or arg index
    value: str
    location: str
    fixable: bool   # env/headers can be rewritten to ${VAR}; args need manual handling


def looks_secret(key: str, value: str) -> bool:
    if not isinstance(value, str) or "${" in value:
        return False
    if any(re.search(p, value) for p in SECRET_PATTERNS):
        return True
    return bool(SECRET_KEY.search(key)) and len(value) >= 12


def var_name(server: str, key: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", f"{server}_{key}".upper()).strip("_")


def scan(claude_json: dict, location: str = "~/.claude.json") -> list[Finding]:
    found = []
    for server, cfg in claude_json.get("mcpServers", {}).items():
        for field in ("env", "headers"):
            for key, value in (cfg.get(field) or {}).items():
                if looks_secret(key, value):
                    found.append(Finding(server, field, key, value, location, True))
        for i, arg in enumerate(cfg.get("args") or []):
            key = arg.split("=", 1)[0] if "=" in arg else str(i)
            value = arg.split("=", 1)[1] if "=" in arg else arg
            if looks_secret(key, value):
                found.append(Finding(server, "args", key, value, location, False))
    return found
