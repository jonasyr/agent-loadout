"""tool_hint.py: a short, never-blocking Context7/Microsoft Learn hint on library-docs web lookups (code searches are
Serena's `remind` now). The hook runs as a subprocess with a temporary HOME."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[1] / "plugins" / "loadout"
HOOK = PLUGIN / "hooks" / "tool_hint.py"
pytestmark = pytest.mark.skipif(os.name == "nt", reason="hook scripts run under python3 on POSIX")


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    h.mkdir()
    return h


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    (r / "src").mkdir(parents=True)
    (r / "pyproject.toml").write_text("[project]\nname='x'\n")
    (r / "src" / "app.py").write_text("def record_project():\n    pass\n")
    return r


def _run(home, payload, raw=None):
    env = {"HOME": str(home), "PATH": os.environ["PATH"]}
    stdin = raw if raw is not None else json.dumps(payload)
    res = subprocess.run(["python3", str(HOOK)], input=stdin, env=env, capture_output=True, text=True, timeout=10)
    assert res.returncode == 0
    return json.loads(res.stdout) if res.stdout.strip() else None


def _grep(repo, pattern, session="s1", path=None):
    tool_input = {"pattern": pattern, **({"path": path} if path else {})}
    return {"hook_event_name": "PreToolUse", "tool_name": "Grep", "tool_input": tool_input,
            "session_id": session, "cwd": str(repo)}


def _bash(repo, command, session="s1"):
    return {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": command},
            "session_id": session, "cwd": str(repo)}


def _mcp(repo, name="mcp__plugin_loadout_serena__find_symbol", session="s1"):
    return {"hook_event_name": "PostToolUse", "tool_name": name, "tool_input": {}, "session_id": session,
            "cwd": str(repo)}


def _context(out):
    return out["hookSpecificOutput"]["additionalContext"] if out else None


def _docs(repo, session="s1"):
    return _web(repo, "WebSearch", {"query": "fastapi docs dependencies"}, session=session)


def _state(home, session="s1"):
    return home / ".local" / "state" / "loadout" / "tool-hint" / f"{session}.json"


def test_no_search_hint_any_more(home, repo):
    for _ in range(4):
        assert _run(home, _grep(repo, "record_project")) is None
        assert _run(home, _bash(repo, "rg -n record_project src")) is None
        assert _run(home, _mcp(repo)) is None
    assert not _state(home).exists()


def test_a_hint_records_when_it_was_shown(home, repo):
    _run(home, _docs(repo))
    assert abs(json.loads(_state(home).read_text())["hint_at"] - time.time()) < 60


def test_no_session_id_gives_no_hint_and_no_state(home, repo):
    payload = _docs(repo)
    del payload["session_id"]
    assert _run(home, payload) is None
    assert not (home / ".local" / "state" / "loadout" / "tool-hint").exists()


def test_a_broken_state_file_starts_fresh(home, repo):
    _state(home).parent.mkdir(parents=True)
    _state(home).write_text("{broken")
    assert _context(_run(home, _docs(repo)))


def test_a_session_id_is_never_a_path(home, repo):
    _run(home, _docs(repo, session="../../escape"))
    assert not list(home.rglob("escape*"))


def test_huge_payload_is_ignored_quickly(home, repo):
    payload = _web(repo, "WebSearch", {"query": "docs " + "a" * 2_000_000})
    start = time.monotonic()
    assert _run(home, None, raw=json.dumps(payload)) is None
    assert time.monotonic() - start < 5
    assert _run(home, None, raw="\x00\xff not json") is None


def test_the_state_folder_is_private(home, repo):
    _run(home, _docs(repo))
    for folder in (home / ".local" / "state" / "loadout", home / ".local" / "state" / "loadout" / "tool-hint"):
        assert folder.stat().st_mode & 0o077 == 0, folder


GATE = PLUGIN / "hooks" / "tool_hint.sh"


def test_the_gate_lets_web_lookups_through_and_stops_everything_else_before_python(home, repo):
    env = {"HOME": str(home), "PATH": os.environ["PATH"]}

    def gate(payload):
        res = subprocess.run(["bash", str(GATE)], input=json.dumps(payload), env=env, capture_output=True,
                             text=True, timeout=10)
        assert res.returncode == 0
        return json.loads(res.stdout) if res.stdout.strip() else None
    assert _context(gate(_docs(repo)))
    other = home / "other"
    other.mkdir()
    env["HOME"] = str(other)
    for payload in (_bash(repo, "rg -n record_project src"), _grep(repo, "record_project"), _mcp(repo)):
        assert gate(payload) is None
    assert not (other / ".local").exists()  # stopped before the hook: no state written


def test_a_python3_that_does_not_run_falls_back_to_python(home, repo, tmp_path):
    # Windows: `python3` can be the Microsoft Store alias, which exists but only prints a notice and fails
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "python3"
    stub.write_text("#!/bin/sh\necho 'Python was not found; run without arguments to install' >&2\nexit 9009\n")
    stub.chmod(0o755)
    (bindir / "python").symlink_to(sys.executable)
    env = {"HOME": str(home), "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}"}
    res = subprocess.run(["bash", str(GATE)], input=json.dumps(_docs(repo)), env=env, capture_output=True,
                         text=True, timeout=10)
    assert res.returncode == 0 and _context(json.loads(res.stdout))


def test_concurrent_runs_never_crash(home, repo):
    env = {"HOME": str(home), "PATH": os.environ["PATH"]}
    procs = [subprocess.Popen(["python3", str(HOOK)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, env=env, text=True) for _ in range(8)]
    for p in procs:
        p.stdin.write(json.dumps(_docs(repo)))
        p.stdin.close()
    for p in procs:
        assert p.wait(timeout=10) == 0 and p.stderr.read() == ""
    assert 1 <= json.loads(_state(home).read_text())["calls"] <= 8


def test_old_state_files_are_cleaned(home, repo):
    folder = _state(home).parent
    folder.mkdir(parents=True)
    old = folder / "old.json"
    old.write_text("{}")
    os.utime(old, (time.time() - 8 * 86400,) * 2)
    _run(home, _docs(repo, session="new"))
    assert not old.exists() and _state(home, "new").exists()


def _web(repo, tool, tool_input, session="s1"):
    return {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input, "session_id": session,
            "cwd": str(repo)}


@pytest.mark.parametrize("tool,tool_input", [
    ("WebSearch", {"query": "pydantic v2 docs field validators"}),
    ("WebFetch", {"url": "https://docs.python.org/3/library/shlex.html", "prompt": "split rules"}),
    ("WebFetch", {"url": "https://learn.microsoft.com/en-us/dotnet/api/system.text.json"}),
    ("WebSearch", {"query": "react useEffect cleanup api reference"}),
])
def test_a_library_docs_lookup_gets_the_context7_fact(home, repo, tool, tool_input):
    text = _context(_run(home, _web(repo, tool, tool_input)))
    assert "Context7" in text and "Microsoft Learn" in text and len(text) <= 300


def test_other_web_lookups_get_nothing(home, repo):
    assert _run(home, _web(repo, "WebSearch", {"query": "weather berlin tomorrow"})) is None
    assert _run(home, _web(repo, "WebFetch", {"url": "https://news.ycombinator.com/item?id=1"})) is None


def test_the_docs_hint_is_spaced_and_needs_no_code_repo(home, tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    shown = [_run(home, _web(plain, "WebSearch", {"query": "fastapi docs dependencies"})) is not None
             for _ in range(11)]
    assert shown[0] and shown[1:10].count(True) == 0 and shown[10]
