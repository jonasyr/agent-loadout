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
    assert skill.read_text(encoding="utf-8").startswith("---\nname: notes\ndescription: TODO:")
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
    assert "description: Use when taking notes.\n" in text
