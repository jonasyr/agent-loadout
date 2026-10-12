"""Which coding agents loadout sets up: <personal>/targets.json."""
import json

import pytest

from loadout import codex, targets
from loadout.__main__ import main


def test_existing_layers_keep_claude_and_have_no_codex(fake_home):
    assert targets.claude_enabled() and not targets.codex_enabled() and not targets.decided()


def test_set_and_read_both_agents(fake_home):
    targets.set_agents({"claude": False, "codex": True})
    assert json.loads(targets.path().read_text()) == {"claude": False, "codex": True}
    assert not targets.claude_enabled() and targets.codex_enabled() and codex.enabled() and targets.decided()


def test_last_agent_cannot_be_turned_off(fake_home):
    targets.set_agents({"claude": True, "codex": False})
    with pytest.raises(ValueError, match="at least one"):
        targets.set_target("claude", False)
    targets.set_target("codex", True)
    assert targets.set_target("claude", False) == "claude: off"


@pytest.mark.parametrize("text,expected", [("claude", {"claude": True, "codex": False}),
                                           ("codex", {"claude": False, "codex": True}),
                                           ("codex, claude", {"claude": True, "codex": True})])
def test_parse_agents(text, expected):
    assert targets.parse_agents(text) == expected


@pytest.mark.parametrize("text", ["", "cursor", "claude,,codex x"])
def test_parse_agents_refuses_unknown(text):
    with pytest.raises(ValueError):
        targets.parse_agents(text)


def test_configure_set_target_claude_off_needs_codex(fake_home, fake_runner, monkeypatch, capsys):
    from loadout import configure
    monkeypatch.setattr(configure, "apply_all", lambda ask: None)
    monkeypatch.setattr(configure, "offer_commit", lambda ask: None)
    assert main(["configure", "set", "target", "claude", "off"]) == 1
    assert "at least one" in capsys.readouterr().err
