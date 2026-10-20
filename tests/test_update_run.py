"""`loadout update` as one run: lock, pull, restart into the new code, plan, re-apply, refresh, tools, health check,
"What changed" (spec decisions 1, 7, 8)."""
import json
import os
import socket
import subprocess
import sys
import time

import pytest

from loadout import apply, backup, bootstrap, check, codex, locks, maintenance, paths, runner, targets, update

PULLED = "LOADOUT_UPDATE_PULLED"


def _world(monkeypatch, claude=True, codex_on=False):
    monkeypatch.setattr(targets, "OVERRIDE", {"claude": claude, "codex": codex_on})
    monkeypatch.setattr(codex, "unavailable", lambda *a, **k: None)
    monkeypatch.setattr(codex, "apply_plugins", lambda bk, **kw: [])
    monkeypatch.setattr(maintenance, "find_outdated", lambda: [])
    monkeypatch.setattr(bootstrap, "missing_tools", lambda *a, **k: [])
    monkeypatch.setattr(check, "run_checks", lambda *a, **k: [])
    monkeypatch.setattr(locks, "FOREGROUND_LIMIT", 1.0)
    monkeypatch.setattr(locks, "POLL", 0.02)


def _heads(fake_runner, monkeypatch, heads: dict):
    """runner.run where `git -C <root> rev-parse HEAD` answers the next head of heads[root] (the last one repeats)."""
    seen = {k: list(v) for k, v in heads.items()}

    def run(cmd, cwd=None, timeout=300, env=None):
        if cmd[:2] == ["git", "-C"] and cmd[3:] == ["rev-parse", "HEAD"] and cmd[2] in seen:
            fake_runner.calls.append(list(cmd))
            left = seen[cmd[2]]
            return runner.Result(0, (left.pop(0) if len(left) > 1 else left[0]) + "\n", "")
        return fake_runner(cmd, cwd, timeout, env)
    monkeypatch.setattr(runner, "run", run)


def _pulls(fake_runner):
    return [c for c in fake_runner.calls if c[:1] == ["git"] and "pull" in c]


def _changed(text):
    assert "What changed" in text, text
    return text.split("What changed", 1)[1]


def test_update_reapplies_the_codex_block(fake_home, fake_runner, monkeypatch, capsys):
    _world(monkeypatch, claude=False, codex_on=True)
    path = paths.codex_home() / "AGENTS.md"
    path.parent.mkdir(parents=True)
    stale = f"# mine\n\n{codex.START}\nold rules\n{codex.END}\n"
    path.write_text(stale, encoding="utf-8")
    assert update.run(True, lambda q: "", argv=["--yes"]) == 0
    assert path.read_text(encoding="utf-8") == codex.splice(stale, codex.render_instructions())
    assert "Codex's AGENTS.md block updated" in _changed(capsys.readouterr().out)


def test_a_kit_pull_restarts_into_the_new_code_once(fake_home, fake_runner, monkeypatch, capsys):
    _world(monkeypatch)
    monkeypatch.delenv(PULLED, raising=False)
    kit = str(paths.kit_root())
    _heads(fake_runner, monkeypatch, {kit: ["aaa", "bbb", "bbb"]})
    restarts = []

    def fake_exec(argv):
        restarts.append((list(argv), os.environ.get(PULLED), (paths.state_dir() / maintenance.LOCK).exists()))
        pulls = len(_pulls(fake_runner))
        code = update.run(True, lambda q: "", argv=argv[1:])  # the new process
        assert len(_pulls(fake_runner)) == pulls, "the restarted run pulled again"
        return code
    monkeypatch.setattr(update, "_exec", fake_exec)
    assert update.run(True, lambda q: "", argv=["--yes"]) == 0
    assert restarts == [(["update", "--yes"], "1", False)]  # the lock is free for the new process
    assert len(_pulls(fake_runner)) == 1
    assert capsys.readouterr().out.count("What changed") == 1


