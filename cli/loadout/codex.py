"""Codex CLI as a second target: the same kit and personal layer, mapped to Codex (docs/how-to/codex.md)."""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import paths, runner
from .jsonio import load_json, save_json

MIN_VERSION = (0, 161)


def targets_path() -> Path:
    return paths.personal_root() / "targets.json"


def enabled() -> bool:
    return load_json(targets_path()).get("codex") is True


def decided() -> bool:
    return "codex" in load_json(targets_path())


def set_enabled(on: bool) -> str:
    data = load_json(targets_path())
    data["codex"] = on
    targets_path().parent.mkdir(parents=True, exist_ok=True)
    save_json(targets_path(), data)
    return f"codex: {'on' if on else 'off'}"


def unavailable() -> str | None:
    """None when a usable codex is on PATH, else the reason in one line."""
    if not runner.have("codex"):
        return "codex not found on PATH"
    res = runner.run(["codex", "--version"], timeout=20)
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", res.stdout)
    if not m:
        return "could not read codex --version"
    if (int(m.group(1)), int(m.group(2))) < MIN_VERSION:
        return f"codex {m.group(0)} is too old; loadout needs 0.161 or newer (update it: mise upgrade codex)"
    return None


START = "<!-- loadout:start -->"
END = "<!-- loadout:end -->"


def _tilde(path: Path) -> str:
    home = str(paths.home())
    return "~" + str(path)[len(home):] if str(path).startswith(home) else str(path)


def render_instructions() -> str:
    """Codex has no @include and no rules folder, so the rules are copied in; their files stay the only source."""
    kit, personal = paths.kit_root() / "rules", paths.personal_root() / "rules"
    parts = [START, f"<!-- Managed by loadout from {_tilde(kit)} and {_tilde(personal)}; "
                    "edit those files, not this block. -->"]
    for folder in (kit, personal):
        if folder.is_dir():
            parts += [f.read_text(encoding="utf-8").strip() for f in sorted(folder.glob("*.md"))]
    parts.append(END)
    return "\n\n".join(parts) + "\n"


def splice(text: str, block: str) -> str | None:
    """text with the block replaced or appended; None when the markers are unbalanced or duplicated."""
    starts, ends = text.count(START), text.count(END)
    if starts == ends == 0:
        return block if not text.strip() else text.rstrip("\n") + "\n\n" + block
    if starts == ends == 1 and text.index(START) < text.index(END):
        before, rest = text.split(START, 1)
        after = rest.split(END, 1)[1]
        return before + block.rstrip("\n") + after
    return None


