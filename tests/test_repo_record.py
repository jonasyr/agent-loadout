"""The record of what each profile wrote, in .loadout.json (spec Part 2)."""
import json

import pytest

from loadout import repo_config, targets
from loadout.repo_writes import RepoWrites


@pytest.fixture
def repo(fake_home, tmp_path):
    p = tmp_path / "repo"
    (p / ".git").mkdir(parents=True)
    targets.set_agents({"claude": True, "codex": False})
    return p


def test_a_wrong_shaped_record_stops_with_the_reason(repo):
    (repo / ".loadout.json").write_text('{\n  "profiles": []\n}\n')
    with pytest.raises(repo_config.Invalid, match="profiles must map"):
        repo_config.load(repo)


def test_without_the_file_the_record_comes_with_the_repos_agents(repo):
    text = repo_config.record_text(repo, None, "web", {".mcp.json": {"mcpServers/cd": {"command": "x"}}})
    assert json.loads(text) == {"agents": ["claude"], "profiles": {"web": {".mcp.json": {"mcpServers/cd": {"command": "x"}}}}}


def test_other_keys_indent_and_crlf_are_kept(repo):
    old = json.dumps({"agents": ["codex"], "note": "mine"}, indent=4).replace("\n", "\r\n") + "\r\n"
    text = repo_config.record_text(repo, old, "web", {".mcp.json": {"a": 1}})
    assert text.startswith('{\r\n    "agents"') and '"note": "mine"' in text and text.endswith("}\r\n")
    assert list(json.loads(text)) == ["agents", "note", "profiles"]


def test_an_empty_record_drops_the_file_the_profile_and_the_key(repo):
    old = json.dumps({"agents": ["claude"], "profiles": {"web": {".mcp.json": {"a": 1}}}}, indent=2) + "\n"
    assert json.loads(repo_config.record_text(repo, old, "web", {".mcp.json": {}})) == {"agents": ["claude"]}


def test_an_unchanged_record_is_no_change(repo):
    old = json.dumps({"agents": ["claude"], "profiles": {"web": {".mcp.json": {"a": 1}}}}, indent=2) + "\n"
    assert repo_config.record_text(repo, old, "web", {".mcp.json": {"a": 1}}) is None
    assert repo_config.record_text(repo, None, "web", {".mcp.json": {}}) is None


def test_a_layout_loadout_cannot_keep_is_refused(repo):
    with pytest.raises(repo_config.Invalid, match="record of profile web is not written"):
        repo_config.record_text(repo, '{"agents":["claude"]}', "web", {".mcp.json": {"a": 1}})


def test_records_read_the_planned_text_first(repo):
    (repo / ".loadout.json").write_text(json.dumps({"agents": ["claude"]}, indent=2) + "\n")
    w = RepoWrites(repo)
    repo_config.plan_record(repo, w, "web", {".mcp.json": {"a": 1}}, [])
    assert repo_config.records(repo, w) == {"web": {".mcp.json": {"a": 1}}}
    assert repo_config.records(repo) == {}


def test_plan_record_notes_a_layout_it_cannot_keep(repo):
    (repo / ".loadout.json").write_text('{"agents":["claude"]}')
    notes = []
    w = RepoWrites(repo)
    repo_config.plan_record(repo, w, "web", {".mcp.json": {"a": 1}}, notes)
    assert w.changes == [] and "not written" in notes[0]
