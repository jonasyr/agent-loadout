"""Timestamped backups with an undo manifest; nothing the kit removes is ever deleted.

Restore follows the same rule: whatever it would overwrite or remove is first moved into a
new "pre-restore" backup, so a restore can itself be undone.
"""
from __future__ import annotations

import filecmp
import json
import os
import shutil
import stat
import time
from pathlib import Path

from . import paths, runner
from .jsonio import get_dict, load_json, save_json
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
        undo = {"move": [str(dest), str(path)]}
        if replace:
            undo["replace"] = True
        self._add(label, undo)  # manifest first: a crash mid-move still leaves the undo record
        try:
            shutil.move(str(path), str(dest))
        except BaseException:
            self.steps.pop()
            self._save()
            raise
        return dest

    def save_copy(self, path: Path, label: str) -> Path:
        dest = self._slot(path)
        mode = stat.S_IMODE(os.stat(path).st_mode)
        shutil.copy2(path, dest)
        _private(dest, PRIVATE_FILE)
        self._add(label, {"restore-file": [str(dest), str(path)], "mode": mode})
        return dest

    def keep(self, path: Path, label: str) -> Path:
        """Move a file loadout wrote (e.g. an old registry value) into the backup; restore points to it."""
        dest = self._slot(path)
        shutil.move(str(path), str(dest))
        _private(dest, PRIVATE_FILE)
        self._add(label, {"kept": str(dest)})
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
        self._save()

    def _save(self) -> None:
        if not hasattr(self, "_created_at"):
            self._created_at = time.time()
        manifest = {"description": self.description, "created_at": self._created_at, "steps": self.steps}
        save_json(self.root / "manifest.json", manifest, mode=PRIVATE_FILE)