def test_a_personal_only_pull_does_not_restart(fake_home, fake_runner, monkeypatch, tmp_path, capsys):
    _world(monkeypatch)
    monkeypatch.delenv(PULLED, raising=False)
    personal = tmp_path / "personal"
    (personal / ".git").mkdir(parents=True)
    monkeypatch.setenv("LOADOUT_PERSONAL", str(personal))
    _heads(fake_runner, monkeypatch, {str(paths.kit_root()): ["aaa"], str(personal): ["x", "y"]})
    monkeypatch.setattr(update, "_exec", lambda argv: pytest.fail("restarted for a personal-layer pull"))
    assert update.run(True, lambda q: "", argv=["--yes"]) == 0
    assert len(_pulls(fake_runner)) == 2
    assert "personal layer: pulled" in _changed(capsys.readouterr().out)


@pytest.mark.skipif(not os.path.exists("/proc/self/ns/pid"), reason="a dead holder is detected by its pid on Linux only")
def test_a_second_run_after_an_interrupted_one_starts_cleanly(fake_home, fake_runner, monkeypatch):
    _world(monkeypatch)
    monkeypatch.delenv(PULLED, raising=False)
    proc = subprocess.Popen([sys.executable, "-c", ""])
    proc.wait()  # its pid is now free: the holder of the lock below is gone
    lock = paths.state_dir() / maintenance.LOCK
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(json.dumps({"pid": proc.pid, "token": f"{proc.pid}-1", "command": "update",
                                "started": time.time(), "host": socket.gethostname(), "ns": locks._ns()}))
    # the interrupted run had pulled already: this run's pull finds nothing new
    _heads(fake_runner, monkeypatch, {str(paths.kit_root()): ["bbb"]})
    monkeypatch.setattr(update, "_exec", lambda argv: pytest.fail("restarted without a new pull"))
    assert update.run(True, lambda q: "", argv=["--yes"]) == 0
    assert len(_pulls(fake_runner)) == 1
    assert not lock.exists()


def test_a_live_holder_is_not_taken_over(fake_home, fake_runner, monkeypatch, capsys):
    _world(monkeypatch)
    monkeypatch.setattr(locks, "FOREGROUND_LIMIT", 0.1)
    lock = paths.state_dir() / maintenance.LOCK
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(json.dumps({"pid": os.getppid(), "token": "x", "command": "update", "started": time.time(),
                                "host": socket.gethostname()}))
    assert update.run(True, lambda q: "", argv=["--yes"]) == 1
    assert "still running" in capsys.readouterr().out and lock.exists()


def test_what_changed_names_each_backup_with_its_undo(fake_home, fake_runner, monkeypatch, capsys):
    _world(monkeypatch)
    s = fake_home / ".claude" / "settings.json"
    real_link_step = apply.link_step

    def link_step(bk, claude_on, retry_symlinks=False):
        old = fake_home / "old-rule.md"
        old.write_text("x")
        bk.move(old, "a replaced rule")
        return real_link_step(bk, claude_on, retry_symlinks)
    monkeypatch.setattr(apply, "link_step", link_step)
    entry = {"id": "tool", "update": {"posix": [["tool-installer"]], "windows": [["tool-installer"]]}}
    monkeypatch.setattr(maintenance, "find_outdated", lambda: [(entry, (1, 0, 0), (2, 0, 0))])
    monkeypatch.setattr(maintenance.versions, "local_version", lambda e: (2, 0, 0))

    def run(cmd, cwd=None, timeout=300, env=None):
        if cmd[0] == "tool-installer":
            s.write_text('{"installer": true}\n')
        return fake_runner(cmd, cwd, timeout, env)
    monkeypatch.setattr(runner, "run", run)
    assert update.run(True, lambda q: "", argv=["--yes"]) == 0
    changed = _changed(capsys.readouterr().out)
    roots = sorted(p for p in paths.backups_root().iterdir() if p.is_dir())
    assert len(roots) >= 2
    for root in roots:
        assert f"loadout restore {root}" in changed
    assert "tool 1.0.0 -> 2.0.0" in changed


