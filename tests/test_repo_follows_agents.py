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


def _real(repo, rel, name):
    (repo / rel / name).mkdir(parents=True)
    (repo / rel / name / "SKILL.md").write_text(f"---\nname: {name}\n---\n")


def test_both_on_links_each_way(repo):
    targets.set_agents({"claude": True, "codex": True})
    _real(repo, ".claude/skills", "pw")
    _real(repo, ".agents/skills", "mine")
    lines = profiles.link_skills(repo, dry_run=False)
    assert Path(os.readlink(repo / ".agents/skills/pw")) == Path("../../.claude/skills/pw")
    assert Path(os.readlink(repo / ".claude/skills/mine")) == Path("../../.agents/skills/mine")
    assert lines == ["linked skill pw for Codex -> .agents/skills/pw",
                     "linked skill mine for Claude Code -> .claude/skills/mine"]
    assert profiles.link_skills(repo, dry_run=False) == []


def test_codex_only_links_a_teammates_claude_skill_and_writes_nothing_under_claude(repo):
    _real(repo, ".claude/skills", "pw")
    targets.set_agents({"claude": False, "codex": True})
    before = sorted(p.name for p in (repo / ".claude" / "skills").iterdir())
    assert profiles.link_skills(repo, dry_run=False) == ["linked skill pw for Codex -> .agents/skills/pw"]
    assert sorted(p.name for p in (repo / ".claude" / "skills").iterdir()) == before


def test_turning_claude_code_on_later_links_codex_skills(repo):
    targets.set_agents({"claude": False, "codex": True})
    _real(repo, ".agents/skills", "notes")
    assert profiles.link_skills(repo, dry_run=False) == []
    assert not (repo / ".claude").exists()
    targets.set_agents({"claude": True, "codex": True})
    assert profiles.link_skills(repo, dry_run=False) == ["linked skill notes for Claude Code -> .claude/skills/notes"]
    assert (repo / ".claude/skills/notes/SKILL.md").is_file()


def test_the_other_agents_link_is_silent_after_claude_code_is_turned_off(repo):
    targets.set_agents({"claude": True, "codex": True})
    _real(repo, ".agents/skills", "notes")
    profiles.link_skills(repo, dry_run=False)  # .claude/skills/notes -> ../../.agents/skills/notes
    targets.set_agents({"claude": False, "codex": True})
    assert profiles.link_skills(repo, dry_run=False) == []


def test_two_real_folders_give_one_line(repo):
    targets.set_agents({"claude": True, "codex": True})
    _real(repo, ".claude/skills", "pw")
    _real(repo, ".agents/skills", "pw")
    assert profiles.link_skills(repo, dry_run=False) == [
        "skill pw: .agents/skills/pw is not a link to .claude/skills/pw, left as is (Codex uses that one)"]


def test_claude_only_links_nothing_into_agents(repo):
    targets.set_agents({"claude": True, "codex": False})
    _real(repo, ".claude/skills", "pw")
    assert profiles.link_skills(repo, dry_run=False) == []
    assert not (repo / ".agents").exists()


def test_a_claude_folder_outside_the_repo_gets_one_line(repo, tmp_path):
    targets.set_agents({"claude": True, "codex": True})
    _real(repo, ".agents/skills", "notes")
    (tmp_path / "elsewhere").mkdir()
    (repo / ".claude").symlink_to(tmp_path / "elsewhere")
    lines = profiles.link_skills(repo, dry_run=False)
    assert len(lines) == 1 and lines[0].startswith("skills not linked:") and ".claude" in lines[0]
    assert list((tmp_path / "elsewhere").iterdir()) == []


def test_link_dry_run_names_the_link_and_writes_nothing(repo):
    targets.set_agents({"claude": True, "codex": True})
    _real(repo, ".agents/skills", "notes")
    assert profiles.link_skills(repo, dry_run=True) == [
        "would link skill notes for Claude Code -> .claude/skills/notes"]
    assert not (repo / ".claude").exists()


def test_profile_links_skills_with_claude_code_only(repo, fake_runner, monkeypatch):
    from loadout import project
    targets.set_agents({"claude": True, "codex": False})
    _real(repo, ".agents/skills", "notes")
    monkeypatch.setattr(profiles, "load_profile", lambda name: profiles.Profile(name="web", description=""))
    assert project.add_profile(repo, "web", install=False) == 0
    assert (repo / ".claude/skills/notes").is_symlink()


def test_new_skill_codex_only_writes_agents_skills_and_no_claude(repo):
    from loadout import backup, new_skill
    targets.set_agents({"claude": False, "codex": True})
    lines = new_skill.create("notes", to="repo", cwd=repo, bk=backup.Backup(description="t"))
    assert (repo / ".agents/skills/notes/SKILL.md").is_file()
    assert not (repo / ".agents/skills/notes").is_symlink()
    assert not (repo / ".claude").exists()
    assert any(".agents/skills/notes/SKILL.md" in l.replace(os.sep, "/") for l in lines)


