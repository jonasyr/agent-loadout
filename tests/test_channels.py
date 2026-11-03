import json

import pytest

from loadout import channels, paths, runner
from loadout.backup import Backup
from loadout.channels import SOAK, Status

T = 1_800_000_000.0
SHA_A, SHA_B = "a" * 40, "b" * 40


def test_unset_channel_is_dev(fake_home):
    assert channels.get() is None
    assert channels.effective() == "dev"
    channels.set_channel("stable")
    assert channels.get() == "stable"
    assert channels.effective() == "stable"
    with pytest.raises(ValueError):
        channels.set_channel("beta")
    assert channels.get() == "stable"


def test_invalid_channel_file_reads_as_unset(fake_home):
    paths.state_dir().mkdir(parents=True)
    (paths.state_dir() / "channel.json").write_text("{nope", encoding="utf-8")
    assert channels.get() is None
    (paths.state_dir() / "channel.json").write_text('{"channel": "beta"}', encoding="utf-8")
    assert channels.get() is None


def test_set_channel_saves_a_copy_of_the_old_file(fake_home):
    channels.set_channel("dev")
    bk = Backup(description="channel")
    channels.set_channel("stable", bk)
    assert channels.get() == "stable"
    assert not bk.empty


def test_set_channel_without_old_file_restores_to_unset(fake_home):
    from loadout import backup
    bk = Backup(description="channel")
    channels.set_channel("stable", bk)
    assert [s["undo"] for s in bk.steps] == [{"created": str(paths.state_dir() / "channel.json")}]
    backup.restore(bk.root, force=True)
    assert channels.get() is None


@pytest.mark.parametrize("name,want", [("v0.2.0", (0, 2, 0)), ("v1.10.3", (1, 10, 3))])
def test_parse_tag_accepts_release_names(name, want):
    assert channels.parse_tag(name) == want


@pytest.mark.parametrize("name", ["v0.1.0", "0.2.0", "v0.2", "v0.2.0-rc1", "v0.2.0\n", "v0.2.0; rm -rf ~", "v٠.٢.٠", "v01.2.0"])
def test_parse_tag_rejects_the_rest(name):
    assert channels.parse_tag(name) is None


def test_remote_tags_prefers_peeled_sha(fake_runner, tmp_path):
    out = (f"{SHA_A}\trefs/tags/v0.2.0\n{SHA_B}\trefs/tags/v0.2.0^{{}}\n"
           f"{SHA_A}\trefs/tags/v0.3.0\n{SHA_A}\trefs/tags/junk\n")
    key = ("git", "-C", str(tmp_path), "ls-remote", "--tags", "origin")
    fake_runner.responses[key] = runner.Result(0, out, "")
    assert channels.remote_tags(tmp_path) == {"v0.2.0": SHA_B, "v0.3.0": SHA_A}
    assert fake_runner.envs[0]["GIT_TERMINAL_PROMPT"] == "0" and fake_runner.timeouts[0] == 60
    fake_runner.responses[key] = runner.Result(128, "", "x")
    assert channels.remote_tags(tmp_path) is None


def test_soak_counts_from_first_seen(fake_home):
    channels.record_seen({"v0.2.0": SHA_A}, T)
    assert channels.eligible(None, T + SOAK - 1, Status()) is None
    assert channels.eligible(None, T + SOAK, Status()) == "v0.2.0"


def test_clock_before_first_seen_is_not_eligible(fake_home):
    channels.record_seen({"v0.2.0": SHA_A}, T)
    assert channels.eligible(None, T - 10, Status()) is None


def test_moved_tag_is_never_eligible_and_alarms_once(fake_home):
    channels.record_seen({"v0.2.0": SHA_A}, T)
    assert channels.record_seen({"v0.2.0": SHA_B}, T + 10) == ["v0.2.0"]
    assert channels.record_seen({"v0.2.0": SHA_B}, T + 20) == []
    assert channels.record_seen({"v0.2.0": SHA_A}, T + 30) == []
    assert channels.eligible(None, T + 10 * SOAK, Status()) is None


def test_record_ignores_bad_names(fake_home):
    channels.record_seen({"v0.1.0": SHA_A, "junk": SHA_A}, T)
    path = paths.state_dir() / "releases.json"
    assert not path.exists() or json.loads(path.read_text())["tags"] == {}


def test_urgent_skips_soak_and_withdrawn_is_skipped(fake_home):
    channels.record_seen({"v0.2.0": SHA_A}, T - 10 * SOAK)
    channels.record_seen({"v0.3.0": SHA_B}, T)
    assert channels.eligible(None, T, Status()) == "v0.2.0"
    assert channels.eligible(None, T, Status(urgent={"0.3.0"})) == "v0.3.0"
    bad = Status(withdrawn={"0.3.0": {"reason": "r", "use": None}})
    assert channels.eligible(None, T + SOAK, bad) == "v0.2.0"


