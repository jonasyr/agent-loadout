"""Link kit/personal rules into ~/.claude/rules and put loadout on PATH."""
from __future__ import annotations

import filecmp
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

from . import paths
from .backup import Backup


def LINKS() -> list[tuple[Path, Path]]:
    from .jsonio import InvalidJSON, load_json

    rules = paths.claude_home() / "rules"
    personal = paths.personal_root()
    out = [
        (rules / "loadout", paths.kit_root() / "rules"),
        (rules / "personal", personal / "rules"),
    ]
    skills = paths.claude_home() / "skills"
    if (personal / "skills").is_dir():
        out += [(skills / p.name, p) for p in sorted((personal / "skills").iterdir()) if p.is_dir()]
    try:
        pointers = load_json(personal / "skills.json")
    except InvalidJSON:
        pointers = {}  # never crash linking; loadout check reports the broken file
    for name, target in sorted(pointers.items()):
        if isinstance(target, str) and Path(target).expanduser().is_dir():
            out.append((skills / name, Path(target).expanduser()))
    out.append((paths.claude_home() / "hooks" / "personal", personal / "hooks"))
    return out


def _marker() -> Path:
    return paths.state_dir() / "copy-mode"


def is_copy_mode() -> bool:
    return _marker().exists()


def _points_to(dest: Path, src: Path) -> bool:
    return dest.is_symlink() and dest.resolve() == src.resolve()


SENTINEL = ".loadout-copy"


def _is_kit_copy(dest: Path, src: Path) -> bool:
    if src.is_dir():
        return dest.is_dir() and not dest.is_symlink() and (dest / SENTINEL).is_file()
    return dest.is_file() and not dest.is_symlink() and filecmp.cmp(dest, src, shallow=False)


def _tree_hashes(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file() and p.name != SENTINEL}


def _copy_edited(dest: Path) -> bool:
    """True when files in a kit copy differ from what loadout copied (recorded in the sentinel)."""
    try:
        recorded = json.loads((dest / SENTINEL).read_text(encoding="utf-8")).get("files")
    except (OSError, ValueError, AttributeError):
        return False  # older sentinel without hashes: refreshed as before
    return isinstance(recorded, dict) and recorded != _tree_hashes(dest)


def _replace_with_copy(src: Path, dest: Path) -> None:
    if dest.is_symlink() or dest.is_file():
        dest.unlink()
    elif dest.exists():
        shutil.rmtree(dest)
    if src.is_dir():
        shutil.copytree(src, dest)
        info = {"note": "copied by loadout; refreshed on every link run", "files": _tree_hashes(dest)}
        (dest / SENTINEL).write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    else:
        shutil.copy2(src, dest)


def _symlinks_work() -> bool:
    probe_dir = paths.state_dir()
    probe_dir.mkdir(parents=True, exist_ok=True)
    probe = probe_dir / f".symlink-probe-{os.getpid()}"
    try:
        os.symlink(probe_dir, probe, target_is_directory=True)
    except OSError:
        return False
    try:
        probe.unlink()
    except OSError:
        pass
    return True


def _link_one(dest: Path, src: Path, bk: Backup) -> str | None:
    if not src.exists() or _points_to(dest, src):
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    if is_copy_mode() and not dest.is_symlink():
        if dest.exists() and (not _is_kit_copy(dest, src) or (src.is_dir() and _copy_edited(dest))):
            bk.move(dest, f"replaced {dest}", replace=True)  # a user dir, or a kit copy edited in place
        _replace_with_copy(src, dest)
        return None  # refresh, not news
    if dest.exists() or dest.is_symlink():
        bk.move(dest, f"replaced {dest}", replace=True)
    try:
        os.symlink(src, dest, target_is_directory=src.is_dir())
        return f"linked {dest} -> {src}"
    except OSError:
        _marker().parent.mkdir(parents=True, exist_ok=True)
        _marker().write_text("symlinks unavailable; files are copied and refreshed by maintenance\n", encoding="utf-8")
        _replace_with_copy(src, dest)
        return f"copied {src} -> {dest} (symlinks unavailable)"


def link_all(bk: Backup, retry_symlinks: bool = False) -> list[str]:
    """retry_symlinks (bootstrap): leave copy mode when symlinks work again (e.g. Developer Mode on)."""
    out = []
    if retry_symlinks and is_copy_mode() and _symlinks_work():
        _marker().unlink()
        out.append("symlinks work now: replacing copied rules with links")
    return out + [a for dest, src in LINKS() if (a := _link_one(dest, src, bk))]


LAUNCHER_MARKER = "# loadout launcher"
PY_OK = "import sys; sys.exit(sys.version_info < (3, 10))"


def launcher_text(script: Path) -> str:
    s = script.as_posix().replace("'", "'\\''")
    return (f"#!/bin/sh\n{LAUNCHER_MARKER} (written by loadout bootstrap; Python 3.10+ or uv runs it)\n"
            f"script='{s}'\n"
            f'if command -v python3 >/dev/null 2>&1 && python3 -c "{PY_OK}" 2>/dev/null; then exec python3 "$script" "$@"; fi\n'
            'if command -v uv >/dev/null 2>&1; then exec uv run --no-project --no-config --python ">=3.10" "$script" "$@"; fi\n'
            'echo "loadout needs Python 3.10 or newer, or uv, on PATH" >&2\nexit 1\n')


def write_windows_shims(target_dir: Path) -> None:
    script = paths.kit_root() / "bin" / "loadout"
    target_dir.mkdir(parents=True, exist_ok=True)
    # newline="" / "\n": write exactly these bytes; text mode on Windows would turn \n into \r\n
    cmd = (f'@echo off\r\nwhere python >nul 2>nul && python -c "{PY_OK}" 2>nul && (python "{script}" %* & exit /b)\r\n'
           f'uv run --no-project --no-config --python ">=3.10" "{script}" %*\r\n')
    (target_dir / "loadout.cmd").write_text(cmd, encoding="utf-8", newline="")
    # Git Bash (used for hooks on Windows) runs extensionless scripts; a CR would break the shebang
    (target_dir / "loadout").write_text(launcher_text(script), encoding="utf-8", newline="\n")


def link_bin(bk: Backup) -> list[str]:
    target_dir = paths.bin_dir()
    if os.name == "nt":
        write_windows_shims(target_dir)
        return [f"wrote shims to {target_dir} (make sure it is on PATH)"]
    dest = target_dir / "loadout"
    text = launcher_text(paths.kit_root() / "bin" / "loadout")
    ours = dest.is_file() and not dest.is_symlink() and LAUNCHER_MARKER in dest.read_text(encoding="utf-8", errors="replace")
    if ours and dest.read_text(encoding="utf-8", errors="replace") == text:
        return []
    dest.parent.mkdir(parents=True, exist_ok=True)
    kit_link = dest.is_symlink() and _points_to(dest, paths.kit_root() / "bin" / "loadout")
    if (dest.exists() or dest.is_symlink()) and not ours and not kit_link:
        bk.move(dest, f"replaced {dest}", replace=True)
    elif dest.is_symlink() or dest.exists():
        dest.unlink()
    dest.write_text(text, encoding="utf-8", newline="\n")
    dest.chmod(0o755)
    return [f"wrote launcher {dest}"]
