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

    for tool in ("dirname", "uname", "grep", "cat", "mkdir", "cp", "chmod", "date", "rm"):
        if shutil.which(tool):
            (stubs / tool).symlink_to(shutil.which(tool))
    # the interpreter uv finds (from / only); it logs like the stubs do
    py = tmp_path / "py/python"
    py.parent.mkdir()
    py.write_text(f'#!/bin/sh\necho "python $* [tty=$([ -t 0 ] && echo yes || echo no)] [pwd=$(pwd)]" >> "{log}"\n')
    py.chmod(0o755)
    uv_ok = f'case "$1 $2" in "python find") [ "$(pwd)" = / ] && echo "{py}";; esac; exit 0'
    return {"stubs": stubs, "home": home, "log": log, "stub": stub, "py": py, "uv_ok": uv_ok,
            "vars": {"HOME": str(home), "PATH": str(stubs), "LOADOUT_REF": "main"}}


def _run(env, args, cwd, stdin=None):
    # a new session has no controlling terminal, whether pytest runs in one or not
    return subprocess.run(["/bin/bash", *args], cwd=cwd, env=env["vars"], input=stdin, start_new_session=True,
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
    assert "uv python find --system --no-config --no-project >=3.11 [UV_NO_MODIFY_PATH=] [pwd=/]" in log
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


@pytest.mark.skipif(not hasattr(os, "openpty"), reason="needs a pseudo-terminal")
def test_one_liner_hands_the_terminal_to_bootstrap(env, tmp_path):
    """curl | bash: stdin is the script, so bootstrap must get /dev/tty to ask its questions."""
    import fcntl
    import termios
    import threading
    work, script = _piped_clone(env, tmp_path)
    master, slave = os.openpty()

    def drain():  # macOS: a full pty buffer blocks the writer, and its exit waits for the output to drain
        try:
            while os.read(master, 4096):
                pass
        except OSError:
            pass
    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    try:
        with open(script) as stdin:
            # stdin is the script; the pseudo-terminal becomes the controlling terminal of a new session
            p = subprocess.run(["/bin/bash", "-s", "--", "--install"], cwd=work, env=env["vars"], stdin=stdin,
                               stdout=slave, stderr=slave, start_new_session=True, timeout=60,
                               preexec_fn=lambda: fcntl.ioctl(1, termios.TIOCSCTTY, 0))
    finally:
        os.close(slave)  # the reader then gets EIO (or EOF) and ends
        reader.join(timeout=5)
        os.close(master)
    assert p.returncode == 0
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
    assert "uv python install --no-config >=3.11 [UV_NO_MODIFY_PATH=] [pwd=/]" in log
    assert f"python bin/loadout bootstrap [tty=no] [pwd={kit}]" in log


def test_uv_install_creates_local_bin_owner_writable_only(env, tmp_path):
    """Ubuntu's umask 002 would make it group-writable, and codebase-memory-mcp refuses to install there."""
    uv = env["home"] / ".local/bin/uv"
    staged = tmp_path / "staged-uv"
    staged.write_text("#!/bin/sh\n" + env["uv_ok"] + "\n")
    staged.chmod(0o755)
    env["stub"]("curl", f'echo "mkdir -p {uv.parent}; cp {staged} {uv}"')
    env["stub"]("sh", 'exec /bin/sh "$@"')
    kit = tmp_path / "kit"
    _fake_clone(kit)
    shutil.copy(SCRIPT, kit / "bootstrap.sh")
    p = subprocess.run(["/bin/sh", "-c", 'umask 002; exec /bin/bash "$0"', str(kit / "bootstrap.sh")], cwd=tmp_path,
                       env=env["vars"], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    assert (env["home"] / ".local/bin").stat().st_mode & 0o777 == 0o755


# --- release channels: the newest soaked annotated tag, never main, on stable ---

def _git(repo, *args, days=None):
    e = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null",
         "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
         "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
    if days is not None:
        import time
        e["GIT_AUTHOR_DATE"] = e["GIT_COMMITTER_DATE"] = f"@{int(time.time() - days * 86400)} +0000"
    subprocess.run(["git", "-C", str(repo), *args], env=e, check=True, capture_output=True)


def _release_repo(tmp_path, tags):
    """tags: [(name, annotated, age in days)] in order; each tag has its own commit, VERSION says which."""
    repo = tmp_path / "upstream"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "bin").mkdir()
    (repo / "bin/loadout").write_text("")
    for name, annotated, days in [*tags, ("main", False, 0)]:
        (repo / "VERSION").write_text(name)
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", name, days=days)
        if name != "main":
            _git(repo, "tag", *(["-a", name, "-m", name] if annotated else [name]), days=days)
    return repo


def _stable_env(env, repo):
    (env["stubs"] / "git").symlink_to(shutil.which("git"))
    env["stub"]("uv", env["uv_ok"])
    env["vars"].pop("LOADOUT_REF", None)
    env["vars"]["LOADOUT_REPO_URL"] = str(repo)
    env["vars"]["GIT_CONFIG_GLOBAL"] = "/dev/null"


def _piped(env, tmp_path, *args):
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    p = _run(env, ["-s", "--", *args], cwd=work, stdin=SCRIPT.read_text())
    return p, work / "agent-loadout"


MIXED = [("v0.1.9", True, 40), ("v0.2.0", True, 20), ("v0.2.1", False, 10), ("v0.9.0", True, 6),
         ("v0.10.0", True, 4), ("v0.11.0", True, 0)]


def test_sh_picks_newest_soaked_annotated_tag(env, tmp_path):
    repo = _release_repo(tmp_path, [("v0.1.0", False, 30), ("v0.2.0", True, 5), ("v0.3.0", True, 0)])
    _stable_env(env, repo)
    p, kit = _piped(env, tmp_path, "--install")
    assert p.returncode == 0, p.stderr
    assert (kit / "VERSION").read_text() == "v0.2.0"
    assert "python bin/loadout bootstrap --install --channel stable [tty=" in env["log"].read_text()


def test_sh_from_an_existing_checkout_forwards_no_channel(env, tmp_path):
    kit = tmp_path / "kit"
    _fake_clone(kit)
    shutil.copy(SCRIPT, kit / "bootstrap.sh")
    env["stub"]("uv", env["uv_ok"])
    assert _run(env, [str(kit / "bootstrap.sh"), "--install"], cwd=tmp_path).returncode == 0
    assert "channel" not in env["log"].read_text()


def test_sh_reused_clone_forwards_no_channel(env, tmp_path):
    _stable_env(env, _release_repo(tmp_path, [("v0.1.0", False, 9), ("v0.2.0", True, 5)]))
    env["vars"]["LOADOUT_REF"] = "v0.1.0"
    _piped(env, tmp_path)
    del env["vars"]["LOADOUT_REF"]
    env["log"].unlink()
    p, _ = _piped(env, tmp_path, "--install")
    assert p.returncode == 0, p.stderr
    assert "channel" not in env["log"].read_text()


def test_sh_skips_lightweight_below_floor_and_unsoaked_tags(env, tmp_path):
    _stable_env(env, _release_repo(tmp_path, MIXED))
    p, kit = _piped(env, tmp_path)
    assert p.returncode == 0, p.stderr
    assert (kit / "VERSION").read_text() == "v0.10.0"  # versions sort numerically


def test_sh_stops_when_no_release_is_ready(env, tmp_path):
    _stable_env(env, _release_repo(tmp_path, [("v0.1.0", False, 30), ("v0.3.0", True, 0)]))
    p, kit = _piped(env, tmp_path, "--install")
    assert p.returncode == 1
    assert "no stable release is ready yet; wait a few days, or install dev:" in p.stderr
    assert "--channel dev" in p.stderr
    assert not kit.exists() and not env["log"].exists()


def test_sh_channel_dev_checks_out_main(env, tmp_path):
    _stable_env(env, _release_repo(tmp_path, [("v0.2.0", True, 5)]))
    p, kit = _piped(env, tmp_path, "--install", "--channel", "dev")
    assert p.returncode == 0, p.stderr
    assert (kit / "VERSION").read_text() == "main"
    assert "python bin/loadout bootstrap --install --channel dev" in env["log"].read_text()


def test_sh_rejects_an_unknown_channel(env, tmp_path):
    _stable_env(env, _release_repo(tmp_path, [("v0.2.0", True, 5)]))
    p, kit = _piped(env, tmp_path, "--channel=nightly")
    assert p.returncode != 0 and "stable or dev" in p.stderr and not kit.exists()


def test_sh_loadout_ref_wins(env, tmp_path):
    _stable_env(env, _release_repo(tmp_path, [("v0.2.0", True, 5)]))
    env["vars"]["LOADOUT_REF"] = "main"
    p, kit = _piped(env, tmp_path)
    assert p.returncode == 0, p.stderr
    assert (kit / "VERSION").read_text() == "main"


def test_sh_reuse_moves_a_clone_without_local_commits_to_the_release(env, tmp_path):
    _stable_env(env, _release_repo(tmp_path, [("v0.1.0", False, 9), ("v0.2.0", True, 5)]))
    env["vars"]["LOADOUT_REF"] = "v0.1.0"
    p, kit = _piped(env, tmp_path)
    assert p.returncode == 0 and (kit / "VERSION").read_text() == "v0.1.0"
    del env["vars"]["LOADOUT_REF"]
    p, _ = _piped(env, tmp_path)
    assert p.returncode == 0, p.stderr
    assert (kit / "VERSION").read_text() == "v0.2.0"


def test_sh_reuse_leaves_a_clone_with_local_commits(env, tmp_path):
    _stable_env(env, _release_repo(tmp_path, [("v0.2.0", True, 5)]))
    env["vars"]["LOADOUT_REF"] = "main"
    p, kit = _piped(env, tmp_path)
    (kit / "VERSION").write_text("mine")
    _git(kit, "add", "-A")
    _git(kit, "commit", "-q", "-m", "mine")
    del env["vars"]["LOADOUT_REF"]
    p, _ = _piped(env, tmp_path)
    assert p.returncode == 0, p.stderr
    assert (kit / "VERSION").read_text() == "mine" and "left as it is" in p.stdout


@pytest.mark.skipif(not shutil.which("pwsh"), reason="needs PowerShell")
def test_ps1_tag_pick_matches_sh(env, tmp_path):
    repo = _release_repo(tmp_path, MIXED)
    text = (paths.kit_root() / "bootstrap.ps1").read_bytes().decode().replace("\r\n", "\n")  # a CRLF checkout cuts the same
    start = text.index("function Get-ReleaseTag")
    end = text.index("\n}\n", start) + 3
    p = subprocess.run(["pwsh", "-NoProfile", "-Command", text[start:end] + f"\nGet-ReleaseTag '{repo}'"],
                       capture_output=True, text=True, timeout=60)
    assert p.stdout.strip() == "v0.10.0", p.stderr
