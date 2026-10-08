"""Timestamped backups with an undo manifest; nothing the kit removes is ever deleted."""
from __future__ import annotations

import shutil
import time
from pathlib import Path

from . import paths, runner
from .jsonio import load_json, save_json


class Backup:
    def __init__(self, root: Path | None = None):
        self.root = root or paths.backups_root() / time.strftime("loadout-%Y%m%d-%H%M%S")
        self.steps: list[dict] = []

    @property
    def empty(self) -> bool:
        return not self.steps

    def _slot(self, path: Path) -> Path:
        dest = self.root / "files" / f"{len(self.steps):03d}-{path.name}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        return dest

    def move(self, path: Path, label: str) -> Path:
        dest = self._slot(path)
        shutil.move(str(path), str(dest))
        self._add(label, {"move": [str(dest), str(path)]})
        return dest

    def save_copy(self, path: Path, label: str) -> Path:
        dest = self._slot(path)
        shutil.copy2(path, dest)
        self._add(label, {"restore-file": [str(dest), str(path)]})
        return dest

    def record_command(self, label: str, undo_cmd: list[str]) -> None:
        self._add(label, {"run": undo_cmd})

    def _add(self, label: str, undo: dict) -> None:
        self.steps.append({"label": label, "undo": undo})
        save_json(self.root / "manifest.json", {"steps": self.steps})


def restore(root: Path) -> list[str]:
    done = []
    for step in reversed(load_json(root / "manifest.json").get("steps", [])):
        undo = step["undo"]
        if "move" in undo:
            src, dst = map(Path, undo["move"])
            if dst.exists() or dst.is_symlink():
                done.append(f"skipped (exists): {dst}")
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
        elif "restore-file" in undo:
            src, dst = map(Path, undo["restore-file"])
            shutil.copy2(src, dst)
        elif "run" in undo:
            res = runner.run(undo["run"])
            if not res.ok:
                done.append(f"failed: {' '.join(undo['run'])}: {res.stderr.strip()}")
                continue
        done.append(f"restored: {step['label']}")
    return done
