"""Codex CLI as a second target: the same kit and personal layer, mapped to Codex (docs/how-to/codex.md)."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from . import paths, runner
from .jsonio import InvalidJSON, get_dict, get_list, load_json, save_json

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


NOT_FOUND = "codex not found on PATH"
WINDOWS_CODEX = "the codex on PATH is the Windows one"
SHARED_HOME = "CODEX_HOME points into Windows"
NO_VERSION = "could not read codex --version"
TOO_OLD = " is too old; loadout needs"
CLI_OPTIONAL = "not installed (optional: VS Code's Codex extension runs its own)"
CLI_UNUSABLE = "{why}; loadout uses VS Code's Codex extension's codex instead"


_CLI_VERSIONS: dict = {}  # (path, mtime, size) -> the `codex --version` match: one run per binary per process


def _cli_version(found: str | None):
    """The version match of the codex on PATH, asked once per binary that did not change (mode() runs per command)."""
    try:
        st = os.stat(found) if found else None
        key = (found, st.st_mtime_ns, st.st_size) if st else None
    except OSError:
        key = None
    if key is not None and key in _CLI_VERSIONS:
        return _CLI_VERSIONS[key]
    res = runner.run(["codex", "--version"], timeout=20)
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", res.stdout)
    if key is not None:
        _CLI_VERSIONS[key] = m
    return m


def cli_problem() -> str | None:
    """Why the codex on PATH cannot be used (the Windows one in WSL, no version, too old); None when it is usable or
    there is none."""
    from . import wsl
    if not runner.have("codex"):
        return None
    found = runner.which("codex")
    if found and wsl.detect() is not None and wsl.is_windows_program("codex"):
        # one loadout per side (ADR 0029): the Windows Codex never reads the WSL home
        return (f"{WINDOWS_CODEX} ({found}): run bootstrap with --install to install Codex in "
                "WSL, or set loadout up on Windows (docs/how-to/wsl.md#codex)")
    m = _cli_version(found)
    if not m:
        return NO_VERSION
    if (int(m.group(1)), int(m.group(2))) < MIN_VERSION:
        return f"codex {m.group(0)} is too old; loadout needs 0.161 or newer (update it: mise upgrade codex)"
    return None


def _state() -> tuple[str | None, str | None, object]:
    """(mode, why not, the extension): "cli" for a usable codex on PATH, else "extension" when VS Code's Codex
    extension on this side runs a usable one (also next to a CLI that cannot be used; spec decision 8), else None
    with the reason: the CLI's first, then the extension's, then NOT_FOUND."""
    cli = runner.have("codex")
    problem = cli_problem() if cli else NOT_FOUND
    if problem is None:
        return "cli", None, None
    ext, why = extension_state()  # VS Code's Codex extension: loadout sets Codex up for it
    if ext is not None:
        return "extension", None, ext
    return None, problem if cli else (why or NOT_FOUND), None


def no_plugin_command() -> bool:
    """True when the codex loadout runs has no `codex plugin` (an older bundled one in VS Code's Codex extension)."""
    res = runner.run([program(), "plugin", "list", "--json"], timeout=120)
    return not res.ok and _NO_PLUGIN_COMMAND in res.stderr


def has_codex() -> bool:
    """A codex to run plugin commands with: one on PATH (its version is the `Codex` row's business), or VS Code's
    Codex extension's own (ADR 0038)."""
    return runner.have("codex") or mode() is not None


def mode() -> str | None:
    """"cli", "extension" or None (no codex loadout can use on this side)."""
    return _state()[0]


def unavailable(allow_shared_home: bool = False) -> str | None:
    """None when a usable codex is on PATH, or, without one (or next to one that cannot be used), when VS Code's Codex
    extension on this side runs a usable codex (extension mode); else the reason in one line. In WSL, a Windows codex
    and a CODEX_HOME that points into Windows are reasons too (ADR 0029); only bootstrap --codex-side wsl allows the
    latter."""
    from . import wsl
    current, why, _ = _state()
    if current is None:
        return why
    shared = os.environ.get("CODEX_HOME", "")
    if (not allow_shared_home and shared and wsl.detect() is not None
            and wsl._on_windows_drive(Path(shared), wsl.MOUNT)):
        return (f"{SHARED_HOME} ({shared}): both sides would read loadout's WSL commands; unset it "
                "in WSL, or run bootstrap with --codex-side wsl to set it up anyway (docs/how-to/wsl.md#codex)")
    return None


def unavailable_fix(problem: str) -> str:
    """The fix line for the `Codex` check row: one per cause that `unavailable` names."""
    if problem.startswith(NOT_FOUND):
        return "install it: loadout bootstrap --install (or turn Codex off: loadout configure set target codex off)"
    if problem.startswith("VS Code's Codex extension"):
        return "update VS Code's Codex extension, or install the Codex CLI: loadout bootstrap --install"
    if problem.startswith(WINDOWS_CODEX):
        return ("loadout bootstrap --install (installs Codex in WSL), or set loadout up on Windows "
                "(docs/how-to/wsl.md#codex)")
    if problem.startswith(SHARED_HOME):
        return "unset CODEX_HOME in WSL, or: loadout bootstrap --codex-side wsl"
    if problem.startswith(NO_VERSION) or TOO_OLD in problem:
        return "mise upgrade codex (or update it the way you installed it), then loadout update"
    return "install or update codex (mise use -g codex), or: loadout configure set target codex off"


EXT_OLD = ("VS Code's Codex extension runs codex {version}; loadout needs 0.161 or newer: update the extension in "
           "VS Code (or install the Codex CLI: loadout bootstrap --install)")
PLUGINS_OLD = ("plugins: skipped: VS Code's Codex extension's codex has no plugin command; update the extension "
               "in VS Code, then run loadout update")
_NO_PLUGIN_COMMAND = "unrecognized subcommand"
LOGIN_EXTENSION = "in VS Code's Codex extension: gear, MCP servers, Authenticate"
EXT_NOVERSION = ("VS Code's Codex extension's own codex gives no version, so loadout does not use it: update the "
                 "extension in VS Code (or install the Codex CLI: loadout bootstrap --install)")
HOOKS_EXTENSION = ("approve loadout's hooks in VS Code's Codex extension: the hooks icon in the prompt bar, then Allow "
                   "all (or Settings > Hooks)")
HOOKS_EXTENSION_CHANGED = ("approve the changed loadout hooks in VS Code's Codex extension: the hooks icon in the prompt "
                           "bar, then Allow all (or Settings > Hooks)")
RESTART_EXTENSION = ("reload the VS Code window (Command Palette: Developer: Reload Window) so the Codex extension loads "
                     "the plugins")


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
    """The codex loadout runs (`mcp`, `plugin`): the CLI in CLI mode, VS Code's Codex extension's own in extension
    mode (spec decision 1, ADR 0038), else "codex". Undo records keep "codex"; restore runs them with this one."""
    current, _, ext = _state()
    return str(ext.binary) if current == "extension" else "codex"


PROC = Path("/proc")
_CODEX_NAMES = {"codex", "codex.exe"}


def _is_codex(program_path: str) -> bool:
    name = program_path.strip().replace("\\", "/").rsplit("/", 1)[-1]
    return name.lower() in _CODEX_NAMES


def codex_running(platform: str | None = None) -> bool | None:
    """Whether a Codex process (CLI, app, VS Code extension's binary) runs on this OS; None: cannot tell.
    Linux reads /proc without running anything; macOS and Windows ask `ps` / `tasklist`."""
    import sys
    platform = platform or sys.platform
    if platform.startswith("linux"):
        from . import wsl
        if wsl.detect() and wsl._on_windows_drive(paths.codex_home(), wsl.MOUNT):
            return None  # a Windows Codex sharing this home runs where WSL's /proc cannot see it
        try:
            entries = [p for p in PROC.iterdir() if p.name.isdigit()]
        except OSError:
            return None
        for pid in entries:
            try:
                if _is_codex(pid.joinpath("comm").read_text(encoding="utf-8", errors="replace")):
                    return True
                first = pid.joinpath("cmdline").read_bytes().split(b"\x00", 1)[0]
                if first and _is_codex(first.decode("utf-8", "replace")):
                    return True
            except OSError:
                continue
        return False
    if platform == "darwin":
        res = runner.run(["ps", "-A", "-o", "comm="], timeout=10)
        return any(_is_codex(line) for line in res.stdout.splitlines()) if res.ok else None
    if platform == "win32":
        res = runner.run(["tasklist", "/FO", "CSV", "/NH"], timeout=10)
        if not res.ok:
            return None
        return any(_is_codex(line.split(",", 1)[0].strip('"')) for line in res.stdout.splitlines() if line.strip())
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


CBM_PROGRAMS = ("npx", "bunx", "uvx", "uv")
CBM_NAME = "codebase-memory-mcp"


def is_cbm(table: dict) -> bool:
    """A Codex server table that starts codebase-memory's MCP server, whatever its name: the program itself, a full
    path to it, or npx/bunx/uvx/uv naming it. (plugins/loadout/hooks/mcp_guard.py inlines this rule; a test keeps
    them equal.)"""
    command, args = table.get("command"), table.get("args")
    if not isinstance(command, str):
        return False
    base = re.split(r"[\\/]", command)[-1].lower().removesuffix(".exe")
    if base == CBM_NAME:
        return True
    return base in CBM_PROGRAMS and isinstance(args, list) and any(isinstance(a, str) and CBM_NAME in a for a in args)


def user_cbm() -> dict[str, dict]:
    """The user's Codex tables (not loadout's) that start codebase-memory, by name."""
    return {n: t for n, t in user_servers().items() if is_cbm(t)}


def cbm_has_own_settings(table: dict, path_counts: bool = True) -> bool:
    """True when a cbm table is more than the plugin's own server (`command = "codebase-memory-mcp"`, no args or
    `mcp`): any other key (env, cwd, timeouts, tool lists, other args), or (path_counts) a path command, is a
    setting of its own. Claude Code passes path_counts=False: codebase-memory's installer writes its binary's full
    path there, which is not a choice of the user's."""
    args, command = table.get("args"), table.get("command")
    keys = {k for k, v in table.items() if v not in ({}, [], "", None)}  # `claude mcp add` writes "env": {} always
    return bool(keys - {"command", "args", "enabled", "type"}
                or args not in (None, [], ["mcp"])
                or (path_counts and isinstance(command, str) and ("/" in command or "\\" in command)))


SERENA_KEPT = "Serena: your own server in config.toml kept"


def own_serena() -> str | None:
    """The name of the user's own Serena server in config.toml now (one loadout did not write, or wrote and you
    changed), or None. Read-only; bootstrap names it once (apply_config does not: it runs at every update and sync)."""
    path = paths.codex_home() / "config.toml"
    try:
        data = _tomllib().loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        return None
    return user_serena(data, set(read_record()["tables"]))


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


SERENA_APPROVAL = (("mcp_servers", "serena", "tools", "serena_repl"), "approval_mode")
SERENA_APPROVAL_NOTE = ('Serena is your own server in config.toml; to approve its tools, choose "Always allow" in Codex')


def desired_keys(switches: bool = True) -> list[tuple[tuple, str, object, object]]:
    """(table path, key, value, force); path () is the top level. force: loadout's value wins even over a changed
    line, used for project-only plugins because `codex plugin add` switches them back on. switches: False leaves out
    the plugin switches, which need `codex plugin list` (a session start runs no command)."""
    from . import preferences
    from .settings_merge import desired_settings
    state = preferences.detect()

    def answer(pid):
        return state[pid].value or preferences.by_id(pid)["default"]
    keys = [((), "model_reasoning_effort", answer("effort_level"), False),
            (("tui",), "notifications", answer("agent_push_notifications") == "yes", False)]
    if answer("codex_serena_approval") == "approve":  # only while loadout owns serena: apply_config, refresh_record
        keys.append((*SERENA_APPROVAL, "approve", False))
    plugins = project_plugins()
    if plugins:
        on = get_dict(desired_settings(), "enabledPlugins")
        keys += [(("plugins", pid), "enabled", on.get(pid) is True, True) for pid in plugins]
    return keys + (_plugin_switches() if switches else [])


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


def is_tool_section(path, name: str) -> bool:
    """[mcp_servers.NAME.tools.TOOL]: what Codex's "Always allow" writes under a server's table. Your text inside a
    table loadout keeps managing: never compared, never rewritten (ADR 0036)."""
    return isinstance(path, tuple) and path[:3] == ("mcp_servers", name, "tools") and len(path) > 3


def _sections(lines: list[str], tl) -> list[list]:
    """[[path or None, [lines], [top flags]]]: the top level first, then one entry per header. The comment and blank
    lines directly above a [mcp_servers.X.tools.Y] header belong to that sub-table, not to the table before it."""
    out = [[None, [], []]]
    for line, top in zip(lines, _top_lines(lines)):
        if top and line.lstrip().startswith("["):
            out.append([_header_path(line, tl) or ("?", line.strip()), [line], [True]])
        else:
            out[-1][1].append(line)
            out[-1][2].append(top)
    for prev, sec in zip(out, out[1:]):
        if not (isinstance(sec[0], tuple) and len(sec[0]) > 3 and is_tool_section(sec[0], sec[0][1])):
            continue
        n, start = len(prev[1]), 0 if prev[0] is None else 1  # a header line never moves
        while n > start and prev[2][n - 1] and (not prev[1][n - 1].strip() or prev[1][n - 1].lstrip().startswith("#")):
            n -= 1
        sec[1][:0], sec[2][:0] = prev[1][n:], prev[2][n:]
        del prev[1][n:], prev[2][n:]
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
            table = servers.pop(name, None)
            if isinstance(table, dict) and "tools" in table:  # your tool approvals: the guard proves they survive
                servers[name] = {"tools": table["tools"]}
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


def _ownership(sections: list[list], owned_tables: dict[str, str]) -> dict[str, str]:
    """Per [mcp_servers] table loadout recorded: "ours" (as loadout wrote it), "gone", "subtables" or "changed"
    (yours from now on). One rule for apply_config, refresh_record and explain. Tool approvals
    ([mcp_servers.x.tools.y], is_tool_section) are yours inside a table that stays loadout's: they count for nothing."""
    out = {}
    for name, text in owned_tables.items():
        sec = next((s for s in sections if s[0] == ("mcp_servers", name)), None)
        if sec is None:
            out[name] = "gone"
        elif any(s[0] and len(s[0]) > 2 and s[0][:2] == ("mcp_servers", name) and not is_tool_section(s[0], name)
                 for s in sections):
            out[name] = "subtables"  # e.g. [mcp_servers.x.env]; removing x alone would leave Codex unable to start
        else:
            out[name] = "ours" if _text(sec[1]) == text else "changed"
    return out


def _find_key(sections: list[list], table: tuple, key: str):
    """(the section of table, the index of key's line in its lines or None); (None, None) without the table.
    Only a line that starts outside strings and arrays counts."""
    target = sections[0] if not table else next((s for s in sections if s[0] == table), None)
    if target is None:
        return None, None
    flags = target[2]  # a header section's flags already start with the header's own True
    found = next((i for i, l in enumerate(target[1]) if flags[i] and re.match(rf"^\s*{re.escape(key)}\s*=", l)), None)
    return target, found


def _released(record: dict, key: str) -> list[str]:
    value = record.get(key)
    return [n for n in value if isinstance(n, str)] if isinstance(value, list) else []


def _set_list(record: dict, key: str, names) -> None:
    """Kept in the record only while non-empty, like install_lines."""
    names = sorted(set(names))
    if names:
        record[key] = names
    else:
        record.pop(key, None)


def _release_approval(owned_keys: dict, added: set[str]) -> None:
    """serena is no longer loadout's: its approval line and the header loadout added become yours (left in the file,
    out of the record), so neither "ask" nor "approve" touches them again."""
    table, key = SERENA_APPROVAL
    owned_keys.pop(_dotted(table, key), None)
    added.discard(_dotted(table[:-1], table[-1]))


def _drop_approval(sections: list[list], owned_keys: dict, added: set[str]) -> bool:
    """Serena's approval is no longer wanted ("ask each time", or serena is not loadout's): remove only the
    approval_mode line loadout wrote, and the [mcp_servers.serena.tools.serena_repl] header when loadout added it and
    the section holds nothing else. A line you changed, or wrote yourself, stays. True when a line goes."""
    table, key = SERENA_APPROVAL
    dotted, head = _dotted(table, key), _dotted(table[:-1], table[-1])
    line = owned_keys.pop(dotted, None)
    target, found = _find_key(sections, table, key) if line is not None else (None, None)
    if found is None or target[1][found].strip() != line:  # gone, or changed by you: yours, not loadout's
        added.discard(head)
        return False
    del target[1][found]
    if len(target[2]) > found:
        del target[2][found]
    if head in added and len([l for l in target[1] if l.strip()]) == 1:  # only the header loadout added is left
        sections.remove(target)
    added.discard(head)
    return True


def _wanted_tables(data: dict, sections: list[list], still_ours: set[str], released: set[str]):
    """desired_tables for this file. A released table whose text is loadout's exact text again (for example one
    released before ADR 0036 only for its tool approvals) is no Serena of yours: loadout takes it back."""
    full = desired_tables()[0]
    back = {n for n in released if n in full and any(s[0] == ("mcp_servers", n) and _text(s[1]) == full[n]
                                                      for s in sections)}
    return desired_tables(skip_serena=user_serena(data, still_ours | back) is not None)


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
    states = _ownership(sections, owned_tables)
    still_ours = {name for name, state in states.items() if state == "ours"}  # an edited section is yours from now on

    def find(path_):
        return next((s for s in sections if s[0] == path_), None)

    # a table loadout wrote and you changed: yours, said once (here or at a session start), then never again
    released = {n for n in _released(record, "released") if find(("mcp_servers", n)) is not None}
    kept = set(_released(record, "kept"))  # loadout's tables it no longer wants, kept for your tool approvals
    tables, lines = _wanted_tables(before, sections, still_ours, released)
    desired = desired_keys()
    approve = any((t, k) == SERENA_APPROVAL for t, k, _v, _f in desired)
    added = set(_released(record, "added_headers"))  # tables loadout created for its own key (serena's approval)
    # before the tables, only while serena is still loadout's: "ask each time", or a serena table loadout drops (it
    # keeps no approval of loadout's own). A serena that is yours is never touched, nor the approval under it
    if states.get("serena") == "ours" and (not approve or "serena" not in tables):
        removed = _drop_approval(sections, owned_keys, added) or removed
    # tables: drop or keep what loadout wrote, never touch anything else
    for name, text in list(owned_tables.items()):
        state = states[name]
        if state == "gone":
            owned_tables.pop(name)
        elif state == "subtables":
            lines.append(f"mcp {name}: left as is in config.toml (it has sub-tables); loadout no longer manages it")
            owned_tables.pop(name)
            released.add(name)
        elif state == "changed":
            lines.append(f"mcp {name}: left as is in config.toml (changed by you); loadout no longer manages it")
            owned_tables.pop(name)
            released.add(name)
        elif name in tables and tables[name] != text:  # replaced in place: the tools.* sections after it stay put
            sec = find(("mcp_servers", name))
            sec[1][:] = tables[name].rstrip("\n").splitlines()
            sec[2][:] = [True] * len(sec[1])
            owned_tables[name] = tables[name]
            removed = True  # the old text goes: restore must be able to bring it back
        elif name not in tables and any(is_tool_section(s[0], name) for s in sections):
            if name not in kept:  # without its table, your approvals would stop Codex from starting
                lines.append(f"mcp {name}: {KEPT}: your tool approvals ([mcp_servers.{name}.tools.*]) need it")
            kept.add(name)
        elif name not in tables:
            sections.remove(find(("mcp_servers", name)))
            owned_tables.pop(name)
            removed = True
    for name, text in tables.items():
        existing = find(("mcp_servers", name))
        if existing is not None:
            if name in released:
                if _text(existing[1]) == text:  # you put loadout's exact text back: loadout's again, quietly
                    released.discard(name)
                    owned_tables[name] = text
                continue  # yours: no warning
            if owned_tables.get(name) != text and not _same_table(existing[1], text, tl):
                lines.append(f"mcp {name}: left as is, config.toml already has a server of that name")
            continue
        sections.append([("mcp_servers", name), text.rstrip("\n").splitlines(), []])
        owned_tables[name] = text

    serena_ours = "serena" in owned_tables and "serena" in tables  # the approval goes only into loadout's serena
    if not serena_ours:  # serena is yours (or gone): so is loadout's approval line and its header, kept as they are
        _release_approval(owned_keys, added)
    elif not approve:  # e.g. serena was gone and is written again: loadout's old line under it goes
        removed = _drop_approval(sections, owned_keys, added) or removed
    # the note only for a Serena that was always yours: not one loadout wrote and you changed (released)
    own_serena = (approve and _dotted(*SERENA_APPROVAL) not in was_keys
                  and user_serena(before, set(owned_tables) | released) is not None)
    said = set(_released(record, "said"))
    if own_serena and "serena_approval" not in said:  # your own Serena is never changed: said once
        lines.append(SERENA_APPROVAL_NOTE)
    said = {"serena_approval"} if own_serena else set()

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
    released_keys = set(_released(record, "released_keys"))  # your own values, said once
    for table, key, value, force in desired:
        if (table, key) == SERENA_APPROVAL and not serena_ours:
            continue
        dotted = _dotted(table, key)
        line = f"{key} = {toml_value(value)}"
        target, found = _find_key(sections, table, key)
        plugin = bool(table) and table[0] == "plugins"
        if target is None:
            header = "[" + ".".join(toml_key(p) for p in table) + "]"
            sections.append([table, [header, line], []])
            if (table, key) == SERENA_APPROVAL:  # its header goes again with loadout's line ("ask each time")
                added.add(_dotted(table[:-1], table[-1]))
            owned_keys[dotted] = line
            install_lines.pop(dotted, None)
            released_keys.discard(dotted)
            switched = switched or plugin
            continue
        if found is None:
            insert = len(target[1])
            while insert > (1 if target[0] is not None else 0) and not target[1][insert - 1].strip():
                insert -= 1
            target[1].insert(insert, line)
            target[2].insert(insert - (1 if target[0] is not None else 0), True)
            owned_keys[dotted] = line
            install_lines.pop(dotted, None)
            released_keys.discard(dotted)
            switched = switched or plugin
        elif target[1][found].strip() == line:
            if dotted in released_keys:  # you put loadout's value back: loadout's again, quietly
                released_keys.discard(dotted)
                owned_keys[dotted] = line
            # otherwise the line stays whoever wrote it (owned only if loadout wrote it before)
        elif force is True or target[1][found].strip() in (owned_keys.get(dotted), install_lines.get(dotted)):
            target[1][found] = line
            owned_keys[dotted] = line
            install_lines.pop(dotted, None)
            released_keys.discard(dotted)
            switched = switched or plugin
        else:
            if dotted not in released_keys:
                lines.append(f"{dotted}: left as is in config.toml (your value)")
            released_keys.add(dotted)
            owned_keys.pop(dotted, None)
            install_lines.pop(dotted, None)

    parts = ["\n".join(sections[0][1]).strip("\n")] if any(l.strip() for l in sections[0][1]) else []
    parts += ["\n".join(s[1]).strip("\n") for s in sections[1:]]
    new = "\n\n".join(p for p in parts if p) + "\n" if parts else ""
    new_record = {**record, "tables": owned_tables, "keys": owned_keys}  # keeps project_plugins
    _set_list(new_record, "released", released)
    _set_list(new_record, "kept", {n for n in kept if n in owned_tables and n not in tables})
    _set_list(new_record, "released_keys", released_keys)
    _set_list(new_record, "added_headers", added)
    _set_list(new_record, "said", said)
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
        bk.save_copy(path, "Codex config.toml before loadout replaced or removed one of its sections")
    elif not path.exists():
        bk.record_created(path, "created Codex config.toml")
    from .jsonio import write_atomic
    write_atomic(path, new)
    record_path().parent.mkdir(parents=True, exist_ok=True)
    save_json(record_path(), new_record)
    return lines


RELEASES = ("(changed by you)", "(it has sub-tables)", "(your value)")
KEPT = "kept in config.toml"


def is_release(line: str) -> bool:
    """apply_config's line for an entry that just became yours, or a table kept for your tool approvals (each comes
    once: the record then keeps it quiet)."""
    return (("left as is in config.toml" in line and any(mark in line for mark in RELEASES))
            or (line.startswith("mcp ") and f": {KEPT}: your tool approvals" in line))


def refresh_record() -> list[str]:
    """At a session start: record the entries of loadout's in config.toml that you changed as yours, and return one
    note per entry newly yours (each said once; `loadout check` is quiet about it afterwards). Writes only loadout's
    record, never config.toml. Codex on only; another loadout run holding the Codex lock: nothing (no wait), that
    run records it itself. The plugin switches are left to the next run that lists plugins (no command here)."""
    from . import targets
    if not targets.codex_enabled():
        return []
    lock = _lock(0, "session start")
    if lock is None:
        return []
    try:
        path = paths.codex_home() / "config.toml"
        if not path.is_file():
            return []
        tl = _tomllib()
        try:
            text = _read_exact(path)
            tl.loads(text)
        except Exception:  # unreadable or not TOML: apply_config says so; nothing is decided here
            return []
        record = read_record()
        sections = _sections(text.splitlines(), tl)
        owned_tables, owned_keys = dict(record["tables"]), dict(record["keys"])
        install_lines = dict(get_dict(record, "install_lines"))
        released = {n for n in _released(record, "released") if any(s[0] == ("mcp_servers", n) for s in sections)}
        released_keys = set(_released(record, "released_keys"))
        notes = []
        shown = _tilde(path)
        if released:  # a table you put back to loadout's exact text is loadout's again (no note)
            data = tl.loads(text)
            still_ours = {n for n, st in _ownership(sections, owned_tables).items() if st == "ours"}
            wanted = _wanted_tables(data, sections, still_ours, released)[0]  # as apply_config
            for name in sorted(released):
                sec = next(s for s in sections if s[0] == ("mcp_servers", name))
                if wanted.get(name) == _text(sec[1]):
                    released.discard(name)
                    owned_tables[name] = wanted[name]
        for name, state in _ownership(sections, owned_tables).items():
            if state == "ours":
                continue
            owned_tables.pop(name)
            if state != "gone" and name not in released:
                released.add(name)
                how = "you added sub-tables to it" if state == "subtables" else "you changed it"
                notes.append(f"loadout (Codex): mcp {name}: {how} in {shown}, so it is yours now; loadout no longer "
                             "manages it or warns about it")
        added = set(_released(record, "added_headers"))
        if "serena" in released:  # serena is yours now (changed, sub-tables): so is loadout's approval line under it;
            _release_approval(owned_keys, added)  # a deleted table is no release: the next run writes it again
        for table, key, value, force in desired_keys(switches=False):
            if (table, key) == SERENA_APPROVAL and "serena" not in owned_tables:  # not loadout's serena: not its key
                continue
            dotted = _dotted(table, key)
            target, found = _find_key(sections, table, key)
            if found is None or force is True:
                continue
            current = target[1][found].strip()
            if current == f"{key} = {toml_value(value)}" and dotted in released_keys:  # loadout's value again
                released_keys.discard(dotted)
                owned_keys[dotted] = current
                continue
            if current == f"{key} = {toml_value(value)}" or current in (owned_keys.get(dotted), install_lines.get(dotted)):
                continue  # loadout's value, or a line loadout wrote: the next run updates it
            owned_keys.pop(dotted, None)
            install_lines.pop(dotted, None)
            if dotted not in released_keys:
                released_keys.add(dotted)
                notes.append(f"loadout (Codex): {dotted}: your value in {shown} stays yours; loadout no longer "
                             "manages it or warns about it")
        new_record = {**record, "tables": owned_tables, "keys": owned_keys}
        if install_lines != get_dict(record, "install_lines"):
            new_record["install_lines"] = install_lines
            if not install_lines:
                new_record.pop("install_lines")
        _set_list(new_record, "released", released)
        _set_list(new_record, "released_keys", released_keys)
        _set_list(new_record, "added_headers", added)
        if new_record != record:
            record_path().parent.mkdir(parents=True, exist_ok=True)
            save_json(record_path(), new_record)
        return notes
    finally:
        lock.release()


_TABLE_STATES = {"ours": "loadout's value", "changed": "changed by you (yours now)", "gone": "removed",
                 "subtables": "has sub-tables (yours now)",
                 "kept": "loadout's, kept for your tool approvals (tools.* sub-tables)"}


def explain_config() -> list[str]:
    """`loadout explain ~/.codex/config.toml`: loadout's entries there and the state of each, names only (a table
    can hold a token). Read-only. With Codex off it reads no Codex file and shows the record as stored."""
    from . import targets
    path = paths.codex_home() / "config.toml"
    record = read_record()
    released, released_keys = _released(record, "released"), _released(record, "released_keys")
    install_lines = {k: v for k, v in get_dict(record, "install_lines").items() if isinstance(v, str)}
    if not targets.codex_enabled():
        out = [f"{_tilde(path)}: Codex is off, so loadout reads no Codex file; entries as recorded at loadout's last "
               f"Codex run (in {_tilde(record_path())}):"]
        kept = set(_released(record, "kept"))
        out += [f"  mcp {n}  loadout's" + (" (kept for your tool approvals)" if n in kept else "")
                for n in sorted(record["tables"])]
        out += [f"  {k}  loadout's" for k in sorted({*record["keys"], *install_lines})]
        out += [f"  mcp {n}  yours (you changed it)" for n in released]
        out += [f"  {k}  yours (your value)" for k in released_keys]
        return out + ["  turn Codex on (loadout configure set target codex on) to compare them with the file"]
    out = [f"{_tilde(path)}: entries loadout wrote (recorded in {_tilde(record_path())})"]
    tl = _tomllib()
    try:
        text = _read_exact(path) if path.exists() else ""
        tl.loads(text)
    except Exception:
        names = [f"mcp {n}" for n in sorted(record["tables"])] + sorted({*record["keys"], *install_lines})
        return out + [f"  {n}  cannot compare, the file does not parse" for n in names]
    sections = _sections(text.splitlines(), tl)
    kept = set(_released(record, "kept"))
    for name, state in sorted(_ownership(sections, record["tables"]).items()):
        out.append(f"  mcp {name}  {_TABLE_STATES['kept' if state == 'ours' and name in kept else state]}")
    for dotted, line in sorted({**install_lines, **record["keys"]}.items()):
        try:
            *table, key = _key_path(dotted, tl)
        except Exception:
            continue
        target, found = _find_key(sections, tuple(table), key)
        if found is None:
            state = "removed"
        elif target[1][found].strip() == line:
            state = "loadout's value" if dotted in record["keys"] else "loadout's (its codex plugin add wrote it)"
        else:
            state = "changed by you (yours now)"
        out.append(f"  {dotted}  {state}")
    out += [f"  mcp {n}  yours (you changed it; loadout no longer manages it)" for n in released
            if any(s[0] == ("mcp_servers", n) for s in sections)]  # a deleted section is nobody's entry

    def present(dotted):
        try:
            *table, key = _key_path(dotted, tl)
        except Exception:
            return False
        return _find_key(sections, tuple(table), key)[1] is not None
    out += [f"  {k}  yours (your value; loadout no longer manages it)" for k in released_keys if present(k)]
    return out + ["  everything else in this file is yours; loadout does not change it"]


def explain_hooks() -> list[str]:
    """`loadout explain ~/.codex/hooks.json`: Serena's hook entries loadout added and whether each is still as it
    wrote it. Read-only; with Codex off it reads no Codex file."""
    from . import codex_hooks, targets
    path = codex_hooks.path()
    owned = [o for o in read_record().get("hooks", []) if isinstance(o, dict)]

    def label(o):
        try:
            command = json.loads(o.get("group"))["hooks"][0]["command"]
        except Exception:
            command = "a hook"
        return f"{o.get('event')} {command}"
    if not targets.codex_enabled():
        return ([f"{_tilde(path)}: Codex is off, so loadout reads no Codex file; entries as recorded at loadout's "
                 f"last Codex run (in {_tilde(record_path())}):"]
                + [f"  {label(o)}  loadout's" for o in owned]
                + ["  turn Codex on (loadout configure set target codex on) to compare them with the file"])
    out = [f"{_tilde(path)}: entries loadout wrote (recorded in {_tilde(record_path())})"]
    try:
        data = json.loads(path.read_bytes().decode("utf-8")) if path.exists() else {}
        events = data.get("hooks", {}) if isinstance(data, dict) else {}
        events = events if isinstance(events, dict) else {}
    except (OSError, ValueError):
        return out + [f"  {label(o)}  cannot compare, the file is not valid JSON" for o in owned]
    for o in owned:
        groups = events.get(o.get("event"))
        here = isinstance(groups, list) and any(codex_hooks._canon(g) == o.get("group") for g in groups)
        out.append(f"  {label(o)}  {'loadout' + chr(39) + 's entry' if here else 'changed or removed by you (yours now)'}")
    if not owned:
        out.append("  (none)")
    return out + ["  everything else in this file is yours; loadout does not change it"]


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
    res = runner.run([program(), "plugin", "list", "--json"], timeout=120)
    data = _json(res.stdout) if res.ok else None
    return {p["pluginId"]: str(p.get("version", "")) for p in get_list(data if isinstance(data, dict) else {}, "installed")
            if isinstance(p, dict) and isinstance(p.get("pluginId"), str)}


class Installed(set):
    """The installed plugin ids, a plain set to every caller, plus `versions`: {plugin id: the version Codex lists,
    which names its active folder in plugins/cache/<marketplace>/<plugin>/}."""
    def __init__(self, ids=(), versions: dict[str, str] | None = None):
        super().__init__(ids)
        self.versions = dict(versions or {})


def installed_plugins() -> Installed | None:
    res = runner.run([program(), "plugin", "list", "--json"], timeout=120)
    data = _json(res.stdout) if res.ok else None
    if not isinstance(data, dict):
        return None
    items = [p for p in get_list(data, "installed") if isinstance(p, dict) and isinstance(p.get("pluginId"), str)]
    return Installed((p["pluginId"] for p in items),
                     {p["pluginId"]: p["version"] for p in items if isinstance(p.get("version"), str)})


_NO_PROMPT = {"GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}  # nobody answers a credential prompt here


def marketplaces() -> dict[str, dict] | None:
    """{marketplace name: {"root": str, "source": str | None}} from `codex plugin marketplace list --json` (read-only).
    Codex's own output: anything unexpected gives None, and callers refresh as before."""
    res = runner.run([program(), "plugin", "marketplace", "list", "--json"], timeout=60)
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


def _sha_less_plugins(info: dict | None) -> dict[str, tuple[str | None, str | None]] | None:
    """{plugin name: (url, ref)} for the plugins of a marketplace with a source of their own and no pinned sha (read
    from its .claude-plugin/marketplace.json). Those can move without the marketplace head moving. url is None for a
    source that cannot be compared (SSH, git@, file or a local path): such a plugin is always refreshed. A plugin
    in the marketplace's own repo (a path string) or pinned to a sha is not listed: the marketplace head covers it.
    None when the cached marketplace.json cannot be read (malformed, not UTF-8): nothing of it can be compared."""
    root = info.get("root") if info else None
    if not root:
        return {}
    try:
        data = load_json(Path(root).expanduser() / ".claude-plugin" / "marketplace.json")
    except (InvalidJSON, OSError):
        return None
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
        own = _sha_less_plugins(listed[market])
        if own is None:  # its marketplace.json cannot be read: refreshed as before
            continue
        skip_m.add(src)
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


CLONE_TIMEOUT = 1800  # a large marketplace (pbakaus/impeccable: 400+ MB) outlasted 900 s on a real machine
LARGE_CLONE = "large repositories can take several minutes"
_held_lock = None  # the Codex lock apply_parts holds, renewed before each long codex call (_keep_lock)
UPGRADE_RETRY_WAIT = 5  # seconds before the one retry of a failed `marketplace upgrade` (not after a timeout)


def _keep_lock() -> None:
    """Renew the held Codex lock: clones and upgrades can each take up to CLONE_TIMEOUT, and a lock older than
    STALE_LOCK may be taken over by another run while this one still works."""
    if _held_lock is not None:
        _held_lock.touch()


def _upgrade(exe: str, market: str) -> runner.Result:
    """`codex plugin marketplace upgrade <market>`, tried once more after a short wait when it fails (a refresh can
    lose a race with a running Codex's own auto-upgrade, or the network blips); a timeout, loadout's or Codex's own,
    is not tried again (each failed Codex try leaves one more clone in its staging folder)."""
    cmd = [exe, "plugin", "marketplace", "upgrade", market]
    _keep_lock()
    res = runner.run(cmd, timeout=CLONE_TIMEOUT)
    if res.ok or res.returncode == 124 or _codex_timed_out(res):
        return res
    import time
    time.sleep(UPGRADE_RETRY_WAIT)
    _keep_lock()
    return runner.run(cmd, timeout=CLONE_TIMEOUT)


TIMEOUT_ISSUE = "openai/codex#38770"


def _codex_timed_out(res: runner.Result) -> bool:
    """Codex's own fixed 30 s clone limit of `marketplace upgrade` hit (not loadout's runner timeout, exit 124)."""
    if res.ok or res.returncode == 124:
        return False
    text = (res.stderr + res.stdout).lower()
    return "timed out after" in text and ("git clone" in text or "marketplace" in text)


def _market_table(market: str) -> dict | None:
    """The user's `[marketplaces.<market>]` table in Codex's config.toml; None when missing or unreadable."""
    import tomllib
    try:
        data = tomllib.loads((paths.codex_home() / "config.toml").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return None
    table = get_dict(get_dict(data, "marketplaces"), market)
    return table if market in get_dict(data, "marketplaces") else None


def _table_blockers(market: str, src: str) -> list[str]:
    """The keys of the user's table that `marketplace add <src>` would not write again (sorted)."""
    table = _market_table(market) or {}
    out = []
    ref = table.get("ref_name")
    if ref and not src.endswith(f"@{ref}"):
        out.append("ref_name")
    if table.get("sparse_paths"):
        out.append("sparse_paths")
    return sorted(out)


_CODEX_TABLE_KEYS = ("last_updated", "last_revision")  # what `marketplace add` refreshes in an unchanged table


def _keep_user_text(cfg: Path, saved: bytes, market: str) -> None:
    """After a re-add: put the user's config.toml back byte for byte, with only the values Codex refreshed
    (last_updated, last_revision) set in the marketplace's table. Codex's own file stays unless the result parses
    to exactly what Codex wrote."""
    import tomllib
    from .jsonio import write_atomic_bytes
    try:
        now = tomllib.loads(cfg.read_text(encoding="utf-8"))
        text = saved.decode("utf-8")
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return
    fresh = get_dict(get_dict(now, "marketplaces"), market)
    name = re.escape(market)
    headers = list(re.finditer(rf"""^[ \t]*\[[ \t]*marketplaces[ \t]*\.[ \t]*(?:{name}|"{name}"|'{name}')[ \t]*\]"""
                               r"[ \t]*(?:#[^\r\n]*)?\r?$", text, re.M))
    if len(headers) != 1:
        return
    start = headers[0].end()
    nxt = re.compile(r"^[ \t]*\[", re.M).search(text, start)
    end = nxt.start() if nxt else len(text)
    region = text[start:end]
    nl = "\r\n" if "\r\n" in text else "\n"
    for key in _CODEX_TABLE_KEYS:
        value = fresh.get(key)
        if not isinstance(value, str):
            continue
        pat = re.compile(rf"""^([ \t]*{key}[ \t]*=[ \t]*)("(?:[^"\\\n]|\\.)*"|'[^'\n]*')""", re.M)
        if pat.search(region):
            region = pat.sub(lambda m: m.group(1) + json.dumps(value), region, count=1)
        else:
            body = region.rstrip("\r\n")  # a new key goes after the table's last line, before its blank lines
            region = f"{body}{nl}{key} = {json.dumps(value)}" + region[len(body):]
    new = text[:start] + region + text[end:]
    try:
        if tomllib.loads(new) != now:
            return
    except tomllib.TOMLDecodeError:
        return
    try:
        write_atomic_bytes(cfg, new.encode("utf-8"))
    except OSError:
        pass  # Codex's own file is valid and stays; the user's original is in the run's backup


def _drop_older_snapshot_copies(market: str, keep: Path) -> None:
    """Keep only the newest backed-up snapshot of `market`: copies in older backups go (their restore step then
    reports nothing left), so the backups hold at most one stale clone per marketplace."""
    import shutil
    from . import backup
    label = f"codex marketplace snapshot {market}"
    for b in backup.backups():
        if b.path == keep:
            continue
        for step in b.steps:
            undo = step.get("undo")
            src = undo.get("move", [None])[0] if isinstance(undo, dict) and step.get("label") == label else None
            if not isinstance(src, str):
                continue
            copy = Path(src)
            try:
                inside = copy.resolve().is_relative_to((b.path / "files").resolve())
            except (OSError, RuntimeError):
                inside = False
            if inside and copy.is_dir() and not copy.is_symlink():
                shutil.rmtree(copy, ignore_errors=True)


def _readd(exe: str, src: str, market: str, bk) -> tuple[bool, str]:
    """Remove the marketplace and add it again (`add` clones with no time limit), after a backup of config.toml and
    with the snapshot moved aside; any failure puts both back. Returns (ok, the failure's detail)."""
    import shutil
    from .jsonio import write_atomic_bytes
    cfg = paths.codex_home() / "config.toml"
    snap = paths.codex_home() / ".tmp" / "marketplaces" / market
    saved = cfg.read_bytes() if cfg.is_file() else None
    if saved is not None:
        bk.save_copy(cfg, f"codex config before re-adding {market}")
    try:
        moved = bk.move(snap, f"codex marketplace snapshot {market}") if snap.exists() else None
    except OSError as err:  # nothing removed yet: the marketplace stays as it is
        return False, f"could not move its snapshot aside: {err}"
    _keep_lock()
    res = runner.run([exe, "plugin", "marketplace", "remove", market], timeout=120)
    if res.ok:
        _keep_lock()
        res = runner.run([exe, "plugin", "marketplace", "add", src, "--json"], timeout=CLONE_TIMEOUT)
        info = _json(res.stdout) if res.ok else None
        if isinstance(info, dict) and "marketplaceName" in info:
            if saved is not None:
                _keep_user_text(cfg, saved, market)
            if moved is not None:
                _drop_older_snapshot_copies(market, bk.root)
            return True, ""
    why = _tail(res)
    if saved is not None and _market_table(market) is None:  # a running Codex may have written it again: keep that
        try:  # the user's file first: it must come back even if the snapshot cannot
            write_atomic_bytes(cfg, saved)
        except OSError:
            why += "; your config.toml stays in the backup (loadout restore puts it back)"
    if moved is not None and not snap.exists():
        try:
            shutil.move(str(moved), str(snap))
        except OSError:
            why += "; the old snapshot stays in the backup (loadout restore puts it back)"
    return False, why


def _install_routes(routes: dict[str, list[str]], bk, refresh: bool, say, listed: set[str] | None,
                    frozen: frozenset = frozenset(), skip_unchanged: bool = False,
                    skips: tuple | None = None) -> tuple[list[str], set[str]]:
    """Add each marketplace and install its plugins. Returns the lines and the plugin ids installed afterwards.
    frozen: marketplaces a refresh leaves as they are (`autoUpdate: false`); missing plugins are still installed.
    skip_unchanged (with refresh): marketplaces and plugins whose upstream head did not move are left alone."""
    exe = program()  # one codex for the whole run, asked once
    lines, installed = [], set(listed or ())
    have = {pid.split("@")[0] for pid in installed}
    planned = skips is not None and refresh
    if planned:  # the plan's decisions, as shown: authoritative, whatever a second look says
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
        head, refreshed, stale = None, False, False
        if src in skip_m:
            market = record[src]["name"]
        else:
            step += 1
            say(f"  adding marketplace {src}, a git clone ({step} of {total}; {LARGE_CLONE})…")
            url = _src_url(src)
            head = remote_head(url, None) if url else None  # before the clone: never newer than what Codex got
            _keep_lock()
            res = runner.run([exe, "plugin", "marketplace", "add", src, "--json"], timeout=CLONE_TIMEOUT)
            if not res.ok and _NO_PLUGIN_COMMAND in res.stderr:  # an extension codex from before `codex plugin`
                return lines + [PLUGINS_OLD], installed
            info = _json(res.stdout) if res.ok else None
            if not isinstance(info, dict) or "marketplaceName" not in info:
                lines.append(f"marketplace {src}: failed: {_tail(res)}")
                continue
            market = info["marketplaceName"]
            if not info.get("alreadyAdded") and listed is not None:
                bk.record_command(f"codex marketplace {market}", ["codex", "plugin", "marketplace", "remove", market])
                refreshed = True
            elif refresh and market not in frozen:
                up = _upgrade(exe, market)
                refreshed, stale = up.ok, not up.ok
                if stale:  # its plugins would be added again from the old snapshot: they stay as they are
                    line = (f"marketplace {market}: failed to upgrade ({_tail(up)}); its installed plugins stay "
                            "at the previous version")
                    if _codex_timed_out(up):  # Codex's fixed 30 s clone limit: `add` has none (ADR 0042)
                        blockers, running = _table_blockers(market, src), None
                        if not blockers:
                            running = codex_running()
                        if blockers:
                            line += f"; loadout did not re-add it because your table sets {', '.join(blockers)}"
                        elif running is not False:
                            unsure = "could not tell whether Codex runs; " if running is None else ""
                            line = (f"marketplace {market}: Codex's upgrade timed out after 30s; {unsure}quit Codex "
                                    f"and run loadout update again to re-add it ({TIMEOUT_ISSUE})")
                        else:
                            ok, why = _readd(exe, src, market, bk)
                            if ok:
                                refreshed, stale = True, False
                                line = (f"marketplace {market}: Codex's upgrade timed out after 30s; removed and "
                                        f"added it again ({TIMEOUT_ISSUE})")
                            else:
                                line += f"; re-adding it failed too ({why})"
                    lines.append(line)
            elif not info.get("alreadyAdded"):
                refreshed = True
            if refreshed:
                _remember(src, market, head)
        own = None
        for name in plugins:
            pid = f"{name}@{market}"
            if (planned and pid in skip_p) or (pid in installed and (not refresh or market in frozen or pid in skip_p
                                                                     or stale)):
                continue
            if stale and listed is None:  # which ones are installed is unknown: the old snapshot could downgrade any
                continue
            step += 1
            say(f"  installing plugin {pid} ({min(step, total)} of {total})…")
            before = _enabled_line(pid)
            _keep_lock()
            res = runner.run([exe, "plugin", "add", pid, "--json"], timeout=600)
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
                    own = _sha_less_plugins((marketplaces() or {}).get(market)) or {}
                if name in own and own[name][0] is not None:
                    purl, ref = own[name]
                    _remember(src, market, plugin=(pid, purl, ref, remote_head(purl, ref)))
    return lines, installed


def missing_routes(installed: set[str] | None = None,
                   listed: dict[str, dict] | None = None) -> tuple[list[str], list[str]]:
    """(marketplace sources, plugin entries) loadout wants in Codex but Codex lacks, for `loadout check` and "Still to
    do". A plugin entry is its full `name@market` id; while its marketplace is missing it is `name (from source)`, since
    the id is unknown until the marketplace exists. loadout's own plugin is left to the `Codex plugin` row.
    installed / listed: what installed_plugins() and marketplaces() returned, when the caller already has them.
    ([], []) without a codex or when a listing fails."""
    if not has_codex():
        return [], []
    from .settings_merge import desired_settings
    desired = desired_settings()
    routes = plugin_routes(desired)[0]
    own = get_dict(get_dict(get_dict(desired, "extraKnownMarketplaces"), "agent-loadout"), "source").get("repo")
    claude_names: dict[str, str] = {}  # source -> the Claude Code marketplace name, a fallback for a source-less listing
    for pid, on in get_dict(desired, "enabledPlugins").items():
        if on is True and isinstance(pid, str) and "@" in pid:
            market = pid.rsplit("@", 1)[1]
            src = OFFICIAL if market == "claude-plugins-official" else get_dict(
                get_dict(get_dict(desired, "extraKnownMarketplaces"), market), "source").get("repo")
            if isinstance(src, str):
                claude_names.setdefault(src, market)
    if not routes:
        return [], []
    installed = installed_plugins() if installed is None else installed
    listed = marketplaces() if listed is None else listed
    if installed is None or listed is None:
        return [], []
    record = _load_record()
    lacks_m: list[str] = []
    lacks_p: list[str] = []
    for src, names in routes.items():
        names = [n for n in names if not (n == "loadout" and src == own)]
        if not names:
            continue
        url = _src_url(src) or ""
        market = next((name for name, info in listed.items() if _same_source(info, url)), None)
        if market is None:  # Codex lists no source for it: the name loadout recorded, or Claude Code's
            for name in (get_dict(record, src).get("name"), claude_names.get(src)):
                if isinstance(name, str) and name in listed and get_dict(listed, name).get("source") is None:
                    market = name
                    break
        if market is None:
            lacks_m.append(src)
            lacks_p.extend(f"{n} (from {src})" for n in names)
            continue
        lacks_p.extend(pid for pid in (f"{n}@{market}" for n in names) if pid not in installed)
    return lacks_m, lacks_p


MISSING_FIX = "loadout update (retries them)"


def _missing_text(lacks: tuple[list[str], list[str]]) -> str:
    parts = []
    if lacks[0]:
        parts.append("marketplaces " + ", ".join(lacks[0]))
    if lacks[1]:
        parts.append("plugins " + ", ".join(lacks[1]))
    return "Codex lacks " + "; ".join(parts)


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
    accounted = left | personal | owned | _codex_serenas() | _codex_cbms()  # a Serena is the kit's tool, never one to adopt
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


def _codex_cbms() -> set[str]:
    """Names of the config.toml tables that start codebase-memory under a name other than the plugin's (check names
    those; the same-name table keeps its usual handling)."""
    return set(user_cbm()) - {CBM_NAME}


def _codex_serenas() -> set[str]:
    """Names of the config.toml servers that start Serena (anyone's)."""
    path = paths.codex_home() / "config.toml"
    try:
        data = _tomllib().loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        return set()
    return {n for n, t in get_dict(data, "mcp_servers").items() if isinstance(t, dict) and is_serena(t)}


def plugin_mcp_files() -> list[Path]:
    """Each installed Codex plugin's MCP server file: the one its .codex-plugin/plugin.json names (inside the plugin),
    else .mcp.json."""
    files = []
    for root in (paths.codex_home() / "plugins" / "cache").glob("*/*/*"):
        try:
            ref = load_json(root / ".codex-plugin" / "plugin.json").get("mcpServers")
        except Exception:  # an unreadable manifest: the default file
            ref = None
        files.append(root / ref if isinstance(ref, str) and paths.inside(root / ref, root) else root / ".mcp.json")
    return files


def _plugin_servers() -> set[str]:
    """MCP servers that Codex has from installed plugins, from the file each manifest names (else .mcp.json).
    A broken server file counts for nothing, so check, drift and the inventory never stop on it."""
    names: set[str] = set()
    for mcp in plugin_mcp_files():
        try:
            names |= {n for n in get_dict(load_json(mcp), "mcpServers") if isinstance(n, str)}
        except Exception:
            continue
    return names


LOADOUT_PLUGIN = "loadout@agent-loadout"


def _loadout_plugin_servers(version: str | None) -> set[str]:
    """Names of the MCP servers loadout's own Codex plugin provides (loadout_plugin_tables)."""
    return set(loadout_plugin_tables(version))


def loadout_plugin_tables(version: str | None) -> dict[str, dict]:
    """The MCP servers loadout's own Codex plugin provides (name -> its table), from the manifest of its active copy
    only (plugins/cache/agent-loadout/loadout/<version>, the version `codex plugin list` names): an older copy Codex
    keeps in its cache is not what it loads. No usable version, a broken manifest or server file: nothing."""
    base = paths.codex_home() / "plugins" / "cache" / "agent-loadout" / "loadout"
    if not isinstance(version, str) or version in ("", ".", "..") or "/" in version or "\\" in version:
        return {}
    root = base / version
    if not root.is_dir() or not paths.inside(root, base):
        return {}
    try:
        ref = load_json(root / ".codex-plugin" / "plugin.json").get("mcpServers")
    except Exception:
        ref = None
    mcp = root / ref if isinstance(ref, str) and paths.inside(root / ref, root) else root / ".mcp.json"
    try:
        return {n: t for n, t in get_dict(load_json(mcp), "mcpServers").items() if isinstance(n, str) and isinstance(t, dict)}
    except Exception:
        return {}


def servers_twice(installed: set[str] | None) -> list[str]:
    """The user's own config.toml servers that loadout's Codex plugin (installed, not switched off) also provides."""
    if installed is None or LOADOUT_PLUGIN not in installed:
        return []
    path = paths.codex_home() / "config.toml"
    try:
        data = _tomllib().loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        return []
    if get_dict(get_dict(data, "plugins"), LOADOUT_PLUGIN).get("enabled") is False:
        return []
    version = getattr(installed, "versions", {}).get(LOADOUT_PLUGIN)  # from the list checks() already fetched
    return sorted(set(user_servers()) & _loadout_plugin_servers(version))


def plugin_serves_cbm(installed: set[str] | None = None) -> bool:
    """Whether loadout's Codex plugin starts codebase-memory here: installed (the plugin list when given, else its
    cached copy), not switched off, and its server name not switched off (`[mcp_servers.codebase-memory-mcp]
    enabled = false`). The one rule for "a table of yours is a second server"."""
    path = paths.codex_home() / "config.toml"
    try:
        data = _tomllib().loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        return False
    if get_dict(get_dict(data, "plugins"), LOADOUT_PLUGIN).get("enabled") is False:
        return False
    if get_dict(get_dict(data, "mcp_servers"), CBM_NAME).get("enabled") is False:
        return False
    if installed is None:  # the plugin list, not the cache: Codex keeps cached copies after an uninstall
        installed = installed_plugins()
    return installed is not None and LOADOUT_PLUGIN in installed


def cbm_twice(installed: set[str] | None) -> list[str]:
    """The names of the user's config.toml tables that start codebase-memory under a name other than the plugin's
    and are on, while the loadout plugin starts its own: Codex runs both."""
    if installed is None or not plugin_serves_cbm(installed):
        return []
    return sorted(n for n, t in user_cbm().items() if n != CBM_NAME and t.get("enabled") is not False)


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
                plugins: bool = True, skips: tuple | None = None, only: tuple | None = None) -> dict[str, list[str]]:
    """Each part's lines, under the Codex lock. refresh: re-add every plugin and upgrade the marketplaces; auto: the
    daily sync (marketplaces set to `autoUpdate: false` stay as they are, and it never waits for another run);
    keep: Serena's hooks are never removed. skip_unchanged: on a refresh, leave marketplaces and plugins whose upstream head did not move.
    changed: when given, gets "config" when config.toml's bytes changed and, on a refresh, "plugins_updated" when
    an installed plugin's version changed (neither prints a line). A busy lock: the skip line under "instructions".
    plugins: False leaves the marketplaces and plugins alone (no add, install or refresh; `loadout update` with its
    Codex plugin item left out). skips: as in apply_plugins. only: the parts to run (e.g. ("plugins",): `loadout
    update` with item 1 left out but its Codex plugin item kept); the others give no lines and change nothing."""
    from . import locks
    lock = _lock(0 if auto else locks.foreground_wait(), command, on_wait)
    if lock is None:
        return {"instructions": [f"skipped: {locks.busy_message(LOCK)}"], **{k: [] for k in PARTS[1:]}}
    global _held_lock
    _held_lock = lock
    try:
        from . import codex_hooks
        config = paths.codex_home() / "config.toml"
        run = set(PARTS if only is None else only)
        parts = {k: [] for k in PARTS}
        if "instructions" in run:
            parts["instructions"] = [apply_instructions(bk)]
        if "config" in run:
            before = _bytes(config)
            parts["config"] = apply_config(bk)
            if changed is not None and _bytes(config) != before:
                changed.add("config")
        remind_before = plugin_runs_remind() if "hooks" in run and not keep else None
        if "hooks" in run:
            parts["hooks"] = codex_hooks.apply(bk, keep=keep)
        if "skills" in run:
            parts["skills"] = apply_skills(bk)
        plugins = plugins and "plugins" in run
        if not plugins:
            parts["plugins"] = []
            return parts
        versions = plugin_versions() if changed is not None and refresh and has_codex() else None
        parts["plugins"] = apply_plugins(bk, refresh=refresh, say=say, auto=auto, skip_unchanged=skip_unchanged,
                                         **({"skips": skips} if skips is not None else {}))
        if remind_before is not None and plugin_runs_remind() != remind_before:
            # this run's plugin install, upgrade or removal moved Serena's remind: one more pass finishes the move
            parts["hooks"] += codex_hooks.apply(bk, keep=keep)
        if versions is not None:
            after = plugin_versions()
            if any(pid in versions and versions[pid] != v for pid, v in after.items()):
                changed.add("plugins_updated")
        return parts
    finally:
        _held_lock = None
        lock.release()


def _bytes(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except OSError:
        return None


def apply_all(bk, refresh: bool = False, say=None, command: str = "setup", on_wait=None, *, auto: bool | None = None,
              keep: bool | None = None, skip_unchanged: bool = False, changed: set | None = None,
              plugins: bool = True, skips: tuple | None = None, only: tuple | None = None) -> list[str]:
    """refresh=True is the background sync: it never waits for another run, and auto and keep follow it unless
    given. Foreground callers wait for it."""
    parts = apply_parts(bk, refresh=refresh, auto=refresh if auto is None else auto,
                        keep=refresh if keep is None else keep, say=say, skip_unchanged=skip_unchanged,
                        command=command, on_wait=on_wait, changed=changed, plugins=plugins, skips=skips, only=only)
    return [line for key in PARTS for line in parts[key]]


def _hooks_fix(lines: list[str]) -> str:
    """The fix per line of codex_hooks.apply(dry_run=True), naming the real files (CODEX_HOME honoured)."""
    from . import codex_hooks
    fixes = []
    for line in lines:
        fix = (f"add the listed entries to [hooks] in {_tilde(paths.codex_home() / 'config.toml')}"
               if codex_hooks.INLINE_MISSING in line
               else f"remove loadout's old serena-hooks entries from {_tilde(codex_hooks.path())} by hand"
               if codex_hooks.OLD_LEFT in line
               else f"add the listed entries to {_tilde(codex_hooks.path())} by hand"
               if codex_hooks.FORMAT_MISSING in line else "loadout bootstrap")
        if fix not in fixes:
            fixes.append(fix)
    return "; ".join(fixes)


def checks() -> list:
    from .check import CheckResult
    if not enabled():
        return []
    problem = unavailable()
    if problem:
        return [CheckResult("Codex", False, problem, unavailable_fix(problem), "warn")]
    results = [CheckResult("Codex", True)]
    if mode() == "extension":  # one row for the CLI: optional next to the extension, or unusable and passed over
        broken = cli_problem()
        results.append(CheckResult("Codex CLI", True, CLI_OPTIONAL) if broken is None and not runner.have("codex")
                       else CheckResult("Codex CLI", False, CLI_UNUSABLE.format(why=broken), unavailable_fix(broken),
                                        "warn"))
    cli = mode() != "extension"  # the wording: the CLI's /hooks and logins, or the extension's
    installed = installed_plugins()
    ok = installed is not None and "loadout@agent-loadout" in installed
    if installed is None and no_plugin_command():  # bootstrap cannot install plugins with this codex
        results.append(CheckResult("Codex plugin", False, PLUGINS_OLD.split(": ", 2)[2],
                                   "update the extension in VS Code, then run loadout update", "warn"))
    else:
        results.append(CheckResult("Codex plugin", ok, "" if ok else "loadout plugin not installed in Codex",
                                   "loadout bootstrap"))
    lacks = missing_routes(installed) if installed is not None else ([], [])
    if lacks[0] or lacks[1]:
        results.append(CheckResult("Codex plugins missing", False, _missing_text(lacks), MISSING_FIX, "warn"))
    config = _tilde(paths.codex_home() / "config.toml")
    results += [CheckResult(f"Codex MCP {name}", False,
                            "defined in config.toml and by the loadout plugin; Codex starts one of them",
                            f"remove your [mcp_servers.{toml_key(name)}] from {config} (the plugin provides it), "
                            "or turn the loadout plugin off in Codex", "warn")
                for name in servers_twice(installed)]
    results += [CheckResult(f"Codex MCP {name}", False,
                            "runs codebase-memory-mcp next to the loadout plugin's; Codex starts two",
                            f"remove your [mcp_servers.{toml_key(name)}] from {config} (the plugin provides it), "
                            "or turn the loadout plugin off in Codex", "warn")
                for name in cbm_twice(installed)]
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
    results.append(CheckResult("Codex Serena hooks", not pending_hooks, "; ".join(pending_hooks),
                               _hooks_fix(pending_hooks), "warn"))
    from .settings_merge import desired_settings
    missing = plugin_routes(desired_settings())[1]
    if missing:
        results.append(CheckResult("Codex plugins", False, "no Codex route for " + ", ".join(missing), "", "warn"))
    status = hooks_status()
    if status in ("untrusted", "changed"):
        results.append(CheckResult("Codex hooks", False, "loadout's hooks are not approved yet" if status == "untrusted"
                                   else "loadout's hooks changed since you approved them",
                                   "start codex, then run /hooks and approve them" if cli
                                   else HOOKS_EXTENSION if status == "untrusted" else HOOKS_EXTENSION_CHANGED, "warn"))
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


def _plugin_hooks_on(data: dict) -> bool:
    """Whether the loadout plugin's hooks can run, so they need an approval: config.toml switches the plugin on
    (`codex plugin add` writes [plugins."loadout@agent-loadout"] enabled = true, the CLI's and VS Code's Codex
    extension's alike; ADR 0038). Read from the file only: no codex runs."""
    entry = get_dict(get_dict(data, "plugins"), "loadout@agent-loadout")
    return entry.get("enabled") is True


def loadout_copy() -> Path | None:
    """The installed Codex copy of loadout@agent-loadout in Codex's plugin cache: `local` (a marketplace cloned from a
    repo installs as "local"), else the newest version folder; None when there is none."""
    folder = paths.codex_home() / "plugins" / "cache" / "agent-loadout" / "loadout"
    try:  # an unreadable cache (EACCES) is no copy: remind then stays in hooks.json
        if (folder / "local").is_dir():
            return folder / "local"
        dirs = [d for d in folder.iterdir() if d.is_dir()] if folder.is_dir() else []
        return max(dirs, key=lambda d: d.stat().st_mtime) if dirs else None
    except OSError:
        return None


def _active_copy() -> Path | None:
    """The Codex copy of loadout@agent-loadout that Codex loads: `local` (a marketplace cloned from a repo installs
    as "local"), else the folder named by the version `codex plugin list` reports (read-only). Old version folders
    stay cached, so neither the newest nor all of them decide. None when it cannot be told."""
    folder = paths.codex_home() / "plugins" / "cache" / "agent-loadout" / "loadout"
    try:
        if (folder / "local").is_dir():
            return folder / "local"
        if not folder.is_dir():
            return None
        listed = installed_plugins()
        version = listed.versions.get("loadout@agent-loadout") if listed is not None else None
        if not isinstance(version, str) or not version or "/" in version or "\\" in version or version in (".", ".."):
            return None
        return folder / version if (folder / version).is_dir() else None
    except OSError:
        return None


def _runs_guarded_remind(copy: Path) -> bool:
    """The copy's hooks/codex.json has a PreToolUse hook running mcp_guard.py with `serena-hooks remind`."""
    try:
        groups = get_list(get_dict(load_json(copy / "hooks" / "codex.json"), "hooks"), "PreToolUse")
    except (InvalidJSON, OSError, AttributeError):
        return False
    for group in groups:
        hooks = group.get("hooks") if isinstance(group, dict) else None
        for hook in hooks if isinstance(hooks, list) else []:
            command = hook.get("command") if isinstance(hook, dict) else None
            if isinstance(command, str) and "mcp_guard.py" in command and "serena-hooks remind" in command:
                return True
    return False


def plugin_runs_remind() -> bool:
    """Whether Codex runs Serena's remind from loadout's plugin (guarded, so it skips harmless searches): the installed
    copy Codex loads (`_active_copy`) has a PreToolUse hook in hooks/codex.json running mcp_guard.py with
    `serena-hooks remind`, and config.toml
    switches the plugin on. An old copy, a missing entry or `enabled = false` is False, so remind stays in hooks.json
    (a wrong yes would leave Codex without a reminder). Only a versioned copy asks `codex plugin list` (read-only);
    the CLI and VS Code's extension share the plugin cache (ADR 0038)."""
    copy = _active_copy()
    if copy is None or not _runs_guarded_remind(copy):
        return False
    path = paths.codex_home() / "config.toml"
    try:
        data = _tomllib().loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        return False
    return _plugin_hooks_on(data)


def hooks_status(remember: bool = False) -> str | None:
    """"trusted", "untrusted" (never approved) or "changed" (the hooks changed since the user approved them);
    None when config.toml cannot be read. Codex's own hash cannot be recomputed stably, so a change is detected as:
    the hooks file differs from the last approved one while the stored approvals did not change."""
    tl = _tomllib()
    path = paths.codex_home() / "config.toml"
    try:
        data = tl.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        state = get_dict(get_dict(data, "hooks"), "state")
    except Exception:
        return None
    from . import codex_hooks
    serena = codex_hooks.serena_items()  # the Serena hooks in hooks.json need /hooks too, loadout's or the user's
    in_file = f"{codex_hooks.path()}:"  # every hooks.json key, so a Serena hook moved onto one is caught
    current = {k: v.get("trusted_hash") for k, v in state.items()
               if (k.startswith(HOOK_PLUGIN + ":") or k.startswith(in_file)) and isinstance(v, dict)
               and v.get("trusted_hash")}
    plugin_on = _plugin_hooks_on(data)
    if not (set(serena) | (hook_keys() if plugin_on else set())) <= set(current):
        return "untrusted"
    digest, seen = _hooks_digest(), load_json(_hooks_record())
    plugin_now = {k: v for k, v in current.items() if k.startswith(HOOK_PLUGIN + ":")}
    plugin_seen = {k: v for k, v in get_dict(seen, "hashes").items() if k.startswith(HOOK_PLUGIN + ":")}
    if plugin_on and seen.get("digest") not in (None, digest) and plugin_seen == plugin_now:  # off: they cannot run
        return "changed"
    # a Serena key whose content changed (edited, or another hook moved onto it) is approved again only when Codex
    # stored a new hash for it; the old hash belongs to what was there before
    seen_items, seen_hashes = get_dict(seen, "serena"), get_dict(seen, "hashes")
    if any(k in seen_hashes and seen_items.get(k) != content and seen_hashes[k] == current.get(k)
           for k, content in serena.items()):
        return "changed"
    # while the plugin is off its hooks cannot run: keep the digest last approved, so a change made meanwhile is
    # still asked about once it is on again
    kept = digest if plugin_on or seen.get("digest") is None else seen.get("digest")
    record = {"digest": kept, "hashes": current, "serena": serena}
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
    if not has_codex():
        return []
    cli = mode() != "extension"  # the wording: the CLI's /hooks, or VS Code's Codex extension's hooks icon
    status = hooks_status(remember=True)
    # unknown (unreadable config): remind, since the approval cannot be confirmed
    todo = HOOKS_TODO if cli else HOOKS_EXTENSION
    changed = HOOKS_CHANGED if cli else HOOKS_EXTENSION_CHANGED
    steps = [changed] if status == "changed" else [] if status == "trusted" else [todo]
    lacks = missing_routes()
    if lacks[0] or lacks[1]:
        steps.append(f"{_missing_text(lacks)}: run {MISSING_FIX}")
    if not cli:
        return (steps + [f"log in to {name} once: {LOGIN_EXTENSION}" for name in logins_needed()]
                + [f"optional: log in to {name} for higher limits: {LOGIN_EXTENSION}" for name in logins_optional()])
    return (steps + [f"log in to {name} in Codex once: codex mcp login {name}" for name in logins_needed()]
            + [f"optional: log in to {name} in Codex for higher limits: codex mcp login {name}" for name in logins_optional()])
