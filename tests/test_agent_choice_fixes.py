"""Final review findings for the agent choice."""
import json
import subprocess

import pytest

from loadout import bootstrap, codex, maintenance, out, paths, runner, targets
from loadout.__main__ import main


def _run(**kw):
    args = dict(install=False, yes=True, plugins=False, adopt_step=False, ask=lambda q: "", interactive=False)
    args.update(kw)
    return bootstrap.bootstrap(**args)


def test_existing_layer_without_a_choice_gets_no_new_file(fake_home, fake_runner):
    """An untracked targets.json would leave the personal repo dirty and pause the daily sync."""
    paths.personal_root().mkdir(parents=True)
    fake_runner.missing.add("codex")
    _run()
    assert not targets.path().exists()


def test_an_answered_question_is_stored(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(codex, "unavailable", lambda: None)
    monkeypatch.setattr(codex, "apply_all", lambda bk, refresh=False, **kw: [])
    monkeypatch.setattr(codex, "open_steps", lambda: [])
    _run(yes=False, interactive=True, ask=lambda q: "3" if "coding agents" in q else "")
    assert json.loads(targets.path().read_text()) == {"claude": True, "codex": True}


def test_invalid_answer_takes_the_default_instead_of_asking_forever(fake_home, fake_runner):
    fake_runner.missing.add("codex")
    assert bootstrap.choose_agents(lambda q: "y", True, None) == {"claude": True, "codex": False}


def test_empty_agents_flag_is_refused(fake_home):
    with pytest.raises(ValueError):
        bootstrap.choose_agents(lambda q: "", True, "")


def test_set_target_claude_on_without_claude_points_to_bootstrap(fake_home, fake_runner, monkeypatch, capsys):
    from loadout import configure
    targets.set_agents({"claude": False, "codex": True})
    fake_runner.missing.add("claude")
    applied = []
    monkeypatch.setattr(configure, "apply_all", lambda ask: applied.append(1))
    monkeypatch.setattr(configure, "offer_commit", lambda ask: None)
    assert main(["configure", "set", "target", "claude", "on"]) == 0
    assert "loadout bootstrap --install" in capsys.readouterr().out and applied == []


def test_set_target_claude_on_with_only_the_extensions_claude_sets_it_up(fake_home, fake_runner, monkeypatch, capsys):
    """VS Code's Claude Code extension ships a claude: it counts as installed (spec Part 3.3)."""
    from conftest import host_claude_bin
    from loadout import configure, link
    exe = fake_home / ".vscode" / "extensions" / "anthropic.claude-code-2.1.10" / host_claude_bin()
    exe.parent.mkdir(parents=True)
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o755)
    targets.set_agents({"claude": False, "codex": True})
    fake_runner.missing.add("claude")
    applied = []
    monkeypatch.setattr(link, "link_all", lambda bk: None)
    monkeypatch.setattr(configure, "apply_all", lambda ask: applied.append(1))
    monkeypatch.setattr(configure, "offer_commit", lambda ask: None)
    assert main(["configure", "set", "target", "claude", "on"]) == 0
    assert applied == [1] and "not installed yet" not in capsys.readouterr().out


def test_cloned_choice_is_announced(fake_home, fake_runner, monkeypatch, capsys):
    def cloned_layer(ask, bk, interactive, **kw):
        paths.personal_root().mkdir(parents=True)
        (paths.personal_root() / "targets.json").write_text(json.dumps({"claude": False, "codex": True}))
        return "cloned", True
    monkeypatch.setattr(bootstrap, "ensure_personal", cloned_layer)
    monkeypatch.setattr(codex, "unavailable", lambda: None)
    monkeypatch.setattr(codex, "apply_all", lambda bk, refresh=False, **kw: [])
    monkeypatch.setattr(codex, "open_steps", lambda: [])
    _run(yes=False, interactive=True, ask=lambda q: "1" if "coding agents" in q else "")
    assert "using your personal layer's agents: Codex" in capsys.readouterr().out


def test_verbose_ending_names_the_chosen_agent(fake_home, fake_runner, monkeypatch, capsys):
    monkeypatch.setattr(out, "VERBOSE", True)
    monkeypatch.setattr(codex, "unavailable", lambda: None)
    monkeypatch.setattr(codex, "apply_all", lambda bk, refresh=False, **kw: [])
    monkeypatch.setattr(codex, "open_steps", lambda: [])
    _run(agents="codex")
    ending = "\n".join(capsys.readouterr().out.rstrip().splitlines()[-2:])
    assert "Claude Code" not in ending and "Codex" in ending, ending


def test_broken_targets_file_does_not_kill_the_background_sync(fake_home, fake_runner, monkeypatch):
    paths.personal_root().mkdir(parents=True)
    (paths.personal_root() / ".git").mkdir()
    targets.path().write_text("{broken")
    monkeypatch.setattr(maintenance, "pull_if_clean", lambda root: True)
    monkeypatch.setattr(maintenance, "find_outdated", lambda: [])
    maintenance._maintain(0)
    notice = (paths.state_dir() / "pending-notice").read_text(encoding="utf-8")
    assert "targets.json" in notice


def test_codex_has_no_update_command_that_could_install_a_second_copy():
    from loadout import catalog
    assert "update" not in catalog.by_id("codex")


def test_update_leaves_claude_alone_on_codex_only(fake_home, fake_runner, monkeypatch):
    targets.set_agents({"claude": False, "codex": True})
    monkeypatch.setattr(maintenance, "find_outdated", lambda: [])
    maintenance.update(True, lambda q: "")
    assert not any(c[0] == "claude" for c in fake_runner.calls)


def test_configure_changes_reach_codex_and_skip_claude_on_codex_only(fake_home, fake_runner, monkeypatch, capsys):
    from loadout import configure
    targets.set_agents({"claude": False, "codex": True})
    monkeypatch.setattr(configure, "offer_commit", lambda ask: None)
    monkeypatch.setattr(codex, "unavailable", lambda: None)
    applied = []
    monkeypatch.setattr(codex, "apply_all", lambda bk, refresh=False, **kw: applied.append(1) or ["plugin x@y: installed"])
    configure.apply_all(lambda q: "")
    out_text = capsys.readouterr().out
    assert applied == [1] and "plugin x@y: installed" in out_text
    assert not any(c[0] == "claude" for c in fake_runner.calls)
    assert not (paths.claude_home() / "settings.json").exists()
    assert "Codex" in out_text and "Claude Code" not in out_text


def test_configure_changes_reach_both_agents(fake_home, fake_runner, monkeypatch):
    from loadout import bootstrap as b, configure
    targets.set_agents({"claude": True, "codex": True})
    monkeypatch.setattr(configure, "offer_commit", lambda ask: None)
    monkeypatch.setattr(b, "setup_plugins", lambda **kw: [])
    monkeypatch.setattr(codex, "unavailable", lambda: None)
    applied = []
    monkeypatch.setattr(codex, "apply_all", lambda bk, refresh=False, **kw: applied.append(1) or [])
    configure.apply_all(lambda q: "")
    assert applied == [1]
