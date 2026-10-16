"""WSL detection and the setup problems loadout can see from inside WSL (docs/how-to/wsl.md)."""
from __future__ import annotations

import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import paths, runner

OSRELEASE = Path("/proc/sys/kernel/osrelease")
MOUNT = "/mnt/"  # where WSL mounts the Windows drives
LINUX_TOOLS = ("node", "npm", "uv", "git")
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


def _codex_on() -> bool:
    from . import targets
    try:
        return targets.codex_enabled()
    except Exception:  # a damaged targets.json: the check stays as before
        return False


WIN_SETTING = "chatgpt.runCodexInWindowsSubsystemForLinux"  # the Codex extension's choice (Windows only)
RECENT_DAYS = 30


@dataclass
class CodexSide:
    side: str  # "wsl", "windows", "both" or "none"
    reasons: list[str] = field(default_factory=list)
    windows_home: Path | None = None
    windows_used: bool = False
    shared_home: bool = False


def windows_home() -> Path | None:
    """The Windows user's home as a WSL path (/mnt/c/Users/<name>), via cmd.exe and wslpath; without interop,
    /mnt/c/Users/$USER when it exists; else None."""
    drive = Path(MOUNT) / "c"
    cwd = str(drive) if drive.is_dir() else None  # cmd.exe warns about a Linux (UNC) working folder
    res = runner.run(["cmd.exe", "/c", "echo", "%USERPROFILE%"], cwd=cwd, timeout=15)
    win = res.stdout.strip().splitlines()[-1].strip() if res.ok and res.stdout.strip() else ""
    path = None
    if win and "%" not in win:
        conv = runner.run(["wslpath", "-u", win], timeout=15)
        path = Path(conv.stdout.strip()) if conv.ok and conv.stdout.strip() else None
    if path is None and os.environ.get("USER"):
        path = drive / "Users" / os.environ["USER"]
    return path if path is not None and path.is_dir() else None


def vscode_settings(home: Path) -> Path:
    return home / "AppData" / "Roaming" / "Code" / "User" / "settings.json"


_KEY_RX = re.compile(r'"chatgpt\.runCodexInWindowsSubsystemForLinux"\s*:\s*')
_BOOL_RX = re.compile(r"(true|false)(?![\w$])")
MANUAL = (f"in VS Code on Windows: Settings, search {WIN_SETTING}, tick it (VS Code reloads); then the Codex "
          "extension runs Codex in WSL")


def _mask_comments(text: str) -> str:
    """The text with // and /* */ comments blanked (same length, so offsets still match): JSONC read by text."""
    out, i, n = list(text), 0, len(text)
    while i < n:
        c = text[i]
        if c == '"':
            i += 1
            while i < n and text[i] != '"':
                i += 2 if text[i] == "\\" else 1
            i += 1
        elif text.startswith("//", i):
            end = text.find("\n", i)
            end = n if end < 0 else end
            out[i:end] = " " * (end - i)
            i = end
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            end = n if end < 0 else end + 2
            out[i:end] = [ch if ch in "\r\n" else " " for ch in text[i:end]]
            i = end
        else:
            i += 1
    return "".join(out)


def _read_settings(home: Path) -> str | None:
    try:  # bytes, not read_text: CRLF and a BOM stay as they are
        return vscode_settings(home).read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _string_depths(masked: str) -> dict[int, int]:
    """Where each string starts in the comment-masked text, and how deep in {} and [] it is."""
    depths, depth, i, n = {}, 0, 0, len(masked)
    while i < n:
        c = masked[i]
        if c == '"':
            depths[i] = depth
            i += 1
            while i < n and masked[i] != '"':
                i += 2 if masked[i] == "\\" else 1
        elif c in "{[":
            depth += 1
        elif c in "}]":
            depth -= 1
        i += 1
    return depths


def _top_setting(masked: str) -> tuple[int, int, bool | None] | None:
    """The switch's value span and value at the top level; the last copy, as VS Code reads it. None when not set;
    a value other than true/false is (start, start, None)."""
    depths = _string_depths(masked)
    keys = [m for m in _KEY_RX.finditer(masked) if depths.get(m.start()) == 1]
    if not keys:
        return None
    start = keys[-1].end()
    v = _BOOL_RX.match(masked, start)
    return (start, start, None) if v is None else (start, v.end(), v.group(1) == "true")


def vscode_wsl_mode(home: Path) -> bool | None:
    """The extension's WSL switch from VS Code's settings.json (JSONC: read by text); None when not set."""
    text = _read_settings(home)
    found = None if text is None else _top_setting(_mask_comments(text))
    return None if found is None else found[2]


