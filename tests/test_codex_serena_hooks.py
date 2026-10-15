"""Codex: Serena's six documented hooks in ~/.codex/hooks.json, exactly once, the user's entries untouched."""
import json

import pytest

from loadout import backup, codex_hooks, runner


@pytest.fixture
def hooks(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(runner, "have", lambda b: b == "serena-hooks")
    p = codex_hooks.path()
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _commands(p):
    data = json.loads(p.read_text())
    return sorted(h["command"] for groups in data["hooks"].values() for g in groups for h in g["hooks"])


OFFICIAL = sorted(f"serena-hooks {s} --client=codex" for s in
                  ("remind", "plan-guard", "reset", "activate", "plan-context", "cleanup"))


def test_a_fresh_setup_gets_the_official_set(hooks):
    lines = codex_hooks.apply(backup.Backup(description="t"))
    assert _commands(hooks) == OFFICIAL
    data = json.loads(hooks.read_text())["hooks"]
    assert data["SessionStart"][0]["matcher"] == "startup|resume"
    assert data["SessionEnd"][0]["hooks"][0]["timeout"] == 3
    assert any("/hooks" in l for l in lines)
    assert codex_hooks.apply(backup.Backup(description="t")) == []  # second run: nothing


def test_the_users_official_set_is_left_alone(hooks):
    codex_hooks.apply(backup.Backup(description="t"))
    users = hooks.read_text()
    codex_hooks.paths.state_dir().joinpath("codex-config.json").unlink()  # as if the user wrote it (serena setup codex)
    assert codex_hooks.apply(backup.Backup(description="t")) == []
    assert hooks.read_text() == users


def test_only_missing_entries_are_added(hooks):
    hooks.write_text(json.dumps({"hooks": {"SessionStart": [{"matcher": "startup|resume", "hooks": [
        {"type": "command", "command": "/opt/bin/serena-hooks activate --client=codex", "timeout": 20}]}],
        "Stop": [{"hooks": [{"type": "command", "command": "serena-hooks cleanup --client=codex"}]}]}}, indent=2) + "\n")
    codex_hooks.apply(backup.Backup(description="t"))
    cmds = _commands(hooks)
    assert sum("activate" in c for c in cmds) == 1 and sum("cleanup" in c for c in cmds) == 1
    assert len(cmds) == 6


def test_a_file_in_another_format_is_not_rewritten(hooks):
    users = '{"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo hi"}]}]}}'  # one line
    hooks.write_text(users)
    lines = codex_hooks.apply(backup.Backup(description="t"))
    assert hooks.read_text() == users
    assert any("add these yourself" in l and "serena-hooks remind --client=codex" in l for l in lines)


def test_without_serena_hooks_nothing_is_written_and_ours_go(hooks, monkeypatch):
    codex_hooks.apply(backup.Backup(description="t"))
    monkeypatch.setattr(runner, "have", lambda b: False)
    codex_hooks.apply(backup.Backup(description="t"))
    assert _commands(hooks) == []


def test_an_entry_the_user_changed_becomes_theirs(hooks):
    codex_hooks.apply(backup.Backup(description="t"))
    data = json.loads(hooks.read_text())
    data["hooks"]["SessionEnd"][0]["hooks"][0]["timeout"] = 9
    hooks.write_text(json.dumps(data, indent=2) + "\n")
    before = hooks.read_text()
    assert codex_hooks.apply(backup.Backup(description="t")) == []  # cleanup still present (theirs now)
    assert hooks.read_text() == before


def test_restore_reverts_the_first_change(hooks):
    hooks.write_text(json.dumps({"hooks": {}}, indent=2) + "\n")
    bk = backup.Backup(description="t")
    codex_hooks.apply(bk)
    assert any(step["label"].startswith("Codex hooks.json") for step in bk.steps)


def test_codex_setup_and_check_include_the_serena_hooks(hooks, monkeypatch):
    from loadout import codex
    monkeypatch.setattr(codex, "apply_instructions", lambda bk: "instructions")
    monkeypatch.setattr(codex, "apply_config", lambda bk, dry_run=False: [])
    monkeypatch.setattr(codex, "apply_skills", lambda bk: [])
    monkeypatch.setattr(codex, "apply_plugins", lambda bk, **k: [])
    lines = codex.apply_all(backup.Backup(description="t"))
    assert any("added Serena's hooks" in l for l in lines) and _commands(hooks) == OFFICIAL
    hooks.unlink()
    for name, value in (("enabled", lambda: True), ("unavailable", lambda: None), ("hooks_status", lambda: "trusted"),
                        ("logins_needed", lambda: []), ("drift", lambda: []),
                        ("installed_plugins", lambda: {"loadout@agent-loadout"})):
        monkeypatch.setattr(codex, name, value)
    (r,) = [r for r in codex.checks() if r.name == "Codex Serena hooks"]
    assert not r.ok and "pending" in r.detail
