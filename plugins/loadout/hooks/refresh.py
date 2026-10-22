#!/usr/bin/env python3
"""Keep codebase-memory's graph fresh at logical change points (stdlib only; always exit 0; prints nothing).

  refresh.py                 the hook (PostToolUse on edits and Bash, Stop, SubagentStop; payload on stdin)
  refresh.py --run <root> [--now]   the detached child that re-indexes <root>

The hook only notes and decides; it never waits for an index:
  - an edit (Claude Code's file_path, Codex's apply_patch headers, deleted and moved files too) of a code file in
    an indexed git repo is added to the repo's `changed` list (at most 20, then a `more` mark); 20 entries
    refresh at once;
  - a tree-rewriting git command (checkout, switch, pull, merge, rebase, reset, stash pop/apply, cherry-pick,
    revert) refreshes at once; any other Bash command is noted, so the next Stop lets the child compare HEAD and
    the `git status --porcelain` hash with the last refresh's;
  - Stop and SubagentStop refresh when `changed` is non-empty, `more` is set or a Bash command was noted;
  - after a failed refresh, the mid-turn triggers wait 10 minutes; Stop still retries.
Nothing happens when codebase-memory-mcp is not on PATH, Claude Code has the server off for the folder
(mcp_guard's rules), the folder is no git repo, or codebase-memory never indexed it (a first index is
auto_index's job). That verdict and the project name are kept in the repo's state for 10 minutes. A new state
file prunes those of gone repos and those idle for 30 days.

The child takes <state>/cbm-refresh/<hash>.lock (one refresh per repo; a lock older than the longest refresh is a
crashed run's; a child removes only its own lock), asks `index_status`, leaves a project codebase-memory's own
watcher watches alone, and runs `index_repository` (with `--name` for a project indexed under another name). A
busy refusal ("another index operation") is silent; any other failure is kept in the state file's `last`, which
`loadout check` shows; a repo cbm watches or no longer indexes drops it.
See docs/reference/hooks.md."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cbm_project  # noqa: E402  (the project name of a folder: one home in the hook folder)
import mcp_guard  # noqa: E402  (whether codebase-memory is there for the agent: one home in the hook folder)

SERVER = "codebase-memory-mcp"
MAX_INPUT = 200_000
LIMIT = 20  # changed code files that refresh mid-turn
MAX_FILES = 50  # files of one patch that are looked at
GIT_TIMEOUT = 2  # in the hook
CHILD_GIT_TIMEOUT = 10
STATUS_TIMEOUT = 60  # every daemon-backed cli call takes ~6 s on a cold daemon
INDEX_TIMEOUT = 1800
STALE = STATUS_TIMEOUT + INDEX_TIMEOUT + 300  # seconds after which a lock is a crashed run's, never a running one's
CACHE_TTL = 600  # the hook keeps the project name and the guard's verdict this long in the repo's state
HOOK_MAX_DBS = 8  # index files the hook reads to find a project indexed under another name (the child reads 64)
BACKOFF = 600  # after a failed refresh, no mid-turn trigger for this long; Stop still retries
KEEP_DAYS = 30
MAX_STATE_FILES = 256
BUSY = "another index operation"
CODE_EXT = (".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".go", ".kt", ".java", ".cs", ".rb", ".php", ".c", ".cc",
            ".cpp", ".h", ".hpp", ".swift", ".scala", ".ex", ".lua", ".sh")  # cli/loadout/searches.py's list
# advisor.py's headers plus the files a patch deletes or moves (to): they change the graph too
PATCH_FILE = re.compile(r"^\*\*\* (?:(?:Add|Update|Delete) File|Move to): (.+?)\s*$", re.M)
REWRITES = {"checkout", "switch", "pull", "merge", "rebase", "reset", "cherry-pick", "revert"}
STASH_REWRITES = {"pop", "apply"}
GIT_VALUE_OPTS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
PUNCTUATION = set(";&|()")
NOT_A_RUN = {"echo", "printf", "#"}


def state_dir() -> Path:
    """The same rule as loadout's paths.state_dir() (this hook cannot import loadout)."""
    home = os.environ.get("HOME") or os.environ.get("USERPROFILE") or str(Path.home())
    base = os.environ.get("XDG_STATE_HOME", "")
    root = Path(base) if base and Path(base).is_absolute() else Path(home) / ".local" / "state"
    return root / "loadout" / "cbm-refresh"


