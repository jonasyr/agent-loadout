"""SessionStart hook, detached daily/weekly maintenance, and `loadout update` (spec §6.4)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

from . import catalog, link, paths, runner, versions
from .backup import Backup
from .jsonio import load_json, save_json

DAY = 86400.0
WEEK = 7 * DAY
NOTICE = "pending-notice"


def _stamp(name: str) -> Path:
    return paths.state_dir() / name


def is_due(name: str, interval: float, now: float) -> bool:
    try:
        return now - float(_stamp(name).read_text(encoding="utf-8")) >= interval
    except (OSError, ValueError):
        return True


def touch(name: str, now: float) -> None:
    _stamp(name).parent.mkdir(parents=True, exist_ok=True)
    _stamp(name).write_text(str(now), encoding="utf-8")


def _spawn_background() -> None:
    kwargs = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen([sys.executable, str(paths.kit_root() / "bin" / "loadout"), "maintenance"], **kwargs)


def notify(text: str) -> None:
    """Queue a message for the next session start; several messages are all kept."""
    path = _stamp(NOTICE)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(text.rstrip() + "\n")


def session_start(now: float) -> str | None:
    out = None
    notice = _stamp(NOTICE)
    if notice.exists():
        out = json.dumps({"systemMessage": notice.read_text(encoding="utf-8").strip()})
        notice.unlink()
    if is_due("last-pull", DAY, now) or is_due("last-update-check", WEEK, now):
        _spawn_background()
    return out


def pull_if_clean(root: Path) -> bool:
    if not (root / ".git").exists() and not root.is_dir():
        return False
    status = runner.run(["git", "-C", str(root), "status", "--porcelain"], timeout=30)
    if not status.ok or status.stdout.strip():
        return False
    # a background process has no one to answer a credential prompt (or a GCM login window)
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}
    return runner.run(["git", "-C", str(root), "pull", "--ff-only", "-q"], timeout=120, env=env).ok


def find_outdated() -> list[tuple[dict, tuple, tuple]]:
    out = []
    for entry in catalog.binaries():
        if not runner.have(entry["id"]):
            continue
        local, latest = versions.local_version(entry), versions.latest_version(entry)
        if local and latest and latest > local:
            out.append((entry, local, latest))
    return out


def maintain(now: float) -> None:
    from .settings_merge import apply_settings

    if os.environ.get("LOADOUT_NO_AUTO_PULL") == "1":
        pass  # opt-out: no daily kit/personal sync (see README, Security & trust)
    elif is_due("last-pull", DAY, now):
        touch("last-pull", now)
        pulled = [pull_if_clean(root) for root in (paths.kit_root(), paths.personal_root()) if (root / ".git").exists()]
        if any(pulled):
            try:
                apply_settings()
                from . import personal_mcp
                for line in personal_mcp.apply_mcp():
                    notify(f"loadout: {line}")
            except Exception as exc:  # never crash in the background; surface next session
                notify(f"loadout: could not apply settings after sync: {exc}")
            if link.is_copy_mode():
                link.link_all(Backup())
    if is_due("last-update-check", WEEK, now):
        touch("last-update-check", now)
        outdated = find_outdated()
        if outdated:
            items = ", ".join(f"{e['id']} {versions.fmt(a)} -> {versions.fmt(b)}" for e, a, b in outdated)
            notify(f"loadout: updates available for {items} → run `loadout update`")


def update(yes: bool, ask: Callable[[str], str]) -> int:
    runner.run(["claude", "plugin", "marketplace", "update"], timeout=300)
    settings_path = paths.claude_home() / "settings.json"
    before = load_json(settings_path)
    outdated = find_outdated()
    if not outdated:
        print("all tools up to date")
    for entry, local, latest in outdated:
        cmds = catalog.platform_cmds(entry, "update")
        print(f"{entry['id']}: {versions.fmt(local)} -> {versions.fmt(latest)}")
        if not cmds:
            print(f"  no update command for this platform. {entry.get('manual', '')}")
            continue
        for cmd in cmds:
            print("  command: " + " ".join(cmd))
        if not yes and ask("  run it? [y/N] ").strip().lower() != "y":
            continue
        for cmd in cmds:
            res = runner.run(cmd, timeout=900)
            print("  ok" if res.ok else f"  failed: {res.stderr.strip()[:300]}")
    after = load_json(settings_path)
    if after != before:
        changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
        bk = Backup(description="update: settings.json as modified by an installer")
        bk.save_copy(settings_path, "settings.json as modified by an installer")
        print(f"an installer modified ~/.claude/settings.json (keys: {', '.join(changed)}); reverting to the "
              f"kit-merged version. The installer's version is in {bk.root}")
        save_json(settings_path, before)
    return 0
