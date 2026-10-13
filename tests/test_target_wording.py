"""With an agent off, loadout neither reads nor names it."""
import json

import pytest

from loadout import adopt, check, codex, configure, own, paths, targets
from loadout.__main__ import main


def _only(monkeypatch, claude, codex_on):
    monkeypatch.setattr(targets, "claude_enabled", lambda: claude)
    monkeypatch.setattr(targets, "codex_enabled", lambda: codex_on)
    monkeypatch.setattr(codex, "_plugin_servers", lambda: set())


def test_restart_hint_names_only_the_agents_that_are_on(fake_home, monkeypatch):
    _only(monkeypatch, True, False)
    assert targets.restart_hint() == "Restart Claude Code (or run /reload-plugins) to load the changes."
    assert adopt.restart_note() == targets.restart_hint() == adopt.RESTART_NOTE
    _only(monkeypatch, True, True)
    assert targets.restart_hint() == "Restart Claude Code (or run /reload-plugins) and Codex to load the changes."
    _only(monkeypatch, False, True)
    hint = targets.restart_hint()
    assert "Codex" in hint and "Claude" not in hint and "reload-plugins" not in hint


def test_configure_own_hint_is_codex_only_when_claude_is_off(fake_home, fake_runner, monkeypatch, capsys):
    _only(monkeypatch, False, True)
    (paths.agents_skills() / "solo").mkdir(parents=True)
    (paths.personal_root() / "rules").mkdir(parents=True)
    code = configure.set_own("solo", "global")
    out = capsys.readouterr().out
    assert code == 0, out
    assert "Restart Codex" in out and "Restart Claude Code" not in out


def test_pref_choice_ignores_claude_codes_file_when_claude_is_off(fake_home, fake_runner, monkeypatch, capsys):
    _only(monkeypatch, False, True)
    root = paths.personal_root()
    (root / "rules").mkdir(parents=True, exist_ok=True)
    (root / "settings.json").write_text(json.dumps({"attribution": {"commit": "", "pr": "", "sessionUrl": False}}))
    paths.claude_home().mkdir(parents=True, exist_ok=True)
    (paths.claude_home() / "settings.json").write_text(json.dumps({"attribution": {"commit": "", "pr": ""}}))
    code = main(["configure", "set", "pref-choice", "ai_attribution", "on"])
    assert "not effective" not in capsys.readouterr().out
    assert code == 0


def test_check_lists_own_codex_items_and_the_mcp_path_check(fake_home, fake_runner, monkeypatch):
    _only(monkeypatch, False, True)
    (paths.agents_skills() / "solo").mkdir(parents=True)
    names = {r.name: r for r in check.run_checks()}
    assert "own tools" in names and not names["own tools"].ok
    seen = []
    monkeypatch.setattr(check, "_mcp_path", lambda: seen.append(1) or [])
    check.run_checks()
    assert seen


def test_bootstrap_intro_names_no_single_agent():
    from loadout import bootstrap
    assert "Claude" not in bootstrap.INTRO and "Codex" not in bootstrap.INTRO  # printed before the agent choice


def test_own_plugin_record_line_names_the_agents_that_are_on(fake_home, monkeypatch):
    _only(monkeypatch, True, True)
    assert "Claude Code" in own.next_start_hint() and "Codex" in own.next_start_hint()
    _only(monkeypatch, False, True)
    assert "Claude" not in own.next_start_hint()
