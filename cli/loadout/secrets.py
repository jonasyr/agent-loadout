"""Detect, redact and store plaintext secrets (MCP configs, settings env, secrets.env)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

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
    field: str      # env | headers | args | url
    key: str        # env/header name, arg key or index, URL query key
    value: str
    location: str
    fixable: bool   # user-scope env/headers in ~/.claude.json can be rewritten to ${VAR}; the rest is report-only


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


def scan(claude_json: dict, location: str = "~/.claude.json", fixable: bool = True) -> list[Finding]:
    """Secrets in a {"mcpServers": {...}} mapping. `fixable` marks env/headers findings as movable."""
    found = []
    servers = claude_json.get("mcpServers")
    for server, cfg in (servers if isinstance(servers, dict) else {}).items():
        if not isinstance(cfg, dict):
            continue
        for field in ("env", "headers"):
            mapping = cfg.get(field)
            for key, value in (mapping if isinstance(mapping, dict) else {}).items():
                if looks_secret(key, value):
                    found.append(Finding(server, field, key, value, location, fixable))
        args = cfg.get("args")
        for i, arg in enumerate(args if isinstance(args, list) else []):
            if not isinstance(arg, str):
                continue
            keyed = "=" in arg
            key = arg.split("=", 1)[0] if keyed else str(i)
            value = arg.split("=", 1)[1] if keyed else arg
            if looks_secret(key, value, keyed_arg=keyed):
                found.append(Finding(server, "args", key, value, location, False))
        url = cfg.get("url")
        if isinstance(url, str) and "?" in url:
            for key, value in parse_qsl(urlsplit(url).query):
                if looks_secret(key, value, keyed_arg=True):
                    found.append(Finding(server, "url", key, value, location, False))
    return found


def scan_all() -> list[Finding]:
    """Every place the kit knows MCP servers or env values live. Only user-scope ~/.claude.json is fixable."""
    from . import paths
    from .jsonio import load_json

    claude_json = load_json(paths.claude_json())
    found = scan(claude_json)
    projects = claude_json.get("projects")
    for proj, cfg in (projects if isinstance(projects, dict) else {}).items():
        if isinstance(cfg, dict):
            found += scan(cfg, f"~/.claude.json projects[{proj}]", fixable=False)
    found += scan(load_json(paths.claude_home() / ".mcp.json"), "~/.claude/.mcp.json", fixable=False)
    personal = paths.personal_root() / "mcp.json"
    found += scan(load_json(personal), str(personal), fixable=False)
    env = load_json(paths.claude_home() / "settings.json").get("env")
    for key, value in (env if isinstance(env, dict) else {}).items():
        if looks_secret(key, value, keyed_arg=True):
            found.append(Finding("settings.json", "env", key, value, "~/.claude/settings.json", False))
    return found


# secrets.env format: NAME='value' with POSIX single-quote escaping, so `. secrets.env` never
# executes or mangles a value. The PowerShell loader (bootstrap.PS_BLOCK) parses the same format.
_ENV_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


def quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def parse_env_line(line: str) -> tuple[str, str] | None:
    m = _ENV_LINE.match(line.rstrip("\r\n"))
    if not m:
        return None
    name, raw = m.group(1), m.group(2).strip()
    if len(raw) >= 2 and raw[0] == raw[-1] == "'":
        return name, raw[1:-1].replace("'\\''", "'")
    if len(raw) >= 2 and raw[0] == raw[-1] == '"':
        return name, raw[1:-1]
    return name, raw


def load_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        parsed = parse_env_line(line)
        if parsed:
            out[parsed[0]] = parsed[1]
    return out
