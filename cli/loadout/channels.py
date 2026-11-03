"""Release channels: the stable/dev setting, release tags this machine has seen, and which one to offer."""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import maintenance, paths, runner
from .backup import Backup, valid_branch
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


def _record_current(tag: str, sha: str) -> None:
    data = _load_releases()
    data["current"] = {"tag": tag, "sha": sha}
    save_json(_releases_path(), data)


def current_release(root: Path) -> str | None:
    """The release the kit is on: the one move_to recorded while HEAD is still its commit (no local tag ref needed),
    else the tag git describe finds exactly at HEAD."""
    rec = _load_releases().get("current")
    if isinstance(rec, dict) and parse_tag(rec.get("tag")) and _SHA.fullmatch(str(rec.get("sha"))):
        head = runner.run(["git", "-C", str(root), "rev-parse", "HEAD"], timeout=30)
        if head.ok and head.stdout.strip() == rec["sha"]:
            return rec["tag"]
    res = runner.run(["git", "-C", str(root), "describe", "--tags", "--exact-match", "HEAD"], timeout=30)
    if not res.ok:
        return None
    name = res.stdout.strip()
    return name if parse_tag(name) else None


def moved_tags() -> list[str]:
    """Release tags the daily check saw point at another commit (local state only), newest first."""
    names = [n for n, e in _tags(_load_releases()).items() if parse_tag(n) and isinstance(e, dict) and e.get("moved")]
    return sorted(names, key=parse_tag, reverse=True)


def kit_slug(root: Path) -> str:
    res = runner.run(["git", "-C", str(root), "remote", "get-url", "origin"], timeout=30)
    m = _SLUG.fullmatch(res.stdout.strip()) if res.ok else None
    return m[1] if m else DEFAULT_SLUG


def pin() -> str | None:
    """The release tag the kit's marketplaces are pinned to: the checked-out release on stable, else None."""
    if effective() != "stable":
        return None
    return current_release(paths.kit_root())


def _pinned(origin, sep: str) -> str:
    if not isinstance(origin, str):
        return origin
    tag = pin()
    return f"{origin}{sep}{tag}" if tag and origin == kit_slug(paths.kit_root()) else origin


def claude_origin(origin: str) -> str:
    """`owner/repo#tag` for the kit's own marketplace on stable (Claude Code refuses an add whose source differs
    from the settings entry), the origin unchanged otherwise."""
    return _pinned(origin, "#")


def codex_source(src: str) -> str:
    """`owner/repo@tag` for the kit's own marketplace on stable (Codex writes `ref = tag`), else unchanged."""
    return _pinned(src, "@")


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


def store_status(status: Status) -> None:
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


def alarm(moved: list[str]) -> None:
    for name in moved:
        maintenance.notify(f"loadout: release {printable(name)} was changed after it was released; it is not "
                           "offered. Tell the maintainer.")


def find_offer(root: Path, now: float, current: tuple[int, int, int] | None) -> tuple[str | None, str | None]:
    """The release to move to now (`loadout update` on stable, `loadout channel stable`), after recording the
    remote's tags and storing the fetched status (move_to checks against it): (tag, None); (None, None) when none is
    eligible; (None, why) when the tags or the status could not be read (offer nothing)."""
    tags = remote_tags(root)
    if tags is None:
        return None, "the release tags could not be read"
    alarm(record_seen(tags, now))
    status = release_status(root)
    if status is None:
        return None, "the release status could not be read"
    store_status(status)
    return eligible(current, now, status), None


def dated_release(root: Path, now: float) -> str | None:
    """dev -> stable before any release has soaked on this machine: the newest recorded, unmoved, not withdrawn
    release whose tagger date is SOAK old (the same one-time trust as a first install). Never used by update."""
    withdrawn = last_status().withdrawn
    names = sorted((n for n, e in _tags(_load_releases()).items()
                    if parse_tag(n) and isinstance(e, dict) and not e.get("moved") and n[1:] not in withdrawn),
                   key=parse_tag, reverse=True)
    git, env = ["git", "-C", str(root)], _git_env()
    for name in names:
        ref = f"refs/tags/{name}"
        if not runner.run([*git, "fetch", "origin", f"{ref}:{ref}", "--no-tags"], timeout=120, env=env).ok:
            continue  # unreachable, or a local tag of that name elsewhere: not this one
        res = runner.run([*git, "for-each-ref", "--format=%(taggerdate:unix)", ref], timeout=30, env=env)
        try:
            when = int(res.stdout.strip()) if res.ok else None
        except ValueError:
            when = None  # a lightweight tag has no tagger date
        if when is not None and when <= now - SOAK:
            return name
    return None


