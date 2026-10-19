"""SessionStart hook, detached daily/weekly maintenance, and `loadout update` (spec §6.4)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import catalog, link, locks, paths, pkgmgr, runner, versions
from .backup import Backup
from .jsonio import load_json, save_json
from .out import printable
from .secrets import redact

DAY = 86400.0
WEEK = 7 * DAY
NOTICE = "pending-notice"


def codex_notice(line: str) -> bool:
    """A Codex line worth a notice: a problem, not loadout leaving the user's own entry alone (said by check)."""
    from .out import PROBLEM
    return (bool(PROBLEM.search(line)) and "left as is" not in line) or "/hooks" in line  # Codex runs nothing unapproved


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
    kwargs = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
              "cwd": str(paths.home())}  # never the project folder: Windows searches it for programs
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
    pull_due = os.environ.get("LOADOUT_NO_AUTO_PULL") != "1" and is_due("last-pull", DAY, now)
    if pull_due or is_due("last-update-check", WEEK, now):
        try:
            _spawn_background()
        except Exception:  # the notice above was already taken: still show it
            pass
    try:  # a hand edit of a rule or me.md reaches Codex at the next session (Claude Code reads the files live)
        from . import codex
        codex.refresh_instructions()
    except Exception:  # never break a session start
        pass
    return out


@dataclass
class PullResult:
    pulled: bool = False  # new commits arrived (settings, MCP and links need re-applying)
    paused: str | None = None  # why git refused; None when the pull ran, or was skipped for want of an upstream
    files: list[str] = field(default_factory=list)  # the files git named in a refusal


def _paused_path() -> Path:
    return paths.state_dir() / "sync-paused.json"


def paused() -> dict[str, dict]:
    """The checkouts whose daily pull git refused: {root: {"reason", "files", "at"}}; empty when none."""
    try:
        data = load_json(_paused_path())
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict) and isinstance(v.get("reason"), str)}


def _record_paused(root: Path, entry: dict | None) -> bool:
    """Store (or, with None, drop) the refusal for root. True when it differs from what was recorded."""
    data = paused()
    old = data.get(str(root))
    if entry is None:
        if old is None:
            return False
        del data[str(root)]
    else:
        data[str(root)] = entry
    if data:
        save_json(_paused_path(), data)
    else:
        _paused_path().unlink(missing_ok=True)
    return entry is not None and (old is None or (old.get("reason"), old.get("files")) != (entry["reason"], entry["files"]))


def _refusal(stderr: str) -> tuple[str, list[str]]:
    """A failed `git pull --ff-only`: the reason in plain words and the files git named (tab-indented lines)."""
    lines = stderr.splitlines()
    for i, line in enumerate(lines):
        if "would be overwritten by merge:" in line:
            files = []
            for item in lines[i + 1:]:
                if not item.startswith("\t"):
                    break
                files.append(item[1:])
            return "local changes the pull would overwrite", files
    if "fast-forward" in stderr or "diverg" in stderr.lower():
        return "your branch and its upstream have diverged", []
    first = next((l.strip() for l in lines if l.strip()), "")
    return printable(first) or "git pull failed", []


def pull(root: Path) -> PullResult:
    """Fast-forward the checkout and let git refuse on its own: it never overwrites a local change, so a dirty
    tree is no reason to skip (untracked files and unrelated edits do not block a fast-forward). A refusal is
    recorded with the files git named and queued once as a notice."""
    if not (root / ".git").exists() and not root.is_dir():
        return PullResult()
    git = ["git", "-c", "core.quotePath=false", "-C", str(root)]
    if not runner.run(["git", "-C", str(root), "symbolic-ref", "-q", "HEAD"], timeout=30).ok:
        return PullResult()  # detached HEAD: nothing to follow
    if not runner.run(["git", "-C", str(root), "rev-parse", "--abbrev-ref", "@{u}"], timeout=30).ok:
        return PullResult()  # no upstream: nothing to pull
    head = ["git", "-C", str(root), "rev-parse", "HEAD"]
    before = runner.run(head, timeout=30).stdout.strip()
    # a background process has no one to answer a credential prompt (or a GCM login window); C locale for parsing
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never", "LC_ALL": "C"}
    res = runner.run([*git, "pull", "--ff-only", "-q"], timeout=120, env=env)
    if not res.ok:
        reason, files = _refusal(res.stderr or "")
        if _record_paused(root, {"reason": reason, "files": files, "at": time.time()}):
            if files:
                notify(f"loadout: the daily sync of {root} paused: {reason}: {', '.join(printable(f) for f in files)}; "
                       "commit or stash them, then run loadout update")
            else:
                notify(f"loadout: the daily sync of {root} paused: {reason}; resolve it, then run loadout update")
        return PullResult(False, reason, files)
    _record_paused(root, None)
    after = runner.run(head, timeout=30).stdout.strip()
    return PullResult(not (before and before == after))


