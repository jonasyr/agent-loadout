"""loadout explain: which entries in a repo file are loadout's (spec Part 0)."""
import json

import pytest

from loadout import __main__ as cli, explain, profiles, project, targets

TOKEN = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"


@pytest.fixture
def repo(fake_home, fake_runner, tmp_path, monkeypatch):
    p = tmp_path / "repo"
    (p / ".git").mkdir(parents=True)
    targets.set_agents({"claude": True, "codex": True})
    monkeypatch.setattr(profiles, "load_profile", lambda n: profiles.Profile(
        name=n, description="d", settings={"env": {"A": "1"}, "permissions": {"allow": ["x", "y"]}},
        mcp={"mcpServers": {"gh": {"command": "gh-mcp", "env": {"GITHUB_TOKEN": TOKEN}},
                           "cd": {"command": "npx", "args": ["-y", "cd@1"]}}}))
    (p / ".loadout.json").write_text('{\n  "agents": [\n    "claude",\n    "codex"\n  ]\n}\n')
    project.add_profile(p, "web", install=False, approve=lambda plan: True)
    return p


def test_it_lists_loadouts_entries_and_their_state(repo, capsys):
    path = repo / ".claude" / "settings.json"
    data = json.loads(path.read_text())
    data["env"]["A"] = "9"
    data["permissions"]["allow"].remove("x")
    path.write_text(json.dumps(data, indent=2) + "\n")
    capsys.readouterr()
    assert explain.explain(".claude/settings.json", cwd=repo) == 0
    out = capsys.readouterr().out
    assert 'profile web  env/A: "1"  changed in this repo (now "9")' in out
    assert 'permissions/allow: "x"  removed in this repo' in out
    assert "permissions/allow: \"y\"  loadout's value" in out


def test_a_secret_is_never_shown(repo, capsys):
    capsys.readouterr()
    explain.explain(".mcp.json", cwd=repo)
    out = capsys.readouterr().out
    assert TOKEN not in out and "(a secret value, not shown)" in out


def test_codex_entries_are_listed(repo, capsys):
    capsys.readouterr()
    explain.explain(".codex/config.toml", cwd=repo)
    assert "mcp_servers/cd" in capsys.readouterr().out  # gh holds a plaintext secret: Codex refuses it


def test_loadout_json_and_gitignore(repo, capsys):
    (repo / ".gitignore").write_text("node_modules\n\n# loadout\n.claude/settings.local.json\n.serena/cache/\n")
    capsys.readouterr()
    explain.explain(".loadout.json", cwd=repo)
    explain.explain(".gitignore", cwd=repo)
    out = capsys.readouterr().out
    assert "agents: claude, codex" in out and "profile web:" in out
    assert ".claude/settings.local.json" in out and "node_modules" not in out


def test_a_file_without_entries_says_so(repo, capsys):
    (repo / "README.md").write_text("hi\n")
    assert explain.explain("README.md", cwd=repo) == 0
    assert "recorded no entries" in capsys.readouterr().out


def test_outside_a_repo_is_an_error(tmp_path, fake_home, capsys):
    (tmp_path / "x.json").write_text("{}")
    assert explain.explain("x.json", cwd=tmp_path) == 1


def test_it_writes_nothing(repo, fake_home, monkeypatch):
    def snapshot():
        return {p: p.read_bytes() for root in (repo, fake_home) for p in root.rglob("*") if p.is_file()}
    before = snapshot()
    monkeypatch.chdir(repo)
    assert cli.main(["explain", ".claude/settings.json"]) == 0
    assert snapshot() == before
