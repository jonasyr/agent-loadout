"""Two loadout users on one repo (spec Parts 2 and 5): A has both agents, B has Codex only. After every step both
users' agents' files are complete and no entry a person changed was reversed without a yes."""
import json

import pytest

from loadout import profiles, project, targets


@pytest.fixture
def world(fake_home, fake_runner, tmp_path, monkeypatch):
    homes = {"a": tmp_path / "home-a", "b": tmp_path / "home-b"}
    for h in homes.values():
        h.mkdir()
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    state = {"settings": {"env": {"MODE": "fast"}, "permissions": {"allow": ["Bash(npm test)"]}},
             "mcp": {"mcpServers": {"cd": {"command": "npx", "args": ["-y", "cd@1"]}}}}
    monkeypatch.setattr(profiles, "load_profile", lambda n: profiles.Profile(
        name=n, description="Web", settings=json.loads(json.dumps(state["settings"])), mcp=state["mcp"]))

    def as_user(who):
        monkeypatch.setenv("HOME", str(homes[who]))
        monkeypatch.setenv("USERPROFILE", str(homes[who]))
        targets.set_agents({"claude": who == "a", "codex": True})
    return repo, state, as_user


def files(repo):
    return {p.relative_to(repo).as_posix(): p.read_bytes() for p in repo.rglob("*") if p.is_file() and ".git" not in p.parts}


def settings(repo):
    return json.loads((repo / ".claude" / "settings.json").read_text())


def complete(repo):
    assert "cd" in json.loads((repo / ".mcp.json").read_text())["mcpServers"]
    assert "[mcp_servers.cd]" in (repo / ".codex" / "config.toml").read_text()
    assert set(json.loads((repo / ".loadout.json").read_text())["agents"]) == {"claude", "codex"}


def profile(repo, **kw):
    return project.add_profile(repo, "web", install=False, approve=lambda plan: True, **kw)


def test_two_users_keep_each_other_whole(world):
    repo, state, as_user = world
    as_user("a")
    assert project.init(repo, ["web"], yes=True, install=False, dry_run=False, ask=lambda q: "", interactive=False,
                        agents=frozenset({"claude", "codex"})) == 0
    complete(repo)

    as_user("b")  # Codex only: the same profile again changes nothing
    before = files(repo)
    assert profile(repo) == 0
    assert files(repo) == before

    path = repo / ".claude" / "settings.json"  # B changes a value by hand
    data = settings(repo)
    data["env"]["MODE"] = "slow"
    path.write_text(json.dumps(data, indent=2) + "\n")

    as_user("a")
    assert profile(repo) == 0
    assert settings(repo)["env"]["MODE"] == "slow"
    complete(repo)

    state["settings"]["env"]["MODE"] = "safe"  # the profile is updated
    state["settings"]["permissions"]["allow"].append("Bash(npm run lint)")
    as_user("b")  # a Codex-only user still keeps Claude Code's repo files current
    assert profile(repo) == 0
    assert settings(repo)["permissions"]["allow"] == ["Bash(npm test)", "Bash(npm run lint)"]
    assert settings(repo)["env"]["MODE"] == "slow"
    complete(repo)

    data = settings(repo)  # A removes an entry by hand
    data["permissions"]["allow"].remove("Bash(npm test)")
    path.write_text(json.dumps(data, indent=2) + "\n")
    as_user("b")  # nothing differs any more (MODE "safe" was offered once and declined), so no question
    asked = []
    assert profile(repo, decide=lambda lines: asked.append(lines) or True) == 0
    assert asked == []
    assert settings(repo)["permissions"]["allow"] == ["Bash(npm run lint)"]  # the removal stays
    assert settings(repo)["env"]["MODE"] == "slow"
    complete(repo)

    as_user("a")
    before = files(repo)
    assert profile(repo) == 0
    assert files(repo) == before
