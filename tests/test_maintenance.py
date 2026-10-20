import json
import pytest

from loadout import maintenance as m, paths, runner, versions


def test_is_due_and_touch(fake_home):
    assert m.is_due("x", m.DAY, 1000.0)
    m.touch("x", 1000.0)
    assert not m.is_due("x", m.DAY, 1000.0 + 10)
    assert m.is_due("x", m.DAY, 1000.0 + m.DAY)


def test_session_start_prints_pending_notice_once(fake_home, monkeypatch):
    monkeypatch.setattr(m, "_spawn_background", lambda: None)
    notice = paths.state_dir() / "pending-notice"
    notice.parent.mkdir(parents=True)
    notice.write_text("updates available")
    out = m.session_start(0.0)
    assert json.loads(out) == {"systemMessage": "updates available"}
    assert m.session_start(0.0) is None


def test_session_start_spawns_only_when_due(fake_home, monkeypatch):
    spawned = []
    monkeypatch.setattr(m, "_spawn_background", lambda: spawned.append(1))
    m.session_start(5.0)
    assert spawned == [1]
    m.touch("last-pull", 5.0)
    m.touch("last-update-check", 5.0)
    m.session_start(6.0)
    assert spawned == [1]


REFUSAL = ("error: Your local changes to the following files would be overwritten by merge:\n"
           "\t.serena/project.yml\nPlease commit your changes or stash them before you merge.\nAborting\n")


def _pull_key(root):
    return ("git", "-c", "core.quotePath=false", "-C", str(root), "pull")


def test_untracked_files_do_not_pause_the_pull(fake_home, fake_runner, tmp_path):
    fake_runner.responses[("git", "-C", str(tmp_path), "status", "--porcelain")] = runner.Result(0, "?? x\n", "")
    res = m.pull(tmp_path)
    assert any(c[:6] == list(_pull_key(tmp_path)) for c in fake_runner.calls)
    assert res.paused is None and m.paused() == {}
    assert not any("status" in c for c in fake_runner.calls)


def test_a_refused_pull_names_the_files_and_changes_nothing(fake_home, fake_runner, tmp_path):
    fake_runner.responses[_pull_key(tmp_path)] = runner.Result(1, "", REFUSAL)
    res = m.pull(tmp_path)
    assert res.pulled is False and res.paused == "local changes the pull would overwrite"
    assert res.files == [".serena/project.yml"]
    rec = m.paused()[str(tmp_path)]
    assert rec["files"] == [".serena/project.yml"] and rec["reason"] == res.paused
    notice = (paths.state_dir() / "pending-notice").read_text()
    assert notice == (f"loadout: the daily sync of {tmp_path} paused: local changes the pull would overwrite: "
                      ".serena/project.yml; commit or stash them, then run loadout update\n")
    last_pull = max(i for i, c in enumerate(fake_runner.calls) if "pull" in c)
    assert last_pull == len(fake_runner.calls) - 1  # git refused: nothing else ran (no reset, stash, checkout)
    m.pull(tmp_path)  # the same refusal again: no second notice
    assert (paths.state_dir() / "pending-notice").read_text() == notice


def test_a_diverged_branch_is_recorded_without_files(fake_home, fake_runner, tmp_path):
    fake_runner.responses[_pull_key(tmp_path)] = runner.Result(128, "", "fatal: Not possible to fast-forward, aborting.\n")
    res = m.pull(tmp_path)
    assert res.paused == "your branch and its upstream have diverged" and res.files == []


def test_the_pull_env_forces_english_and_no_prompts(fake_home, fake_runner, tmp_path):
    m.pull(tmp_path)
    pulls = [e for c, e in zip(fake_runner.calls, fake_runner.envs) if "pull" in c]
    assert pulls
    for env in pulls:
        assert env["GIT_TERMINAL_PROMPT"] == "0" and env["GCM_INTERACTIVE"] == "never" and env["LC_ALL"] == "C"


def test_no_upstream_is_skipped_not_paused(fake_home, fake_runner, tmp_path):
    fake_runner.responses[("git", "-C", str(tmp_path), "rev-parse", "--abbrev-ref", "@{u}")] = runner.Result(128, "", "no upstream")
    res = m.pull(tmp_path)
    assert res == m.PullResult(False, None, [], skipped="no upstream branch") and m.paused() == {}
    assert not any("pull" in c for c in fake_runner.calls)


