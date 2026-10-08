"""The single place where loadout runs external commands (tests replace run/have)."""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


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


def run(cmd: list[str], cwd: str | None = None, timeout: float = 300) -> Result:
    exe = shutil.which(cmd[0])
    if exe is None:
        return Result(127, "", f"{cmd[0]}: not found")
    try:
        proc = subprocess.run([exe, *cmd[1:]], cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return Result(124, "", f"{cmd[0]}: timed out after {timeout}s")
    return Result(proc.returncode, proc.stdout, proc.stderr)
