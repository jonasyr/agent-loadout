"""bootstrap records the channel, seeds releases.json and leaves a withdrawn release (release channels, task 7)."""
import json
import os

import pytest

from loadout import bootstrap, channels, paths, runner
from loadout.backup import Backup

OLD, NEW = "a" * 40, "b" * 40
LS = f"{OLD}\trefs/tags/v0.2.0\n{NEW}\trefs/tags/v0.3.0\n"


@pytest.fixture(autouse=True)
def no_real_restart(monkeypatch):
    """A test must never replace the pytest process: continue_in is faked (the restart test reads its calls)."""
    monkeypatch.delenv(bootstrap.MOVED, raising=False)
    monkeypatch.setattr(runner, "continue_in", lambda cmd, **k: pytest.fail(f"unexpected restart {cmd}"))
    yield
    os.environ.pop(bootstrap.MOVED, None)  # the step sets it for the process itself


def _git(kit, *args):
    return ("git", "-C", str(kit), *args)


def _kit(tmp_path, monkeypatch):
    kit = tmp_path / "kit"
    (kit / ".git").mkdir(parents=True)
    monkeypatch.setenv("LOADOUT_ROOT", str(kit))
    return kit


def _releases():
    return json.loads((paths.state_dir() / "releases.json").read_text())


def test_bootstrap_writes_channel_and_seeds_releases(fake_home, fake_runner, tmp_path, monkeypatch):
    kit = _kit(tmp_path, monkeypatch)
    fake_runner.responses[_git(kit, "ls-remote")] = runner.Result(0, LS, "")
    fake_runner.responses[_git(kit, "describe")] = runner.Result(1, "", "")
    bk = Backup(description="bootstrap")
    bootstrap._channel_step("stable", bk)
    assert channels.get() == "stable"
    tags = _releases()["tags"]
    assert tags["v0.2.0"]["sha"] == OLD and tags["v0.3.0"]["sha"] == NEW and tags["v0.3.0"]["first_seen"] > 0
    assert not bk.empty  # the channel file is in the run's backup


def test_dev_channel_is_written_and_no_status_is_read(fake_home, fake_runner, tmp_path, monkeypatch):
    kit = _kit(tmp_path, monkeypatch)
    fake_runner.responses[_git(kit, "ls-remote")] = runner.Result(0, LS, "")
    bootstrap._channel_step("dev", Backup(description="bootstrap"))
    assert channels.get() == "dev"
    assert not [c for c in fake_runner.calls if c[3:4] in (["show"], ["checkout"])]


def test_offline_remote_still_writes_the_channel(fake_home, fake_runner, tmp_path, monkeypatch):
    kit = _kit(tmp_path, monkeypatch)
    fake_runner.responses[_git(kit, "ls-remote")] = runner.Result(1, "", "offline")
    bootstrap._channel_step("stable", Backup(description="bootstrap"))
    assert channels.get() == "stable"


def test_bootstrap_moves_off_a_withdrawn_release(fake_home, fake_runner, tmp_path, monkeypatch):
    kit = _kit(tmp_path, monkeypatch)
    status = {"withdrawn": [{"version": "0.3.0", "reason": "broken", "use": "0.2.0"}]}
    fake_runner.responses[_git(kit, "ls-remote")] = runner.Result(0, LS, "")
    fake_runner.responses[_git(kit, "describe")] = runner.Result(0, "v0.3.0\n", "")
    fake_runner.responses[_git(kit, "show")] = runner.Result(0, json.dumps(status), "")
    fake_runner.responses[_git(kit, "rev-parse", "HEAD")] = runner.Result(0, NEW + "\n", "")
    fake_runner.responses[_git(kit, "rev-parse", "FETCH_HEAD^{commit}")] = runner.Result(0, OLD + "\n", "")
    fake_runner.responses[_git(kit, "symbolic-ref")] = runner.Result(1, "", "")
    monkeypatch.setenv(bootstrap.MOVED, "1")  # the restart itself is tested below
    bootstrap._channel_step("stable", Backup(description="bootstrap"))
    assert ["git", "-C", str(kit), "checkout", "--detach", OLD] in fake_runner.calls


