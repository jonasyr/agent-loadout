"""SessionStart hook, detached daily/weekly maintenance, and `loadout update` (spec §6.4)."""
from __future__ import annotations

import json
import os
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
    # never the project folder as cwd: Windows searches it for programs
    runner.spawn_detached([sys.executable, str(paths.kit_root() / "bin" / "loadout"), "maintenance"], str(paths.home()))


def notify(text: str) -> None:
    """Queue a message for the next session start; several messages are all kept. Redacted first: a Codex line can
    carry a failed clone's stderr."""
    text = redact(text)
    path = _stamp(NOTICE)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(text.rstrip() + "\n")


def _session_steps(agent: str, source: str | None) -> str | None:
    """The agent's open "Now do this" lines for a session start, and which of them this start settles: a Claude Code
    step only at a fresh start (source "startup": resume, clear and compact keep the old plugins loaded); in Codex
    "restart" at any start and the hooks step once /hooks has approved them. What this start settles is cleared
    without being shown: the session already loaded the new plugins and servers. None when there is nothing to say."""
    from . import steps, targets
    on = targets.claude_enabled() if agent == "claude" else targets.codex_enabled()
    if agent not in steps.NAMES or not on:
        return None
    steps.settle(targets.claude_enabled(), targets.codex_enabled())  # hooks approved, rows passing, servers gone
    items = steps.pending(agent)
    if not items:
        return None
    done: set[str] = set()
    if agent == "claude" and source == "startup":  # a bootstrap step stays until its rows pass (settle)
        done = {s.id for s in items if s.id != "claude/bootstrap"}
    elif agent == "codex":
        done = {"codex/restart"}
    steps.clear(agent, done)
    lines = steps.block([s for s in items if s.id not in done], agent == "claude", agent == "codex")
    return "\n".join(lines) if lines else None


def session_start(now: float, agent: str | None = None, source: str | None = None) -> str | None:
    """The systemMessage for a session start. agent: which agent starts (an older plugin copy passes none: only the
    notice, as before); source: Claude Code's "startup", "resume", "clear" or "compact" from the hook's stdin."""
    out = None
    try:  # an entry of loadout's you changed in Codex's config.toml: yours now, said once, in this same session
        from . import codex
        for note in codex.refresh_record():
            notify(note)
    except Exception:  # never break a session start
        pass
    notice = _stamp(NOTICE)
    text = notice.read_text(encoding="utf-8").strip() if notice.exists() else None
    if text is not None:
        notice.unlink()
    try:
        extra = _session_steps(agent, source) if agent else None
    except Exception:  # a hook never breaks a session
        extra = None
    if text is not None or extra:
        out = json.dumps({"systemMessage": "\n\n".join(p for p in (text, extra) if p)})
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
    offline: str | None = None  # a network failure (redacted reason): nothing pulled, nothing recorded or said
    skipped: str | None = None  # nothing to follow ("detached HEAD", "no upstream branch"): nothing recorded or said


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


NETWORK = ("unable to access", "could not resolve", "connection timed out", "failed to connect", "timed out after")


def _refusal(code: int, stderr: str) -> tuple[str, list[str]] | None:
    """A failed `git pull --ff-only`: (reason, files git named), or None for a network failure, which is no
    refusal (nothing to fix in the checkout). Text is redacted (a remote URL can carry a token), not escaped:
    printing escapes it."""
    low = stderr.lower()
    if code == 124 or any(n in low for n in NETWORK):
        return None
    lines = stderr.splitlines()
    for i, line in enumerate(lines):
        if "would be overwritten by merge:" in line:
            files = []
            for item in lines[i + 1:]:
                if not item.startswith("\t"):
                    break
                files.append(redact(item[1:]))
            what = "untracked files" if "untracked working tree files" in line else "local changes"
            return f"{what} the pull would overwrite", files
    if "Not possible to fast-forward" in stderr or "diverg" in low:
        return "your branch and its upstream have diverged", []
    first = next((l.strip() for l in lines if l.strip()), "")
    return redact(first) or "git pull failed", []