def test_a_failed_step_is_listed_as_failed_with_its_fix(fake_home, fake_runner, monkeypatch, capsys):
    _world(monkeypatch)
    entry = {"id": "tool", "update": {"posix": [["tool-installer"]], "windows": [["tool-installer"]]}}
    monkeypatch.setattr(maintenance, "find_outdated", lambda: [(entry, (1, 0, 0), (2, 0, 0))])
    monkeypatch.setattr(maintenance.versions, "local_version", lambda e: (1, 0, 0))
    fake_runner.responses[("tool-installer",)] = runner.Result(1, "", "network down")
    assert update.run(True, lambda q: "", argv=["--yes"]) == 0
    changed = _changed(capsys.readouterr().out)
    line = next(l for l in changed.splitlines() if "tool" in l and "failed" in l)
    assert "network down" in line and "fix: run loadout update again" in line
    assert "  tool 1.0.0 -> 2.0.0\n" not in changed  # not listed as updated


def test_a_busy_codex_lock_is_listed_as_not_run(fake_home, fake_runner, monkeypatch, capsys):
    _world(monkeypatch, claude=False, codex_on=True)
    monkeypatch.setattr(locks, "FOREGROUND_LIMIT", 0.1)
    held = locks.acquire(codex.LOCK, "bootstrap", 0)
    try:
        assert update.run(True, lambda q: "", argv=["--yes"]) == 0
    finally:
        held.release()
    changed = _changed(capsys.readouterr().out)
    line = next(l for l in changed.splitlines() if "Codex" in l and "not run" in l)
    assert "fix: run loadout update again" in line
    assert "up to date" not in changed


def test_codex_only_touches_no_claude_files(fake_home, fake_runner, monkeypatch, capsys):
    _world(monkeypatch, claude=False, codex_on=True)
    claude = fake_home / ".claude"
    claude.mkdir()
    (claude / "settings.json").write_text("{not json")
    before = sorted((p.relative_to(claude), p.read_bytes()) for p in claude.rglob("*") if p.is_file())
    assert update.run(True, lambda q: "", argv=["--yes"]) == 0
    after = sorted((p.relative_to(claude), p.read_bytes()) for p in claude.rglob("*") if p.is_file())
    assert after == before
    assert not any(c[0] == "claude" for c in fake_runner.calls)
    assert "Claude Code" not in capsys.readouterr().out


def test_no_terminal_and_no_yes_changes_nothing(fake_home, fake_runner, monkeypatch, capsys):
    _world(monkeypatch, claude=False, codex_on=True)
    path = paths.codex_home() / "AGENTS.md"
    path.parent.mkdir(parents=True)
    path.write_text(f"{codex.START}\nold\n{codex.END}\n", encoding="utf-8")
    assert update.run(False, lambda q: pytest.fail("asked"), argv=[]) == 0
    assert path.read_text(encoding="utf-8") == f"{codex.START}\nold\n{codex.END}\n"
    assert update.NO_TERMINAL in capsys.readouterr().out


def test_exec_replaces_the_process_on_posix_and_waits_on_windows(monkeypatch):
    seen = []
    monkeypatch.setattr(os, "execv", lambda exe, args: seen.append(("execv", exe, args)), raising=False)
    class Child:
        def __init__(self, args):
            seen.append(("call", args))

        def wait(self):
            return 3
    monkeypatch.setattr(subprocess, "Popen", Child)
    script = str(paths.kit_root() / "bin" / "loadout")
    update._exec(["update", "--yes"], windows=False)
    assert seen[-1] == ("execv", sys.executable, [sys.executable, script, "update", "--yes"])
    with pytest.raises(SystemExit) as stop:
        update._exec(["update"], windows=True)
    assert stop.value.code == 3 and seen[-1] == ("call", [sys.executable, script, "update"])


