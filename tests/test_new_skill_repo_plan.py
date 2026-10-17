"""`configure new skill --to repo`: the repo's agents, manage: false, a plan and a yes (spec Parts 0, 1)."""
import pytest

from loadout import new_skill, targets


@pytest.fixture
def repo(fake_home, tmp_path):
    p = tmp_path / "repo"
    (p / ".git").mkdir(parents=True)
    return p


def test_a_codex_only_repo_gets_the_skill_in_agents_skills(repo):
    targets.set_agents({"claude": True, "codex": True})
    (repo / ".loadout.json").write_text('{\n  "agents": [\n    "codex"\n  ]\n}\n')
    new_skill.create("notes", "repo", "Use when x", cwd=repo, approve=lambda plan: True)
    assert (repo / ".agents" / "skills" / "notes" / "SKILL.md").is_file() and not (repo / ".claude").exists()


def test_manage_false_writes_nothing(repo):
    (repo / ".loadout.json").write_text('{"manage": false}')
    assert new_skill.create("notes", "repo", "Use when x", cwd=repo, approve=lambda plan: True) == [
        "manage is false in .loadout.json: nothing written"]
    assert not (repo / ".claude").exists() and not (repo / ".agents").exists()


def test_a_declined_plan_writes_nothing(repo):
    targets.set_agents({"claude": True, "codex": False})
    seen = []
    lines = new_skill.create("notes", "repo", "Use when x", cwd=repo, approve=lambda plan: seen.append(plan) or False)
    assert lines == ["nothing changed"] and not (repo / ".claude").exists()
    assert any("create  .claude/skills/notes/SKILL.md" in l for l in seen[0])


def test_a_broken_loadout_json_is_refused_with_its_reason(repo):
    (repo / ".loadout.json").write_text("{not json")
    with pytest.raises(new_skill.Refused, match=r"\.loadout\.json:"):
        new_skill.create("notes", "repo", "Use when x", cwd=repo, approve=lambda plan: True)
    assert not (repo / ".claude").exists()
