"""loadout check names skill links a checkout turned into plain files (spec Part 3)."""
import hashlib

from loadout import check, runner

TARGET = b"../../.claude/skills/demo"
OID = hashlib.sha1(b"blob %d\0" % len(TARGET) + TARGET).hexdigest()


def _repo(tmp_path):
    p = tmp_path / "repo"
    (p / ".git").mkdir(parents=True)
    (p / ".agents" / "skills").mkdir(parents=True)
    (p / ".agents" / "skills" / "demo").write_text("../../.claude/skills/demo")
    return p


def test_check_warns_once_with_the_fix(tmp_path, fake_home, fake_runner, monkeypatch):
    p = _repo(tmp_path)
    (p / "sub").mkdir()
    monkeypatch.chdir(p / "sub")
    fake_runner.responses[("git",)] = runner.Result(0, f"120000 {OID} 0\t.agents/skills/demo\0", "")
    rows = check._repo_skill_links()
    assert len(rows) == 1 and rows[0].severity == "warn" and not rows[0].ok
    assert "1 skill link in .agents/skills is a plain file" in rows[0].detail and str(p) in rows[0].detail
    assert "core.symlinks true" in rows[0].fix and not rows[0].fix.startswith("skill links: ")


def test_no_row_without_a_finding_or_outside_a_repo(tmp_path, fake_home, fake_runner, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert check._repo_skill_links() == []
    p = _repo(tmp_path)
    monkeypatch.chdir(p)
    assert check._repo_skill_links() == []  # git (fake) lists no link


def test_no_row_in_a_home_dotfiles_repo(fake_home, fake_runner, monkeypatch):
    (fake_home / ".git").mkdir()
    (fake_home / ".agents" / "skills").mkdir(parents=True)
    (fake_home / ".agents" / "skills" / "demo").write_text("x")
    fake_runner.responses[("git",)] = runner.Result(0, f"120000 {OID} 0\t.agents/skills/demo\0", "")
    monkeypatch.chdir(fake_home)
    assert check._repo_skill_links() == []


def test_run_checks_includes_the_row(tmp_path, fake_home, fake_runner, monkeypatch):
    p = _repo(tmp_path)
    monkeypatch.chdir(p)
    fake_runner.responses[("git", "-C", str(p), "ls-files")] = runner.Result(0, f"120000 {OID} 0\t.agents/skills/demo\0", "")
    assert any(r.name == "repo skill links" for r in check.run_checks())
