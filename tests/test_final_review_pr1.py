"""Fixes from the final whole-branch review of repo-agents PR 1."""
import json

import pytest

from loadout import codex_project, new_skill, profiles, project, repo_config, repo_writes, targets


@pytest.fixture
def repo(fake_home, fake_runner, tmp_path):
    p = tmp_path / "repo"
    (p / ".git").mkdir(parents=True)
    return p


def test_the_codex_plugins_backup_line_is_shown(repo, monkeypatch, capsys):
    targets.set_agents({"claude": False, "codex": True})
    monkeypatch.setattr(profiles, "load_profile", lambda n: profiles.Profile(name="web", description="", install=["x@y"]))
    monkeypatch.setattr(codex_project, "plugins", lambda prof, dry_run: ["backup: /b (undo: loadout restore /b)"])
    project.add_profile(repo, "web", approve=lambda plan: True)
    assert "loadout restore /b" in capsys.readouterr().out


def test_a_secret_in_a_json_list_is_masked(repo):
    value = "Zq8xLp2Vt9" * 3
    w = repo_writes.RepoWrites(repo)
    w.create(repo / ".mcp.json", json.dumps({"mcpServers": {"x": {"args": ["--api-key", value, "--token=" + value]}}}) + "\n", "p")
    (repo / "o.json").write_text(json.dumps({"args": ["--password", value]}) + "\n")
    w.modify(repo / "o.json", json.dumps({"args": ["--password", value, "-v"]}) + "\n", "p")
    text = "\n".join(w.render())
    assert value not in text and "--api-key" in text


@pytest.mark.parametrize("agents", ['[["claude"]]', "[{}]", "[1]"])
def test_unhashable_or_odd_agents_are_refused_not_a_traceback(repo, agents):
    (repo / ".loadout.json").write_text('{"agents": %s}' % agents)
    with pytest.raises(repo_config.Invalid):
        repo_config.load(repo)


def test_manage_false_new_skill_prints_the_plan_and_exits_0(repo, capsys):
    (repo / ".loadout.json").write_text('{"manage": false}')
    assert new_skill.create("notes", "repo", "Use when x", cwd=repo, approve=lambda plan: True)[-1] == project.MANAGE_OFF
    assert not (repo / ".claude").exists() and not (repo / ".agents").exists()


def test_the_not_written_reason_follows_the_pending_choice(repo):
    targets.set_agents({"claude": True, "codex": True})
    prof = profiles.Profile(name="web", description="", settings={"a": 1})
    with repo_config.pending(repo, frozenset({"codex"})):
        (note,) = profiles.repo_off_notes(prof, repo)
    assert "this repo is for Codex only" in note


def test_a_user_without_codex_in_a_codex_repo_is_told(repo, monkeypatch, capsys):
    targets.set_agents({"claude": True, "codex": False})
    (repo / ".loadout.json").write_text('{\n  "agents": [\n    "claude",\n    "codex"\n  ]\n}\n')
    prof = profiles.Profile(name="thesis", description="", install=["x@claude-plugins-official"])
    monkeypatch.setattr(profiles, "load_profile", lambda n: prof)
    project.add_profile(repo, "thesis", dry_run=True)
    assert "not installed for Codex, which is off for you" in capsys.readouterr().out