def pull_if_clean(root: Path) -> bool:
    """True only when a pull brought new commits (kept for callers that want the bare answer)."""
    return pull(root).pulled


def find_outdated() -> list[tuple[dict, tuple, tuple]]:
    out = []
    for entry in catalog.binaries():
        if entry.get("helper") or not runner.have(entry["id"]):
            continue  # helpers (mise) only install other tools; they are not offered as updates
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

    def held(e, b):
        if e["id"] not in refused or pkgmgr.mise_tool(e):  # mise tools: mise already filtered them
            return False
        return (versions.parse_version(refused[e["id"]]) or ()) >= b

    return [(e, a, b) for e, a, b in outdated if not held(e, b)]


LOCK = "maintenance.lock"
STALE_LOCK = 3600.0


_held: locks.Lock | None = None


def _acquire_lock(command: str = "maintain", wait: float | None = 0) -> bool:
    """One maintenance/update run at a time; a lock older than an hour is from a crashed run."""
    global _held
    _held = locks.acquire(LOCK, command, wait, stale=STALE_LOCK)
    return _held is not None


def _touch_lock() -> None:
    """Long runs refresh the lock, so nobody takes it over as stale while we still work."""
    if _held:
        _held.touch()


def _release_lock() -> None:
    global _held
    if _held:
        _held.release()
    _held = None


def maintain(now: float) -> None:
    if not _acquire_lock():
        return
    try:
        _maintain(now)
    finally:
        _release_lock()


def _maintain(now: float) -> None:
    from .settings_merge import apply_settings

    if os.environ.get("LOADOUT_NO_AUTO_PULL") == "1":
        pass  # opt-out: no daily kit/personal sync (see README, Security & trust)
    elif is_due("last-pull", DAY, now):
        touch("last-pull", now)
        pulled = [pull(root).pulled for root in (paths.kit_root(), paths.personal_root()) if (root / ".git").exists()]
        if any(pulled):
            from . import targets
            from .jsonio import InvalidJSON
            try:
                claude_on = targets.claude_enabled()
            except InvalidJSON as exc:  # never die silently in the background: say so next session, keep Claude
                notify(f"loadout: {targets.path()} is not valid JSON ({exc}); fix it, then run loadout bootstrap")
                claude_on = True
            if claude_on:  # Codex only: nothing of Claude Code to refresh
                try:
                    apply_settings()
                    from . import personal_mcp
                    for line in personal_mcp.apply_mcp():
                        notify(f"loadout: {line}")
                except Exception as exc:  # never crash in the background; surface next session
                    notify(f"loadout: could not apply settings after sync: {exc}")
                try:
                    bk = Backup(description="maintenance: links refreshed after a pull")
                    link.link_all(bk)  # every mode: pulled skills and hook scripts must be linked for merged hooks to run
                    if not bk.empty:
                        notify(f"loadout: refreshed links and copies; replaced or edited ones are in {bk.root} "
                               f"(undo: loadout restore {bk.root})")
                except Exception as exc:  # never crash in the background; surface next session
                    notify(f"loadout: could not link after sync: {exc}")
            try:
                from . import codex
                if codex.enabled() and codex.unavailable() is None:
                    bk = Backup(description="maintenance: Codex refreshed after a pull")
                    for line in codex.apply_all(bk, refresh=True, command="maintain"):
                        if codex_notice(line):
                            notify(f"loadout (Codex): {line}")
                    if not bk.empty:
                        notify(f"loadout (Codex): refreshed; replaced or edited files are in {bk.root} "
                               f"(undo: loadout restore {bk.root})")
                    for line in codex.drift():
                        notify(f"loadout: {line}")
            except Exception as exc:  # never crash in the background; surface next session
                notify(f"loadout: could not refresh Codex after sync: {exc}")
    _touch_lock()
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
    from . import adopt, duplicates, inventory, own
    try:  # Claude Code's entries only: a Codex server is never a duplicate of the Claude plugin
        items = [i for i in inventory.collect(with_versions=False) if i.kind in ("mcp", "hook") and not own.is_codex(i)]
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
    if not _acquire_lock("update", locks.foreground_wait()):
        print(locks.busy_message(LOCK))
        return 1
    try:
        return _update(yes, ask)
    finally:
        _release_lock()


