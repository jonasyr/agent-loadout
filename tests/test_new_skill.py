"""loadout configure new skill: a SKILL.md stub in one of the three places a skill of yours can live."""
import json

import pytest

from loadout import backup, new_skill, paths, targets


def _agents(monkeypatch, claude=True, codex=True):
    monkeypatch.setattr(targets, "claude_enabled", lambda: claude)
    monkeypatch.setattr(targets, "codex_enabled", lambda: codex)


def _restore(bk):
    _, ok, _ = backup.restore(bk.root)
    assert ok


def test_global_writes_the_stub_and_links_it_for_both_agents(fake_home, monkeypatch):
    _agents(monkeypatch)
    bk = backup.Backup(description="t")
    lines = new_skill.create("notes", bk=bk)
    skill = paths.personal_root() / "skills" / "notes" / "SKILL.md"
    assert skill.read_text(encoding="utf-8").startswith("---\nname: notes\ndescription: \"TODO:")
    for dest in (paths.claude_home() / "skills" / "notes", paths.agents_skills() / "notes"):
        assert dest.is_symlink() and dest.resolve() == skill.parent.resolve()
    assert any("notes" in l and "created" in l for l in lines)


def test_only_the_agents_that_are_on_get_a_link(fake_home, monkeypatch):
    _agents(monkeypatch, claude=False, codex=True)
    new_skill.create("notes", bk=backup.Backup(description="t"))
    assert (paths.agents_skills() / "notes").is_symlink()
    assert not (paths.claude_home() / "skills").exists()


def test_restore_removes_the_folder_and_the_links(fake_home, monkeypatch):
    _agents(monkeypatch)
    bk = backup.Backup(description="t")
    new_skill.create("notes", bk=bk)
    _restore(bk)
    assert not (paths.personal_root() / "skills" / "notes").exists()
    for dest in (paths.claude_home() / "skills" / "notes", paths.agents_skills() / "notes"):
        assert not dest.exists() and not dest.is_symlink()


@pytest.mark.parametrize("name", ["Notes", "-x", "a/b", "..", "", "x" * 65, "a_b"])
def test_a_bad_name_is_bad_input_and_writes_nothing(fake_home, monkeypatch, name):
    _agents(monkeypatch)
    with pytest.raises(new_skill.BadInput):
        new_skill.create(name, bk=backup.Backup(description="t"))
    assert not (paths.personal_root() / "skills").exists()


def test_an_unknown_target_is_bad_input(fake_home, monkeypatch):
    _agents(monkeypatch)
    with pytest.raises(new_skill.BadInput):
        new_skill.create("notes", to="elsewhere", bk=backup.Backup(description="t"))


def test_an_existing_link_destination_is_refused_even_a_dangling_one(fake_home, monkeypatch):
    _agents(monkeypatch)
    dest = paths.agents_skills() / "notes"
    dest.parent.mkdir(parents=True)
    dest.symlink_to(fake_home / "gone", target_is_directory=True)
    with pytest.raises(new_skill.Refused, match="already exists"):
        new_skill.create("notes", bk=backup.Backup(description="t"))
    assert not (paths.personal_root() / "skills" / "notes").exists()


def test_a_name_taken_in_another_case_is_refused(fake_home, monkeypatch):
    _agents(monkeypatch)
    (paths.claude_home() / "skills" / "Notes").mkdir(parents=True)
    with pytest.raises(new_skill.Refused):
        new_skill.create("notes", bk=backup.Backup(description="t"))


def test_running_it_twice_refuses_the_second_time(fake_home, monkeypatch):
    _agents(monkeypatch)
    new_skill.create("notes", bk=backup.Backup(description="t"))
    before = (paths.personal_root() / "skills" / "notes" / "SKILL.md").read_bytes()
    with pytest.raises(new_skill.Refused):
        new_skill.create("notes", description="other", bk=backup.Backup(description="t"))
    assert (paths.personal_root() / "skills" / "notes" / "SKILL.md").read_bytes() == before


