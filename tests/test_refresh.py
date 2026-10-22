"""refresh.py: re-indexes a codebase-memory project at the end of a turn, after a tree-rewriting git command and
after 20 changed code files, in a detached child, never blocking the agent. Stub `git` and `codebase-memory-mcp`
on a temporary PATH record their argv; the hook and its `--run` child are called in-process, except for the one
test that measures the real hook process."""
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[1] / "plugins" / "loadout"
SCRIPT = PLUGIN / "hooks" / "refresh.py"
pytestmark = pytest.mark.skipif(os.name == "nt", reason="stub executables are shell scripts")

GIT = """#!/bin/sh
echo "git $*" >> "$STUB/log"
case "$*" in
  *"rev-parse --show-toplevel"*) [ -f "$STUB/root" ] && cat "$STUB/root" && exit 0; exit 128;;
  *"rev-parse HEAD"*) cat "$STUB/head";;
  *"status --porcelain"*) cat "$STUB/porcelain" 2>/dev/null;;
esac
"""
CBM = """#!/bin/sh
echo "cbm $*" >> "$STUB/log"
[ -f "$STUB/sleep" ] && sleep "$(cat "$STUB/sleep")"
case "$3" in
  index_status)  # like cbm 0.12.1: JSON only with --format json (the default is a tree), flags as cbm takes them
    case "$*" in *"--project "*" --format json"*) cat "$STUB/status.json";; *) echo "project: p"; echo "status: ready";; esac
    exit "$(cat "$STUB/status.rc" 2>/dev/null || echo 0)";;
  index_repository) cat "$STUB/index.out" 2>/dev/null; [ -f "$STUB/index.err" ] && cat "$STUB/index.err" >&2
                    exit "$(cat "$STUB/index.rc" 2>/dev/null || echo 0)";;
esac
"""
READY = {"project": "p", "status": "ready", "watch": {"watched": False, "strategy": "git"}}


def _load():
    spec = importlib.util.spec_from_file_location("refresh_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def env(tmp_path, fake_home, monkeypatch):
    stub, bindir, repo, cache = tmp_path / "stub", tmp_path / "bin", tmp_path / "repo", tmp_path / "cache"
    for d in (stub, bindir, repo, cache):
        d.mkdir()
    for name, text in (("git", GIT), ("codebase-memory-mcp", CBM)):
        (bindir / name).write_text(text)
        (bindir / name).chmod(0o755)
    (stub / "root").write_text(f"{repo}\n")
    (stub / "head").write_text("aaa\n")
    (stub / "porcelain").write_text("")
    (stub / "status.json").write_text(json.dumps(READY))
    default = str(repo).lstrip("/").replace("/", "-")
    (cache / f"{default}.db").write_bytes(b"")
    monkeypatch.setenv("STUB", str(stub))
    monkeypatch.setenv("CBM_CACHE_DIR", str(cache))
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}/usr/bin:/bin")
    mod = _load()
    spawned = []
    monkeypatch.setattr(mod, "spawn", lambda root, now=False: spawned.append((root, now)))
    return {"mod": mod, "spawned": spawned, "stub": stub, "repo": repo, "cache": cache, "home": fake_home,
            "default": default, "bin": bindir}


def _log(env):
    p = env["stub"] / "log"
    return p.read_text().splitlines() if p.exists() else []


def _indexes(env):
    return [line for line in _log(env) if line.startswith("cbm cli --quiet index_repository")]


def _edit(env, path, tool="Edit"):
    env["mod"].handle({"session_id": "s1", "hook_event_name": "PostToolUse", "tool_name": tool,
                       "cwd": str(env["repo"]), "tool_input": {"file_path": str(path)}})


def _bash(env, command):
    env["mod"].handle({"session_id": "s1", "hook_event_name": "PostToolUse", "tool_name": "Bash",
                       "cwd": str(env["repo"]), "tool_input": {"command": command}})


def _stop(env, event="Stop"):
    env["mod"].handle({"session_id": "s1", "hook_event_name": event, "cwd": str(env["repo"])})


def _state(env):
    files = list((env["home"] / ".local" / "state" / "loadout" / "cbm-refresh").glob("*.json"))
    assert len(files) <= 1
    return json.loads(files[0].read_text()) if files else None


def test_edit_then_stop_triggers_one_refresh(env):
    _edit(env, env["repo"] / "a.py")
    _edit(env, env["repo"] / "a.py")
    _edit(env, env["repo"] / "README.md")  # not code
    assert env["spawned"] == [] and _state(env)["changed"] == [str(env["repo"] / "a.py")]
    _stop(env)
    assert env["spawned"] == [(str(env["repo"]), False)]
    env["mod"].run(str(env["repo"]))
    assert len(_indexes(env)) == 1
    assert _indexes(env) == [f"cbm cli --quiet index_repository --repo-path {env['repo']}"]  # no name, no mode
    st = _state(env)
    assert st["changed"] == [] and st["head"] == "aaa" and st["last"]["ok"] is True


