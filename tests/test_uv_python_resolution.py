"""uv as a Python fallback: never let it discover an interpreter from the open project (a planted .venv).

The stub uv behaves like the real one: `python find` and `run` started inside the project return or run
the project's .venv interpreter; only a `python find` started in `/` returns the good interpreter.
"""
import os
import re
import subprocess
import sys

import pytest

from loadout import link, paths

RUN_SH = paths.kit_root() / "plugins/loadout/hooks/run.sh"
posix = pytest.mark.skipif(os.name == "nt", reason="POSIX launcher and run.sh")


def _exe(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n" + body + "\n")
    path.chmod(0o755)


@pytest.fixture
def planted(tmp_path):
    log = tmp_path / "log"
    proj = tmp_path / "proj"
    _exe(proj / ".venv/bin/python", f'echo "PLANTED $*" >> "{log}"; echo PLANTED')
    (proj / ".venv/pyvenv.cfg").write_text("home = /usr/bin\n")
    good = tmp_path / "good/python"
    _exe(good, f'echo "GOOD $*" >> "{log}"; echo "good $*"')
    stubs = tmp_path / "stubs"
    state = tmp_path / "installed"
    _exe(stubs / "uv", f"""echo "uv $* [cwd=$(pwd)]" >> "{log}"
case "$1 $2" in
  "python find")
    if [ "$(pwd)" = / ]; then [ -f "{state}" ] || [ -z "$NEED_INSTALL" ] && echo "{good}"; exit 0; fi
    echo "{proj}/.venv/bin/python"; exit 0 ;;
  "python install") : > "{state}"; echo "installing python (stdout)"; exit 0 ;;
  "run "*) exec "{proj}/.venv/bin/python" "$@" ;;
esac""")
    return {"log": log, "proj": proj, "good": good, "stubs": stubs}


def _launcher(tmp_path):
    launcher = tmp_path / "loadout"
    launcher.write_text(link.launcher_text(tmp_path / "kit/bin/loadout"))
    launcher.chmod(0o755)
    return launcher


@posix
@pytest.mark.parametrize("need_install", [False, True])
def test_launcher_never_runs_a_planted_venv(tmp_path, planted, need_install):
    env = {"PATH": str(planted["stubs"]), "HOME": str(tmp_path)}
    if need_install:
        env["NEED_INSTALL"] = "1"
    proc = subprocess.run(["/bin/sh", str(_launcher(tmp_path)), "check"], cwd=planted["proj"], env=env,
                          capture_output=True, text=True)
    log = planted["log"].read_text()
    assert "PLANTED" not in log, log
    assert f"GOOD {tmp_path / 'kit/bin/loadout'} check" in log
    finds = [l for l in log.splitlines() if l.startswith("uv python find")]
    assert finds and all(l.endswith("[cwd=/]") for l in finds)
    assert all(l.endswith("[cwd=/]") for l in log.splitlines() if l.startswith("uv "))
    assert ("uv python install" in log) == need_install
    assert proc.stdout == f"good {tmp_path / 'kit/bin/loadout'} check\n"  # install chatter goes to stderr


@posix
@pytest.mark.parametrize("need_install", [False, True])
def test_run_sh_never_runs_a_planted_venv(tmp_path, planted, need_install):
    env = {"PATH": str(planted["stubs"]), "HOME": str(tmp_path)}
    if need_install:
        env["NEED_INSTALL"] = "1"
    proc = subprocess.run(["/bin/bash", str(RUN_SH), "--soft", "--python", "hook.py", "stop"], cwd=planted["proj"],
                          env=env, capture_output=True, text=True, input="{}")
    log = planted["log"].read_text()
    assert "PLANTED" not in log, log
    assert "GOOD hook.py stop" in log
    assert all(l.endswith("[cwd=/]") for l in log.splitlines() if l.startswith("uv "))
    assert proc.returncode == 0 and proc.stdout == "good hook.py stop\n" and proc.stderr == ""  # hook JSON stays clean


@posix
def test_run_sh_skips_the_hook_when_uv_finds_no_python(tmp_path):
    stubs = tmp_path / "stubs"
    _exe(stubs / "uv", "exit 0")  # finds nothing, install does nothing
    proc = subprocess.run(["/bin/bash", str(RUN_SH), "--soft", "--python", "hook.py"], cwd=tmp_path,
                          env={"PATH": str(stubs), "HOME": str(tmp_path)}, capture_output=True, text=True, input="{}")
    assert proc.returncode == 0 and proc.stdout == "" and proc.stderr == ""


def _scripts(tmp_path):
    link.write_windows_shims(tmp_path / "shims")
    return {"launcher": link.launcher_text(tmp_path / "kit/bin/loadout"), "run.sh": RUN_SH.read_text(),
            "loadout.cmd": (tmp_path / "shims/loadout.cmd").read_text(),
            "bootstrap.sh": (paths.kit_root() / "bootstrap.sh").read_text(),
            "bootstrap.ps1": (paths.kit_root() / "bootstrap.ps1").read_text()}


def test_no_entry_point_lets_uv_run_from_the_project(tmp_path):
    for name, text in _scripts(tmp_path).items():
        code = [l for l in text.splitlines() if not l.lstrip().startswith(("#", "rem "))]
        assert not any("uv run" in l for l in code), name
        uv_calls = [l for l in code if re.search(r"\buv python (find|install)\b", l)]
        assert uv_calls, name
        for line in uv_calls:
            assert "--no-config" in line, (name, line)
            if "python find" in line:
                assert "--no-project" in line and "--system" in line, (name, line)


def test_cmd_shim_ignores_the_current_folder(tmp_path):
    lines = _scripts(tmp_path)["loadout.cmd"].splitlines()
    first_call = next(i for i, l in enumerate(lines) if re.search(r"\b(python|uv|where)\b", l, re.IGNORECASE))
    head = [l.strip().lower() for l in lines[:first_call]]
    assert "setlocal" in head and "set nodefaultcurrentdirectoryinexepath=1" in head
    text = "\n".join(lines)
    assert text.index('pushd "%SystemRoot%"') < text.index("uv python find")


@pytest.mark.parametrize("version,code", [((3, 10), 1), ((3, 10, 18, "final", 0), 1), ((3, 11), 0), ((3, 12, 1, "final", 0), 0)])
def test_version_predicates_really_reject_3_9(version, code):
    run_sh = re.search(r"-c '([^']*version_info[^']*)'", RUN_SH.read_text()).group(1)
    for pred in (link.PY_OK, run_sh):
        prog = f"import sys; sys.version_info = {version!r}; exec({pred!r})"
        assert subprocess.run([sys.executable, "-I", "-c", prog]).returncode == code, pred