def stable_target(root: Path, now: float) -> tuple[str | None, str | None]:
    """The release a move from dev to stable goes to (`loadout channel stable`, `bootstrap --channel stable`): an
    eligible one, else the one-time tagger-date fallback. (tag, None); (None, None) when none is ready; (None, why)
    when the tags or the status could not be read."""
    tag, why = find_offer(root, now, None)  # on main: any release may be the one to move to
    if why:
        return None, why
    return tag or dated_release(root, now), None


def recorded(tag: str) -> str | None:
    """The commit this machine recorded for a release tag."""
    entry = _tags(_load_releases()).get(tag) if parse_tag(tag) else None
    sha = entry.get("sha") if isinstance(entry, dict) else None
    return sha if isinstance(sha, str) and _SHA.fullmatch(sha) else None


def withdrawn_notice(tag: str, info: dict) -> str:
    """What the daily check and a bootstrap re-run say when the release you run was withdrawn. Neither moves:
    the move is loadout update's, with its plan and yes."""
    fix = f"run loadout update (to {info['use']})" if info.get("use") else "run loadout restore"
    return f"the release you run ({tag}) was withdrawn: {printable(info['reason'][:200])}; {fix}"


def check_releases(now: float) -> None:
    """The daily step: remember the release tags on origin, queue alarms for moved ones and, on stable only, one
    notice per withdrawn current release or newly offered release. Offline: nothing recorded or said."""
    root = paths.kit_root()
    tags = remote_tags(root)
    if tags is None:
        return
    alarm(record_seen(tags, now))
    if effective() != "stable":
        return
    status = release_status(root)
    if status is None:  # unknown: keep the stored status, offer nothing
        return
    store_status(status)
    tag = current_release(root)
    current = parse_tag(tag) if tag else None
    text = tag[1:] if tag and current else None
    if text in status.withdrawn:
        data = _load_releases()
        done = data.get("withdrawn_notified")
        done = done if isinstance(done, list) else []
        if text not in done:
            maintenance.notify("loadout: " + withdrawn_notice(tag, status.withdrawn[text]))
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



class CheckFailed(Exception):
    """git could not tell whether the kit checkout has local work: the caller refuses (fail closed)."""


def local_changes(root: Path, base: str) -> list[str]:
    """What a checkout would leave behind or fight with: tracked edits (untracked files never block; git refuses
    itself when one is in the way) and the commits not reachable from `base` (`--tags` or `origin/main`).
    Raises CheckFailed when git cannot answer."""
    git, env = ["git", "-C", str(root)], _git_env()
    out = []
    res = runner.run([*git, "status", "--porcelain", "--untracked-files=no"], timeout=60, env=env)
    if not res.ok:
        raise CheckFailed(root)
    for line in res.stdout.splitlines():
        if len(line) > 3 and not line.startswith("??"):
            out.append(printable(line[3:]))
    res = runner.run([*git, "log", "--format=%h %s", "HEAD", "--not", base], timeout=60, env=env)
    if not res.ok:
        raise CheckFailed(root)
    out += [f"commit {printable(line)}" for line in res.stdout.splitlines() if line.strip()]
    return out


def _dirty(root: Path, base: str) -> str | None:
    """The refusal text when the checkout has local work or cannot be checked; None when it is clean."""
    try:
        found = local_changes(root, base)
    except CheckFailed:
        return f"could not check {root} for local changes; nothing was moved"
    if found:
        return (f"local changes in {root}: {', '.join(found)}; commit, stash or remove them, "
                "or run loadout from a clean checkout")
    return None