def _update_plugins(claude_on: bool, codex_on: bool, yes: bool, ask: Callable[[str], str]) -> None:
    """Refresh the plugins the kit enables, in each agent that is on, after a yes, and say what changed."""
    from . import codex, out, targets
    from .jsonio import get_dict
    from .settings_merge import desired_settings
    todo = []
    if claude_on:
        installed = get_dict(load_json(paths.claude_home() / "plugins" / "installed_plugins.json"), "plugins")
        todo = [pid for pid, on in get_dict(desired_settings(), "enabledPlugins").items()
                if on and isinstance(installed.get(pid), list)
                and any(isinstance(e, dict) and e.get("scope") == "user" for e in installed[pid])]
    if codex_on and (reason := codex.unavailable()) is not None:
        print(f"Codex: {reason}; its plugins are left as they are")
        codex_on = False
    elif codex_on and not runner.have("codex"):  # extension mode: no plugins to refresh
        print(codex.PLUGINS_EXTENSION)
        codex_on = False
    if not todo and not codex_on:
        return
    where = " and ".join(([f"{len(todo)} in Claude Code"] if todo else []) + (["the Codex plugins"] if codex_on else []))
    print(f"plugins: refresh {where}")
    if not yes and ask("  refresh them? [y/N] ").strip().lower() != "y":
        print("  left as they are (run `loadout update --yes` to refresh them)")
        return
    changed = False
    for pid in todo:
        print(f"  plugin {pid}…", flush=True)
        _touch_lock()
        res = runner.run(["claude", "plugin", "update", pid, "--scope", "user"], timeout=300)
        if not res.ok:
            print(f"plugin {pid}: failed: {redact((res.stderr or res.stdout).strip()[:300])}")
        elif "already at the latest version" not in res.stdout.lower() + res.stderr.lower():
            print(f"plugin {pid}: updated")
            changed = True
    if codex_on:
        lock = codex._lock(locks.foreground_wait(), "update", _touch_lock)
        if lock is None:
            print(f"Codex: {locks.busy_message(codex.LOCK)}")
        else:
            bk = Backup(description="update: Codex plugins")
            try:
                before = codex.plugin_versions()
                codex_lines = codex.apply_plugins(bk, refresh=True, say=out.progress)
                out.end_progress()
                for line in codex_lines:
                    print(redact(line))
                    changed = changed or line.endswith(": installed")
                after = codex.plugin_versions()
            finally:
                lock.release()
            for pid in sorted(after):
                if pid in before and before[pid] != after[pid]:
                    print(f"plugin {pid}: updated")
                    changed = True
            if not bk.empty:
                print(f"backup: {bk.root}  (undo: loadout restore {bk.root})")
    if changed:
        print(targets.restart_hint())


def _update(yes: bool, ask: Callable[[str], str]) -> int:
    from . import targets
    if targets.claude_enabled():  # Codex only: no Claude Code marketplaces to refresh
        runner.run(["claude", "plugin", "marketplace", "update"], timeout=300)
    claude_on = targets.claude_enabled()
    _update_plugins(claude_on, targets.codex_enabled(), yes, ask)
    settings_path = paths.claude_home() / "settings.json"
    before = load_json(settings_path) if claude_on else {}  # Codex only: Claude Code's file is not read at all
    outdated = find_outdated()
    ran = False
    if not outdated:
        print("all tools up to date")
    for entry, local, latest in outdated:
        _touch_lock()
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
            res = runner.run(cmd, cwd=pkgmgr.run_cwd(cmd), timeout=900)
            all_ok = all_ok and res.ok
            print("  ok" if res.ok else f"  failed: {res.stderr.strip()[:300]}")
        if how == "mise":  # mise decides what is outdated (minimum_release_age): no bookkeeping of our own
            _remember_refused(entry["id"], None)
            continue
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
    if not claude_on:  # Codex only: Claude Code's settings and servers are not loadout's to fix
        return 0
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
