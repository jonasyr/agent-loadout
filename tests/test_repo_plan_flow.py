"""init and profile: plan, yes, write, undo (spec Parts 0, 1)."""
from pathlib import Path

import pytest

from loadout import backup, profiles, project, targets


@pytest.fixture
def repo(fake_home, fake_runner, tmp_path, monkeypatch):
    p = tmp_path / "repo"
    (p / ".git").mkdir(parents=True)
    monkeypatch.setattr(profiles, "load_profile", lambda name: profiles.Profile(
        name=name, description="Web UI", settings={"disabledMcpjsonServers": ["cd"]}, install=["pw@market"]))
    targets.set_agents({"claude": True, "codex": False})
    return p


def _files(p):
    return sorted(x.relative_to(p).as_posix() for x in p.rglob("*") if ".git" not in x.parts)


def test_a_declined_plan_writes_and_runs_nothing(repo, fake_runner, capsys):
    rc = project.add_profile(repo, "web", approve=lambda plan: False)
    assert rc == 0 and _files(repo) == [] and fake_runner.calls == []
    out = capsys.readouterr().out
    assert "change" in out or "create" in out
    assert "nothing changed" in out


def test_no_terminal_without_yes_writes_nothing(repo, fake_runner, capsys):
    rc = project.add_profile(repo, "web", approve=project.approver(False, lambda q: "", interactive=False))
    assert rc == 0 and _files(repo) == [] and fake_runner.calls == []
    assert project.NO_TERMINAL in capsys.readouterr().out


def test_eof_from_a_closed_stdin_is_a_no(repo, fake_runner):
    approve = project.approver(False, lambda q: "", interactive=True)
    assert project.add_profile(repo, "web", approve=approve) == 0 and _files(repo) == []


def test_yes_applies_the_plan_and_restore_undoes_it(repo, fake_runner, capsys):
    rc = project.add_profile(repo, "web", approve=project.approver(True, lambda q: "", interactive=False))
    assert rc == 0 and ".claude/settings.json" in _files(repo) and ".loadout.json" in _files(repo)
    out = capsys.readouterr().out
    line = next(l for l in out.splitlines() if "undo: loadout restore " in l)
    lines, ok, _ = backup.restore(Path(line.split("undo: loadout restore ", 1)[1].strip()))
    assert ok, lines
    assert _files(repo) == []


def test_the_plan_shown_is_what_is_written(repo, fake_runner, capsys):
    project.add_profile(repo, "web", dry_run=True)
    planned = capsys.readouterr().out
    project.add_profile(repo, "web", approve=lambda plan: True)
    for rel in _files(repo):
        if "/" not in rel or rel.startswith(".claude/"):
            assert rel.split("/")[0] in planned


def test_dry_run_shows_the_settings_diff_and_changes_nothing(repo, fake_runner, capsys):
    assert project.add_profile(repo, "web", dry_run=True) == 0
    out = capsys.readouterr().out
    assert '+ disabledMcpjsonServers: ["cd"]' in out and _files(repo) == [] and fake_runner.calls == []


def test_manage_false_writes_nothing_and_says_so(repo, fake_runner, capsys):
    (repo / ".loadout.json").write_text('{"manage": false}')
    assert project.add_profile(repo, "web", approve=lambda plan: True) == 0
    assert project.MANAGE_OFF in capsys.readouterr().out
    assert _files(repo) == [".loadout.json"] and fake_runner.calls == []


def test_an_invalid_loadout_json_stops_before_any_change(repo, fake_runner, capsys):
    (repo / ".loadout.json").write_text('{"agents": "codex"}')
    assert project.add_profile(repo, "web", approve=lambda plan: True) == 1
    assert ".loadout.json: agents" in capsys.readouterr().out and _files(repo) == [".loadout.json"]


def test_a_codex_only_user_in_a_both_agents_repo(repo, fake_runner, capsys):
    targets.set_agents({"claude": False, "codex": True})
    (repo / ".loadout.json").write_text('{\n  "agents": [\n    "claude",\n    "codex"\n  ]\n}\n')
    project.add_profile(repo, "web", install=True, approve=lambda plan: True)
    assert (repo / ".claude" / "settings.json").is_file()
    assert not [c for c in fake_runner.calls if c[:2] == ["claude", "plugin"]]
    assert "plugin pw@market: not installed for Claude Code, which is off for you" in capsys.readouterr().out


def test_init_agents_flag_writes_the_choice(repo, fake_runner):
    rc = project.init(repo, [], yes=True, install=False, dry_run=False, ask=lambda q: "", interactive=False,
                      agents=frozenset({"codex"}))
    assert rc == 0
    assert (repo / ".loadout.json").read_text() == '{\n  "agents": [\n    "codex"\n  ]\n}\n'
    assert not (repo / "CLAUDE.md").exists() and (repo / "AGENTS.md").exists()


def test_init_asks_which_agents_in_a_terminal(repo, fake_runner):
    targets.set_agents({"claude": True, "codex": True})
    answers = iter(["2", "-", "y"])  # Codex only; no profiles; apply
    project.init(repo, [], yes=False, install=False, dry_run=False, ask=lambda q: next(answers), interactive=True)
    assert '"codex"' in (repo / ".loadout.json").read_text() and '"claude"' not in (repo / ".loadout.json").read_text()


def test_changing_agents_removes_nothing_and_lists_what_is_left(repo, fake_runner, capsys):
    project.init(repo, [], yes=True, install=False, dry_run=False, ask=lambda q: "", interactive=False,
                 agents=frozenset({"claude", "codex"}))
    capsys.readouterr()
    project.init(repo, [], yes=True, install=False, dry_run=False, ask=lambda q: "", interactive=False,
                 agents=frozenset({"codex"}))
    assert (repo / "CLAUDE.md").exists()
    assert "no longer needed for this repo's agents (yours to remove): CLAUDE.md" in capsys.readouterr().out
