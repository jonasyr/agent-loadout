"""`.loadout.json`: which agents a repo is for, and whether loadout may write there (spec Part 1)."""
import os

import pytest

from loadout import repo_config, targets


@pytest.fixture
def repo(fake_home, tmp_path):
    p = tmp_path / "repo"
    (p / ".git").mkdir(parents=True)
    return p


def test_without_the_file_the_users_agents_decide(repo):
    targets.set_agents({"claude": True, "codex": False})
    cfg = repo_config.load(repo)
    assert cfg.exists is False and cfg.agents is None and cfg.manage is True
    assert repo_config.agents(repo) == {"claude": True, "codex": False}


def test_the_file_wins_over_the_users_agents(repo):
    targets.set_agents({"claude": True, "codex": True})
    (repo / ".loadout.json").write_text('{\n  "agents": [\n    "codex"\n  ]\n}\n')
    assert repo_config.agents(repo) == {"claude": False, "codex": True}


def test_manage_false_is_read(repo):
    (repo / ".loadout.json").write_text('{"manage": false}')
    assert repo_config.load(repo).manage is False


@pytest.mark.parametrize("text, word", [
    ('{"agents": "codex"}', "agents"),
    ('{"agents": []}', "agents"),
    ('{"agents": ["codex", "codex"]}', "agents"),
    ('{"agents": ["cursor"]}', "agents"),
    ('{"manage": "no"}', "manage"),
    ('[1]', "object"),
    ('{', "parse"),
])
def test_an_invalid_file_is_refused_with_its_reason(repo, text, word):
    (repo / ".loadout.json").write_text(text)
    with pytest.raises(repo_config.Invalid) as exc:
        repo_config.load(repo)
    assert str(exc.value).startswith(".loadout.json: ") and word in str(exc.value)


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink")
def test_a_link_leading_outside_the_repo_is_refused(repo, tmp_path):
    outside = tmp_path / "elsewhere.json"
    outside.write_text('{"agents": ["codex"]}')
    (repo / ".loadout.json").symlink_to(outside)
    with pytest.raises(repo_config.Invalid, match="outside"):
        repo_config.load(repo)


def test_new_text_creates_and_keeps_other_keys(repo):
    assert repo_config.new_text(repo, frozenset({"codex", "claude"})) == '{\n  "agents": [\n    "claude",\n    "codex"\n  ]\n}\n'
    (repo / ".loadout.json").write_text('{\r\n    "team": "x",\r\n    "agents": [\r\n        "codex"\r\n    ]\r\n}\r\n')
    assert repo_config.new_text(repo, frozenset({"codex"})) is None
    assert repo_config.new_text(repo, frozenset({"claude", "codex"})) == (
        '{\r\n    "team": "x",\r\n    "agents": [\r\n        "claude",\r\n        "codex"\r\n    ]\r\n}\r\n')


def test_new_text_refuses_a_hand_laid_out_file(repo):
    (repo / ".loadout.json").write_text('{"agents": ["codex"], "team": "x"}\n')
    with pytest.raises(repo_config.Invalid, match="by hand"):
        repo_config.new_text(repo, frozenset({"claude", "codex"}))


@pytest.mark.parametrize("value, want", [
    ("codex", {"codex"}), ("claude,codex", {"claude", "codex"}), (" Codex , claude ", {"claude", "codex"}),
])
def test_parse_agents(value, want):
    assert repo_config.parse_agents(value) == frozenset(want)


@pytest.mark.parametrize("value", ["", "cursor", "codex,", ","])
def test_parse_agents_refuses(value):
    with pytest.raises(ValueError, match="--agents"):
        repo_config.parse_agents(value)
