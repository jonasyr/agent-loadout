"""The single place where loadout runs external commands (tests replace run/have)."""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass

# cmd.exe interprets these even inside quotes when a .cmd/.bat shim receives them ("BatBadBut")
CMD_METACHARS = set('&|<>^%!"')


@dataclass
class Result:
    returncode: int
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def have(binary: str) -> bool:
    return shutil.which(binary) is not None


def _is_windows() -> bool:
    return os.name == "nt"


def would_refuse(cmd: list[str]) -> bool:
    """True when run() would refuse cmd: a Windows .cmd/.bat shim cannot take cmd.exe metacharacters."""
    exe = shutil.which(cmd[0])
    return bool(exe and _is_windows() and exe.lower().endswith((".cmd", ".bat"))
                and any(set(a) & CMD_METACHARS for a in cmd[1:]))


def shell_line(cmd: list[str]) -> str:
    """One command as a POSIX sh line to paste by hand (full text, nothing redacted)."""
    import shlex
    return shlex.join(cmd)


def powershell_line(cmd: list[str]) -> str:
    """PowerShell: `--%` (stop-parsing) passes the rest verbatim, with CreateProcess quoting."""
    return f"{cmd[0]} --% {subprocess.list2cmdline(cmd[1:])}" if len(cmd) > 1 else cmd[0]


def manual_block(title: str, cmds: list[list[str]]) -> tuple[str, str]:
    """(title line, body) of a paste-ready block with labelled POSIX sh and PowerShell forms."""
    body = ("# POSIX sh (bash, zsh, Git Bash):\n" + "".join(shell_line(c) + "\n" for c in cmds)
            + "# PowerShell:\n" + "".join(powershell_line(c) + "\n" for c in cmds))
    return f"# {title}\n", body


def write_manual_commands(directory, title: str, cmds: list[list[str]]) -> str:
    """Append the exact commands to <directory>/manual-commands.txt (0600), once. Returns the file path."""
    from pathlib import Path
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    path = d / "manual-commands.txt"
    head, body = manual_block(title, cmds)
    existing = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    if head + body not in existing:  # identical block already there: do not repeat it
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(head + body + "\n")
    if os.name != "nt":
        os.chmod(path, 0o600)
    return str(path)


def run(cmd: list[str], cwd: str | None = None, timeout: float = 300, env: dict | None = None) -> Result:
    exe = shutil.which(cmd[0])
    if exe is None:
        return Result(127, "", f"{cmd[0]}: not found")
    if would_refuse(cmd):
        from .secrets import redact
        return Result(126, "", "refusing to pass special characters through cmd.exe; run manually: "
                      + redact(" ".join(cmd)))
    try:
        proc = subprocess.run([exe, *cmd[1:]], cwd=cwd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return Result(124, "", f"{cmd[0]}: timed out after {timeout}s")
    return Result(proc.returncode, proc.stdout or "", proc.stderr or "")
