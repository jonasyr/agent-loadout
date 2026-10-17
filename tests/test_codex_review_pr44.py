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


def test_a_changed_agent_choice_also_stops_the_steps_after_the_plan(repo, monkeypatch):
    targets.set_agents({"claude": False, "codex": True})
    prof = profiles.Profile(name="thesis", description="", install=["x@claude-plugins-official"])
    monkeypatch.setattr(profiles, "load_profile", lambda n: prof)
    ran = []
    monkeypatch.setattr(codex_project, "plugins", lambda p, dry_run: ran.append(p.name) or [])

    def approve(plan):
        (repo / ".loadout.json").write_text('{"manage": false}')
        return True
    assert project.add_profile(repo, "thesis", approve=approve) == 1
    assert ran == [] and not (repo / ".codex").exists()


def test_new_skill_stops_when_the_agent_choice_changed(repo):
    from loadout import new_skill
    targets.set_agents({"claude": True, "codex": True})

    def approve(plan):
        (repo / ".loadout.json").write_text('{\n  "agents": [\n    "codex"\n  ]\n}\n')
        return True
    with pytest.raises(new_skill.Refused, match="changed since the plan"):
        new_skill.create("notes", "repo", "Use when x", cwd=repo, approve=approve)
    assert not (repo / ".claude").exists() and not (repo / ".agents").exists()


def test_adopt_shows_the_profile_plan_before_writing(repo, monkeypatch, capsys):
    from loadout import adopt, own
    monkeypatch.setattr(profiles, "load_profile", lambda n: profiles.Profile(name="mine", description="", settings={"a": 1}))
    monkeypatch.setattr(own, "candidate_repos", lambda item: [repo])
    answers = iter(["y", "n"])  # apply to the detected repo: yes; the plan: no
    adopt._offer_profiles({"mine": [object()]}, lambda q: next(answers))
    assert "Plan for" in capsys.readouterr().out and not (repo / ".claude").exists()


def test_a_new_json_file_shows_no_removed_entry(repo):
    w = repo_writes.RepoWrites(repo)
    w.create(repo / "a.json", '{\n  "x": 1\n}\n', "p")
    assert not any(l.strip() == "-" or l.strip().startswith("- ") for l in w.render())


def test_the_follow_up_plan_stops_when_the_agent_choice_changed(repo, monkeypatch):
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

    def approve(plan):
        answers.append(plan)
        if len(answers) == 2:
            (repo / ".loadout.json").write_text('{"manage": false}')
        return True
    assert project.add_profile(repo, "web", approve=approve) == 1
    assert len(answers) == 2 and not (repo / ".agents").exists()


def test_a_secret_nested_in_a_list_of_objects_is_masked(repo):
    import json
    value = "Zq8xLp2Vt9" * 3
    w = repo_writes.RepoWrites(repo)
    w.create(repo / "h.json", json.dumps({"hooks": [{"args": ["--token", value]}, [["--password", value]]]}) + "\n", "p")
    assert value not in "\n".join(w.render())


def test_a_failed_loadout_json_write_stops_the_plan(repo, monkeypatch):
    from loadout import repo_config
    (repo / ".loadout.json").write_text('{\n  "agents": [\n    "claude"\n  ]\n}\n')
    w = repo_writes.RepoWrites(repo)
    w.watch(repo / repo_config.FILE)
    w.modify(repo / repo_config.FILE, '{\n  "agents": [\n    "codex"\n  ]\n}\n', "init")
    w.create(repo / "AGENTS.md", "x\n", "init")
    real = repo_writes.write_atomic

    def locked(path, text, *a, **k):
        if path.name == ".loadout.json":
            raise PermissionError(13, "locked")
        return real(path, text, *a, **k)
    monkeypatch.setattr(repo_writes, "write_atomic", locked)
    problems = w.apply(backup.Backup(description="t", repo=repo))
    assert w.stale and problems and not (repo / "AGENTS.md").exists()


def test_a_dotted_key_and_a_nested_path_stay_distinct(repo):
    (repo / "d.json").write_text('{\n  "a.b": 2\n}\n')
    w = repo_writes.RepoWrites(repo)
    w.modify(repo / "d.json", '{\n  "a.b": 2,\n  "a": {\n    "b": 2\n  }\n}\n', "p")
    assert any(l.strip().startswith("+ a.b") for l in w.render())


