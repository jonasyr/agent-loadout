"""tool_hint.py: a short, never-blocking hint after repeated symbol searches without Serena or the graph.
The hook runs as a subprocess with a temporary HOME and a fixture repo."""
import json
import os
import subprocess
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


def test_the_third_symbol_search_gets_one_short_fact(home, repo):
    assert _run(home, _grep(repo, "record_project")) is None
    assert _run(home, _grep(repo, "record_project")) is None
    out = _run(home, _grep(repo, "record_project"))
    text = _context(out)
    assert "record_project" in text and "search_graph" in text and "find_symbol" in text
    assert len(text) <= 300
    assert out["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert "permissionDecision" not in out["hookSpecificOutput"]


def test_shell_searches_count_also_behind_rtk_and_git_grep(home, repo):
    _run(home, _bash(repo, "rtk rg -n record_project src"))
    _run(home, _bash(repo, "cd src && grep -rn 'def record_project' ."))
    assert "record_project" in _context(_run(home, _bash(repo, "git grep record_project")))


def test_codex_command_as_list_counts(home, repo):
    for _ in range(2):
        _run(home, _bash(repo, ["rg", "-n", "record_project", "src"]))
    assert _context(_run(home, _bash(repo, ["rg", "record_project"])))


def test_serena_or_graph_use_resets_the_counter_and_drift_brings_the_hint_back(home, repo):
    _run(home, _grep(repo, "record_project"))
    _run(home, _grep(repo, "record_project"))
    _run(home, _mcp(repo, "mcp__plugin_loadout_codebase-memory-mcp__search_graph"))
    assert _run(home, _grep(repo, "record_project")) is None
    assert _run(home, _grep(repo, "record_project")) is None
    assert _context(_run(home, _grep(repo, "record_project")))  # drifted again: hint again, never silenced


def test_codex_mcp_names_reset_too(home, repo):
    _run(home, _grep(repo, "record_project"))
    _run(home, _grep(repo, "record_project"))
    _run(home, _mcp(repo, "mcp__serena__find_symbol"))
    assert _run(home, _grep(repo, "record_project")) is None


def test_spacing_allows_one_hint_per_ten_calls(home, repo):
    shown = [_context(_run(home, _grep(repo, "record_project"))) is not None for _ in range(13)]
    assert shown.index(True) == 2  # the 3rd call
    assert shown[3:12].count(True) == 0  # calls 4-12 are within 10 calls of the hint
    assert shown[12] is True  # call 13: 3 searches since the hint, 10 calls later


def test_common_words_never_count(home, repo):
    for word in ("error", "TODO", "config", "import", "self"):
        for _ in range(4):
            assert _run(home, _grep(repo, word)) is None
            assert _run(home, _bash(repo, f"rg -n {word}")) is None
    for _ in range(4):
        assert _run(home, _bash(repo, "rg -n 'failed to connect'")) is None  # a phrase, not a symbol


def test_a_find_for_code_files_counts_without_a_symbol(home, repo):
    for _ in range(2):
        _run(home, _bash(repo, "find . -name '*.py'"))
    text = _context(_run(home, _bash(repo, "find src -name '*.py'")))
    assert "search_graph" in text


def test_non_code_paths_never_count(home, repo):
    for _ in range(4):
        assert _run(home, _bash(repo, "rg record_project docs/notes.md CHANGELOG.md")) is None
        assert _run(home, _grep(repo, "record_project", path="logs/app.log")) is None


def test_non_code_repo_gives_no_hint(home, tmp_path):
    plain = tmp_path / "notes"
    plain.mkdir()
    (plain / "todo.md").write_text("x")
    for _ in range(4):
        assert _run(home, _grep(plain, "record_project")) is None


def test_no_session_id_gives_no_hint_and_no_state(home, repo):
    for _ in range(4):
        payload = _grep(repo, "record_project")
        del payload["session_id"]
        assert _run(home, payload) is None
    assert not (home / ".local" / "state" / "loadout" / "tool-hint").exists()


def test_a_broken_state_file_starts_fresh(home, repo):
    state = home / ".local" / "state" / "loadout" / "tool-hint"
    state.mkdir(parents=True)
    (state / "s1.json").write_text("{broken")
    _run(home, _grep(repo, "record_project"))
    _run(home, _grep(repo, "record_project"))
    assert _context(_run(home, _grep(repo, "record_project")))


def test_a_session_id_is_never_a_path(home, repo):
    for _ in range(3):
        _run(home, _grep(repo, "record_project", session="../../escape"))
    assert not (home / ".local" / "escape.json").exists()


def test_huge_payload_is_ignored_quickly(home, repo):
    start = time.monotonic()
    assert _run(home, None, raw='{"tool_input": {"command": "' + "a" * 2_000_000 + '"}}') is None
    assert time.monotonic() - start < 5
    assert _run(home, None, raw="\x00\xff not json") is None


def test_concurrent_runs_never_crash(home, repo):
    env = {"HOME": str(home), "PATH": os.environ["PATH"]}
    procs = [subprocess.Popen(["python3", str(HOOK)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, env=env, text=True) for _ in range(8)]
    for p in procs:
        p.stdin.write(json.dumps(_grep(repo, "record_project")))
        p.stdin.close()
    for p in procs:
        assert p.wait(timeout=10) == 0 and p.stderr.read() == ""


def test_old_state_files_are_cleaned(home, repo):
    state = home / ".local" / "state" / "loadout" / "tool-hint"
    state.mkdir(parents=True)
    old = state / "old.json"
    old.write_text("{}")
    os.utime(old, (time.time() - 8 * 86400,) * 2)
    _run(home, _grep(repo, "record_project", session="new"))
    assert not old.exists() and (state / "new.json").exists()


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
