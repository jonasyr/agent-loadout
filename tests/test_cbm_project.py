"""cbm_project.py: points a session or subagent at the codebase-memory project of its folder.
Runs as a subprocess with a temporary HOME; the cache folder is a fake one."""
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[1] / "plugins" / "loadout"
SCRIPT = PLUGIN / "hooks" / "cbm_project.py"


def _stub_bin(tmp_path):
    """A codebase-memory-mcp on PATH: the hook points only to a tool the agent has (CI machines have none)."""
    bindir = tmp_path / "stub-bin"
    bindir.mkdir(exist_ok=True)
    stub = bindir / ("codebase-memory-mcp.cmd" if os.name == "nt" else "codebase-memory-mcp")
    stub.write_text("@echo off\n" if os.name == "nt" else "#!/bin/sh\n")
    stub.chmod(0o755)
    return bindir


def _run(tmp_path, cwd, event="session-start", raw=None, extra_env=None):
    path = f"{_stub_bin(tmp_path)}{os.pathsep}{os.environ.get('PATH', '')}"
    env = {"HOME": str(tmp_path / "home"), "PATH": path, **({"PATHEXT": os.environ["PATHEXT"]}
                                                             if "PATHEXT" in os.environ else {})}
    env.update(extra_env or {})
    res = subprocess.run([sys.executable, str(SCRIPT), event], input=raw if raw is not None else json.dumps({"cwd": str(cwd)}),
                         env=env, capture_output=True, text=True, timeout=20)
    assert res.returncode == 0 and res.stderr == ""
    return json.loads(res.stdout) if res.stdout.strip() else None


def _cache(tmp_path):
    d = tmp_path / "home" / ".cache" / "codebase-memory-mcp"
    d.mkdir(parents=True)
    return d


def _db(path, name, root):
    con = sqlite3.connect(path)
    con.execute("create table projects(name text, indexed_at text, root_path text)")
    con.execute("insert into projects values (?, 'now', ?)", (name, str(root)))
    con.commit()
    con.close()


def test_default_name_is_found(tmp_path):
    (tmp_path / "home").mkdir()
    cache = _cache(tmp_path)
    repo = tmp_path / "repo"
    default = str(repo).lstrip("/").replace("/", "-")
    (cache / f"{default}.db").write_bytes(b"")
    out = _run(tmp_path, repo)
    ctx = out["hookSpecificOutput"]
    assert ctx["hookEventName"] == "SessionStart"
    assert f"indexed as project {default};" in ctx["additionalContext"]
    assert f'project="{default}"' in ctx["additionalContext"]


def test_subagent_event_name(tmp_path):
    cache = _cache(tmp_path)
    repo = tmp_path / "repo"
    (cache / f"{str(repo).lstrip('/').replace('/', '-')}.db").write_bytes(b"")
    assert _run(tmp_path, repo, "subagent-start")["hookSpecificOutput"]["hookEventName"] == "SubagentStart"


def test_custom_name_is_found_by_root_path(tmp_path):
    cache = _cache(tmp_path)
    repo = tmp_path / "repo"
    _db(cache / "other.db", "my-custom-name", repo)
    _db(cache / "_config.db", "ignored", repo)
    out = _run(tmp_path, repo)
    assert "project my-custom-name;" in out["hookSpecificOutput"]["additionalContext"]


def test_unindexed_folder_prints_nothing(tmp_path):
    cache = _cache(tmp_path)
    _db(cache / "other.db", "x", tmp_path / "elsewhere")
    assert _run(tmp_path, tmp_path / "repo") is None


def test_cbm_cache_dir_is_honoured(tmp_path):
    (tmp_path / "home").mkdir()
    cache = tmp_path / "custom"
    cache.mkdir()
    _db(cache / "p.db", "from-custom", tmp_path / "repo")
    out = _run(tmp_path, tmp_path / "repo", extra_env={"CBM_CACHE_DIR": str(cache)})
    assert "project from-custom;" in out["hookSpecificOutput"]["additionalContext"]


def test_broken_db_and_broken_stdin_are_silent(tmp_path):
    cache = _cache(tmp_path)
    (cache / "broken.db").write_text("not a database")
    assert _run(tmp_path, tmp_path / "repo") is None
    assert _run(tmp_path, tmp_path / "repo", raw="not json") is None
    assert _run(tmp_path, tmp_path / "repo", raw="") is None


def test_default_name_collapses_repeated_dashes_like_cbm():
    # cbm 0.12.1 names /tmp/claude-1000/-home-x/repo `tmp-claude-1000-home-x-repo` (verified with a real index)
    import importlib.util
    spec = importlib.util.spec_from_file_location("cbm_project_t", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.default_name("/tmp/claude-1000/-home-x/repo") == "tmp-claude-1000-home-x-repo"
    assert mod.default_name("/home/jonas/Documents/Code/arsnova.eu") == "home-jonas-Documents-Code-arsnova.eu"
    assert mod.default_name("/a/b/.claude/worktrees/x") == "a-b-.claude-worktrees-x"


def _run_cbm(tmp_path, args, cwd, path_bin=True, claude_json=None):
    import subprocess, sys, json, os
    home = tmp_path / "h"
    (home / ".cache" / "codebase-memory-mcp").mkdir(parents=True, exist_ok=True)
    name = str(cwd).lstrip("/").replace("/", "-")
    (home / ".cache" / "codebase-memory-mcp" / f"{name}.db").write_bytes(b"")
    bindir = tmp_path / "b"
    bindir.mkdir(exist_ok=True)
    stub = bindir / "codebase-memory-mcp"
    if path_bin:
        stub.write_text("#!/bin/sh\n")
        stub.chmod(0o755)
    elif stub.exists():
        stub.unlink()
    if claude_json is not None:
        (home / ".claude.json").write_text(json.dumps(claude_json))
    env = {"HOME": str(home), "PATH": f"{bindir}{os.pathsep}/usr/bin:/bin"}
    res = subprocess.run([sys.executable, str(SCRIPT), *args], input=json.dumps({"cwd": str(cwd)}), env=env,
                         capture_output=True, text=True, timeout=10)
    return res.stdout.strip()


@pytest.mark.skipif(os.name == "nt", reason="a shell-script stub and a POSIX default project name")
def test_no_project_line_without_the_binary_or_with_the_server_off(tmp_path):
    cwd = tmp_path / "repo"
    cwd.mkdir()
    assert "indexed as project" in _run_cbm(tmp_path, ["session-start"], cwd)
    assert _run_cbm(tmp_path, ["session-start"], cwd, path_bin=False) == ""
    off = {"projects": {str(cwd): {"disabledMcpServers": ["plugin:loadout:codebase-memory-mcp"]}}}
    assert _run_cbm(tmp_path, ["session-start"], cwd, claude_json=off) == ""
    assert "indexed as project" in _run_cbm(tmp_path, ["session-start", "--agent", "codex"], cwd, claude_json=off)
