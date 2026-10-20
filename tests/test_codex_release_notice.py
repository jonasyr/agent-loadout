"""An entry loadout wrote in ~/.codex/config.toml that you changed is yours after one note at the next session
start; `loadout check` is quiet about it afterwards (plan 2026-10-20, items 17+19)."""
import json
import time

import pytest

from loadout import backup, codex, maintenance, paths


@pytest.fixture(autouse=True)
def _no_background_run(monkeypatch):
    """session_start would start a real detached `loadout maintenance` (git pull, update check)."""
    monkeypatch.setattr(maintenance, "_spawn_background", lambda: None)


def _codex_on(claude=True):
    paths.personal_root().mkdir(parents=True, exist_ok=True)
    (paths.personal_root() / "targets.json").write_text(json.dumps({"claude": claude, "codex": True}))


def _personal_mcp(servers):
    path = paths.personal_root() / "mcp.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"mcpServers": servers}), encoding="utf-8")


def _cfg():
    return paths.codex_home() / "config.toml"


def _apply():
    return codex.apply_config(backup.Backup(description="t"))


def _message(out):
    return json.loads(out)["systemMessage"] if out else ""


def _check_row(monkeypatch):
    monkeypatch.setattr(codex, "installed_plugins", lambda: {"loadout@agent-loadout"})
    monkeypatch.setattr(codex, "unavailable", lambda: None)
    monkeypatch.setattr(codex, "hooks_status", lambda: "trusted")
    monkeypatch.setattr(codex, "logins_needed", lambda: [])
    monkeypatch.setattr(codex, "drift", lambda: [])
    (row,) = [r for r in codex.checks() if r.name == "Codex config"]
    return row


def _edit_gh():
    _cfg().write_bytes(_cfg().read_bytes().replace(b'command = "gh-mcp"', b'command = "gh-mcp"\nstartup_timeout_sec = 30'))
    return _cfg().read_bytes()


def test_a_table_you_changed_is_yours_after_one_note_and_check_is_quiet(fake_home, fake_runner, monkeypatch):
    _codex_on()
    _personal_mcp({"gh": {"command": "gh-mcp"}})
    _apply()
    mine = _edit_gh()
    first = _message(maintenance.session_start(0))
    assert "mcp gh" in first and "yours now" in first
    assert _cfg().read_bytes() == mine
    record = codex.read_record()
    assert record["released"] == ["gh"] and "gh" not in record["tables"] and "serena" in record["tables"]
    assert "mcp gh" not in _message(maintenance.session_start(0))  # one note only
    row = _check_row(monkeypatch)
    assert row.ok, row.detail
    assert _cfg().read_bytes() == mine


def test_your_own_kept_value_gets_one_note_then_quiet(fake_home, fake_runner, monkeypatch):
    _codex_on()
    _apply()
    mine = _cfg().read_bytes().replace(b'model_reasoning_effort = "medium"', b'model_reasoning_effort = "high"')
    _cfg().write_bytes(mine)
    assert any("(your value)" in l for l in codex.apply_config(object(), dry_run=True))  # check warns today
    first = _message(maintenance.session_start(0))
    assert "model_reasoning_effort" in first and "yours" in first
    assert "model_reasoning_effort" not in _message(maintenance.session_start(0))
    assert codex.read_record()["released_keys"] == ["model_reasoning_effort"]
    assert _check_row(monkeypatch).ok and _cfg().read_bytes() == mine
    assert not any("model_reasoning_effort" in l for l in _apply()) and _cfg().read_bytes() == mine


def test_a_same_named_table_never_loadouts_keeps_its_warning(fake_home, fake_runner, monkeypatch):
    _codex_on()
    _cfg().parent.mkdir(parents=True)
    _cfg().write_text('[mcp_servers.gh]\ncommand = "my-own-gh"\n', encoding="utf-8")
    _personal_mcp({"gh": {"command": "gh-mcp"}})
    assert "mcp gh" not in _message(maintenance.session_start(0))
    assert "released" not in codex.read_record()
    row = _check_row(monkeypatch)
    assert not row.ok and "mcp gh: left as is, config.toml already has a server of that name" in row.detail
    _apply()
    assert any("already has a server of that name" in l for l in codex.apply_config(object(), dry_run=True))


def test_session_start_never_waits_for_a_busy_codex_lock_and_never_fails(fake_home, fake_runner, monkeypatch):
    _codex_on()
    _personal_mcp({"gh": {"command": "gh-mcp"}})
    _apply()
    _edit_gh()
    record = codex.record_path().read_bytes()
    held = codex._lock(0, "bootstrap")
    try:
        began = time.monotonic()
        assert "mcp gh" not in _message(maintenance.session_start(0))
        assert time.monotonic() - began < 5
        assert codex.record_path().read_bytes() == record
    finally:
        held.release()
    assert "mcp gh" in _message(maintenance.session_start(0))  # the lock is free: the note comes now

    def broken():
        raise RuntimeError("boom")
    monkeypatch.setattr(codex, "refresh_record", broken)
    maintenance.notify("queued before")
    assert "queued before" in _message(maintenance.session_start(0))


def test_codex_off_afterwards_removes_only_what_is_still_loadouts(fake_home, fake_runner, monkeypatch):
    from loadout import configure
    from loadout.__main__ import main
    _codex_on()
    _personal_mcp({"gh": {"command": "gh-mcp"}})
    _apply()
    mine = _edit_gh()
    maintenance.session_start(0)
    monkeypatch.setattr(configure, "offer_commit", lambda ask: None)
    assert main(["configure", "set", "target", "codex", "off"]) == 0
    assert _cfg().read_bytes() == mine
    assert "gh" not in codex.read_record()["tables"] and "serena" in codex.read_record()["tables"]
    with monkeypatch.context() as m:
        m.setattr(codex, "_tomllib", lambda: pytest.fail("Codex is off: config.toml must not be read"))
        maintenance.session_start(0)
    _codex_on()
    _personal_mcp({})  # gh leaves the personal layer: your table stays, loadout's own entries still follow
    _apply()
    text = _cfg().read_text(encoding="utf-8")
    assert "[mcp_servers.gh]\ncommand = \"gh-mcp\"\nstartup_timeout_sec = 30\n" in text
    assert "[mcp_servers.serena]" in text


def test_a_codex_only_user_gets_the_note_too(fake_home, fake_runner):
    _codex_on(claude=False)
    _personal_mcp({"gh": {"command": "gh-mcp"}})
    _apply()
    _edit_gh()
    assert "mcp gh" in _message(maintenance.session_start(0, agent="codex"))
