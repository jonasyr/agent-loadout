"""loadout init / profile also set up Codex in the repo."""
import os
import sys
from pathlib import Path

import pytest

from loadout import codex, codex_project, paths, profiles, project, runner, settings_merge, targets


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


def test_profile_servers_become_project_tables(repo):
    lines = codex_project.config(WEB, repo, dry_run=False)
    text = (repo / ".codex" / "config.toml").read_text()
    assert '[mcp_servers.chrome-devtools]\ncommand = "npx"' in text
    assert "enabled = false" in text  # disabledMcpjsonServers
    assert any("chrome-devtools" in l for l in lines)


def test_running_twice_changes_nothing_and_warns_nothing(repo):
    codex_project.config(WEB, repo, dry_run=False)
    before = (repo / ".codex" / "config.toml").read_text()
    assert codex_project.config(WEB, repo, dry_run=False) == []
    assert (repo / ".codex" / "config.toml").read_text() == before


def test_user_text_stays_and_a_same_named_table_is_reported(repo):
    cfg = repo / ".codex" / "config.toml"
    cfg.parent.mkdir()
    user = '# mine\nnote = """\n[mcp_servers.fake]\n"""\n\n[mcp_servers.chrome-devtools]\ncommand = "other"\n'
    cfg.write_text(user)
    lines = codex_project.config(WEB, repo, dry_run=False)
    assert cfg.read_text() == user
    assert any("left as is" in l and "chrome-devtools" in l for l in lines)


def test_plugins_are_enabled_in_the_project(repo):
    codex_project.config(THESIS, repo, dry_run=False)
    assert '[plugins."deepeval@claude-plugins-official"]\nenabled = true' in (repo / ".codex" / "config.toml").read_text()


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


def test_symlinked_codex_folder_outside_the_repo_is_refused(repo, tmp_path):
    (tmp_path / "elsewhere").mkdir()
    (repo / ".codex").symlink_to(tmp_path / "elsewhere")
    lines = codex_project.config(WEB, repo, dry_run=False)
    assert any("points outside" in l for l in lines)
    assert not (tmp_path / "elsewhere" / "config.toml").exists()


def test_repo_skills_are_linked_for_codex(repo):
    targets.set_agents({"claude": False, "codex": True})
    (repo / ".claude" / "skills" / "pw").mkdir(parents=True)
    (repo / ".agents" / "skills" / "mine").mkdir(parents=True)
    lines = profiles.link_skills(repo, dry_run=False)
    link = repo / ".agents" / "skills" / "pw"
    assert link.is_symlink() and Path(os.readlink(link)) == Path("../../.claude/skills/pw")
    assert (repo / ".agents" / "skills" / "mine").is_dir()  # never replaced
    assert profiles.link_skills(repo, dry_run=False) == []  # second run: nothing to do
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
    monkeypatch.setattr(codex_project, "apply", lambda prof, p, install, dry_run, **k: calls.append(prof.name) or [])
    monkeypatch.setattr(profiles, "load_profile", lambda name: WEB)
    monkeypatch.setattr(targets, "codex_enabled", lambda: False)
    project.add_profile(repo, "web", install=False)
    assert calls == []
    (repo / ".loadout.json").unlink()  # the first run fixed the repo's agents to yours then (ADR 0030); start over
    monkeypatch.setattr(targets, "codex_enabled", lambda: True)
    project.add_profile(repo, "web", install=False)
    assert calls == ["web"]


def test_trust_note_unless_the_project_is_trusted(repo, monkeypatch):
    monkeypatch.setattr(codex_project, "config", lambda prof, p, dry_run, skip=frozenset(), **k: ["x"])
    assert codex_project.TRUST_NOTE in codex_project.apply(WEB, repo, install=False, dry_run=False)
    cfg = paths.codex_home() / "config.toml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(f'[projects.{codex.toml_value(str(repo.resolve()))}]\ntrust_level = "trusted"\n')  # Windows paths need escaping
    assert codex_project.TRUST_NOTE not in codex_project.apply(WEB, repo, install=False, dry_run=False)


