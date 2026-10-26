import os

import pytest

from loadout import runner


class FakeRunner:
    """Records commands; returns canned results matched by command prefix."""

    def __init__(self):
        self.calls = []
        self.envs = []
        self.cwds = []
        self.timeouts = []
        self.responses = {}
        self.missing = set()
        self.paths = {}  # binary -> resolved path (runner.which); default: not found, so no package manager


    def __call__(self, cmd, cwd=None, timeout=300, env=None):
        self.calls.append(list(cmd))
        self.envs.append(env)
        self.cwds.append(cwd)
        self.timeouts.append(timeout)
        for prefix, result in self.responses.items():
            if tuple(cmd[: len(prefix)]) == prefix:
                if isinstance(result, list):  # a sequence: consumed in order, the last one repeats
                    return result.pop(0) if len(result) > 1 else result[0]
                return result
        return runner.Result(0, "", "")

    def have(self, binary):
        return binary not in self.missing

    def which(self, binary):
        return self.paths.get(binary)


# the exact real command lines tests may run (argument for argument): any other real program, or these programs
# with other arguments, fails the test. A pattern cannot prove that an interpreter (python -c, cmd /c, a git alias)
# starts nothing else, so only lines that were read and judged harmless are listed
HARMLESS_COMMANDS = frozenset({
    ("echo", "x"),
    ("git", "--version"),
    ("python", "-c", "print('ok')"),
    ("python", "-c", "import os; print(os.environ['LOADOUT_T'])"),
    ("python", "-c", "import os; print(os.environ.get('LOADOUT_UPDATE_PULLED'))"),
    ("python", "-c", "import sys; sys.stdout.buffer.write('\u23fa ok '.encode('utf-8') + b'\\xff')"),
})
# `git -C <a test's own folder> ls-files ...`: a read-only built-in (aliases cannot replace built-ins)
_GIT_LS_FILES = ("ls-files", "-s", "-z", "--", ".claude/skills", ".agents/skills")


def _harmless(line, base):
    if line in HARMLESS_COMMANDS:
        return True
    return (len(line) == 3 + len(_GIT_LS_FILES) and line[:2] == ("git", "-C") and line[3:] == _GIT_LS_FILES
            and os.path.realpath(line[2]).startswith(os.path.realpath(base)))


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
    # nor can it run a real program through runner.run (AGENTS.md: no real claude/codex/installers in tests). A test
    # that needs external commands uses fake_runner (which replaces runner.run, so this guard steps aside); a
    # program a test put in a temporary folder (a stub) runs, and so do the harmless ones below
    from loadout import runner
    real_run, base, real_subprocess_run = runner.run, str(tmp_path_factory.getbasetemp()), subprocess.run

    def guarded_run(cmd, *args, **kwargs):
        exe = runner._resolve(cmd[0]) or runner._fallback(cmd[0]) if cmd else None
        name = os.path.basename(str(cmd[0])).lower().removesuffix(".exe") if cmd else ""
        real = exe is not None and os.path.exists(exe)  # a made-up path (a test that fakes subprocess) runs nothing
        stub = real and os.path.realpath(exe).startswith(os.path.realpath(base))
        line = (name, *(str(a) for a in cmd[1:]))
        faked = runner.subprocess.run is not real_subprocess_run  # the test replaced subprocess: nothing starts
        if real and not stub and not faked and not _harmless(line, base):
            pytest.fail(f"a test ran the real `{name}` ({exe}) through runner.run: {line!r}; use fake_runner or a "
                        "stub in tmp_path")
        if real and not stub and not faked and name in ("python", "python3"):
            cmd = [cmd[0], "-I", "-S", *cmd[1:]]  # isolated, and no `site` at all: no sitecustomize, user or system
        elif real and not stub and not faked and name == "git":
            cmd = [cmd[0], "-c", "core.fsmonitor=false", "-c", f"core.hooksPath={os.devnull}", *cmd[1:]]  # no hooks
        return real_run(cmd, *args, **kwargs)
    monkeypatch.setattr(runner, "run", guarded_run)


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
    monkeypatch.delenv("CBM_CACHE_DIR", raising=False)  # check never reads a real codebase-memory cache
    from loadout import wsl
    monkeypatch.setattr(wsl, "OSRELEASE", tmp_path / "no-osrelease")  # tests never see a real WSL machine
    return home


@pytest.fixture
def fake_runner(monkeypatch):
    from loadout import vscode
    monkeypatch.setattr(vscode, "_VERSIONS", {})  # no version cached from another test
    from loadout import codex
    monkeypatch.setattr(codex, "_CLI_VERSIONS", {})  # nor a Codex CLI version
    monkeypatch.setattr(runner, "FALLBACK", {})  # no bundled binary registered by another test
    fake = FakeRunner()
    # codebase-memory's auto_index reads as already on, so tests that are not about it see no cbm change
    fake.responses[("codebase-memory-mcp", "config", "get", "auto_index")] = runner.Result(0, "true\n", "")
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


@pytest.fixture
def codex_ext(fake_home, fake_runner, monkeypatch):
    """VS Code's Codex extension (a usable bundled codex 0.162.1) and no Codex CLI on PATH; returns the binary."""
    from loadout import targets
    monkeypatch.setattr(targets, "OVERRIDE", {"claude": False, "codex": True})
    fake_runner.missing.add("codex")
    folder = fake_home / ".vscode" / "extensions" / "openai.chatgpt-26.715.61943-linux-x64"
    binary = folder / host_codex_bin()
    binary.parent.mkdir(parents=True)
    binary.write_text("bin")
    binary.chmod(0o755)
    fake_runner.responses[(str(binary), "--version")] = runner.Result(0, "codex-cli 0.162.1\n", "")
    return binary