def test_subagent_stop_triggers_too(env):
    _edit(env, env["repo"] / "a.py", tool="Write")
    _stop(env, "SubagentStop")
    assert env["spawned"] == [(str(env["repo"]), False)]


def test_no_change_no_refresh(env):
    _stop(env)
    assert env["spawned"] == []
    _edit(env, env["repo"] / "a.py")
    _stop(env)
    env["mod"].run(str(env["repo"]))  # the baseline: HEAD and status after this refresh
    _bash(env, "ls -la")  # might have changed files: the next Stop compares HEAD and status
    _stop(env)
    assert len(env["spawned"]) == 2
    env["mod"].run(str(env["repo"]))
    assert len(_indexes(env)) == 1  # nothing moved
    _bash(env, "make gen")
    (env["stub"] / "porcelain").write_text(" M gen.py\n")
    _stop(env)
    env["mod"].run(str(env["repo"]))
    assert len(_indexes(env)) == 2


@pytest.mark.parametrize("command,now", [("git checkout -b x", True), ("git switch main", True),
                                         ("git pull --rebase", True), ("git stash pop", True),
                                         ("cd sub && git -C . reset --hard HEAD~1", True),
                                         ("git status", False), ("git log --oneline", False),
                                         ("git stash list", False), ("echo git checkout x", False)])
def test_git_checkout_triggers_now(env, command, now):
    _bash(env, command)
    assert env["spawned"] == ([(str(env["repo"]), True)] if now else [])


def test_git_rewrite_refreshes_without_comparing(env):
    env["mod"].run(str(env["repo"]), now=True)  # `git checkout -b x` moves no file and no HEAD sha
    assert len(_indexes(env)) == 1


def test_twenty_files_trigger_mid_turn(env):
    for i in range(19):
        _edit(env, env["repo"] / f"m{i}.py")
    assert env["spawned"] == []
    _edit(env, env["repo"] / "m19.py")
    assert env["spawned"] == [(str(env["repo"]), False)]


def test_refresh_skips_unindexed_repo(env):
    (env["cache"] / f"{env['default']}.db").unlink()
    _edit(env, env["repo"] / "a.py")
    _stop(env)
    assert env["spawned"] == [] and _state(env) is None
    env["mod"].run(str(env["repo"]))
    assert not [line for line in _log(env) if line.startswith("cbm")]


def test_index_status_error_records_no_failure(env):
    (env["stub"] / "status.json").write_text('{"error": "project not found"}')
    (env["stub"] / "status.rc").write_text("1")
    _edit(env, env["repo"] / "a.py")
    env["mod"].run(str(env["repo"]))
    assert _indexes(env) == [] and _state(env).get("last") is None


def test_watched_project_is_left_to_codebase_memory(env):
    (env["stub"] / "status.json").write_text(json.dumps({**READY, "watch": {"watched": True}}))
    _edit(env, env["repo"] / "a.py")
    env["mod"].run(str(env["repo"]))
    assert _indexes(env) == [] and _state(env)["changed"] == []


def test_custom_project_name_is_passed(env):
    import sqlite3
    (env["cache"] / f"{env['default']}.db").unlink()
    con = sqlite3.connect(env["cache"] / "mine.db")
    con.execute("create table projects(name text, indexed_at text, root_path text)")
    con.execute("insert into projects values ('mine', 'now', ?)", (str(env["repo"]),))
    con.commit()
    con.close()
    _edit(env, env["repo"] / "a.py")
    env["mod"].run(str(env["repo"]))
    assert any("--project mine --format json" in line for line in _log(env) if "index_status" in line)
    assert _indexes(env) == [f"cbm cli --quiet index_repository --repo-path {env['repo']} --name mine"]


def test_refresh_runs_once_under_lock(env):
    _edit(env, env["repo"] / "a.py")
    mod = env["mod"]
    lock = mod.lock_path(str(env["repo"]))
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("123")
    mod.run(str(env["repo"]))
    assert _indexes(env) == []
    old = time.time() - 11 * 60  # a lock older than 10 minutes is a crashed run's
    os.utime(lock, (old, old))
    mod.run(str(env["repo"]))
    assert len(_indexes(env)) == 1 and not lock.exists()


def test_busy_index_is_silent(env):
    (env["stub"] / "index.err").write_text("error: another index operation for this repo is active\n")
    (env["stub"] / "index.rc").write_text("1")
    _edit(env, env["repo"] / "a.py")
    env["mod"].run(str(env["repo"]))
    st = _state(env)
    assert len(_indexes(env)) == 1 and st.get("last") is None and st["changed"] == [str(env["repo"] / "a.py")]


