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


def _tomllib():
    """tomllib (Python 3.11+), which the config edit needs to prove it changed nothing of the user's."""
    try:
        import tomllib
        return tomllib
    except ImportError:
        return None


def toml_key(key: str) -> str:
    return key if _BARE.match(key) else toml_value(key)


def toml_value(value) -> str:
    """Strings, booleans, lists of strings, tables of strings. JSON's escapes are valid TOML basic-string escapes;
    DEL is the one character JSON leaves raw and TOML forbids."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False).replace("\x7f", "\\u007f")
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


def _check_shape(name: str, cfg) -> None:
    if not isinstance(cfg, dict):
        raise Refused(f"mcp {name}: not a server configuration")
    unknown = sorted(set(cfg) - _SUPPORTED)
    if unknown:
        raise Refused(f"mcp {name}: Codex mapping does not support {', '.join(unknown)}")
    for field in ("command", "url", "type"):
        if field in cfg and not isinstance(cfg[field], str):
            raise Refused(f"mcp {name}: {field} must be a string")
    args = cfg.get("args")
    if args is not None and not (isinstance(args, list) and all(isinstance(a, str) for a in args)):
        raise Refused(f"mcp {name}: args must be a list of strings")
    for field in ("env", "headers"):
        table = cfg.get(field)
        if table is not None and not (isinstance(table, dict)
                                      and all(isinstance(k, str) and isinstance(v, str) for k, v in table.items())):
            raise Refused(f"mcp {name}: {field} must map names to strings")


def server(name: str, cfg: dict) -> dict:
    """A Claude-style MCP config as Codex keys; secrets only as variable names, never as plaintext."""
    _check_shape(name, cfg)
    from .secrets import scan
    for finding in scan({"mcpServers": {name: cfg}}):
        raise Refused(f"mcp {name}: {finding.field} {finding.key} holds a plaintext secret; move it to secrets.env "
                      "(Codex forwards env variables and headers by name, never arguments or URLs)")
    for value in (cfg.get("command"), cfg.get("url"), *(cfg.get("args") or [])):
        if isinstance(value, str) and "${" in value:
            raise Refused(f"mcp {name}: Codex does not expand ${{…}} in command, args or url; pass the value through env")
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
            text = table_text(name, server(name, cfg))
            try:
                text.encode("utf-8")
            except UnicodeEncodeError:
                raise Refused(f"mcp {name}: holds characters that cannot be written as UTF-8") from None
            tables[name] = text
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


def _top_lines(lines: list[str]) -> list[bool]:
    """Per line: whether it starts outside any multi-line string, array or inline table (where a header or key can be)."""
    top, ml, depth = [], None, 0
    for line in lines:
        top.append(ml is None and depth == 0)
        i, n = 0, len(line)
        while i < n:
            if ml:
                j = line.find(ml, i)
                if j < 0:
                    break
                i, ml = j + 3, None
                continue
            c = line[i]
            if c == "#":
                break
            if line.startswith('"""', i) or line.startswith("'''", i):
                ml, i = line[i:i + 3], i + 3
                continue
            if c == '"':
                i += 1
                while i < n and line[i] != '"':
                    i += 2 if line[i] == "\\" else 1
                i += 1
                continue
            if c == "'":
                j = line.find("'", i + 1)
                i = n if j < 0 else j + 1
                continue
            if c in "[{":
                depth += 1
            elif c in "]}":
                depth = max(0, depth - 1)
            i += 1
    return top


def _header_path(line: str, tl) -> tuple | None:
    """The key path a header line opens, normalised by tomllib (quotes, spaces); arrays of tables never match a table."""
    try:
        data = tl.loads(line.strip() + "\n")
    except Exception:
        return None
    path = []
    while isinstance(data, dict) and len(data) == 1:
        key, data = next(iter(data.items()))
        path.append(key)
    return ("[[",) + tuple(path) if isinstance(data, list) else tuple(path)


