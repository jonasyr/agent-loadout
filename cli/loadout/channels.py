"""Release channels: the stable/dev setting, release tags this machine has seen, and which one to offer."""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import maintenance, paths, runner
from .backup import Backup
from .jsonio import load_json, save_json
from .out import printable

FLOOR = (0, 2, 0)
SOAK = 3 * maintenance.DAY
KIT_MARKET = "agent-loadout"
DEFAULT_SLUG = "jonasyr/agent-loadout"
CHANNELS = ("stable", "dev")

_NUM = "(0|[1-9][0-9]*)"
_TAG = re.compile(rf"v{_NUM}\.{_NUM}\.{_NUM}", re.ASCII)
_SHA = re.compile(r"[0-9a-f]{40}")
_SLUG = re.compile(r"(?:https://github\.com/|ssh://git@github\.com/|git@github\.com:)([\w.-]+/[\w.-]+?)(?:\.git)?/?")


def _channel_path() -> Path:
    return paths.state_dir() / "channel.json"


def _releases_path() -> Path:
    return paths.state_dir() / "releases.json"


def get() -> str | None:
    try:
        name = load_json(_channel_path()).get("channel")
    except Exception:
        return None
    return name if name in CHANNELS else None


def effective() -> str:
    return get() or "dev"


def set_channel(name: str, bk: Backup | None = None) -> None:
    if name not in CHANNELS:
        raise ValueError(f"unknown channel {name!r}; use stable or dev")
    path = _channel_path()
    if bk is not None:  # manifest first, so restore returns to the old state (or to unset)
        if path.exists():
            bk.save_copy(path, "release channel")
        else:
            bk.record_created(path, "release channel")
    save_json(path, {"channel": name})


def parse_tag(name: str) -> tuple[int, int, int] | None:
    m = _TAG.fullmatch(name) if isinstance(name, str) else None
    if not m:
        return None
    version = (int(m[1]), int(m[2]), int(m[3]))
    return version if version >= FLOOR else None


