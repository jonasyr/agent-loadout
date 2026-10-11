"""bootstrap.sh: checkout detection, one-liner clone, uv install and hand-off (stubs only, no network)."""
import os
import shutil
import subprocess
import sys

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
    # the interpreter uv finds (from / only); it logs like the stubs do
    py = tmp_path / "py/python"
    py.parent.mkdir()
    py.write_text(f'#!/bin/sh\necho "python $* [tty=$([ -t 0 ] && echo yes || echo no)] [pwd=$(pwd)]" >> "{log}"\n')
    py.chmod(0o755)
    uv_ok = f'case "$1 $2" in "python find") [ "$(pwd)" = / ] && echo "{py}";; esac; exit 0'
    return {"stubs": stubs, "home": home, "log": log, "stub": stub, "py": py, "uv_ok": uv_ok,
            "vars": {"HOME": str(home), "PATH": str(stubs)}}


def _run(env, args, cwd, stdin=None):
    return subprocess.run(["/bin/bash", *args], cwd=cwd, env=env["vars"], input=stdin,
                          capture_output=True, text=True, timeout=60)


def test_checkout_hands_off_to_uv_run_without_dir(env, tmp_path):
    env["stub"]("uv", env["uv_ok"])
    kit = tmp_path / "kit"
    (kit / "bin").mkdir(parents=True)
    (kit / "bin/loadout").write_text("")
    shutil.copy(SCRIPT, kit / "bootstrap.sh")
    p = _run(env, [str(kit / "bootstrap.sh"), "--install", "--dir", "/ignored"], cwd=tmp_path)
    assert p.returncode == 0, p.stderr
    log = env["log"].read_text()
    assert "uv python find --system --no-config --no-project >=3.10 [UV_NO_MODIFY_PATH=] [pwd=/]" in log
    assert f"python bin/loadout bootstrap --install [tty=no] [pwd={kit}]" in log and "--dir" not in log


def test_no_arguments_work_on_old_bash(env, tmp_path):
    env["stub"]("uv", env["uv_ok"])
    kit = tmp_path / "kit"
    (kit / "bin").mkdir(parents=True)
    (kit / "bin/loadout").write_text("")
    shutil.copy(SCRIPT, kit / "bootstrap.sh")
    assert _run(env, [str(kit / "bootstrap.sh")], cwd=tmp_path).returncode == 0


def test_installs_uv_without_touching_profiles(env, tmp_path):
    uv = env["home"] / ".local/bin/uv"
    staged = tmp_path / "staged-uv"
    staged.write_text("#!/bin/sh\n" + env["uv_ok"] + "\n")
    staged.chmod(0o755)
    env["stub"]("curl", f'echo "mkdir -p {uv.parent}; cp {staged} {uv}"')
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
    env["stub"]("uv", env["uv_ok"])
    work = tmp_path / "work"
    work.mkdir()
    p = _run(env, ["-s", "--", "--install"], cwd=work, stdin=SCRIPT.read_text())
    assert p.returncode == 0, p.stderr
    assert (work / "agent-loadout/bin/loadout").exists()
    assert f"python bin/loadout bootstrap --install [tty=no] [pwd={work / 'agent-loadout'}]" in env["log"].read_text()


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
    env["stub"]("uv", env["uv_ok"])
    p = _run(env, ["-s"], cwd=work, stdin=SCRIPT.read_text())
    assert p.returncode == 1 and "bin/loadout" not in (env["log"].read_text() if env["log"].exists() else "")


def test_dot_git_origin_reused(env, tmp_path):
    work = tmp_path / "work"
    _fake_clone(work / "agent-loadout")
    _git_stub(env, "https://github.com/jonasyr/agent-loadout.git", (work / "agent-loadout").resolve())
    env["stub"]("uv", env["uv_ok"])
    p = _run(env, ["-s"], cwd=work, stdin=SCRIPT.read_text())
    assert p.returncode == 0, p.stderr
    assert f"pwd={work / 'agent-loadout'}" in env["log"].read_text()


def test_folder_inside_other_repo_refused(env, tmp_path):
    work = tmp_path / "work"
    _fake_clone(work / "agent-loadout")
    _git_stub(env, "https://github.com/jonasyr/agent-loadout", work.resolve())
    env["stub"]("uv", env["uv_ok"])
    assert _run(env, ["-s"], cwd=work, stdin=SCRIPT.read_text()).returncode == 1


