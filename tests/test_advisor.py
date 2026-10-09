"""Execution-advisor hooks (plugins/loadout/hooks/advisor.py) and `loadout advisor-mark`.

The hook scripts run as subprocesses with stdin fixtures and a temporary HOME."""
import json
import os
import shutil
import subprocess

import pytest

from loadout import paths
from loadout.__main__ import main

PLUGIN = paths.kit_root() / "plugins" / "loadout"
HOOK = PLUGIN / "hooks" / "advisor.py"
pytestmark = pytest.mark.skipif(os.name == "nt", reason="hook scripts run under bash/python3 on POSIX")

PLAN = """# Tasklog Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Export tasks as CSV.

### Task 1: Writer

- [ ] **Step 1: Write the failing test**
- [ ] **Step 2: Implement**
"""


def _hook(mode, payload, home, raw=None):
    env = {"HOME": str(home), "PATH": os.environ["PATH"]}
    stdin = raw if raw is not None else json.dumps(payload)
    return subprocess.run(["python3", str(HOOK), mode], input=stdin, env=env, capture_output=True, text=True)


def _write(path, text=PLAN):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _record(home, plan, session="s1", tool="Write"):
    payload = {"session_id": session, "hook_event_name": "PostToolUse", "tool_name": tool,
               "tool_input": {"file_path": str(plan)}}
    r = _hook("record", payload, home)
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""
    return r


def _stop(home, session="s1", active=False):
    payload = {"session_id": session, "hook_event_name": "Stop", "stop_hook_active": active,
               "transcript_path": str(home / "t.jsonl")}
    r = _hook("stop", payload, home)
    assert r.returncode == 0 and r.stderr == ""
    return r


def _pending(home):
    f = home / ".claude/.loadout/advisor-pending.json"
    return json.loads(f.read_text()) if f.exists() else None


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    h.mkdir()
    return h


@pytest.fixture
def plan(tmp_path):
    return _write(tmp_path / "repo/docs/superpowers/plans/2026-10-09-export.md")


def test_plan_write_is_recorded(home, plan):
    _record(home, plan)
    entries = _pending(home)["plans"]
    assert [(e["path"], e["session_id"]) for e in entries] == [(str(plan), "s1")]
    text = (home / ".claude/.loadout/advisor-pending.json").read_text()
    assert text.endswith("}\n") and '\n  "plans"' in text  # kit JSON style: 2-space indent, trailing newline


def test_repeated_writes_record_one_entry(home, plan):
    _record(home, plan)
    _record(home, plan, tool="Edit")
    assert len(_pending(home)["plans"]) == 1


def test_any_plans_dir_counts(home, tmp_path):
    p = _write(tmp_path / "repo/plans/feature.md")
    _record(home, p, tool="MultiEdit")
    assert _pending(home)["plans"][0]["path"] == str(p)


@pytest.mark.parametrize("rel,text", [
    ("repo/src/app.md", PLAN),                                        # not under plans/
    ("repo/docs/superpowers/plans/notes.txt", PLAN),                  # not markdown
    ("repo/docs/superpowers/plans/ideas.md", "# Ideas\n\n- [ ] one\n"),  # no "Implementation Plan" header
    ("repo/docs/superpowers/plans/done.md", "# X Implementation Plan\n\nNo tasks yet.\n"),  # no checkbox
])
def test_non_plan_write_is_not_recorded(home, tmp_path, rel, text):
    _record(home, _write(tmp_path / rel, text))
    assert _pending(home) is None


def test_stop_without_pending_plan_allows(home):
    assert _stop(home).stdout == ""


def test_stop_blocks_once_with_instruction(home, plan):
    _record(home, plan)
    r = _stop(home)
    out = json.loads(r.stdout)
    assert out["decision"] == "block"
    assert f"A plan was just finished: {plan}." in out["reason"]
    assert "/loadout:execution-advisor" in out["reason"] and "Hybrid" in out["reason"]
    assert r.stdout.count("\n") <= 1  # only the block JSON
    # the hook never blocks twice: stop_hook_active allows, and the same plan version is not nagged again
    assert _stop(home, active=True).stdout == ""
    assert _stop(home).stdout == ""


def test_stop_hook_active_always_allows(home, plan):
    _record(home, plan)
    assert _stop(home, active=True).stdout == ""
    assert json.loads(_stop(home).stdout)["decision"] == "block"  # nothing was consumed by the allowed stop


def test_other_session_is_not_blocked(home, plan):
    _record(home, plan, session="s1")
    assert _stop(home, session="s2").stdout == ""


def test_evaluated_hash_allows(home, plan, fake_home_env):
    _record(home, plan)
    assert main(["advisor-mark", str(plan)]) == 0
    assert _stop(home).stdout == ""


