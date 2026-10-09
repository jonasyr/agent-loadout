"""Detect plaintext secrets in MCP server configs."""
from __future__ import annotations

import re
from dataclasses import dataclass

SECRET_PATTERNS = [
    r"gh[pousr]_[A-Za-z0-9]{20,}", r"github_pat_[A-Za-z0-9_]{20,}", r"sk-[A-Za-z0-9_-]{20,}",
    r"apk_[A-Za-z0-9_=-]{16,}", r"xox[baprs]-[A-Za-z0-9-]{10,}", r"AKIA[0-9A-Z]{16}",
]
SECRET_KEY = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|AUTH", re.I)
HEX_RUN = re.compile(r"[0-9a-fA-F]{32,}")
B64_RUN = re.compile(r"[A-Za-z0-9+/_=-]{40,}")
MASK = "***"


@dataclass
class Finding:
    server: str
    field: str      # env | headers | args
    key: str        # env/header name, or arg index
    value: str
    location: str
    fixable: bool   # env/headers can be rewritten to ${VAR}; args need manual handling


def high_entropy(value: str) -> bool:
    """A long hex (>= 32) or base64-ish (>= 40) run that mixes letters and digits (and cases, for base64)."""
    for m in HEX_RUN.finditer(value):
        run = m.group()
        if re.search(r"\d", run) and re.search(r"[a-fA-F]", run):
            return True
    for m in B64_RUN.finditer(value):
        run = m.group()
        if re.search(r"[a-z]", run) and re.search(r"[A-Z]", run) and re.search(r"\d", run):
            return True
    return False


def looks_secret(key: str, value: str, keyed_arg: bool = False) -> bool:
    """keyed_arg: the value came from a KEY=value argument, so the high-entropy test applies too."""
    if not isinstance(value, str) or "${" in value:
        return False
    if any(re.search(p, value) for p in SECRET_PATTERNS):
        return True
    if SECRET_KEY.search(key) and len(value) >= 12:
        return True
    return keyed_arg and high_entropy(value)


_JSON_PAIR = re.compile(r'"(?P<k>[^"\\]*)"(?P<sep>\s*:\s*)"(?P<v>(?:[^"\\]|\\.)*)"')
_KEY_EQ = re.compile(r"(?P<k>[A-Za-z0-9_.-]+)=(?P<v>[^\s&'\"]+)")
_FLAG_VALUE = re.compile(r"(?P<k>--?[A-Za-z0-9_-]*(?:key|token|secret|password|auth)[A-Za-z0-9_-]*)(?P<sp>\s+)(?P<v>[^\s-]\S{7,})", re.I)
_BEARER = re.compile(r"(?P<k>\b(?:Bearer|Basic|token)\s+)(?P<v>[A-Za-z0-9._~+/=-]{8,})")


def redact(text: str) -> str:
    """Mask anything that looks like a secret before it reaches the console."""
    if not text:
        return text
    text = _JSON_PAIR.sub(lambda m: f'"{m["k"]}"{m["sep"]}"{MASK}"' if looks_secret(m["k"], m["v"]) else m.group(), text)
    text = _BEARER.sub(lambda m: m["k"] + MASK, text)
    text = _KEY_EQ.sub(lambda m: f"{m['k']}={MASK}" if looks_secret(m["k"], m["v"], keyed_arg=True) else m.group(), text)
    text = _FLAG_VALUE.sub(lambda m: m["k"] + m["sp"] + MASK, text)
    for pattern in SECRET_PATTERNS:
        text = re.sub(pattern, MASK, text)
    return text


def var_name(server: str, key: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", f"{server}_{key}".upper()).strip("_")


def scan(claude_json: dict, location: str = "~/.claude.json") -> list[Finding]:
    found = []
    for server, cfg in claude_json.get("mcpServers", {}).items():
        for field in ("env", "headers"):
            mapping = cfg.get(field)
            for key, value in (mapping if isinstance(mapping, dict) else {}).items():
                if looks_secret(key, value):
                    found.append(Finding(server, field, key, value, location, True))
        args = cfg.get("args")
        for i, arg in enumerate(args if isinstance(args, list) else []):
            if not isinstance(arg, str):
                continue
            key = arg.split("=", 1)[0] if "=" in arg else str(i)
            value = arg.split("=", 1)[1] if "=" in arg else arg
            if looks_secret(key, value):
                found.append(Finding(server, "args", key, value, location, False))
    return found
