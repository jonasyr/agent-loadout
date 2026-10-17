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


def _exists(install: Install) -> bool:
    return install.extensions.is_dir() or (install.user_dir is not None and install.user_dir.is_dir())


def installs(platform: str | None = None, win_home: Path | None = None) -> list[Install]:
    """VS Code installs this loadout can see: the local one; in WSL also VS Code on Windows (win_home, else found
    through wsl.windows_home) and its Remote-WSL server."""
    platform = platform or sys.platform
    home = paths.home()
    ext_env = os.environ.get("VSCODE_EXTENSIONS")
    found = [Install("local", _user_dir(home, platform), Path(ext_env) if ext_env else home / ".vscode" / "extensions")]
    if wsl.detect() is not None:
        win = win_home or wsl.windows_home()
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
        if not m or not entry.is_dir():
            continue
        key = tuple(int(x) for x in m.group(1).split("."))
        if best is None or key > best[0]:
            best = (key, entry, m.group(1))
    return None if best is None else (best[1], best[2])


def _binary(agent: str, folder: Path) -> Path | None:
    if agent == "claude":
        candidates = [folder / "resources" / "native-binary" / n for n in ("claude", "claude.exe")]
    else:
        try:
            candidates = [d / n for d in sorted((folder / "bin").iterdir()) for n in ("codex", "codex.exe")]
        except OSError:
            candidates = []
    return next((p for p in candidates if p.is_file()), None)


def extensions(on: dict[str, bool], platform: str | None = None, win_home: Path | None = None) -> list[Extension]:
    """The agent extensions of the agents that are on, one per install that has it."""
    out = []
    for install in installs(platform, win_home):
        for agent, ext_id in EXT_ID.items():
            if not on.get(agent):
                continue  # an agent that is off: nothing of it is read
            hit = newest(install.extensions, ext_id)
            if hit is not None:
                out.append(Extension(agent, install, hit[0], hit[1], _binary(agent, hit[0])))
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
    except ValueError:
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