def _key(root: str) -> str:
    return hashlib.sha256(root.encode("utf-8")).hexdigest()[:16]


def state_path(root: str) -> Path:
    return state_dir() / f"{_key(root)}.json"


def lock_path(root: str) -> Path:
    return state_dir() / f"{_key(root)}.lock"


def _load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(path: Path, data: dict) -> None:
    # loadout's state folder is private (0700), like the CLI keeps it; created here when the hook runs first
    path.parent.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.mkdir(mode=0o700, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    os.replace(tmp, path)


def _save_state(root: str, state: dict) -> None:
    """Save a repo's state; a new state file first prunes those of gone repos and those idle for 30 days."""
    path = state_path(root)
    new = not path.exists()
    _save(path, state)
    if new:
        _clean(path)


def _clean(keep: Path) -> None:
    cutoff = time.time() - KEEP_DAYS * 86400
    try:
        entries = sorted(keep.parent.glob("*.json"))[:MAX_STATE_FILES]
    except OSError:
        return
    for p in entries:
        if p == keep:
            continue
        try:
            root = _load(p).get("root")
            if p.stat().st_mtime < cutoff or not isinstance(root, str) or not os.path.isdir(root):
                p.unlink()
        except OSError:
            pass


def _failed_recently(state: dict) -> bool:
    last = state.get("last")
    at = last.get("at") if isinstance(last, dict) else None
    return (isinstance(last, dict) and last.get("ok") is False and isinstance(at, (int, float))
            and time.time() - at < BACKOFF)


def _changed(state: dict) -> list[str]:
    v = state.get("changed")
    return [p for p in v if isinstance(p, str)] if isinstance(v, list) else []


def _git(args: list[str], cwd: str, timeout: float) -> str | None:
    try:
        res = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout,
                             stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return res.stdout if res.returncode == 0 else None


def repo_root(folder: str) -> str | None:
    out = _git(["rev-parse", "--show-toplevel"], folder, GIT_TIMEOUT)
    root = out.strip() if out else ""
    return os.path.normpath(root) if root else None


AGENT = "claude"  # `--agent codex` from codex.json: Codex's own switch, never Claude Code's files


def available(cwd: str) -> bool:
    """mcp_guard's rules (a) and (b) for the agent that runs this hook."""
    return mcp_guard.available(SERVER, AGENT, cwd, mcp_guard._home())


def spawn(root: str, now: bool = False) -> None:
    """Start `refresh.py --run <root>` detached; never waited for."""
    argv = [sys.executable, str(Path(__file__).resolve()), "--run", root, *(["--now"] if now else [])]
    kwargs: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
                    "close_fds": True, "cwd": root}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(argv, **kwargs)


# --- the hook ---------------------------------------------------------------------------------------------------

def edited_files(payload: dict, tool_input: dict) -> list[str]:
    """The files an edit wrote: Claude Code names one (file_path); a Codex apply_patch names them in its headers,
    relative to the session's folder (cwd)."""
    names = PATCH_FILE.findall(tool_input["command"]) if isinstance(tool_input.get("command"), str) else []
    if isinstance(tool_input.get("file_path"), str):
        names.append(tool_input["file_path"])
    cwd = payload.get("cwd")
    out = []
    for n in names[:MAX_FILES]:
        if not os.path.isabs(n) and isinstance(cwd, str):
            n = os.path.join(cwd, n)
        if os.path.isabs(n):
            out.append(os.path.normpath(n))
    return out


def _segments(command: str) -> list[list[str]]:
    """The words of each simple command in a shell line (split at ;, &&, ||, |, &, parentheses)."""
    try:
        lex = shlex.shlex(command, posix=True, punctuation_chars=";&|()")
        lex.whitespace_split = True
        lex.commenters = ""
        words = list(lex)
    except ValueError:
        words = command.split()
    out: list[list[str]] = [[]]
    for w in words:
        if w and set(w) <= PUNCTUATION:
            out.append([])
        else:
            out[-1].append(w)
    return [s for s in out if s]


