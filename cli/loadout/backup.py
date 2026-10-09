"""Timestamped backups with an undo manifest; nothing the kit removes is ever deleted.

Restore follows the same rule: whatever it would overwrite or remove is first moved into a
new "pre-restore" backup, so a restore can itself be undone.
"""
from __future__ import annotations

import filecmp
import os
import shutil
import stat
import time
from pathlib import Path

from . import paths, runner
from .jsonio import load_json, save_json
from .secrets import redact

PRIVATE_DIR = 0o700
PRIVATE_FILE = 0o600


def _private(path: Path, mode: int) -> None:
    if os.name != "nt":
        os.chmod(path, mode)


class Backup:
    def __init__(self, root: Path | None = None, description: str = ""):
        self._fixed = root is not None
        self._root = root or paths.backups_root() / time.strftime("loadout-%Y%m%d-%H%M%S")
        self.description = description
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
            _private(self._root, PRIVATE_DIR)
            return
        base = self._root
        n = 1
        while True:
            candidate = base if n == 1 else base.with_name(f"{base.name}-{n}")
            try:
                candidate.parent.mkdir(parents=True, exist_ok=True)
                candidate.mkdir(mode=PRIVATE_DIR, exist_ok=False)
            except FileExistsError:
                n += 1
                continue
            _private(candidate, PRIVATE_DIR)  # backups can hold secrets (old configs, undo commands)
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
        mode = stat.S_IMODE(os.stat(path).st_mode)
        shutil.copy2(path, dest)
        _private(dest, PRIVATE_FILE)
        self._add(label, {"restore-file": [str(dest), str(path)], "mode": mode})
        return dest

    def record_created(self, path: Path, label: str) -> None:
        """A file the kit created: undo moves it into the pre-restore backup."""
        self._ensure_root()
        self._add(label, {"created": str(path)})

    def record_command(self, label: str, undo_cmd: list[str], **info) -> None:
        """info: extra facts kept in the manifest for the user (e.g. a marketplace's full source)."""
        self._ensure_root()
        self._add(label, {"run": undo_cmd}, **info)

    def _add(self, label: str, undo: dict, **info) -> None:
        self.steps.append({"label": label, "undo": undo, **info})
        manifest = {"description": self.description, "created_at": time.time(), "steps": self.steps}
        save_json(self.root / "manifest.json", manifest, mode=PRIVATE_FILE)


