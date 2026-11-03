import json

from loadout import channels, maintenance as m, paths, runner

T = 1_800_000_000.0
SHA_A, SHA_B = "a" * 40, "b" * 40
CHANGELOG = "# Changelog\n\n## 0.3.0 - 2026-11-01\n\n- one\n- two\n* three\n- four\n\n## 0.2.0\n\n- old\n"


def _kit(tmp_path, monkeypatch):
    kit = tmp_path / "kit"
    (kit / ".git").mkdir(parents=True)
    monkeypatch.setenv("LOADOUT_ROOT", str(kit))
    return kit


def _git(kit, *args):
    return ("git", "-C", str(kit), *args)


def _remote(fake_runner, kit, tags, current=None, status=None, changelog=CHANGELOG):
    lines = "".join(f"{sha}\trefs/tags/{name}\n" for name, sha in tags.items())
    fake_runner.responses[_git(kit, "ls-remote", "--tags", "origin")] = runner.Result(0, lines, "")
    fake_runner.responses[_git(kit, "describe")] = (runner.Result(0, current + "\n", "") if current
                                                    else runner.Result(128, "", "no tag"))
    fake_runner.responses[_git(kit, "fetch", "origin", "main")] = runner.Result(0, "", "")
    fake_runner.responses[_git(kit, "show", "FETCH_HEAD:release-status.json")] = \
        runner.Result(0, json.dumps(status or {}), "")
    fake_runner.responses[_git(kit, "fetch", "origin", "tag")] = runner.Result(0, "", "")
    fake_runner.responses[_git(kit, "show", "v0.3.0:CHANGELOG.md")] = runner.Result(0, changelog, "")


def _notices():
    path = paths.state_dir() / "pending-notice"
    return path.read_text().splitlines() if path.exists() else []


def test_release_check_offline_records_nothing(fake_home, fake_runner, tmp_path, monkeypatch):
    kit = _kit(tmp_path, monkeypatch)
    fake_runner.responses[_git(kit, "ls-remote")] = runner.Result(128, "", "unable to access")
    monkeypatch.setenv("LOADOUT_NO_AUTO_PULL", "1")
    channels.set_channel("stable")
    monkeypatch.setattr(m, "find_outdated", lambda: [])
    m.touch("last-update-check", T)
    m.maintain(T)
    assert not (paths.state_dir() / "releases.json").exists()
    assert _notices() == []
    assert not m.is_due("last-release-check", m.DAY, T + 1)


def test_stable_gets_one_notice_per_release(fake_home, fake_runner, tmp_path, monkeypatch):
    kit = _kit(tmp_path, monkeypatch)
    channels.set_channel("stable")
    channels.record_seen({"v0.3.0": SHA_A}, T - 3 * m.DAY)
    _remote(fake_runner, kit, {"v0.3.0": SHA_A}, current="v0.2.0")
    channels.check_releases(T)
    notes = _notices()
    assert len(notes) == 1 and "loadout 0.3.0 is available" in notes[0]
    assert "(since 0.2.0: one; two; three); run loadout update" in notes[0] and "four" not in notes[0]
    channels.check_releases(T + m.DAY)
    assert _notices() == notes


def test_dev_records_but_never_notifies(fake_home, fake_runner, tmp_path, monkeypatch):
    kit = _kit(tmp_path, monkeypatch)
    channels.set_channel("dev")
    _remote(fake_runner, kit, {"v0.3.0": SHA_A})
    channels.check_releases(T)
    assert "v0.3.0" in json.loads((paths.state_dir() / "releases.json").read_text())["tags"]
    assert _notices() == []
    assert not any("release-status.json" in " ".join(c) for c in fake_runner.calls)


def test_withdrawn_current_release_notice_names_the_fix(fake_home, fake_runner, tmp_path, monkeypatch):
    kit = _kit(tmp_path, monkeypatch)
    channels.set_channel("stable")
    status = {"withdrawn": [{"version": "0.2.0", "reason": "breaks Codex", "use": "0.2.1"}]}
    _remote(fake_runner, kit, {"v0.2.0": SHA_A}, current="v0.2.0", status=status)
    channels.check_releases(T)
    assert _notices() == ["loadout: the release you run (v0.2.0) was withdrawn: breaks Codex; "
                          "run loadout update (to 0.2.1)"]
    channels.check_releases(T + m.DAY)
    assert len(_notices()) == 1
    assert channels.last_status().withdrawn["0.2.0"]["use"] == "0.2.1"


