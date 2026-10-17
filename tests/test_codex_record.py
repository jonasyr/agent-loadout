"""The repo's .codex/config.toml: owned text only added, its entries recorded (spec Part 2)."""
import json
from pathlib import Path

import pytest

from loadout import backup, codex_project, profiles, project, targets

PROF = profiles.Profile(name="web", description="", mcp={"mcpServers": {"cd": {"command": "npx", "args": ["-y", "cd@1"]}}},
                        install=["pw@claude-plugins-official"])
CD = "mcp_servers/cd"
PW = "plugins/pw@claude-plugins-official/enabled"


@pytest.fixture
def repo(fake_home, fake_runner, tmp_path):
    p = tmp_path / "repo"
    (p / ".git").mkdir(parents=True)
    (p / ".loadout.json").write_text('{\n  "agents": [\n    "codex"\n  ]\n}\n')
    targets.set_agents({"claude": False, "codex": True})
    return p


def rec(repo):
    return json.loads((repo / ".loadout.json").read_text()).get("profiles", {}).get("web", {}).get(".codex/config.toml", {})


def test_config_records_what_it_added(repo):
    codex_project.config(PROF, repo, False)
    assert rec(repo) == {CD: {"command": "npx", "args": ["-y", "cd@1"]}, PW: True}


def test_a_table_a_person_removed_is_not_added_again(repo):
    codex_project.config(PROF, repo, False)
    cfg = repo / ".codex" / "config.toml"
    cfg.write_text("")
    lines = codex_project.config(PROF, repo, False)
    assert cfg.read_text() == "" and sum("kept removed" in l for l in lines) == 2


def test_a_table_the_user_already_had_is_not_recorded(repo):
    cfg = repo / ".codex" / "config.toml"
    cfg.parent.mkdir()
    cfg.write_text('[mcp_servers.cd]\ncommand = "npx"\nargs = ["-y", "cd@1"]\n')
    codex_project.config(PROF, repo, False)
    assert CD not in rec(repo) and PW in rec(repo)


def test_a_newer_table_in_the_profile_is_noted_not_written(repo):
    codex_project.config(PROF, repo, False)
    newer = profiles.Profile(name="web", description="", mcp={"mcpServers": {"cd": {"command": "npx", "args": ["-y", "cd@2"]}}},
                             install=PROF.install)
    lines = codex_project.config(newer, repo, False)
    assert "cd@1" in (repo / ".codex" / "config.toml").read_text()
    assert any("has a new definition" in l for l in lines) and not any("left as is" in l for l in lines)


def test_the_held_config_records_only_plugins_that_installed(repo, monkeypatch, capsys):
    monkeypatch.setattr(profiles, "load_profile", lambda n: PROF)
    monkeypatch.setattr(codex_project, "plugins", lambda p, dry_run: ["plugin pw@claude-plugins-official: failed: boom"])
    project.add_profile(repo, "web", install=True, approve=lambda plan: True)
    assert CD in rec(repo) and PW not in rec(repo)
    assert "written after the Codex plugin installs" in capsys.readouterr().out


def test_restore_after_the_held_record_write_returns_every_file(repo, monkeypatch, capsys):
    original = (repo / ".loadout.json").read_bytes()
    monkeypatch.setattr(profiles, "load_profile", lambda n: PROF)
    monkeypatch.setattr(codex_project, "plugins", lambda p, dry_run: [])
    project.add_profile(repo, "web", install=True, approve=lambda plan: True)
    assert PW in rec(repo)
    line = next(l for l in capsys.readouterr().out.splitlines() if "undo: loadout restore " in l)
    _, ok, _ = backup.restore(Path(line.split("undo: loadout restore ", 1)[1].strip()))
    assert ok and (repo / ".loadout.json").read_bytes() == original and not (repo / ".codex" / "config.toml").exists()
