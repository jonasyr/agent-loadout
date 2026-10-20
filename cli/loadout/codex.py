"""Codex CLI as a second target: the same kit and personal layer, mapped to Codex (docs/how-to/codex.md)."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from . import paths, runner
from .jsonio import get_dict, get_list, load_json, save_json

MIN_VERSION = (0, 161)


def targets_path() -> Path:
    from . import targets
    return targets.path()


def enabled() -> bool:
    from . import targets
    return targets.codex_enabled()


def decided() -> bool:
    from . import targets
    return "codex" in load_json(targets.path())


def set_enabled(on: bool) -> str:
    from . import targets
    return targets.set_target("codex", on)


def unavailable(allow_shared_home: bool = False) -> str | None:
    """None when a usable codex is on PATH, or, without one, when VS Code's Codex extension on this side runs a usable
    codex (extension mode); else the reason in one line. In WSL, a Windows codex and a CODEX_HOME that points into
    Windows are reasons too (ADR 0029); only bootstrap --codex-side wsl allows the latter."""
    from . import wsl
    cli = runner.have("codex")
    if not cli:
        ext, why = extension_state()  # VS Code's Codex extension alone: loadout sets Codex up for it
        if ext is None:
            return why or "codex not found on PATH"
    found = runner.which("codex") if cli else None
    if found and wsl.detect() is not None and wsl._on_windows_drive(Path(found), wsl.MOUNT):
        # one loadout per side (ADR 0029): the Windows Codex never reads the WSL home
        return (f"the codex on PATH is the Windows one ({found}): run bootstrap with --install to install Codex in "
                "WSL, or set loadout up on Windows (docs/how-to/wsl.md#codex)")
    shared = os.environ.get("CODEX_HOME", "")
    if (not allow_shared_home and shared and wsl.detect() is not None
            and wsl._on_windows_drive(Path(shared), wsl.MOUNT)):
        return (f"CODEX_HOME points into Windows ({shared}): both sides would read loadout's WSL commands; unset it "
                "in WSL, or run bootstrap with --codex-side wsl to set it up anyway (docs/how-to/wsl.md#codex)")
    if not cli:
        return None  # extension mode: the extension's codex was checked in extension_state
    res = runner.run(["codex", "--version"], timeout=20)
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", res.stdout)
    if not m:
        return "could not read codex --version"
    if (int(m.group(1)), int(m.group(2))) < MIN_VERSION:
        return f"codex {m.group(0)} is too old; loadout needs 0.161 or newer (update it: mise upgrade codex)"
    return None


EXT_OLD = ("VS Code's Codex extension runs codex {version}; loadout needs 0.161 or newer: update the extension in "
           "VS Code (or install the Codex CLI: loadout bootstrap --install)")
PLUGINS_EXTENSION = ("plugins: not installed: VS Code's Codex extension loads none (use the Codex CLI alongside it "
                     "for them: loadout bootstrap --install)")
LOGIN_EXTENSION = "in VS Code's Codex extension: gear, MCP servers, Authenticate"
EXT_NOVERSION = ("VS Code's Codex extension's own codex gives no version, so loadout does not use it: update the "
                 "extension in VS Code (or install the Codex CLI: loadout bootstrap --install)")
HOOKS_NO_CLI = ("approve the loadout hooks once in the Codex CLI's /hooks (VS Code's Codex extension has none), and use "
                "the CLI for plugin skills: install it with loadout bootstrap --install, then run `codex` in VS Code's "
                "terminal and /hooks")


def extension_state():
    """With no Codex CLI: (the VS Code Codex extension on this side whose own codex loadout can use, None), or
    (None, why not) when there is one but its codex is too old or gives no version, or (None, None) when none."""
    from . import vscode
    why = None
    for ext in vscode.extensions({"codex": True}, look=False):  # this side only: no cmd.exe lookup per call
        if ext.install.where == "windows" or ext.binary is None:
            continue
        version = vscode.bundled_version(ext)
        if version is None:
            why = why or EXT_NOVERSION
            continue
        if vscode.too_old(version):
            why = EXT_OLD.format(version=version)
            continue
        return ext, None
    return None, why


def program() -> str:
    """The codex to run read-only commands with: the CLI, else the VS Code extension's own (extension mode)."""
    if runner.have("codex"):
        return "codex"
    ext, _ = extension_state()
    return str(ext.binary) if ext is not None else "codex"


START = "<!-- loadout:start -->"
END = "<!-- loadout:end -->"


def _tilde(path: Path) -> str:
    home = str(paths.home())
    return "~" + str(path)[len(home):] if str(path).startswith(home) else str(path)


def render_instructions() -> str:
    """Codex has no @include and no rules folder, so the rules are copied in; their files stay the only source."""
    kit, personal = paths.kit_root() / "rules", paths.personal_root() / "rules"
    parts = [START, f"<!-- Managed by loadout from {_tilde(kit)} and {_tilde(personal)}; "
                    "edit those files, not this block. -->",
             "In Codex, MCP tools load on demand: search for the Serena and codebase-memory tools (and the other MCP "
             "servers) before deciding that a tool is missing."]
    for folder in (kit, personal):
        if folder.is_dir():
            parts += [f.read_text(encoding="utf-8").strip() for f in sorted(folder.glob("*.md"))]
    parts.append(END)
    return "\n\n".join(parts) + "\n"


def splice(text: str, block: str) -> str | None:
    """text with the block replaced or appended; None when the markers are unbalanced or duplicated.
    The block takes the file's line endings (Windows CRLF stays CRLF), so the user's text stays byte for byte."""
    nl = "\r\n" if "\r\n" in text else "\n"
    if nl != "\n":
        block = block.replace("\r\n", "\n").replace("\n", nl)
    starts, ends = text.count(START), text.count(END)
    if starts == ends == 0:
        return block if not text.strip() else text.rstrip("\r\n") + nl + nl + block
    if starts == ends == 1 and text.index(START) < text.index(END):
        before, rest = text.split(START, 1)
        after = rest.split(END, 1)[1]
        return before + block.rstrip("\r\n") + after
    return None


def _read_exact(path: Path) -> str:
    """The file's text with its own line endings (read_text would turn CRLF into LF)."""
    return path.read_bytes().decode("utf-8")


def _block_hash(text: str) -> str | None:
    """sha256 of loadout's block in text (line endings as LF), or None without one balanced block."""
    if not (text.count(START) == text.count(END) == 1 and text.index(START) < text.index(END)):
        return None
    import hashlib
    block = text[text.index(START):text.index(END) + len(END)].replace("\r\n", "\n")
    return hashlib.sha256(block.encode("utf-8")).hexdigest()


def _remember_block(text: str) -> None:
    record = load_json(record_path())
    record = {k: v for k, v in record.items() if k != "block_notice"}
    record_path().parent.mkdir(parents=True, exist_ok=True)
    save_json(record_path(), {**record, "block": _block_hash(text)})


def apply_instructions(bk) -> str:
    path = paths.codex_home() / "AGENTS.md"
    old = _read_exact(path) if path.exists() else ""
    new = splice(old, render_instructions())
    if new is None:
        return f"skipped {path}: its loadout markers are unbalanced or duplicated; fix them by hand"
    if new == old:
        if load_json(record_path()).get("block") != _block_hash(old):  # a block from before the record: now known
            _remember_block(old)
        return "instructions up to date"
    if path.exists() and START not in old:
        bk.save_copy(path, "Codex AGENTS.md before loadout added its block")
    elif path.exists():
        bk.save_copy(path, "Codex AGENTS.md before loadout rewrote its block")
    else:
        bk.record_created(path, "created Codex AGENTS.md")
    from .jsonio import write_atomic
    write_atomic(path, new)
    _remember_block(new)
    return f"instructions written to {_tilde(path)}"