def _exists(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _mcp_target(cmd: list) -> tuple[str, str] | None:
    t = runner.mcp_target(cmd)
    return (t[0], t[2]) if t else None


def _refused_pairs(ordered: list[dict], root: Path, force: bool) -> dict[int, str]:
    """Replay positions to skip: a remove whose paired (later) add-json would be refused, and that add.

    Running the remove alone would lose the server (Windows npm claude.cmd cannot take JSON).
    """
    skip: dict[int, str] = {}
    for i, step in enumerate(ordered):
        cmd = get_dict(step, "undo").get("run")
        if not cmd or (step.get("restored") and not force) or _mcp_target(cmd) is None or _mcp_target(cmd)[0] != "remove":
            continue
        name = _mcp_target(cmd)[1]
        for j in range(i + 1, len(ordered)):
            other = get_dict(ordered[j], "undo").get("run")
            if other and _mcp_target(other) == ("add-json", name) and _allowed_run(cmd) and _allowed_run(other):
                if runner.would_refuse(other):
                    where = runner.write_manual_commands(
                        root, f"restore: mcp {name} (remove, then add; full commands, contains secrets)", [cmd, other])
                    msg = (f"failed: {{label}}: not run, the paired add-json cannot run through this claude "
                           f"(Windows .cmd shim); run both commands in {where} by hand")
                    skip[i] = skip[j] = msg
                break
    return skip


def _allowed_run(cmd) -> bool:
    """Only the undo commands loadout itself records; a manifest cannot make restore run anything else."""
    if not isinstance(cmd, list) or len(cmd) < 4 or not all(isinstance(a, str) for a in cmd):
        return False
    n = len(cmd)
    slot = {"add-json": 5, "remove": 5}.get(cmd[2]) if cmd[:2] == ["claude", "mcp"] and n > 2 else n - 1
    if cmd[:2] == ["claude", "plugin"] and n > 2 and cmd[2] in ("enable", "install"):
        slot = 3
    if slot is None or slot >= n or cmd[slot].startswith("-") or not cmd[slot]:  # the name, id or origin slot
        return False
    if cmd[:3] == ["claude", "mcp", "add-json"] and n == 7 and cmd[3:5] == ["-s", "user"]:
        try:
            return isinstance(json.loads(cmd[6]), dict)
        except ValueError:
            return False
    if cmd[:3] == ["claude", "mcp", "remove"]:
        return n == 6 and cmd[3:5] == ["-s", "user"]
    if cmd[:2] == ["claude", "plugin"] and n == 6 and cmd[2] in ("enable", "install"):
        return cmd[4:] == ["--scope", "user"]
    if cmd[:4] == ["claude", "plugin", "marketplace", "add"]:
        return n == 5
    if cmd[:3] == ["codex", "plugin", "remove"]:
        return n == 4
    if cmd[:4] == ["codex", "plugin", "marketplace", "remove"]:
        return n == 5
    return False


def _inside(path: Path, folder: Path) -> bool:
    if path.name in ("", ".", ".."):  # files/.. would be the backup itself
        return False
    try:  # resolve the folder around the entry, not the entry itself: a backed-up symlink stays a symlink
        (path.parent.resolve() / path.name).relative_to(folder.resolve())
        return True
    except (ValueError, OSError):
        return False


def _undo(step: dict, pre: Backup, root: Path | None = None) -> str:
    undo, label = step["undo"], step["label"]
    for key in ("move", "restore-file"):
        if key in undo and not _inside(Path(undo[key][0]), (root or pre.root) / "files"):
            return f"failed: {label}: its backup copy is not inside {root or pre.root}"
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
        if src.is_symlink() or not src.is_file():  # save_copy always writes a regular file
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
    elif "kept" in undo:
        return f"not restored automatically: {label}; the old value is in {undo['kept']}, restore it by hand"
    elif "run" in undo:
        cmd = undo["run"]
        if not _allowed_run(cmd):  # the undo commands loadout records only, never a shell
            shown = " ".join(map(str, cmd)) if isinstance(cmd, list) else str(cmd)
            return f"failed: refusing to run this command from a manifest: {shown}"
        if runner.would_refuse(cmd):
            where = runner.write_manual_commands(root or pre.root, f"restore: {label} (full command, contains secrets)", [cmd])
            return f"failed: {label}: cannot run through this claude (Windows .cmd shim); run the command in {where} by hand"
        res = runner.run(cmd)
        if not res.ok:
            return f"failed: {' '.join(cmd)}: {res.stderr.strip()}"
    return f"restored: {label}"


def restore(root: Path, force: bool = False) -> tuple[list[str], bool, Path | None]:
    """Replay a backup's undo steps in reverse. Returns (messages, all_ok, pre-restore backup root)."""
    try:  # the backup folder itself, resolved: a symlinked or `..` folder is not one of loadout's backups
        base = paths.backups_root().resolve()
        root = root.resolve()
        inside = root != base and root.is_relative_to(base)
    except OSError:
        inside = False
    if not inside:
        return [f"loadout only restores backups under {paths.backups_root()}; move it there first"], False, None
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        return [f"no loadout backup at {root} (manifest.json missing); see `loadout restore --list`"], False, None
    manifest = load_json(manifest_path)
    if "steps" in manifest and not isinstance(manifest["steps"], list):
        return [f"failed: the backup's manifest is damaged ({manifest_path}: steps is not a list)"], False, None
    if manifest.get("restored_at") and not force:
        when = _stamp(manifest["restored_at"])
        return [f"{root} was already restored at {when}; re-run with --force to replay it again"], False, None
    pre = Backup(description=f"pre-restore of {root}")
    lines, ok = [], True
    failed = []
    ordered = [s for s in reversed(manifest.get("steps", [])) if isinstance(s, dict)]  # a damaged entry is skipped
    paired = _refused_pairs(ordered, root, force)
    for i, step in enumerate(ordered):
        name = str(step.get("label", "?"))
        if step.get("restored") and not force:
            lines.append(f"already restored: {name}")
            continue
        try:
            msg = paired[i].replace("{label}", name, 1) if i in paired else _undo(step, pre, root)
        except Exception as exc:  # one broken step must not abort the rest
            msg = f"failed: {name}: {exc}"
        if msg.startswith(("failed", "skipped (exists)")):
            failed.append(name)
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


def _stamp(value) -> str:
    """A time for a message; a damaged value (a string where a number was written) shows as '?'."""
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(value))
    except (TypeError, ValueError, OverflowError, OSError):
        return "?"


def list_backups() -> list[str]:
    root = paths.backups_root()
    rows = []
    for d in root.iterdir() if root.is_dir() else []:
        if d.is_symlink():  # restore refuses it, so it is not listed
            continue
        manifest = d / "manifest.json"
        if not manifest.is_file():
            continue
        try:
            data = load_json(manifest)
        except Exception:
            continue
        if not isinstance(data.get("steps", []), list):  # a damaged manifest is not listed
            continue
        created = data.get("created_at")
        rows.append((created if isinstance(created, (int, float)) and created > 0 else manifest.stat().st_mtime,
                     d.name, d, data))
    out = []
    home = str(paths.home())
    for created, _, d, data in sorted(rows, key=lambda r: (r[0], r[1]), reverse=True):
        n = len(data.get("steps", []))
        state = "restored " + _stamp(data["restored_at"]) if data.get("restored_at") else "not restored"
        desc = f"  {data['description']}" if data.get("description") else ""
        shown = "~" + str(d)[len(home):] if str(d).startswith(home) else str(d)
        when = _stamp(created)
        out.append(f"{shown}  {when}  {n} step{'s' if n != 1 else ''}  {state}{desc}")
    return out
