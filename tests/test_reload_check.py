"""plugins/loadout/hooks/reload_check.py, run as a subprocess from a copy inside a fake plugin cache."""
import json
import os
import shutil
import subprocess

import pytest

from loadout import paths

SRC = paths.kit_root() / "plugins" / "loadout" / "hooks" / "reload_check.py"
NOTICE = ("loadout: the plugin was updated after this session started. "
          "Run /reload-plugins to load the new skills and hooks.")
pytestmark = pytest.mark.skipif(os.name == "nt", reason="hook scripts run under bash/python3 on POSIX")


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    h.mkdir()
    return h


def _plugin(root):
    """A plugin folder with the script in hooks/; returns the script path."""
    (root / "hooks").mkdir(parents=True)
    shutil.copy(SRC, root / "hooks" / "reload_check.py")
    return root / "hooks" / "reload_check.py"


def _cache(home, version):
    return home / ".claude/plugins/cache/agent-loadout/loadout" / version


def _installed(home, entries):
    p = home / ".claude/plugins/installed_plugins.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(entries if isinstance(entries, str) else json.dumps({"version": 2, "plugins": {"loadout@agent-loadout": entries}}))


def _run(home, script, session="s1", raw=None):
    stdin = raw if raw is not None else json.dumps({"session_id": session, "hook_event_name": "Stop"})
    r = subprocess.run(["python3", str(script)], input=stdin, env={"HOME": str(home), "PATH": os.environ["PATH"]},
                       capture_output=True, text=True)
    assert r.returncode == 0 and r.stderr == ""
    return r.stdout


def test_same_path_is_silent(home):
    script = _plugin(_cache(home, "aaa"))
    _installed(home, [{"scope": "user", "installPath": str(_cache(home, "aaa"))}])
    assert _run(home, script) == ""


def test_updated_plugin_notifies_once_per_session(home):
    script = _plugin(_cache(home, "aaa"))
    _installed(home, [{"scope": "user", "installPath": str(_cache(home, "bbb"))}])
    assert json.loads(_run(home, script)) == {"systemMessage": NOTICE}
    assert _run(home, script) == ""
    assert json.loads(_run(home, script, session="s2")) == {"systemMessage": NOTICE}


def test_state_keeps_last_20_sessions(home):
    script = _plugin(_cache(home, "aaa"))
    _installed(home, [{"scope": "user", "installPath": str(_cache(home, "bbb"))}])
    for i in range(25):
        _run(home, script, session=f"s{i}")
    data = json.loads((home / ".local/state/loadout/reload-notified.json").read_text())
    assert data["sessions"] == [f"s{i}" for i in range(5, 25)]


def test_any_matching_entry_is_silent(home):
    script = _plugin(_cache(home, "aaa"))
    _installed(home, [{"scope": "user", "installPath": str(_cache(home, "bbb"))},
                      {"scope": "project", "projectPath": "/x", "installPath": str(_cache(home, "aaa"))}])
    assert _run(home, script) == ""


def test_dev_checkout_outside_the_cache_is_silent(home, tmp_path):
    script = _plugin(tmp_path / "repo/plugins/loadout")
    _installed(home, [{"scope": "user", "installPath": str(_cache(home, "bbb"))}])
    assert _run(home, script) == ""


@pytest.mark.parametrize("content", [None, "{ broken", json.dumps({"version": 2, "plugins": {}}),
                                     json.dumps({"version": 2, "plugins": {"loadout@agent-loadout": "x"}}),
                                     json.dumps({"version": 2, "plugins": {"loadout@agent-loadout": [{"scope": "user"}]}})])
def test_missing_or_malformed_installed_plugins_is_silent(home, content):
    script = _plugin(_cache(home, "aaa"))
    if content is not None:
        _installed(home, content)
    assert _run(home, script) == ""


@pytest.mark.parametrize("raw", ["", "not json", "[]", json.dumps({"hook_event_name": "Stop"})])
def test_bad_stdin_is_silent(home, raw):
    script = _plugin(_cache(home, "aaa"))
    _installed(home, [{"scope": "user", "installPath": str(_cache(home, "bbb"))}])
    assert _run(home, script, raw=raw) == ""


def test_unwritable_state_is_silent(home):
    script = _plugin(_cache(home, "aaa"))
    _installed(home, [{"scope": "user", "installPath": str(_cache(home, "bbb"))}])
    (home / ".local/state/loadout").parent.mkdir(parents=True, exist_ok=True)
    (home / ".local/state/loadout").write_text("a file, not a folder")
    assert _run(home, script) == ""  # cannot record the session: say nothing rather than repeat every turn


