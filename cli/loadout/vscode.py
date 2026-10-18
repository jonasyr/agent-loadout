"""VS Code and the agents' extensions, read-only: where VS Code is, which agent extensions it has, their bundled
binaries, the settings that matter, the home each window reads (docs/superpowers/specs/2026-10-17-vscode-extensions-design.md)."""
from __future__ import annotations

import json
import os
import platform as _platform
import re
import shlex
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
    os_name: str = "linux"  # the OS that binary runs on: "linux", "darwin" or "windows"


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
    try:  # folders VS Code removed or replaced but has not deleted yet
        obsolete = json.loads((folder / ".obsolete").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        obsolete = {}
    gone = {k.lower() for k, v in obsolete.items() if v} if isinstance(obsolete, dict) else set()
    best = None
    for entry in entries:
        name = entry.name.lower()
        if not name.startswith(ext_id + "-") or name in gone:
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
_ARCH_NAMES = {"x86_64": ("x86_64", "x64", "amd64"), "aarch64": ("aarch64", "arm64")}


def _arch(machine: str | None = None) -> str:
    m = (machine or _platform.machine()).lower()
    return next((a for a, names in _ARCH_NAMES.items() if m in names), m)


def _binary(agent: str, folder: Path, os_name: str = "linux", machine: str | None = None) -> Path | None:
    """The bundled agent binary for os_name and this machine's architecture; a Codex build can hold one folder
    per OS and architecture under bin/."""
    if agent == "claude":
        name = "claude.exe" if os_name == "windows" else "claude"  # another OS's binary starts nothing here
        candidates = [folder / "resources" / "native-binary" / name]
    else:
        try:
            dirs = sorted((folder / "bin").iterdir())
        except OSError:
            dirs = []
        known = tuple(n for names in _OS_NAMES.values() for n in names)
        own = [d for d in dirs if d.name.lower().startswith(_OS_NAMES[os_name])]
        if not own and not any(d.name.lower().startswith(known) for d in dirs):
            own = dirs  # a layout without OS names: take what is there
        tagged = [d for d in own if any(n in d.name.lower() for names in _ARCH_NAMES.values() for n in names)]
        if tagged:  # folders that name an architecture: only this machine's counts
            own = [d for d in tagged if any(n in d.name.lower() for n in _ARCH_NAMES.get(_arch(machine), (_arch(machine),)))]
        exe = ("codex.exe", "codex") if os_name == "windows" else ("codex", "codex.exe")
        candidates = [d / n for d in own for n in exe]  # another OS's build is no bundled Codex for this one
    usable = _is_file if os_name == "windows" else _runnable  # a POSIX binary needs execute permission
    return next((p for p in candidates if usable(p)), None)


def _wsl_switch(agent: str, install: Install) -> bool:
    """VS Code on Windows whose Codex extension runs its Linux Codex inside WSL
    (chatgpt.runCodexInWindowsSubsystemForLinux)."""
    return agent == "codex" and install.where == "windows" and \
        wsl.vscode_wsl_mode(install.extensions.parent.parent) is True


def runs_in_wsl(ext: Extension) -> bool:
    return _wsl_switch(ext.agent, ext.install)


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
                os_name = "linux" if _wsl_switch(agent, install) else _os_of(install.where, platform)
                binary = _binary(agent, hit[0], os_name)
                if agent == "codex":  # chatgpt.cliExecutable, when it names a usable file, is what the extension runs
                    binary = _wrapper_path(install, setting(install, "chatgpt.cliExecutable")) or binary
                out.append(Extension(agent, install, hit[0], hit[1], binary, os_name))
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
    try:
        profiles = sorted(install.user_dir.glob("profiles/*/settings.json"))
    except OSError:
        profiles = []
    return [install.user_dir / "settings.json", *profiles]  # which profile is active is not on disk: any may be


def windows_claude(install: Install) -> bool:
    """VS Code on Windows, seen from WSL: a claude where the Windows installers put it (the native installer's
    .local\\bin, npm's global folder). The Windows PATH itself cannot be read from WSL."""
    win = install.extensions.parent.parent
    return any(_is_file(win / p) for p in (".local/bin/claude.exe", "AppData/Roaming/npm/claude.cmd",
                                            "AppData/Roaming/npm/claude.exe"))


def broken_settings(install: Install) -> list[Path]:
    """Settings files of the install that exist but do not parse: what they set cannot be read."""
    return [p for p in settings_files(install) if _is_file(p) and read_jsonc(p) is None]


def setting(install: Install, key: str) -> object | None:
    """A setting from the user settings (the Remote-WSL server's machine settings). A profile's value is never
    taken: which profile is active is not on disk."""
    data = read_jsonc(settings_files(install)[0])
    return data.get(key) if data is not None else None


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
    """The folders a Remote-WSL window's agent finds commands in: the system folders, as changed by the PATH
    assignments in ~/.vscode-server/server-env-setup, in order (no shell startup file runs there). An assignment
    without $PATH replaces what came before."""
    dirs = list(SYSTEM_DIRS)
    try:
        text = (paths.home() / SERVER_ENV).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return dirs
    home = str(paths.home())
    for m in _PATH_LINE.finditer(text):
        try:
            words = shlex.split(m.group(1), comments=True)  # quotes and a trailing # comment, as the shell reads them
        except ValueError:
            continue  # an unbalanced quote: the shell would fail on it too
        if not words:
            continue
        new = []
        for part in words[0].split(":"):
            if part in ("$PATH", "${PATH}"):
                new += dirs
                continue
            part = part.replace("${HOME}", home).replace("$HOME", home)
            part = home + part[1:] if part.startswith("~/") else part
            if part and "$" not in part:
                new.append(part)
        dirs = new
    return dirs


def _runnable(path: Path) -> bool:
    return _is_file(path) and os.access(path, os.X_OK)


def findable(command: str, dirs: list[str]) -> bool:
    """The command starts from one of dirs (or is an absolute path): a file with execute permission."""
    if os.path.isabs(command):
        return _runnable(Path(command))
    return any(_runnable(Path(d) / command) for d in dirs)


_WIN_PATH = re.compile(r"^([A-Za-z]):[\\/](.*)$")


def _wrapper_path(install: Install, value) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    m = _WIN_PATH.match(value.strip()) if install.where == "windows" else None
    if m:  # VS Code on Windows names a Windows path; from WSL it is under the drive's mount
        path = Path(wsl.MOUNT) / m.group(1).lower() / m.group(2).replace("\\", "/")
    else:
        path = Path(value.strip()).expanduser()
    usable = _is_file if install.where == "windows" or sys.platform == "win32" else _runnable
    return path if usable(path) else None


def wrapper(install: Install) -> Path | None:
    """claudeCode.claudeProcessWrapper from the user settings when it names a file that exists. A profile's value
    does not count: which profile is active is not on disk."""
    files = settings_files(install)
    return _wrapper_path(install, (read_jsonc(files[0]) or {}).get("claudeCode.claudeProcessWrapper"))


def profile_wrapper(install: Install) -> bool:
    """A VS Code profile (not the user settings) sets a wrapper that names a file."""
    return any(_wrapper_path(install, (read_jsonc(p) or {}).get("claudeCode.claudeProcessWrapper")) is not None
               for p in settings_files(install)[1:])


def _commands(servers) -> dict[str, str]:
    if not isinstance(servers, dict):
        return {}
    return {name: s["command"] for name, s in servers.items()
            if isinstance(s, dict) and isinstance(s.get("command"), str) and s["command"]
            and s.get("enabled") is not False}  # a switched-off Codex server starts nothing


def _toml_tables(path: Path) -> dict[str, dict]:
    from . import codex
    try:
        servers = codex._tomllib().loads(path.read_text(encoding="utf-8")).get("mcp_servers")
    except Exception:  # missing, unreadable or not TOML: nothing to check
        return {}
    return {n: t for n, t in servers.items() if isinstance(t, dict)} if isinstance(servers, dict) else {}


def mcp_commands(agent: str, project: Path | None = None, plugin: bool = True) -> dict[str, str]:
    """The commands of the MCP servers an extension starts: Codex's [mcp_servers.*] in config.toml, and in a
    project its .codex/config.toml, which wins for a name it shares (the extension loads no plugins); Claude Code's
    user servers in ~/.claude.json plus the loadout plugin's."""
    if agent == "codex":
        tables = _toml_tables(paths.codex_home() / "config.toml")
        from .codex_project import _trusted
        if project is not None and _trusted(project):  # Codex reads a project's layer only once it is trusted;
            # that layer wins key by key, `enabled = false` included
            for name, table in _toml_tables(project / ".codex" / "config.toml").items():
                tables[name] = {**tables.get(name, {}), **table}
        return _commands(tables)
    found = {}
    def read(path: Path) -> dict:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}
    user = read(paths.claude_json())
    if plugin:
        found.update(_commands(read(paths.kit_root() / "plugins" / "loadout" / ".mcp.json").get("mcpServers")))
    found.update(_commands(user.get("mcpServers")))
    if project is not None:  # Claude Code's scopes: local beats project beats user
        disabled = set()
        for settings in (paths.claude_home() / "settings.json", project / ".claude" / "settings.json",
                         project / ".claude" / "settings.local.json"):
            names = read(settings).get("disabledMcpjsonServers")
            disabled |= {n for n in names if isinstance(n, str)} if isinstance(names, list) else set()
        found.update({n: c for n, c in _commands(read(project / ".mcp.json").get("mcpServers")).items()
                      if n not in disabled})  # a .mcp.json server switched off is not started
        projects = user.get("projects")
        entry = projects.get(str(project.resolve())) if isinstance(projects, dict) else None
        if isinstance(entry, dict):
            found.update(_commands(entry.get("mcpServers")))
    return found
