"""The repo writers plan their changes, keep the user's bytes, and follow the repo's agents (spec Parts 0, 1)."""
import json

import pytest

from loadout import profiles, repo_writes, scaffold, targets


@pytest.fixture
def repo(fake_home, tmp_path):
    p = tmp_path / "repo"
    (p / ".git").mkdir(parents=True)
    return p


def _web():
    return profiles.Profile(name="web", description="Web UI", settings={"disabledMcpjsonServers": ["cd"]},
                            mcp={"mcpServers": {"cd": {"command": "npx"}}}, why={"settings.disabledMcpjsonServers": "off until needed"})


def test_planning_writes_nothing(repo):
    targets.set_agents({"claude": True, "codex": True})
    w = repo_writes.RepoWrites(repo)
    scaffold.scaffold(repo, w=w)
    scaffold.ensure_gitignore(repo, w=w)
    profiles.apply_profile(_web(), repo, w=w)
    assert sorted(p.name for p in repo.iterdir()) == [".git"]
    kinds = {(c.kind, c.path.relative_to(repo).as_posix()) for c in w.changes}
    assert ("create", "AGENTS.md") in kinds and ("create", ".claude/settings.json") in kinds and ("create", ".gitignore") in kinds


def test_the_reason_names_the_profile_and_its_why(repo):
    targets.set_agents({"claude": True, "codex": False})
    w = repo_writes.RepoWrites(repo)
    profiles.apply_profile(_web(), repo, w=w)
    assert any("profile web" in c.why and "off until needed" in c.why for c in w.changes)


@pytest.mark.parametrize("indent, nl", [(4, "\r\n"), ("\t", "\n")])
def test_a_profile_keeps_the_files_layout(repo, indent, nl):
    targets.set_agents({"claude": True, "codex": False})
    (repo / ".claude").mkdir()
    before = (json.dumps({"model": "x"}, indent=indent) + "\n").replace("\n", nl)
    (repo / ".claude" / "settings.json").write_bytes(before.encode())
    profiles.apply_profile(_web(), repo)
    after = (repo / ".claude" / "settings.json").read_bytes().decode()
    assert after == (json.dumps({"model": "x", "disabledMcpjsonServers": ["cd"]}, indent=indent) + "\n").replace("\n", nl)


def test_a_hand_laid_out_file_is_left_and_its_entries_named(repo):
    targets.set_agents({"claude": True, "codex": False})
    (repo / ".claude").mkdir()
    (repo / ".claude" / "settings.json").write_text('{"model":"x"}\n')
    changed, skipped = profiles.apply_profile(_web(), repo)
    assert (repo / ".claude" / "settings.json").read_text() == '{"model":"x"}\n'
    assert any(".claude/settings.json" in l and "by hand" in l and "disabledMcpjsonServers" in l for l in skipped)


def test_a_no_op_run_does_not_touch_the_file(repo):
    targets.set_agents({"claude": True, "codex": False})
    profiles.apply_profile(_web(), repo)
    path = repo / ".claude" / "settings.json"
    stamp = path.stat().st_mtime_ns
    w = repo_writes.RepoWrites(repo)
    profiles.apply_profile(_web(), repo, w=w)
    assert not [c for c in w.changes if c.path == path] and path.stat().st_mtime_ns == stamp


def test_gitignore_gets_one_header(repo):
    targets.set_agents({"claude": False, "codex": True})
    scaffold.ensure_gitignore(repo)
    targets.set_agents({"claude": True, "codex": True})
    scaffold.ensure_gitignore(repo)
    text = (repo / ".gitignore").read_text()
    assert text.count("# loadout") == 1 and ".claude/settings.local.json" in text and text.index("# loadout") < text.index(".claude/")


def test_gitignore_keeps_crlf(repo):
    (repo / ".gitignore").write_bytes(b"node_modules/\r\n")
    scaffold.ensure_gitignore(repo)
    assert b"\n" not in (repo / ".gitignore").read_bytes().replace(b"\r\n", b"")