def rewrite_dir(command: object, cwd: str) -> str | None:
    """The folder a tree-rewriting git command (the plan's list) runs in: cwd, moved by an earlier `cd DIR` in the
    line and by `git -C DIR`; None when the line rewrites nothing."""
    if not isinstance(command, str) or len(command) > 10_000:
        return None
    here = cwd
    for seg in _segments(command.replace("\n", " ; ")):
        if seg[:1] == ["cd"] and len(seg) > 1:
            here = os.path.join(here, os.path.expanduser(seg[1]))
            continue
        for i, w in enumerate(seg):
            if os.path.basename(w) != "git" or (i and seg[i - 1] in NOT_A_RUN):
                continue
            rest, j, target = seg[i + 1:], 0, here
            while j < len(rest) and rest[j].startswith("-"):
                if rest[j] == "-C" and j + 1 < len(rest):
                    target = os.path.join(target, os.path.expanduser(rest[j + 1]))
                j += 2 if rest[j] in GIT_VALUE_OPTS else 1
            sub = rest[j] if j < len(rest) else None
            if sub in REWRITES or (sub == "stash" and j + 1 < len(rest) and rest[j + 1] in STASH_REWRITES):
                return os.path.normpath(target)
            break
    return None


def rewrites_tree(command: object) -> bool:
    """A git command that rewrites the working tree or HEAD (the plan's list), anywhere in the line."""
    return rewrite_dir(command, ".") is not None


def _open(root: str, cwd: str) -> dict | None:
    """The repo's state when codebase-memory is there for it (on PATH, on for the folder, the repo indexed), else
    None. The verdict and the project name are kept in the state for CACHE_TTL, so most hook calls neither parse
    ~/.claude.json nor read index files."""
    state = _load(state_path(root))
    cache = state.get("cache")
    now = time.time()
    if (isinstance(cache, dict) and cache.get("cwd") == cwd and cache.get("agent") == AGENT
            and isinstance(cache.get("at"), (int, float))
            and 0 <= now - cache["at"] < CACHE_TTL):
        return state if cache.get("ok") is True else None
    name = cbm_project.project_for(root, max_dbs=HOOK_MAX_DBS) if available(cwd) else None
    state.update(root=root, cache={"at": now, "cwd": cwd, "agent": AGENT, "ok": bool(name), "name": name})
    state.setdefault("changed", [])
    _save_state(root, state)
    return state if name else None


def _session(state: dict, session: object) -> None:
    state["session"] = session if isinstance(session, str) else None


def _record(root: str, state: dict, files: list[str], session: object) -> None:
    changed = _changed(state)
    touched = state.get("touched") if isinstance(state.get("touched"), dict) else {}
    now = time.time()
    for f in files:
        if f in changed:
            touched[f] = now  # edited again: a refresh that began before now must keep it
            continue
        touched[f] = now
        if len(changed) < LIMIT:
            changed.append(f)
        else:
            state["more"] = time.time()  # more than LIMIT files changed: the list stops growing
    state["changed"] = changed
    state["touched"] = {k: v for k, v in touched.items() if k in changed}
    _session(state, session)
    _save_state(root, state)
    if len(changed) >= LIMIT and not _failed_recently(state):
        spawn(root)


def _note(root: str, state: dict, session: object, at: float | None = None) -> None:
    """Remember a shell command for the next Stop; `at` (a tree rewrite) also keeps it past a refresh that
    started before it, so a refresh still running cannot settle it away."""
    state["noted"] = True
    state["noted_at"] = at if at is not None else time.time()  # a refresh that began before this keeps it
    _session(state, session)
    _save_state(root, state)