def apply_instructions(bk) -> str:
    path = paths.codex_home() / "AGENTS.md"
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    new = splice(old, render_instructions())
    if new is None:
        return f"skipped {path}: its loadout markers are unbalanced or duplicated; fix them by hand"
    if new == old:
        return "instructions up to date"
    if path.exists() and START not in old:
        bk.save_copy(path, "Codex AGENTS.md before loadout added its block")
    elif not path.exists():
        bk.record_created(path, "created Codex AGENTS.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new, encoding="utf-8", newline="\n")
    return f"instructions written to {_tilde(path)}"


SERENA = {"command": "serena", "args": ["start-mcp-server", "--context=codex", "--project-from-cwd"]}
_BARE = re.compile(r"^[A-Za-z0-9_-]+$")
_VAR = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")
_BEARER = re.compile(r"^Bearer \$\{([A-Za-z_][A-Za-z0-9_]*)\}$")
_SUPPORTED = {"type", "command", "args", "env", "url", "headers"}


class Refused(Exception):
    """A server config loadout will not write into Codex, with the reason and the fix."""


def toml_key(key: str) -> str:
    return key if _BARE.match(key) else json.dumps(key, ensure_ascii=False)


def toml_value(value) -> str:
    """Strings, booleans, lists of strings, tables of strings. JSON's escapes are valid TOML basic-string escapes."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return "[" + ", ".join(toml_value(v) for v in value) + "]"
    if isinstance(value, dict) and all(isinstance(v, str) for v in value.values()):
        return "{ " + ", ".join(f"{toml_key(k)} = {toml_value(v)}" for k, v in value.items()) + " }" if value else "{}"
    raise Refused(f"unsupported value type {type(value).__name__}")


def _plain(name: str, key: str, value: str) -> None:
    if "${" in value:
        raise Refused(f"mcp {name}: {key} mixes text and a variable; Codex can forward only a whole value from a variable")
    from .secrets import looks_secret
    if looks_secret(key, value):
        raise Refused(f"mcp {name}: {key} holds a plaintext secret; move it to secrets.env and refer to it as ${{{key}}}")


def server(name: str, cfg: dict) -> dict:
    """A Claude-style MCP config as Codex keys; secrets only as variable names."""
    unknown = sorted(set(cfg) - _SUPPORTED)
    if unknown:
        raise Refused(f"mcp {name}: Codex mapping does not support {', '.join(unknown)}")
    out: dict = {}
    if isinstance(cfg.get("url"), str):
        out["url"] = cfg["url"]
        plain, env_headers = {}, {}
        for key, value in (cfg.get("headers") or {}).items():
            bearer = _BEARER.match(value) if key.lower() == "authorization" else None
            var = _VAR.match(value)
            if bearer:
                out["bearer_token_env_var"] = bearer.group(1)
            elif var:
                env_headers[key] = var.group(1)
            else:
                _plain(name, key, value)
                plain[key] = value
        if plain:
            out["http_headers"] = plain
        if env_headers:
            out["env_http_headers"] = env_headers
        return out
    if not isinstance(cfg.get("command"), str):
        raise Refused(f"mcp {name}: neither a command nor a url")
    out["command"] = cfg["command"]
    if cfg.get("args"):
        out["args"] = list(cfg["args"])
    plain, forwarded = {}, []
    for key, value in (cfg.get("env") or {}).items():
        var = _VAR.match(value)
        if var and var.group(1) != key:
            raise Refused(f"mcp {name}: env {key} refers to ${{{var.group(1)}}}; Codex forwards a variable only under "
                          f"its own name, so name it {key} in secrets.env")
        if var:
            forwarded.append(key)
        else:
            _plain(name, key, value)
            plain[key] = value
    if plain:
        out["env"] = plain
    if forwarded:
        out["env_vars"] = forwarded
    return out


def table_text(name: str, srv: dict) -> str:
    return "\n".join([f"[mcp_servers.{toml_key(name)}]", *(f"{toml_key(k)} = {toml_value(v)}" for k, v in srv.items())]) + "\n"


def record_path() -> Path:
    return paths.state_dir() / "codex-config.json"


def desired_tables() -> tuple[dict[str, str], list[str]]:
    """Table text per server name, and the lines for servers that cannot be mapped."""
    servers = load_json(paths.personal_root() / "mcp.json").get("mcpServers", {})
    tables, problems = {"serena": table_text("serena", SERENA)}, []
    for name, cfg in (servers if isinstance(servers, dict) else {}).items():
        try:
            tables[name] = table_text(name, server(name, cfg))
        except Refused as exc:
            problems.append(f"skipped {exc}")
    return tables, problems


def desired_keys() -> list[tuple[str, str, object]]:
    """(table, key, value); table "" is the top level. Only preferences with a Codex equivalent."""
    from . import preferences
    state = preferences.detect()

    def answer(pid):
        return state[pid].value or preferences.by_id(pid)["default"]
    return [("", "model_reasoning_effort", answer("effort_level")),
            ("tui", "notifications", answer("agent_push_notifications") == "yes")]


def _sections(lines: list[str]) -> list[list]:
    """[[header or None, [lines]]]: the top level first, then one entry per [table] or [[array]] header."""
    out = [[None, []]]
    for line in lines:
        s = line.strip()
        if s.startswith("[") and not s.startswith("[["):
            out.append([s[1:s.index("]")].strip(), [line]])
        elif s.startswith("[["):
            out.append([s, [line]])
        else:
            out[-1][1].append(line)
    return out


def _text(section_lines: list[str]) -> str:
    return "\n".join(section_lines).rstrip("\n").rstrip() + "\n"


def apply_config(bk, dry_run: bool = False) -> list[str]:
    path = paths.codex_home() / "config.toml"
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    record = load_json(record_path())
    owned_tables, owned_keys = dict(record.get("tables", {})), dict(record.get("keys", {}))
    sections = _sections(old.splitlines())
    tables, lines = desired_tables()

    # tables: drop or keep what loadout wrote, never touch anything else
    by_header = {s[0]: s for s in sections if s[0]}
    for name, text in list(owned_tables.items()):
        sec = by_header.get(f"mcp_servers.{toml_key(name)}")
        if sec is None:
            owned_tables.pop(name)
        elif _text(sec[1]) != text:
            lines.append(f"mcp {name}: left as is in config.toml (changed by you); loadout no longer manages it")
            owned_tables.pop(name)
        elif tables.get(name) != text:
            sections.remove(sec)
            owned_tables.pop(name)
    by_header = {s[0]: s for s in sections if s[0]}
    for name, text in tables.items():
        header = f"mcp_servers.{toml_key(name)}"
        if header in by_header:
            if owned_tables.get(name) != text:
                lines.append(f"mcp {name}: left as is, config.toml already has a server of that name")
            continue
        sections.append([header, text.rstrip("\n").splitlines()])
        owned_tables[name] = text

    # keys: one line each, in their table
    for table, key, value in desired_keys():
        dotted = f"{table}.{key}" if table else key
        line = f"{key} = {toml_value(value)}"
        target = next((s for s in sections if s[0] == (table or None)), None)
        if target is None:
            sections.append([table, [f"[{table}]", line]])
            owned_keys[dotted] = line
            continue
        found = next((i for i, l in enumerate(target[1]) if re.match(rf"^\s*{re.escape(key)}\s*=", l)), None)
        if found is None:
            insert = len(target[1])
            while insert > (1 if target[0] else 0) and not target[1][insert - 1].strip():
                insert -= 1
            target[1].insert(insert, line)
            owned_keys[dotted] = line
        elif target[1][found].strip() == line:
            owned_keys[dotted] = line
        elif owned_keys.get(dotted) == target[1][found].strip():
            target[1][found] = line
            owned_keys[dotted] = line
        else:
            lines.append(f"{dotted}: left as is in config.toml (your value)")
            owned_keys.pop(dotted, None)

    parts = ["\n".join(sections[0][1]).strip("\n")] if any(l.strip() for l in sections[0][1]) else []
    parts += ["\n".join(s[1]).strip("\n") for s in sections[1:]]
    new = "\n\n".join(p for p in parts if p) + "\n" if parts else ""
    if new == old or new.strip() == old.strip():
        return lines
    if dry_run:
        return lines + ["config.toml: changes pending"]
    try:
        import tomllib
        tomllib.loads(new)
    except ImportError:
        pass
    except Exception as exc:  # tomllib.TOMLDecodeError
        return lines + [f"skipped {path}: the result would not parse ({exc}); nothing written, fix the file by hand"]
    if path.exists() and not record:
        bk.save_copy(path, "Codex config.toml before loadout's first change")
    elif not path.exists():
        bk.record_created(path, "created Codex config.toml")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new, encoding="utf-8", newline="\n")
    record_path().parent.mkdir(parents=True, exist_ok=True)
    save_json(record_path(), {"tables": owned_tables, "keys": owned_keys})
    return lines