def test_git_init_does_not_run_when_git_appeared_after_the_plan(fake_home, fake_runner, tmp_path):
    proj = tmp_path / "p"
    proj.mkdir()
    outside = tmp_path / "elsewhere"
    outside.mkdir()

    def ask(q):
        if "Apply" in q:
            (proj / ".git").symlink_to(outside, target_is_directory=True)  # appeared while the question was open
            return "y"
        return "-"
    import os
    if os.name == "nt":
        pytest.skip("POSIX symlink")
    project.init(proj, [], yes=False, install=False, dry_run=False, ask=ask, interactive=True)
    assert ["git", "init"] not in fake_runner.calls


def test_a_git_init_step_refuses_when_git_exists_at_run_time(repo, fake_runner, tmp_path):
    proj = tmp_path / "q"
    proj.mkdir()
    w = repo_writes.RepoWrites(proj)
    w.run(["git", "init"], "init", absent=(proj / ".git",))
    (proj / ".git").mkdir()
    problems = w.apply(backup.Backup(description="t", repo=proj))
    assert ["git", "init"] not in fake_runner.calls and problems


def test_new_skill_fails_when_its_file_appeared_after_the_plan(repo):
    from loadout import new_skill
    targets.set_agents({"claude": True, "codex": False})

    def approve(plan):
        (repo / ".claude" / "skills" / "notes").mkdir(parents=True)
        (repo / ".claude" / "skills" / "notes" / "SKILL.md").write_text("mine\n")
        return True
    with pytest.raises(new_skill.Refused, match="changed since the plan"):
        new_skill.create("notes", "repo", "Use when x", cwd=repo, approve=approve)
    assert (repo / ".claude" / "skills" / "notes" / "SKILL.md").read_text() == "mine\n"


@pytest.mark.parametrize("answer, word", [("n", "not applied"), ("y", "applied")])
def test_adopt_reports_what_really_happened(repo, monkeypatch, capsys, answer, word):
    from loadout import adopt, own
    monkeypatch.setattr(profiles, "load_profile", lambda n: profiles.Profile(name="mine", description="", settings={"a": 1}))
    monkeypatch.setattr(own, "candidate_repos", lambda item: [repo])
    answers = iter(["y", answer])
    adopt._offer_profiles({"mine": [object()]}, lambda q: next(answers))
    line = [l for l in capsys.readouterr().out.splitlines() if "profile mine" in l][-1]
    assert line.endswith(f"profile mine {word}") or (word == "applied" and line.endswith("profile mine applied"))


def test_a_relative_repo_path_is_recorded_absolute(repo, monkeypatch):
    from loadout.jsonio import load_json
    monkeypatch.setattr(profiles, "load_profile", lambda n: profiles.Profile(name="mine", description="", settings={"a": 1}))
    monkeypatch.chdir(repo.parent)
    project.add_profile(__import__("pathlib").Path(repo.name), "mine", approve=lambda plan: True)
    from loadout import paths
    manifest = sorted(paths.backups_root().glob("*/manifest.json"))[-1]
    data = load_json(manifest)
    assert data["repo"] == str(repo.resolve())
    assert all(__import__("os").path.isabs(v) for st in data["steps"] for v in (st["undo"].get("created"), ) if v)


def test_init_adding_codex_names_only_installed_plugins(repo, monkeypatch):
    targets.set_agents({"claude": True, "codex": True})
    (repo / ".loadout.json").write_text('{\n  "agents": [\n    "claude"\n  ]\n}\n')
    prof = profiles.Profile(name="thesis", description="", install=["x@claude-plugins-official"])
    monkeypatch.setattr(profiles, "load_profile", lambda n: prof)
    monkeypatch.setattr(codex_project, "plugins", lambda p, dry_run: ["plugin x@claude-plugins-official: failed: boom"])
    project.init(repo, ["thesis"], yes=True, install=True, dry_run=False, ask=lambda q: "", interactive=False,
                 agents=frozenset({"claude", "codex"}))
    cfg = repo / ".codex" / "config.toml"
    assert not cfg.exists() or "x@claude-plugins-official" not in cfg.read_text()
