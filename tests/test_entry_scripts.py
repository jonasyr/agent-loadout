"""bootstrap.sh: checkout detection, one-liner clone, uv install and hand-off (stubs only, no network)."""
import os
import shutil
import subprocess

import pytest

from loadout import paths

pytestmark = pytest.mark.skipif(os.name == "nt", reason="bash entry script")
SCRIPT = paths.kit_root() / "bootstrap.sh"


@pytest.fixture
def env(tmp_path):
    stubs, home = tmp_path / "stubs", tmp_path / "home"
    stubs.mkdir()
    home.mkdir()
    log = tmp_path / "log"

    def stub(name, body):
        f = stubs / name
        f.write_text(f'#!/bin/sh\necho "{name} $* [UV_NO_MODIFY_PATH=$UV_NO_MODIFY_PATH] [pwd=$(pwd)]" >> "{log}"\n{body}\n')
        f.chmod(0o755)

    for tool in ("dirname", "uname", "grep", "cat", "mkdir", "cp", "chmod"):
        if shutil.which(tool):
            (stubs / tool).symlink_to(shutil.which(tool))
    return {"stubs": stubs, "home": home, "log": log, "stub": stub,
            "vars": {"HOME": str(home), "PATH": str(stubs)}}


def _run(env, args, cwd, stdin=None):
    return subprocess.run(["/bin/bash", *args], cwd=cwd, env=env["vars"], input=stdin,
                          capture_output=True, text=True, timeout=60)


def test_checkout_hands_off_to_uv_run_without_dir(env, tmp_path):
    env["stub"]("uv", "exit 0")
    kit = tmp_path / "kit"
    (kit / "bin").mkdir(parents=True)
    (kit / "bin/loadout").write_text("")
    shutil.copy(SCRIPT, kit / "bootstrap.sh")
    p = _run(env, [str(kit / "bootstrap.sh"), "--install", "--dir", "/ignored"], cwd=tmp_path)
    assert p.returncode == 0, p.stderr
    log = env["log"].read_text()
    assert "uv run --no-project --no-config --python >=3.10 bin/loadout bootstrap --install" in log
    assert f"pwd={kit}" in log and "--dir" not in log


def test_no_arguments_work_on_old_bash(env, tmp_path):
    env["stub"]("uv", "exit 0")
    kit = tmp_path / "kit"
    (kit / "bin").mkdir(parents=True)
    (kit / "bin/loadout").write_text("")
    shutil.copy(SCRIPT, kit / "bootstrap.sh")
    assert _run(env, [str(kit / "bootstrap.sh")], cwd=tmp_path).returncode == 0


def test_installs_uv_without_touching_profiles(env, tmp_path):
    uv = env["home"] / ".local/bin/uv"
    env["stub"]("curl", f'printf "mkdir -p {uv.parent}; printf \'#!/bin/sh\\\\nexit 0\\\\n\' > {uv}; chmod +x {uv}\\n"')
    env["stub"]("sh", 'exec /bin/sh "$@"')
    kit = tmp_path / "kit"
    (kit / "bin").mkdir(parents=True)
    (kit / "bin/loadout").write_text("")
    shutil.copy(SCRIPT, kit / "bootstrap.sh")
    p = _run(env, [str(kit / "bootstrap.sh")], cwd=tmp_path)
    assert p.returncode == 0, p.stderr
    assert "curl -LsSf https://astral.sh/uv/install.sh" in env["log"].read_text()
    assert "[UV_NO_MODIFY_PATH=1]" in env["log"].read_text()
    assert uv.exists()


def test_one_liner_clones_into_cwd(env, tmp_path):
    fake_kit = tmp_path / "upstream"
    (fake_kit / "bin").mkdir(parents=True)
    (fake_kit / "bin/loadout").write_text("")
    env["stub"]("git", f'case "$1" in clone) cp -r "{fake_kit}" "$4";; esac; exit 0')
    env["stub"]("uv", "exit 0")
    work = tmp_path / "work"
    work.mkdir()
    p = _run(env, ["-s", "--", "--install"], cwd=work, stdin=SCRIPT.read_text())
    assert p.returncode == 0, p.stderr
    assert (work / "agent-loadout/bin/loadout").exists()
    assert f"pwd={work / 'agent-loadout'}" in env["log"].read_text()
    assert "--install" in env["log"].read_text()


