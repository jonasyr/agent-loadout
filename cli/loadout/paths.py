"""Filesystem locations. Everything derives from HOME at call time so tests can redirect it."""
from __future__ import annotations

import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent


def kit_root() -> Path:
    env = os.environ.get("LOADOUT_ROOT")
    return Path(env).expanduser().resolve() if env else PACKAGE_DIR.parent.parent


def home() -> Path:
    return Path(os.environ.get("HOME") or os.environ.get("USERPROFILE") or Path.home())


def claude_home() -> Path:
    return home() / ".claude"


def claude_json() -> Path:
    return home() / ".claude.json"


def state_dir() -> Path:
    return claude_home() / ".loadout"


def backups_root() -> Path:
    return claude_home() / "backups"


def personal_root() -> Path:
    env = os.environ.get("LOADOUT_PERSONAL")
    return Path(env).expanduser() if env else home() / ".config" / "loadout" / "personal"


def secrets_file() -> Path:
    return home() / ".config" / "loadout" / "secrets.env"


def bin_dir() -> Path:
    return home() / ".local" / "bin"


def platform_key() -> str:
    return "windows" if os.name == "nt" else "posix"
