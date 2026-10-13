"""Codex has no LSP plugins: after an edit, run the language's checker on the changed files and tell the agent.

Codex-only (hooks/codex.json). Python: pyright on the files; TypeScript: tsc --noEmit for the nearest tsconfig;
Rust: cargo check for the nearest Cargo.toml. Each check is capped at LIMIT seconds. Silent when clean or when the
checker is missing.
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

LIMIT = 20
SKIPPED = "type check skipped (timeout after "  # a note, not a reason to stop the agent
PATCH_FILE = re.compile(r"^\*\*\* (?:Add|Update) File: (.+?)\s*$", re.M)


def changed_files(event: dict) -> list:
    tool_input = event.get("tool_input") or {}
    cwd = Path(event.get("cwd") or ".")
    names = PATCH_FILE.findall(tool_input["command"]) if isinstance(tool_input.get("command"), str) else []
    if isinstance(tool_input.get("file_path"), str):
        names.append(tool_input["file_path"])
    return [cwd / name for name in names]  # an absolute name stays absolute


def _nearest(path: Path, marker: str):
    return next((d for d in path.parents if (d / marker).exists()), None)


def _which(name: str):
    """shutil.which without the current folder (Windows searches it first); the absolute path or None."""
    if os.name == "nt":
        os.environ["NoDefaultCurrentDirectoryInExePath"] = "1"
    exe = shutil.which(name)
    try:
        if exe is None or os.path.dirname(os.path.abspath(exe)) == os.path.abspath(os.getcwd()):
            return None
    except OSError:
        return None
    return exe


def checks(files: list) -> list:
    """(command, folder) per checker that applies to the files and is installed."""
    found = []
    py = [str(f) for f in files if f.suffix in (".py", ".pyi")]
    if py and (pyright := _which("pyright")):
        found.append(([pyright, *py], Path(py[0]).parent))
    for project in dict.fromkeys(_nearest(f, "tsconfig.json") for f in files if f.suffix in (".ts", ".tsx", ".mts", ".cts")):
        if project is not None and (tsc := _which("tsc")):
            found.append(([tsc, "--noEmit", "-p", str(project)], project))
    for crate in dict.fromkeys(_nearest(f, "Cargo.toml") for f in files if f.suffix == ".rs"):
        if crate is not None and (cargo := _which("cargo")):
            found.append(([cargo, "check", "--quiet", "--message-format=short"], crate))
    return found


def _run(cmd: list, cwd: Path):
    try:
        res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=LIMIT)
    except subprocess.TimeoutExpired:
        return SKIPPED + f"{LIMIT} s): {' '.join(cmd[:2])}"
    except OSError:
        return None
    if res.returncode == 0:
        return None
    return f"$ {' '.join(cmd)}\n" + (res.stdout + res.stderr).strip()[-4000:]


def main(stdin=sys.stdin, stdout=sys.stdout) -> int:
    try:
        event = json.load(stdin)
    except (ValueError, OSError):
        return 0
    files = [f for f in changed_files(event) if f.exists()]
    reports = [r for cmd, cwd in checks(files) if (r := _run(cmd, cwd))]
    errors = [r for r in reports if not r.startswith(SKIPPED)]
    notes = [r for r in reports if r.startswith(SKIPPED)]
    if errors:
        stdout.write(json.dumps({"decision": "block",
                                 "reason": "Type check after your edit:\n\n" + "\n\n".join(errors + notes)}) + "\n")
    elif notes:
        stdout.write(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                                        "additionalContext": "\n".join(notes)}}) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