def test_one_liner_without_git_explains_and_stops(env, tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    p = _run(env, ["-s"], cwd=work, stdin=SCRIPT.read_text())
    assert p.returncode == 1
    assert "git" in p.stderr and ("apt install git" in p.stderr or "xcode-select" in p.stderr)


def test_one_liner_refuses_foreign_target(env, tmp_path):
    env["stub"]("git", 'case "$*" in *"remote get-url origin"*) echo https://example.com/other.git;; esac; exit 0')
    work = tmp_path / "work"
    (work / "agent-loadout").mkdir(parents=True)
    p = _run(env, ["-s"], cwd=work, stdin=SCRIPT.read_text())
    assert p.returncode == 1 and "agent-loadout" in p.stderr


def _git_stub(env, origin, top):
    env["stub"]("git", f'case "$*" in *"remote get-url"*) echo {origin};; *"rev-parse --show-toplevel"*) echo "{top}";; esac; exit 0')


def _fake_clone(path):
    (path / "bin").mkdir(parents=True)
    (path / "bin/loadout").write_text("")


def test_lookalike_origin_refused(env, tmp_path):
    work = tmp_path / "work"
    _fake_clone(work / "agent-loadout")
    _git_stub(env, "https://evil.example/jonasyr/agent-loadout-x", work / "agent-loadout")
    env["stub"]("uv", "exit 0")
    p = _run(env, ["-s"], cwd=work, stdin=SCRIPT.read_text())
    assert p.returncode == 1 and "uv run" not in (env["log"].read_text() if env["log"].exists() else "")


def test_dot_git_origin_reused(env, tmp_path):
    work = tmp_path / "work"
    _fake_clone(work / "agent-loadout")
    _git_stub(env, "https://github.com/jonasyr/agent-loadout.git", (work / "agent-loadout").resolve())
    env["stub"]("uv", "exit 0")
    p = _run(env, ["-s"], cwd=work, stdin=SCRIPT.read_text())
    assert p.returncode == 0, p.stderr
    assert f"pwd={work / 'agent-loadout'}" in env["log"].read_text()


def test_folder_inside_other_repo_refused(env, tmp_path):
    work = tmp_path / "work"
    _fake_clone(work / "agent-loadout")
    _git_stub(env, "https://github.com/jonasyr/agent-loadout", work.resolve())
    env["stub"]("uv", "exit 0")
    assert _run(env, ["-s"], cwd=work, stdin=SCRIPT.read_text()).returncode == 1


def test_one_liner_in_clone_uses_cwd(env, tmp_path):
    work = tmp_path / "work"
    _fake_clone(work)
    _git_stub(env, "https://github.com/jonasyr/agent-loadout", work.resolve())
    env["stub"]("uv", "exit 0")
    p = _run(env, ["-s"], cwd=work, stdin=SCRIPT.read_text())
    assert p.returncode == 0, p.stderr
    assert f"pwd={work}" in env["log"].read_text() and not (work / "agent-loadout").exists()


def test_checkout_keeps_redirected_stdin(env, tmp_path):
    env["stub"]("uv", 'read line; echo "stdin=$line" >> "$(dirname "$0")/../log"')
    kit = tmp_path / "kit"
    _fake_clone(kit)
    shutil.copy(SCRIPT, kit / "bootstrap.sh")
    p = _run(env, [str(kit / "bootstrap.sh")], cwd=tmp_path, stdin="hello\n")
    assert p.returncode == 0, p.stderr
    assert "stdin=hello" in env["log"].read_text()


def test_uv_install_failure_is_explained(env, tmp_path):
    env["stub"]("curl", "exit 1")
    env["stub"]("sh", "exit 0")
    kit = tmp_path / "kit"
    _fake_clone(kit)
    shutil.copy(SCRIPT, kit / "bootstrap.sh")
    p = _run(env, [str(kit / "bootstrap.sh")], cwd=tmp_path)
    assert p.returncode == 1 and "could not install uv" in p.stderr