# --- review fixes -------------------------------------------------------------------------------------------------

REFUSED = ("error: Your local changes to the following files would be overwritten by merge:\n\tme.md\n"
           "Please commit your changes or stash them before you merge.\nAborting\n")


def test_a_refused_personal_pull_survives_the_restart(fake_home, fake_runner, monkeypatch, tmp_path, capsys):
    _world(monkeypatch)
    monkeypatch.delenv(PULLED, raising=False)
    personal = tmp_path / "personal"
    (personal / ".git").mkdir(parents=True)
    monkeypatch.setenv("LOADOUT_PERSONAL", str(personal))
    kit = str(paths.kit_root())
    _heads(fake_runner, monkeypatch, {kit: ["aaa", "bbb", "bbb"], str(personal): ["x"]})
    fake_runner.responses[("git", "-c", "core.quotePath=false", "-C", str(personal), "pull")] = runner.Result(1, "", REFUSED)
    outputs = []

    def fake_exec(argv):
        capsys.readouterr()  # what the first process printed is gone with it
        code = update.run(True, lambda q: "", argv=argv[1:])
        outputs.append(capsys.readouterr().out)
        return code
    monkeypatch.setattr(update, "_exec", fake_exec)
    assert update.run(True, lambda q: "", argv=["--yes"]) == 0
    changed = _changed(outputs[0])
    line = next(l for l in changed.splitlines() if "personal layer" in l)
    assert "me.md" in line and "commit or stash them in" in line


def test_a_pulled_personal_layer_is_named_after_the_restart(fake_home, fake_runner, monkeypatch, tmp_path, capsys):
    _world(monkeypatch)
    monkeypatch.delenv(PULLED, raising=False)
    personal = tmp_path / "personal"
    (personal / ".git").mkdir(parents=True)
    monkeypatch.setenv("LOADOUT_PERSONAL", str(personal))
    _heads(fake_runner, monkeypatch, {str(paths.kit_root()): ["aaa", "bbb", "bbb"], str(personal): ["x", "y", "y"]})
    outputs = []

    def fake_exec(argv):
        capsys.readouterr()
        code = update.run(True, lambda q: "", argv=argv[1:])
        outputs.append(capsys.readouterr().out)
        return code
    monkeypatch.setattr(update, "_exec", fake_exec)
    update.run(True, lambda q: "", argv=["--yes"])
    assert "personal layer: pulled new commits" in _changed(outputs[0])


@pytest.mark.skipif(os.name == "nt", reason="a dead holder is detected by its pid on POSIX only")
def test_a_dead_pid_in_another_pid_namespace_is_not_taken_over(fake_home, fake_runner, monkeypatch, capsys):
    _world(monkeypatch)
    monkeypatch.setattr(locks, "FOREGROUND_LIMIT", 0.1)
    proc = subprocess.Popen([sys.executable, "-c", ""])
    proc.wait()
    lock = paths.state_dir() / maintenance.LOCK
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(json.dumps({"pid": proc.pid, "token": "t", "command": "update", "started": time.time(),
                                "host": socket.gethostname(), "ns": "another-namespace"}))
    assert update.run(True, lambda q: "", argv=["--yes"]) == 1
    assert lock.exists()


def test_the_claude_refresh_runs_exactly_the_plugins_the_plan_showed(fake_home, fake_runner, monkeypatch):
    _world(monkeypatch)
    from loadout import settings_merge
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: {"enabledPlugins": {"a@m": True, "b@m": True}})
    installed = paths.claude_home() / "plugins" / "installed_plugins.json"
    installed.parent.mkdir(parents=True, exist_ok=True)
    installed.write_text(json.dumps({"plugins": {"a@m": [{"scope": "user"}]}}))

    def install_b(say=None, dry=False, on=None, planned=None):  # the plugin step installs b@m after the plan was shown
        if not dry:
            installed.write_text(json.dumps({"plugins": {"a@m": [{"scope": "user"}], "b@m": [{"scope": "user"}]}}))
        return apply.StepResult("Plugins", "")
    monkeypatch.setattr(apply, "claude_plugins_step", install_b)
    update.run(True, lambda q: "", argv=["--yes"])
    assert [c[3] for c in fake_runner.calls if c[:3] == ["claude", "plugin", "update"]] == ["a@m"]


