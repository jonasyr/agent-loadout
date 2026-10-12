"""Bootstrap asks which coding agents to set up and sets up exactly those."""
import json

import pytest

from loadout import bootstrap, codex, out, paths, runner, targets


def _run(**kw):
    # adopt and plugins off by default: with Claude Code on they would look up versions over the network
    args = dict(install=False, yes=True, plugins=False, adopt_step=False, ask=lambda q: "", interactive=False)
    args.update(kw)
    return bootstrap.bootstrap(**args)


def test_question_defaults(fake_home, fake_runner):
    fake_runner.missing.add("codex")
    assert bootstrap.choose_agents(lambda q: "", True, None) == {"claude": True, "codex": False}
    fake_runner.missing.discard("codex")
    assert bootstrap.choose_agents(lambda q: "", True, None) == {"claude": True, "codex": True}
    assert bootstrap.choose_agents(lambda q: "2", True, None) == {"claude": False, "codex": True}


def test_no_terminal_keeps_claude_and_flag_wins(fake_home, fake_runner):
    assert bootstrap.choose_agents(lambda q: "3", False, None) == {"claude": True, "codex": False}
    assert bootstrap.choose_agents(lambda q: "1", True, "codex") == {"claude": False, "codex": True}


def test_existing_machine_is_not_asked_and_keeps_claude(fake_home, fake_runner):
    (fake_home / ".config/loadout/personal").mkdir(parents=True)
    fake_runner.missing.add("codex")
    asked = []
    assert bootstrap.choose_agents(lambda q: asked.append(q) or "2", True, None) == {"claude": True, "codex": False}
    assert asked == []


def test_existing_machine_with_codex_is_asked(fake_home, fake_runner):
    (fake_home / ".config/loadout/personal").mkdir(parents=True)
    assert bootstrap.choose_agents(lambda q: "", True, None) == {"claude": True, "codex": True}


def test_codex_only_bootstrap_never_touches_claude(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(codex, "unavailable", lambda: None)
    monkeypatch.setattr(codex, "apply_all", lambda bk, refresh=False, **kw: ["instructions written"])
    monkeypatch.setattr(codex, "open_steps", lambda: [])
    _run(agents="codex", plugins=True, adopt_step=True)  # both on: with Claude Code off they must be skipped
    assert not any(c[0] == "claude" for c in fake_runner.calls)
    created = {p.relative_to(paths.claude_home()).parts[0] for p in paths.claude_home().rglob("*")} if paths.claude_home().exists() else set()
    assert created <= {".loadout", "backups"}, created
    assert json.loads(targets.path().read_text()) == {"claude": False, "codex": True}


def test_cloned_choice_wins_and_installs_what_is_missing(fake_home, fake_runner, monkeypatch):
    def cloned_layer(ask, bk, interactive):
        root = paths.personal_root()
        root.mkdir(parents=True)
        (root / "targets.json").write_text(json.dumps({"claude": True, "codex": True}))
        return "cloned", True
    monkeypatch.setattr(bootstrap, "ensure_personal", cloned_layer)
    calls = []
    monkeypatch.setattr(bootstrap, "check_prereqs", lambda install, ask, installed=None, notes=None: calls.append(
        {e["id"] for e in __import__("loadout").catalog.binaries()}) or [])
    monkeypatch.setattr(codex, "unavailable", lambda: None)
    monkeypatch.setattr(codex, "apply_all", lambda bk, refresh=False, **kw: [])
    monkeypatch.setattr(codex, "open_steps", lambda: [])
    _run(install=True, yes=False, interactive=True, ask=lambda q: "1" if "coding agents" in q else "")
    assert targets.codex_enabled(), "the cloned layer's choice wins over the answered question"
    assert len(calls) == 2 and "codex" in calls[1], "prerequisites run again for the newly chosen agent"


def test_an_explicit_agents_flag_wins_over_the_cloned_layer(fake_home, fake_runner, monkeypatch):
    def cloned_layer(ask, bk, interactive):
        paths.personal_root().mkdir(parents=True)
        (paths.personal_root() / "targets.json").write_text(json.dumps({"claude": True, "codex": True}))
        return "cloned", True
    monkeypatch.setattr(bootstrap, "ensure_personal", cloned_layer)
    _run(agents="claude")
    assert json.loads(targets.path().read_text()) == {"claude": True, "codex": False}


def test_next_line_names_the_chosen_agent(fake_home, fake_runner, monkeypatch, capsys):
    monkeypatch.setattr(out, "VERBOSE", False)
    monkeypatch.setattr(codex, "unavailable", lambda: None)
    monkeypatch.setattr(codex, "apply_all", lambda bk, refresh=False, **kw: [])
    monkeypatch.setattr(codex, "open_steps", lambda: [])
    _run(agents="codex")
    assert "run `codex`" in capsys.readouterr().out
