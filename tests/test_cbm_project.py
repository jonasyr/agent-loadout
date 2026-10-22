"""cbm_project.py: points a session or subagent at the codebase-memory project of its folder.
Runs as a subprocess with a temporary HOME; the cache folder is a fake one."""
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1] / "plugins" / "loadout"
SCRIPT = PLUGIN / "hooks" / "cbm_project.py"


def _run(tmp_path, cwd, event="session-start", raw=None, extra_env=None):
    env = {"HOME": str(tmp_path / "home"), "PATH": os.environ.get("PATH", "")}
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