def test_new_skill_codex_only_refuses_a_name_in_claude_skills(repo):
    from loadout import backup, new_skill
    targets.set_agents({"claude": False, "codex": True})
    _real(repo, ".claude/skills", "notes")
    with pytest.raises(new_skill.Refused):
        new_skill.create("notes", to="repo", cwd=repo, bk=backup.Backup(description="t"))
    assert not (repo / ".agents").exists()


WEB = profiles.Profile(name="web", description="",
                       mcp={"mcpServers": {"x": {"command": "x"}}}, settings={"disabledMcpjsonServers": ["x"]})


def test_codex_only_profile_writes_no_claude_files_and_says_so(repo, fake_runner, monkeypatch, capsys):
    from loadout import codex_project, project
    targets.set_agents({"claude": False, "codex": True})
    monkeypatch.setattr(profiles, "load_profile", lambda name: WEB)
    monkeypatch.setattr(codex_project, "apply", lambda *a, **k: [])
    assert project.add_profile(repo, "web", install=False) == 0
    assert not (repo / ".claude").exists() and not (repo / ".mcp.json").exists()
    out = capsys.readouterr().out
    assert "Claude Code is off: .claude/settings.json not written (turn it on and run loadout profile web again)" in out
    assert "Claude Code is off: .mcp.json not written" in out


def test_turning_claude_code_on_then_profile_writes_them(repo, fake_runner, monkeypatch):
    from loadout import codex_project, project
    targets.set_agents({"claude": False, "codex": True})
    monkeypatch.setattr(profiles, "load_profile", lambda name: WEB)
    monkeypatch.setattr(codex_project, "apply", lambda *a, **k: [])
    project.add_profile(repo, "web", install=False)
    targets.set_agents({"claude": True, "codex": True})
    project.add_profile(repo, "web", install=False)
    assert (repo / ".mcp.json").is_file() and (repo / ".claude/settings.json").is_file()


def test_codex_only_init_writes_no_claude_md_and_no_claude_gitignore_line(repo):
    from loadout import scaffold
    targets.set_agents({"claude": False, "codex": True})
    created, _ = scaffold.scaffold(repo)
    assert repo / "CLAUDE.md" not in created and not (repo / "CLAUDE.md").exists()
    assert (repo / "AGENTS.md").is_file()
    assert scaffold.ensure_gitignore(repo) == [".serena/cache/"]


def test_both_on_init_is_unchanged(repo):
    from loadout import scaffold
    targets.set_agents({"claude": True, "codex": True})
    scaffold.scaffold(repo)
    assert (repo / "CLAUDE.md").is_file()
    assert scaffold.ensure_gitignore(repo) == scaffold.GITIGNORE_LINES


@pytest.mark.parametrize("blocker", [".claude", ".claude/skills"])
def test_a_link_target_that_is_a_file_gives_one_line_not_a_crash(repo, blocker):
    targets.set_agents({"claude": True, "codex": False})
    _real(repo, ".agents/skills", "notes")
    (repo / blocker).parent.mkdir(parents=True, exist_ok=True)
    (repo / blocker).write_text("")
    lines = profiles.link_skills(repo, dry_run=False)
    assert len(lines) == 1 and lines[0].startswith("skills not linked:") and "not a folder" in lines[0]


def test_skills_from_a_folder_outside_the_repo_are_not_linked(repo, tmp_path):
    targets.set_agents({"claude": True, "codex": False})
    (tmp_path / "elsewhere" / "skills" / "evil").mkdir(parents=True)
    (repo / ".agents").symlink_to(tmp_path / "elsewhere")
    lines = profiles.link_skills(repo, dry_run=False)
    assert len(lines) == 1 and lines[0].startswith("skills not linked:") and "outside" in lines[0]
    assert not (repo / ".claude").exists()


def test_calm_summary_names_the_links_it_made(repo, fake_runner, monkeypatch, capsys):
    from loadout import out, project
    monkeypatch.setattr(out, "VERBOSE", False)
    targets.set_agents({"claude": True, "codex": False})
    _real(repo, ".agents/skills", "notes")
    monkeypatch.setattr(profiles, "load_profile", lambda name: profiles.Profile(name="web", description=""))
    assert project.add_profile(repo, "web", install=False) == 0
    text = capsys.readouterr().out
    assert "notes skill link" in text and "nothing to change" not in text