def refresh_instructions() -> str | None:
    """At a session start: rewrite loadout's block in ~/.codex/AGENTS.md when a rule or me.md changed by hand.
    Only an existing, balanced block, only with Codex on; never creates the file or a block (bootstrap does)."""
    from . import targets
    if not targets.codex_enabled():
        return None
    import time
    lock = paths.state_dir() / LOCK
    try:  # another loadout run is setting Codex up right now: it writes the block itself
        if time.time() - lock.stat().st_mtime < STALE_LOCK:
            return None
    except OSError:
        pass
    path = paths.codex_home() / "AGENTS.md"
    try:
        old = _read_exact(path)
    except (OSError, UnicodeDecodeError):
        return None
    if START not in old:
        return None
    new = splice(old, render_instructions())
    if new is None:
        return None
    record = load_json(record_path())
    current = _block_hash(old)
    if new == old:
        if record.get("block") != current:  # a block from before the record, still current: now known as loadout's
            _remember_block(old)
        return None
    if not record.get("block"):  # not known to be as loadout wrote it: left until bootstrap or the sync rewrite it
        return None
    if record["block"] != current:  # you edited inside the block: it stays as you left it
        if record.get("block_notice") != current:
            from .maintenance import notify
            notify(f"{_tilde(path)}: you edited inside loadout's block, so it is no longer refreshed at a session "
                   "start. Move your text outside the markers, then run loadout bootstrap (it rewrites the block "
                   "and keeps the old file in a backup).")
            save_json(record_path(), {**record, "block_notice": current})
        return None
    from .backup import Backup
    Backup(description="session start: Codex AGENTS.md block refreshed").save_copy(
        path, "Codex AGENTS.md before loadout refreshed its block")
    from .jsonio import write_atomic
    write_atomic(path, new)
    _remember_block(new)
    return f"refreshed loadout's block in {_tilde(path)}"


SERENA = {"command": "serena", "args": ["start-mcp-server", "--project-from-cwd", "--context=codex"],
          "startup_timeout_sec": 15}  # as `serena setup codex` writes it (oraios.github.io/serena, clients page)
# the plugin's Context7 address (?client=claude-code-plugin) asks Codex for OAuth; the plain one answers anonymously
CONTEXT7 = {"url": "https://mcp.context7.com/mcp"}
_BARE = re.compile(r"^[A-Za-z0-9_-]+$")
_VAR = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")
_BEARER = re.compile(r"^Bearer \$\{([A-Za-z_][A-Za-z0-9_]*)\}$")
_SUPPORTED = {"type", "command", "args", "env", "url", "headers"}


class Refused(Exception):
    """A server config loadout will not write into Codex, with the reason and the fix."""


def _tomllib():
    """tomllib, which the config edit needs to prove it changed nothing of the user's."""
    import tomllib
    return tomllib


def toml_key(key: str) -> str:
    return key if _BARE.match(key) else toml_value(key)


def toml_value(value) -> str:
    """Strings, booleans, lists of strings, tables of strings. JSON's escapes are valid TOML basic-string escapes;
    DEL is the one character JSON leaves raw and TOML forbids."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
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


def read_record() -> dict:
    """codex-config.json with `tables` and `keys` as objects, whatever the file holds."""
    record = load_json(record_path())
    return {**record, "tables": get_dict(record, "tables"), "keys": get_dict(record, "keys")}


def is_serena(table: dict) -> bool:
    """A Codex server table that starts Serena's MCP server, whatever its name: serena, a full path to it, or uvx/uv."""
    command, args = table.get("command"), table.get("args")
    if not isinstance(command, str) or not isinstance(args, list) or "start-mcp-server" not in args:
        return False
    base = re.split(r"[\\/]", command)[-1].lower().removesuffix(".exe")
    return base == "serena" or (base in ("uvx", "uv") and any(isinstance(a, str) and "serena" in a for a in args))


def user_serena(data: dict, owned: set[str]) -> str | None:
    """The name of the user's own Serena server in config.toml (a table loadout did not write), or None."""
    for name, table in get_dict(data, "mcp_servers").items():
        if name not in owned and isinstance(table, dict) and is_serena(table):
            return name
    return None


def desired_tables(skip_serena: bool = False) -> tuple[dict[str, str], list[str]]:
    """Table text per server name, and the lines for servers that cannot be mapped. skip_serena: the user has
    their own Serena (user_serena), so loadout writes none (spec PR A)."""
    servers = get_dict(load_json(paths.personal_root() / "mcp.json"), "mcpServers")
    tables, problems = ({} if skip_serena else {"serena": table_text("serena", SERENA)}), []
    from .settings_merge import desired_settings
    if get_dict(desired_settings(), "enabledPlugins").get("context7@claude-plugins-official") is True:
        tables["context7"] = table_text("context7", CONTEXT7)
    personal_serena = None
    for name, cfg in servers.items():
        try:
            mapped = server(name, cfg)
            if is_serena(mapped):  # one Serena only: the user's own in config.toml, else the first personal one
                if skip_serena:
                    continue
                if personal_serena is not None:
                    problems.append(f"skipped mcp {name}: a second Serena (loadout keeps {personal_serena})")
                    continue
                personal_serena = name
                if name != "serena" and tables.get("serena") == table_text("serena", SERENA):
                    tables.pop("serena")
            text = table_text(name, mapped)
            try:
                text.encode("utf-8")
            except UnicodeEncodeError:
                raise Refused(f"mcp {name}: holds characters that cannot be written as UTF-8") from None
            tables[name] = text
        except Refused as exc:
            problems.append(f"skipped {exc}")
    return tables, problems


def project_plugins() -> list[str]:
    """Plugins loadout installed for a project profile only: kept off at user level, on in that project."""
    value = load_json(record_path()).get("project_plugins", [])
    return [p for p in value if isinstance(p, str)] if isinstance(value, list) else []


def add_project_plugin(pid: str) -> None:
    data = load_json(record_path())
    plugins = project_plugins()
    if pid not in plugins:
        data["project_plugins"] = plugins + [pid]
        record_path().parent.mkdir(parents=True, exist_ok=True)
        save_json(record_path(), data)


def _plugin_switches() -> list[tuple]:
    """`enabled` keys for plugins loadout manages and Codex has installed: off when switched off for Claude Code
    (over a line loadout wrote or its own `codex plugin add` caused; any other line is yours); back to true when
    switched on again and loadout owns the line. Never guesses: without the installed list, no key."""
    from .settings_merge import desired_settings
    enabled = get_dict(desired_settings(), "enabledPlugins")
    projects = set(project_plugins())
    owned = read_record()["keys"]
    on = [pid for pid, v in enabled.items() if v is True and isinstance(pid, str) and pid not in projects
          and _dotted(("plugins", pid), "enabled") in owned]
    off = [pid for pid, v in enabled.items() if v is False and isinstance(pid, str) and "@" in pid
           and pid not in projects]
    if not (on or off):
        return []
    listed = installed_plugins()
    if listed is None:
        return []
    return ([(("plugins", pid), "enabled", True, False) for pid in on if pid in listed]
            + [(("plugins", pid), "enabled", False, False) for pid in off if pid in listed])


