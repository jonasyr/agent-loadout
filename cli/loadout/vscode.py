"""VS Code and the agents' extensions, read-only: where VS Code is, which agent extensions it has, their bundled
binaries, the settings that matter, the home each window reads (docs/superpowers/specs/2026-10-17-vscode-extensions-design.md)."""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from . import paths, runner, wsl

EXT_ID = {"claude": "anthropic.claude-code", "codex": "openai.chatgpt"}
LABEL = {"claude": "Claude Code", "codex": "Codex"}
WHERE = {"local": "", "windows": "Windows window", "remote-wsl": "Remote-WSL window"}
CODEX_MIN = (0, 161)
_FOLDER_VERSION = re.compile(r"(\d+(?:\.\d+)+)")
_VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)")
_TRAILING_COMMA = re.compile(r",(\s*[}\]])")


@dataclass(frozen=True)
class Install:
    where: str  # "local", "windows" (VS Code on Windows, seen from WSL) or "remote-wsl" (its server in WSL)
    user_dir: Path | None  # <...>/Code/User: settings.json and profiles/; None for the Remote-WSL server
    extensions: Path


@dataclass(frozen=True)
class Extension:
    agent: str  # "claude" or "codex"
    install: Install
    folder: Path
    version: str
    binary: Path | None  # the bundled agent binary; None when this build has none


def _user_dir(home: Path, platform: str) -> Path:
    if platform == "win32":
        return Path(os.environ.get("APPDATA") or home / "AppData" / "Roaming") / "Code" / "User"
    if platform == "darwin":
        return home / "Library" / "Application Support" / "Code" / "User"
    return Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config") / "Code" / "User"


def _is_dir(path: Path) -> bool:
    return os.path.isdir(path)  # never raises: a reparse point or an unreadable folder on /mnt/c is just "no"


def _is_file(path: Path) -> bool:
    return os.path.isfile(path)


def _exists(install: Install) -> bool:
    return _is_dir(install.extensions) or (install.user_dir is not None and _is_dir(install.user_dir))


def installs(platform: str | None = None, win_home: Path | None = None, look: bool = True) -> list[Install]:
    """VS Code installs this loadout can see: the local one; in WSL also VS Code on Windows (win_home, else found
    through wsl.windows_home unless look is False: a caller that already looked) and its Remote-WSL server."""
    platform = platform or sys.platform
    home = paths.home()
    ext_env = os.environ.get("VSCODE_EXTENSIONS")
    found = [Install("local", _user_dir(home, platform), Path(ext_env) if ext_env else home / ".vscode" / "extensions")]
    if wsl.detect() is not None:
        win = win_home or (wsl.windows_home() if look else None)
        if win is not None:
            found.append(Install("windows", wsl.vscode_settings(win).parent, win / ".vscode" / "extensions"))
        found.append(Install("remote-wsl", None, home / ".vscode-server" / "extensions"))
    return [i for i in found if _exists(i)]


def newest(folder: Path, ext_id: str) -> tuple[Path, str] | None:
    """The extension's newest version folder (by number: 2.1.10 after 2.1.9) and its version."""
    try:
        entries = list(folder.iterdir())
    except OSError:
        return None
    best = None
    for entry in entries:
        name = entry.name.lower()
        if not name.startswith(ext_id + "-"):
            continue
        m = _FOLDER_VERSION.match(name[len(ext_id) + 1:])
        if not m or not _is_dir(entry):
            continue
        key = tuple(int(x) for x in m.group(1).split("."))
        if best is None or key > best[0]:
            best = (key, entry, m.group(1))
    return None if best is None else (best[1], best[2])


def _os_of(where: str, platform: str) -> str:
    """The OS an install's agent binary runs on: VS Code on Windows seen from WSL runs Windows programs, the
    Remote-WSL server Linux ones, a local install the host's."""
    if where == "windows":
        return "windows"
    if where == "remote-wsl":
        return "linux"
    return {"win32": "windows", "darwin": "darwin"}.get(platform, "linux")


_OS_NAMES = {"windows": ("windows", "win32"), "darwin": ("darwin", "macos", "mac"), "linux": ("linux",)}


def _binary(agent: str, folder: Path, os_name: str = "linux") -> Path | None:
    """The bundled agent binary for os_name; a Codex build can hold one folder per OS under bin/."""
    if agent == "claude":
        candidates = [folder / "resources" / "native-binary" / n for n in ("claude", "claude.exe")]
    else:
        try:
            dirs = sorted((folder / "bin").iterdir())
        except OSError:
            dirs = []
        own = [d for d in dirs if d.name.lower().startswith(_OS_NAMES[os_name])]
        exe = ("codex.exe", "codex") if os_name == "windows" else ("codex", "codex.exe")
        candidates = [d / n for d in own + [d for d in dirs if d not in own] for n in exe]
    return next((p for p in candidates if _is_file(p)), None)


def extensions(on: dict[str, bool], platform: str | None = None, win_home: Path | None = None,
               look: bool = True) -> list[Extension]:
    """The agent extensions of the agents that are on, one per install that has it."""
    if not any(on.values()):
        return []  # nothing of an agent that is off is read, and no Windows lookup for nothing
    platform = platform or sys.platform
    out = []
    for install in installs(platform, win_home, look):
        for agent, ext_id in EXT_ID.items():
            if not on.get(agent):
                continue  # an agent that is off: nothing of it is read
            hit = newest(install.extensions, ext_id)
            if hit is not None:
                out.append(Extension(agent, install, hit[0], hit[1],
                                     _binary(agent, hit[0], _os_of(install.where, platform))))
    return out


