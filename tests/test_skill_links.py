"""Committed skill links a checkout turned into plain files (spec Part 3)."""
import hashlib

from loadout import runner, skill_links


def blob(text: str) -> str:
    data = text.encode()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _repo(tmp_path):
    p = tmp_path / "repo"
    (p / ".git").mkdir(parents=True)
    (p / ".agents" / "skills").mkdir(parents=True)
    (p / ".claude" / "skills" / "demo").mkdir(parents=True)
    return p


def test_no_plain_file_means_no_git_call(tmp_path, fake_runner):
    p = _repo(tmp_path)
    (p / ".agents" / "skills" / "real").mkdir()
    assert skill_links.plain_files(p) == set() and fake_runner.calls == []


def test_a_plain_file_git_records_as_a_link_is_found(tmp_path, fake_runner):
    p = _repo(tmp_path)
    (p / ".agents" / "skills" / "demo").write_text("../../.claude/skills/demo")
    (p / ".agents" / "skills" / "mine").write_text("my notes")
    fake_runner.responses[("git",)] = runner.Result(
        0, f"120000 {blob('../../.claude/skills/demo')} 0\t.agents/skills/demo\0" "100644 def 0\t.agents/skills/mine\0", "")
    assert skill_links.plain_files(p) == {".agents/skills/demo"}
    assert fake_runner.calls[0][:3] == ["git", "-C", str(p)] and "-z" in fake_runner.calls[0]


def test_git_failing_or_no_repo_finds_nothing(tmp_path, fake_runner):
    p = _repo(tmp_path)
    (p / ".agents" / "skills" / "demo").write_text("../../.claude/skills/demo")
    fake_runner.responses[("git",)] = runner.Result(128, "", "fatal: not a git repository")
    assert skill_links.plain_files(p) == set()
    (p / ".git").rmdir()
    assert skill_links.plain_files(p) == set()


def test_the_report_counts_per_folder_and_names_the_fix():
    lines = skill_links.report({".agents/skills/a", ".agents/skills/b", ".claude/skills/c"})
    assert lines[0] == ("skill links: 1 skill link in .claude/skills is a plain file in this checkout (Git without "
                        "symlinks), so Claude Code does not see this skill")
    assert lines[1] == ("skill links: 2 skill links in .agents/skills are plain files in this checkout (Git without "
                        "symlinks), so Codex does not see these skills")
    assert "git config core.symlinks true" in lines[2]
    assert 'git checkout -- ".claude/skills/c" ".agents/skills/a" ".agents/skills/b"' in lines[2]
    assert "Developer Mode" in lines[2] and "git checkout -- .claude/skills" not in lines[2]
    assert all(l.startswith(skill_links.PREFIX) for l in lines)


def test_the_fix_names_only_the_folders_with_plain_files():
    assert 'git checkout -- ".agents/skills/a"`' in skill_links.report({".agents/skills/a"})[-1]
    assert skill_links.report(set()) == []


def test_a_file_whose_bytes_are_not_the_link_target_is_not_a_broken_link(tmp_path, fake_runner):
    p = _repo(tmp_path)
    (p / ".agents" / "skills" / "demo").write_text("my own notes, not a link target")
    fake_runner.responses[("git",)] = runner.Result(0, f"120000 {blob('../../.claude/skills/demo')} 0\t.agents/skills/demo\0", "")
    assert skill_links.plain_files(p) == set()


def test_a_crafted_link_name_never_reaches_the_printed_command():
    evil = {'.agents/skills/x"; rm -rf ~; "', ".agents/skills/$(curl evil)", ".agents/skills/ok-name"}
    fix = skill_links.report(evil)[-1]
    command = fix.split("`git checkout -- ", 1)[1].split("`", 1)[0]
    assert command == '".agents/skills/ok-name"'
    assert "rm -rf" not in command and "$(" not in command
    assert "by hand" in fix


def test_only_crafted_names_print_no_command():
    fix = skill_links.report({".agents/skills/$(x)"})[-1]
    assert "git checkout --" not in fix and "by hand" in fix
