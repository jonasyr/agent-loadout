"""init and profile end with a status line and numbered to-dos, each said once; the skills a profile command adds
are linked for the repo's other agent without a second question (spec 2026-10-29 init output, G2 and G3)."""
import pytest

from loadout import codex_project, out, profiles, project, runner, targets

WEB = profiles.Profile(name="web", description="Web UI work", notes="enable chrome-devtools in /mcp when needed.",
                       mcp={"mcpServers": {"chrome-devtools": {"type": "stdio", "command": "npx", "args": ["-y", "c"]}}},
                       settings={"disabledMcpjsonServers": ["chrome-devtools"]},
                       commands=[["playwright-cli", "install", "--skills"]])
DB = profiles.Profile(name="db", description="", notes="Set DATABASE_URL in your shell or secrets.env.",
                      mcp={"mcpServers": {"dbhub": {"type": "stdio", "command": "npx",
                                                    "args": ["--dsn", "${DATABASE_URL}"]}}})


@pytest.fixture
def repo(fake_home, tmp_path, monkeypatch):
    p = tmp_path / "repo"
    (p / ".git").mkdir(parents=True)
    monkeypatch.setattr(targets, "codex_enabled", lambda: True)
    monkeypatch.setattr(targets, "claude_enabled", lambda: True)
    monkeypatch.setattr(profiles, "load_profile", lambda name: {"web": WEB, "db": DB}[name])
    monkeypatch.setattr(out, "VERBOSE", False)
    return p


def _init(repo, ask=lambda q: "y"):
    return project.init(repo, ["web", "db"], yes=False, install=True, dry_run=False, ask=ask, interactive=True,
                        agents=frozenset({"claude", "codex"}))


def _todos(text):
    after = text[text.index(project.STILL_TO_DO):].splitlines()[1:]
    return [l for l in after if l.lstrip()[:1].isdigit()]


def test_init_result_lists_todos_once(repo, fake_runner, capsys):
    _init(repo)
    text = capsys.readouterr().out
    todos = _todos(text)
    assert sum("codex" in t and "trust" in t for t in todos) == 1
    assert sum("DATABASE_URL" in t for t in todos) == 1
    assert "/loadout:onboard" in todos[-1]
    assert text.count(codex_project.TRUST_NOTE) <= 1 and text.count("start `codex` here once") == 1


def test_record_later_note_hidden_in_calm(repo, fake_runner, capsys, monkeypatch):
    _init(repo)
    assert "the record of profile web's .codex/config.toml" not in capsys.readouterr().out
    (repo / ".loadout.json").unlink()
    monkeypatch.setattr(out, "VERBOSE", True)
    import shutil
    for p in repo.iterdir():
        if p.name != ".git":
            shutil.rmtree(p) if p.is_dir() and not p.is_symlink() else p.unlink()
    _init(repo)
    assert "the record of profile web's .codex/config.toml" in capsys.readouterr().out


def test_skill_links_no_second_question(repo, fake_runner, monkeypatch, capsys):
    def run(cmd, cwd=None, **k):
        if cmd[:1] == ["playwright-cli"]:
            skill = repo / ".claude" / "skills" / "x"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("---\nname: x\ndescription: x\n---\n")
        return fake_runner(cmd, cwd=cwd, **k)
    monkeypatch.setattr(runner, "run", run)
    asked = []
    _init(repo, ask=lambda q: asked.append(q) or "y")
    assert len([q for q in asked if q == project.QUESTION]) == 1
    assert (repo / ".agents" / "skills" / "x").is_symlink()


def test_codex_backup_line_kept(repo, fake_runner, monkeypatch, capsys):
    monkeypatch.setattr(codex_project, "plugins", lambda prof, dry_run: ["backup: loadout restore /x/codex-1"])
    _init(repo)
    assert "backup: loadout restore /x/codex-1" in capsys.readouterr().out


def test_plan_names_the_links_and_the_result_lists_them(repo, fake_runner, monkeypatch, capsys):
    # Codex review on #74: the approved plan must say that skills the commands add get linked; the result names them
    def run(cmd, cwd=None, **k):
        if cmd[:1] == ["playwright-cli"]:
            skill = repo / ".claude" / "skills" / "x"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("---\nname: x\ndescription: x\n---\n")
        return fake_runner(cmd, cwd=cwd, **k)
    monkeypatch.setattr(runner, "run", run)
    _init(repo)
    text = capsys.readouterr().out
    plan, result = text[:text.index("Init ")], text[text.index("Init "):]
    assert "  link    skills these commands add, for Codex (.agents/skills)" in plan
    assert "linked skill x for Codex" in result
