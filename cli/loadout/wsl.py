"""WSL detection and the setup problems loadout can see from inside WSL (docs/how-to/wsl.md)."""
from __future__ import annotations

import sys
from pathlib import Path

from . import paths, runner

OSRELEASE = Path("/proc/sys/kernel/osrelease")
LINUX_TOOLS = ("claude", "node", "npm", "uv", "git")
SANDBOX = (("bwrap", "bubblewrap"), ("socat", "socat"))


def detect(osrelease: Path = OSRELEASE, platform: str | None = None) -> int | None:
    """2 for WSL 2, 1 for WSL 1, None outside WSL."""
    if not (platform or sys.platform).startswith("linux"):
        return None
    try:
        text = osrelease.read_text(encoding="utf-8", errors="replace").lower()
    except OSError:
        return None
    if "microsoft" not in text:
        return None
    return 2 if "wsl2" in text else 1


def _on_windows_drive(path: Path, mount: str) -> bool:
    s = Path(path).as_posix()
    if not s.startswith(mount):
        return False
    first = s[len(mount):].split("/", 1)[0]
    return len(first) == 1 and first.isalpha()


def problems(version: int, cwd: Path, mount: str = "/mnt/") -> list[tuple[str, str]]:
    out = []
    if version == 1:
        out.append(("WSL 1: Claude Code's sandbox needs WSL 2, and its native binary can fail with `Exec format error`",
                    "in PowerShell: `wsl --set-version <distro> 2`"))
    for label, path in (("the kit", paths.kit_root()), ("the personal layer", paths.personal_root()),
                        ("the current folder", cwd)):
        if _on_windows_drive(path, mount):
            out.append((f"{label} ({Path(path).as_posix()}) is on the Windows filesystem (slow, search can be incomplete)",
                        "move it into the Linux home, e.g. `~/code/...`"))
    for tool in LINUX_TOOLS:
        found = runner.which(tool)
        if found and Path(found).as_posix().startswith(mount):
            out.append((f"{tool} resolves to the Windows program {found}",
                        "install it inside WSL and put its directory first in PATH, "
                        "or set `appendWindowsPath = false` in `/etc/wsl.conf`"))
    if version == 2:
        missing = [pkg for binary, pkg in SANDBOX if not runner.have(binary)]
        if missing:
            out.append((f"sandbox packages missing: {', '.join(missing)}",
                        f"`sudo apt-get install {' '.join(missing)}`"))
    return out


def report_lines(version: int, cwd: Path) -> list[str]:
    lines = [f"WSL {version} detected"]
    for problem, fix in problems(version, cwd):
        lines += [problem, f"  fix: {fix}"]
    return lines
