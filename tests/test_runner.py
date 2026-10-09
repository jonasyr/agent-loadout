import os
import shutil
import subprocess
import sys

from loadout import paths, runner


def test_run_decodes_utf8_and_replaces_bad_bytes():
    code = "import sys; sys.stdout.buffer.write('\u23fa ok '.encode('utf-8') + b'\\xff')"
    res = runner.run([sys.executable, "-c", code])
    assert res.ok
    assert res.stdout.startswith("\u23fa ok") and "\ufffd" in res.stdout


def test_run_passes_env():
    res = runner.run([sys.executable, "-c", "import os; print(os.environ['LOADOUT_T'])"],
                     env={**os.environ, "LOADOUT_T": "yes"})
    assert res.stdout.strip() == "yes"


def test_windows_cmd_shim_refuses_cmd_metacharacters(monkeypatch):
    monkeypatch.setattr(runner, "_is_windows", lambda: True)
    monkeypatch.setattr(shutil, "which", lambda name: r"C:\npm\claude.CMD")

    def never(*a, **k):
        raise AssertionError("must not run")

    monkeypatch.setattr(subprocess, "run", never)
    secret = "ghp_" + "x" * 30
    res = runner.run(["claude", "mcp", "add-json", "-s", "user", "s", '{"env": {"T": "%s"}}' % secret])
    assert res.returncode == 126
    assert "run manually" in res.stderr and "claude mcp add-json" in res.stderr
    assert secret not in res.stderr


def test_windows_cmd_shim_plain_args_still_run(monkeypatch):
    monkeypatch.setattr(runner, "_is_windows", lambda: True)
    monkeypatch.setattr(shutil, "which", lambda name: r"C:\npm\claude.cmd")
    seen = []
    monkeypatch.setattr(subprocess, "run", lambda argv, **k: (seen.append(argv), subprocess.CompletedProcess(argv, 0, "", ""))[1])
    assert runner.run(["claude", "plugin", "list"]).ok
    assert seen


def test_gitattributes_forces_lf_for_scripts():
    text = (paths.kit_root() / ".gitattributes").read_text(encoding="utf-8")
    for rule in ("*.sh text eol=lf", "bin/loadout text eol=lf", "*.py text eol=lf"):
        assert rule in text


def test_shell_scripts_have_lf_and_exec_bit():
    root = paths.kit_root()
    staged = subprocess.run(["git", "ls-files", "-s"], cwd=root, capture_output=True, text=True).stdout.splitlines()
    modes = {line.split("\t")[1]: line.split()[0] for line in staged}
    for rel in ("bin/loadout", "plugins/loadout/hooks/run.sh", "plugins/loadout/hooks/subagent-context.sh", "bootstrap.sh"):
        assert b"\r" not in (root / rel).read_bytes(), rel
        assert modes[rel] == "100755", rel