def _sections(lines: list[str], tl) -> list[list]:
    """[[path or None, [lines], [top flags]]]: the top level first, then one entry per header."""
    out = [[None, [], []]]
    for line, top in zip(lines, _top_lines(lines)):
        if top and line.lstrip().startswith("["):
            out.append([_header_path(line, tl) or ("?", line.strip()), [line], [True]])
        else:
            out[-1][1].append(line)
            out[-1][2].append(top)
    return out


def _text(section_lines: list[str]) -> str:
    return "\n".join(section_lines).rstrip("\n").rstrip() + "\n"


def _prune(value):
    if isinstance(value, dict):
        kept = {k: _prune(v) for k, v in value.items()}
        return {k: v for k, v in kept.items() if v != {}}
    return value


def _without_owned(data: dict, tables, keys) -> dict:
    data = json.loads(json.dumps(data, default=str))  # a deep copy; dates become strings on both sides alike
    servers = data.get("mcp_servers")
    if isinstance(servers, dict):
        for name in tables:
            servers.pop(name, None)
    for dotted in keys:
        *parents, last = dotted.split(".")
        cur = data
        for part in parents:
            cur = cur.get(part) if isinstance(cur, dict) else None
        if isinstance(cur, dict):
            cur.pop(last, None)
    return _prune(data)


def apply_config(bk, dry_run: bool = False) -> list[str]:
    path = paths.codex_home() / "config.toml"
    tl = _tomllib()
    if tl is None:
        return [f"skipped {path}: editing it safely needs Python 3.11 or newer"]
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    try:
        before = tl.loads(old)
    except Exception as exc:
        return [f"skipped {path}: it does not parse now ({exc}); fix it, then run loadout bootstrap"]
    record = load_json(record_path())
    owned_tables, owned_keys = dict(record.get("tables", {})), dict(record.get("keys", {}))
    was_tables, was_keys = set(owned_tables), set(owned_keys)
    sections = _sections(old.splitlines(), tl)
    tables, lines = desired_tables()

    def find(path_):
        return next((s for s in sections if s[0] == path_), None)

    # tables: drop or keep what loadout wrote, never touch anything else
    for name, text in list(owned_tables.items()):
        sec = find(("mcp_servers", name))
        if sec is None:
            owned_tables.pop(name)
        elif _text(sec[1]) != text:
            lines.append(f"mcp {name}: left as is in config.toml (changed by you); loadout no longer manages it")
            owned_tables.pop(name)
        elif tables.get(name) != text:
            sections.remove(sec)
            owned_tables.pop(name)
    for name, text in tables.items():
        if find(("mcp_servers", name)) is not None:
            if owned_tables.get(name) != text:
                lines.append(f"mcp {name}: left as is, config.toml already has a server of that name")
            continue
        sections.append([("mcp_servers", name), text.rstrip("\n").splitlines(), []])
        owned_tables[name] = text

    # keys: one line each, in their table, only on lines that start outside strings and arrays
    for table, key, value in desired_keys():
        dotted = f"{table}.{key}" if table else key
        line = f"{key} = {toml_value(value)}"
        target = sections[0] if not table else find((table,))
        if target is None:
            sections.append([(table,), [f"[{table}]", line], []])
            owned_keys[dotted] = line
            continue
        flags = [True] + target[2] if target[0] is not None else target[2]
        found = next((i for i, l in enumerate(target[1])
                      if flags[i] and re.match(rf"^\s*{re.escape(key)}\s*=", l)), None)
        if found is None:
            insert = len(target[1])
            while insert > (1 if target[0] is not None else 0) and not target[1][insert - 1].strip():
                insert -= 1
            target[1].insert(insert, line)
            target[2].insert(insert - (1 if target[0] is not None else 0), True)
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
    new_record = {"tables": owned_tables, "keys": owned_keys}
    if new == old or (not old.strip() and not new.strip()):
        if new_record != {"tables": record.get("tables", {}), "keys": record.get("keys", {})} and not dry_run:
            save_json(record_path(), new_record)
        return lines
    try:
        after = tl.loads(new)
    except Exception as exc:
        return lines + [f"skipped {path}: the result would not parse ({exc}); nothing written, fix the file by hand"]
    ours_tables, ours_keys = was_tables | set(owned_tables), was_keys | set(owned_keys)
    if _without_owned(before, ours_tables, ours_keys) != _without_owned(after, ours_tables, ours_keys):
        return lines + [f"skipped {path}: the edit would change entries loadout does not own; nothing written"]
    if dry_run:
        return lines + ["config.toml: changes pending"]
    if path.exists() and not record:
        bk.save_copy(path, "Codex config.toml before loadout's first change")
    elif not path.exists():
        bk.record_created(path, "created Codex config.toml")
    from .jsonio import write_atomic
    write_atomic(path, new)
    record_path().parent.mkdir(parents=True, exist_ok=True)
    save_json(record_path(), new_record)
    return lines


