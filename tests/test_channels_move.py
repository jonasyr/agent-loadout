import os

from loadout import backup, channels, runner

SHA = "c" * 40
TAG_SHA = "d" * 40
NOW = 1_800_000_000.0


def _kit(tmp_path, monkeypatch):
    kit = tmp_path / "kit"
    (kit / ".git").mkdir(parents=True)
    monkeypatch.setenv("LOADOUT_ROOT", str(kit))
    return kit


def _git(kit, *args):
    return ("git", "-C", str(kit), *args)


class RecordingBackup:
    def __init__(self, fake_runner):
        self.fake = fake_runner
        self.recorded = []

    def record_command(self, label, undo_cmd, **info):
        self.fake.calls.append(["RECORD", label, *undo_cmd])
        self.recorded.append((label, undo_cmd))


def _verbs(fake):
    return [c[3] if c[:2] == ["git", "-C"] else c[0] for c in fake.calls]


def _ready(fake, kit, tag="v0.3.0", recorded=TAG_SHA, fetched=TAG_SHA, branch=""):
    channels.record_seen({tag: recorded}, NOW)
    fake.responses[_git(kit, "rev-parse", "HEAD")] = runner.Result(0, SHA + "\n", "")
    fake.responses[_git(kit, "rev-parse", "FETCH_HEAD^{commit}")] = runner.Result(0, fetched + "\n", "")
    fake.responses[_git(kit, "symbolic-ref")] = (runner.Result(0, branch + "\n", "") if branch
                                                 else runner.Result(1, "", "not a symbolic ref"))


def test_move_refuses_local_commits_and_edits(fake_home, fake_runner, tmp_path, monkeypatch):
    kit = _kit(tmp_path, monkeypatch)
    bk = RecordingBackup(fake_runner)
    _ready(fake_runner, kit)
    fake_runner.responses[_git(kit, "status")] = runner.Result(0, " M cli/x.py\n?? stray.txt\n", "")
    text = channels.move_to(kit, "v0.3.0", bk)
    assert text.startswith("local changes") and "cli/x.py" in text and "stray.txt" not in text
    assert not {"checkout", "fetch", "RECORD"} & set(_verbs(fake_runner)) and not bk.recorded

    fake_runner.responses[_git(kit, "status")] = runner.Result(0, "", "")
    fake_runner.responses[_git(kit, "log")] = runner.Result(0, "abc1234 wip thing\n", "")
    text = channels.move_to(kit, "v0.3.0", bk)
    assert "commit abc1234 wip thing" in text and not bk.recorded
    assert "checkout" not in _verbs(fake_runner)


def test_move_records_undo_before_checkout(fake_home, fake_runner, tmp_path, monkeypatch):
    kit = _kit(tmp_path, monkeypatch)
    bk = RecordingBackup(fake_runner)
    _ready(fake_runner, kit)
    assert channels.move_to(kit, "v0.3.0", bk) is None
    steps = [c for c in fake_runner.calls if c[3:4] not in (["status"], ["log"])]
    order = [c[3] if c[0] == "git" else c[0] for c in steps]
    assert order.index("fetch") < order.index("RECORD") < order.index("checkout")
    assert order[-1] == "checkout" and order.count("checkout") == 1
    assert bk.recorded == [("kit checkout", ["git", "-C", str(kit), "checkout", "--detach", SHA])]
    assert steps[-1][3:] == ["checkout", "--detach", TAG_SHA]  # the verified sha, not the tag name
    assert ["git", "-C", str(kit), "fetch", "origin", "refs/tags/v0.3.0", "--no-tags"] in fake_runner.calls
    assert backup._allowed_run(bk.recorded[0][1])


def test_undo_on_a_branch_is_a_switch(fake_home, fake_runner, tmp_path, monkeypatch):
    kit = _kit(tmp_path, monkeypatch)
    bk = RecordingBackup(fake_runner)
    _ready(fake_runner, kit, branch="main")
    assert channels.move_to(kit, "v0.3.0", bk, base="origin/main") is None
    assert bk.recorded == [("kit checkout", ["git", "-C", str(kit), "switch", "main"])]
    assert backup._allowed_run(bk.recorded[0][1])
    bk.recorded.clear()
    _ready(fake_runner, kit, branch="--force")  # an odd name falls back to the detached commit
    assert channels.move_to(kit, "v0.3.0", bk) is None
    assert bk.recorded[0][1][3:] == ["checkout", "--detach", SHA]


