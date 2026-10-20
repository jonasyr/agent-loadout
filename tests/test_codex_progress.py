"""Long Codex setups say what they are doing, survive Ctrl+C cleanly and never run twice at once."""
import json
import os
import time

from loadout import backup, codex, out, paths, runner
from loadout.__main__ import main


def test_slow_steps_are_announced(fake_home, fake_runner, monkeypatch):
    from loadout import settings_merge
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: {
        "enabledPlugins": {"impeccable@impeccable": True},
        "extraKnownMarketplaces": {"impeccable": {"source": {"source": "github", "repo": "pbakaus/impeccable"}}}})
    fake_runner.responses[("codex", "plugin", "list")] = runner.Result(0, json.dumps({"installed": []}), "")
    fake_runner.responses[("codex", "plugin", "marketplace", "add")] = runner.Result(
        0, json.dumps({"marketplaceName": "impeccable", "alreadyAdded": False}), "")
    said = []
    codex.apply_plugins(backup.Backup(description="t"), say=said.append)
    assert any("pbakaus/impeccable" in s and "a git clone" in s for s in said)
    assert any("impeccable@impeccable" in s for s in said)


def test_ctrl_c_ends_with_a_short_message(fake_home, monkeypatch, capsys):
    from loadout import configure

    def interrupted(ask):
        raise KeyboardInterrupt
    monkeypatch.setattr(configure, "prefs", interrupted)
    assert main(["configure", "prefs"]) == 130
    err = capsys.readouterr().err
    assert "interrupted" in err and "Traceback" not in err


def _quiet_codex(monkeypatch):
    for name in ("apply_instructions", "apply_config", "apply_skills", "apply_plugins"):
        monkeypatch.setattr(codex, name, lambda *a, **k: [] if name != "apply_instructions" else "ok")


def test_a_second_run_waits_its_turn(fake_home, fake_runner, monkeypatch, capsys):
    import threading
    from loadout import locks
    _quiet_codex(monkeypatch)
    monkeypatch.setattr(locks, "POLL", 0.02)
    first = locks.acquire(codex.LOCK, "bootstrap", 0)
    threading.Timer(0.2, first.release).start()
    lines = codex.apply_all(backup.Backup(description="t"))
    assert not any("still running" in l for l in lines)
    assert "waiting for the other loadout run (bootstrap, started " in capsys.readouterr().out
    assert not (paths.state_dir() / codex.LOCK).exists(), "the lock is released after the run"


def test_a_second_run_gives_up_after_the_limit(fake_home, fake_runner, monkeypatch):
    from loadout import locks
    _quiet_codex(monkeypatch)
    monkeypatch.setattr(locks, "POLL", 0.02)
    monkeypatch.setattr(locks, "FOREGROUND_LIMIT", 0.1)
    locks.acquire(codex.LOCK, "update", 0)
    lines = codex.apply_all(backup.Backup(description="t"))
    assert len(lines) == 1 and "(update, started " in lines[0] and "run this again when it has finished" in lines[0]
    assert out.PROBLEM.search(lines[0])


def test_the_background_sync_never_waits(fake_home, fake_runner, monkeypatch):
    from loadout import locks
    _quiet_codex(monkeypatch)
    locks.acquire(codex.LOCK, "update", 0)
    t0 = time.monotonic()
    lines = codex.apply_all(backup.Backup(description="t"), refresh=True, command="maintain")
    assert time.monotonic() - t0 < 0.5 and "still running" in lines[0]


def test_a_stale_codex_lock_is_taken_over(fake_home, fake_runner, monkeypatch):
    _quiet_codex(monkeypatch)
    lock = paths.state_dir() / codex.LOCK
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("12345")
    old = time.time() - 2 * 3600
    os.utime(lock, (old, old))  # a lock from a crashed run
    assert not any("still running" in l for l in codex.apply_all(backup.Backup(description="t")))
    assert not lock.exists(), "the lock is released after the run"