def test_a_detached_head_is_skipped_not_paused(fake_home, fake_runner, tmp_path):
    fake_runner.responses[("git", "-C", str(tmp_path), "symbolic-ref")] = runner.Result(1, "", "")
    assert m.pull(tmp_path).paused is None and not any("pull" in c for c in fake_runner.calls)


def test_a_later_good_pull_clears_the_pause(fake_home, fake_runner, tmp_path):
    fake_runner.responses[_pull_key(tmp_path)] = runner.Result(1, "", REFUSAL)
    m.pull(tmp_path)
    assert m.paused()
    del fake_runner.responses[_pull_key(tmp_path)]
    assert m.pull(tmp_path).paused is None
    assert m.paused() == {} and not (paths.state_dir() / "sync-paused.json").exists()


def test_maintain_writes_notice_for_outdated(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(m, "pull_if_clean", lambda root: False)
    monkeypatch.setattr(m, "find_outdated", lambda: [({"id": "serena"}, (1, 7, 0), (1, 8, 0))])
    m.maintain(100.0)
    text = (paths.state_dir() / "pending-notice").read_text()
    assert "serena 1.7.0 -> 1.8.0" in text and "loadout update" in text


def test_maintain_survives_offline(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(m, "pull_if_clean", lambda root: False)
    fake_runner.responses[("serena", "--version")] = runner.Result(0, "Serena 1.7.0", "")
    fake_runner.responses[("playwright-cli", "--version")] = runner.Result(0, "0.1.22", "")
    attempts = []

    def boom(url):
        attempts.append(url)
        raise OSError("offline")

    monkeypatch.setattr(versions, "_fetch_json", boom)
    m.maintain(100.0)  # must not raise
    assert attempts, "latest_version never reached the network path"
    assert not (paths.state_dir() / "pending-notice").exists()


def test_update_reverts_settings_modified_by_installer(fake_home, fake_runner, monkeypatch):
    s = fake_home / ".claude/settings.json"
    s.parent.mkdir(parents=True)
    s.write_text('{"a": 1}\n')
    entry = {"id": "tool", "update": {"posix": [["tool-installer"]], "windows": [["tool-installer"]]}}
    monkeypatch.setattr(m, "find_outdated", lambda: [(entry, (1, 0, 0), (2, 0, 0))])

    merged = {}

    def installer(cmd, cwd=None, timeout=300, env=None):
        fake_runner.calls.append(list(cmd))
        if cmd[0] == "tool-installer":
            merged.update(json.loads(s.read_text()))  # update re-applied the kit merge before the tools ran
            s.write_text('{"a": 1, "hooks": {"X": []}}\n')
        return runner.Result(0, "", "")

    monkeypatch.setattr(runner, "run", installer)
    assert m.update(yes=True, ask=lambda q: "") == 0
    assert merged["a"] == 1 and json.loads(s.read_text()) == merged


def test_update_guard_backs_up_installer_version_and_names_keys(fake_home, fake_runner, monkeypatch, capsys):
    s = fake_home / ".claude/settings.json"
    s.parent.mkdir(parents=True)
    s.write_text('{"a": 1}\n')
    entry = {"id": "tool", "update": {"posix": [["tool-installer"]], "windows": [["tool-installer"]]}}
    monkeypatch.setattr(m, "find_outdated", lambda: [(entry, (1, 0, 0), (2, 0, 0))])

    merged = {}

    def installer(cmd, cwd=None, timeout=300, env=None):
        if cmd[0] == "tool-installer":
            merged.update(json.loads(s.read_text()))  # update re-applied the kit merge before the tools ran
            s.write_text('{"a": 2, "hooks": {"X": []}}\n')
        return runner.Result(0, "", "")

    monkeypatch.setattr(runner, "run", installer)
    m.update(yes=True, ask=lambda q: "")
    out = capsys.readouterr().out
    assert merged["a"] == 1 and json.loads(s.read_text()) == merged
    keys = set(out.split("keys: ", 1)[1].split(")", 1)[0].split(", "))
    assert {"a", "hooks"} <= keys
    # the guard's backup by its description: the re-apply may have made an earlier one, and listing order differs
    guards = [d for d in paths.backups_root().iterdir() if (d / "manifest.json").exists()
              and json.loads((d / "manifest.json").read_text())["description"]
              == "update: settings.json as modified by an installer"]
    assert len(guards) == 1
    copies = list((guards[0] / "files").glob("*settings.json"))
    assert len(copies) == 1 and json.loads(copies[0].read_text()) == {"a": 2, "hooks": {"X": []}}


@pytest.mark.parametrize("broken", [b'{"a": 2, "hooks": {', b'\xff\xfe{"a": \xff}'], ids=["malformed", "not-utf8"])
def test_update_guard_restores_settings_an_installer_left_unreadable(fake_home, fake_runner, monkeypatch, capsys,
                                                                    broken):
    s = fake_home / ".claude/settings.json"
    s.parent.mkdir(parents=True)
    s.write_text('{"a": 1}\n')
    entry = {"id": "tool", "update": {"posix": [["tool-installer"]], "windows": [["tool-installer"]]}}
    monkeypatch.setattr(m, "find_outdated", lambda: [(entry, (1, 0, 0), (2, 0, 0))])
    merged = []

    def installer(cmd, cwd=None, timeout=300, env=None):
        if cmd[0] == "tool-installer":
            merged.append(s.read_bytes())  # the kit-merged file, as the re-apply left it
            s.write_bytes(broken)
        return runner.Result(0, "", "")

    monkeypatch.setattr(runner, "run", installer)
    assert m.update(yes=True, ask=lambda q: "") == 0
    assert merged and s.read_bytes() == merged[0]  # the pre-installer bytes, exactly
    guards = [d for d in paths.backups_root().iterdir() if (d / "manifest.json").exists()
              and json.loads((d / "manifest.json").read_text())["description"]
              == "update: settings.json as modified by an installer"]
    assert len(guards) == 1
    assert [p.read_bytes() for p in (guards[0] / "files").glob("*settings.json")] == [broken]
    changed = capsys.readouterr().out.split("What changed", 1)[1]
    assert "could not be read" in changed and str(guards[0]) in changed


def test_update_guard_restores_settings_an_installer_only_reformatted(fake_home, fake_runner, monkeypatch, capsys):
    s = fake_home / ".claude/settings.json"
    s.parent.mkdir(parents=True)
    s.write_text('{"a": 1}\n')
    entry = {"id": "tool", "update": {"posix": [["tool-installer"]], "windows": [["tool-installer"]]}}
    monkeypatch.setattr(m, "find_outdated", lambda: [(entry, (1, 0, 0), (2, 0, 0))])
    merged = []

    def installer(cmd, cwd=None, timeout=300, env=None):
        if cmd[0] == "tool-installer":
            merged.append(s.read_bytes())
            s.write_bytes(b"\xef\xbb\xbf" + json.dumps(json.loads(merged[0]), indent=8).encode().replace(b"\n", b"\r\n"))
        return runner.Result(0, "", "")

    monkeypatch.setattr(runner, "run", installer)
    assert m.update(yes=True, ask=lambda q: "") == 0
    assert merged and s.read_bytes() == merged[0]
    guards = [d for d in paths.backups_root().iterdir() if (d / "manifest.json").exists()
              and json.loads((d / "manifest.json").read_text())["description"]
              == "update: settings.json as modified by an installer"]
    assert len(guards) == 1
    assert [p.read_bytes()[:3] for p in (guards[0] / "files").glob("*settings.json")] == [b"\xef\xbb\xbf"]


def test_no_auto_pull_env_skips_pull(fake_home, fake_runner, monkeypatch, tmp_path):
    kit = tmp_path / "kit"
    (kit / ".git").mkdir(parents=True)
    monkeypatch.setenv("LOADOUT_ROOT", str(kit))
    monkeypatch.setenv("LOADOUT_NO_AUTO_PULL", "1")
    monkeypatch.setattr(m, "find_outdated", lambda: [])
    pulled = []
    monkeypatch.setattr(m, "pull_if_clean", lambda root: pulled.append(root) or False)
    m.maintain(100.0)
    assert pulled == []


def test_session_start_no_auto_pull_does_not_count_pull_as_due(fake_home, monkeypatch):
    spawned = []
    monkeypatch.setattr(m, "_spawn_background", lambda: spawned.append(1))
    monkeypatch.setenv("LOADOUT_NO_AUTO_PULL", "1")
    m.touch("last-update-check", 5.0)  # weekly check fresh, last-pull never stamped
    m.session_start(6.0)
    assert spawned == []


def test_session_start_no_auto_pull_still_spawns_for_weekly_check(fake_home, monkeypatch):
    spawned = []
    monkeypatch.setattr(m, "_spawn_background", lambda: spawned.append(1))
    monkeypatch.setenv("LOADOUT_NO_AUTO_PULL", "1")
    m.touch("last-update-check", 5.0)
    m.session_start(5.0 + m.WEEK)
    assert spawned == [1]


def test_an_unknown_failure_reason_is_redacted(fake_home, fake_runner, tmp_path):
    token = "ghp_" + "abcdefghijklmnopqrstuvwxyz0123456789"  # built, so the repo scan finds no literal token
    err = f"fatal: repository 'https://jonas:{token}@github.com/x/y.git/' not found\n"
    fake_runner.responses[_pull_key(tmp_path)] = runner.Result(128, "", err)
    m.pull(tmp_path)
    texts = [(paths.state_dir() / "sync-paused.json").read_text(), (paths.state_dir() / "pending-notice").read_text()]
    assert all("ghp_" not in t for t in texts) and "github.com/x/y.git" in texts[0]


@pytest.mark.parametrize("err,code", [("fatal: unable to access 'https://jonas:ghp_x@github.com/x/y.git/': Could not resolve host\n", 128),
                                      ("ssh: connect to host h: Connection timed out\n", 128),
                                      ("fatal: Failed to connect to github.com port 443\n", 128),
                                      ("git: timed out after 120s", 124)])
def test_network_failures_are_not_a_pause(fake_home, fake_runner, tmp_path, err, code):
    fake_runner.responses[_pull_key(tmp_path)] = runner.Result(code, "", err)
    res = m.pull(tmp_path)
    assert res.paused is None and m.paused() == {}
    assert not (paths.state_dir() / "pending-notice").exists()


def test_the_record_is_raw_and_escaped_once_when_printed(fake_home, fake_runner, tmp_path):
    fake_runner.responses[_pull_key(tmp_path)] = runner.Result(1, "", REFUSAL.replace(".serena/project.yml", "a\x1bb"))
    m.pull(tmp_path)
    assert m.paused()[str(tmp_path)]["files"] == ["a\x1bb"]
    notice = (paths.state_dir() / "pending-notice").read_text()
    assert "a\\x1bb" in notice and "\\\\x1b" not in notice and "\x1b" not in notice


def test_untracked_overwrite_has_its_own_reason(fake_home, fake_runner, tmp_path):
    err = "error: The following untracked working tree files would be overwritten by merge:\n\tx\nAborting\n"
    fake_runner.responses[_pull_key(tmp_path)] = runner.Result(1, "", err)
    assert m.pull(tmp_path).paused == "untracked files the pull would overwrite"


def test_a_message_that_only_mentions_fast_forward_is_not_diverged(fake_home, fake_runner, tmp_path):
    fake_runner.responses[_pull_key(tmp_path)] = runner.Result(1, "", "error: cannot pull: fast-forward merge unsupported here\n")
    assert m.pull(tmp_path).paused == "error: cannot pull: fast-forward merge unsupported here"


def test_skips_clear_an_old_record(fake_home, fake_runner, tmp_path):
    fake_runner.responses[_pull_key(tmp_path)] = runner.Result(1, "", REFUSAL)
    m.pull(tmp_path)
    fake_runner.responses[("git", "-C", str(tmp_path), "rev-parse", "--abbrev-ref", "@{u}")] = runner.Result(128, "", "")
    m.pull(tmp_path)
    assert m.paused() == {}


def test_a_notice_is_redacted_before_it_is_queued(fake_home):
    secret = "ghp_" + "c" * 36
    m.notify(f"loadout (Codex): plugin x: failed: https://x:{secret}@github.com/o/r")
    text = (paths.state_dir() / "pending-notice").read_text(encoding="utf-8")
    assert secret not in text and "failed" in text
