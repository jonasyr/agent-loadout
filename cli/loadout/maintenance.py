"""SessionStart hook, detached daily/weekly maintenance, and `loadout update` (spec §6.4)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
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
        try:
            _spawn_background()
        except Exception:  # the notice above was already taken: still show it
            pass
    return out


def pull_if_clean(root: Path) -> bool:
    if not (root / ".git").exists() and not root.is_dir():
        return False
    """True only when a pull brought new commits (so settings/MCP need re-applying)."""
    status = runner.run(["git", "-C", str(root), "status", "--porcelain"], timeout=30)
    if not status.ok or status.stdout.strip():
        return False
    head = ["git", "-C", str(root), "rev-parse", "HEAD"]
    before = runner.run(head, timeout=30).stdout.strip()
    # a background process has no one to answer a credential prompt (or a GCM login window)
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}
    if not runner.run(["git", "-C", str(root), "pull", "--ff-only", "-q"], timeout=120, env=env).ok:
        return False
    after = runner.run(head, timeout=30).stdout.strip()
    return not (before and before == after)


def find_outdated() -> list[tuple[dict, tuple, tuple]]:
    out = []
    for entry in catalog.binaries():
        if not runner.have(entry["id"]):
            continue
        tool = pkgmgr.mise_tool(entry)
        if tool:  # ask mise: it knows the user's minimum_release_age and pins
            status = pkgmgr.mise_outdated(tool)
            if status is not None:
                if status:
                    out.append((entry, status[0] or versions.local_version(entry), status[1]))
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
    if not isinstance(data, dict):
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


LOCK = "maintenance.lock"
STALE_LOCK = 3600.0


def _acquire_lock() -> bool:
    """One maintenance run at a time; a lock older than an hour is from a crashed run."""
    lock = _stamp(LOCK)
    lock.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime < STALE_LOCK:
                    return False
                lock.unlink()
            except OSError:
                return False
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(str(os.getpid()))
        return True
    return False


def maintain(now: float) -> None:
    if not _acquire_lock():
        return
    try:
        _maintain(now)
    finally:
        try:
            _stamp(LOCK).unlink()
        except OSError:
            pass


def _maintain(now: float) -> None:
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
                bk = Backup(description="maintenance: rule copies refreshed after a pull")
                link.link_all(bk)
                if not bk.empty:
                    notify(f"loadout: refreshed the copied rules; your edited copies are in {bk.root} "
                           f"(undo: loadout restore {bk.root})")
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
    """Legacy kit-duplicate hook scripts (exact cbm-* names) that no settings hook references any more."""
    from . import duplicates
    hooks_dir = paths.claude_home() / "hooks"
    if not hooks_dir.is_dir():
        return []
    refs, out = _hook_references(), []
    for path in sorted(hooks_dir.iterdir()):
        if not path.is_file() or not duplicates.is_legacy_script_file(path.name) or path.name in refs:
            continue
        bk.move(path, f"hook script {path}")
        out.append(f"moved unreferenced hook script {path} to the backup")
    return out


def undo_reregistered(bk: Backup) -> tuple[list[str], list[str]]:
    """(removed, reported). Removes only exact duplicates of MCP servers/hooks the enabled loadout plugin ships."""
    from . import adopt, duplicates, inventory
    try:
        items = [i for i in inventory.collect(with_versions=False) if i.kind in ("mcp", "hook")]
        enabled = duplicates.plugin_enabled()
        verdicts = {(v.item.kind, v.item.name, v.item.location, v.item.detail): v.action
                    for v in inventory.classify(items)}
    except Exception as exc:  # e.g. invalid JSON: report, never guess
        return [], [f"could not check for re-registered duplicates: {exc}"]
    dupes, reported = [], []
    for item in items:
        exact = enabled and (duplicates.is_duplicate_mcp(item) if item.kind == "mcp" else duplicates.is_duplicate_hook(item))
        if exact and duplicates.would_refuse_undo(item):
            reported.append(f"{item.kind} {item.name}: duplicate, not removed automatically here (Windows .cmd shim); "
                            "review with `loadout adopt`")
        elif exact:
            dupes.append(inventory.Verdict(item, "migrate", "exact duplicate of the loadout plugin"))
        elif verdicts.get((item.kind, item.name, item.location, item.detail)) == "migrate":
            reported.append(f"{item.kind} {item.name}: resembles a kit item but is not an exact duplicate of the "
                            "enabled loadout plugin; left alone (review with `loadout adopt`)")
    removed = adopt.apply(dupes, bk) if dupes else []
    if enabled:
        removed += _stray_hook_scripts(bk)
    return removed, reported


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
        all_ok = True
        for cmd in cmds:
            res = runner.run(cmd, timeout=900)
            all_ok = all_ok and res.ok
            print("  ok" if res.ok else f"  failed: {res.stderr.strip()[:300]}")
        now = versions.local_version(entry)
        if now is not None and now >= latest:
            _remember_refused(entry["id"], None)
        elif not all_ok or now is None:
            pass  # a failure is not a refusal: keep notifying
        elif now == local:
            _remember_refused(entry["id"], latest)
            print(f"  still {versions.fmt(now)}: the update ran but the package manager installed nothing newer; "
                  f"no new notice until a version newer than {versions.fmt(latest)} appears")
        else:
            _remember_refused(entry["id"], None)
            print(f"  updated to {versions.fmt(now)}; {versions.fmt(latest)} was not installed (held back by the package manager?)")
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
        removed, reported = undo_reregistered(bk)
        if removed:
            print("\nundid duplicates that an installer re-registered (the loadout plugin provides them):")
            for line in removed:
                print(f"  {redact(line)}")
        for line in reported:
            print(f"note: {redact(line)}")
        if not bk.empty:
            print(f"backup: {bk.root}  (undo: loadout restore {bk.root})")
    return 0
