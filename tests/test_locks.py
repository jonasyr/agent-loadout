import os
import threading
import time

import pytest

from loadout import locks, out, paths


@pytest.fixture(autouse=True)
def quick(monkeypatch):
    monkeypatch.setattr(locks, "POLL", 0.02)


def _file(name="t.lock"):
    return paths.state_dir() / name


def test_acquire_writes_who_holds_it(fake_home):
    lock = locks.acquire("t.lock", "update", 0)
    assert lock is not None
    command, started = locks.holder("t.lock")
    assert command == "update" and abs(time.time() - started) < 60
    lock.release()
    assert locks.holder("t.lock") is None


def test_a_second_acquire_waits_then_gets_it(fake_home):
    first = locks.acquire("t.lock", "update", 0)
    threading.Timer(0.3, first.release).start()
    t0 = time.monotonic()
    second = locks.acquire("t.lock", "bootstrap", 5)
    assert second is not None and time.monotonic() - t0 >= 0.25
    second.release()


def test_wait_zero_gives_up_at_once(fake_home):
    first = locks.acquire("t.lock", "update", 0)
    t0 = time.monotonic()
    assert locks.acquire("t.lock", "maintain", 0) is None
    assert time.monotonic() - t0 < 0.2
    first.release()


def test_a_limit_gives_up_and_the_message_names_the_holder(fake_home):
    first = locks.acquire("t.lock", "update", 0)
    assert locks.acquire("t.lock", "bootstrap", 0.1) is None
    msg = locks.busy_message("t.lock")
    assert "(update, started " in msg and "is still running; run this again when it has finished" in msg
    first.release()


def test_a_stale_lock_is_taken_over(fake_home):
    locks.acquire("t.lock", "old", 0)
    old = time.time() - 2 * 3600
    os.utime(_file(), (old, old))
    lock = locks.acquire("t.lock", "new", 0)
    assert lock is not None and locks.holder("t.lock")[0] == "new"
    assert not list(_file().parent.glob("t.lock.stale-*"))


def test_an_old_plain_pid_lock_counts_as_held(fake_home):
    _file().parent.mkdir(parents=True, exist_ok=True)
    _file().write_text("12345")
    mtime = _file().stat().st_mtime
    assert locks.holder("t.lock") == ("loadout", mtime)
    assert locks.acquire("t.lock", "update", 0) is None


def test_release_leaves_someone_elses_lock(fake_home):
    lock = locks.acquire("t.lock", "update", 0)
    _file().write_text('{"token": "other", "command": "x", "started": 1}')
    lock.release()
    assert _file().exists()
    lock.touch()  # not ours: no error, no change


def test_touch_refreshes_our_lock(fake_home):
    lock = locks.acquire("t.lock", "update", 0)
    old = time.time() - 1800
    os.utime(_file(), (old, old))
    lock.touch()
    assert time.time() - _file().stat().st_mtime < 60


def test_ctrl_c_while_waiting_clears_the_line(fake_home, monkeypatch, capsys):
    locks.acquire("t.lock", "update", 0)
    monkeypatch.setattr(out, "VERBOSE", False)
    monkeypatch.setattr(out, "_tty", lambda: True)

    def interrupted(_seconds):
        raise KeyboardInterrupt
    monkeypatch.setattr(locks, "_sleep", interrupted)
    with pytest.raises(KeyboardInterrupt):
        locks.acquire("t.lock", "bootstrap", None)
    text = capsys.readouterr().out
    assert "waiting for the other loadout run (update, started " in text
    assert text.endswith("\r") and out._shown == 0


def test_off_a_terminal_the_wait_line_is_printed_once(fake_home, monkeypatch, capsys):
    locks.acquire("t.lock", "update", 0)
    monkeypatch.setattr(out, "_tty", lambda: False)
    assert locks.acquire("t.lock", "bootstrap", 0.15) is None
    assert capsys.readouterr().out.count("waiting for the other loadout run") == 1