def handle(payload: dict) -> None:
    raw_cwd = payload.get("cwd")
    cwd = raw_cwd if isinstance(raw_cwd, str) and raw_cwd else os.getcwd()
    event = payload.get("hook_event_name")
    session = payload.get("session_id")
    if event == "PostToolUse":
        tool_input = payload.get("tool_input")
        if not isinstance(tool_input, dict):
            return
        if payload.get("tool_name") == "Bash":
            target = rewrite_dir(tool_input.get("command"), cwd)
            where = target if target is not None and os.path.isdir(target) else cwd  # an unknown dir: the session's
            root = repo_root(where)  # `git -C ../other checkout` rewrites ../other, not the session's repo
            state = _open(root, where) if root else None
            if state is None:
                return
            if target is not None:
                _note(root, state, session, at=time.time())  # first: a refresh still running cannot drop it
                if not _failed_recently(state):
                    spawn(root, now=True)
            else:
                _note(root, state, session)  # after a recent failure, the rewrite waits for Stop
            return
        by_root: dict[str, list[str]] = {}
        roots: dict[str, str | None] = {}
        for f in edited_files(payload, tool_input):
            if not f.endswith(CODE_EXT):
                continue
            folder = os.path.dirname(f)
            while folder and not os.path.isdir(folder) and os.path.dirname(folder) != folder:
                folder = os.path.dirname(folder)  # a new file in a new folder: its nearest existing parent
            if folder not in roots:
                roots[folder] = repo_root(folder)
            root = roots[folder]
            if root and (f == root or f.startswith(root.rstrip(os.sep) + os.sep)):
                by_root.setdefault(root, []).append(f)
        for root, files in by_root.items():
            state = _open(root, cwd)
            if state is not None:
                _record(root, state, files, session)
    elif event in ("Stop", "SubagentStop"):
        root = repo_root(cwd)
        due = set()
        if root:
            state = _load(state_path(root))
            if (_changed(state) or state.get("more") or state.get("noted") is True) and _open(root, cwd) is not None:
                due.add(root)
        if isinstance(session, str):  # this session's edits in other repos
            try:
                for p in sorted(state_dir().glob("*.json"))[:64]:
                    st = _load(p)
                    pending = _changed(st) or st.get("more") or st.get("noted") is True
                    if st.get("session") == session and pending and isinstance(st.get("root"), str):
                        due.add(st["root"])
            except OSError:
                pass
        for r in sorted(due):
            spawn(r)


# --- the child --------------------------------------------------------------------------------------------------

def _lock(root: str) -> bool:
    path = lock_path(root)
    path.parent.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.mkdir(mode=0o700, exist_ok=True)
    for _ in range(2):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            try:
                if time.time() - path.stat().st_mtime > STALE:
                    path.unlink()
                    continue
            except OSError:
                pass
            return False
        with os.fdopen(fd, "w") as fh:
            fh.write(str(os.getpid()))
        return True
    return False