def test_changed_plan_blocks_again(home, plan, fake_home_env):
    _record(home, plan)
    assert main(["advisor-mark", str(plan)]) == 0
    plan.write_text(PLAN + "\n### Task 2: Reader\n\n- [ ] **Step 1: Test**\n", encoding="utf-8")
    _record(home, plan, tool="Edit")
    assert json.loads(_stop(home).stdout)["decision"] == "block"


def test_ticking_checkboxes_does_not_count_as_a_change(home, plan, fake_home_env):
    """Executing a plan ticks its boxes; that must not re-trigger the advisor."""
    _record(home, plan)
    assert main(["advisor-mark", str(plan)]) == 0
    plan.write_text(PLAN.replace("- [ ] **Step 1", "- [x] **Step 1"), encoding="utf-8")
    _record(home, plan, tool="Edit")
    assert _stop(home).stdout == ""


def test_deleted_plan_allows(home, plan):
    _record(home, plan)
    plan.unlink()
    assert _stop(home).stdout == ""


@pytest.mark.parametrize("mode", ["record", "stop"])
@pytest.mark.parametrize("raw", ["", "not json", "[1, 2]", '{"tool_input": "x"}', '{"session_id": 5}'])
def test_malformed_stdin_allows_silently(home, mode, raw):
    r = _hook(mode, None, home, raw=raw)
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""


def test_corrupt_state_allows_silently(home, plan):
    _record(home, plan)
    (home / ".claude/.loadout/advisor-pending.json").write_text("{broken")
    r = _stop(home)
    assert r.stdout == ""
    r = _record(home, plan)  # recording recovers from a corrupt file
    assert json.loads(_stop(home).stdout)["decision"] == "block"


def test_unknown_mode_is_silent(home):
    r = _hook("bogus", {}, home)
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""


def test_hooks_json_wires_the_advisor():
    hooks = json.loads((PLUGIN / "hooks/hooks.json").read_text())["hooks"]
    post = [g for g in hooks["PostToolUse"] if g["matcher"] == "Write|Edit|MultiEdit"]
    assert post and "hooks/advisor.py\" record" in post[0]["hooks"][0]["command"]
    stop = hooks["Stop"][0]["hooks"][0]["command"]
    assert stop.startswith('"${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" --soft python3 ') and stop.endswith("advisor.py\" stop")


def test_hooks_json_commands_run_through_run_sh(home, plan):
    """The exact hooks.json command lines work end to end under bash."""
    hooks = json.loads((PLUGIN / "hooks/hooks.json").read_text())["hooks"]
    record = [g for g in hooks["PostToolUse"] if g["matcher"] == "Write|Edit|MultiEdit"][0]["hooks"][0]["command"]
    stop = hooks["Stop"][0]["hooks"][0]["command"]
    env = {"HOME": str(home), "PATH": os.environ["PATH"], "CLAUDE_PLUGIN_ROOT": str(PLUGIN)}
    payload = {"session_id": "s1", "tool_input": {"file_path": str(plan)}}
    r = subprocess.run(["bash", "-c", record], input=json.dumps(payload), env=env, capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout == ""
    r = subprocess.run(["bash", "-c", stop], input='{"session_id": "s1"}', env=env, capture_output=True, text=True)
    assert r.returncode == 0 and json.loads(r.stdout)["decision"] == "block"


def test_run_sh_is_silent_without_python3(home, tmp_path):
    bash = shutil.which("bash")
    env = {"HOME": str(home), "PATH": str(tmp_path / "empty")}
    r = subprocess.run([bash, str(PLUGIN / "hooks/run.sh"), "--soft", "python3", str(HOOK), "stop"],
                       input='{"session_id": "s1"}', env=env, capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""


# --- loadout advisor-mark ---

@pytest.fixture
def fake_home_env(home, monkeypatch):
    """Point the in-process CLI at the same temporary HOME the hook subprocesses use."""
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


def test_advisor_mark_records_hash(fake_home_env, plan, capsys):
    assert main(["advisor-mark", str(plan)]) == 0
    assert "marked" in capsys.readouterr().out
    done = json.loads((fake_home_env / ".claude/.loadout/advisor-done.json").read_text())
    (entry,) = done["evaluated"].values()
    assert entry["path"] == str(plan)


def test_advisor_mark_missing_plan_fails(fake_home_env, tmp_path, capsys):
    assert main(["advisor-mark", str(tmp_path / "nope.md")]) == 1
    assert "no such plan" in capsys.readouterr().err


def test_advisor_mark_is_hidden_from_help(capsys):
    with pytest.raises(SystemExit):
        main(["--help"])
    assert "advisor-mark" not in capsys.readouterr().out