def _exists(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _mcp_target(cmd: list) -> tuple[str, str] | None:
    """("remove"|"add-json", server name) for a `claude mcp remove|add-json` command, else None."""
    if len(cmd) < 3 or cmd[:2] != ["claude", "mcp"] or cmd[2] not in ("remove", "add-json"):
        return None
    rest, pos = cmd[3:], []
    i = 0
    while i < len(rest):
        if rest[i] in ("-s", "--scope"):
            i += 2
            continue
        pos.append(rest[i])
        i += 1
    return (cmd[2], pos[0]) if pos else None


def _refused_pairs(ordered: list[dict], root: Path, force: bool) -> dict[int, str]:
    """Replay positions to skip: a remove whose paired (later) add-json would be refused, and that add.

    Running the remove alone would lose the server (Windows npm claude.cmd cannot take JSON).
    """
    skip: dict[int, str] = {}
    for i, step in enumerate(ordered):
        cmd = step.get("undo", {}).get("run")
        if not cmd or (step.get("restored") and not force) or _mcp_target(cmd) is None or _mcp_target(cmd)[0] != "remove":
            continue
        name = _mcp_target(cmd)[1]
        for j in range(i + 1, len(ordered)):
            other = ordered[j].get("undo", {}).get("run")
            if other and _mcp_target(other) == ("add-json", name):
                if runner.would_refuse(other):
                    where = runner.write_manual_commands(
                        root, f"restore: mcp {name} (remove, then add; full commands, contains secrets)", [cmd, other])
                    msg = (f"failed: {{label}}: not run, the paired add-json cannot run through this claude "
                           f"(Windows .cmd shim); run both commands in {where} by hand")
                    skip[i] = skip[j] = msg
                break
    return skip


def _undo(step: dict, pre: Backup, root: Path | None = None) -> str:
    undo, label = step["undo"], step["label"]
    if "move" in undo:
        src, dst = map(Path, undo["move"])
        if not _exists(src):
            return f"skipped (already restored, nothing left in the backup): {dst}"
        if _exists(dst):
            if not (dst.is_symlink() or undo.get("replace")):
                return f"skipped (exists): {dst}"
            pre.move(dst, f"{dst} before restore", replace=True)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
    elif "restore-file" in undo:
        src, dst = map(Path, undo["restore-file"])
        if not src.is_file():
            return f"failed: {label}: backup copy {src} is missing"
        if dst.is_file() and filecmp.cmp(src, dst, shallow=False):
            return f"unchanged: {label}"
        if _exists(dst):
            pre.save_copy(dst, f"{dst} before restore")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        if "mode" in undo and os.name != "nt":
            os.chmod(dst, undo["mode"])
    elif "created" in undo:
        path = Path(undo["created"])
        if not _exists(path):
            return f"skipped (already gone): {path}"
        pre.move(path, f"{path} (created by loadout)", replace=True)
        return f"moved aside: {path}"
    elif "run" in undo:
        cmd = undo["run"]
        if not cmd or cmd[0] != "claude":
            return f"failed: refusing to run a non-claude command from a manifest: {' '.join(cmd)}"
        if runner.would_refuse(cmd):
            where = runner.write_manual_commands(root or pre.root, f"restore: {label} (full command, contains secrets)", [cmd])
            return f"failed: {label}: cannot run through this claude (Windows .cmd shim); run the command in {where} by hand"
        res = runner.run(cmd)
        if not res.ok:
            return f"failed: {' '.join(cmd)}: {res.stderr.strip()}"
    return f"restored: {label}"


def restore(root: Path, force: bool = False) -> tuple[list[str], bool, Path | None]:
    """Replay a backup's undo steps in reverse. Returns (messages, all_ok, pre-restore backup root)."""
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        return [f"no loadout backup at {root} (manifest.json missing); see `loadout restore --list`"], False, None
    manifest = load_json(manifest_path)
    if manifest.get("restored_at") and not force:
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(manifest["restored_at"]))
        return [f"{root} was already restored at {when}; re-run with --force to replay it again"], False, None
    pre = Backup(description=f"pre-restore of {root}")
    lines, ok = [], True
    failed = []
    ordered = list(reversed(manifest.get("steps", [])))
    paired = _refused_pairs(ordered, root, force)
    for i, step in enumerate(ordered):
        if step.get("restored") and not force:
            lines.append(f"already restored: {step.get('label', '?')}")
            continue
        try:
            msg = paired[i].replace("{label}", step.get("label", "?"), 1) if i in paired else _undo(step, pre, root)
        except Exception as exc:  # one broken step must not abort the rest
            msg = f"failed: {step.get('label', '?')}: {exc}"
        if msg.startswith(("failed", "skipped (exists)")):
            failed.append(step.get("label", "?"))
            step.pop("restored", None)
        else:
            step["restored"] = True
        lines.append(redact(msg))
    ok = not failed
    if ok:
        manifest["restored_at"] = time.time()
    if manifest.get("steps"):
        save_json(manifest_path, manifest, mode=PRIVATE_FILE)
    if failed:
        lines.append(f"{len(failed)} step(s) NOT restored: {'; '.join(redact(x) for x in failed)}; "
                     "fix the cause and re-run the same restore to complete them")
    return lines, ok, (None if pre.empty else pre.root)


def list_backups() -> list[str]:
    root = paths.backups_root()
    rows = []
    for d in root.iterdir() if root.is_dir() else []:
        manifest = d / "manifest.json"
        if not manifest.is_file():
            continue
        try:
            data = load_json(manifest)
        except Exception:
            continue
        rows.append((data.get("created_at") or manifest.stat().st_mtime, d.name, d, data))
    out = []
    for created, _, d, data in sorted(rows, key=lambda r: (r[0], r[1]), reverse=True):
        n = len(data.get("steps", []))
        state = ("restored " + time.strftime("%Y-%m-%d %H:%M", time.localtime(data["restored_at"]))
                 if data.get("restored_at") else "not restored")
        desc = f"  {data['description']}" if data.get("description") else ""
        out.append(f"{d}  {n} step{'s' if n != 1 else ''}  {state}{desc}")
    return out
