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
    kit = _kit(tmp_path, monkeypatch)  # a fresh install: the script checked out a release
    fake_runner.responses[_git(kit, "ls-remote")] = runner.Result(0, LS, "")
    fake_runner.responses[_git(kit, "describe")] = runner.Result(0, "v0.2.0\n", "")
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
    fake_runner.responses[_git(kit, "describe")] = runner.Result(0, "v0.2.0\n", "")
    bootstrap._channel_step("stable", Backup(description="bootstrap"))
    assert channels.get() == "stable"


def test_offline_explicit_stable_off_a_release_stays_dev(fake_home, fake_runner, tmp_path, monkeypatch, capsys):
    kit = _kit(tmp_path, monkeypatch)
    fake_runner.responses[_git(kit, "ls-remote")] = runner.Result(1, "", "offline")
    fake_runner.responses[_git(kit, "describe")] = runner.Result(128, "", "no tag")
    bootstrap._channel_step("stable", Backup(description="bootstrap"))
    assert "you stay on dev" in capsys.readouterr().out and channels.get() is None


def test_bootstrap_never_follows_a_withdrawal_on_its_own(fake_home, fake_runner, tmp_path, monkeypatch, capsys):
    """A withdrawal names a release to use; the move goes through loadout update's plan and yes, never bootstrap."""
    kit = _kit(tmp_path, monkeypatch)
    _withdrawn(fake_runner, kit)
    bootstrap._channel_step("stable", Backup(description="bootstrap"))  # the autouse fixture fails on a restart
    assert not [c for c in fake_runner.calls if c[3:4] == ["checkout"]]
    assert "the release you run (v0.3.0) was withdrawn: broken; run loadout update (to 0.2.0)" in capsys.readouterr().out


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
    monkeypatch.setattr(sys, "argv", ["loadout", "bootstrap", "--yes"])
    calls = []
    monkeypatch.setattr(runner, "continue_in", lambda cmd, **k: calls.append(cmd) or (_ for _ in ()).throw(SystemExit(0)))
    with pytest.raises(SystemExit):
        bootstrap._continue_once(kit)
    assert calls == [[sys.executable, str(kit / "bin" / "loadout"), "bootstrap", "--yes"]]
    assert bootstrap.MOVED in runner.PROCESS_ONLY
    # the continued process sees the marker: no second re-exec
    calls.clear()
    bootstrap._continue_once(kit)
    assert calls == []


def test_a_moved_tag_is_reported(fake_home, fake_runner, tmp_path, monkeypatch, capsys):
    kit = _kit(tmp_path, monkeypatch)
    channels.record_seen({"v0.2.0": "c" * 40}, 1.0)
    fake_runner.responses[_git(kit, "ls-remote")] = runner.Result(0, LS, "")
    notes = []
    monkeypatch.setattr(channels.maintenance, "notify", notes.append)
    bootstrap._channel_step("stable", Backup(description="bootstrap"))
    assert any("v0.2.0" in n and "changed after it was released" in n for n in notes)


# --- an explicit --channel stable on an existing dev install does what loadout channel stable does ---

HEAD = "c" * 40


def _dev_install(fake_runner, kit, when, status=""):
    """A kit on main, on no release; the remote has v0.2.0 and v0.3.0, both with the tagger date `when`."""
    fake_runner.responses[_git(kit, "ls-remote")] = runner.Result(0, LS, "")
    fake_runner.responses[_git(kit, "describe")] = runner.Result(128, "", "no tag")
    fake_runner.responses[_git(kit, "show")] = runner.Result(0, '{"urgent": [], "withdrawn": []}', "")
    fmt = "--format=%(taggerdate:unix)"
    for tag in ("v0.2.0", "v0.3.0"):
        fake_runner.responses[_git(kit, "for-each-ref", fmt, f"refs/tags/{tag}")] = runner.Result(0, f"{when}\n", "")
    fake_runner.responses[_git(kit, "rev-parse", "HEAD")] = runner.Result(0, HEAD + "\n", "")
    fake_runner.responses[_git(kit, "rev-parse", "FETCH_HEAD^{commit}")] = runner.Result(0, NEW + "\n", "")
    fake_runner.responses[_git(kit, "symbolic-ref")] = runner.Result(0, "main\n", "")
    fake_runner.responses[_git(kit, "status")] = runner.Result(0, status, "")


def test_explicit_stable_on_a_dev_install_moves_with_an_undo_and_continues(fake_home, fake_runner, tmp_path,
                                                                            monkeypatch):
    import sys
    import time
    kit = _kit(tmp_path, monkeypatch)
    _dev_install(fake_runner, kit, int(time.time()) - 5 * 86400)
    monkeypatch.setattr(sys, "argv", ["loadout", "bootstrap", "--channel", "stable"])
    calls = []
    monkeypatch.setattr(runner, "continue_in", lambda cmd, **k: calls.append(cmd) or (_ for _ in ()).throw(SystemExit(0)))
    bk = Backup(description="bootstrap")
    with pytest.raises(SystemExit):
        bootstrap._channel_step("stable", bk)
    assert [c for c in fake_runner.calls if c[3:4] == ["checkout"]] == [[*_git(kit), "checkout", "--detach", NEW]]
    assert [*_git(kit), "fetch", "origin", "main"] in fake_runner.calls  # local commits measured against main
    assert channels.get() == "stable"
    steps = json.loads((bk.root / "manifest.json").read_text())["steps"]
    assert {"run": [*_git(kit), "switch", "main"]} in [s.get("undo") for s in steps]
    assert calls == [[sys.executable, str(kit / "bin" / "loadout"), "bootstrap", "--channel", "stable"]]


def test_explicit_stable_with_no_release_ready_stays_dev(fake_home, fake_runner, tmp_path, monkeypatch, capsys):
    import time
    kit = _kit(tmp_path, monkeypatch)
    _dev_install(fake_runner, kit, int(time.time()) - 3600)
    bootstrap._channel_step("stable", Backup(description="bootstrap"))
    assert "no release is ready yet; you stay on dev" in capsys.readouterr().out
    assert not (paths.state_dir() / "channel.json").exists()
    assert not [c for c in fake_runner.calls if c[3:4] in (["checkout"], ["switch"])]


def test_explicit_stable_refused_move_leaves_the_channel_as_it_was(fake_home, fake_runner, tmp_path, monkeypatch,
                                                                     capsys):
    import time
    kit = _kit(tmp_path, monkeypatch)
    channels.set_channel("dev")
    _dev_install(fake_runner, kit, int(time.time()) - 5 * 86400, status=" M cli/loadout/x.py\n")
    bootstrap._channel_step("stable", Backup(description="bootstrap"))
    assert "cli/loadout/x.py" in capsys.readouterr().out and channels.get() == "dev"
    assert not [c for c in fake_runner.calls if c[3:4] == ["checkout"]]