def test_the_repos_agents_win_over_the_users(repo):
    targets.set_agents({"claude": True, "codex": True})
    (repo / ".loadout.json").write_text('{\n  "agents": [\n    "codex"\n  ]\n}\n')
    w = repo_writes.RepoWrites(repo)
    scaffold.scaffold(repo, w=w)
    profiles.apply_profile(_web(), repo, w=w)
    written = {c.path.relative_to(repo).as_posix() for c in w.changes}
    assert "CLAUDE.md" not in written and ".claude/settings.json" not in written and ".mcp.json" not in written
    assert profiles.repo_off_notes(_web(), repo) == [
        ".claude/settings.json and .mcp.json: not written, this repo is for Codex only (.loadout.json; "
        "add Claude Code with loadout init --agents claude,codex)"]


def test_a_codex_only_user_writes_claude_files_in_a_both_agents_repo(repo):
    targets.set_agents({"claude": False, "codex": True})
    (repo / ".loadout.json").write_text('{\n  "agents": [\n    "claude",\n    "codex"\n  ]\n}\n')
    profiles.apply_profile(_web(), repo)
    assert (repo / ".claude" / "settings.json").is_file() and (repo / ".mcp.json").is_file()
    assert profiles.repo_skill_dirs(repo) == (repo / ".claude" / "skills", repo / ".agents" / "skills")


# --- task-4 review fixes ---

def test_a_hand_laid_out_file_that_already_has_the_entries_is_quiet(repo):
    targets.set_agents({"claude": True, "codex": False})
    (repo / ".claude").mkdir()
    (repo / ".claude" / "settings.json").write_text('{"disabledMcpjsonServers": ["cd"]}\n')
    prof = profiles.Profile(name="web", description="", settings={"disabledMcpjsonServers": ["cd"]})
    assert profiles.apply_profile(prof, repo) == ([], [])


def test_the_add_by_hand_line_names_keys_not_values(repo):
    targets.set_agents({"claude": True, "codex": False})
    secret = "sk-" + "Zq8xLp2Vt9" * 3
    (repo / ".mcp.json").write_text('{"mcpServers":{}}\n')
    prof = profiles.Profile(name="db", description="", mcp={"mcpServers": {"db": {"env": {"API_KEY": secret}}}})
    _, skipped = profiles.apply_profile(prof, repo)
    assert skipped and secret not in "\n".join(skipped) and "mcpServers.db.env.API_KEY" in skipped[0]


def test_a_failed_link_in_now_mode_is_reported_not_raised(repo, monkeypatch):
    from loadout import repo_writes
    targets.set_agents({"claude": True, "codex": True})
    (repo / ".claude" / "skills" / "pw").mkdir(parents=True)
    monkeypatch.setattr(repo_writes.os, "symlink", lambda *a, **k: (_ for _ in ()).throw(OSError(1, "no rights")))
    lines = profiles.link_skills(repo, False, w=repo_writes.RepoWrites(repo, now=True))
    assert any("not linked for Codex" in l for l in lines)


def test_gitignore_with_mixed_endings_keeps_each_line(repo):
    (repo / ".gitignore").write_bytes(b"a\r\nb\n")
    scaffold.ensure_gitignore(repo)
    assert (repo / ".gitignore").read_bytes().startswith(b"a\r\nb\n")


def _plugins_profile():
    return profiles.Profile(name="thesis", description="", install=["a@m", "b@m"])


def test_a_repo_not_for_claude_names_the_plugins_it_skips(repo):
    targets.set_agents({"claude": True, "codex": True})
    (repo / ".loadout.json").write_text('{\n  "agents": [\n    "codex"\n  ]\n}\n')
    assert profiles.repo_off_notes(_plugins_profile(), repo) == []
    assert profiles.repo_off_notes(_plugins_profile(), repo, install=True) == [
        "skipped for this repo (not for Claude Code): plugin a@m, plugin b@m"]


def test_the_plan_names_the_skipped_plugins(repo, monkeypatch, capsys):
    from loadout import project
    targets.set_agents({"claude": True, "codex": True})
    (repo / ".loadout.json").write_text('{\n  "agents": [\n    "codex"\n  ]\n}\n')
    monkeypatch.setattr(profiles, "load_profile", lambda name: _plugins_profile())
    assert project.add_profile(repo, "thesis", install=True, dry_run=True) == 0
    assert "skipped for this repo (not for Claude Code): plugin a@m, plugin b@m" in capsys.readouterr().out
