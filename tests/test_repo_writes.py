"""Repo writes are collected, shown, then applied with a backup that restore undoes (spec Part 0)."""
import os

import pytest

from loadout import backup, repo_writes


@pytest.fixture
def repo(fake_home, tmp_path):
    p = tmp_path / "repo"
    (p / ".git").mkdir(parents=True)
    return p


def test_collecting_changes_nothing(repo):
    w = repo_writes.RepoWrites(repo)
    w.create(repo / "AGENTS.md", "# x\n", "init: instructions every agent reads")
    w.modify(repo / ".gitignore", "a\n", "init")
    assert not (repo / "AGENTS.md").exists() and [c.kind for c in w.changes] == ["create", "modify"]


def test_the_plan_names_each_change_with_its_reason(repo):
    (repo / ".claude").mkdir()
    (repo / ".claude" / "settings.json").write_text('{\n  "a": 1\n}\n')
    w = repo_writes.RepoWrites(repo)
    w.create(repo / "AGENTS.md", "l1\nl2\n", "init: instructions every agent reads")
    w.modify(repo / ".claude" / "settings.json", '{\n  "a": 2,\n  "b": [\n    "x"\n  ]\n}\n', "profile web")
    w.link(repo / ".agents" / "skills" / "pw", "../../.claude/skills/pw", "skill pw for Codex")
    w.run(["playwright-cli", "install", "--skills"], "profile web")
    text = "\n".join(w.render())
    assert "create  AGENTS.md (2 lines)" in text and "init: instructions every agent reads" in text
    assert "change  .claude/settings.json" in text and "~ a: 1 -> 2" in text and '+ b: ["x"]' in text
    assert "link    .agents/skills/pw -> ../../.claude/skills/pw" in text
    assert "run     playwright-cli install --skills" in text and "restore cannot undo" in text


def test_the_plan_redacts_secrets(repo):
    token = "ghp" + "_" + "a1b2c3d4e5" * 4
    w = repo_writes.RepoWrites(repo)
    w.create(repo / ".mcp.json", '{"k": "%s"}\n' % token, "profile x")
    w.run(["tool", f"--token={token}"], "profile x")
    assert token not in "\n".join(w.render())


def test_apply_writes_exactly_the_plan_and_restore_undoes_it(repo):
    (repo / "docs").mkdir()
    (repo / "docs" / "mine.md").write_text("my notes\n")
    (repo / ".gitignore").write_bytes(b"node_modules/\r\n")
    w = repo_writes.RepoWrites(repo)
    w.create(repo / ".claude" / "settings.json", "{}\n", "profile web")
    w.create(repo / "docs" / "README.md", "# docs\n", "init")
    w.modify(repo / ".gitignore", "node_modules/\r\n# loadout\r\n.serena/cache/\r\n", "init")
    bk = backup.Backup(description="t", repo=repo)
    assert w.apply(bk) == []
    assert (repo / ".claude" / "settings.json").read_text() == "{}\n"
    lines, ok, _ = backup.restore(bk.root)
    assert ok, lines
    assert not (repo / ".claude").exists()
    assert (repo / "docs" / "mine.md").read_text() == "my notes\n" and not (repo / "docs" / "README.md").exists()
    assert (repo / ".gitignore").read_bytes() == b"node_modules/\r\n"


def test_the_backup_names_the_repo(repo):
    from loadout.jsonio import load_json
    bk = backup.Backup(description="t", repo=repo)
    w = repo_writes.RepoWrites(repo)
    w.create(repo / "AGENTS.md", "x\n", "init")
    w.apply(bk)
    assert load_json(bk.root / "manifest.json")["repo"] == str(repo)


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink")
def test_a_link_and_a_copied_folder_are_undone(repo, tmp_path):
    src = tmp_path / "skill"
    src.mkdir()
    (src / "SKILL.md").write_text("s\n")
    w = repo_writes.RepoWrites(repo)
    w.copytree(src, repo / ".claude" / "skills" / "pw", "skill pw")
    w.link(repo / ".agents" / "skills" / "pw", "../../.claude/skills/pw", "skill pw for Codex")
    bk = backup.Backup(description="t", repo=repo)
    assert w.apply(bk) == []
    assert (repo / ".agents" / "skills" / "pw" / "SKILL.md").read_text() == "s\n"
    assert backup.restore(bk.root)[1]
    assert not (repo / ".claude").exists() and not (repo / ".agents").exists()


def test_a_run_saves_what_it_touches_first(repo, fake_runner):
    (repo / ".claude").mkdir()
    (repo / ".claude" / "settings.json").write_text("{}\n")
    w = repo_writes.RepoWrites(repo)
    w.run(["claude", "plugin", "install", "x@y", "--scope", "project"], "profile web",
          touches=(repo / ".claude" / "settings.json",))
    bk = backup.Backup(description="t", repo=repo)
    w.apply(bk)
    (repo / ".claude" / "settings.json").write_text('{"enabledPlugins": {"x@y": true}}\n')  # what claude wrote
    assert ["claude", "plugin", "install", "x@y", "--scope", "project"] in fake_runner.calls
    assert backup.restore(bk.root)[1]
    assert (repo / ".claude" / "settings.json").read_text() == "{}\n"


def test_now_mode_writes_at_once(repo):
    w = repo_writes.RepoWrites(repo, now=True)
    w.create(repo / "AGENTS.md", "x\n", "init")
    assert (repo / "AGENTS.md").read_text() == "x\n"