def test_no_auto_pull_skips_updates_pull_too(fake_home, fake_runner, monkeypatch, capsys):
    _world(monkeypatch)
    monkeypatch.delenv(PULLED, raising=False)
    monkeypatch.setenv("LOADOUT_NO_AUTO_PULL", "1")
    monkeypatch.setattr(update, "_exec", lambda argv: pytest.fail("restarted"))
    assert update.run(True, lambda q: "", argv=["--yes"]) == 0
    assert _pulls(fake_runner) == []
    assert any(l.split() == ["✓", "Pull", "skipped", "(LOADOUT_NO_AUTO_PULL=1)"]
               for l in capsys.readouterr().out.splitlines())


def test_a_failed_tool_command_detail_is_redacted(fake_home, fake_runner, monkeypatch, capsys):
    _world(monkeypatch)
    entry = {"id": "tool", "update": {"posix": [["tool-installer"]], "windows": [["tool-installer"]]}}
    monkeypatch.setattr(maintenance, "find_outdated", lambda: [(entry, (1, 0, 0), (2, 0, 0))])
    monkeypatch.setattr(maintenance.versions, "local_version", lambda e: (1, 0, 0))
    secret = "ghp_" + "a" * 36
    fake_runner.responses[("tool-installer",)] = runner.Result(1, f"token {secret} rejected", "")
    update.run(True, lambda q: "", argv=["--yes"])
    text = capsys.readouterr().out
    assert secret not in text and "rejected" in text


def test_nothing_to_do_says_so(fake_home, fake_runner, monkeypatch, capsys):
    _world(monkeypatch, claude=False, codex_on=False)
    monkeypatch.delenv(PULLED, raising=False)
    _heads(fake_runner, monkeypatch, {str(paths.kit_root()): ["aaa"]})
    monkeypatch.setattr(update, "_exec", lambda argv: pytest.fail("restarted"))
    update.run(True, lambda q: "", argv=["--yes"])  # the first run may write the launcher
    capsys.readouterr()
    assert update.run(True, lambda q: "", argv=["--yes"]) == 0
    assert _changed(capsys.readouterr().out).strip() == "nothing: everything was already current"


def test_ctrl_c_in_the_windows_child_exits_with_its_code(monkeypatch):
    class Child:
        def __init__(self, args):
            self.n = 0

        def wait(self):
            self.n += 1
            if self.n == 1:
                raise KeyboardInterrupt
            return 130  # the interrupted child's own exit code
    monkeypatch.setattr(subprocess, "Popen", Child)
    with pytest.raises(SystemExit) as stop:
        update._exec(["update"], windows=True)
    assert stop.value.code == 130


# --- final review fixes -------------------------------------------------------------------------------------------

def test_a_kit_pull_by_another_run_during_the_wait_still_restarts(fake_home, fake_runner, monkeypatch):
    _world(monkeypatch)
    monkeypatch.delenv(PULLED, raising=False)
    kit = str(paths.kit_root())
    head = {"now": "aaa"}

    def run(cmd, cwd=None, timeout=300, env=None):
        if cmd[:2] == ["git", "-C"] and cmd[3:] == ["rev-parse", "HEAD"] and cmd[2] == kit:
            fake_runner.calls.append(list(cmd))
            return runner.Result(0, head["now"] + "\n", "")
        return fake_runner(cmd, cwd, timeout, env)
    monkeypatch.setattr(runner, "run", run)
    real_acquire = maintenance._acquire_lock

    def acquire(command="maintain", wait=0):  # the daily sync pulled while this run waited for the lock
        head["now"] = "bbb"
        return real_acquire(command, wait)
    monkeypatch.setattr(maintenance, "_acquire_lock", acquire)
    restarts = []
    monkeypatch.setattr(update, "_exec", lambda argv: restarts.append(list(argv)) or 0)
    assert update.run(True, lambda q: "", argv=["--yes"]) == 0
    assert restarts == [["update", "--yes"]]


