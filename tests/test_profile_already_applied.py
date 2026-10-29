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


@pytest.fixture
def setup(fake_home, fake_runner, tmp_path, monkeypatch):
    p = tmp_path / "repo"
    (p / ".git").mkdir(parents=True)
    monkeypatch.setattr(out, "VERBOSE", False)
    monkeypatch.setattr(targets, "claude_enabled", lambda: True)
    monkeypatch.setattr(targets, "codex_enabled", lambda: False)
    monkeypatch.setattr(profiles, "load_profile", lambda name: {"web": WEB, "android": ANDROID}[name])
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