def test_a_symlinked_config_file_outside_the_repo_is_refused(repo, tmp_path):
    outside = tmp_path / "outside.toml"
    outside.write_text("")
    (repo / ".codex").mkdir()
    (repo / ".codex" / "config.toml").symlink_to(outside)
    lines = codex_project.config(WEB, repo, dry_run=False)
    assert any("points outside" in l for l in lines)
    assert outside.read_text() == ""


def test_a_symlinked_skills_folder_outside_the_repo_is_refused(repo, tmp_path):
    targets.set_agents({"claude": False, "codex": True})
    (repo / ".claude" / "skills" / "pw").mkdir(parents=True)
    (tmp_path / "elsewhere").mkdir()
    (repo / ".agents").mkdir()
    (repo / ".agents" / "skills").symlink_to(tmp_path / "elsewhere")
    lines = profiles.link_skills(repo, dry_run=False)
    assert any("points outside" in l for l in lines)
    assert list((tmp_path / "elsewhere").iterdir()) == []


def test_a_plugin_the_user_installed_in_codex_is_not_switched_off(repo, fake_runner, monkeypatch):
    import json
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: {"enabledPlugins": {}})
    monkeypatch.setattr(codex, "apply_config", lambda bk, dry_run=False: [])
    fake_runner.responses[("codex", "plugin", "list")] = runner.Result(
        0, json.dumps({"installed": [{"pluginId": "deepeval@claude-plugins-official"}]}), "")
    fake_runner.responses[("codex", "plugin", "marketplace", "add", codex.OFFICIAL)] = runner.Result(
        0, json.dumps({"marketplaceName": "claude-plugins-official", "alreadyAdded": True}), "")
    lines = codex_project.plugins(THESIS, dry_run=False)
    assert codex.project_plugins() == []
    assert any("already installed in Codex" in l for l in lines)


def test_recording_a_project_plugin_is_undoable(repo, fake_runner, monkeypatch):
    import json
    from loadout import backup
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: {"enabledPlugins": {}})
    seen = []
    monkeypatch.setattr(codex, "apply_config", lambda bk, dry_run=False: seen.append(bk) or [])
    fake_runner.responses[("codex", "plugin", "list")] = runner.Result(0, json.dumps({"installed": []}), "")
    fake_runner.responses[("codex", "plugin", "marketplace", "add", codex.OFFICIAL)] = runner.Result(
        0, json.dumps({"marketplaceName": "claude-plugins-official", "alreadyAdded": True}), "")
    codex_project.plugins(THESIS, dry_run=False)
    labels = [s["label"] for s in seen[0].steps]
    assert any("codex-config.json" in l for l in labels)


def test_codex_only_machine_never_runs_claude_plugin_install(repo, fake_runner, monkeypatch):
    monkeypatch.setattr(profiles, "load_profile", lambda name: THESIS)
    monkeypatch.setattr(targets, "claude_enabled", lambda: False)
    monkeypatch.setattr(targets, "codex_enabled", lambda: True)
    monkeypatch.setattr(codex_project, "apply", lambda prof, p, install, dry_run, **k: [])
    project.add_profile(repo, "thesis", install=True)
    assert not any(c[:2] == ["claude", "plugin"] for c in fake_runner.calls)


def test_a_failed_plugin_list_makes_nothing_project_only(repo, fake_runner, monkeypatch):
    import json
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: {"enabledPlugins": {}})
    monkeypatch.setattr(codex, "apply_config", lambda bk, dry_run=False: [])
    fake_runner.responses[("codex", "plugin", "list")] = runner.Result(1, "", "boom")
    fake_runner.responses[("codex", "plugin", "marketplace", "add", codex.OFFICIAL)] = runner.Result(
        0, json.dumps({"marketplaceName": "claude-plugins-official", "alreadyAdded": True}), "")
    codex_project.plugins(THESIS, dry_run=False)
    assert codex.project_plugins() == []


