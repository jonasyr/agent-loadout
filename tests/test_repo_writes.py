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


# --- task-3 review fixes ---

def test_restore_keeps_a_user_file_in_a_folder_loadout_created(repo):
    w = repo_writes.RepoWrites(repo)
    w.create(repo / ".claude" / "settings.json", "{}\n", "profile web")
    bk = backup.Backup(description="t", repo=repo)
    assert w.apply(bk) == []
    (repo / ".claude" / "settings.local.json").write_text("mine\n")  # written later by Claude Code or the user
    lines, ok, _ = backup.restore(bk.root)
    assert ok, lines
    assert (repo / ".claude" / "settings.local.json").read_text() == "mine\n"
    assert not (repo / ".claude" / "settings.json").exists()
    assert any("kept" in l and ".claude" in l for l in lines)


def test_restore_removes_an_emptied_created_folder(repo):
    w = repo_writes.RepoWrites(repo)
    w.create(repo / "docs" / "adr" / "README.md", "x\n", "init")
    bk = backup.Backup(description="t", repo=repo)
    w.apply(bk)
    assert backup.restore(bk.root)[1]
    assert not (repo / "docs").exists()


@pytest.mark.parametrize("key", ["DB_PASSWORD", "API_KEY", "token"])
def test_a_generic_secret_value_is_masked_in_the_json_diff(repo, key):
    value = "Zq8xLp2Vt9" * 3
    (repo / ".mcp.json").write_text('{\n  "a": 1\n}\n')
    w = repo_writes.RepoWrites(repo)
    w.modify(repo / ".mcp.json", '{\n  "a": 1,\n  "env": {\n    "%s": "%s"\n  }\n}\n' % (key, value), "profile x")
    w.create(repo / "new.json", '{\n  "%s": "%s"\n}\n' % (key, value), "profile x")
    text = "\n".join(w.render())
    assert value not in text and f"env.{key}" in text


def test_a_secret_in_a_text_diff_line_is_masked(repo):
    (repo / "app.ini").write_text("a = 1\n")
    w = repo_writes.RepoWrites(repo)
    w.modify(repo / "app.ini", "a = 1\npassword = hunter2hunter2x\n", "profile x")
    assert "hunter2hunter2x" not in "\n".join(w.render())


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink")
def test_a_write_through_a_link_leading_outside_the_repo_is_refused(repo, tmp_path):
    outside = tmp_path / "bashrc"
    outside.write_text("mine\n")
    (repo / ".gitignore").symlink_to(outside)
    (repo / "AGENTS.md").symlink_to(tmp_path / "dangling.md")
    (repo / ".claude").symlink_to(tmp_path / "elsewhere", target_is_directory=True)
    (tmp_path / "elsewhere").mkdir()
    w = repo_writes.RepoWrites(repo)
    w.modify(repo / ".gitignore", "x\n", "init")
    w.create(repo / "AGENTS.md", "x\n", "init")
    w.create(repo / ".claude" / "settings.json", "{}\n", "profile")
    problems = w.apply(backup.Backup(description="t", repo=repo))
    assert len(problems) == 3 and all("outside the repo" in p for p in problems)
    assert outside.read_text() == "mine\n" and not (tmp_path / "dangling.md").exists()
    assert list((tmp_path / "elsewhere").iterdir()) == []


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink")
def test_a_failed_link_leaves_no_unrecorded_folder(repo, monkeypatch):
    def refuse(*a, **k):
        raise OSError(1, "no symlink rights")
    monkeypatch.setattr(repo_writes.os, "symlink", refuse)
    w = repo_writes.RepoWrites(repo)
    w.link(repo / ".agents" / "skills" / "pw", "../../.claude/skills/pw", "skill pw")
    bk = backup.Backup(description="t", repo=repo)
    assert any("not linked" in p for p in w.apply(bk))
    backup.restore(bk.root)
    assert not (repo / ".agents").exists()


def test_create_on_a_file_that_appeared_keeps_its_bytes(repo):
    w = repo_writes.RepoWrites(repo)
    w.create(repo / "AGENTS.md", "loadout\n", "init")
    (repo / "AGENTS.md").write_bytes(b"theirs\r\n")  # appeared between plan and apply
    bk = backup.Backup(description="t", repo=repo)
    w.apply(bk)
    assert backup.restore(bk.root)[1]
    assert (repo / "AGENTS.md").read_bytes() == b"theirs\r\n"


def test_modify_on_a_missing_file_creates_it_and_one_failure_does_not_stop_the_rest(repo, tmp_path):
    w = repo_writes.RepoWrites(repo)
    w.modify(repo / ".gitignore", "x\n", "init")
    (repo / ".claude" / "skills" / "pw").mkdir(parents=True)
    w.copytree(tmp_path, repo / ".claude" / "skills" / "pw", "skill pw")  # destination exists now
    w.create(repo / "AGENTS.md", "x\n", "init")
    problems = w.apply(backup.Backup(description="t", repo=repo))
    assert (repo / ".gitignore").read_text() == "x\n" and (repo / "AGENTS.md").exists()
    assert len(problems) == 1 and "exists" in problems[0]


def test_now_mode_redacts_its_error(repo, monkeypatch):
    token = "ghp" + "_" + "a1b2c3d4e5" * 4

    class Res:
        ok, stderr = False, f"bad token {token}"
    monkeypatch.setattr(repo_writes.runner, "run", lambda *a, **k: Res())
    with pytest.raises(OSError) as exc:
        repo_writes.RepoWrites(repo, now=True).run(["tool"], "x")
    assert token not in str(exc.value)
