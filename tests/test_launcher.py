import os
import subprocess

import pytest

from loadout import backup, link, paths

pytestmark = pytest.mark.skipif(os.name == "nt", reason="POSIX launcher and run.sh")
RUN_SH = paths.kit_root() / "plugins/loadout/hooks/run.sh"


def _stub(d, name, body):
    f = d / name
    f.write_text("#!/bin/sh\n" + body + "\n")
    f.chmod(0o755)


def _env(stub_dir):
    return {"PATH": f"{stub_dir}:/usr/bin:/bin", "HOME": str(stub_dir)}


def test_link_bin_writes_launcher_and_keeps_user_file_in_backup(fake_home):
    target = fake_home / ".local/bin/loadout"
    target.parent.mkdir(parents=True)
    target.write_text("user script")
    bk = backup.Backup()
    link.link_bin(bk)
    assert link.LAUNCHER_MARKER in target.read_text() and os.access(target, os.X_OK)
    assert not bk.empty
    again = backup.Backup()
    link.link_bin(again)
    assert again.empty  # our own launcher is refreshed without a backup


def test_launcher_uses_python3_when_new_enough(tmp_path):
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    _stub(stubs, "python3", 'case "$1" in -c) exit 0;; esac; echo "python3 $*"')
    _stub(stubs, "uv", 'echo "uv $*"')
    launcher = tmp_path / "loadout"
    launcher.write_text(link.launcher_text(tmp_path / "kit/bin/loadout"))
    launcher.chmod(0o755)
    out = subprocess.run([str(launcher), "check"], env=_env(stubs), capture_output=True, text=True).stdout
    assert out.startswith("python3 ") and out.rstrip().endswith("check")


def test_launcher_falls_back_to_uv_for_old_python(tmp_path):
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    _stub(stubs, "python3", 'case "$1" in -c) exit 1;; esac; echo "python3 $*"')  # 3.9 (macOS)
    _stub(stubs, "uv", 'echo "uv $*"')
    launcher = tmp_path / "loadout"
    launcher.write_text(link.launcher_text(tmp_path / "kit/bin/loadout"))
    launcher.chmod(0o755)
    out = subprocess.run([str(launcher), "check"], env=_env(stubs), capture_output=True, text=True).stdout
    assert out.startswith("uv run --no-project --python >=3.10 ")


@pytest.mark.parametrize("have,expected", [
    ({"python3": 'case "$1" in -c) exit 0;; esac; echo "python3 $*"'}, "python3 "),
    ({"python3": 'case "$1" in -c) exit 1;; esac; echo "python3 $*"', "uv": 'echo "uv $*"'}, "uv run --no-project --python >=3.10 "),
    ({}, ""),
])
def test_run_sh_python(tmp_path, have, expected):
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    for name, body in have.items():
        _stub(stubs, name, body)
    proc = subprocess.run(["/bin/bash", str(RUN_SH), "--soft", "--python", "x.py", "stop"],
                          env={"PATH": str(stubs), "HOME": str(tmp_path)}, capture_output=True, text=True, input="{}")
    assert proc.returncode == 0 and proc.stderr == ""
    assert proc.stdout.startswith(expected) if expected else proc.stdout == ""
