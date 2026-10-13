"""A repo's symlinks never make init/profile write outside the repo."""
import os

import pytest

from loadout import profiles, project, scaffold

pytestmark = pytest.mark.skipif(os.name == "nt", reason="symlinks need Developer Mode on Windows")


def _repo(tmp_path):
    repo, outside = tmp_path / "repo", tmp_path / "outside"
    repo.mkdir(); outside.mkdir()
    return repo, outside


def test_profile_settings_through_a_symlinked_claude_folder(tmp_path):
    repo, outside = _repo(tmp_path)
    (repo / ".claude").symlink_to(outside)
    prof = profiles.Profile(name="t", description="", settings={"env": {"A": "1"}})
    changed, skipped = profiles.apply_profile(prof, repo)
    assert not (outside / "settings.json").exists()
    assert skipped and ".claude/settings.json" in skipped[0]
    assert changed == []


def test_mcp_json_symlink_is_not_followed(tmp_path):
    repo, outside = _repo(tmp_path)
    (repo / ".mcp.json").symlink_to(outside / "x.json")  # dangling
    prof = profiles.Profile(name="t", description="", mcp={"mcpServers": {"a": {"command": "x"}}})
    _, skipped = profiles.apply_profile(prof, repo)
    assert not (outside / "x.json").exists()
    assert skipped


def test_add_profile_reports_skipped_and_fails(tmp_path, capsys, monkeypatch):
    repo, outside = _repo(tmp_path)
    (repo / ".mcp.json").symlink_to(outside / "x.json")
    prof = profiles.Profile(name="t", description="", mcp={"mcpServers": {"a": {"command": "x"}}})
    monkeypatch.setattr(profiles, "load_profile", lambda name: prof)
    assert project.add_profile(repo, "t", install=False) == 1
    assert "skipped .mcp.json: it points outside the repo" in capsys.readouterr().out


def test_scaffold_never_creates_through_a_dangling_symlink(tmp_path):
    repo, outside = _repo(tmp_path)
    (repo / "AGENTS.md").symlink_to(outside / "AGENTS.md")
    created, notes = scaffold.scaffold(repo)
    assert not (outside / "AGENTS.md").exists()
    assert repo / "AGENTS.md" not in created


def test_scaffold_skips_a_symlinked_docs_folder(tmp_path):
    repo, outside = _repo(tmp_path)
    (repo / "docs").symlink_to(outside)
    scaffold.scaffold(repo)
    assert list(outside.iterdir()) == []


def test_gitignore_symlink_outside_is_not_appended(tmp_path):
    repo, outside = _repo(tmp_path)
    (outside / "g").write_text("x\n")
    (repo / ".gitignore").symlink_to(outside / "g")
    assert scaffold.ensure_gitignore(repo) == []
    assert (outside / "g").read_text() == "x\n"


def test_init_never_runs_git_init_through_a_dangling_git_symlink(tmp_path, fake_home, fake_runner, capsys):
    from loadout import project
    repo, outside = _repo(tmp_path)
    (repo / ".git").symlink_to(outside / "gitdir")
    rc = project.init(repo, [], yes=True, install=False, dry_run=False, ask=lambda q: "", interactive=False)
    assert ["git", "init"] not in fake_runner.calls
    assert "skipped git init" in capsys.readouterr().out
    assert rc == 1


def test_init_exits_1_when_a_template_or_gitignore_was_skipped(tmp_path, fake_home, fake_runner, capsys):
    from loadout import project
    repo, outside = _repo(tmp_path)
    (repo / ".git").mkdir()
    (repo / "AGENTS.md").unlink(missing_ok=True)
    (repo / "docs").symlink_to(outside)
    (outside / "g").write_text("x\n")
    (repo / ".gitignore").symlink_to(outside / "g")
    rc = project.init(repo, [], yes=True, install=False, dry_run=False, ask=lambda q: "", interactive=False)
    out = capsys.readouterr().out
    assert rc == 1
    assert "skipped .gitignore" in out


def test_skills_not_copied_counts_as_a_problem(tmp_path, fake_home, fake_runner, monkeypatch):
    from loadout import profiles, project
    repo, outside = _repo(tmp_path)
    (repo / ".claude").symlink_to(outside)
    monkeypatch.setattr(profiles, "load_profile", lambda name: profiles.Profile(name="t", description="", skills=["x"]))
    assert project.add_profile(repo, "t", install=False) == 1


def test_a_dangling_template_symlink_outside_is_named_and_fails_init(tmp_path, fake_home, fake_runner, capsys):
    from loadout import project
    repo, outside = _repo(tmp_path)
    (repo / ".git").mkdir()
    (repo / "AGENTS.md").symlink_to(outside / "AGENTS.md")
    rc = project.init(repo, [], yes=True, install=False, dry_run=False, ask=lambda q: "", interactive=False)
    assert "skipped AGENTS.md" in capsys.readouterr().out and rc == 1