def _record_undo(root: Path, bk: Backup) -> str | None:
    """Record how to return to where the checkout is now: its branch when it is on one, else its commit."""
    git = ["git", "-C", str(root)]
    old = runner.run([*git, "rev-parse", "HEAD"], timeout=30).stdout.strip()
    if not _SHA.fullmatch(old):
        return f"could not read the current commit of {root}"
    res = runner.run([*git, "symbolic-ref", "-q", "--short", "HEAD"], timeout=30)
    branch = res.stdout.strip() if res.ok else ""
    undo = [*git, "switch", branch] if valid_branch(branch) else [*git, "checkout", "--detach", old]
    bk.record_command("kit checkout", undo)
    return None


def _failed(res, what: str) -> str:
    found = maintenance._refusal(res.returncode, res.stderr or "")
    if found is None:
        first = next((l.strip() for l in (res.stderr or res.stdout or "").splitlines() if l.strip()), "")
        return f"{what} failed: {printable(maintenance.redact(first))[:300] or 'the remote could not be reached'}"
    reason, files = found
    return f"{printable(reason)}: {', '.join(map(printable, files))}" if files else printable(reason)


def _verify_release(tag: str) -> tuple[str | None, str | None]:
    """(recorded commit, None) for a release this machine saw and may still offer; (None, why not) otherwise."""
    entry = _tags(_load_releases()).get(tag) if parse_tag(tag) else None
    if not isinstance(entry, dict) or not _SHA.fullmatch(str(entry.get("sha"))):
        return None, f"{printable(str(tag))} is not a release this machine has seen"
    if entry.get("moved"):
        return None, f"release {tag} was changed after it was released; not moved"
    if tag[1:] in last_status().withdrawn:
        return None, f"release {tag} was withdrawn; not moved"
    return entry["sha"], None


def move_to(root: Path, tag: str, bk: Backup, base: str = "--tags") -> str | None:
    """Check out a recorded, unmoved, not withdrawn release (detached, at the verified commit). None on success,
    else why not. `base` is what local commits are measured against (`--tags` on stable, `origin/main` from dev).
    The undo is recorded before the checkout moves."""
    git, env = ["git", "-C", str(root)], _git_env()
    expected, why = _verify_release(tag)
    if why:
        return why
    if base == "origin/main":
        res = runner.run([*git, "fetch", "origin", "main"], timeout=120, env=env)
        if not res.ok:
            return _failed(res, "fetching main")
    problem = _dirty(root, base)
    if problem:
        return problem
    res = runner.run([*git, "fetch", "origin", f"refs/tags/{tag}", "--no-tags"], timeout=120, env=env)
    if not res.ok:
        return _failed(res, f"fetching {tag}")
    got = runner.run([*git, "rev-parse", "FETCH_HEAD^{commit}"], timeout=30, env=env).stdout.strip()
    if got != expected:
        return f"release {tag} does not match what this machine recorded; not moved"
    problem = _record_undo(root, bk)
    if problem:
        return problem
    res = runner.run([*git, "checkout", "--detach", expected], timeout=120, env=env)
    if not res.ok:
        return _failed(res, f"checking out {tag}")
    _record_current(tag, expected)  # the release identity, whether or not a local tag ref exists
    return None


def move_to_dev(root: Path, bk: Backup) -> str | None:
    """Back onto main, fast-forwarded to origin. None on success, else why not."""
    git, env = ["git", "-C", str(root)], _git_env()
    res = runner.run([*git, "fetch", "origin", "main"], timeout=120, env=env)
    if not res.ok:
        return _failed(res, "fetching main")
    problem = _dirty(root, "origin/main")
    if problem:
        return problem
    problem = _record_undo(root, bk)
    if problem:
        return problem
    local = runner.run([*git, "rev-parse", "--verify", "--quiet", "refs/heads/main"], timeout=30, env=env).ok
    switch = ["switch", "main"] if local else ["switch", "-c", "main", "--track", "origin/main"]
    res = runner.run([*git, *switch], timeout=120, env=env)
    if not res.ok:
        return _failed(res, "switching to main")
    res = runner.run([*git, "pull", "--ff-only"], timeout=120, env=env)
    return None if res.ok else _failed(res, "pulling main")
