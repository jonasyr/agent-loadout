"""codex.codex_running(): whether a Codex process runs on this OS (read-only; never the real /proc in tests)."""
from loadout import codex, runner


def _proc(monkeypatch, tmp_path, procs):
    for pid, (comm, cmdline) in procs.items():
        d = tmp_path / str(pid)
        d.mkdir()
        (d / "comm").write_text(comm + "\n")
        (d / "cmdline").write_bytes(cmdline)
    (tmp_path / "self").mkdir()  # not a pid: ignored
    monkeypatch.setattr(codex, "PROC", tmp_path)


def test_linux_finds_codex_by_comm(monkeypatch, tmp_path, fake_runner):
    _proc(monkeypatch, tmp_path, {1: ("systemd", b"/sbin/init\x00"), 123: ("codex", b"codex\x00")})
    assert codex.codex_running("linux") is True


def test_linux_finds_codex_by_cmdline_path(monkeypatch, tmp_path, fake_runner):
    _proc(monkeypatch, tmp_path, {7: ("node", b"/opt/x/codex\x00app-server\x00")})
    assert codex.codex_running("linux") is True


def test_linux_ignores_lookalikes(monkeypatch, tmp_path, fake_runner):
    _proc(monkeypatch, tmp_path, {2: ("codex-reviewer", b"codex-reviewer\x00"), 3: ("mycodex", b"mycodex\x00"),
                                  4: ("run", b"/home/u/codex-stuff/run\x00")})
    assert codex.codex_running("linux") is False


def test_linux_without_proc_cannot_tell(monkeypatch, tmp_path, fake_runner):
    monkeypatch.setattr(codex, "PROC", tmp_path / "nope")
    assert codex.codex_running("linux") is None


def test_mac_and_windows_use_runner(fake_runner):
    fake_runner.responses[("ps", "-A", "-o", "comm=")] = runner.Result(
        0, "/usr/sbin/cron\n/Applications/Codex.app/Contents/MacOS/Codex\n", "")
    assert codex.codex_running("darwin") is True
    fake_runner.responses[("tasklist",)] = runner.Result(0, '"explorer.exe","1"\n"codex.exe","2"\n', "")
    assert codex.codex_running("win32") is True
    fake_runner.responses[("ps", "-A", "-o", "comm=")] = runner.Result(1, "", "x")
    fake_runner.responses[("tasklist",)] = runner.Result(1, "", "x")
    assert codex.codex_running("darwin") is None and codex.codex_running("win32") is None
    fake_runner.responses[("tasklist",)] = runner.Result(0, '"explorer.exe","1"\n', "")
    assert codex.codex_running("win32") is False
    assert codex.codex_running("sunos5") is None


def test_fake_runner_list_responses_are_consumed_in_order(fake_runner):
    fake_runner.responses[("x",)] = [runner.Result(1, "", "a"), runner.Result(0, "b", "")]
    assert [runner.run(["x"]).returncode for _ in range(3)] == [1, 0, 0]