def test_ctrl_c_on_windows_waits_for_the_child_to_release_its_locks(monkeypatch):
    monkeypatch.setattr(subprocess, "call", lambda *a, **k: pytest.fail("the child can be killed mid-cleanup"))
    waits = []

    class Child:
        def __init__(self, args):
            self.args = args

        def wait(self):
            waits.append(1)
            if len(waits) < 3:  # Ctrl+C twice while the child runs its finally
                raise KeyboardInterrupt
            return 7
    monkeypatch.setattr(subprocess, "Popen", Child)
    with pytest.raises(SystemExit) as stop:
        update._exec(["update"], windows=True)
    assert stop.value.code == 7 and len(waits) == 3


def test_the_restart_marker_does_not_reach_child_processes(monkeypatch):
    monkeypatch.setenv(PULLED, "personal")
    probe = [sys.executable, "-c", f"import os; print(os.environ.get({PULLED!r}))"]
    assert runner.run(probe, timeout=60).stdout.strip() == "None"
    assert runner.run(probe, timeout=60, env={**os.environ, "X": "1"}).stdout.strip() == "None"
    assert os.environ[PULLED] == "personal"  # the process itself keeps it (a second update in it neither pulls nor restarts)


def test_a_missing_launcher_after_the_pull_is_a_plain_message(monkeypatch, capsys):
    def gone(exe, args):
        raise FileNotFoundError(2, "No such file or directory")
    monkeypatch.setattr(os, "execv", gone, raising=False)
    with pytest.raises(SystemExit) as stop:
        update._exec(["update"], windows=False)
    assert stop.value.code == 1
    assert capsys.readouterr().out.strip().endswith("run loadout update again")


@pytest.mark.parametrize("windows", [False, True])
def test_no_test_can_restart_into_the_real_loadout(windows):
    """conftest guards the restart: a test that forgets to fake it fails instead of running the real launcher."""
    with pytest.raises(pytest.fail.Exception, match="restart"):
        update._exec(["update"], windows=windows)


def test_an_offline_pull_is_listed_as_not_refreshed(fake_home, fake_runner, monkeypatch, capsys):
    _world(monkeypatch)
    monkeypatch.delenv(PULLED, raising=False)
    personal = paths.personal_root()
    (personal / ".git").mkdir(parents=True)
    token = "ghp_" + "abcdefghijklmnopqrstuvwxyz0123456789"  # built, so the repo scan finds no literal token
    fake_runner.responses[("git", "-c", "core.quotePath=false", "-C", str(personal), "pull")] = runner.Result(
        128, "", f"fatal: unable to access 'https://jonas:{token}@github.com/x/y.git/': Could not resolve host\n")
    _heads(fake_runner, monkeypatch, {str(paths.kit_root()): ["aaa"], str(personal): ["ppp"]})
    assert update.run(True, lambda q: "", argv=["--yes"]) == 0
    text = capsys.readouterr().out
    assert "ghp_" not in text and "Personal layer: up to date" not in text
    changed = _changed(text)
    line = next(l for l in changed.splitlines() if "not refreshed" in l)
    assert str(personal) in line and "Could not resolve host" in line and "again when online" in line
    assert maintenance.paused() == {}  # still no pause and no notice (the daily sync stays quiet)
    assert not (paths.state_dir() / "pending-notice").exists()


