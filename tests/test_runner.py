import os
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
    monkeypatch.setattr(runner, "_resolve", lambda name: "/winnpm/claude.CMD")

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
    monkeypatch.setattr(runner, "_resolve", lambda name: "/winnpm/claude.cmd")
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


def test_only_the_runner_starts_processes():
    """AGENTS.md: external commands run only through runner; the update restart and the background sync too."""
    import re
    found = []
    for path in sorted((paths.kit_root() / "cli" / "loadout").glob("*.py")):
        if path.name == "runner.py":
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"\b(subprocess\.(Popen|run|call|check_call|check_output)|os\.exec\w*|os\.spawn\w*|os\.system)\(", line):
                found.append(f"{path.name}:{n}")
    assert found == []


def test_continue_in_waits_for_the_windows_child_through_ctrl_c(monkeypatch):
    import pytest
    waits = iter([KeyboardInterrupt, 3])

    class Child:
        def wait(self):
            nxt = next(waits)
            if nxt is KeyboardInterrupt:
                raise KeyboardInterrupt
            return nxt
    seen = []
    monkeypatch.setattr(runner.subprocess, "Popen", lambda cmd, **kw: seen.append(cmd) or Child())
    with pytest.raises(SystemExit) as exc:
        runner.continue_in(["/py", "/kit/bin/loadout", "update"], windows=True, on_error=lambda e: None)
    assert exc.value.code == 3 and seen == [["/py", "/kit/bin/loadout", "update"]]


def test_continue_in_reports_a_launch_that_cannot_start(monkeypatch):
    import pytest

    def boom(exe, cmd):
        raise OSError("no such file")
    monkeypatch.setattr(runner.os, "execv", boom)
    errors = []
    with pytest.raises(SystemExit):
        runner.continue_in(["/py", "/kit/bin/loadout", "update"], windows=False,
                           on_error=lambda e: errors.append(str(e)) or (_ for _ in ()).throw(SystemExit(1)))
    assert errors == ["no such file"]
