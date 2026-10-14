"""Repo files follow the agents that are on (ADR 0027)."""
import os
from pathlib import Path

import pytest

from loadout import profiles, targets


@pytest.fixture
def repo(fake_home, tmp_path):
    p = tmp_path / "repo"
    (p / ".git").mkdir(parents=True)
    return p


@pytest.fixture
def kit_skill(fake_home, monkeypatch, tmp_path):
    src = tmp_path / "personal" / "profiles" / "skills" / "pw"
    src.mkdir(parents=True)
    (src / "SKILL.md").write_text("---\nname: pw\n---\n")
    monkeypatch.setattr(profiles, "_skill_source", lambda name: src if name == "pw" else None)
    return profiles.Profile(name="web", description="", skills=["pw"])


@pytest.mark.parametrize("agents, real, link", [
    ({"claude": True, "codex": True}, ".claude/skills", ".agents/skills"),
    ({"claude": True, "codex": False}, ".claude/skills", None),
    ({"claude": False, "codex": True}, ".agents/skills", None),
])
def test_repo_skill_dirs_follow_the_agents(repo, agents, real, link):
    targets.set_agents(agents)
    got_real, got_link = profiles.repo_skill_dirs(repo)
    assert got_real == repo / real
    assert got_link == (repo / link if link else None)


def test_codex_only_copies_into_agents_skills_and_writes_no_claude(repo, kit_skill):
    targets.set_agents({"claude": False, "codex": True})
    lines = profiles.copy_skills(kit_skill, repo)
    assert (repo / ".agents" / "skills" / "pw" / "SKILL.md").is_file()
    assert not (repo / ".claude").exists()
    assert lines == [f"copied skill pw -> {repo / '.agents' / 'skills' / 'pw'}"]


def test_a_skill_in_the_other_folder_is_left_as_is(repo, kit_skill):
    targets.set_agents({"claude": False, "codex": True})
    (repo / ".claude" / "skills" / "pw").mkdir(parents=True)  # a teammate's
    lines = profiles.copy_skills(kit_skill, repo)
    assert lines == [f"skill pw: {repo / '.claude' / 'skills' / 'pw'} exists, left as is"]
    assert not (repo / ".agents").exists()


def test_codex_only_dry_run_creates_nothing(repo, kit_skill):
    targets.set_agents({"claude": False, "codex": True})
    lines = profiles.copy_skills(kit_skill, repo, dry_run=True)
    assert lines == [f"would copy skill pw -> {repo / '.agents' / 'skills' / 'pw'}"]
    assert not (repo / ".agents").exists()


def test_codex_only_agents_folder_outside_the_repo_is_refused(repo, kit_skill, tmp_path):
    targets.set_agents({"claude": False, "codex": True})
    (tmp_path / "elsewhere").mkdir()
    (repo / ".agents").symlink_to(tmp_path / "elsewhere")
    lines = profiles.copy_skills(kit_skill, repo)
    assert len(lines) == 1 and "points outside" in lines[0] and ".agents" in lines[0]
    assert list((tmp_path / "elsewhere").iterdir()) == []