def _cbm(tool: str, flags: list[str], timeout: float) -> tuple[int, str, str]:
    """One cbm tool through its CLI with flags (cbm 0.12 deprecates raw JSON arguments)."""
    try:
        res = subprocess.run([SERVER, "cli", "--quiet", tool, *flags], capture_output=True, text=True,
                             timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return -1, "", f"{tool} timed out after {int(timeout)} s"
    except (OSError, subprocess.SubprocessError, ValueError) as e:
        return -1, "", f"{tool} did not start: {e}"
    return res.returncode, res.stdout or "", res.stderr or ""


def _json_out(text: str) -> dict:
    start = text.find("{")
    try:
        data = json.loads(text[start:]) if start >= 0 else None
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _snapshot(root: str) -> tuple[str | None, str | None]:
    head = _git(["rev-parse", "HEAD"], root, CHILD_GIT_TIMEOUT)
    status = _git(["status", "--porcelain"], root, CHILD_GIT_TIMEOUT)
    return (head.strip() if head else None,
            hashlib.sha256(status.encode("utf-8")).hexdigest() if status is not None else None)


def _settle(root: str, done: list[str], head: str | None, status: str | None, last: dict | None,
            started: float, clear: bool = False) -> None:
    """Drop the refreshed files (edits that came in meanwhile stay), store the baseline and the outcome; clear:
    drop a failure that no longer holds (codebase-memory watches the repo itself)."""
    path = state_path(root)
    state = _load(path)
    touched = state.get("touched") if isinstance(state.get("touched"), dict) else {}
    later = {f for f, t in touched.items() if isinstance(t, (int, float)) and t > started}
    state["changed"] = [f for f in _changed(state) if f not in done or f in later]  # edits after the start stay
    state["touched"] = {f: t for f, t in touched.items() if f in state["changed"]}
    more = state.get("more")
    if not (isinstance(more, (int, float)) and more > started):
        state.pop("more", None)  # an overflow from before this refresh is covered by it
    noted_at = state.get("noted_at")
    if isinstance(noted_at, (int, float)) and noted_at > started:
        state.update(root=root, head=head, status=status)  # a rewrite after this refresh began: Stop runs again
    else:
        state.pop("noted_at", None)
        state.update(root=root, noted=False, head=head, status=status)
    if last is not None:
        state["last"] = last
    elif clear:
        state.pop("last", None)
    _save(path, state)


def _clear_failure(root: str) -> None:
    """A repo codebase-memory no longer has (or no longer indexes): its old failure is no failure any more."""
    path = state_path(root)
    state = _load(path)
    if isinstance(state.get("last"), dict) and state["last"].get("ok") is False:
        state.pop("last")
        _save(path, state)


def _unlock(root: str) -> None:
    """Remove the lock only while it is ours: a lock taken over meanwhile belongs to another child."""
    path = lock_path(root)
    try:
        if path.read_text(encoding="utf-8").strip() == str(os.getpid()):
            path.unlink()
    except OSError:
        pass


def run(root: str, now: bool = False) -> None:
    root = os.path.normpath(root)
    name = cbm_project.project_for(root)
    if not name:
        _clear_failure(root)
        return
    if not _lock(root):
        return
    try:
        started = time.time()
        state = _load(state_path(root))
        done = _changed(state)
        head, status = _snapshot(root)
        if not now and not done and head is not None and (head, status) == (state.get("head"), state.get("status")):
            _settle(root, done, head, status, None, started)  # a noted command moved nothing
            return
        rc, out, err = _cbm("index_status", ["--project", name, "--format", "json"], STATUS_TIMEOUT)  # else a tree
        info = _json_out(out)
        if rc != 0 or info.get("error") or info.get("status") != "ready":
            _clear_failure(root)
            return  # not indexed (or busy indexing): no failure; a first index is auto_index's job
        watch = info.get("watch")
        if isinstance(watch, dict) and watch.get("watched") is True:
            _settle(root, done, head, status, None, started, clear=True)  # cbm's own watcher re-indexes it
            return
        flags = ["--repo-path", root]
        if name != cbm_project.default_name(root):
            flags += ["--name", name]
        rc, out, err = _cbm("index_repository", flags, INDEX_TIMEOUT)
        if BUSY in out or BUSY in err:
            return  # a refresh cbm refuses is dropped silently; the next trigger retries
        result = _json_out(out)
        if rc == 0 and not result.get("error"):
            _settle(root, done, head, status, {"at": int(time.time()), "ok": True, "error": ""}, started)
            return
        text = (err.strip() or str(result.get("error") or "") or out.strip() or f"exit {rc}")
        state = _load(state_path(root))
        state.update(root=root, last={"at": int(time.time()), "ok": False, "error": text[:300]})
        _save(state_path(root), state)
    finally:
        _unlock(root)


def main(argv: list[str]) -> int:
    global AGENT
    try:
        if argv[:1] == ["--agent"] and len(argv) >= 2:
            AGENT, argv = argv[1], argv[2:]
        if len(argv) >= 2 and argv[0] == "--run":
            run(argv[1], now="--now" in argv[2:])
            return 0
        raw = sys.stdin.read(MAX_INPUT + 1)
        if len(raw) > MAX_INPUT:
            return 0
        payload = json.loads(raw)
        if isinstance(payload, dict):
            handle(payload)
    except Exception:  # a hook must never break a session
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