def set_vscode_wsl_mode(bk, home: Path) -> str:
    """Set the extension's WSL switch by a text edit of VS Code's settings.json (JSONC), backup first;
    every other byte stays."""
    from . import jsonio
    path = vscode_settings(home)
    text = _read_settings(home)
    if text is None:
        return f"VS Code settings not found ({path}); {MANUAL}"
    masked = _mask_comments(text)
    found = _top_setting(masked)
    if found is not None and found[2] is True:
        return "VS Code already runs Codex in WSL"
    if found is not None and found[2] is None:
        return f"VS Code settings ({path}) give {WIN_SETTING} a value other than true or false; {MANUAL}"
    if found is not None:
        new = text[:found[0]] + "true" + text[found[1]:]
    else:
        brace = masked.find("{")
        if brace < 0:
            return f"VS Code settings ({path}) are not an object; {MANUAL}"
        nl = "\r\n" if "\r\n" in text else "\n"
        empty = masked[brace + 1:].lstrip().startswith("}")
        new = text[:brace + 1] + f'{nl}  "{WIN_SETTING}": true{nl if empty else ","}' + text[brace + 1:]
    try:
        bk.save_copy(path, "VS Code settings.json before loadout switched the Codex extension to WSL")
        jsonio.write_atomic_bytes(path, new.encode("utf-8"))
    except OSError as exc:  # Windows can hold the file open; the switch is optional, the rest of setup goes on
        return f"could not change VS Code settings ({exc}); {MANUAL}"
    return f"VS Code: the Codex extension now runs Codex in WSL ({WIN_SETTING} = true; VS Code reloads)"


def _recent(folder: Path, days: int = RECENT_DAYS) -> bool:
    cutoff = time.time() - days * 86400
    try:
        return any(f.stat().st_mtime >= cutoff for f in folder.rglob("*.jsonl"))
    except OSError:
        return False


def codex_side(mount: str | None = None) -> CodexSide:
    """Which side of WSL the user's Codex runs on, from read-only signals (docs/how-to/wsl.md#codex)."""
    mount = mount or MOUNT
    found = runner.which("codex")
    linux = bool(found) and not _on_windows_drive(Path(found), mount)
    windows_bin = (bool(found) and not linux) or bool(runner.which("codex.exe"))
    home = windows_home()
    used = home is not None and _recent(home / ".codex" / "sessions")
    mode = vscode_wsl_mode(home) if home is not None else None
    codex_home = os.environ.get("CODEX_HOME", "")
    shared = bool(codex_home) and _on_windows_drive(Path(codex_home), mount)
    reasons = []
    if linux:
        reasons.append(f"Codex in WSL: {found}")
    if windows_bin:
        reasons.append(f"a Windows Codex is on PATH{f' ({found})' if found and not linux else ''}")
    if used:
        reasons.append(f"the Windows Codex home ({home / '.codex'}) has sessions from the last {RECENT_DAYS} days")
    if mode is True:
        reasons.append(f"VS Code runs Codex in WSL ({WIN_SETTING} = true)")
    elif mode is False:
        reasons.append(f"VS Code runs Codex on Windows ({WIN_SETTING} = false)")
    if shared:
        reasons.append(f"CODEX_HOME points into Windows ({codex_home})")
    wsl_side, win_side = linux or mode is True, windows_bin or used or mode is False
    side = "both" if wsl_side and win_side else "wsl" if wsl_side else "windows" if win_side else "none"
    return CodexSide(side, reasons, home, used, shared)


def _claude_on() -> bool:
    from . import targets
    try:
        return targets.claude_enabled()
    except Exception:  # a damaged targets.json: the check stays as before
        return True


def problems(version: int, cwd: Path | None, mount: str | None = None) -> list[tuple[str, str]]:
    """The setup problems seen from WSL; Claude Code's tools and sandbox only with Claude Code on."""
    mount = mount or MOUNT
    out = []
    claude = _claude_on()
    if version == 1 and claude:
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
    for tool in (("claude",) if claude else ()) + LINUX_TOOLS + (("codex",) if _codex_on() else ()):
        found = runner.which(tool)
        if found and _on_windows_drive(Path(found), mount):
            out.append((f"{tool} resolves to the Windows program {found}",
                        "install it inside WSL and put its directory first in PATH, "
                        "or set `appendWindowsPath = false` in `/etc/wsl.conf`"))
    if version == 2 and claude:
        missing = [pkg for binary, pkg in SANDBOX if not runner.have(binary)]
        if missing:
            out.append((f"sandbox packages missing: {', '.join(missing)} (needed for Claude Code's sandbox)",
                        f"`sudo apt-get install {' '.join(missing)}`"))
    return out


def repo_note(project: Path) -> str | None:
    """In WSL, for a repo on a Windows drive: the one-line note init and profile print (never a problem)."""
    if detect() is None or not _on_windows_drive(project, MOUNT):
        return None
    return ("note: this repo is on the Windows drive (slower in WSL: Serena and codebase-memory index it more slowly; "
            "links in its skill folders are WSL links that a Windows-side Codex does not follow)")


def report_lines(version: int, cwd: Path | None) -> list[str]:
    lines = [f"WSL {version} detected"]
    for problem, fix in problems(version, cwd):
        lines += [problem, f"  fix: {fix}"]
    return lines
