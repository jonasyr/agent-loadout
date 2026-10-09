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


def run(cmd: list[str], cwd: str | None = None, timeout: float = 300, env: dict | None = None) -> Result:
    exe = shutil.which(cmd[0])
    if exe is None:
        return Result(127, "", f"{cmd[0]}: not found")
    if _is_windows() and exe.lower().endswith((".cmd", ".bat")) and any(set(a) & CMD_METACHARS for a in cmd[1:]):
        from .secrets import redact
        return Result(126, "", "refusing to pass special characters through cmd.exe; run manually: "
                      + redact(" ".join(cmd)))
    try:
        proc = subprocess.run([exe, *cmd[1:]], cwd=cwd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return Result(124, "", f"{cmd[0]}: timed out after {timeout}s")
    return Result(proc.returncode, proc.stdout or "", proc.stderr or "")