def test_trust_note_repeats_on_a_second_run_while_untrusted(repo, monkeypatch):
    monkeypatch.setattr(codex_project, "config", lambda prof, p, dry_run, skip=frozenset(), **k: [])
    assert codex_project.TRUST_NOTE in codex_project.apply(WEB, repo, install=False, dry_run=False)
    empty = profiles.Profile(name="empty", description="")
    assert codex_project.TRUST_NOTE not in codex_project.apply(empty, repo, install=False, dry_run=False)


def _official(fake_runner, listed):
    import json
    fake_runner.responses[("codex", "plugin", "list")] = (
        runner.Result(1, "", "boom") if listed is None else runner.Result(0, json.dumps({"installed": listed}), ""))
    fake_runner.responses[("codex", "plugin", "marketplace", "add", codex.OFFICIAL)] = runner.Result(
        0, json.dumps({"marketplaceName": "claude-plugins-official", "alreadyAdded": True}), "")


def test_nothing_is_installed_when_the_plugin_list_fails(repo, fake_runner, monkeypatch):
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: {"enabledPlugins": {}})
    monkeypatch.setattr(codex, "apply_config", lambda bk, dry_run=False: [])
    _official(fake_runner, None)
    lines = codex_project.plugins(THESIS, dry_run=False)
    assert not any(c[:3] == ["codex", "plugin", "add"] for c in fake_runner.calls)
    assert any("not installed" in l and "could not list" in l for l in lines)


def test_config_toml_is_saved_before_a_project_switch_is_written(repo, fake_runner, monkeypatch):
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: {"enabledPlugins": {}})
    seen = []
    monkeypatch.setattr(codex, "apply_config", lambda bk, dry_run=False: seen.append(bk) or [])
    cfg = paths.codex_home() / "config.toml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text('model = "x"\n')
    _official(fake_runner, [])
    codex_project.plugins(THESIS, dry_run=False)
    assert any("config.toml" in s["label"] for s in seen[0].steps)


def test_a_failed_install_leaves_the_repo_switch_out_and_exits_1(repo, fake_runner, monkeypatch, capsys):
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: {"enabledPlugins": {}})
    monkeypatch.setattr(codex, "apply_config", lambda bk, dry_run=False: [])
    monkeypatch.setattr(profiles, "load_profile", lambda name: THESIS)
    monkeypatch.setattr(targets, "claude_enabled", lambda: False)
    monkeypatch.setattr(targets, "codex_enabled", lambda: True)
    _official(fake_runner, [])
    fake_runner.responses[("codex", "plugin", "add")] = runner.Result(1, "", "network down")
    assert project.add_profile(repo, "thesis", install=True) == 1
    cfg = repo / ".codex" / "config.toml"
    assert not cfg.exists() or "deepeval" not in cfg.read_text()


@pytest.mark.parametrize("text", ["mcp_servers = 1\n", "plugins = 1\n"])
def test_odd_containers_in_the_repo_config_are_reported(repo, text):
    cfg = repo / ".codex" / "config.toml"
    cfg.parent.mkdir()
    cfg.write_text(text)
    lines = codex_project.config(THESIS if "plugins" in text else WEB, repo, dry_run=False)
    assert any(l.startswith("skipped") for l in lines)
    assert cfg.read_text() == text


def test_odd_projects_value_counts_as_untrusted(repo):
    cfg = paths.codex_home() / "config.toml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text("projects = 1\n")
    assert codex_project._trusted(repo) is False


def test_a_failed_marketplace_counts_for_its_plugins(repo):
    lines = [f"marketplace {codex.OFFICIAL}: failed: boom",
             "plugin deepeval@claude-plugins-official: not installed (its marketplace failed)"]
    assert codex_project.failed_plugins(THESIS, lines) == {"deepeval@claude-plugins-official"}


