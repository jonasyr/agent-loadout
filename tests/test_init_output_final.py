"""Final review fixes (spec 2026-10-29 init output): a real init problem is a ! problem in calm mode, each problem is
said once, and a repo with "manage": false says so even when the profile is already applied."""
import json
import os

import pytest

from loadout import out, profiles, project, targets

DB = profiles.Profile(name="db", description="", mcp={"mcpServers": {"dbhub": {"type": "stdio", "command": "npx"}}})


@pytest.fixture
def repo(fake_home, fake_runner, tmp_path, monkeypatch):
    p = tmp_path / "repo"
    (p / ".git").mkdir(parents=True)
    monkeypatch.setattr(out, "VERBOSE", False)
    monkeypatch.setattr(targets, "claude_enabled", lambda: True)
    monkeypatch.setattr(targets, "codex_enabled", lambda: False)
    monkeypatch.setattr(profiles, "load_profile", lambda name: DB)
    return p


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink")
def test_gitignore_outside_is_a_problem_in_calm_mode(repo, tmp_path, capsys):
    (tmp_path / "elsewhere").write_text("x\n")
    (repo / ".gitignore").symlink_to(tmp_path / "elsewhere")
    rc = project.init(repo, ["db"], yes=True, install=False, dry_run=False, ask=lambda q: "", interactive=False,
                      agents=frozenset({"claude"}))
    text = capsys.readouterr().out
    result = text[text.index("Init"):]
    assert rc == 1 and "! Init" in text and "skipped .gitignore: it points outside the repo" in result


def test_each_problem_said_once(repo, capsys):
    assert project._report("Init", type("B", (), {"empty": True})(), [], ["boom", "boom"]) == 1
    assert capsys.readouterr().out.count("boom") == 1


def test_manage_false_wins_over_already_applied(repo, capsys):
    (repo / ".loadout.json").write_text(json.dumps({"agents": ["claude"]}) + "\n")
    assert project.add_profile(repo, "db", approve=lambda plan: True) == 0
    data = json.loads((repo / ".loadout.json").read_text())
    data["manage"] = False
    (repo / ".loadout.json").write_text(json.dumps(data) + "\n")
    capsys.readouterr()
    assert project.add_profile(repo, "db", approve=lambda plan: True) == 0
    text = capsys.readouterr().out
    assert project.MANAGE_OFF in text and project.ALREADY.format(name="db") not in text