def test_calm_codex_only_notes_are_steps_not_warnings(repo, fake_runner, monkeypatch, capsys):
    from loadout import codex_project, out, project
    monkeypatch.setattr(out, "VERBOSE", False)
    targets.set_agents({"claude": False, "codex": True})
    monkeypatch.setattr(profiles, "load_profile", lambda name: WEB)
    monkeypatch.setattr(codex_project, "apply", lambda *a, **k: [])
    assert project.add_profile(repo, "web", install=False) == 0
    text = capsys.readouterr().out
    assert "applied with problems" not in text and "Claude Code is off: .mcp.json not written" in text


@pytest.mark.parametrize("agents, src, dest", [
    ({"claude": True, "codex": False}, ".agents/skills", ".claude/skills"),
    ({"claude": False, "codex": True}, ".claude/skills", ".agents/skills"),
])
def test_a_skill_entry_that_leads_outside_the_repo_is_not_linked(repo, tmp_path, agents, src, dest):
    targets.set_agents(agents)
    (tmp_path / "elsewhere" / "evil").mkdir(parents=True)
    (repo / src).mkdir(parents=True)
    (repo / src / "evil").symlink_to(tmp_path / "elsewhere" / "evil")
    lines = profiles.link_skills(repo, dry_run=False)
    assert len(lines) == 1 and "evil" in lines[0] and "outside" in lines[0] and "not linked" in lines[0]
    assert not (repo / dest / "evil").exists() and not (repo / dest / "evil").is_symlink()


@pytest.mark.parametrize("linked", [".claude", ".claude/skills"])
def test_a_link_folder_that_is_itself_a_link_inside_the_repo_is_refused(repo, linked):
    # ../../.agents/skills/NAME would resolve from the link's real folder and dangle
    targets.set_agents({"claude": True, "codex": False})
    _real(repo, ".agents/skills", "foo")
    (repo / "alt" / "claude" / "skills").mkdir(parents=True)
    if linked == ".claude":
        (repo / ".claude").symlink_to(repo / "alt" / "claude")
    else:
        (repo / ".claude").mkdir()
        (repo / ".claude" / "skills").symlink_to(repo / "alt" / "claude" / "skills")
    lines = profiles.link_skills(repo, dry_run=False)
    assert len(lines) == 1 and lines[0].startswith("skills not linked:") and "is a link" in lines[0]
    assert list((repo / "alt" / "claude" / "skills").iterdir()) == []


@pytest.mark.parametrize("agents, src, dest, agent", [
    ({"claude": False, "codex": True}, ".claude/skills", ".agents/skills", "Codex"),
    ({"claude": True, "codex": False}, ".agents/skills", ".claude/skills", "Claude Code"),
])
def test_an_absolute_link_to_the_skill_is_reported(repo, agents, src, dest, agent):
    # it works in this checkout only; every other clone gets a dangling link
    targets.set_agents(agents)
    _real(repo, src, "pw")
    (repo / dest).mkdir(parents=True)
    (repo / dest / "pw").symlink_to(repo / src / "pw")
    assert profiles.link_skills(repo, dry_run=False) == [
        f"skill pw: {dest}/pw is not a link to {src}/pw, left as is ({agent} uses that one)"]


def test_two_real_folders_are_reported_with_claude_code_only(repo):
    targets.set_agents({"claude": True, "codex": False})
    _real(repo, ".claude/skills", "pw")
    _real(repo, ".agents/skills", "pw")
    assert profiles.link_skills(repo, dry_run=False) == [
        "skill pw: .claude/skills/pw is not a link to .agents/skills/pw, left as is (Claude Code uses that one)"]


@pytest.mark.parametrize("agents, blocker", [
    ({"claude": False, "codex": True}, ".agents"),
    ({"claude": False, "codex": True}, ".agents/skills"),
    ({"claude": True, "codex": False}, ".claude"),
    ({"claude": True, "codex": False}, ".claude/skills"),
])
def test_a_copy_target_that_is_a_file_gives_one_line_not_a_crash(repo, kit_skill, agents, blocker):
    targets.set_agents(agents)
    (repo / blocker).parent.mkdir(parents=True, exist_ok=True)
    (repo / blocker).write_text("")
    lines = profiles.copy_skills(kit_skill, repo)
    assert len(lines) == 1 and lines[0].startswith("skills not copied:") and "not a folder" in lines[0]


def test_every_link_made_resolves_to_the_skill(repo):
    # a relative link with "/" does not resolve on Windows; CI runs this there
    from loadout import backup, new_skill
    targets.set_agents({"claude": True, "codex": True})
    _real(repo, ".claude/skills", "pw")
    _real(repo, ".agents/skills", "notes")
    profiles.link_skills(repo, dry_run=False)
    new_skill.create("fresh", to="repo", cwd=repo, bk=backup.Backup(description="t"))
    for link in (".agents/skills/pw", ".claude/skills/notes", ".agents/skills/fresh"):
        assert (repo / link).is_symlink() and (repo / link / "SKILL.md").is_file(), link
