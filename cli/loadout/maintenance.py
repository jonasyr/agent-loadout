"""SessionStart hook, detached daily/weekly maintenance, and `loadout update` (spec §6.4)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

from . import catalog, link, paths, pkgmgr, runner, versions
from .backup import Backup
from .jsonio import load_json, save_json
from .secrets import redact

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


def _refused_path() -> Path:
    return paths.state_dir() / "refused-updates.json"


def _refused() -> dict:
    try:
        data = load_json(_refused_path())
    except Exception:
        return {}
    return {k: v for k, v in data.items() if isinstance(v, str)}


def _remember_refused(tool: str, latest: tuple | None) -> None:
    data = _refused()
    if latest is None:
        data.pop(tool, None)
    else:
        data[tool] = versions.fmt(latest)
    save_json(_refused_path(), data)


def worth_notifying(outdated: list) -> list:
    """Drop updates a package manager already refused (e.g. mise minimum_release_age) until a newer one appears."""
    refused = _refused()
    return [(e, a, b) for e, a, b in outdated
            if not (e["id"] in refused and (versions.parse_version(refused[e["id"]]) or ()) >= b)]


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
        outdated = worth_notifying(find_outdated())
        if outdated:
            items = ", ".join(f"{e['id']} {versions.fmt(a)} -> {versions.fmt(b)}" for e, a, b in outdated)
            notify(f"loadout: updates available for {items} → run `loadout update`")


def _hook_references() -> str:
    """Every hook command in the user's settings files, as one searchable text."""
    texts = []
    for name in ("settings.json", "settings.local.json"):
        try:
            texts.append(json.dumps(load_json(paths.claude_home() / name).get("hooks", {})))
        except Exception:
            texts.append("")
    return "\n".join(texts)


def _stray_hook_scripts(bk: Backup) -> list[str]:
    """Hook script files duplicating kit hooks (cbm-*) that no settings hook references any more."""
    hooks_dir = paths.claude_home() / "hooks"
    if not hooks_dir.is_dir():
        return []
    refs, out = _hook_references(), []
    for path in sorted(hooks_dir.iterdir()):
        entry = catalog.match("hook", path.name, path.name)
        if entry is None or entry["status"] != "core" or path.name in refs:
            continue
        bk.move(path, f"hook script {path}")
        out.append(f"moved unreferenced hook script {path} to the backup")
    return out


def undo_reregistered(bk: Backup) -> list[str]:
    """Apply only adopt's `migrate` verdicts: exact duplicates of what the loadout plugin provides."""
    from . import adopt, inventory
    try:
        verdicts = inventory.classify(inventory.collect(with_versions=False))
    except Exception as exc:  # e.g. invalid JSON: report, never guess
        return [f"could not check for re-registered duplicates: {exc}"]
    dupes = [v for v in verdicts if v.action == "migrate" and v.item.kind in ("mcp", "hook", "skill")]
    out = adopt.apply(dupes, bk) if dupes else []
    return out + _stray_hook_scripts(bk)


def update(yes: bool, ask: Callable[[str], str]) -> int:
    runner.run(["claude", "plugin", "marketplace", "update"], timeout=300)
    settings_path = paths.claude_home() / "settings.json"
    before = load_json(settings_path)
    outdated = find_outdated()
    ran = False
    if not outdated:
        print("all tools up to date")
    for entry, local, latest in outdated:
        cmds, how = pkgmgr.update_plan(entry)
        print(f"{entry['id']}: {versions.fmt(local)} -> {versions.fmt(latest)}" + (f" (via {how})" if how != "catalog" else ""))
        if not cmds:
            print(f"  no update command for this platform. {entry.get('manual', '')}")
            continue
        for cmd in cmds:
            print("  command: " + " ".join(cmd))
        if not yes and ask("  run it? [y/N] ").strip().lower() != "y":
            continue
        ran = True
        for cmd in cmds:
            res = runner.run(cmd, timeout=900)
            print("  ok" if res.ok else f"  failed: {res.stderr.strip()[:300]}")
        now = versions.local_version(entry)
        if now is not None and now >= latest:
            _remember_refused(entry["id"], None)
        else:
            _remember_refused(entry["id"], latest)
            print(f"  still {versions.fmt(now or local)} (the package manager may hold it back, e.g. mise "
                  f"minimum_release_age); no new notice until a version newer than {versions.fmt(latest)} appears")
    after = load_json(settings_path)
    if after != before:
        changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
        bk = Backup(description="update: settings.json as modified by an installer")
        bk.save_copy(settings_path, "settings.json as modified by an installer")
        print(f"an installer modified ~/.claude/settings.json (keys: {', '.join(changed)}); reverting to the "
              f"kit-merged version. The installer's version is in {bk.root}")
        save_json(settings_path, before)
    if ran:  # installers re-register what the loadout plugin already provides
        bk = Backup(description="update: duplicates re-registered by installers")
        lines = undo_reregistered(bk)
        if lines:
            print("\nundid duplicates that an installer re-registered (the loadout plugin provides them):")
            for line in lines:
                print(f"  {redact(line)}")
        if not bk.empty:
            print(f"backup: {bk.root}  (undo: loadout restore {bk.root})")
    return 0