def test_a_secret_or_a_line_break_in_the_description_is_refused(fake_home, monkeypatch):
    _agents(monkeypatch)
    token = "ghp_" + "Z" * 36
    for text in (f"uses {token}", "two\nlines"):
        with pytest.raises(new_skill.Refused):
            new_skill.create("notes", description=text, bk=backup.Backup(description="t"))
    assert not (paths.personal_root() / "skills" / "notes").exists()


def test_the_description_lands_in_the_frontmatter(fake_home, monkeypatch):
    _agents(monkeypatch)
    new_skill.create("notes", description="Use when taking notes.", bk=backup.Backup(description="t"))
    text = (paths.personal_root() / "skills" / "notes" / "SKILL.md").read_text(encoding="utf-8")
    assert "description: \"Use when taking notes.\"\n" in text


def test_project_writes_into_the_profile_and_lists_it(fake_home, monkeypatch):
    _agents(monkeypatch)
    bk = backup.Backup(description="t")
    new_skill.create("notes", to="project:mine", bk=bk)
    assert (paths.personal_root() / "profiles" / "skills" / "notes" / "SKILL.md").is_file()
    data = json.loads((paths.personal_root() / "profiles" / "mine.json").read_text())
    assert data["skills"] == ["notes"]
    assert not (paths.claude_home() / "skills" / "notes").exists()  # reaches a repo through loadout profile
    _restore(bk)
    assert not (paths.personal_root() / "profiles" / "skills" / "notes").exists()
    assert not (paths.personal_root() / "profiles" / "mine.json").exists()


def test_a_bad_profile_name_is_bad_input(fake_home, monkeypatch):
    _agents(monkeypatch)
    with pytest.raises(new_skill.BadInput):
        new_skill.create("notes", to="project:../x", bk=backup.Backup(description="t"))


@pytest.mark.parametrize("text", ["{broken", '{"skills": "notes"}'])
def test_a_damaged_profile_is_refused_and_left_alone(fake_home, monkeypatch, text):
    _agents(monkeypatch)
    path = paths.personal_root() / "profiles" / "mine.json"
    path.parent.mkdir(parents=True)
    path.write_text(text)
    with pytest.raises(new_skill.Refused):
        new_skill.create("notes", to="project:mine", bk=backup.Backup(description="t"))
    assert path.read_text() == text
    assert not (paths.personal_root() / "profiles" / "skills" / "notes").exists()


def _repo(tmp_path, git_file=False):
    repo = tmp_path / "repo"
    repo.mkdir()
    if git_file:
        (repo / ".git").write_text("gitdir: /elsewhere/.git/worktrees/repo\n")
    else:
        (repo / ".git").mkdir()
    return repo


def test_repo_writes_claude_skills_and_links_agents_skills(fake_home, monkeypatch, tmp_path):
    _agents(monkeypatch)
    repo = _repo(tmp_path)
    bk = backup.Backup(description="t")
    new_skill.create("notes", to="repo", cwd=repo, bk=bk)
    assert (repo / ".claude" / "skills" / "notes" / "SKILL.md").is_file()
    link = repo / ".agents" / "skills" / "notes"
    assert link.is_symlink() and str(link.readlink()) == "../../.claude/skills/notes"
    _restore(bk)
    assert not (repo / ".claude" / "skills" / "notes").exists() and not link.is_symlink()


def test_repo_without_codex_writes_no_agents_link(fake_home, monkeypatch, tmp_path):
    _agents(monkeypatch, claude=True, codex=False)
    repo = _repo(tmp_path)
    new_skill.create("notes", to="repo", cwd=repo, bk=backup.Backup(description="t"))
    assert not (repo / ".agents").exists()


