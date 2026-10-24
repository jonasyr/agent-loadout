"""tests/conftest.py's guard: a test cannot run a real program through runner.run (AGENTS.md: no real claude, codex
or installers in tests); fake_runner, stubs in tmp_path and a few harmless programs still work."""
import os
import shutil
import tempfile

import pytest

from loadout import runner

pytestmark = pytest.mark.skipif(os.name == "nt", reason="stub executables are shell scripts")


def _stub(folder, name="claude"):
    path = os.path.join(folder, name)
    with open(path, "w") as fh:
        fh.write("#!/bin/sh\necho stub\n")
    os.chmod(path, 0o755)
    return path


def test_a_real_program_outside_the_test_folders_fails_the_test():
    outside = tempfile.mkdtemp(prefix="loadout-real-")  # not under pytest's base temp: stands for ~/.local/bin
    try:
        with pytest.raises(pytest.fail.Exception, match="ran the real `claude`"):
            runner.run([_stub(outside)])
    finally:
        shutil.rmtree(outside)


def test_a_stub_in_tmp_path_runs(tmp_path):
    res = runner.run([_stub(str(tmp_path))])
    assert res.ok and res.stdout.strip() == "stub"


def test_a_made_up_path_is_not_a_real_program(monkeypatch):
    monkeypatch.setattr(runner, "_resolve", lambda binary: "/no/such/dir/codex")
    assert runner.run(["codex", "--version"]).returncode in (126, 127)  # it cannot start: nothing real ran


def test_harmless_programs_run():
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    assert runner.run(["git", "--version"]).ok


def test_fake_runner_steps_the_guard_aside(fake_runner):
    assert runner.run(["codex", "plugin", "list"]).ok and fake_runner.calls == [["codex", "plugin", "list"]]


@pytest.mark.parametrize("cmd", [["python", "-m", "pip", "install", "x"], ["python", "tool.py"],
                                 ["python", "-c", "import subprocess; subprocess.run(['claude'])"],
                                 ["python", "-c", "import os; os.system('codex')"]])
def test_python_may_only_run_inline_code_that_starts_nothing(cmd):
    with pytest.raises(pytest.fail.Exception, match="ran the real `python`"):
        runner.run(cmd)


def test_python_inline_code_runs():
    assert runner.run(["python", "-c", "print('ok')"]).stdout.strip() == "ok"


def test_cmd_may_only_echo(monkeypatch):
    monkeypatch.setattr(runner, "_resolve", lambda binary: shutil.which("sh"))  # a real program named cmd
    with pytest.raises(pytest.fail.Exception, match="ran the real `cmd`"):
        runner.run(["cmd", "/c", "claude", "plugin", "list"])