def pull(root: Path) -> PullResult:
    """Fast-forward the checkout and let git refuse on its own: it never overwrites a local change, so a dirty
    tree is no reason to skip (untracked files and unrelated edits do not block a fast-forward). A refusal is
    recorded with the files git named and queued once as a notice."""
    if not (root / ".git").exists() and not root.is_dir():
        return PullResult()
    git = ["git", "-c", "core.quotePath=false", "-C", str(root)]
    if not runner.run(["git", "-C", str(root), "symbolic-ref", "-q", "HEAD"], timeout=30).ok:
        _record_paused(root, None)
        return PullResult(skipped="detached HEAD")  # nothing to follow
    if not runner.run(["git", "-C", str(root), "rev-parse", "--abbrev-ref", "@{u}"], timeout=30).ok:
        _record_paused(root, None)
        return PullResult(skipped="no upstream branch")  # nothing to pull
    head = ["git", "-C", str(root), "rev-parse", "HEAD"]
    before = runner.run(head, timeout=30).stdout.strip()
    # a background process has no one to answer a credential prompt (or a GCM login window); C locale for parsing
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never", "LC_ALL": "C"}
    res = runner.run([*git, "pull", "--ff-only", "-q"], timeout=120, env=env)
    if not res.ok:
        found = _refusal(res.returncode, res.stderr or "")
        if found is None:  # offline or unreachable: nothing is recorded or said; `loadout update` lists it
            text = res.stderr or res.stdout or ""
            first = next((l.strip() for l in text.splitlines() if l.strip()), "")
            return PullResult(offline=redact(first)[:300] or "the remote could not be reached")
        reason, files = found
        if _record_paused(root, {"reason": reason, "files": files, "at": time.time()}):
            if files:
                notify(f"loadout: the daily sync of {root} paused: {printable(reason)}: {', '.join(printable(f) for f in files)}; "
                       "commit or stash them, then run loadout update")
            else:
                notify(f"loadout: the daily sync of {root} paused: {printable(reason)}; resolve it, then run loadout update")
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


def _declined_path() -> Path:
    return paths.state_dir() / "declined-updates.json"


def _declined() -> dict:
    try:
        data = load_json(_declined_path())
    except Exception:
        return {}
    return {k: v for k, v in data.items() if isinstance(v, str)} if isinstance(data, dict) else {}


def decline(tool_id: str, version: tuple) -> None:
    """The person left this update out: no weekly notice until a version newer than `version` appears."""
    data = _declined()
    data[tool_id] = versions.fmt(version)
    save_json(_declined_path(), data)


def _remember_refused(tool: str, latest: tuple | None) -> None:
    data = _refused()
    if latest is None:
        data.pop(tool, None)
        declined = _declined()  # the update installed it (or mise did): the left-out note is spent
        if tool in declined:
            declined.pop(tool)
            save_json(_declined_path(), declined)
    else:
        data[tool] = versions.fmt(latest)
    save_json(_refused_path(), data)


def worth_notifying(outdated: list) -> list:
    """Drop updates a package manager already refused (e.g. mise minimum_release_age) until a newer one appears."""
    refused, declined = _refused(), _declined()

    def held(e, b):
        if e["id"] in declined and (versions.parse_version(declined[e["id"]]) or ()) >= b:
            return True  # left out by the person, mise tools too
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
                        if codex_notice(line) or codex.is_release(line):  # a release is said once, then quiet
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


def update(yes: bool, ask: Callable[[str], str], argv: list[str] | None = None) -> int:
    """`loadout update` (cli/loadout/update.py): lock, pull, restart into the pulled code, plan, apply, report."""
    from . import update as update_run
    return update_run.run(yes, ask, argv=list(argv) if argv is not None else (["--yes"] if yes else []))