def test_switch_allowlist(fake_home, tmp_path, monkeypatch):
    kit = _kit(tmp_path, monkeypatch)
    k = str(kit)
    assert backup._allowed_run(["git", "-C", k, "switch", "main"])
    assert backup._allowed_run(["git", "-C", k, "switch", "feat/x-1.2"])
    assert not backup._allowed_run(["git", "-C", str(tmp_path), "switch", "main"])
    for bad in ("-f", "--detach", "../x", "a..b", "x.lock", "x/", "-c", "", "a b", "a//b", "a/-b"):
        assert not backup._allowed_run(["git", "-C", k, "switch", bad]), bad
    assert not backup._allowed_run(["git", "-C", k, "switch", "-f", "main"])
    assert not backup._allowed_run(["git", "-C", k, "switch", "main", "x"])
    assert not backup._allowed_run(["git", "-C", k, "switch"])


def test_dev_checkout_ahead_of_last_tag_is_not_refused_with_origin_main_base(fake_home, fake_runner, tmp_path, monkeypatch):
    kit = _kit(tmp_path, monkeypatch)
    bk = RecordingBackup(fake_runner)
    _ready(fake_runner, kit, branch="main")
    assert channels.move_to(kit, "v0.3.0", bk, base="origin/main") is None
    log = [c for c in fake_runner.calls if c[3:4] == ["log"]]
    assert log and log[0][-3:] == ["HEAD", "--not", "origin/main"]
    # origin/main is fetched first so the base is current
    fetch_main = fake_runner.calls.index(["git", "-C", str(kit), "fetch", "origin", "main"])
    assert fetch_main < fake_runner.calls.index(log[0])
    fake_runner.calls.clear()
    assert channels.move_to(kit, "v0.3.0", bk) is None  # the default base needs no fetch of main
    assert ["git", "-C", str(kit), "fetch", "origin", "main"] not in fake_runner.calls
    assert [c for c in fake_runner.calls if c[3:4] == ["log"]][0][-3:] == ["HEAD", "--not", "--tags"]


def test_change_check_fails_closed(fake_home, fake_runner, tmp_path, monkeypatch):
    kit = _kit(tmp_path, monkeypatch)
    for verb in ("status", "log"):
        bk = RecordingBackup(fake_runner)
        _ready(fake_runner, kit)
        fake_runner.responses[_git(kit, "status")] = runner.Result(0, "", "")
        fake_runner.responses[_git(kit, "log")] = runner.Result(0, "", "")
        fake_runner.responses[_git(kit, verb)] = runner.Result(128, "", "fatal: broken")
        text = channels.move_to(kit, "v0.3.0", bk)
        assert text.startswith("could not check") and "local changes" in text
        assert not bk.recorded and "checkout" not in _verbs(fake_runner)
        assert channels.move_to_dev(kit, bk).startswith("could not check") and not bk.recorded


def test_unknown_moved_or_withdrawn_tag_is_refused(fake_home, fake_runner, tmp_path, monkeypatch):
    kit = _kit(tmp_path, monkeypatch)
    bk = RecordingBackup(fake_runner)
    fake_runner.responses[_git(kit, "rev-parse", "HEAD")] = runner.Result(0, SHA + "\n", "")
    assert "not" in channels.move_to(kit, "v0.3.0", bk)  # never seen
    channels.record_seen({"v0.3.0": TAG_SHA}, NOW)
    channels.record_seen({"v0.3.0": "e" * 40}, NOW + 1)  # moved
    assert "changed after" in channels.move_to(kit, "v0.3.0", bk)
    channels.record_seen({"v0.4.0": TAG_SHA}, NOW)
    channels.store_status(channels.Status(withdrawn={"0.4.0": {"reason": "bad", "use": None}}))
    assert "withdrawn" in channels.move_to(kit, "v0.4.0", bk)
    assert not bk.recorded and not {"fetch", "checkout"} & set(_verbs(fake_runner))


def test_sha_mismatch_is_refused_and_nothing_moves(fake_home, fake_runner, tmp_path, monkeypatch):
    kit = _kit(tmp_path, monkeypatch)
    bk = RecordingBackup(fake_runner)
    _ready(fake_runner, kit, fetched="e" * 40)
    text = channels.move_to(kit, "v0.3.0", bk)
    assert text == "release v0.3.0 does not match what this machine recorded; not moved"
    assert not bk.recorded and "checkout" not in _verbs(fake_runner)


def test_checkout_refusal_is_reported(fake_home, fake_runner, tmp_path, monkeypatch):
    kit = _kit(tmp_path, monkeypatch)
    bk = RecordingBackup(fake_runner)
    _ready(fake_runner, kit)
    err = "error: Your local changes to the following files would be overwritten by checkout:\n\tREADME.md\nAborting"
    fake_runner.responses[_git(kit, "checkout")] = runner.Result(1, "", err)
    text = channels.move_to(kit, "v0.3.0", bk)
    assert "README.md" in text


