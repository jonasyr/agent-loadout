"""Link kit/personal rules into ~/.claude/rules and put loadout on PATH."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from . import paths
from .backup import Backup


def LINKS() -> list[tuple[Path, Path]]:
    rules = paths.claude_home() / "rules"
    return [
        (rules / "loadout", paths.kit_root() / "rules"),
        (rules / "personal", paths.personal_root() / "rules"),
    ]


def _marker() -> Path:
    return paths.state_dir() / "copy-mode"


def is_copy_mode() -> bool:
    return _marker().exists()


def _points_to(dest: Path, src: Path) -> bool:
    return dest.is_symlink() and dest.resolve() == src.resolve()


def _replace_with_copy(src: Path, dest: Path) -> None:
    if dest.is_symlink() or dest.is_file():
        dest.unlink()
    elif dest.exists():
        shutil.rmtree(dest)
    if src.is_dir():
        shutil.copytree(src, dest)
    else:
        shutil.copy2(src, dest)


def _link_one(dest: Path, src: Path, bk: Backup) -> str | None:
    if not src.exists() or _points_to(dest, src):
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    if is_copy_mode() and not dest.is_symlink():
        _replace_with_copy(src, dest)
        return None  # refresh, not news
    if dest.exists() or dest.is_symlink():
        bk.move(dest, f"replaced {dest}")
    try:
        os.symlink(src, dest, target_is_directory=src.is_dir())
        return f"linked {dest} -> {src}"
    except OSError:
        _marker().parent.mkdir(parents=True, exist_ok=True)
        _marker().write_text("symlinks unavailable; files are copied and refreshed by maintenance\n")
        _replace_with_copy(src, dest)
        return f"copied {src} -> {dest} (symlinks unavailable)"


def link_all(bk: Backup) -> list[str]:
    return [a for dest, src in LINKS() if (a := _link_one(dest, src, bk))]


def write_windows_shims(target_dir: Path) -> None:
    script = paths.kit_root() / "bin" / "loadout"
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "loadout.cmd").write_text(f'@echo off\r\npython "{script}" %*\r\n', encoding="utf-8")
    # Git Bash (used for hooks on Windows) runs extensionless scripts
    (target_dir / "loadout").write_text(f'#!/bin/sh\nexec python "{script.as_posix()}" "$@"\n', encoding="utf-8")


def link_bin(bk: Backup) -> list[str]:
    target_dir = paths.bin_dir()
    if os.name == "nt":
        write_windows_shims(target_dir)
        return [f"wrote shims to {target_dir} (make sure it is on PATH)"]
    action = _link_one(target_dir / "loadout", paths.kit_root() / "bin" / "loadout", bk)
    return [action] if action else []