def test_a_current_release_is_not_moved(fake_home, fake_runner, tmp_path, monkeypatch):
    kit = _kit(tmp_path, monkeypatch)
    fake_runner.responses[_git(kit, "ls-remote")] = runner.Result(0, LS, "")
    fake_runner.responses[_git(kit, "describe")] = runner.Result(0, "v0.3.0\n", "")
    fake_runner.responses[_git(kit, "show")] = runner.Result(0, json.dumps({"urgent": ["0.3.0"]}), "")
    bootstrap._channel_step("stable", Backup(description="bootstrap"))
    assert not [c for c in fake_runner.calls if c[3:4] == ["checkout"]]


def test_a_rerun_without_channel_on_a_machine_without_one_writes_nothing(fake_home, fake_runner, tmp_path, monkeypatch):
    kit = _kit(tmp_path, monkeypatch)
    bk = Backup(description="bootstrap")
    bootstrap._channel_step(None, bk)
    assert not (paths.state_dir() / "channel.json").exists() and bk.empty
    assert not fake_runner.calls


def test_a_rerun_without_channel_keeps_the_stored_one(fake_home, fake_runner, tmp_path, monkeypatch):
    kit = _kit(tmp_path, monkeypatch)
    channels.set_channel("dev")
    fake_runner.responses[_git(kit, "ls-remote")] = runner.Result(0, LS, "")
    bootstrap._channel_step(None, Backup(description="bootstrap"))
    assert channels.get() == "dev" and "v0.3.0" in _releases()["tags"]


def _withdrawn(fake_runner, kit):
    status = {"withdrawn": [{"version": "0.3.0", "reason": "broken", "use": "0.2.0"}]}
    fake_runner.responses[_git(kit, "ls-remote")] = runner.Result(0, LS, "")
    fake_runner.responses[_git(kit, "describe")] = runner.Result(0, "v0.3.0\n", "")
    fake_runner.responses[_git(kit, "show")] = runner.Result(0, json.dumps(status), "")
    fake_runner.responses[_git(kit, "rev-parse", "HEAD")] = runner.Result(0, NEW + "\n", "")
    fake_runner.responses[_git(kit, "rev-parse", "FETCH_HEAD^{commit}")] = runner.Result(0, OLD + "\n", "")
    fake_runner.responses[_git(kit, "symbolic-ref")] = runner.Result(1, "", "")


def test_after_a_move_bootstrap_continues_in_the_new_code_once(fake_home, fake_runner, tmp_path, monkeypatch):
    import sys
    kit = _kit(tmp_path, monkeypatch)
    _withdrawn(fake_runner, kit)
    monkeypatch.setattr(sys, "argv", ["loadout", "bootstrap", "--yes"])
    monkeypatch.delenv(bootstrap.MOVED, raising=False)
    calls = []
    monkeypatch.setattr(runner, "continue_in", lambda cmd, **k: calls.append(cmd) or (_ for _ in ()).throw(SystemExit(0)))
    try:
        bootstrap._channel_step("stable", Backup(description="bootstrap"))
    except SystemExit:
        pass
    assert calls == [[sys.executable, str(kit / "bin" / "loadout"), "bootstrap", "--yes"]]
    assert bootstrap.MOVED in runner.PROCESS_ONLY
    # the continued process sees the marker: no second re-exec
    calls.clear()
    bootstrap._channel_step("stable", Backup(description="bootstrap"))
    assert calls == []


def test_a_moved_tag_is_reported(fake_home, fake_runner, tmp_path, monkeypatch, capsys):
    kit = _kit(tmp_path, monkeypatch)
    channels.record_seen({"v0.2.0": "c" * 40}, 1.0)
    fake_runner.responses[_git(kit, "ls-remote")] = runner.Result(0, LS, "")
    notes = []
    monkeypatch.setattr(channels.maintenance, "notify", notes.append)
    bootstrap._channel_step("stable", Backup(description="bootstrap"))
    assert any("v0.2.0" in n and "changed after it was released" in n for n in notes)