def test_undo_allowlist_matches_kit_root_resolved(fake_home, tmp_path, monkeypatch):
    kit = _kit(tmp_path, monkeypatch)
    other = tmp_path / "other"
    other.mkdir()

    def cmd(root, sha=SHA, *extra, flag="--detach"):
        return ["git", "-C", str(root), "checkout", flag, sha, *extra]

    assert backup._allowed_run(cmd(kit))
    assert backup._allowed_run(cmd(str(kit) + os.sep))
    assert backup._allowed_run(cmd(kit / "sub" / ".."))
    link = tmp_path / "link"
    link.symlink_to(kit)
    assert backup._allowed_run(cmd(link))
    assert not backup._allowed_run(cmd(other))
    assert not backup._allowed_run(cmd(kit, "abc1234"))
    assert not backup._allowed_run(cmd(kit, flag="--force"))
    assert not backup._allowed_run(cmd(kit, SHA, "--", "x"))
    assert not backup._allowed_run(cmd(kit, "g" * 40))
    assert not backup._allowed_run(cmd(kit, SHA.upper()))


def test_move_to_dev_creates_main_tracking_origin(fake_home, fake_runner, tmp_path, monkeypatch):
    kit = _kit(tmp_path, monkeypatch)
    bk = RecordingBackup(fake_runner)
    fake_runner.responses[_git(kit, "rev-parse", "HEAD")] = runner.Result(0, SHA + "\n", "")
    fake_runner.responses[_git(kit, "symbolic-ref")] = runner.Result(1, "", "")
    fake_runner.responses[_git(kit, "rev-parse", "--verify")] = runner.Result(1, "", "")
    assert channels.move_to_dev(kit, bk) is None
    calls = [c[3:] for c in fake_runner.calls if c[0] == "git"]
    assert ["switch", "-c", "main", "--track", "origin/main"] in calls
    assert calls[-1] == ["pull", "--ff-only"]
    assert calls.index(["fetch", "origin", "main"]) < [c[0] for c in calls].index("log")
    assert bk.recorded[0][0] == "kit checkout"

    fake_runner.calls.clear()
    fake_runner.responses[_git(kit, "rev-parse", "--verify")] = runner.Result(0, "x\n", "")
    assert channels.move_to_dev(kit, bk) is None
    assert ["switch", "main"] in [c[3:] for c in fake_runner.calls if c[0] == "git"]


def test_move_to_dev_refuses_local_changes(fake_home, fake_runner, tmp_path, monkeypatch):
    kit = _kit(tmp_path, monkeypatch)
    bk = RecordingBackup(fake_runner)
    fake_runner.responses[_git(kit, "status")] = runner.Result(0, " M a.py\n", "")
    assert "a.py" in channels.move_to_dev(kit, bk)
    assert not bk.recorded and "switch" not in _verbs(fake_runner)


def _moved_without_a_local_tag(fake, kit):
    """A stable move whose changelog fetch (the only one that creates refs/tags/X) failed: git describe cannot
    name the release afterwards, whatever HEAD is."""
    channels.set_channel("stable")
    _ready(fake, kit)
    fake.responses[_git(kit, "fetch", "origin", "tag")] = runner.Result(1, "", "would clobber existing tag")
    fake.responses[_git(kit, "describe")] = runner.Result(128, "", "fatal: no tag exactly matches")
    assert channels.changelog_lines(kit, "v0.3.0") == []
    assert channels.move_to(kit, "v0.3.0", RecordingBackup(fake)) is None
    fake.responses[_git(kit, "rev-parse", "HEAD")] = runner.Result(0, TAG_SHA + "\n", "")  # checked out


def test_a_move_names_its_release_without_a_local_tag(fake_home, fake_runner, tmp_path, monkeypatch):
    kit = _kit(tmp_path, monkeypatch)
    _moved_without_a_local_tag(fake_runner, kit)
    assert channels.current_release(kit) == "v0.3.0"
    assert channels.pin() == "v0.3.0"
    assert channels.claude_origin(channels.DEFAULT_SLUG) == channels.DEFAULT_SLUG + "#v0.3.0"
    assert channels.codex_source(channels.DEFAULT_SLUG) == channels.DEFAULT_SLUG + "@v0.3.0"


def test_after_a_restore_the_recorded_release_no_longer_counts(fake_home, fake_runner, tmp_path, monkeypatch):
    kit = _kit(tmp_path, monkeypatch)
    _moved_without_a_local_tag(fake_runner, kit)
    fake_runner.responses[_git(kit, "rev-parse", "HEAD")] = runner.Result(0, SHA + "\n", "")  # the undo ran
    assert channels.current_release(kit) is None and channels.pin() is None
    fake_runner.responses[_git(kit, "describe")] = runner.Result(0, "v0.2.0\n", "")  # back on an older release
    assert channels.current_release(kit) == "v0.2.0"
    fake_runner.responses[_git(kit, "describe")] = runner.Result(0, "v0.2.0-rc1\n", "")
    assert channels.current_release(kit) is None
