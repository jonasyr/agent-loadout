import json

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


def test_pull_skipped_when_dirty(fake_home, fake_runner, tmp_path):
    fake_runner.responses[("git", "-C", str(tmp_path), "status", "--porcelain")] = runner.Result(0, " M x\n", "")
    assert m.pull_if_clean(tmp_path) is False
    assert not any("pull" in c for c in fake_runner.calls)


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

    def installer(cmd, cwd=None, timeout=300):
        fake_runner.calls.append(list(cmd))
        if cmd[0] == "tool-installer":
            s.write_text('{"a": 1, "hooks": {"X": []}}\n')
        return runner.Result(0, "", "")

    monkeypatch.setattr(runner, "run", installer)
    assert m.update(yes=True, ask=lambda q: "") == 0
    assert json.loads(s.read_text()) == {"a": 1}


def test_update_guard_backs_up_installer_version_and_names_keys(fake_home, fake_runner, monkeypatch, capsys):
    s = fake_home / ".claude/settings.json"
    s.parent.mkdir(parents=True)
    s.write_text('{"a": 1}\n')
    entry = {"id": "tool", "update": {"posix": [["tool-installer"]], "windows": [["tool-installer"]]}}
    monkeypatch.setattr(m, "find_outdated", lambda: [(entry, (1, 0, 0), (2, 0, 0))])

    def installer(cmd, cwd=None, timeout=300, env=None):
        if cmd[0] == "tool-installer":
            s.write_text('{"a": 2, "hooks": {"X": []}}\n')
        return runner.Result(0, "", "")

    monkeypatch.setattr(runner, "run", installer)
    m.update(yes=True, ask=lambda q: "")
    out = capsys.readouterr().out
    assert json.loads(s.read_text()) == {"a": 1}
    assert "a, hooks" in out
    copies = [p for p in paths.backups_root().rglob("files/*settings.json")]
    assert copies and json.loads(copies[0].read_text()) == {"a": 2, "hooks": {"X": []}}


def test_background_pull_never_prompts(fake_home, fake_runner, tmp_path):
    m.pull_if_clean(tmp_path)
    pulls = [(c, e) for c, e in zip(fake_runner.calls, fake_runner.envs) if "pull" in c]
    assert pulls
    for _, env in pulls:
        assert env["GIT_TERMINAL_PROMPT"] == "0" and env["GCM_INTERACTIVE"] == "never"


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
