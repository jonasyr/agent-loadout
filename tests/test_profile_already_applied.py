"""`loadout profile NAME` again: "already applied" only when the repo files are unchanged AND this machine has the
profile's parts (plugins, what its commands leave behind); otherwise only the missing parts are planned
(spec 2026-10-29 init output, G4)."""
import json

import pytest

from loadout import out, paths, profiles, project, runner, targets

WEB = profiles.Profile(name="web", description="", settings={"disabledMcpjsonServers": ["chrome-devtools"]},
                       commands=[["playwright-cli", "install", "--skills"]],
                       done_when=[".claude/skills/playwright-cli", ".agents/skills/playwright-cli"])
KOTLIN = "kotlin-lsp@claude-plugins-official"
ANDROID = profiles.Profile(name="android", description="", install=[KOTLIN],
                           settings={"enabledPlugins": {KOTLIN: True}})

TOOL = profiles.Profile(name="tool", description="", commands=[["tool", "setup"]], done_when=[".tool"])


@pytest.fixture
def setup(fake_home, fake_runner, tmp_path, monkeypatch):
    p = tmp_path / "repo"
    (p / ".git").mkdir(parents=True)
    monkeypatch.setattr(out, "VERBOSE", False)
    monkeypatch.setattr(targets, "claude_enabled", lambda: True)
    monkeypatch.setattr(targets, "codex_enabled", lambda: False)
    monkeypatch.setattr(profiles, "load_profile", lambda name: {"web": WEB, "android": ANDROID, "tool": TOOL}[name])
    return p


def _agents(repo, *agents):
    (repo / ".loadout.json").write_text(json.dumps({"agents": list(agents)}) + "\n")


