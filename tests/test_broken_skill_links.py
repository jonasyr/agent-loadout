"""A checkout without symlinks: profile and init report the plain files once and exit 0 (spec Part 3).
Real git in throwaway repos; the user's git config is switched off."""
import os
import shutil
import subprocess

import pytest

from loadout import profiles, project, targets

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")


def git(cwd, *args):
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout


@pytest.fixture(autouse=True)
def only_git_runs(monkeypatch):
    """The real runner, for git only: any other command (claude, codex, an installer) fails the test."""
    from loadout import runner
    real = runner.run

    def run(cmd, *a, **k):
        if cmd[0] != "git":
            raise AssertionError(f"a test may not run {cmd[0]}")
        return real(cmd, *a, **k)
    monkeypatch.setattr(runner, "run", run)


@pytest.fixture
def clone(fake_home, tmp_path, monkeypatch):
    """A both-agents repo with a committed .agents/skills/demo link, cloned with core.symlinks=false."""
    origin = tmp_path / "origin"
    (origin / ".claude" / "skills" / "demo").mkdir(parents=True)
    (origin / ".claude" / "skills" / "demo" / "SKILL.md").write_text("---\nname: demo\n---\n")
    (origin / ".agents" / "skills").mkdir(parents=True)
    try:
        os.symlink(os.path.join("..", "..", ".claude", "skills", "demo"), origin / ".agents" / "skills" / "demo",
                   target_is_directory=True)
    except OSError:
        pytest.skip("no symlink rights here")
    (origin / ".loadout.json").write_text('{\n  "agents": [\n    "claude",\n    "codex"\n  ]\n}\n')
    git(origin, "init", "-q")
    git(origin, "-c", "core.symlinks=true", "add", "-A")
    git(origin, "commit", "-qm", "init")
    dest = tmp_path / "clone"
    git(tmp_path, "-c", "core.symlinks=false", "clone", "-q", str(origin), str(dest))
    assert (dest / ".agents" / "skills" / "demo").is_file()
    targets.set_agents({"claude": True, "codex": True})
    monkeypatch.setattr(profiles, "load_profile", lambda n: profiles.Profile(name=n, description="d", settings={"x": 1}))
    return dest


def test_profile_reports_the_plain_file_once_and_exits_0(clone, capsys):
    before = (clone / ".agents" / "skills" / "demo").read_bytes()
    assert project.add_profile(clone, "web", install=False, approve=lambda plan: True) == 0
    printed = capsys.readouterr().out
    plan, _, report = printed.partition("Profile web")  # notes show in the plan, then again in the report
    assert plan.count("1 skill link in .agents/skills is a plain file") == 1
    assert report.count("1 skill link in .agents/skills is a plain file") <= 1
    assert "core.symlinks true" in printed and "left as is" not in printed
    assert (clone / ".agents" / "skills" / "demo").read_bytes() == before


def test_init_with_two_profiles_reports_it_once(clone, capsys):
    assert project.init(clone, ["a", "b"], yes=True, install=False, dry_run=False, ask=lambda q: "",
                        interactive=False) == 0
    plan, _, report = capsys.readouterr().out.partition("Init ")
    assert plan.count("is a plain file in this checkout") == 1 and report.count("is a plain file in this checkout") <= 1


def test_the_library_path_reports_it_too(clone, capsys):
    assert project.add_profile(clone, "web", install=False) == 0
    assert "is a plain file in this checkout" in capsys.readouterr().out


def test_a_plain_file_git_does_not_record_as_a_link_still_fails(clone, capsys):
    mine = clone / ".agents" / "skills" / "other"
    (clone / ".claude" / "skills" / "other").mkdir()
    mine.write_text("my own file")
    assert project.add_profile(clone, "web", install=False, approve=lambda plan: True) == 1
    assert "left as is" in capsys.readouterr().out and mine.read_text() == "my own file"


def test_a_file_put_at_a_committed_links_place_is_not_a_broken_checkout(fake_home, tmp_path, monkeypatch, capsys):
    origin = tmp_path / "origin"
    (origin / ".claude" / "skills" / "demo").mkdir(parents=True)
    (origin / ".agents" / "skills").mkdir(parents=True)
    link = origin / ".agents" / "skills" / "demo"
    try:
        os.symlink(os.path.join("..", "..", ".claude", "skills", "demo"), link, target_is_directory=True)
    except OSError:
        pytest.skip("no symlink rights here")
    (origin / ".claude" / "skills" / "demo" / "SKILL.md").write_text("x")
    (origin / ".loadout.json").write_text('{\n  "agents": [\n    "claude",\n    "codex"\n  ]\n}\n')
    git(origin, "init", "-q")
    git(origin, "-c", "core.symlinks=true", "add", "-A")
    git(origin, "commit", "-qm", "init")
    link.unlink()
    link.write_text("my own file")  # a person's choice, not Git without symlinks
    targets.set_agents({"claude": True, "codex": True})
    monkeypatch.setattr(profiles, "load_profile", lambda n: profiles.Profile(name=n, description="d", settings={"x": 1}))
    assert project.add_profile(origin, "web", install=False, approve=lambda plan: True) == 1
    printed = capsys.readouterr().out
    assert "left as is" in printed and "plain file in this checkout" not in printed and link.read_text() == "my own file"