def test_a_failed_tool_install_is_redacted(fake_home, fake_runner, monkeypatch, capsys):
    _world(monkeypatch)
    token = "ghp_" + "abcdefghijklmnopqrstuvwxyz0123456789"  # built, so the repo scan finds no literal token
    entry = {"id": "newtool"}
    monkeypatch.setattr(bootstrap, "missing_tools", lambda *a, **k: [(entry, [["newtool-installer"]], False)])
    fake_runner.missing.add("newtool")  # still missing after its installer failed
    fake_runner.responses[("newtool-installer",)] = runner.Result(
        1, "", f"fatal: could not read https://jonas:{token}@github.com/x/y.git\n")
    assert update.run(True, lambda q: "", argv=["--yes"]) == 0
    changed = _changed(capsys.readouterr().out)
    line = next(l for l in changed.splitlines() if "newtool" in l)
    assert "ghp_" not in line and "github.com/x/y.git" in line


def test_an_offline_personal_pull_survives_the_kit_restart(fake_home, fake_runner, monkeypatch, capsys):
    _world(monkeypatch)
    monkeypatch.delenv(PULLED, raising=False)
    personal = paths.personal_root()
    (personal / ".git").mkdir(parents=True)
    fake_runner.responses[("git", "-c", "core.quotePath=false", "-C", str(personal), "pull")] = runner.Result(
        128, "", "ssh: connect to host github.com: Connection timed out\n")
    _heads(fake_runner, monkeypatch, {str(paths.kit_root()): ["aaa", "bbb", "bbb"], str(personal): ["ppp"]})

    def fake_exec(argv):
        return update.run(True, lambda q: "", argv=argv[1:])  # the new process
    monkeypatch.setattr(update, "_exec", fake_exec)
    assert update.run(True, lambda q: "", argv=["--yes"]) == 0
    changed = _changed(capsys.readouterr().out)
    line = next(l for l in changed.splitlines() if "not refreshed" in l)
    assert str(personal) in line and "Connection timed out" in line and "again when online" in line
    assert "kit: pulled new commits" in changed


def test_a_failed_prerequisite_leaves_its_dependents_unattempted(fake_home, fake_runner, monkeypatch, capsys):
    _world(monkeypatch)
    mise, ra = {"id": "mise", "helper": True}, {"id": "rust-analyzer", "needs": ["mise"]}
    monkeypatch.setattr(bootstrap, "missing_tools", lambda *a, **k: [(mise, [["mise-installer"]], False),
                                                                     (ra, [["mise", "use", "-g", "rust-analyzer"]], False)])
    fake_runner.missing.update({"mise", "rust-analyzer"})
    fake_runner.responses[("mise-installer",)] = runner.Result(1, "", "download failed")
    assert update.run(True, lambda q: "", argv=["--yes"]) == 0
    assert ["mise", "use", "-g", "rust-analyzer"] not in fake_runner.calls
    changed = _changed(capsys.readouterr().out)
    assert "rust-analyzer: not attempted: mise failed" in changed


def test_a_refused_codex_change_is_listed_not_called_current(fake_home, fake_runner, monkeypatch, capsys):
    _world(monkeypatch, claude=False, codex_on=True)
    path = paths.codex_home() / "AGENTS.md"
    path.parent.mkdir(parents=True)
    path.write_text(f"# mine\n{codex.START}\nold\n{codex.START}\n", encoding="utf-8")  # unbalanced markers
    assert update.run(True, lambda q: "", argv=["--yes"]) == 0
    changed = _changed(capsys.readouterr().out)
    assert "everything was already current" not in changed
    line = next(l for l in changed.splitlines() if "AGENTS.md" in l)
    assert "markers are unbalanced" in line and "fix:" in line


