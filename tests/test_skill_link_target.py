"""What Git stores for a skill link loadout creates (spec Part 3): every clone, on every platform, must get a target
with forward slashes. Runs on the Linux, Windows and WSL CI runners."""
import os
import shutil
import subprocess

import pytest

from loadout import profiles, targets

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")


def git(cwd, *args):
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
    return subprocess.run(["git", "-c", "core.symlinks=true", *args], cwd=cwd, env=env, check=True,
                          capture_output=True, text=True).stdout


def test_git_stores_the_link_target_with_forward_slashes(fake_home, tmp_path):
    repo = tmp_path / "repo"
    (repo / ".claude" / "skills" / "demo").mkdir(parents=True)
    (repo / ".claude" / "skills" / "demo" / "SKILL.md").write_text("---\nname: demo\n---\n")
    (repo / ".loadout.json").write_text('{\n  "agents": [\n    "claude",\n    "codex"\n  ]\n}\n')
    git(repo, "init", "-q")
    targets.set_agents({"claude": True, "codex": True})
    lines = profiles.link_skills(repo, False)
    if any("not linked" in l for l in lines):
        pytest.skip(f"no symlink rights here: {lines}")
    git(repo, "add", "-A")
    mode, sha = git(repo, "ls-files", "-s", "--", ".agents/skills/demo").split()[:2]
    assert mode == "120000"
    assert git(repo, "cat-file", "-p", sha) == "../../.claude/skills/demo"