def test_a_failed_marketplace_skips_only_its_own_plugins(repo, fake_runner, monkeypatch):
    import json
    two = profiles.Profile(name="two", description="", install=["x@claude-plugins-official", "x@other"])
    markets = {"other": {"source": {"source": "github", "repo": "o/other"}}}
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: {"enabledPlugins": {}, "extraKnownMarketplaces": markets})
    monkeypatch.setattr(codex, "apply_config", lambda bk, dry_run=False: [])
    fake_runner.responses[("codex", "plugin", "list")] = runner.Result(0, json.dumps({"installed": []}), "")
    fake_runner.responses[("codex", "plugin", "marketplace", "add", codex.OFFICIAL)] = runner.Result(1, "", "boom")
    fake_runner.responses[("codex", "plugin", "marketplace", "add", "o/other")] = runner.Result(
        0, json.dumps({"marketplaceName": "other", "alreadyAdded": True}), "")
    lines = codex_project.plugins(two, dry_run=False)
    assert codex_project.failed_plugins(two, lines) == {"x@claude-plugins-official"}


def test_conflicts_left_as_is_fail_the_profile(repo, monkeypatch):
    monkeypatch.setattr(profiles, "load_profile", lambda name: WEB)
    monkeypatch.setattr(targets, "codex_enabled", lambda: True)
    monkeypatch.setattr(codex_project, "apply", lambda prof, p, install, dry_run, **k: [
        "mcp chrome-devtools: left as is in x (a server of that name is already there)"])
    assert project.add_profile(repo, "web", install=False) == 1


def test_no_codex_route_makes_profile_exit_1(repo, fake_runner, monkeypatch):
    monkeypatch.setattr(profiles, "load_profile", lambda name: THESIS)
    monkeypatch.setattr(targets, "claude_enabled", lambda: False)
    monkeypatch.setattr(targets, "codex_enabled", lambda: True)
    monkeypatch.setattr(codex_project, "apply", lambda prof, p, install, dry_run, **k: ["plugin x@y: no Codex route (its marketplace is not on GitHub)"])
    assert project.add_profile(repo, "thesis") == 1


def test_init_exits_1_when_a_profile_failed(repo, fake_runner, monkeypatch):
    failing = profiles.Profile(name="web", description="", commands=[["tool", "x"]])
    monkeypatch.setattr(profiles, "load_profile", lambda name: failing)
    fake_runner.responses[("tool",)] = runner.Result(1, "", "boom")
    assert project.init(repo, ["web"], yes=True, install=True, dry_run=False, ask=lambda q: "", interactive=False) == 1


def test_failed_skill_links_make_profile_exit_1(repo, monkeypatch):
    monkeypatch.setattr(profiles, "load_profile", lambda name: WEB)
    monkeypatch.setattr(targets, "codex_enabled", lambda: True)
    monkeypatch.setattr(codex_project, "apply", lambda prof, p, install, dry_run, **k: ["skill pw: not linked for Codex (denied)"])
    assert project.add_profile(repo, "web", install=False) == 1


def test_a_different_skill_under_the_same_name_is_reported(repo):
    targets.set_agents({"claude": False, "codex": True})
    (repo / ".claude" / "skills" / "pw").mkdir(parents=True)
    (repo / ".agents" / "skills" / "pw").mkdir(parents=True)
    lines = profiles.link_skills(repo, dry_run=False)
    assert any("pw" in l and "left as is" in l for l in lines)
    (repo / ".agents" / "skills" / "pw").rmdir()
    profiles.link_skills(repo, dry_run=False)
    assert profiles.link_skills(repo, dry_run=False) == []  # our own link: silent


