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


def test_binaries_follow_the_chosen_agents(fake_home):
    from loadout import catalog
    ids = lambda: {e["id"] for e in catalog.binaries()}  # noqa: E731
    assert "claude" in ids() and "codex" not in ids()
    targets.set_agents({"claude": False, "codex": True})
    assert "claude" not in ids() and "codex" in ids()
    targets.set_agents({"claude": True, "codex": True})
    assert {"claude", "codex"} <= ids()


def test_codex_installs_through_mise():
    from loadout import catalog
    entry = catalog.by_id("codex")
    assert entry["install"]["posix"] == [["mise", "use", "-g", "codex"]] and entry["needs"] == ["mise"]
    assert entry["target"] == "codex" and entry["required"] is True


def test_check_without_claude_has_no_claude_groups(fake_home, fake_runner, monkeypatch):
    from loadout import check
    targets.set_agents({"claude": False, "codex": True})
    monkeypatch.setattr(codex, "checks", lambda: [])
    fake_runner.missing.add("claude")
    names = [r.name for r in check.run_checks()]
    assert not any(n.startswith(("link ", "settings", "plugin", "duplicate", "own")) for n in names), names
    assert not any(n == "claude" for n in names)


def test_sync_without_claude_skips_claude_parts(fake_home, fake_runner, monkeypatch):
    from loadout import link, maintenance, personal_mcp, settings_merge
    targets.set_agents({"claude": False, "codex": True})
    called = []
    monkeypatch.setattr(settings_merge, "apply_settings", lambda: called.append("settings") or (None, None))
    monkeypatch.setattr(personal_mcp, "apply_mcp", lambda: called.append("mcp") or [])
    monkeypatch.setattr(link, "link_all", lambda bk, retry_symlinks=False: called.append("links") or [])
    monkeypatch.setattr(maintenance, "pull_if_clean", lambda root: True)
    monkeypatch.setattr(maintenance, "find_outdated", lambda: [])
    monkeypatch.setattr(codex, "unavailable", lambda: None)
    monkeypatch.setattr(codex, "apply_all", lambda bk, refresh=False, **kw: called.append("codex") or [])
    monkeypatch.setattr(codex, "drift", lambda: [])
    (__import__("loadout").paths.personal_root() / ".git").mkdir(parents=True)
    maintenance._maintain(0)
    assert called == ["codex"]


def test_drift_is_empty_without_claude(fake_home, fake_runner):
    targets.set_agents({"claude": False, "codex": True})
    assert codex.drift() == []
