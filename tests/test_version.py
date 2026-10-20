"""`loadout --version`: the release from pyproject.toml plus the kit's commit, for bug reports."""
import re

import pytest

from loadout import paths, runner
from loadout.__main__ import build_parser, main

RELEASE = re.search(r'^version = "([^"]+)"', (paths.kit_root() / "pyproject.toml").read_text(encoding="utf-8"), re.M).group(1)


def _version(capsys):
    with pytest.raises(SystemExit) as exit_:
        main(["--version"])
    assert exit_.value.code == 0
    return capsys.readouterr().out.strip()


def test_version_names_the_release_and_the_commit(fake_runner, capsys):
    fake_runner.responses[("git", "-C", str(paths.kit_root()), "rev-parse", "--short", "HEAD")] = runner.Result(0, "abc1234\n", "")
    assert _version(capsys) == f"loadout {RELEASE} (abc1234)"


def test_version_without_git_names_the_release(fake_runner, capsys):
    fake_runner.responses[("git",)] = runner.Result(128, "", "not a git repository")
    assert _version(capsys) == f"loadout {RELEASE}"


def test_building_the_parser_runs_nothing(fake_runner):
    """Hooks call loadout at every session start; the version is looked up only when asked for."""
    build_parser()
    assert fake_runner.calls == []


def test_python_dash_m_registers_every_subcommand(tmp_path):
    """`python -m loadout` runs this module as __main__; the registry must not be a second copy of it."""
    import os, subprocess, sys
    root = paths.kit_root()
    env = {**os.environ, "HOME": str(tmp_path), "USERPROFILE": str(tmp_path), "PYTHONPATH": str(root / "cli"),
           "LOADOUT_UPDATE_PULLED": "1"}
    for name in ("LOADOUT_PERSONAL", "CODEX_HOME", "XDG_STATE_HOME"):
        env.pop(name, None)
    run = lambda *args: subprocess.run([sys.executable, "-m", "loadout", *args], cwd=root / "cli", env=env,
                                       capture_output=True, text=True)
    sub = run("check", "--help")
    assert sub.returncode == 0 and "--verbose" in sub.stdout, sub.stderr
    top = run("--help")
    assert top.returncode == 0 and all(name in top.stdout for name in ("update", "check", "configure"))


def test_the_parser_knows_every_subcommand_without_importing_commands_first():
    assert build_parser().parse_args(["check"]).command == "check"