def test_withdrawn_without_fix_says_restore(fake_home, fake_runner, tmp_path, monkeypatch):
    kit = _kit(tmp_path, monkeypatch)
    channels.set_channel("stable")
    status = {"withdrawn": [{"version": "0.2.0", "reason": "bad"}]}
    _remote(fake_runner, kit, {"v0.2.0": SHA_A}, current="v0.2.0", status=status)
    channels.check_releases(T)
    assert _notices()[0].endswith("run loadout restore")


def test_moved_tag_alarm_is_queued(fake_home, fake_runner, tmp_path, monkeypatch):
    kit = _kit(tmp_path, monkeypatch)
    channels.set_channel("dev")
    channels.record_seen({"v0.3.0": SHA_A}, T - 10)
    _remote(fake_runner, kit, {"v0.3.0": SHA_B})
    channels.check_releases(T)
    assert _notices() == ["loadout: release v0.3.0 was changed after it was released; it is not offered. "
                          "Tell the maintainer."]
    channels.check_releases(T + 1)
    assert len(_notices()) == 1


def test_changelog_lines_failure_is_empty(fake_runner, tmp_path):
    fake_runner.responses[_git(tmp_path, "fetch", "origin", "tag")] = runner.Result(1, "", "x")
    assert channels.changelog_lines(tmp_path, "v0.3.0") == []


def test_changelog_lines_caps_and_limits(fake_runner, tmp_path):
    long = "- " + "x" * 300
    _remote(fake_runner, tmp_path, {}, changelog=f"## 0.3.0\n{long}\n- a\x1b[31m\n- b\n- c\n")
    lines = channels.changelog_lines(tmp_path, "v0.3.0")
    assert len(lines) == 3 and len(lines[0]) == 120 and "\x1b" not in lines[1]


def test_last_status_empty_when_missing(fake_home):
    st = channels.last_status()
    assert st.urgent == set() and st.withdrawn == {}


def test_stable_daily_pull_skips_kit_but_pulls_personal(fake_home, fake_runner, tmp_path, monkeypatch):
    _kit(tmp_path, monkeypatch)
    personal = tmp_path / "personal"
    (personal / ".git").mkdir(parents=True)
    monkeypatch.setenv("LOADOUT_PERSONAL", str(personal))
    channels.set_channel("stable")
    monkeypatch.setattr(m, "find_outdated", lambda: [])
    monkeypatch.setattr(channels, "check_releases", lambda now: None)
    pulled = []
    monkeypatch.setattr(m, "pull", lambda root: pulled.append(root) or m.PullResult())
    m.maintain(T)
    assert pulled == [personal]


def test_dev_daily_pull_still_pulls_kit(fake_home, fake_runner, tmp_path, monkeypatch):
    kit = _kit(tmp_path, monkeypatch)
    channels.set_channel("dev")
    monkeypatch.setattr(m, "find_outdated", lambda: [])
    monkeypatch.setattr(channels, "check_releases", lambda now: None)
    pulled = []
    monkeypatch.setattr(m, "pull", lambda root: pulled.append(root) or m.PullResult())
    m.maintain(T)
    assert kit in pulled


def test_release_check_runs_with_no_auto_pull(fake_home, fake_runner, tmp_path, monkeypatch):
    _kit(tmp_path, monkeypatch)
    monkeypatch.setenv("LOADOUT_NO_AUTO_PULL", "1")
    spawned, checked = [], []
    monkeypatch.setattr(m, "_spawn_background", lambda: spawned.append(1))
    m.touch("last-update-check", T)
    m.session_start(T + 1)
    assert spawned == [1]
    m.touch("last-release-check", T)
    spawned.clear()
    m.session_start(T + 2)
    assert spawned == []
    monkeypatch.setattr(m, "find_outdated", lambda: [])
    monkeypatch.setattr(channels, "check_releases", lambda now: checked.append(now))
    m.maintain(T + 2 * m.DAY)
    assert checked == [T + 2 * m.DAY]
    assert not any("pull" in c for c in fake_runner.calls)


def test_migration_notice_once(fake_home):
    channels.migration_notice()
    channels.migration_notice()
    assert _notices() == ["loadout now has release channels: you are on dev (main). "
                          "For tested releases only: loadout channel stable"]


def test_migration_notice_not_when_channel_set(fake_home):
    channels.set_channel("dev")
    channels.migration_notice()
    assert _notices() == []
