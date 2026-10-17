"""Findings of the final review of repo-agents PR 2."""
import json

import pytest

from loadout import __main__ as cli, codex_project, explain, out, profiles, project, targets

ESC = "\x1b]0;owned\x07\x1b[2J\x9b2J"
SECRETS = ("rootpass99", "hunter22pass", "otherpass77", "newpass88")


@pytest.fixture
def repo(fake_home, fake_runner, tmp_path):
    p = tmp_path / "repo"
    (p / ".git").mkdir(parents=True)
    targets.set_agents({"claude": True, "codex": False})
    return p


def use(monkeypatch, settings=None, mcp=None, install=()):
    monkeypatch.setattr(profiles, "load_profile", lambda n: profiles.Profile(
        name=n, description="d", settings=settings or {}, mcp=mcp or {}, install=list(install)))


def run(repo, **kw):
    return project.add_profile(repo, "web", install=False, approve=lambda plan: True, **kw)


def test_short_and_flag_secrets_never_reach_the_record_explain_or_notes(repo, monkeypatch, capsys):
    use(monkeypatch, {"env": {"PGPASSWORD": "rootpass99"}},
        {"mcpServers": {"db": {"command": "db-mcp", "args": ["--password", "hunter22pass"]}}})
    run(repo)
    path = repo / ".claude" / "settings.json"
    path.write_text(json.dumps({"env": {"PGPASSWORD": "otherpass77"}}, indent=2) + "\n")
    use(monkeypatch, {"env": {"PGPASSWORD": "newpass88"}},
        {"mcpServers": {"db": {"command": "db-mcp", "args": ["--password", "hunter22pass"]}}})
    asked = []
    run(repo, decide=lambda lines: asked.extend(lines) or False)
    explain.explain(".claude/settings.json", cwd=repo)
    explain.explain(".mcp.json", cwd=repo)
    shown = capsys.readouterr().out + "\n".join(asked) + (repo / ".loadout.json").read_text()
    assert asked and not [s for s in SECRETS if s in shown]


def test_explain_reports_an_invalid_loadout_json(repo, capsys):
    (repo / ".loadout.json").write_text('{\n  "profiles": []\n}\n')
    assert explain.explain(".claude/settings.json", cwd=repo) == 1
    assert "profiles must map" in capsys.readouterr().out


@pytest.mark.parametrize("verbose", [False, True])
def test_the_library_path_never_prints_terminal_escapes(repo, monkeypatch, capsys, verbose):
    monkeypatch.setattr(out, "VERBOSE", verbose)
    path = repo / ".claude" / "settings.json"
    path.parent.mkdir()
    path.write_text(json.dumps({ESC: 1, "env": {"A": ESC}}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (repo / ".loadout.json").write_text(json.dumps(
        {"agents": ["claude"], "profiles": {"web": {".claude/settings.json": {ESC: 2}}}}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    use(monkeypatch, {"env": {"A": "1"}})
    project.add_profile(repo, "web", install=False)
    printed = capsys.readouterr().out
    assert "\x1b" not in printed and "\x07" not in printed and "\x9b" not in printed


def test_a_one_line_loadout_json_gets_its_record_in_its_layout(repo, monkeypatch):
    (repo / ".loadout.json").write_text('{"agents": ["claude"]}')
    use(monkeypatch, {"env": {"A": "1"}})
    run(repo)
    text = (repo / ".loadout.json").read_text()
    assert "\n" not in text and json.loads(text)["profiles"]["web"] == {".claude/settings.json": {"env/A": "1"}}


def test_the_held_codex_plan_says_when_the_record_cannot_be_written(fake_home, fake_runner, tmp_path, monkeypatch, capsys):
    p = tmp_path / "crepo"
    (p / ".git").mkdir(parents=True)
    (p / ".loadout.json").write_text('{"agents":["codex"]}')  # a layout loadout cannot reproduce
    targets.set_agents({"claude": False, "codex": True})
    use(monkeypatch, mcp={"mcpServers": {"cd": {"command": "npx", "args": ["-y", "cd@1"]}}}, install=["pw@claude-plugins-official"])
    monkeypatch.setattr(codex_project, "plugins", lambda prof, dry_run: [])
    project.add_profile(p, "web", install=True, approve=lambda plan: True)
    printed = capsys.readouterr().out
    assert "written after the Codex plugin installs" not in printed
    assert "is not written" in printed
    assert (p / ".loadout.json").read_text() == '{"agents":["codex"]}'


def test_profile_yes_in_a_terminal_does_not_ask_the_take_question(repo, monkeypatch):
    use(monkeypatch, {"env": {"A": "1"}})
    run(repo)
    (repo / ".claude" / "settings.json").write_text(json.dumps({"env": {"A": "9"}}, indent=2) + "\n")
    use(monkeypatch, {"env": {"A": "2"}})
    monkeypatch.chdir(repo)
    monkeypatch.setattr(cli, "_ask", lambda q: pytest.fail(f"asked: {q}"))
    monkeypatch.setattr("loadout.ui.is_interactive", lambda: True)
    assert cli.main(["profile", "web", "--yes", "--no-install"]) == 0
    assert json.loads((repo / ".claude" / "settings.json").read_text())["env"]["A"] == "9"