def test_a_repo_switch_that_is_off_is_reported_as_a_problem(repo):
    cfg = repo / ".codex" / "config.toml"
    cfg.parent.mkdir()
    cfg.write_text('[plugins."deepeval@claude-plugins-official"]\nenabled = false\n')
    lines = codex_project.config(THESIS, repo, dry_run=False)
    assert any("deepeval" in l and "switched off" in l for l in lines)


def test_profile_plugins_name_the_backup_folder(repo, fake_runner, monkeypatch):
    import json
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: {"enabledPlugins": {}})
    monkeypatch.setattr(codex, "apply_config", lambda bk, dry_run=False: [])
    fake_runner.responses[("codex", "plugin", "list")] = runner.Result(0, json.dumps({"installed": []}), "")
    fake_runner.responses[("codex", "plugin", "marketplace", "add", codex.OFFICIAL)] = runner.Result(
        0, json.dumps({"marketplaceName": "claude-plugins-official", "alreadyAdded": True}), "")
    seen = []
    from loadout import backup as backup_mod
    real = backup_mod.Backup

    class Spy(real):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            seen.append(self)
    monkeypatch.setattr(backup_mod, "Backup", Spy)
    lines = codex_project.plugins(THESIS, dry_run=False)
    assert not seen[0].empty
    assert any(str(seen[0].root) in line for line in lines)


def _extension_only(fake_runner, monkeypatch):
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: {"enabledPlugins": {}})
    monkeypatch.setattr(profiles, "load_profile", lambda name: THESIS)
    monkeypatch.setattr(targets, "claude_enabled", lambda: False)
    monkeypatch.setattr(targets, "codex_enabled", lambda: True)
    fake_runner.missing.add("codex")
    monkeypatch.setattr(codex, "extension_state", lambda: (object(), None))  # a usable extension


def test_extension_mode_sets_no_plugins_and_says_so(repo, fake_runner, monkeypatch):
    _extension_only(fake_runner, monkeypatch)
    for dry in (False, True):
        assert codex_project.plugins(THESIS, dry_run=dry) == [codex_project.PLUGINS_EXTENSION_NOTE]
    assert not any(c[:2] == ["codex", "plugin"] for c in fake_runner.calls)


def test_profile_in_extension_mode_prints_the_note_and_exits_0(repo, fake_runner, monkeypatch, capsys):
    _extension_only(fake_runner, monkeypatch)
    assert project.add_profile(repo, "thesis", install=True) == 0
    out = capsys.readouterr().out
    assert "VS Code's Codex extension loads no plugins; the profile's Codex plugins are not set" in out
    assert "run loadout profile again" not in out and "installed in your Codex" not in out
    cfg = repo / ".codex" / "config.toml"
    assert not cfg.exists() or "deepeval" not in cfg.read_text()


def test_profile_plan_in_extension_mode_has_the_note(repo, fake_runner, monkeypatch, capsys):
    _extension_only(fake_runner, monkeypatch)
    assert project.add_profile(repo, "thesis", install=True, dry_run=True) == 0
    out = capsys.readouterr().out
    assert codex_project.PLUGINS_EXTENSION_NOTE in out and "installed in your Codex" not in out


def test_profile_with_no_codex_and_no_usable_extension_fails_with_the_reason(repo, fake_runner, monkeypatch, capsys):
    _extension_only(fake_runner, monkeypatch)
    monkeypatch.setattr(codex, "extension_state", lambda: (None, codex.EXT_OLD.format(version="0.100.0")))
    lines = codex_project.plugins(THESIS, dry_run=False)
    assert codex_project.PLUGINS_EXTENSION_NOTE not in lines
    assert lines and all("0.100.0" in l and "not installed" in l for l in lines)
    assert project.add_profile(repo, "thesis", install=True) == 1
    out = capsys.readouterr().out
    assert codex_project.PLUGINS_EXTENSION_NOTE not in out and "installed in your Codex" not in out
    assert "0.100.0" in out