def desired_keys() -> list[tuple[tuple, str, object, object]]:
    """(table path, key, value, force); path () is the top level. force: loadout's value wins even over a changed
    line, used for project-only plugins because `codex plugin add` switches them back on."""
    from . import preferences
    from .settings_merge import desired_settings
    state = preferences.detect()

    def answer(pid):
        return state[pid].value or preferences.by_id(pid)["default"]
    keys = [((), "model_reasoning_effort", answer("effort_level"), False),
            (("tui",), "notifications", answer("agent_push_notifications") == "yes", False)]
    plugins = project_plugins()
    if plugins:
        on = get_dict(desired_settings(), "enabledPlugins")
        keys += [(("plugins", pid), "enabled", on.get(pid) is True, True) for pid in plugins]
    return keys + _plugin_switches()


def _dotted(path: tuple, key: str) -> str:
    return ".".join(toml_key(p) for p in (*path, key))


def _key_path(dotted: str, tl) -> tuple:
    """`plugins."x@m".enabled` -> ("plugins", "x@m", "enabled"), as TOML reads it."""
    data, out = tl.loads(f"{dotted} = 0\n"), []
    while isinstance(data, dict):
        key, data = next(iter(data.items()))
        out.append(key)
    return tuple(out)


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


def _enabled_line(pid: str) -> str | None:
    """The `enabled` line of [plugins."pid"] in ~/.codex/config.toml as written, or None."""
    path = paths.codex_home() / "config.toml"
    try:
        text = _read_exact(path) if path.exists() else ""
    except (OSError, UnicodeDecodeError):
        return None
    sec = next((s for s in _sections(text.splitlines(), _tomllib()) if s[0] == ("plugins", pid)), None)
    if sec is None:
        return None
    return next((l.strip() for l, top in zip(sec[1][1:], sec[2][1:]) if top and re.match(r"^\s*enabled\s*=", l)), None)


def _record_install_line(pid: str, before: str | None) -> None:
    """After loadout's own `codex plugin add`: the `enabled = true` it caused is loadout's to switch later.
    Only a line that appeared, or replaced loadout's own line; a line you wrote stays yours."""
    after = _enabled_line(pid)
    record = read_record()
    dotted = _dotted(("plugins", pid), "enabled")
    if after != "enabled = true" or (before is not None and before != record["keys"].get(dotted)):
        return
    lines = get_dict(record, "install_lines")
    save_json(record_path(), {**record, "install_lines": {**lines, dotted: after}})


def _text(section_lines: list[str]) -> str:
    return "\n".join(section_lines).rstrip("\n").rstrip() + "\n"


def _same_table(section_lines: list[str], text: str, tl) -> bool:
    """The user's table already says exactly what loadout would write: no conflict to report."""
    try:
        return tl.loads(_text(section_lines)) == tl.loads(text)
    except Exception:
        return False


def _prune(value):
    if isinstance(value, dict):
        kept = {k: _prune(v) for k, v in value.items()}
        return {k: v for k, v in kept.items() if v != {}}
    return value


def _without_owned(data: dict, tables, keys, tl) -> dict:
    data = json.loads(json.dumps(data, default=str))  # a deep copy; dates become strings on both sides alike
    servers = data.get("mcp_servers")
    if isinstance(servers, dict):
        for name in tables:
            servers.pop(name, None)
    for dotted in keys:
        try:
            *parents, last = _key_path(dotted, tl)
        except Exception:  # a hand-edited record entry that is not a TOML key: nothing to leave out
            continue
        cur = data
        for part in parents:
            cur = cur.get(part) if isinstance(cur, dict) else None
        if isinstance(cur, dict):
            cur.pop(last, None)
    return _prune(data)


def apply_config(bk, dry_run: bool = False) -> list[str]:
    path = paths.codex_home() / "config.toml"
    tl = _tomllib()
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    try:
        before = tl.loads(old)
    except Exception as exc:
        return [f"skipped {path}: it does not parse now ({exc}); fix it, then run loadout bootstrap"]
    record = read_record()
    owned_tables, owned_keys = dict(record["tables"]), dict(record["keys"])
    was_tables, was_keys = set(owned_tables), set(owned_keys)
    sections = _sections(old.splitlines(), tl)
    removed = False  # an owned section that goes gets its own backup copy
    still_ours = {name for name, text in owned_tables.items()  # a section the user edited is theirs from now on
                  if any(s[0] == ("mcp_servers", name) and _text(s[1]) == text for s in sections)}
    tables, lines = desired_tables(skip_serena=user_serena(before, still_ours) is not None)

    def find(path_):
        return next((s for s in sections if s[0] == path_), None)

    # tables: drop or keep what loadout wrote, never touch anything else
    for name, text in list(owned_tables.items()):
        sec = find(("mcp_servers", name))
        subtables = [s for s in sections if s[0] and len(s[0]) > 2 and s[0][:2] == ("mcp_servers", name)]
        if sec is None:
            owned_tables.pop(name)
        elif subtables:  # e.g. [mcp_servers.x.tools.y]; removing x alone would leave Codex unable to start
            lines.append(f"mcp {name}: left as is in config.toml (it has sub-tables); loadout no longer manages it")
            owned_tables.pop(name)
        elif _text(sec[1]) != text:
            lines.append(f"mcp {name}: left as is in config.toml (changed by you); loadout no longer manages it")
            owned_tables.pop(name)
        elif tables.get(name) != text:
            sections.remove(sec)
            owned_tables.pop(name)
            removed = True
    for name, text in tables.items():
        existing = find(("mcp_servers", name))
        if existing is not None:
            if owned_tables.get(name) != text and not _same_table(existing[1], text, tl):
                lines.append(f"mcp {name}: left as is, config.toml already has a server of that name")
            continue
        sections.append([("mcp_servers", name), text.rstrip("\n").splitlines(), []])
        owned_tables[name] = text

    # keys: one line each, in their table, only on lines that start outside strings and arrays
    # force: True (loadout's value wins) or False (a changed line is yours). A plugin's `enabled = true` that
    # loadout's own `codex plugin add` wrote (install_lines) counts as loadout's; any other line is yours
    switched = False  # a plugin switch changes: its own backup copy, so restore of this run undoes it
    install_lines = {k: v for k, v in get_dict(record, "install_lines").items() if isinstance(v, str)}
    if install_lines:  # seen uninstalled: a later line is not from loadout's install any more
        listed = installed_plugins()
        if listed is not None:
            present = {_dotted(("plugins", pid), "enabled") for pid in listed}
            install_lines = {k: v for k, v in install_lines.items() if k in present}
    for table, key, value, force in desired_keys():
        dotted = _dotted(table, key)
        line = f"{key} = {toml_value(value)}"
        target = sections[0] if not table else find(table)
        plugin = bool(table) and table[0] == "plugins"
        if target is None:
            header = "[" + ".".join(toml_key(p) for p in table) + "]"
            sections.append([table, [header, line], []])
            owned_keys[dotted] = line
            install_lines.pop(dotted, None)
            switched = switched or plugin
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
            install_lines.pop(dotted, None)
            switched = switched or plugin
        elif target[1][found].strip() == line:
            pass  # the same value: the line stays whoever wrote it (owned only if loadout wrote it before)
        elif force is True or target[1][found].strip() in (owned_keys.get(dotted), install_lines.get(dotted)):
            target[1][found] = line
            owned_keys[dotted] = line
            install_lines.pop(dotted, None)
            switched = switched or plugin
        else:
            lines.append(f"{dotted}: left as is in config.toml (your value)")
            owned_keys.pop(dotted, None)
            install_lines.pop(dotted, None)

    parts = ["\n".join(sections[0][1]).strip("\n")] if any(l.strip() for l in sections[0][1]) else []
    parts += ["\n".join(s[1]).strip("\n") for s in sections[1:]]
    new = "\n\n".join(p for p in parts if p) + "\n" if parts else ""
    new_record = {**record, "tables": owned_tables, "keys": owned_keys}  # keeps project_plugins
    if install_lines:
        new_record["install_lines"] = install_lines
    else:
        new_record.pop("install_lines", None)
    if new == old or (not old.strip() and not new.strip()):
        if new_record != {**record, "tables": record.get("tables", {}), "keys": record.get("keys", {})} and not dry_run:
            save_json(record_path(), new_record)
        return lines
    try:
        after = tl.loads(new)
    except Exception as exc:
        return lines + [f"skipped {path}: the result would not parse ({exc}); nothing written, fix the file by hand"]
    ours_tables, ours_keys = was_tables | set(owned_tables), was_keys | set(owned_keys)
    if _without_owned(before, ours_tables, ours_keys, tl) != _without_owned(after, ours_tables, ours_keys, tl):
        return lines + [f"skipped {path}: the edit would change entries loadout does not own; nothing written"]
    if dry_run:
        return lines + ["config.toml: changes pending"]
    if path.exists() and not (record.get("tables") or record.get("keys")):  # project_plugins alone wrote nothing
        bk.save_copy(path, "Codex config.toml before loadout's first change")
    elif path.exists() and switched:
        bk.save_copy(path, "Codex config.toml before switching plugins on or off")
    elif path.exists() and removed:  # a section goes: restore must be able to bring it back
        bk.save_copy(path, "Codex config.toml before loadout removed one of its sections")
    elif not path.exists():
        bk.record_created(path, "created Codex config.toml")
    from .jsonio import write_atomic
    write_atomic(path, new)
    record_path().parent.mkdir(parents=True, exist_ok=True)
    save_json(record_path(), new_record)
    return lines