def bundled_version(ext: Extension) -> str | None:
    """The version of the agent the extension runs: Claude Code's is the extension's own; Codex's is asked."""
    if ext.agent == "claude":
        return ext.version
    if ext.binary is None:
        return None
    res = runner.run([str(ext.binary), "--version"], timeout=15)
    m = _VERSION.search(res.stdout) if res.ok else None
    return m.group(0) if m else None


def too_old(version: str) -> bool:
    m = _VERSION.match(version)
    return m is not None and (int(m.group(1)), int(m.group(2))) < CODEX_MIN


def read_jsonc(path: Path) -> dict | None:
    """A VS Code settings file (JSONC: comments, trailing commas, a BOM) as a dict; None when it cannot be read."""
    try:
        text = path.read_bytes().decode("utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return None
    masked = wsl._mask_comments(text)
    pieces, last = [], 0
    for m in re.finditer(r'"(?:[^"\\]|\\.)*"', masked):  # trailing commas outside strings only
        pieces.append(_TRAILING_COMMA.sub(r"\1", masked[last:m.start()]))
        pieces.append(m.group(0))
        last = m.end()
    pieces.append(_TRAILING_COMMA.sub(r"\1", masked[last:]))
    try:
        data = json.loads("".join(pieces))
    except (ValueError, RecursionError):  # RecursionError: a pathologically nested file
        return None
    return data if isinstance(data, dict) else None


def settings_files(install: Install) -> list[Path]:
    """The user settings file of an install (the Remote-WSL server's machine settings for its server)."""
    if install.user_dir is None:
        return [install.extensions.parent / "data" / "Machine" / "settings.json"]
    return [install.user_dir / "settings.json"]


def setting(install: Install, key: str) -> object | None:
    for path in settings_files(install):
        data = read_jsonc(path)
        if data is not None and key in data:
            return data[key]
    return None


def row_name(ext: Extension) -> str:
    where = WHERE[ext.install.where]
    return f"VS Code ({LABEL[ext.agent]}{', ' + where if where else ''})"


SYSTEM_DIRS = ("/usr/local/sbin", "/usr/local/bin", "/usr/sbin", "/usr/bin", "/sbin", "/bin")
SERVER_ENV = ".vscode-server/server-env-setup"  # VS Code's place for a Remote-WSL server's environment
_PATH_LINE = re.compile(r"^\s*(?:export\s+)?PATH=(.+)$", re.M)


def reads_home(ext: Extension) -> Path:
    """The agent folder the extension's agent reads. A Windows window seen from WSL reads the Windows homes, except
    Codex with its WSL switch on, which runs the Codex in WSL and reads the WSL home."""
    if ext.install.where == "windows":
        win = ext.install.extensions.parent.parent  # <Windows home>/.vscode/extensions
        if ext.agent == "codex" and wsl.vscode_wsl_mode(win) is True:
            return paths.codex_home()
        return win / (".claude" if ext.agent == "claude" else ".codex")
    return paths.claude_home() if ext.agent == "claude" else paths.codex_home()


def remote_path_dirs() -> list[str]:
    """The folders a Remote-WSL window's agent finds commands in: the system folders, plus what
    ~/.vscode-server/server-env-setup puts on PATH (no shell startup file runs there)."""
    dirs = list(SYSTEM_DIRS)
    try:
        text = (paths.home() / SERVER_ENV).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return dirs
    home = str(paths.home())
    for m in _PATH_LINE.finditer(text):
        for part in m.group(1).strip().strip("\"'").split(":"):
            part = part.replace("${HOME}", home).replace("$HOME", home)
            part = home + part[1:] if part.startswith("~/") else part
            if part and "$" not in part:
                dirs.append(part)
    return dirs


def findable(command: str, dirs: list[str]) -> bool:
    if os.path.isabs(command):
        return _is_file(Path(command))
    return any(_is_file(Path(d) / command) for d in dirs)


def _commands(servers) -> dict[str, str]:
    if not isinstance(servers, dict):
        return {}
    return {name: s["command"] for name, s in servers.items()
            if isinstance(s, dict) and isinstance(s.get("command"), str) and s["command"]
            and s.get("enabled") is not False}  # a switched-off Codex server starts nothing


def mcp_commands(agent: str) -> dict[str, str]:
    """The commands of the MCP servers an extension starts: Codex's [mcp_servers.*] in config.toml (the extension
    loads no plugins); Claude Code's user servers in ~/.claude.json plus the loadout plugin's."""
    if agent == "codex":
        from . import codex
        try:
            data = codex._tomllib().loads((paths.codex_home() / "config.toml").read_text(encoding="utf-8"))
        except Exception:  # missing, unreadable or not TOML: nothing to check
            return {}
        return _commands(data.get("mcp_servers"))
    found = {}
    plugin = paths.kit_root() / "plugins" / "loadout" / ".mcp.json"
    for path in (plugin, paths.claude_json()):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            found.update(_commands(data.get("mcpServers")))
    return found