def test_repo_root_is_found_from_a_subfolder_and_a_worktree(fake_home, monkeypatch, tmp_path):
    _agents(monkeypatch)
    repo = _repo(tmp_path, git_file=True)
    (repo / "src" / "deep").mkdir(parents=True)
    new_skill.create("notes", to="repo", cwd=repo / "src" / "deep", bk=backup.Backup(description="t"))
    assert (repo / ".claude" / "skills" / "notes" / "SKILL.md").is_file()


def test_repo_outside_git_is_refused(fake_home, monkeypatch, tmp_path):
    _agents(monkeypatch)
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(new_skill.Refused, match="git repo"):
        new_skill.create("notes", to="repo", cwd=plain, bk=backup.Backup(description="t"))
    assert not (plain / ".claude").exists()


def test_repo_skills_folder_linking_outside_is_refused(fake_home, monkeypatch, tmp_path):
    _agents(monkeypatch)
    repo = _repo(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (repo / ".claude").symlink_to(outside, target_is_directory=True)
    with pytest.raises(new_skill.Refused, match="outside"):
        new_skill.create("notes", to="repo", cwd=repo, bk=backup.Backup(description="t"))
    assert not any(outside.iterdir())


def _frontmatter(path):
    """name and description as a YAML loader reads a double-quoted scalar (a JSON string is one)."""
    lines = path.read_text(encoding="utf-8").split("---\n")[1].splitlines()
    fields = dict(l.split(": ", 1) for l in lines)
    return {"name": fields["name"], "description": json.loads(fields["description"])}  # must be quoted


@pytest.mark.parametrize("text", ["Use when: the user asks", "[draft] notes", "# notes", "yes", 'say "hi"', "a #tag"])
def test_any_description_keeps_the_frontmatter_valid(fake_home, monkeypatch, text):
    _agents(monkeypatch)
    new_skill.create("notes", description=text, bk=backup.Backup(description="t"))
    fm = _frontmatter(paths.personal_root() / "skills" / "notes" / "SKILL.md")
    assert fm == {"name": "notes", "description": text}


def test_an_empty_description_is_refused(fake_home, monkeypatch):
    _agents(monkeypatch)
    with pytest.raises(new_skill.Refused):
        new_skill.create("notes", description="  ", bk=backup.Backup(description="t"))
    assert not (paths.personal_root() / "skills" / "notes").exists()


def test_repo_that_is_the_home_folder_is_refused(fake_home, monkeypatch):
    """Dotfiles in a repo at ~: the "repo" would be ~, and .claude/skills there is Claude Code's own folder."""
    _agents(monkeypatch, claude=False, codex=True)
    (paths.home() / ".git").mkdir()
    (paths.home() / "Documents").mkdir()
    with pytest.raises(new_skill.Refused, match="home"):
        new_skill.create("notes", to="repo", cwd=paths.home() / "Documents", bk=backup.Backup(description="t"))
    assert not (paths.claude_home() / "skills").exists() and not paths.agents_skills().exists()


def test_a_skills_json_pointer_with_that_name_is_taken(fake_home, monkeypatch, tmp_path):
    _agents(monkeypatch)
    shared = tmp_path / "shared-notes"
    shared.mkdir()
    pointers = paths.personal_root() / "skills.json"
    pointers.parent.mkdir(parents=True, exist_ok=True)
    pointers.write_text(json.dumps({"notes": str(shared)}))
    with pytest.raises(new_skill.Refused, match="skills.json"):
        new_skill.create("notes", bk=backup.Backup(description="t"))
    assert not (paths.personal_root() / "skills" / "notes").exists()


def test_repo_agents_skills_that_is_a_file_is_refused_before_writing(fake_home, monkeypatch, tmp_path):
    _agents(monkeypatch)
    repo = _repo(tmp_path)
    (repo / ".agents").mkdir()
    (repo / ".agents" / "skills").write_text("not a folder")
    with pytest.raises(new_skill.Refused, match="not a folder"):
        new_skill.create("notes", to="repo", cwd=repo, bk=backup.Backup(description="t"))
    assert not (repo / ".claude").exists()