OFFICIAL = "anthropics/claude-plugins-official"
_REPO = re.compile(r"^[A-Za-z0-9][\w.-]*/[\w.-]+$")  # owner/repo only: never an option, URL or path


def _json(text: str):
    """codex prints warnings before its JSON on some setups; read from the first line that holds valid JSON.
    None when there is none (never raises)."""
    pos = 0
    for line in text.splitlines(keepends=True):
        if line.lstrip()[:1] in ("{", "["):
            try:
                return json.JSONDecoder().raw_decode(text[pos + len(line) - len(line.lstrip()):])[0]
            except ValueError:
                pass
        pos += len(line)
    return None


def _tail(res: runner.Result) -> str:
    return (res.stderr.strip() or res.stdout.strip())[-300:]


def plugin_routes(settings: dict) -> tuple[dict[str, list[str]], list[str]]:
    """{GitHub source: [plugin names]} for every plugin enabled for Claude Code, and those without a GitHub source."""
    markets = get_dict(settings, "extraKnownMarketplaces")
    routes: dict[str, list[str]] = {}
    missing = []
    for pid, on in get_dict(settings, "enabledPlugins").items():
        if on is not True or not isinstance(pid, str) or "@" not in pid:
            continue
        name, market = pid.rsplit("@", 1)
        source = get_dict(markets.get(market), "source")
        repo = source.get("repo") if source.get("source") == "github" else None
        src = OFFICIAL if market == "claude-plugins-official" else (
            repo if isinstance(repo, str) and _REPO.match(repo) else None)
        if src is None:
            missing.append(pid)
        else:
            routes.setdefault(src, []).append(name)
    return routes, missing


def plugin_versions() -> dict[str, str]:
    """{plugin id: version} of the installed Codex plugins; {} when the list fails."""
    res = runner.run(["codex", "plugin", "list", "--json"], timeout=120)
    data = _json(res.stdout) if res.ok else None
    return {p["pluginId"]: str(p.get("version", "")) for p in get_list(data if isinstance(data, dict) else {}, "installed")
            if isinstance(p, dict) and isinstance(p.get("pluginId"), str)}


def installed_plugins() -> set[str] | None:
    res = runner.run(["codex", "plugin", "list", "--json"], timeout=120)
    data = _json(res.stdout) if res.ok else None
    if not isinstance(data, dict):
        return None
    return {p["pluginId"] for p in get_list(data, "installed") if isinstance(p, dict) and isinstance(p.get("pluginId"), str)}