OFFICIAL = "anthropics/claude-plugins-official"


def _json(text: str):
    """codex prints warnings before its JSON on some setups; read from the first brace."""
    start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=-1)
    return json.loads(text[start:]) if start >= 0 else None


def _tail(res: runner.Result) -> str:
    return (res.stderr.strip() or res.stdout.strip())[-300:]


def plugin_routes(settings: dict) -> tuple[dict[str, list[str]], list[str]]:
    """{GitHub source: [plugin names]} for every plugin enabled for Claude Code, and those without a GitHub source."""
    markets = settings.get("extraKnownMarketplaces", {})
    routes: dict[str, list[str]] = {}
    missing = []
    for pid, on in settings.get("enabledPlugins", {}).items():
        if on is not True or "@" not in pid:
            continue
        name, market = pid.rsplit("@", 1)
        source = markets.get(market, {}).get("source", {})
        src = OFFICIAL if market == "claude-plugins-official" else (
            source.get("repo") if source.get("source") == "github" else None)
        if src is None:
            missing.append(pid)
        else:
            routes.setdefault(src, []).append(name)
    return routes, missing


def installed_plugins() -> set[str] | None:
    res = runner.run(["codex", "plugin", "list", "--json"], timeout=120)
    data = _json(res.stdout) if res.ok else None
    return {p.get("pluginId") for p in data.get("installed", [])} if isinstance(data, dict) else None


def apply_plugins(bk, refresh: bool = False) -> list[str]:
    from .settings_merge import desired_settings
    routes, missing = plugin_routes(desired_settings())
    lines = [f"plugin {pid}: no Codex route (its marketplace is not on GitHub)" for pid in missing]
    installed = installed_plugins() or set()
    for src, plugins in routes.items():
        res = runner.run(["codex", "plugin", "marketplace", "add", src, "--json"], timeout=900)
        info = _json(res.stdout) if res.ok else None
        if not isinstance(info, dict) or "marketplaceName" not in info:
            lines.append(f"marketplace {src}: failed: {_tail(res)}")
            continue
        market = info["marketplaceName"]
        if not info.get("alreadyAdded"):
            bk.record_command(f"codex marketplace {market}", ["codex", "plugin", "marketplace", "remove", market])
        elif refresh:
            runner.run(["codex", "plugin", "marketplace", "upgrade", market], timeout=900)
        for name in plugins:
            pid = f"{name}@{market}"
            if pid in installed and not refresh:
                continue
            res = runner.run(["codex", "plugin", "add", pid, "--json"], timeout=600)
            if not res.ok:
                lines.append(f"plugin {pid}: failed: {_tail(res)}")
            elif pid not in installed:
                bk.record_command(f"codex plugin {pid}", ["codex", "plugin", "remove", pid])
                lines.append(f"plugin {pid}: installed")
    return lines


def skill_links() -> list[tuple[Path, Path]]:
    """The same personal skills (folders and skills.json pointers) that link.py links for Claude Code."""
    from . import link
    claude_skills = paths.claude_home() / "skills"
    return [(paths.agents_skills() / dest.name, src) for dest, src in link.LINKS() if dest.parent == claude_skills]


def apply_skills(bk) -> list[str]:
    from . import link
    return [line for dest, src in skill_links() if (line := link._link_one(dest, src, bk))]


def mcp_names() -> set[str] | None:
    res = runner.run(["codex", "mcp", "list", "--json"], timeout=120)
    data = _json(res.stdout) if res.ok else None
    return {s.get("name") for s in data if isinstance(s, dict)} if isinstance(data, list) else None


