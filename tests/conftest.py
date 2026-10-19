import os

import pytest

from loadout import runner


class FakeRunner:
    """Records commands; returns canned results matched by command prefix."""

    def __init__(self):
        self.calls = []
        self.envs = []
        self.cwds = []
        self.responses = {}
        self.missing = set()
        self.paths = {}  # binary -> resolved path (runner.which); default: not found, so no package manager


    def __call__(self, cmd, cwd=None, timeout=300, env=None):
        self.calls.append(list(cmd))
        self.envs.append(env)
        self.cwds.append(cwd)
        for prefix, result in self.responses.items():
            if tuple(cmd[: len(prefix)]) == prefix:
                return result
        return runner.Result(0, "", "")

    def have(self, binary):
        return binary not in self.missing

    def which(self, binary):
        return self.paths.get(binary)


@pytest.fixture(autouse=True)
def never_the_real_home(tmp_path_factory, monkeypatch):
    """Every test runs with a throwaway HOME, so one that forgets fake_home still cannot read or write the real
    ~/.claude, ~/.codex or ~/.config/loadout (fake_home sets its own, like before)."""
    home = tmp_path_factory.mktemp("isolated-home")  # outside tmp_path: tests list their own tmp_path
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("LOADOUT_PERSONAL", raising=False)
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)  # state_dir() follows the throwaway HOME
    for var in ("APPDATA", "XDG_CONFIG_HOME", "VSCODE_EXTENSIONS"):  # never the real VS Code folders
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("PATH", os.environ.get("PATH", ""))  # teardown restores it: nothing leaks a fake tool dir into later tests
    monkeypatch.setenv("LOADOUT_REEXEC", "1")  # bin/loadout never re-execs the test process through a real uv
    monkeypatch.setenv("LOADOUT_UPDATE_PULLED", "1")  # `loadout update` neither pulls nor restarts the test process
    # and even a test that deletes that marker cannot restart into the real launcher: update._exec fails the test
    # unless the test faked os.execv (POSIX) or subprocess.Popen (Windows) itself
    import subprocess
    from loadout import update
    real_exec, real_execv, real_popen = update._exec, os.execv, subprocess.Popen

    def guarded_exec(argv, windows=None):
        on_windows = os.name == "nt" if windows is None else windows
        if (subprocess.Popen is real_popen) if on_windows else (os.execv is real_execv):
            pytest.fail(f"a test tried to restart into the real loadout ({argv}); fake update._exec")
        return real_exec(argv, windows=windows)
    monkeypatch.setattr(update, "_exec", guarded_exec)


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("LOADOUT_PERSONAL", raising=False)
    monkeypatch.delenv("CODEX_HOME", raising=False)  # never a real Codex home
    monkeypatch.setenv("USER", "loadout-test-user")  # wsl.windows_home's /mnt/c/Users/$USER guess never finds a real one
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    from loadout import wsl
    monkeypatch.setattr(wsl, "OSRELEASE", tmp_path / "no-osrelease")  # tests never see a real WSL machine
    return home


@pytest.fixture
def fake_runner(monkeypatch):
    from loadout import vscode
    monkeypatch.setattr(vscode, "_VERSIONS", {})  # no version cached from another test
    monkeypatch.setattr(runner, "FALLBACK", {})  # no bundled binary registered by another test
    fake = FakeRunner()
    monkeypatch.setattr(runner, "run", fake)
    monkeypatch.setattr(runner, "have", fake.have)
    monkeypatch.setattr(runner, "which", fake.which)
    return fake


@pytest.fixture
def kit_root():
    from loadout import paths
    return paths.kit_root()


@pytest.fixture(autouse=True)
def verbose_output(monkeypatch):
    """Existing tests assert today's detail lines (verbose mode); calm-mode tests set out.VERBOSE = False."""
    from loadout import out
    monkeypatch.setattr(out, "VERBOSE", True)


def host_arch() -> str:
    import platform
    return "aarch64" if platform.machine().lower() in ("aarch64", "arm64") else "x86_64"


def linux_codex_bin() -> str:
    """The bundled Codex of a Linux build for this machine's architecture (Remote-WSL, a "linux" platform)."""
    return f"bin/linux-{host_arch()}/codex"


def host_codex_bin() -> str:
    """Where the bundled Codex of this host's VS Code extension build lives (tests build that one)."""
    import sys
    arch = host_arch()
    if sys.platform == "win32":
        return f"bin/windows-{arch}/codex.exe"
    return f"bin/{'darwin' if sys.platform == 'darwin' else 'linux'}-{arch}/codex"


@pytest.fixture
def codex_bin() -> str:
    return host_codex_bin()


def host_claude_bin() -> str:
    import sys
    return "resources/native-binary/claude.exe" if sys.platform == "win32" else "resources/native-binary/claude"
