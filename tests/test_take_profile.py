"""The question about a teammate's changes, and --take-profile (spec Part 2)."""
import json

import pytest

from loadout import __main__ as cli, profiles, project, targets

LINES = ["This repo differs from profile web in 1 entry:", '  .claude/settings.json  env/A: the repo has "9", the profile has "2"']


def test_take_profile_takes_without_asking(capsys):
    assert project.chooser(True, lambda q: pytest.fail("asked"), True)(LINES) is True
    assert LINES[0] in capsys.readouterr().out


def test_without_a_terminal_the_repo_values_stay_and_the_flag_is_named(capsys):
    assert project.chooser(False, lambda q: pytest.fail("asked"), False)(LINES) is False
    assert "--take-profile" in capsys.readouterr().out


def test_a_dry_run_does_not_ask():
    assert project.chooser(False, lambda q: pytest.fail("asked"), True, dry_run=True)(LINES) is False


def test_in_a_terminal_it_asks_once():
    asked = []
    assert project.chooser(False, lambda q: asked.append(q) or "y", True)(LINES) is True
    assert asked == [project.TAKE_QUESTION]


@pytest.fixture
def shared(fake_home, fake_runner, tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    targets.set_agents({"claude": True, "codex": False})
    value = {"A": "1"}
    monkeypatch.setattr(profiles, "load_profile", lambda n: profiles.Profile(name=n, description="d", settings={"env": dict(value)}))
    project.add_profile(repo, "web", install=False, approve=lambda plan: True)
    path = repo / ".claude" / "settings.json"
    path.write_text(json.dumps({"env": {"A": "9"}}, indent=2) + "\n")
    value["A"] = "2"
    monkeypatch.chdir(repo)
    return path


def test_the_cli_flag_takes_the_profile_values(shared):
    assert cli.main(["profile", "web", "--yes", "--take-profile", "--no-install"]) == 0
    assert json.loads(shared.read_text())["env"]["A"] == "2"


def test_yes_alone_keeps_the_repo_values(shared):
    assert cli.main(["profile", "web", "--yes", "--no-install"]) == 0
    assert json.loads(shared.read_text())["env"]["A"] == "9"


def test_the_question_comes_before_the_plan(shared, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_ask", lambda q: "y")
    monkeypatch.setattr("loadout.ui.is_interactive", lambda: True)
    cli.main(["profile", "web", "--no-install"])
    out = capsys.readouterr().out
    assert out.index("This repo differs") < out.index("Plan for")
    assert json.loads(shared.read_text())["env"]["A"] == "2"
