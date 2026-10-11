"""WSL detection and the setup problems loadout can see from inside WSL (docs/how-to/wsl.md)."""
from __future__ import annotations

import sys
from pathlib import Path

from . import paths, runner

OSRELEASE = Path("/proc/sys/kernel/osrelease")
LINUX_TOOLS = ("claude", "node", "npm", "uv", "git")
SANDBOX = (("bwrap", "bubblewrap"), ("socat", "socat"))


def detect(osrelease: Path | None = None, platform: str | None = None) -> int | None:
    """2 for WSL 2, 1 for WSL 1, None outside WSL."""
    osrelease = osrelease or OSRELEASE
    if not (platform or sys.platform).startswith("linux"):
        return None
    try:
        text = osrelease.read_text(encoding="utf-8", errors="replace").lower()
    except OSError:
        return None
    if "microsoft" not in text:
        return None
    return 2 if "wsl2" in text else 1


def current_dir() -> Path | None:
    """The working directory, or None when it was deleted under the shell."""
    try:
        return Path.cwd()
    except OSError:
        return None


def _real(path: Path) -> Path:
    try:
        return Path(path).resolve()  # a link into /mnt/c is on the Windows drive too
    except (OSError, RuntimeError):
        return Path(path)


def _on_windows_drive(path: Path, mount: str) -> bool:
    s = _real(path).as_posix()
    if not s.startswith(mount):
        return False
    first = s[len(mount):].split("/", 1)[0]
    return len(first) == 1 and first.isalpha()


def problems(version: int, cwd: Path | None, mount: str = "/mnt/") -> list[tuple[str, str]]:
    out = []
    if version == 1:
        out.append(("WSL 1: Claude Code's sandbox needs WSL 2, and its native binary can fail with `Exec format error`",
                    "in PowerShell: `wsl --set-version <distro> 2`"))
    roots = (("the kit", paths.kit_root()), ("the personal layer", paths.personal_root()))
    for label, path in roots:
        if _on_windows_drive(path, mount):
            out.append((f"{label} ({Path(path).as_posix()}) is on the Windows filesystem (slow, search can be incomplete)",
                        "move it into the Linux home, e.g. `~/code/...`, then re-run ./bootstrap.sh there "
                        "(the installed links point into it)"))
    if cwd is not None and _on_windows_drive(cwd, mount) and _real(cwd) not in {_real(p) for _, p in roots}:
        out.append((f"the current folder ({Path(cwd).as_posix()}) is on the Windows filesystem (slow, search can be incomplete)",
                    "move it into the Linux home, e.g. `~/code/...`"))
    for tool in LINUX_TOOLS:
        found = runner.which(tool)
        if found and _on_windows_drive(Path(found), mount):
            out.append((f"{tool} resolves to the Windows program {found}",
                        "install it inside WSL and put its directory first in PATH, "
                        "or set `appendWindowsPath = false` in `/etc/wsl.conf`"))
    if version == 2:
        missing = [pkg for binary, pkg in SANDBOX if not runner.have(binary)]
        if missing:
            out.append((f"sandbox packages missing: {', '.join(missing)} (needed for Claude Code's sandbox)",
                        f"`sudo apt-get install {' '.join(missing)}`"))
    return out


def report_lines(version: int, cwd: Path | None) -> list[str]:
    lines = [f"WSL {version} detected"]
    for problem, fix in problems(version, cwd):
        lines += [problem, f"  fix: {fix}"]
    return lines
