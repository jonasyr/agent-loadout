"""Fixes from the Codex review of PR 44."""
import pytest

from loadout import backup, codex_project, profiles, project, repo_writes, targets


@pytest.fixture
def repo(fake_home, fake_runner, tmp_path):
    p = tmp_path / "repo"
    (p / ".git").mkdir(parents=True)
    return p


def test_a_file_changed_after_the_plan_is_left_as_is(repo):
    (repo / ".gitignore").write_text("a\n")
    w = repo_writes.RepoWrites(repo)
    w.modify(repo / ".gitignore", "a\nb\n", "init")
    w.create(repo / "AGENTS.md", "loadout\n", "init")
    (repo / ".gitignore").write_text("a\nmine\n")      # edited while the question was open
    (repo / "AGENTS.md").write_text("theirs\n")        # appeared while the question was open
    problems = w.apply(backup.Backup(description="t", repo=repo))
    assert len(problems) == 2 and all("changed since the plan" in p for p in problems)
    assert (repo / ".gitignore").read_text() == "a\nmine\n" and (repo / "AGENTS.md").read_text() == "theirs\n"


def test_links_for_skills_a_command_installed_are_asked_about(repo, fake_runner, monkeypatch, capsys):
    targets.set_agents({"claude": True, "codex": True})
    prof = profiles.Profile(name="web", description="", commands=[["installer"]])
    monkeypatch.setattr(profiles, "load_profile", lambda n: prof)

    def run(cmd, **k):
        if cmd[0] == "installer":
            (repo / ".claude" / "skills" / "pw").mkdir(parents=True)
        from loadout import runner
        return runner.Result(0, "", "")
    monkeypatch.setattr(repo_writes.runner, "run", run)
    answers = []
    project.add_profile(repo, "web", approve=lambda plan: answers.append(plan) or len(answers) == 1)
    assert len(answers) == 2 and any("link    .agents/skills/pw" in l for l in answers[1])
    assert not (repo / ".agents" / "skills" / "pw").exists()  # the second plan was declined


def test_a_failed_codex_plugin_is_not_named_in_the_repo(repo, monkeypatch):
    targets.set_agents({"claude": False, "codex": True})
    prof = profiles.Profile(name="thesis", description="", install=["x@claude-plugins-official"])
    monkeypatch.setattr(profiles, "load_profile", lambda n: prof)
    monkeypatch.setattr(codex_project, "plugins", lambda p, dry_run: ["plugin x@claude-plugins-official: failed: boom"])
    project.add_profile(repo, "thesis", approve=lambda plan: True)
    cfg = repo / ".codex" / "config.toml"
    assert not cfg.exists() or "x@claude-plugins-official" not in cfg.read_text()


def test_a_declined_init_plan_exits_0_even_with_a_skip(repo, tmp_path):
    import os
    if os.name == "nt":
        pytest.skip("POSIX symlink")
    (repo / "AGENTS.md").symlink_to(tmp_path / "outside.md")  # a scaffold skip: rc 1 if applied
    assert project.init(repo, [], yes=False, install=False, dry_run=False, ask=lambda q: "n", interactive=False) == 0
    assert project.init(repo, [], yes=False, install=False, dry_run=True, ask=lambda q: "n", interactive=False) == 0


def test_nothing_is_applied_when_the_agent_choice_changed_after_the_plan(repo, monkeypatch):
    targets.set_agents({"claude": True, "codex": True})
    prof = profiles.Profile(name="web", description="", settings={"a": 1})
    monkeypatch.setattr(profiles, "load_profile", lambda n: prof)

    def approve(plan):
        (repo / ".loadout.json").write_text('{\n  "agents": [\n    "codex"\n  ]\n}\n')  # another process, meanwhile
        return True
    assert project.add_profile(repo, "web", approve=approve) == 1
    assert not (repo / ".claude").exists()


def test_manage_false_new_skill_shows_the_plan_first(repo):
    from loadout import new_skill
    (repo / ".loadout.json").write_text('{"manage": false}')
    lines = new_skill.create("notes", "repo", "Use when x", cwd=repo, approve=lambda plan: True)
    assert lines[-1] == project.MANAGE_OFF and any("SKILL.md" in l for l in lines[:-1])
    assert not (repo / ".claude").exists() and not (repo / ".agents").exists()