def test_failure_is_recorded_and_check_shows_it(env):
    from loadout import check
    assert check._cbm_refresh() == []
    (env["stub"] / "index.err").write_text("boom: disk full\n")
    (env["stub"] / "index.rc").write_text("2")
    _edit(env, env["repo"] / "a.py")
    env["mod"].run(str(env["repo"]))
    last = _state(env)["last"]
    assert last["ok"] is False and "boom: disk full" in last["error"]
    rows = check._cbm_refresh()
    assert len(rows) == 1 and not rows[0].ok and rows[0].severity == "warn"
    assert str(env["repo"]) in rows[0].detail and "boom" in rows[0].detail
    (env["stub"] / "index.rc").write_text("0")
    (env["stub"] / "index.err").unlink()
    env["mod"].run(str(env["repo"]))
    assert check._cbm_refresh() == []


def test_hook_skips_when_codebase_memory_is_off_for_the_folder(env):
    (env["home"] / ".claude.json").write_text(json.dumps(
        {"projects": {str(env["repo"]): {"disabledMcpServers": ["plugin:loadout:codebase-memory-mcp"]}}}))
    _edit(env, env["repo"] / "a.py")
    _bash(env, "git checkout main")
    _stop(env)
    assert env["spawned"] == [] and _state(env) is None


def test_hook_skips_without_the_binary(env):
    (env["bin"] / "codebase-memory-mcp").unlink()
    _bash(env, "git checkout main")
    assert env["spawned"] == []


def test_hook_returns_fast_and_prints_nothing(env):
    (env["stub"] / "sleep").write_text("3")  # every cbm call of the child takes 3 s
    _edit(env, env["repo"] / "a.py")
    e = {k: os.environ[k] for k in ("HOME", "PATH", "STUB", "CBM_CACHE_DIR")}
    payload = json.dumps({"session_id": "s1", "hook_event_name": "Stop", "cwd": str(env["repo"])})
    start = time.monotonic()
    res = subprocess.run([sys.executable, str(SCRIPT)], input=payload, env=e, capture_output=True, text=True,
                         timeout=20)
    assert time.monotonic() - start < 2
    assert res.returncode == 0 and res.stdout == "" and res.stderr == ""
    deadline = time.monotonic() + 20  # the detached child goes on alone and indexes
    while not _indexes(env) and time.monotonic() < deadline:
        time.sleep(0.2)
    assert len(_indexes(env)) == 1


def test_non_repo_folder_does_nothing(env):
    (env["stub"] / "root").unlink()
    _edit(env, env["repo"] / "a.py")
    _bash(env, "git checkout main")
    _stop(env)
    assert env["spawned"] == [] and _state(env) is None


def test_codex_apply_patch_paths_are_recorded(env):
    patch = ("*** Begin Patch\n*** Update File: src/a.py\n@@\n-x\n+y\n*** Add File: b.ts\n+z\n"
             "*** Add File: notes.md\n+n\n*** End Patch\n")
    env["mod"].handle({"session_id": "s1", "hook_event_name": "PostToolUse", "tool_name": "apply_patch",
                       "cwd": str(env["repo"]), "tool_input": {"command": patch}})
    assert _state(env)["changed"] == [str(env["repo"] / "src/a.py"), str(env["repo"] / "b.ts")]


def test_broken_input_is_silent(env):
    for raw in ("", "not json", "[]"):
        res = subprocess.run([sys.executable, str(SCRIPT)], input=raw, capture_output=True, text=True, timeout=20,
                             env={k: os.environ[k] for k in ("HOME", "PATH")})
        assert res.returncode == 0 and res.stdout == "" and res.stderr == ""


def test_hooks_are_wired():
    claude = json.loads((PLUGIN / "hooks" / "hooks.json").read_text())["hooks"]
    codex = json.loads((PLUGIN / "hooks" / "codex.json").read_text())["hooks"]

    def has(hooks, event, matcher):
        return any(g.get("matcher") == matcher and any("refresh.py" in h["command"] for h in g["hooks"])
                   for g in hooks.get(event, []))
    assert has(claude, "PostToolUse", "Write|Edit|MultiEdit|Bash") and has(claude, "Stop", "")
    assert has(claude, "SubagentStop", "")
    assert has(codex, "PostToolUse", "Edit|Write|Bash") and has(codex, "Stop", "")


def test_cbm_is_called_with_its_flags_and_json_output(env):
    _edit(env, env["repo"] / "a.py")
    _stop(env)
    env["mod"].run(str(env["repo"]))
    status = [l for l in _log(env) if " index_status " in l]
    assert status == [f"cbm cli --quiet index_status --project {env['default']} --format json"]
    assert _indexes(env) == [f"cbm cli --quiet index_repository --repo-path {env['repo']}"]