def _skill_names(folder: Path) -> set[str]:
    return {p.name for p in folder.iterdir() if not p.name.startswith(".") and p.name != "synced"} if folder.is_dir() else set()


def drift() -> list[str]:
    """Names present in only one agent and accounted for by neither the kit, the personal layer nor a 'leave'."""
    from . import own
    in_codex = mcp_names()
    if in_codex is None:
        return []
    left = {key.split(":")[-1] for key in own.decisions()}
    personal = set(load_json(paths.personal_root() / "mcp.json").get("mcpServers", {}))
    owned = set(load_json(record_path()).get("tables", {}))
    in_claude = set(load_json(paths.claude_json()).get("mcpServers", {}))
    accounted = left | personal | owned
    out = [f'MCP server "{n}" only in Claude Code (record it with loadout adopt, then both get it)'
           for n in sorted(in_claude - in_codex - accounted)]
    out += [f'MCP server "{n}" only in Codex (add it to your personal layer\'s mcp.json, see docs/how-to/codex.md)'
            for n in sorted(in_codex - in_claude - accounted - _plugin_servers())]
    claude_skills, codex_skills = _skill_names(paths.claude_home() / "skills"), _skill_names(paths.agents_skills())
    personal_skills = {dest.name for dest, _ in skill_links()}
    out += [f'skill "{n}" only in Claude Code (record it with loadout adopt, then both get it)'
            for n in sorted(claude_skills - codex_skills - personal_skills - left)]
    out += [f'skill "{n}" only in Codex (copy it into your personal layer\'s skills/, see docs/how-to/codex.md)'
            for n in sorted(codex_skills - claude_skills - personal_skills - left)]
    return out


def _plugin_servers() -> set[str]:
    """MCP servers that Codex has from installed plugins (their .mcp.json), not from the user."""
    names: set[str] = set()
    for mcp in (paths.codex_home() / "plugins" / "cache").glob("*/*/*/.mcp.json"):
        names |= set(load_json(mcp).get("mcpServers", {}))
    return names


HOOKS_TODO = "approve the loadout hooks in Codex once: start `codex`, then run /hooks"


def apply_all(bk, refresh: bool = False) -> list[str]:
    return [apply_instructions(bk), *apply_config(bk), *apply_skills(bk), *apply_plugins(bk, refresh=refresh)]


def checks() -> list:
    from .check import CheckResult
    if not enabled():
        return []
    problem = unavailable()
    if problem:
        return [CheckResult("Codex", False, problem, "install or update codex (mise use -g codex), or: loadout configure set target codex off", "warn")]
    results = [CheckResult("Codex", True)]
    installed = installed_plugins()
    ok = installed is not None and "loadout@agent-loadout" in installed
    results.append(CheckResult("Codex plugin", ok, "" if ok else "loadout plugin not installed in Codex", "loadout bootstrap"))
    path = paths.codex_home() / "AGENTS.md"
    current = splice(path.read_text(encoding="utf-8") if path.exists() else "", render_instructions())
    ok = path.exists() and current == path.read_text(encoding="utf-8")
    results.append(CheckResult("Codex instructions", ok, "" if ok else f"{_tilde(path)} lacks loadout's current block", "loadout bootstrap"))
    if (paths.codex_home() / "AGENTS.override.md").exists():
        results.append(CheckResult("Codex instructions", False, "AGENTS.override.md shadows AGENTS.md, so Codex ignores loadout's block",
                                   "merge it into AGENTS.md or remove it", "warn"))
    pending = apply_config(object(), dry_run=True)
    results.append(CheckResult("Codex config", not pending, "; ".join(pending), "loadout bootstrap", "warn"))
    from .settings_merge import desired_settings
    missing = plugin_routes(desired_settings())[1]
    if missing:
        results.append(CheckResult("Codex plugins", False, "no Codex route for " + ", ".join(missing), "", "warn"))
    lines = drift()
    results.append(CheckResult("Codex drift", not lines, "; ".join(lines), "loadout adopt (see docs/how-to/codex.md)", "warn"))
    return results