def test_one_liner_in_clone_uses_cwd(env, tmp_path):
    work = tmp_path / "work"
    _fake_clone(work)
    _git_stub(env, "https://github.com/jonasyr/agent-loadout", work.resolve())
    env["stub"]("uv", env["uv_ok"])
    p = _run(env, ["-s"], cwd=work, stdin=SCRIPT.read_text())
    assert p.returncode == 0, p.stderr
    assert f"pwd={work}" in env["log"].read_text() and not (work / "agent-loadout").exists()


def test_checkout_keeps_redirected_stdin(env, tmp_path):
    env["stub"]("uv", env["uv_ok"])
    env["py"].write_text(f'#!/bin/sh\nread line; echo "stdin=$line" >> "{env["log"]}"\n')
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


def _piped_clone(env, tmp_path):
    work = tmp_path / "work"
    _fake_clone(work)
    _git_stub(env, "https://github.com/jonasyr/agent-loadout", work.resolve())
    env["stub"]("uv", env["uv_ok"])
    script = tmp_path / "piped.sh"
    script.write_text(SCRIPT.read_text())
    return work, script


@pytest.mark.skipif(not sys.platform.startswith("linux") or not shutil.which("script"), reason="util-linux script(1)")
def test_one_liner_hands_the_terminal_to_bootstrap(env, tmp_path):
    """curl | bash: stdin is the script, so bootstrap must get /dev/tty to ask its questions."""
    work, script = _piped_clone(env, tmp_path)
    p = subprocess.run([shutil.which("script"), "-qec", f"/bin/bash -s -- --install < {script}", "/dev/null"],
                       cwd=work, env={**env["vars"], "SHELL": "/bin/sh"}, capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "python bin/loadout bootstrap --install [tty=yes]" in env["log"].read_text()


@pytest.mark.skipif(not shutil.which("setsid"), reason="needs setsid")
def test_one_liner_without_a_terminal_runs_non_interactively(env, tmp_path):
    work, script = _piped_clone(env, tmp_path)
    with open(script) as stdin:
        p = subprocess.run([shutil.which("setsid"), "-w", "/bin/bash", "-s", "--", "--install"], cwd=work,
                           env=env["vars"], stdin=stdin, capture_output=True, text=True, timeout=60)
    assert p.returncode == 0 and "tty" not in p.stderr, p.stderr
    assert "python bin/loadout bootstrap --install [tty=no]" in env["log"].read_text()


def test_tty_hand_off_is_guarded():
    text = SCRIPT.read_text()
    assert 'if [ "$piped" = 1 ] && [ ! -t 0 ] && { : </dev/tty; } 2>/dev/null; then' in text
    assert 'exec "${run[@]}" </dev/tty' in text


def test_cut_off_download_runs_nothing(env, tmp_path):
    env["stub"]("git", "exit 0")
    env["stub"]("uv", env["uv_ok"])
    env["stub"]("curl", "exit 0")
    text = SCRIPT.read_text()
    work = tmp_path / "work"
    work.mkdir()
    for cut in ('export PATH="$HOME/.local/bin', 'cd "$kit"'):
        p = _run(env, ["-s", "--", "--install"], cwd=work, stdin=text[:text.index(cut)])
        assert p.returncode != 0
        assert not env["log"].exists(), env["log"].read_text()
        assert not (work / "agent-loadout").exists()
    assert text.rstrip().splitlines()[-1] == 'main "$@"'


def test_missing_curl_is_explained(env, tmp_path):
    kit = tmp_path / "kit"
    _fake_clone(kit)
    shutil.copy(SCRIPT, kit / "bootstrap.sh")
    p = _run(env, [str(kit / "bootstrap.sh")], cwd=tmp_path)
    assert p.returncode == 1
    assert "loadout needs curl to download uv. Install it, then run this again:" in p.stderr
    if sys.platform.startswith("linux"):
        assert "sudo apt install curl" in p.stderr


def test_python_is_installed_from_a_neutral_folder_when_uv_has_none(env, tmp_path):
    state = tmp_path / "installed"
    env["stub"]("uv", f'case "$1 $2" in "python install") : > "{state}";; '
                      f'"python find") [ -f "{state}" ] && [ "$(pwd)" = / ] && echo "{env["py"]}";; esac; exit 0')
    kit = tmp_path / "kit"
    _fake_clone(kit)
    shutil.copy(SCRIPT, kit / "bootstrap.sh")
    p = _run(env, [str(kit / "bootstrap.sh")], cwd=tmp_path)
    assert p.returncode == 0, p.stderr
    log = env["log"].read_text()
    assert "uv python install --no-config >=3.10 [UV_NO_MODIFY_PATH=] [pwd=/]" in log
    assert f"python bin/loadout bootstrap [tty=no] [pwd={kit}]" in log