def _git_env() -> dict:
    return {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never", "LC_ALL": "C"}


def remote_tags(root: Path) -> dict[str, str] | None:
    res = runner.run(["git", "-C", str(root), "ls-remote", "--tags", "origin"], timeout=60, env=_git_env())
    if not res.ok:
        return None
    tags: dict[str, str] = {}
    for line in res.stdout.splitlines():
        sha, _, ref = line.strip().partition("\t")
        if not _SHA.fullmatch(sha) or not ref.startswith("refs/tags/"):
            continue
        name = ref[len("refs/tags/"):]
        peeled = name.endswith("^{}")
        name = name[:-3] if peeled else name
        if parse_tag(name) is None:
            continue
        if peeled or name not in tags:  # the peeled commit of an annotated tag wins
            tags[name] = sha
    return tags


def _load_releases() -> dict:
    try:
        return load_json(_releases_path())
    except Exception:
        return {}


def _tags(data: dict) -> dict:
    tags = data.get("tags")
    return tags if isinstance(tags, dict) else {}


def record_seen(tags: dict[str, str], now: float) -> list[str]:
    data = _load_releases()
    known = _tags(data)
    moved: list[str] = []
    changed = False
    for name, sha in tags.items():
        if parse_tag(name) is None or not isinstance(sha, str) or not _SHA.fullmatch(sha):
            continue
        entry = known.get(name)
        if not isinstance(entry, dict):
            known[name] = {"sha": sha, "first_seen": now}
            changed = True
        elif entry.get("sha") != sha and not entry.get("moved"):
            entry["moved"] = True  # never offered again, even if it moves back
            moved.append(name)
            changed = True
    if changed:
        data["tags"] = known
        save_json(_releases_path(), data)
    return moved


def mark_notified(name: str) -> None:
    data = _load_releases()
    entry = _tags(data).get(name)
    if isinstance(entry, dict):
        entry["notified"] = True
        save_json(_releases_path(), data)


def notified(name: str) -> bool:
    entry = _tags(_load_releases()).get(name)
    return isinstance(entry, dict) and bool(entry.get("notified"))


@dataclass
class Status:
    urgent: set[str] = field(default_factory=set)
    withdrawn: dict[str, dict] = field(default_factory=dict)


def _version(text) -> str | None:
    return text if isinstance(text, str) and parse_tag("v" + text) is not None else None


def release_status(root: Path) -> Status | None:
    """The status file on origin/main; an empty Status when the file does not exist there; None when it could not
    be read (offline, a git failure, invalid JSON): the caller keeps what it knew and offers nothing."""
    import json
    env = _git_env()
    git = ["git", "-C", str(root)]
    if not runner.run([*git, "fetch", "origin", "main"], timeout=60, env=env).ok:
        return None
    res = runner.run([*git, "show", "FETCH_HEAD:release-status.json"], timeout=60, env=env)
    if not res.ok:
        missing = "does not exist" in res.stderr or "exists on disk, but not in" in res.stderr
        return Status() if missing else None
    try:
        data = json.loads(res.stdout)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    status = Status()
    urgent = data.get("urgent")
    if isinstance(urgent, list):
        status.urgent = {v for v in map(_version, urgent) if v}
    withdrawn = data.get("withdrawn")
    for item in withdrawn if isinstance(withdrawn, list) else []:
        if not isinstance(item, dict):
            continue
        version, reason = _version(item.get("version")), item.get("reason")
        if version and isinstance(reason, str) and reason.strip():
            status.withdrawn[version] = {"reason": reason, "use": _version(item.get("use"))}
    return status


def eligible(current: tuple[int, int, int] | None, now: float, status: Status) -> str | None:
    urgent = set(status.urgent) | {w["use"] for w in status.withdrawn.values() if w.get("use")}
    best: tuple[tuple[int, int, int], str] | None = None
    for name, entry in _tags(_load_releases()).items():
        version = parse_tag(name)
        if version is None or not isinstance(entry, dict) or entry.get("moved"):
            continue
        text = ".".join(map(str, version))
        if text in status.withdrawn or (current is not None and version <= current):
            continue
        first_seen = entry.get("first_seen")
        if not isinstance(first_seen, (int, float)) or now < first_seen:
            continue  # a clock that went back: not yet
        if text not in urgent and now - first_seen < SOAK:
            continue
        if best is None or version > best[0]:
            best = (version, name)
    return best[1] if best else None


def current_release(root: Path) -> str | None:
    res = runner.run(["git", "-C", str(root), "describe", "--tags", "--exact-match", "HEAD"], timeout=30)
    if not res.ok:
        return None
    name = res.stdout.strip()
    return name if parse_tag(name) else None


def kit_slug(root: Path) -> str:
    res = runner.run(["git", "-C", str(root), "remote", "get-url", "origin"], timeout=30)
    m = _SLUG.fullmatch(res.stdout.strip()) if res.ok else None
    return m[1] if m else DEFAULT_SLUG


def last_status() -> Status:
    """The release status the last daily check fetched (empty when none): `loadout check` needs no network."""
    raw = _load_releases().get("status")
    status = Status()
    if not isinstance(raw, dict):
        return status
    urgent = raw.get("urgent")
    if isinstance(urgent, list):
        status.urgent = {v for v in map(_version, urgent) if v}
    withdrawn = raw.get("withdrawn")
    for version, item in (withdrawn.items() if isinstance(withdrawn, dict) else []):
        if _version(version) and isinstance(item, dict) and isinstance(item.get("reason"), str):
            status.withdrawn[version] = {"reason": item["reason"], "use": _version(item.get("use"))}
    return status


def _store_status(status: Status) -> None:
    data = _load_releases()
    data["status"] = {"urgent": sorted(status.urgent), "withdrawn": status.withdrawn}
    save_json(_releases_path(), data)


def changelog_lines(root: Path, tag: str, limit: int = 3) -> list[str]:
    """The first bullets of the tag's `## {version}` section in its CHANGELOG.md; [] on any failure."""
    if parse_tag(tag) is None:
        return []
    git = ["git", "-C", str(root)]
    env = _git_env()
    if not runner.run([*git, "fetch", "origin", "tag", tag, "--no-tags"], timeout=60, env=env).ok:
        return []
    res = runner.run([*git, "show", f"{tag}:CHANGELOG.md"], timeout=60, env=env)
    if not res.ok:
        return []
    heading, inside, out = "## " + tag[1:], False, []
    for line in res.stdout.splitlines():
        if line.startswith("## "):
            if inside:
                break
            inside = line == heading or line.startswith(heading + " ")
        elif inside and line.lstrip().startswith(("- ", "* ")):
            text = printable(line.lstrip()[2:].strip()[:120])
            if text:
                out.append(text)
                if len(out) >= limit:
                    break
    return out


def migration_notice() -> None:
    """Once, for a machine with no channel setting yet: it follows main, and stable is one command away."""
    if _channel_path().exists() or maintenance._stamp("channel-notice").exists():
        return
    maintenance.touch("channel-notice", time.time())
    maintenance.notify("loadout now has release channels: you are on dev (main). "
                       "For tested releases only: loadout channel stable")


def check_releases(now: float) -> None:
    """The daily step: remember the release tags on origin, queue alarms for moved ones and, on stable only, one
    notice per withdrawn current release or newly offered release. Offline: nothing recorded or said."""
    root = paths.kit_root()
    tags = remote_tags(root)
    if tags is None:
        return
    for name in record_seen(tags, now):
        maintenance.notify(f"loadout: release {printable(name)} was changed after it was released; it is not "
                           "offered. Tell the maintainer.")
    if effective() != "stable":
        return
    status = release_status(root)
    if status is None:  # unknown: keep the stored status, offer nothing
        return
    _store_status(status)
    tag = current_release(root)
    current = parse_tag(tag) if tag else None
    text = tag[1:] if tag and current else None
    if text in status.withdrawn:
        data = _load_releases()
        done = data.get("withdrawn_notified")
        done = done if isinstance(done, list) else []
        if text not in done:
            info = status.withdrawn[text]
            fix = f"run loadout update (to {info['use']})" if info.get("use") else "run loadout restore"
            maintenance.notify(f"loadout: the release you run ({tag}) was withdrawn: "
                               f"{printable(info['reason'][:200])}; {fix}")
            data["withdrawn_notified"] = [*done, text]
            save_json(_releases_path(), data)
        return
    offer = eligible(current, now, status)
    if offer is None or notified(offer):
        return
    lines = changelog_lines(root, offer)
    since = f"since {text or 'a development version'}"
    detail = f"{since}: {'; '.join(lines)}" if lines else since
    maintenance.notify(f"loadout {offer[1:]} is available ({detail}); run loadout update")
    mark_notified(offer)
