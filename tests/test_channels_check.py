"""loadout check: the Channel row reads only local state (channel.json, releases.json, git describe)."""
import json
import time

from loadout import channels, check, maintenance, paths, runner


def _state(**releases):
    d = paths.state_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / "releases.json").write_text(json.dumps(releases))


def _on(fake_runner, tag):
    fake_runner.responses[("git", "-C", str(paths.kit_root()), "describe", "--tags", "--exact-match", "HEAD")] = (
        runner.Result(0, tag + "\n", "") if tag else runner.Result(128, "", "no tag"))


def _row():
    (res,) = check._channel()
    assert res.name == "Channel"
    return res


def test_dev_row_is_ok(fake_home, fake_runner):
    res = _row()
    assert res.ok and res.info == "dev, main"


def test_stable_row_is_ok_on_the_newest(fake_home, fake_runner):
    channels.set_channel("stable")
    _on(fake_runner, "v0.3.0")
    res = _row()
    assert res.ok and res.info == "stable, v0.3.0"


def test_stable_row_warns_when_a_newer_release_is_available(fake_home, fake_runner):
    channels.set_channel("stable")
    _on(fake_runner, "v0.3.0")
    _state(tags={"v0.4.0": {"sha": "a" * 40, "first_seen": time.time() - 10 * maintenance.DAY}})
    res = _row()
    assert not res.ok and res.severity == "warn"
    assert res.detail == "stable, v0.3.0: v0.4.0 is available" and res.fix == "loadout update"


def test_a_release_still_soaking_is_not_announced(fake_home, fake_runner):
    channels.set_channel("stable")
    _on(fake_runner, "v0.3.0")
    _state(tags={"v0.4.0": {"sha": "a" * 40, "first_seen": time.time()}})
    assert _row().ok


def test_withdrawn_current_release_warns(fake_home, fake_runner):
    channels.set_channel("stable")
    _on(fake_runner, "v0.3.0")
    _state(status={"urgent": [], "withdrawn": {"0.3.0": {"reason": "breaks restore", "use": "0.3.1"}}})
    res = _row()
    assert not res.ok and res.severity == "warn"
    assert res.detail == "stable, v0.3.0 was withdrawn: breaks restore"
    assert "loadout update" in res.fix and "loadout restore" in res.fix


def test_moved_release_warns(fake_home, fake_runner):
    channels.set_channel("stable")
    _on(fake_runner, "v0.3.0")
    _state(tags={"v0.4.0": {"sha": "a" * 40, "first_seen": 1, "moved": True}})
    res = _row()
    assert not res.ok and res.severity == "warn"
    assert res.detail == "release v0.4.0 was changed after it was released"
    assert "maintainer" in res.fix


def test_the_row_runs_no_network_git(fake_home, fake_runner):
    channels.set_channel("stable")
    _on(fake_runner, "v0.3.0")
    _row()
    assert not any("fetch" in c or "ls-remote" in c for c in fake_runner.calls)
