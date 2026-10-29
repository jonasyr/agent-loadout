"""A part Codex can't express (dbhub's ${DATABASE_URL} in args, a Claude-only plugin) is a planned skip: one `skip`
line in the plan, said once, ✓ and exit 0 (spec 2026-10-29 init output, G2). Other refusals stay problems."""
import json

import pytest

from loadout import catalog, out, profiles, project, targets

DB = profiles.Profile(name="db", description="", mcp={"mcpServers": {"dbhub": {
    "type": "stdio", "command": "npx", "args": ["-y", "@bytebase/dbhub@1.4.0", "--dsn", "${DATABASE_URL}"]}}})


@pytest.fixture
def repo(fake_home, tmp_path, monkeypatch):
    p = tmp_path / "repo"
    (p / ".git").mkdir(parents=True)
    (p / ".loadout.json").write_text(json.dumps({"agents": ["claude", "codex"]}) + "\n")
    monkeypatch.setattr(targets, "codex_enabled", lambda: True)
    monkeypatch.setattr(targets, "claude_enabled", lambda: True)
    monkeypatch.setattr(out, "VERBOSE", False)
    return p


def _run(repo, monkeypatch, prof):
    monkeypatch.setattr(profiles, "load_profile", lambda name: prof)
    return project.add_profile(repo, prof.name, install=True, approve=project.approver(True, lambda q: "y", False))


def test_dbhub_skip_shown_once(repo, fake_runner, monkeypatch, capsys):
    _run(repo, monkeypatch, DB)
    text = capsys.readouterr().out
    assert sum(l.startswith("  skip    mcp dbhub: Codex does not expand") for l in text.splitlines()) == 1
    assert text.count("Codex does not expand") == 1


def test_planned_skip_exit_0_yes(repo, fake_runner, monkeypatch, capsys):
    assert _run(repo, monkeypatch, DB) == 0
    text = capsys.readouterr().out
    assert "applied with problems" not in text and "✓" in text


def test_real_refusal_still_fails(repo, fake_runner, monkeypatch, capsys):
    secret = profiles.Profile(name="s", description="", mcp={"mcpServers": {"x": {
        "command": "npx", "env": {"API_KEY": "sk-" + "live-abcdef0123456789"}}}})
    assert _run(repo, monkeypatch, secret) == 1
    assert "applied with problems" in capsys.readouterr().out


def test_claude_only_plugin_is_planned_skip(repo, fake_runner, monkeypatch, capsys):
    pid = sorted(catalog.claude_only_plugins())[0]
    prof = profiles.Profile(name="c", description="", install=[pid], settings={"enabledPlugins": {pid: True}})
    assert _run(repo, monkeypatch, prof) == 0
    text = capsys.readouterr().out
    assert sum(l.startswith("  skip    ") for l in text.splitlines()) == 1
