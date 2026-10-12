"""Long Codex setups say what they are doing, survive Ctrl+C cleanly and never run twice at once."""
import json
import os
import time

from loadout import backup, codex, paths, runner
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
    assert any("pbakaus/impeccable" in s and "can take a few minutes" in s for s in said)
    assert any("impeccable@impeccable" in s for s in said)


def test_ctrl_c_ends_with_a_short_message(fake_home, monkeypatch, capsys):
    from loadout import configure

    def interrupted(ask):
        raise KeyboardInterrupt
    monkeypatch.setattr(configure, "prefs", interrupted)
    assert main(["configure", "prefs"]) == 130
    err = capsys.readouterr().err
    assert "interrupted" in err and "Traceback" not in err


def test_a_second_run_waits_its_turn(fake_home, fake_runner, monkeypatch):
    for name in ("apply_instructions", "apply_config", "apply_skills", "apply_plugins"):
        monkeypatch.setattr(codex, name, lambda *a, **k: [] if name != "apply_instructions" else "ok")
    lock = paths.state_dir() / codex.LOCK
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("12345")
    lines = codex.apply_all(backup.Backup(description="t"))
    assert any("another loadout run" in l for l in lines)
    old = time.time() - 2 * 3600
    os.utime(lock, (old, old))  # a lock from a crashed run
    assert not any("another loadout run" in l for l in codex.apply_all(backup.Backup(description="t")))
    assert not lock.exists(), "the lock is released after the run"