def _claude_installed(repo, *ids):
    d = paths.claude_home() / "plugins"
    d.mkdir(parents=True, exist_ok=True)
    plugins = {i: [{"scope": "project", "projectPath": str(repo.resolve()), "installPath": "/x"}] for i in ids}
    (d / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": plugins}))


def _apply(repo, name):
    """The first run: files written and recorded, commands run (fake)."""
    assert project.add_profile(repo, name, approve=lambda plan: True) == 0


def _again(repo, name, asked, **k):
    return project.add_profile(repo, name, approve=lambda plan: asked.append(plan) or True, **k)


def test_already_applied_no_question(setup, fake_runner, capsys):
    repo = setup
    _agents(repo, "claude")
    _apply(repo, "web")
    (repo / ".claude" / "skills" / "playwright-cli").mkdir(parents=True)
    capsys.readouterr()
    fake_runner.calls.clear()
    asked = []
    assert _again(repo, "web", asked) == 0
    assert capsys.readouterr().out.strip() == project.ALREADY.format(name="web")
    assert asked == [] and fake_runner.calls == []


def test_dry_run_already_applied(setup, fake_runner, capsys):
    repo = setup
    _agents(repo, "claude")
    _apply(repo, "web")
    (repo / ".claude" / "skills" / "playwright-cli").mkdir(parents=True)
    capsys.readouterr()
    assert project.add_profile(repo, "web", dry_run=True) == 0
    assert capsys.readouterr().out.strip() == project.ALREADY.format(name="web")


def test_missing_plugin_is_planned(setup, fake_runner, capsys):
    repo = setup
    _agents(repo, "claude")
    _apply(repo, "android")
    _claude_installed(repo)  # a teammate's clone: nothing installed for this project
    capsys.readouterr()
    asked = []
    _again(repo, "android", asked)
    assert len(asked) == 1
    runs = [l for l in asked[0] if l.startswith("  run")]
    assert len(runs) == 1 and f"claude plugin install {KOTLIN} --scope project" in runs[0]


def test_installed_plugin_is_already_applied(setup, fake_runner, capsys):
    repo = setup
    _agents(repo, "claude")
    _apply(repo, "android")
    _claude_installed(repo, KOTLIN)
    capsys.readouterr()
    asked = []
    assert _again(repo, "android", asked) == 0 and asked == []


def test_commands_rerun_when_done_when_missing(setup, fake_runner, capsys):
    repo = setup
    _agents(repo, "claude")
    _apply(repo, "web")
    asked = []
    _again(repo, "web", asked)
    assert len(asked) == 1 and any("run     playwright-cli install --skills" in l for l in asked[0])


def test_codex_only_ignores_claude_plugins(setup, fake_runner, monkeypatch, capsys):
    repo = setup
    _agents(repo, "codex")
    monkeypatch.setattr(targets, "codex_enabled", lambda: True)
    fake_runner.responses[("codex", "plugin", "list")] = runner.Result(
        0, json.dumps({"installed": [{"pluginId": KOTLIN}], "available": []}), "")
    assert project.add_profile(repo, "android", install=False, approve=lambda plan: True) == 0  # files only
    capsys.readouterr()
    asked = []
    assert _again(repo, "android", asked) == 0 and asked == []
    assert project.ALREADY.format(name="android") in capsys.readouterr().out


def test_refresh_runs_anyway(setup, fake_runner, capsys):
    repo = setup
    _agents(repo, "claude")
    _apply(repo, "web")
    (repo / ".claude" / "skills" / "playwright-cli").mkdir(parents=True)
    asked = []
    _again(repo, "web", asked, refresh=True)
    assert len(asked) == 1 and any("run     playwright-cli install --skills" in l for l in asked[0])


def test_already_applied_is_reported_to_the_caller(setup, fake_runner, capsys):
    # review: adopt read applied=False as "not applied" right after "already applied here"
    repo = setup
    _agents(repo, "claude")
    _apply(repo, "web")
    (repo / ".claude" / "skills" / "playwright-cli").mkdir(parents=True)
    done = {}
    assert project.add_profile(repo, "web", approve=lambda plan: True, result=done) == 0
    assert done.get("already") is True


def test_a_command_that_is_a_claude_plugin_command_is_kept(setup):
    # review: a profile command shaped like `claude plugin install …` is still matched by its own text first
    from loadout.repo_writes import Change
    cmd = ["claude", "plugin", "install", "x@y", "--scope", "user"]
    assert project._still_needed(Change("run", None, "", cmd=cmd), [" ".join(cmd)])


def test_dangling_done_when_link_is_missing(setup, fake_runner, capsys):
    # Codex review on #74: a dangling link left behind does not count as done
    repo = setup
    _agents(repo, "claude")
    _apply(repo, "web")
    (repo / ".agents" / "skills").mkdir(parents=True)
    (repo / ".agents" / "skills" / "playwright-cli").symlink_to("../../.claude/skills/playwright-cli")
    assert project.missing_here(WEB, repo) == ["playwright-cli install --skills"]


def test_link_promise_does_not_block_already_applied(setup, fake_runner, capsys):
    # Codex review on #74: in a repo for both agents the plan's link line is not a file change
    repo = setup
    _agents(repo, "claude", "codex")
    assert project.add_profile(repo, "web", install=False, approve=lambda plan: True) == 0
    (repo / ".claude" / "skills" / "playwright-cli").mkdir(parents=True)
    (repo / ".agents" / "skills").mkdir(parents=True)
    (repo / ".agents" / "skills" / "playwright-cli").symlink_to("../../.claude/skills/playwright-cli")
    capsys.readouterr()
    asked = []
    assert _again(repo, "web", asked) == 0 and asked == []
    assert project.ALREADY.format(name="web") in capsys.readouterr().out


def test_missing_claude_plugin_does_no_codex_work(setup, fake_runner, monkeypatch, capsys):
    # Codex review on #74: only what is missing runs; Codex's plugins are all there
    repo = setup
    _agents(repo, "claude", "codex")
    monkeypatch.setattr(targets, "codex_enabled", lambda: True)
    fake_runner.responses[("codex", "plugin", "list")] = runner.Result(
        0, json.dumps({"installed": [{"pluginId": KOTLIN}], "available": []}), "")
    assert project.add_profile(repo, "android", install=False, approve=lambda plan: True) == 0
    _claude_installed(repo)
    fake_runner.calls.clear()
    asked = []
    _again(repo, "android", asked)
    assert len(asked) == 1
    assert not any(c[:3] == ["codex", "plugin", "marketplace"] or c[:3] == ["codex", "plugin", "install"]
                   for c in fake_runner.calls), fake_runner.calls


def test_a_short_plugin_install_command_does_not_crash(setup):
    # review: a profile command `claude plugin install` without an id is not a generated install step
    from loadout.repo_writes import Change
    assert not project._still_needed(Change("run", None, "", cmd=["claude", "plugin", "install"]), ["plugin a@b"])


def test_only_the_missing_plugins_marketplace_is_added(setup):
    # review: with two marketplaces and one plugin missing, only that plugin's marketplace add is kept
    from loadout.repo_writes import Change
    prof = profiles.Profile(name="two", description="", install=["a@m1", "b@m2"], settings={"extraKnownMarketplaces": {
        "m1": {"source": {"source": "github", "repo": "o/m1"}}, "m2": {"source": {"source": "github", "repo": "o/m2"}}}})
    add = lambda origin: Change("run", None, "", cmd=["claude", "plugin", "marketplace", "add", origin])
    assert project._still_needed(add("o/m2"), ["plugin b@m2"], prof)
    assert not project._still_needed(add("o/m1"), ["plugin b@m2"], prof)


def test_command_only_profile_is_already_applied(setup, fake_runner, capsys):
    # review: a profile with only commands owns no entries, so it has no record; its done_when path decides
    repo = setup
    _agents(repo, "claude")
    _apply(repo, "tool")
    (repo / ".tool").mkdir()
    capsys.readouterr()
    fake_runner.calls.clear()
    asked = []
    assert _again(repo, "tool", asked) == 0
    assert capsys.readouterr().out.strip() == project.ALREADY.format(name="tool")
    assert asked == [] and fake_runner.calls == []


def test_codex_plugins_installs_only_the_missing_ones(monkeypatch):
    # review: a missing-only re-run hands Codex only the plugins it lacks, not every route of the profile
    from loadout import codex, codex_project
    monkeypatch.setattr(codex_project, "_wanted", lambda prof: ([], ["a@m1", "b@m2"], []))
    monkeypatch.setattr(codex, "has_codex", lambda: False)
    monkeypatch.setattr(codex, "unavailable", lambda: "off")
    lines = codex_project.plugins(profiles.Profile(name="x", description=""), False, only={"b@m2"})
    assert lines == ["plugin b@m2: not installed (off)"]


def test_install_only_profile_is_already_applied(setup, fake_runner, monkeypatch, capsys):
    # review: a profile with only plugins owns no repo entries; the installed plugins decide
    repo = setup
    plug = profiles.Profile(name="plug", description="", install=[KOTLIN])
    monkeypatch.setattr(profiles, "load_profile", lambda name: plug)
    _agents(repo, "claude")
    _apply(repo, "plug")
    _claude_installed(repo, KOTLIN)
    capsys.readouterr()
    fake_runner.calls.clear()
    asked = []
    assert _again(repo, "plug", asked) == 0
    assert capsys.readouterr().out.strip() == project.ALREADY.format(name="plug")
    assert asked == [] and fake_runner.calls == []


def test_commands_without_done_when_still_run_on_a_fresh_repo(setup, fake_runner, monkeypatch):
    # nothing can tell that such commands ran here, so the profile is planned, never "already applied"
    repo = setup
    bare = profiles.Profile(name="bare", description="", commands=[["tool", "setup"]])
    monkeypatch.setattr(profiles, "load_profile", lambda name: bare)
    _agents(repo, "claude")
    asked = []
    _again(repo, "bare", asked)
    assert len(asked) == 1


def test_no_unplanned_link_when_the_agents_change_during_the_commands(setup, fake_runner, monkeypatch):
    # Codex review (P1): the plan was for Claude only; .loadout.json gains Codex while the command runs
    repo = setup
    _agents(repo, "claude")
    real = runner.run

    def run(cmd, *a, **k):
        if cmd[:1] == ["playwright-cli"]:
            (repo / ".claude" / "skills" / "playwright-cli").mkdir(parents=True)
            (repo / ".claude" / "skills" / "playwright-cli" / "SKILL.md").write_text("x")
            _agents(repo, "claude", "codex")
        return real(cmd, *a, **k)

    monkeypatch.setattr(runner, "run", run)
    monkeypatch.setattr(targets, "codex_enabled", lambda: True)
    assert project.add_profile(repo, "web", approve=lambda plan: True) == 1
    assert not (repo / ".agents" / "skills" / "playwright-cli").is_symlink()


def test_done_when_through_a_link_out_of_the_repo_is_missing(setup, fake_runner, tmp_path):
    # Codex review: a done_when path that a symlink leads out of the repo does not count as done
    repo = setup
    _agents(repo, "claude")
    _apply(repo, "tool")
    (tmp_path / "elsewhere").mkdir()
    (repo / ".tool").symlink_to(tmp_path / "elsewhere")
    asked = []
    _again(repo, "tool", asked)
    assert len(asked) == 1 and any("run     tool setup" in l for l in asked[0])


def test_skills_only_profile_is_already_applied(setup, fake_runner, monkeypatch, capsys):
    # Codex review on #74: a profile with only skills has no record; its copied skills, unchanged, show it is done
    repo = setup
    src = paths.personal_root() / "profiles" / "skills" / "my-skill"
    src.mkdir(parents=True)
    (src / "SKILL.md").write_text("---\nname: my-skill\ndescription: d\n---\n")
    sk = profiles.Profile(name="sk", description="", skills=["my-skill"])
    monkeypatch.setattr(profiles, "load_profile", lambda name: sk)
    _agents(repo, "claude")
    _apply(repo, "sk")
    capsys.readouterr()
    asked = []
    assert _again(repo, "sk", asked) == 0
    assert capsys.readouterr().out.strip() == project.ALREADY.format(name="sk")
    assert asked == []


def test_a_changed_skill_copy_is_not_already_applied(setup, fake_runner, monkeypatch, capsys):
    repo = setup
    src = paths.personal_root() / "profiles" / "skills" / "my-skill"
    src.mkdir(parents=True)
    (src / "SKILL.md").write_text("---\nname: my-skill\ndescription: d\n---\n")
    monkeypatch.setattr(profiles, "load_profile", lambda name: profiles.Profile(name="sk", description="",
                                                                               skills=["my-skill"]))
    _agents(repo, "claude")
    _apply(repo, "sk")
    (repo / ".claude" / "skills" / "my-skill" / "SKILL.md").write_text("mine now")
    capsys.readouterr()
    _again(repo, "sk", [])
    assert project.ALREADY.format(name="sk") not in capsys.readouterr().out
