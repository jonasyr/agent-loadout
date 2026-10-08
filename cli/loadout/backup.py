"""Timestamped backups with an undo manifest; nothing the kit removes is ever deleted."""
from __future__ import annotations

import shutil
import time
from pathlib import Path

from . import paths, runner
from .jsonio import load_json, save_json


class Backup:
    def __init__(self, root: Path | None = None):
        self._fixed = root is not None
        self._root = root or paths.backups_root() / time.strftime("loadout-%Y%m%d-%H%M%S")
        self.steps: list[dict] = []

    @property
    def root(self) -> Path:
        return self._root

    @property
    def empty(self) -> bool:
        return not self.steps

    def _ensure_root(self) -> None:
        """Pick a fresh directory at first write, so concurrent Backups never share one."""
        if self._fixed:
            self._root.mkdir(parents=True, exist_ok=True)
            return
        base = self._root
        n = 1
        while True:
            candidate = base if n == 1 else base.with_name(f"{base.name}-{n}")
            try:
                candidate.parent.mkdir(parents=True, exist_ok=True)
                candidate.mkdir(exist_ok=False)
            except FileExistsError:
                n += 1
                continue
            self._root = candidate
            self._fixed = True
            return

    def _slot(self, path: Path) -> Path:
        self._ensure_root()
        dest = self.root / "files" / f"{len(self.steps):03d}-{path.name}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        return dest

    def move(self, path: Path, label: str, replace: bool = False) -> Path:
        dest = self._slot(path)
        shutil.move(str(path), str(dest))
        undo = {"move": [str(dest), str(path)]}
        if replace:
            undo["replace"] = True
        self._add(label, undo)
        return dest

    def save_copy(self, path: Path, label: str) -> Path:
        dest = self._slot(path)
        shutil.copy2(path, dest)
        self._add(label, {"restore-file": [str(dest), str(path)]})
        return dest

    def record_command(self, label: str, undo_cmd: list[str]) -> None:
        self._ensure_root()
        self._add(label, {"run": undo_cmd})

    def _add(self, label: str, undo: dict) -> None:
        self.steps.append({"label": label, "undo": undo})
        save_json(self.root / "manifest.json", {"steps": self.steps})


def _remove(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    else:
        shutil.rmtree(path)


def restore(root: Path) -> list[str]:
    done = []
    for step in reversed(load_json(root / "manifest.json").get("steps", [])):
        undo = step["undo"]
        if "move" in undo:
            src, dst = map(Path, undo["move"])
            if dst.exists() or dst.is_symlink():
                if not (dst.is_symlink() or undo.get("replace")):
                    done.append(f"skipped (exists): {dst}")
                    continue
                _remove(dst)  # loadout's own replacement (symlink or copy) makes way for the original
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
        elif "restore-file" in undo:
            src, dst = map(Path, undo["restore-file"])
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        elif "run" in undo:
            res = runner.run(undo["run"])
            if not res.ok:
                done.append(f"failed: {' '.join(undo['run'])}: {res.stderr.strip()}")
                continue
        done.append(f"restored: {step['label']}")
    return done
