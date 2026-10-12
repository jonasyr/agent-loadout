"""loadout init / profile also set up Codex in the repo."""
import sys

import pytest

from loadout import codex, codex_project, paths, profiles, project, runner, settings_merge, targets

needs_tomllib = pytest.mark.skipif(sys.version_info < (3, 11), reason="config edits need tomllib")

WEB = profiles.Profile(
    name="web", description="",
    mcp={"mcpServers": {"chrome-devtools": {"type": "stdio", "command": "npx", "args": ["-y", "chrome-devtools-mcp@1.10.1"]}}},
    settings={"disabledMcpjsonServers": ["chrome-devtools"]})
THESIS = profiles.Profile(name="thesis", description="", install=["deepeval@claude-plugins-official"],
                          settings={"enabledPlugins": {"deepeval@claude-plugins-official": True}})


@pytest.fixture
def repo(fake_home, tmp_path):
    p = tmp_path / "repo"
    (p / ".git").mkdir(parents=True)
    return p


@needs_tomllib
def test_profile_servers_become_project_tables(repo):
    lines = codex_project.config(WEB, repo, dry_run=False)
    text = (repo / ".codex" / "config.toml").read_text()
    assert '[mcp_servers.chrome-devtools]\ncommand = "npx"' in text
    assert "enabled = false" in text  # disabledMcpjsonServers
    assert any("chrome-devtools" in l for l in lines)


@needs_tomllib
def test_running_twice_changes_nothing_and_warns_nothing(repo):
    codex_project.config(WEB, repo, dry_run=False)
    before = (repo / ".codex" / "config.toml").read_text()
    assert codex_project.config(WEB, repo, dry_run=False) == []
    assert (repo / ".codex" / "config.toml").read_text() == before


@needs_tomllib
def test_user_text_stays_and_a_same_named_table_is_reported(repo):
    cfg = repo / ".codex" / "config.toml"
    cfg.parent.mkdir()
    user = '# mine\nnote = """\n[mcp_servers.fake]\n"""\n\n[mcp_servers.chrome-devtools]\ncommand = "other"\n'
    cfg.write_text(user)
    lines = codex_project.config(WEB, repo, dry_run=False)
    assert cfg.read_text() == user
    assert any("left as is" in l and "chrome-devtools" in l for l in lines)


@needs_tomllib
def test_plugins_are_enabled_in_the_project(repo):
    codex_project.config(THESIS, repo, dry_run=False)
    assert '[plugins."deepeval@claude-plugins-official"]\nenabled = true' in (repo / ".codex" / "config.toml").read_text()


@needs_tomllib
def test_a_server_codex_cannot_take_is_skipped_with_a_reason(repo):
    db = profiles.Profile(name="db", description="", mcp={"mcpServers": {"dbhub": {
        "command": "npx", "args": ["--dsn", "${DATABASE_URL}"]}}})
    lines = codex_project.config(db, repo, dry_run=False)
    assert any(l.startswith("skipped mcp dbhub") for l in lines)
    assert not (repo / ".codex" / "config.toml").exists()


def test_dry_run_writes_nothing(repo):
    lines = codex_project.config(WEB, repo, dry_run=True)
    assert not (repo / ".codex").exists()
    assert lines and all(l.startswith(("would", "skipped")) for l in lines)


def test_without_tomllib_one_line(repo, monkeypatch):
    monkeypatch.setattr(codex, "_tomllib", lambda: None)
    assert codex_project.config(WEB, repo, dry_run=False) == [
        f"skipped {repo / '.codex' / 'config.toml'}: editing it safely needs Python 3.11 or newer"]


def test_symlinked_codex_folder_outside_the_repo_is_refused(repo, tmp_path):
    (tmp_path / "elsewhere").mkdir()
    (repo / ".codex").symlink_to(tmp_path / "elsewhere")
    lines = codex_project.config(WEB, repo, dry_run=False)
    assert any("points outside" in l for l in lines)
    assert not (tmp_path / "elsewhere" / "config.toml").exists()


def test_repo_skills_are_linked_for_codex(repo):
    (repo / ".claude" / "skills" / "pw").mkdir(parents=True)
    (repo / ".agents" / "skills" / "mine").mkdir(parents=True)
    lines = codex_project.skills(repo, dry_run=False)
    link = repo / ".agents" / "skills" / "pw"
    assert link.is_symlink() and str(link.readlink()) == "../../.claude/skills/pw"
    assert (repo / ".agents" / "skills" / "mine").is_dir()  # never replaced
    assert codex_project.skills(repo, dry_run=False) == []  # second run: nothing to do
    assert lines == ["linked skill pw for Codex -> .agents/skills/pw"]


def test_profile_plugin_is_installed_and_recorded_project_only(repo, fake_runner, monkeypatch):
    import json
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: {"enabledPlugins": {}})
    monkeypatch.setattr(codex, "apply_config", lambda bk, dry_run=False: [])
    fake_runner.responses[("codex", "plugin", "list")] = runner.Result(0, json.dumps({"installed": []}), "")
    fake_runner.responses[("codex", "plugin", "marketplace", "add", codex.OFFICIAL)] = runner.Result(
        0, json.dumps({"marketplaceName": "claude-plugins-official", "alreadyAdded": True}), "")
    codex_project.plugins(THESIS, dry_run=False)
    assert ["codex", "plugin", "add", "deepeval@claude-plugins-official", "--json"] in fake_runner.calls
    assert codex.project_plugins() == ["deepeval@claude-plugins-official"]


def test_a_plugin_already_on_everywhere_is_not_made_project_only(repo, fake_runner, monkeypatch):
    import json
    monkeypatch.setattr(settings_merge, "desired_settings",
                        lambda: {"enabledPlugins": {"deepeval@claude-plugins-official": True}})
    monkeypatch.setattr(codex, "apply_config", lambda bk, dry_run=False: [])
    fake_runner.responses[("codex", "plugin", "list")] = runner.Result(
        0, json.dumps({"installed": [{"pluginId": "deepeval@claude-plugins-official"}]}), "")
    fake_runner.responses[("codex", "plugin", "marketplace", "add", codex.OFFICIAL)] = runner.Result(
        0, json.dumps({"marketplaceName": "claude-plugins-official", "alreadyAdded": True}), "")
    codex_project.plugins(THESIS, dry_run=False)
    assert codex.project_plugins() == []


def test_add_profile_runs_codex_only_when_codex_is_on(repo, fake_runner, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(codex_project, "apply", lambda prof, p, install, dry_run: calls.append(prof.name) or [])
    monkeypatch.setattr(profiles, "load_profile", lambda name: WEB)
    monkeypatch.setattr(targets, "codex_enabled", lambda: False)
    project.add_profile(repo, "web", install=False)
    assert calls == []
    monkeypatch.setattr(targets, "codex_enabled", lambda: True)
    project.add_profile(repo, "web", install=False)
    assert calls == ["web"]


def test_trust_note_unless_the_project_is_trusted(repo, monkeypatch):
    monkeypatch.setattr(codex_project, "config", lambda prof, p, dry_run: ["x"])
    monkeypatch.setattr(codex_project, "skills", lambda p, dry_run: [])
    assert codex_project.TRUST_NOTE in codex_project.apply(WEB, repo, install=False, dry_run=False)
    cfg = paths.codex_home() / "config.toml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(f'[projects."{repo.resolve()}"]\ntrust_level = "trusted"\n')
    if codex._tomllib() is not None:
        assert codex_project.TRUST_NOTE not in codex_project.apply(WEB, repo, install=False, dry_run=False)