def test_withdrawal_target_counts_as_urgent(fake_home):
    channels.record_seen({"v0.3.1": SHA_A}, T)
    st = Status(withdrawn={"0.3.0": {"reason": "r", "use": "0.3.1"}})
    assert channels.eligible(None, T, st) == "v0.3.1"


def test_only_newer_than_current(fake_home):
    channels.record_seen({"v0.2.0": SHA_A, "v0.3.0": SHA_B}, T)
    assert channels.eligible((0, 3, 0), T + SOAK, Status()) is None
    assert channels.eligible((0, 2, 0), T + SOAK, Status()) == "v0.3.0"


def test_notified_flag(fake_home):
    channels.record_seen({"v0.2.0": SHA_A}, T)
    assert not channels.notified("v0.2.0")
    channels.mark_notified("v0.2.0")
    assert channels.notified("v0.2.0")
    assert not channels.notified("v0.9.0")


def _status_run(fake_runner, root, text, fetch_ok=True, show_ok=True):
    fake_runner.responses[("git", "-C", str(root), "fetch", "origin", "main")] = runner.Result(0 if fetch_ok else 1, "", "")
    fake_runner.responses[("git", "-C", str(root), "show", "FETCH_HEAD:release-status.json")] = \
        runner.Result(0 if show_ok else 128, text, "")


def test_release_status_reads_the_file(fake_runner, tmp_path):
    body = json.dumps({"urgent": ["0.3.1"], "withdrawn": [{"version": "0.3.0", "reason": "bad", "use": "0.3.1"},
                                                          {"version": "0.2.5", "reason": "worse"}]})
    _status_run(fake_runner, tmp_path, body)
    st = channels.release_status(tmp_path)
    assert st.urgent == {"0.3.1"}
    assert st.withdrawn == {"0.3.0": {"reason": "bad", "use": "0.3.1"}, "0.2.5": {"reason": "worse", "use": None}}


@pytest.mark.parametrize("body,urgent,withdrawn", [
    (json.dumps({"urgent": "x", "withdrawn": [{"version": "0.3.0", "reason": "r"}]}), set(),
     {"0.3.0": {"reason": "r", "use": None}}),
    (json.dumps({"urgent": ["0.3.0"], "withdrawn": [{"version": "0.3.0"}]}), {"0.3.0"}, {}),
])
def test_release_status_bad_shapes_are_empty(fake_runner, tmp_path, body, urgent, withdrawn):
    _status_run(fake_runner, tmp_path, body)
    st = channels.release_status(tmp_path)
    assert (st.urgent, st.withdrawn) == (urgent, withdrawn)


@pytest.mark.parametrize("body", ["{nope", "[]"])
def test_release_status_unreadable_json_is_unknown(fake_runner, tmp_path, body):
    _status_run(fake_runner, tmp_path, body)
    assert channels.release_status(tmp_path) is None


def test_release_status_failures_are_unknown_but_a_missing_file_is_empty(fake_runner, tmp_path):
    _status_run(fake_runner, tmp_path, "{}", fetch_ok=False)
    assert channels.release_status(tmp_path) is None
    _status_run(fake_runner, tmp_path, "{}", show_ok=False)
    assert channels.release_status(tmp_path) is None
    key = ("git", "-C", str(tmp_path), "show", "FETCH_HEAD:release-status.json")
    for err in ("fatal: path 'release-status.json' does not exist in 'FETCH_HEAD'",
                "fatal: path 'release-status.json' exists on disk, but not in 'FETCH_HEAD'"):
        fake_runner.responses[key] = runner.Result(128, "", err)
        assert channels.release_status(tmp_path) == Status()


def test_current_release(fake_runner, tmp_path):
    key = ("git", "-C", str(tmp_path), "describe", "--tags", "--exact-match", "HEAD")
    fake_runner.responses[key] = runner.Result(0, "v0.2.0\n", "")
    assert channels.current_release(tmp_path) == "v0.2.0"
    fake_runner.responses[key] = runner.Result(0, "v0.1.0\n", "")
    assert channels.current_release(tmp_path) is None
    fake_runner.responses[key] = runner.Result(128, "", "")
    assert channels.current_release(tmp_path) is None


@pytest.mark.parametrize("url,slug", [
    ("https://github.com/o/r.git\n", "o/r"),
    ("https://github.com/o/r\n", "o/r"),
    ("git@github.com:o/r.git\n", "o/r"),
    ("ssh://git@github.com/o/r.git\n", "o/r"),
    ("https://example.com/o/r.git\n", channels.DEFAULT_SLUG),
])
def test_kit_slug_from_origin_forms(fake_runner, tmp_path, url, slug):
    fake_runner.responses[("git", "-C", str(tmp_path), "remote", "get-url", "origin")] = runner.Result(0, url, "")
    assert channels.kit_slug(tmp_path) == slug


def test_kit_slug_failing_remote(fake_runner, tmp_path):
    fake_runner.responses[("git", "-C", str(tmp_path), "remote", "get-url", "origin")] = runner.Result(2, "", "")
    assert channels.kit_slug(tmp_path) == channels.DEFAULT_SLUG
