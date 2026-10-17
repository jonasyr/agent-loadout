"""Findings of the per-task reviews of repo-agents PR 2."""
import json

import pytest

from loadout import codex_project, profiles, project, repo_config, targets

PW = "plugins/pw@claude-plugins-official/enabled"
CODEX = profiles.Profile(name="web", description="", mcp={"mcpServers": {"cd": {"command": "npx", "args": ["-y", "cd@1"]}}},
                         install=["pw@claude-plugins-official"])


@pytest.fixture
def repo(fake_home, fake_runner, tmp_path):
    p = tmp_path / "repo"
    (p / ".git").mkdir(parents=True)
    targets.set_agents({"claude": True, "codex": False})
    return p


def use(monkeypatch, settings):
    monkeypatch.setattr(profiles, "load_profile", lambda n: profiles.Profile(name=n, description="d", settings=settings))


def run(repo, **kw):
    return project.add_profile(repo, "web", install=False, approve=lambda plan: True, **kw)


def settings(repo):
    return json.loads((repo / ".claude" / "settings.json").read_text())


def test_take_profile_works_after_an_offer_was_declined(repo, monkeypatch):
    use(monkeypatch, {"env": {"A": "1"}})
    run(repo)
    (repo / ".claude" / "settings.json").write_text(json.dumps({"env": {"A": "9"}}, indent=2) + "\n")
    use(monkeypatch, {"env": {"A": "2"}})
    run(repo, decide=project.chooser(False, lambda q: "", False))  # no terminal: kept, offered
    assert settings(repo)["env"]["A"] == "9"
    run(repo, decide=project.chooser(True, lambda q: "", False))
    assert settings(repo)["env"]["A"] == "2"


def test_a_declined_offer_still_is_not_asked_again_in_a_terminal(repo, monkeypatch):
    use(monkeypatch, {"env": {"A": "1"}})
    run(repo)
    (repo / ".claude" / "settings.json").write_text(json.dumps({"env": {"A": "9"}}, indent=2) + "\n")
    use(monkeypatch, {"env": {"A": "2"}})
    asked = []
    run(repo, decide=project.chooser(False, lambda q: asked.append(q) or "n", True))
    run(repo, decide=project.chooser(False, lambda q: asked.append(q) or "n", True))
    assert len(asked) == 1 and settings(repo)["env"]["A"] == "9"


def test_true_replacing_one_is_written(repo, monkeypatch):
    use(monkeypatch, {"a": 1})
    run(repo)
    use(monkeypatch, {"a": True})
    run(repo)
    assert settings(repo)["a"] is True
    rec = json.loads((repo / ".loadout.json").read_text())["profiles"]["web"][".claude/settings.json"]
    assert rec["a"] is True


def test_a_record_of_true_replacing_one_is_a_change(repo):
    old = json.dumps({"agents": ["claude"], "profiles": {"web": {".mcp.json": {"a": 1}}}}, indent=2) + "\n"
    assert repo_config.record_text(repo, old, "web", {".mcp.json": {"a": True}}) is not None


@pytest.fixture
def codex_repo(fake_home, fake_runner, tmp_path):
    p = tmp_path / "crepo"
    (p / ".git").mkdir(parents=True)
    (p / ".loadout.json").write_text('{\n  "agents": [\n    "codex"\n  ]\n}\n')
    targets.set_agents({"claude": False, "codex": True})
    return p


def crec(repo):
    return json.loads((repo / ".loadout.json").read_text()).get("profiles", {}).get("web", {}).get(".codex/config.toml", {})


def test_a_failed_install_keeps_a_removed_plugin_removed(codex_repo):
    codex_project.config(CODEX, codex_repo, False)
    cfg = codex_repo / ".codex" / "config.toml"
    cfg.write_text(cfg.read_text().split("[plugins.")[0])  # a person removes the plugin
    codex_project.config(CODEX, codex_repo, False, skip=frozenset({"pw@claude-plugins-official"}))
    assert PW in crec(codex_repo)
    lines = codex_project.config(CODEX, codex_repo, False)
    assert "plugins." not in cfg.read_text() and any("kept removed" in l for l in lines)


def test_a_person_edited_codex_table_is_a_note_not_a_problem(codex_repo):
    codex_project.config(CODEX, codex_repo, False)
    cfg = codex_repo / ".codex" / "config.toml"
    cfg.write_text(cfg.read_text().replace("cd@1", "cd@9"))
    lines = codex_project.config(CODEX, codex_repo, False)
    assert "cd@9" in cfg.read_text()
    assert not any(b in l for l in lines for b in project.CODEX_BAD)
    assert any("changed in this repo" in l for l in lines)
