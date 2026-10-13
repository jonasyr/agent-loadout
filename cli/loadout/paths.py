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


def codex_home() -> Path:
    """Codex's configuration folder: $CODEX_HOME, else ~/.codex."""
    env = os.environ.get("CODEX_HOME")
    return Path(env) if env else home() / ".codex"


def agents_skills() -> Path:
    """User skills read by Codex (and other agents following the Agent Skills layout)."""
    return home() / ".agents" / "skills"


def state_dir() -> Path:
    """loadout's own state: $XDG_STATE_HOME/loadout, else ~/.local/state/loadout (ADR 0025).
    A relative or empty XDG_STATE_HOME is ignored, as the XDG spec requires."""
    base = os.environ.get("XDG_STATE_HOME", "")
    root = Path(base).expanduser() if base and Path(base).expanduser().is_absolute() else home() / ".local" / "state"
    return root / "loadout"


def backups_root() -> Path:
    return state_dir() / "backups"


def legacy_state_dir() -> Path:
    """Where state lived before ADR 0025; read only by the migration and by restore's path mapping."""
    return claude_home() / ".loadout"


def legacy_backups_root() -> Path:
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


def tool_dirs() -> list[Path]:
    """Where user-space installers put commands (uv, Claude Code, mise shims, npm globals, winget portable installs, codebase-memory-mcp on Windows), existing ones only."""
    base = home()
    if platform_key() == "windows":
        local = Path(os.environ.get("LOCALAPPDATA") or base / "AppData" / "Local")
        roaming = Path(os.environ.get("APPDATA") or base / "AppData" / "Roaming")
        dirs = [base / ".local" / "bin", local / "mise" / "shims", local / "Microsoft" / "WinGet" / "Links",
                roaming / "npm",  # npm's global prefix in Node.js for Windows
                local / "Programs" / "codebase-memory-mcp"]
    else:
        dirs = [base / ".local" / "bin", base / ".local" / "share" / "mise" / "shims"]
    return [d for d in dirs if d.is_dir()]


def inside(path: Path, root: Path) -> bool:
    """True if `path` really lives under `root`, following symlinks (a dangling one resolves to its target)."""
    try:
        Path(os.path.realpath(path)).relative_to(os.path.realpath(root))
        return True
    except ValueError:
        return False
