#!/usr/bin/env python3
"""Keep codebase-memory's graph fresh at logical change points (stdlib only; always exit 0; prints nothing).

  refresh.py                 the hook (PostToolUse on edits and Bash, Stop, SubagentStop; payload on stdin)
  refresh.py --run <root> [--now]   the detached child that re-indexes <root>

The hook only notes and decides; it never waits for an index:
  - an edit (Claude Code's file_path, Codex's apply_patch headers) of a code file in an indexed git repo is added
    to the repo's `changed` list; 20 entries refresh at once;
  - a tree-rewriting git command (checkout, switch, pull, merge, rebase, reset, stash pop/apply, cherry-pick,
    revert) refreshes at once; any other Bash command is noted, so the next Stop lets the child compare HEAD and
    the `git status --porcelain` hash with the last refresh's;
  - Stop and SubagentStop refresh when `changed` is non-empty or a Bash command was noted.
Nothing happens when codebase-memory-mcp is not on PATH, Claude Code has the server off for the folder
(mcp_guard's rules), the folder is no git repo, or codebase-memory never indexed it (a first index is
auto_index's job).

The child takes <state>/cbm-refresh/<hash>.lock (one refresh per repo; a lock older than 10 minutes is a crashed
run's), asks `index_status`, leaves a project codebase-memory's own watcher watches alone, and runs
`index_repository` (with `name` for a project indexed under another name). A busy refusal ("another index
operation") is silent; any other failure is kept in the state file's `last`, which `loadout check` shows.
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
STALE = 600  # seconds after which a lock is a crashed run's
GIT_TIMEOUT = 2  # in the hook
CHILD_GIT_TIMEOUT = 10
STATUS_TIMEOUT = 60  # every daemon-backed cli call takes ~6 s on a cold daemon
INDEX_TIMEOUT = 1800
BUSY = "another index operation"
CODE_EXT = (".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".go", ".kt", ".java", ".cs", ".rb", ".php", ".c", ".cc",
            ".cpp", ".h", ".hpp", ".swift", ".scala", ".ex", ".lua", ".sh")  # cli/loadout/searches.py's list
PATCH_FILE = re.compile(r"^\*\*\* (?:Add|Update) File: (.+?)\s*$", re.M)  # the same headers as advisor.py
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


def available(cwd: str) -> bool:
    """mcp_guard's rules (a) and (b): the binary is on PATH and Claude Code has the server on for the folder."""
    return mcp_guard.binary_on_path(SERVER) and mcp_guard.server_available(SERVER, cwd, mcp_guard._home())


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


def rewrites_tree(command: object) -> bool:
    """A git command that rewrites the working tree or HEAD (the plan's list), anywhere in the line."""
    if not isinstance(command, str) or len(command) > 10_000:
        return False
    for seg in _segments(command.replace("\n", " ; ")):
        for i, w in enumerate(seg):
            if os.path.basename(w) != "git" or (i and seg[i - 1] in NOT_A_RUN):
                continue
            rest, j = seg[i + 1:], 0
            while j < len(rest) and rest[j].startswith("-"):
                j += 2 if rest[j] in GIT_VALUE_OPTS else 1
            sub = rest[j] if j < len(rest) else None
            if sub in REWRITES or (sub == "stash" and j + 1 < len(rest) and rest[j + 1] in STASH_REWRITES):
                return True
            break
    return False


def _indexed(root: str) -> bool:
    return bool(cbm_project.project_for(root))


def _record(root: str, files: list[str], session: object) -> None:
    path = state_path(root)
    state = _load(path)
    changed = _changed(state)
    for f in files:
        if f not in changed:
            changed.append(f)
    state.update(changed=changed, root=root, session=session if isinstance(session, str) else None)
    _save(path, state)
    if len(changed) >= LIMIT:
        spawn(root)


def _note(root: str, session: object) -> None:
    path = state_path(root)
    state = _load(path)
    if state.get("noted") is True and state.get("root") == root:
        return
    state.update(noted=True, root=root, session=session if isinstance(session, str) else None)
    state.setdefault("changed", [])
    _save(path, state)


def handle(payload: dict) -> None:
    raw_cwd = payload.get("cwd")
    cwd = raw_cwd if isinstance(raw_cwd, str) and raw_cwd else os.getcwd()
    event = payload.get("hook_event_name")
    if not available(cwd):
        return
    session = payload.get("session_id")
    if event == "PostToolUse":
        tool_input = payload.get("tool_input")
        if not isinstance(tool_input, dict):
            return
        if payload.get("tool_name") == "Bash":
            root = repo_root(cwd)
            if not root or not _indexed(root):
                return
            if rewrites_tree(tool_input.get("command")):
                spawn(root, now=True)
            else:
                _note(root, session)
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
            if _indexed(root):
                _record(root, files, session)
    elif event in ("Stop", "SubagentStop"):
        root = repo_root(cwd)
        due = set()
        if root:
            state = _load(state_path(root))
            if _changed(state) or state.get("noted") is True:
                due.add(root)
        if isinstance(session, str):  # this session's edits in other repos
            try:
                for p in sorted(state_dir().glob("*.json"))[:64]:
                    st = _load(p)
                    if st.get("session") == session and _changed(st) and isinstance(st.get("root"), str):
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


def _cbm(tool: str, args: dict, timeout: float) -> tuple[int, str, str]:
    try:
        res = subprocess.run([SERVER, "cli", "--quiet", tool, json.dumps(args)], capture_output=True, text=True,
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


def _settle(root: str, done: list[str], head: str | None, status: str | None, last: dict | None) -> None:
    """Drop the refreshed files (edits that came in meanwhile stay), store the baseline and the outcome."""
    path = state_path(root)
    state = _load(path)
    state["changed"] = [f for f in _changed(state) if f not in done]
    state.update(root=root, noted=False, head=head, status=status)
    if last is not None:
        state["last"] = last
    _save(path, state)


def run(root: str, now: bool = False) -> None:
    root = os.path.normpath(root)
    name = cbm_project.project_for(root)
    if not name or not _lock(root):
        return
    try:
        state = _load(state_path(root))
        done = _changed(state)
        head, status = _snapshot(root)
        if not now and not done and head is not None and (head, status) == (state.get("head"), state.get("status")):
            _settle(root, done, head, status, None)  # a noted command moved nothing
            return
        rc, out, err = _cbm("index_status", {"project": name}, STATUS_TIMEOUT)
        info = _json_out(out)
        if rc != 0 or info.get("error") or info.get("status") != "ready":
            return  # not indexed (or busy indexing): no failure; a first index is auto_index's job
        watch = info.get("watch")
        if isinstance(watch, dict) and watch.get("watched") is True:
            _settle(root, done, head, status, None)  # codebase-memory's own watcher re-indexes it
            return
        args = {"repo_path": root}
        if name != cbm_project.default_name(root):
            args["name"] = name
        rc, out, err = _cbm("index_repository", args, INDEX_TIMEOUT)
        if BUSY in out or BUSY in err:
            return  # a refresh cbm refuses is dropped silently; the next trigger retries
        result = _json_out(out)
        if rc == 0 and not result.get("error"):
            _settle(root, done, head, status, {"at": int(time.time()), "ok": True, "error": ""})
            return
        text = (err.strip() or str(result.get("error") or "") or out.strip() or f"exit {rc}")
        state = _load(state_path(root))
        state.update(root=root, last={"at": int(time.time()), "ok": False, "error": text[:300]})
        _save(state_path(root), state)
    finally:
        try:
            lock_path(root).unlink()
        except OSError:
            pass


def main(argv: list[str]) -> int:
    try:
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
