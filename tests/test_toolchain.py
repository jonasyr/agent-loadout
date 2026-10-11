import os
from pathlib import Path

from loadout import bootstrap as b, catalog, paths, runner


def _only(monkeypatch, entries):
    monkeypatch.setattr(catalog, "binaries", lambda: entries)


def _bin(i, needs=(), required=True, helper=False):
    e = {"id": i, "kind": "binary", "status": "core", "required": required, "needs": list(needs),
         "install": {"posix": [[f"install-{i}"]], "windows": [[f"install-{i}"]]}, "version": {"cmd": [i, "--version"]}}
    if helper:
        e["helper"] = True
    return e


def test_tool_dirs_lists_existing_user_folders(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(paths, "platform_key", lambda: "posix")
    (fake_home / ".local/bin").mkdir(parents=True)
    (fake_home / ".local/share/mise/shims").mkdir(parents=True)
    assert paths.tool_dirs() == [fake_home / ".local/bin", fake_home / ".local/share/mise/shims"]


def test_prepend_tool_dirs_is_idempotent(fake_home, fake_runner, monkeypatch):
    (fake_home / ".local/bin").mkdir(parents=True)
    monkeypatch.setenv("PATH", "/usr/bin")
    b.prepend_tool_dirs()
    b.prepend_tool_dirs()
    parts = os.environ["PATH"].split(os.pathsep)
    assert parts.count(str(fake_home / ".local/bin")) == 1 and parts[0] == str(fake_home / ".local/bin")


def test_installs_dependencies_first_and_only_what_is_missing(fake_home, fake_runner, monkeypatch):
    _only(monkeypatch, [_bin("playwright-cli", ["node"]), _bin("node", ["mise"]), _bin("mise", helper=True, required=False), _bin("uv")])
    fake_runner.missing.update({"playwright-cli", "node", "mise"})  # uv is already there

    def run(cmd, cwd=None, timeout=300, env=None):
        fake_runner.calls.append(list(cmd))
        fake_runner.missing.discard(cmd[0].removeprefix("install-"))  # the install worked
        return runner.Result(0, "", "")

    monkeypatch.setattr(runner, "run", run)
    assert b.check_prereqs(True, lambda q: "") == []
    installs = [c for c in fake_runner.calls if c[0].startswith("install-")]  # reshim and gh auth calls are not installs
    assert installs == [["install-mise"], ["install-node"], ["install-playwright-cli"]]


def test_helper_is_not_installed_when_nothing_needs_it(fake_home, fake_runner, monkeypatch):
    _only(monkeypatch, [_bin("node", ["mise"]), _bin("mise", helper=True, required=False)])
    fake_runner.missing.add("mise")  # node is there: no mise
    b.check_prereqs(True, lambda q: "")
    assert ["install-mise"] not in fake_runner.calls


def test_failed_dependency_skips_dependants(fake_home, fake_runner, monkeypatch, capsys):
    _only(monkeypatch, [_bin("node", ["mise"]), _bin("mise", helper=True, required=False)])
    fake_runner.missing.update({"node", "mise"})
    fake_runner.responses[("install-mise",)] = runner.Result(1, "", "boom")
    missing = b.check_prereqs(True, lambda q: "")
    assert ["install-node"] not in fake_runner.calls
    assert "node" in missing
    assert "skipped: needs mise" in capsys.readouterr().out


def test_mise_commands_run_in_home(fake_home, fake_runner, monkeypatch):
    e = _bin("node", ["mise"])
    e["install"] = {"posix": [["mise", "use", "-g", "node@lts"]], "windows": [["mise", "use", "-g", "node@lts"]]}
    _only(monkeypatch, [e, _bin("mise", helper=True, required=False)])
    fake_runner.missing.add("node")
    seen = []
    monkeypatch.setattr(runner, "run", lambda cmd, cwd=None, timeout=300, env=None: seen.append((cmd, cwd)) or runner.Result(0, "", ""))
    b.check_prereqs(True, lambda q: "")
    assert (["mise", "use", "-g", "node@lts"], str(paths.home())) in seen


def test_without_install_flag_nothing_runs(fake_home, fake_runner, monkeypatch):
    _only(monkeypatch, [_bin("node", ["mise"]), _bin("mise", helper=True, required=False)])
    fake_runner.missing.update({"node", "mise"})
    assert b.check_prereqs(False, lambda q: "") == ["node"]
    assert not any(c[0].startswith("install-") for c in fake_runner.calls)


def test_path_block_goes_to_rc_and_login_profile(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(paths, "platform_key", lambda: "posix")
    monkeypatch.setenv("SHELL", "/bin/bash")
    (fake_home / ".local/bin").mkdir(parents=True)
    (fake_home / ".bashrc").write_text("case $- in *i*) ;; *) return;; esac\n")
    out = b.setup_path(None)
    assert out
    for f in (".bashrc", ".profile"):
        text = (fake_home / f).read_text()
        assert text.count(b.PATH_MARKER) == 1
        assert '"$HOME/.local/bin"' in text
    assert b.setup_path(None) == []  # idempotent: nothing changed, nothing to say


def test_path_block_prefers_existing_bash_profile(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(paths, "platform_key", lambda: "posix")
    monkeypatch.setenv("SHELL", "/bin/bash")
    (fake_home / ".local/bin").mkdir(parents=True)
    (fake_home / ".bash_profile").write_text("# mine\n")
    b.setup_path(None)
    assert b.PATH_MARKER in (fake_home / ".bash_profile").read_text()
    assert not (fake_home / ".profile").exists()


def test_path_block_skips_folders_outside_home_and_missing_ones(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(paths, "platform_key", lambda: "posix")
    monkeypatch.setattr(paths, "tool_dirs", lambda: [Path("/opt/elsewhere/bin")])
    assert b.setup_path(None) == []


def test_windows_user_path_is_extended_once(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(paths, "platform_key", lambda: "windows")
    (fake_home / ".local/bin").mkdir(parents=True)
    get = ("powershell", "-NoProfile", "-Command", "[Environment]::GetEnvironmentVariable('Path', 'User')")
    fake_runner.responses[get] = runner.Result(0, "C:\\Tools\r\n", "")
    out = b.setup_path(None)
    sets = [c for c in fake_runner.calls if "SetEnvironmentVariable" in " ".join(c)]
    assert len(sets) == 1 and str(fake_home / ".local/bin") in sets[0][-1] and "C:\\Tools" in sets[0][-1]
    assert out