_NO_PROMPT = {"GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}  # nobody answers a credential prompt here


def marketplaces() -> dict[str, dict] | None:
    """{marketplace name: {"root": str, "source": str | None}} from `codex plugin marketplace list --json` (read-only).
    Codex's own output: anything unexpected gives None, and callers refresh as before."""
    res = runner.run(["codex", "plugin", "marketplace", "list", "--json"], timeout=60)
    data = _json(res.stdout) if res.ok else None
    items = data.get("marketplaces") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return None
    found = {}
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            continue
        source = item.get("marketplaceSource")
        source = source.get("source") if isinstance(source, dict) else None
        found[item["name"]] = {"root": item.get("root") if isinstance(item.get("root"), str) else None,
                               "source": source if isinstance(source, str) else None}
    return found


def remote_head(url: str, ref: str | None) -> str | None:
    """The commit a remote's ref (default HEAD) points at, from `git ls-remote`; None when it cannot be read
    (offline, private, no such ref). url comes from a validated owner/repo or a marketplace's own plugin source."""
    if not url.startswith("https://") or not (ref is None or isinstance(ref, str)):
        return None
    res = runner.run(["git", "ls-remote", url, ref or "HEAD"], timeout=30, env={**os.environ, **_NO_PROMPT})
    first = res.stdout.split(None, 1)[0] if res.ok and res.stdout.strip() else ""
    return first if re.fullmatch(r"[0-9a-fA-F]{7,64}", first) else None


def _record_file() -> Path:
    return paths.state_dir() / "codex-marketplaces.json"


def _load_record() -> dict:
    data = load_json(_record_file())
    return data if isinstance(data, dict) else {}


def _src_url(src: str) -> str | None:
    return f"https://github.com/{src}.git" if _REPO.match(src) else None


def _norm_source(source) -> str | None:
    """A git source as host/path for comparing: https:// or a bare owner/repo (GitHub), the host in lower case,
    without a trailing / or .git. None for anything else."""
    if not isinstance(source, str) or not source.strip():
        return None
    text = source.strip()
    if _REPO.match(text):
        text = f"https://github.com/{text}"
    if not text.lower().startswith("https://"):
        return None
    host, _, path = text[len("https://"):].partition("/")
    path = path.rstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    return f"{host.lower()}/{path}" if host and path else None


def _same_source(listed: dict | None, url: str) -> bool:
    """Whether the marketplace Codex lists comes from url (one removed and re-added from another repo under the same
    name does not)."""
    mine = _norm_source(url)
    return mine is not None and _norm_source((listed or {}).get("source")) == mine


def _sha_less_plugins(info: dict | None) -> dict[str, tuple[str | None, str | None]]:
    """{plugin name: (url, ref)} for the plugins of a marketplace with a source of their own and no pinned sha (read
    from its .claude-plugin/marketplace.json). Those can move without the marketplace head moving. url is None for a
    source that cannot be compared (SSH, git@, file or a local path): such a plugin is always refreshed. A plugin
    in the marketplace's own repo (a path string) or pinned to a sha is not listed: the marketplace head covers it."""
    root = info.get("root") if info else None
    if not root:
        return {}
    data = load_json(Path(root).expanduser() / ".claude-plugin" / "marketplace.json")
    found = {}
    for plug in get_list(data if isinstance(data, dict) else {}, "plugins"):
        src = plug.get("source") if isinstance(plug, dict) else None
        if not isinstance(src, dict) or src.get("sha") or not isinstance(plug.get("name"), str):
            continue
        url = src.get("url") or (f"https://github.com/{src['repo']}.git" if isinstance(src.get("repo"), str)
                                 and _REPO.match(src["repo"]) else None)
        if isinstance(url, str) and url.startswith("https://"):
            ref = src.get("ref")
            found[plug["name"]] = (url, ref if isinstance(ref, str) else None)
        else:
            found[plug["name"]] = (None, None)
    return found


def unchanged_routes(routes: dict[str, list[str]], installed: set[str] | None = None) -> tuple[set[str], set[str]]:
    """(marketplace sources, plugin ids) that need no add, upgrade or reinstall: the remote head equals the one
    loadout recorded after its last refresh, Codex lists the marketplace and every wanted plugin is installed. A
    plugin with its own unpinned git source is skipped only when that source's head is unchanged too. Whatever cannot
    be compared (no record, ls-remote fails, an unparsable list) is left out, so it is refreshed as before."""
    record, listed = _load_record(), marketplaces()
    installed = installed_plugins() if installed is None else installed
    skip_m: set[str] = set()
    skip_p: set[str] = set()
    if listed is None or installed is None:
        return skip_m, skip_p
    for src, names in routes.items():
        entry, url = record.get(src), _src_url(src)
        market = entry.get("name") if isinstance(entry, dict) else None
        if not url or not isinstance(market, str) or market not in listed or not _same_source(listed[market], url):
            continue  # a marketplace of that name from another source is refreshed as before
        head = remote_head(url, None)
        if head is None or head != entry.get("head"):
            continue
        pids = [f"{n}@{market}" for n in names]
        if any(pid not in installed for pid in pids):
            continue
        skip_m.add(src)
        own = _sha_less_plugins(listed[market])
        recorded = get_dict(entry, "plugins")
        for name, pid in zip(names, pids):
            if name not in own:
                skip_p.add(pid)
                continue
            purl, ref = own[name]
            if purl is None:  # an external source that cannot be compared: refreshed as before
                continue
            old = recorded.get(pid)
            now = remote_head(purl, ref)
            if now is not None and isinstance(old, dict) and old.get("head") == now and old.get("url") == purl:
                skip_p.add(pid)
    return skip_m, skip_p


def _remember(src: str, market: str, head: str | None = None, plugin: tuple[str, str, str | None, str | None] | None = None):
    """Record (after a success) that loadout refreshed marketplace src at head, or plugin (pid, url, ref, head)."""
    try:
        import time
        record = _load_record()
        entry = record.get(src) if isinstance(record.get(src), dict) else {}
        entry = {"name": market, "url": _src_url(src), "head": entry.get("head"), "at": entry.get("at", 0),
                 "plugins": get_dict(entry, "plugins")}
        if head:
            entry.update(head=head, at=int(time.time()))
        if plugin and plugin[3]:
            entry["plugins"][plugin[0]] = {"url": plugin[1], "ref": plugin[2], "head": plugin[3]}
        if entry["head"]:
            record[src] = entry
            _record_file().parent.mkdir(parents=True, exist_ok=True)
            save_json(_record_file(), record)
    except OSError:
        pass  # the record only saves time; losing it means the next update refreshes everything


def _install_routes(routes: dict[str, list[str]], bk, refresh: bool, say, listed: set[str] | None,
                    frozen: frozenset = frozenset(), skip_unchanged: bool = False,
                    skips: tuple | None = None) -> tuple[list[str], set[str]]:
    """Add each marketplace and install its plugins. Returns the lines and the plugin ids installed afterwards.
    frozen: marketplaces a refresh leaves as they are (`autoUpdate: false`); missing plugins are still installed.
    skip_unchanged (with refresh): marketplaces and plugins whose upstream head did not move are left alone."""
    lines, installed = [], set(listed or ())
    have = {pid.split("@")[0] for pid in installed}
    if skips is not None and refresh:  # the plan's decisions, as shown
        skip_m, skip_p = set(skips[0]), set(skips[1])
    else:
        skip_m, skip_p = unchanged_routes(routes, set(installed) if listed is not None else None) \
            if skip_unchanged and refresh and listed is not None else (set(), set())
    record = _load_record() if skip_m else {}
    skip_m = {src for src in skip_m if isinstance(get_dict(record, src).get("name"), str)}  # its name is needed
    total = sum(1 for src in routes if src not in skip_m) + sum(
        1 for src, names in routes.items() for name in names
        if (refresh or name not in have) and not (src in skip_m and any(p.startswith(name + "@") for p in skip_p)))
    step = 0
    for src, plugins in routes.items():
        head, refreshed = None, False
        if src in skip_m:
            market = record[src]["name"]
        else:
            step += 1
            say(f"  adding marketplace {src}, a git clone ({step} of {total})…")
            url = _src_url(src)
            head = remote_head(url, None) if url else None  # before the clone: never newer than what Codex got
            res = runner.run(["codex", "plugin", "marketplace", "add", src, "--json"], timeout=900)
            info = _json(res.stdout) if res.ok else None
            if not isinstance(info, dict) or "marketplaceName" not in info:
                lines.append(f"marketplace {src}: failed: {_tail(res)}")
                continue
            market = info["marketplaceName"]
            if not info.get("alreadyAdded") and listed is not None:
                bk.record_command(f"codex marketplace {market}", ["codex", "plugin", "marketplace", "remove", market])
                refreshed = True
            elif refresh and market not in frozen:
                up = runner.run(["codex", "plugin", "marketplace", "upgrade", market], timeout=900)
                refreshed = up.ok
            elif not info.get("alreadyAdded"):
                refreshed = True
            if refreshed:
                _remember(src, market, head)
        own = None
        for name in plugins:
            pid = f"{name}@{market}"
            if pid in installed and (not refresh or market in frozen or pid in skip_p):
                continue
            step += 1
            say(f"  installing plugin {pid} ({min(step, total)} of {total})…")
            before = _enabled_line(pid)
            res = runner.run(["codex", "plugin", "add", pid, "--json"], timeout=600)
            if not res.ok:
                lines.append(f"plugin {pid}: failed: {_tail(res)}")
                continue
            _record_install_line(pid, before)
            if pid not in installed and listed is not None:
                bk.record_command(f"codex plugin {pid}", ["codex", "plugin", "remove", pid])
                lines.append(f"plugin {pid}: installed")
            installed.add(pid)
            if src in skip_m or refreshed or record_has(src):
                if own is None:
                    own = _sha_less_plugins((marketplaces() or {}).get(market))
                if name in own and own[name][0] is not None:
                    purl, ref = own[name]
                    _remember(src, market, plugin=(pid, purl, ref, remote_head(purl, ref)))
    return lines, installed


def record_has(src: str) -> bool:
    return isinstance(_load_record().get(src), dict)


def apply_plugins(bk, refresh: bool = False, say=None, auto: bool = False, skip_unchanged: bool = False,
                  skips: tuple | None = None) -> list[str]:
    """say: called with a progress line before each slow step (git clones of marketplaces, plugin installs).
    auto: an automatic refresh (the daily sync): marketplaces set to `autoUpdate: false` stay as they are, as in
    Claude Code; an explicit `loadout update` passes False and updates every marketplace.
    skip_unchanged (with refresh): leave marketplaces and plugins whose upstream head did not move as they are.
    skips: (marketplace sources, plugin ids) a plan already decided to leave (`loadout update`): used as they are,
    with no second look upstream, so the run does what the plan showed."""
    if not runner.have("codex"):
        return [PLUGINS_EXTENSION]  # extension mode: the extension loads no plugins, and they install through the CLI
    say = say or (lambda line: None)
    from .settings_merge import desired_settings
    desired = desired_settings()
    routes, missing = plugin_routes(desired)
    frozen = frozenset(name for name, cfg in get_dict(desired, "extraKnownMarketplaces").items()
                       if auto and isinstance(cfg, dict) and cfg.get("autoUpdate") is False)
    lines = [f"plugin {pid}: no Codex route (its marketplace is not on GitHub)" for pid in missing]
    return lines + _install_routes(routes, bk, refresh, say, installed_plugins(), frozen, skip_unchanged, skips)[0]


def skill_links() -> list[tuple[Path, Path]]:
    """The personal skills that link.py links for Claude Code, plus the catalog's recommended skills that a tool's
    installer put into ~/.claude/skills (codebase-memory's), so Codex gets the same skills."""
    from . import catalog, link
    claude_skills = paths.claude_home() / "skills"
    pairs = [(paths.agents_skills() / dest.name, src) for dest, src in link.LINKS() if dest.parent == claude_skills]
    linked = {dest.name for dest, _ in pairs}
    if claude_skills.is_dir():
        for entry in sorted(claude_skills.iterdir()):
            known = catalog.match("skill", entry.name, str(entry))
            if (entry.name not in linked and entry.is_dir() and not entry.is_symlink()
                    and known and known.get("status") in ("core", "recommended")):
                pairs.append((paths.agents_skills() / entry.name, entry))
    return pairs


def apply_skills(bk) -> list[str]:
    from . import link
    return [line for dest, src in skill_links() if (line := link._link_one(dest, src, bk))]


def mcp_names() -> set[str] | None:
    res = runner.run([program(), "mcp", "list", "--json"], cwd=str(paths.home()), timeout=120)  # not a repo's servers
    data = _json(res.stdout) if res.ok else None
    return {s["name"] for s in data if isinstance(s, dict) and isinstance(s.get("name"), str)} if isinstance(data, list) else None


def _skill_names(folder: Path) -> set[str]:
    return {p.name for p in folder.iterdir() if not p.name.startswith(".") and p.name != "synced"} if folder.is_dir() else set()


CONFIG_LOCATION = "~/.codex/config.toml"
_CODEX_KEYS = {"command", "args", "env", "env_vars", "url", "bearer_token_env_var", "http_headers", "env_http_headers"}


def user_servers(edited: bool = False) -> dict[str, dict]:
    """The user's [mcp_servers.*] tables in ~/.codex/config.toml, without the ones loadout wrote.
    edited: also the tables of loadout's that you changed since (the secret scan looks at what you added)."""
    tl = _tomllib()
    path = paths.codex_home() / "config.toml"
    if not path.exists():
        return {}
    try:
        servers = tl.loads(path.read_text(encoding="utf-8")).get("mcp_servers", {})
    except Exception:
        return {}
    if not isinstance(servers, dict):
        return {}
    owned = read_record()["tables"]

    def as_written(name, table):
        try:
            return tl.loads(owned[name]).get("mcp_servers", {}).get(name) == table
        except Exception:
            return False
    return {n: t for n, t in servers.items()
            if isinstance(t, dict) and (n not in owned or (edited and not as_written(n, t)))}


def _strs(value, kind) -> bool:
    if kind is list:
        return isinstance(value, list) and all(isinstance(v, str) for v in value)
    return isinstance(value, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in value.items())


def to_claude(name: str, table: dict) -> dict:
    """A Codex server table in the Claude Code format of the personal mcp.json; variables stay variables."""
    extra = sorted(set(table) - _CODEX_KEYS)
    if extra:
        raise Refused(f"mcp {name}: {', '.join(extra)} has no Claude Code equivalent; leave it in Codex or remove it")
    shapes = {"command": str, "url": str, "bearer_token_env_var": str, "args": list, "env_vars": list,
              "env": dict, "http_headers": dict, "env_http_headers": dict}
    for key, kind in shapes.items():
        if key in table and not (isinstance(table[key], str) if kind is str else _strs(table[key], kind)):
            raise Refused(f"mcp {name}: {key} has an unexpected shape; leave it in Codex or remove it")
    if "url" in table:
        headers = dict(table.get("http_headers") or {})
        if table.get("bearer_token_env_var"):
            headers["Authorization"] = f"Bearer ${{{table['bearer_token_env_var']}}}"
        headers.update({k: f"${{{v}}}" for k, v in (table.get("env_http_headers") or {}).items()})
        return {"type": "http", "url": table["url"], **({"headers": headers} if headers else {})}
    if not isinstance(table.get("command"), str):
        raise Refused(f"mcp {name}: neither a command nor a url")
    out = {"type": "stdio", "command": table["command"]}
    if table.get("args"):
        out["args"] = list(table["args"])
    env = dict(table.get("env") or {})
    env.update({k: f"${{{k}}}" for k in table.get("env_vars") or []})
    if env:
        out["env"] = env
    return out


def codex_only_skills() -> list[Path]:
    """Skills in ~/.agents/skills that neither loadout linked nor Claude Code has."""
    root = paths.agents_skills()
    if not root.is_dir():
        return []
    from . import targets
    ours = {dest.name for dest, _ in skill_links()}
    claude = _skill_names(paths.claude_home() / "skills") if targets.claude_enabled() else set()
    return [p for p in sorted(root.iterdir())
            if not p.name.startswith(".") and p.name != "synced" and p.name not in ours | claude]


def remove_server(name: str, bk) -> str:
    """Remove a user's server from ~/.codex/config.toml through Codex itself; the file is saved first (restore
    puts it back)."""
    path = paths.codex_home() / "config.toml"
    if path.exists():
        bk.save_copy(path, f"Codex config.toml before removing mcp {name}")
    res = runner.run([program(), "mcp", "remove", name], cwd=str(paths.home()), timeout=120)
    return f"mcp {name}: removed from Codex" if res.ok else f"mcp {name}: failed: {_tail(res)}"


def drift() -> list[str]:
    """Names present in only one agent and accounted for by neither the kit, the personal layer nor a 'leave'."""
    from . import own, targets
    if not targets.claude_enabled():  # drift compares the two agents; with one agent there is none
        return []
    in_codex = mcp_names()
    if in_codex is None:
        return []
    left = {key.split(":")[-1] for key in own.decisions()}
    personal = set(get_dict(load_json(paths.personal_root() / "mcp.json"), "mcpServers"))
    owned = set(read_record()["tables"])
    in_claude = set(get_dict(load_json(paths.claude_json()), "mcpServers"))
    accounted = left | personal | owned | _codex_serenas()  # a Serena is the kit's tool, never one to adopt
    out = [f'MCP server "{n}" only in Claude Code (record it with loadout adopt, then both get it)'
           for n in sorted(in_claude - in_codex - accounted)]
    out += [f'MCP server "{n}" only in Codex (record it with loadout adopt, then both get it)'
            for n in sorted(in_codex - in_claude - accounted - _plugin_servers())]
    claude_skills, codex_skills = _skill_names(paths.claude_home() / "skills"), _skill_names(paths.agents_skills())
    personal_skills = {dest.name for dest, _ in skill_links()}
    out += [f'skill "{n}" only in Claude Code (record it with loadout adopt, then both get it)'
            for n in sorted(claude_skills - codex_skills - personal_skills - left)]
    out += [f'skill "{n}" only in Codex (record it with loadout adopt, then both get it)'
            for n in sorted(codex_skills - claude_skills - personal_skills - left)]
    return out


def _codex_serenas() -> set[str]:
    """Names of the config.toml servers that start Serena (anyone's)."""
    path = paths.codex_home() / "config.toml"
    try:
        data = _tomllib().loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        return set()
    return {n for n, t in get_dict(data, "mcp_servers").items() if isinstance(t, dict) and is_serena(t)}


def _plugin_servers() -> set[str]:
    """MCP servers that Codex has from installed plugins, from the file each manifest names (else .mcp.json)."""
    names: set[str] = set()
    for root in (paths.codex_home() / "plugins" / "cache").glob("*/*/*"):
        ref = load_json(root / ".codex-plugin" / "plugin.json").get("mcpServers")
        mcp = root / ref if isinstance(ref, str) and paths.inside(root / ref, root) else root / ".mcp.json"
        names |= set(get_dict(load_json(mcp), "mcpServers"))
    return names


HOOKS_TODO = "approve the loadout hooks in Codex once: start `codex`, then run /hooks"


LOCK = "codex.lock"
STALE_LOCK = 3600.0


def _lock(wait: float | None = 0, command: str = "setup", on_wait=None):
    """One Codex setup at a time (bootstrap, configure, the daily sync, update); a lock older than an hour is from a
    crash. wait: 0 tries once (background, session start), None waits until free, a number waits that long."""
    from . import locks
    return locks.acquire(LOCK, command, wait, stale=STALE_LOCK, on_wait=on_wait)


PARTS = ("instructions", "config", "hooks", "skills", "plugins")


def apply_parts(bk, *, refresh: bool, auto: bool, keep: bool, say=None, skip_unchanged: bool = False,
                command: str = "setup", on_wait=None, changed: set | None = None,
                plugins: bool = True, skips: tuple | None = None) -> dict[str, list[str]]:
    """Each part's lines, under the Codex lock. refresh: re-add every plugin and upgrade the marketplaces; auto: the
    daily sync (marketplaces set to `autoUpdate: false` stay as they are, and it never waits for another run);
    keep: Serena's hooks are never removed. skip_unchanged: on a refresh, leave marketplaces and plugins whose upstream head did not move.
    changed: when given, gets "config" when config.toml's bytes changed and, on a refresh, "plugins_updated" when
    an installed plugin's version changed (neither prints a line). A busy lock: the skip line under "instructions".
    plugins: False leaves the marketplaces and plugins alone (no add, install or refresh; `loadout update` with its
    Codex plugin item left out). skips: as in apply_plugins."""
    from . import locks
    lock = _lock(0 if auto else locks.foreground_wait(), command, on_wait)
    if lock is None:
        return {"instructions": [f"skipped: {locks.busy_message(LOCK)}"], **{k: [] for k in PARTS[1:]}}
    try:
        from . import codex_hooks
        config = paths.codex_home() / "config.toml"
        parts = {"instructions": [apply_instructions(bk)]}
        if changed is None:
            parts["config"] = apply_config(bk)
        else:
            before = _bytes(config)
            parts["config"] = apply_config(bk)
            if _bytes(config) != before:
                changed.add("config")
        parts["hooks"] = codex_hooks.apply(bk, keep=keep)
        parts["skills"] = apply_skills(bk)
        if not plugins:
            parts["plugins"] = []
            return parts
        versions = plugin_versions() if changed is not None and refresh and runner.have("codex") else None
        parts["plugins"] = apply_plugins(bk, refresh=refresh, say=say, auto=auto, skip_unchanged=skip_unchanged,
                                         **({"skips": skips} if skips is not None else {}))
        if versions is not None:
            after = plugin_versions()
            if any(pid in versions and versions[pid] != v for pid, v in after.items()):
                changed.add("plugins_updated")
        return parts
    finally:
        lock.release()


def _bytes(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except OSError:
        return None


def apply_all(bk, refresh: bool = False, say=None, command: str = "setup", on_wait=None, *, auto: bool | None = None,
              keep: bool | None = None, skip_unchanged: bool = False, changed: set | None = None,
              plugins: bool = True, skips: tuple | None = None) -> list[str]:
    """refresh=True is the background sync: it never waits for another run, and auto and keep follow it unless
    given. Foreground callers wait for it."""
    parts = apply_parts(bk, refresh=refresh, auto=refresh if auto is None else auto,
                        keep=refresh if keep is None else keep, say=say, skip_unchanged=skip_unchanged,
                        command=command, on_wait=on_wait, changed=changed, plugins=plugins, skips=skips)
    return [line for key in PARTS for line in parts[key]]


def checks() -> list:
    from .check import CheckResult
    if not enabled():
        return []
    problem = unavailable()
    if problem:
        return [CheckResult("Codex", False, problem, "install or update codex (mise use -g codex), or: loadout configure set target codex off", "warn")]
    results = [CheckResult("Codex", True)]
    cli = runner.have("codex")
    if cli:
        installed = installed_plugins()
        ok = installed is not None and "loadout@agent-loadout" in installed
        results.append(CheckResult("Codex plugin", ok, "" if ok else "loadout plugin not installed in Codex",
                                   "loadout bootstrap"))
    else:  # extension mode: plugins need the CLI, and the extension loads none
        results.append(CheckResult("Codex plugin", False, PLUGINS_EXTENSION.split(": ", 1)[1],
                                   "loadout bootstrap --install (the Codex CLI)", "warn"))
    path = paths.codex_home() / "AGENTS.md"
    current = splice(path.read_text(encoding="utf-8") if path.exists() else "", render_instructions())
    ok = path.exists() and current == path.read_text(encoding="utf-8")
    results.append(CheckResult("Codex instructions", ok, "" if ok else f"{_tilde(path)} lacks loadout's current block", "loadout update"))
    if (paths.codex_home() / "AGENTS.override.md").exists():
        results.append(CheckResult("Codex instructions", False, "AGENTS.override.md shadows AGENTS.md, so Codex ignores loadout's block",
                                   "merge it into AGENTS.md or remove it", "warn"))
    pending = apply_config(object(), dry_run=True)
    yours = ("rename or remove that table in ~/.codex/config.toml if you want loadout's; loadout never changes your "
             "entries")
    left = [line for line in pending if "left as is" in line]
    fix = yours if left and len(left) == len(pending) else f"loadout bootstrap; {yours}" if left else "loadout bootstrap"
    results.append(CheckResult("Codex config", not pending, "; ".join(pending), fix, "warn"))
    from . import codex_hooks
    pending_hooks = codex_hooks.apply(object(), dry_run=True)
    hooks_fix = ("add the listed entries to ~/.codex/hooks.json" if pending_hooks
                 and all("add these yourself" in line for line in pending_hooks) else "loadout bootstrap")
    results.append(CheckResult("Codex Serena hooks", not pending_hooks, "; ".join(pending_hooks), hooks_fix, "warn"))
    from .settings_merge import desired_settings
    missing = plugin_routes(desired_settings())[1]
    if missing:
        results.append(CheckResult("Codex plugins", False, "no Codex route for " + ", ".join(missing), "", "warn"))
    status = hooks_status()
    if status in ("untrusted", "changed"):
        results.append(CheckResult("Codex hooks", False, "loadout's hooks are not approved yet" if status == "untrusted"
                                   else "loadout's hooks changed since you approved them",
                                   "start codex, then run /hooks and approve them" if cli else HOOKS_NO_CLI, "warn"))
    elif status == "trusted":
        results.append(CheckResult("Codex hooks", True))
    logins = logins_needed()
    if logins:
        results.append(CheckResult("Codex logins", False, "waiting for a login: " + ", ".join(logins),
                                   "; ".join(f"codex mcp login {n}" for n in logins) if cli else LOGIN_EXTENSION,
                                   "warn"))
    lines = drift()
    results.append(CheckResult("Codex drift", not lines, "; ".join(lines), "loadout adopt (see docs/how-to/your-own-tools.md)", "warn"))
    return results


# --- open steps the user has to take in Codex, named where they work (bootstrap, configure, check)

HOOK_PLUGIN = "loadout@agent-loadout:hooks/codex.json"
HOOKS_CHANGED = "approve the changed loadout hooks in Codex: start `codex`, then run /hooks"


def _codex_hooks_file() -> Path:
    return paths.kit_root() / "plugins" / "loadout" / "hooks" / "codex.json"


def hook_keys() -> set[str]:
    """The keys Codex uses for loadout's hooks in config.toml's [hooks.state] (plugin:file:event:group:hook)."""
    hooks = load_json(_codex_hooks_file()).get("hooks", {})
    snake = lambda name: re.sub(r"(?<!^)([A-Z])", r"_\1", name).lower()  # noqa: E731
    return {f"{HOOK_PLUGIN}:{snake(event)}:{g}:{h}"
            for event, groups in hooks.items() for g, group in enumerate(groups) for h, _ in enumerate(group.get("hooks", []))}


def _hooks_digest() -> str:
    import hashlib
    try:
        return hashlib.sha256(_codex_hooks_file().read_bytes()).hexdigest()
    except OSError:
        return ""


def _hooks_record() -> Path:
    return paths.state_dir() / "codex-hooks.json"


def hooks_status(remember: bool = False) -> str | None:
    """"trusted", "untrusted" (never approved) or "changed" (the hooks changed since the user approved them);
    None when config.toml cannot be read. Codex's own hash cannot be recomputed stably, so a change is detected as:
    the hooks file differs from the last approved one while the stored approvals did not change."""
    tl = _tomllib()
    path = paths.codex_home() / "config.toml"
    try:
        state = tl.loads(path.read_text(encoding="utf-8")).get("hooks", {}) if path.exists() else {}
        state = get_dict(state, "state")
    except Exception:
        return None
    from . import codex_hooks
    serena = codex_hooks.serena_items()  # the Serena hooks in hooks.json need /hooks too, loadout's or the user's
    in_file = f"{codex_hooks.path()}:"  # every hooks.json key, so a Serena hook moved onto one is caught
    current = {k: v.get("trusted_hash") for k, v in state.items()
               if (k.startswith(HOOK_PLUGIN + ":") or k.startswith(in_file)) and isinstance(v, dict)
               and v.get("trusted_hash")}
    if not (hook_keys() | set(serena)) <= set(current):
        return "untrusted"
    digest, seen = _hooks_digest(), load_json(_hooks_record())
    plugin_now = {k: v for k, v in current.items() if k.startswith(HOOK_PLUGIN + ":")}
    plugin_seen = {k: v for k, v in get_dict(seen, "hashes").items() if k.startswith(HOOK_PLUGIN + ":")}
    if seen.get("digest") not in (None, digest) and plugin_seen == plugin_now:
        return "changed"
    # a Serena key whose content changed (edited, or another hook moved onto it) is approved again only when Codex
    # stored a new hash for it; the old hash belongs to what was there before
    seen_items, seen_hashes = get_dict(seen, "serena"), get_dict(seen, "hashes")
    if any(k in seen_hashes and seen_items.get(k) != content and seen_hashes[k] == current.get(k)
           for k, content in serena.items()):
        return "changed"
    record = {"digest": digest, "hashes": current, "serena": serena}
    if remember and seen != record:
        _hooks_record().parent.mkdir(parents=True, exist_ok=True)
        save_json(_hooks_record(), record)
    return "trusted"


def _not_logged_in() -> list[str]:
    res = runner.run([program(), "mcp", "list", "--json"], cwd=str(paths.home()), timeout=120)  # not a repo's servers
    data = _json(res.stdout) if res.ok else None
    return [s["name"] for s in data if isinstance(s, dict) and s.get("auth_status") == "not_logged_in"
            and isinstance(s.get("name"), str)] if isinstance(data, list) else []


def logins_optional() -> list[str]:
    """loadout's own servers that work without a login but allow more with one (Context7's rate limits)."""
    owned = set(read_record()["tables"])
    return [name for name in _not_logged_in() if name in owned]


def logins_needed() -> list[str]:
    """Codex MCP servers that wait for an OAuth login (`codex mcp login NAME`)."""
    res = runner.run([program(), "mcp", "list", "--json"], cwd=str(paths.home()), timeout=120)  # not a repo's servers
    data = _json(res.stdout) if res.ok else None
    # Codex says not_logged_in for every server that offers OAuth, also when it answers anonymously; the servers
    # loadout writes itself are chosen to work without a login (Context7's plain address, verified live)
    owned = set(read_record()["tables"])
    return [s["name"] for s in data if isinstance(s, dict) and s.get("auth_status") == "not_logged_in"
            and isinstance(s.get("name"), str) and s["name"] not in owned] if isinstance(data, list) else []


def open_steps() -> list[str]:
    """What the user still has to do in Codex, for "Still to do" lists; empty when nothing is open."""
    if not enabled():
        return []
    cli = runner.have("codex")
    if not cli and extension_state()[0] is None:
        return []
    status = hooks_status(remember=True)
    # unknown (unreadable config): remind, since the approval cannot be confirmed
    todo = HOOKS_TODO if cli else HOOKS_NO_CLI
    steps = [HOOKS_CHANGED if cli else HOOKS_NO_CLI] if status == "changed" else [] if status == "trusted" else [todo]
    if not cli:
        return (steps + [f"log in to {name} once: {LOGIN_EXTENSION}" for name in logins_needed()]
                + [f"optional: log in to {name} for higher limits: {LOGIN_EXTENSION}" for name in logins_optional()])
    return (steps + [f"log in to {name} in Codex once: codex mcp login {name}" for name in logins_needed()]
            + [f"optional: log in to {name} in Codex for higher limits: codex mcp login {name}" for name in logins_optional()])