def test_a_value_the_user_kept_is_not_a_failure(fake_home, fake_runner, monkeypatch, capsys):
    _world(monkeypatch, claude=False, codex_on=True)
    monkeypatch.delenv(PULLED, raising=False)  # not a restarted run: nothing pulled to report
    _heads(fake_runner, monkeypatch, {str(paths.kit_root()): ["aaa"]})
    update.run(True, lambda q: "", argv=["--yes"])  # the first run sets Codex up
    monkeypatch.setattr(codex, "apply_config", lambda bk, dry_run=False: [
        "model: left as is in config.toml (your value)"])
    capsys.readouterr()
    assert update.run(True, lambda q: "", argv=["--yes"]) == 0
    changed = _changed(capsys.readouterr().out)
    assert "left as is" not in changed and "fix:" not in changed
    assert "nothing: everything was already current" in changed


@pytest.mark.parametrize("offline", ["personal layer", "kit"])
def test_an_offline_checkout_leaves_the_daily_pull_due(fake_home, fake_runner, monkeypatch, offline):
    _world(monkeypatch)
    monkeypatch.delenv(PULLED, raising=False)
    personal = paths.personal_root()
    (personal / ".git").mkdir(parents=True)
    root = personal if offline == "personal layer" else paths.kit_root()
    fake_runner.responses[("git", "-c", "core.quotePath=false", "-C", str(root), "pull")] = runner.Result(
        128, "", "fatal: unable to access 'https://github.com/x/y.git/': Could not resolve host\n")
    _heads(fake_runner, monkeypatch, {str(paths.kit_root()): ["aaa"], str(personal): ["ppp"]})
    assert update.run(True, lambda q: "", argv=["--yes"]) == 0
    assert not (paths.state_dir() / "last-pull").exists()  # the background sync tries again soon


@pytest.mark.parametrize("key,reason", [(("symbolic-ref",), "detached HEAD"),
                                        (("rev-parse", "--abbrev-ref"), "no upstream branch")])
def test_a_checkout_with_nothing_to_follow_is_listed_as_not_refreshed(fake_home, fake_runner, monkeypatch, capsys,
                                                                      key, reason):
    _world(monkeypatch)
    monkeypatch.delenv(PULLED, raising=False)
    personal = paths.personal_root()
    (personal / ".git").mkdir(parents=True)
    fake_runner.responses[("git", "-C", str(personal), *key)] = runner.Result(1, "", "")
    _heads(fake_runner, monkeypatch, {str(paths.kit_root()): ["aaa"], str(personal): ["ppp"]})
    assert update.run(True, lambda q: "", argv=["--yes"]) == 0
    text = capsys.readouterr().out
    assert not [l for l in text.splitlines() if "Personal layer" in l and "up to date" in l]
    changed = _changed(text)
    line = next(l for l in changed.splitlines() if "not refreshed" in l)
    assert str(personal) in line and reason in line and "upstream" in line
    assert "everything was already current" not in changed
    assert maintenance.paused() == {} and not (paths.state_dir() / "pending-notice").exists()  # the daily sync stays quiet


def test_a_personal_layer_with_nothing_to_follow_survives_the_kit_restart(fake_home, fake_runner, monkeypatch, capsys):
    _world(monkeypatch)
    monkeypatch.delenv(PULLED, raising=False)
    personal = paths.personal_root()
    (personal / ".git").mkdir(parents=True)
    fake_runner.responses[("git", "-C", str(personal), "symbolic-ref")] = runner.Result(1, "", "")
    _heads(fake_runner, monkeypatch, {str(paths.kit_root()): ["aaa", "bbb", "bbb"], str(personal): ["ppp"]})
    monkeypatch.setattr(update, "_exec", lambda argv: update.run(True, lambda q: "", argv=argv[1:]))
    assert update.run(True, lambda q: "", argv=["--yes"]) == 0
    changed = _changed(capsys.readouterr().out)
    line = next(l for l in changed.splitlines() if "not refreshed" in l)
    assert str(personal) in line and "detached HEAD" in line and "upstream" in line
    assert "kit: pulled new commits" in changed