def test_hooks_json_wires_reload_check_soft_on_session_start_and_stop():
    hooks = json.loads((paths.kit_root() / "plugins/loadout/hooks/hooks.json").read_text())["hooks"]
    for event in ("SessionStart", "Stop"):
        cmds = [h["command"] for g in hooks[event] for h in g["hooks"]]
        assert any('run.sh" --soft --python' in c and "hooks/reload_check.py" in c for c in cmds), event


# --- the /reload-plugins step clears once the session runs the newly installed loadout plugin ----------------------

RELOAD = {"id": "claude/reload-plugins", "text": "run /reload-plugins (or restart Claude Code)", "reason": "x", "since": 1.0}
OTHER = {"id": "claude/mcp:a", "text": "run /mcp and reconnect a", "reason": "y", "since": 2.0}
CODEX = {"id": "codex/hooks", "text": "approve", "reason": "z", "since": 3.0}


def _steps_file(home):
    return home / ".local/state/loadout/open-steps.json"


def _write_steps(home, data):
    p = _steps_file(home)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(data if isinstance(data, str) else json.dumps(data, indent=2) + "\n")


def test_stop_clears_a_loadout_plugin_reload_step_when_the_new_plugin_runs(home):
    script = _plugin(_cache(home, "bbb"))
    _installed(home, [{"scope": "user", "installPath": str(_cache(home, "bbb"))}])
    _write_steps(home, {"claude": [OTHER, {**RELOAD, "loadout_plugin": True}], "codex": [CODEX]})
    assert _run(home, script) == ""
    text = _steps_file(home).read_text()
    assert json.loads(text) == {"claude": [OTHER], "codex": [CODEX]}  # the other steps stay as they were
    assert text == json.dumps({"claude": [OTHER], "codex": [CODEX]}, indent=2, ensure_ascii=False) + "\n"
    assert not list(_steps_file(home).parent.glob("*.tmp"))


def test_the_last_step_of_an_agent_drops_the_agent(home):
    script = _plugin(_cache(home, "bbb"))
    _installed(home, [{"scope": "user", "installPath": str(_cache(home, "bbb"))}])
    _write_steps(home, {"claude": [{**RELOAD, "loadout_plugin": True}], "codex": [CODEX]})
    _run(home, script, raw="")  # cleared even without a session id
    assert json.loads(_steps_file(home).read_text()) == {"codex": [CODEX]}


def test_an_old_session_keeps_the_step_until_it_reloads(home):
    script = _plugin(_cache(home, "aaa"))
    _installed(home, [{"scope": "user", "installPath": str(_cache(home, "bbb"))}])
    data = {"claude": [{**RELOAD, "loadout_plugin": True}]}
    _write_steps(home, data)
    _run(home, script)
    assert json.loads(_steps_file(home).read_text()) == data


def test_a_step_without_loadout_plugin_stays(home):
    """Only another plugin (superpowers) was updated: this hook cannot see whether it was reloaded."""
    script = _plugin(_cache(home, "bbb"))
    _installed(home, [{"scope": "user", "installPath": str(_cache(home, "bbb"))}])
    data = {"claude": [RELOAD, OTHER]}
    _write_steps(home, data)
    before = _steps_file(home).read_text()
    _run(home, script)
    assert _steps_file(home).read_text() == before


def test_a_dev_checkout_never_clears_the_step(home, tmp_path):
    script = _plugin(tmp_path / "repo/plugins/loadout")
    _installed(home, [{"scope": "user", "installPath": str(tmp_path / "repo/plugins/loadout")}])
    data = {"claude": [{**RELOAD, "loadout_plugin": True}]}
    _write_steps(home, data)
    _run(home, script)
    assert json.loads(_steps_file(home).read_text()) == data


@pytest.mark.parametrize("content", [None, "{ broken", "[]", json.dumps({"claude": "x"}),
                                     json.dumps({"claude": [OTHER]})])
def test_a_missing_broken_or_stepless_file_is_left_alone(home, content):
    script = _plugin(_cache(home, "bbb"))
    _installed(home, [{"scope": "user", "installPath": str(_cache(home, "bbb"))}])
    if content is not None:
        _write_steps(home, content)
    assert _run(home, script) == ""
    if content is None:
        assert not _steps_file(home).exists()
    else:
        assert _steps_file(home).read_text() == content
