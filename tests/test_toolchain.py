import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

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


GET = ("powershell", "-NoProfile", "-Command", b.WIN_PATH_GET)


def _posix(monkeypatch, shell="/bin/bash"):
    monkeypatch.setattr(paths, "platform_key", lambda: "posix")
    monkeypatch.setenv("SHELL", shell)


def test_path_block_goes_to_rc_and_login_profile(fake_home, fake_runner, monkeypatch):
    _posix(monkeypatch)
    (fake_home / ".local/bin").mkdir(parents=True)
    (fake_home / ".bashrc").write_text("case $- in *i*) ;; *) return;; esac\n")
    out, changed = b.setup_path(None)
    assert out and changed
    for f in (".bashrc", ".profile"):
        text = (fake_home / f).read_text()
        assert text.count(b.PATH_MARKER + "\n") == 1 and b.PATH_END in text
        assert '"$HOME/.local/bin"' in text
    assert b.setup_path(None) == ([], False)  # idempotent: nothing changed, nothing to say


def test_path_block_prefers_existing_bash_profile(fake_home, fake_runner, monkeypatch):
    _posix(monkeypatch)
    (fake_home / ".local/bin").mkdir(parents=True)
    (fake_home / ".bash_profile").write_text("# mine\n")
    b.setup_path(None)
    assert b.PATH_MARKER in (fake_home / ".bash_profile").read_text()
    assert not (fake_home / ".profile").exists()


def test_path_block_skips_folders_outside_home_and_missing_ones(fake_home, fake_runner, monkeypatch):
    _posix(monkeypatch)
    monkeypatch.setattr(paths, "tool_dirs", lambda: [Path("/opt/elsewhere/bin")])
    assert b.setup_path(None) == ([], False)


def test_path_block_keeps_the_first_folder_first(fake_home, fake_runner, monkeypatch):
    _posix(monkeypatch)
    dirs = [fake_home / ".local/bin", fake_home / ".local/share/mise/shims"]
    monkeypatch.setattr(paths, "tool_dirs", lambda: dirs)
    block = b._path_block(dirs)
    assert block.index(".local/share/mise/shims") < block.index('PATH="$HOME/.local/bin"')  # prepended last, so first


@pytest.mark.skipif(sys.platform == "win32" or not shutil.which("sh"), reason="needs a POSIX sh")
def test_sourcing_the_block_twice_adds_no_duplicates(fake_home, fake_runner):
    dirs = [fake_home / ".local/bin", fake_home / ".local/share/mise/shims"]
    script = fake_home / "blk.sh"
    script.write_text(b._path_block(dirs))
    res = subprocess.run(["sh", "-c", f'PATH=/usr/bin; HOME={fake_home}; . {script}; . {script}; echo "$PATH"'],
                         capture_output=True, text=True)
    parts = res.stdout.strip().split(":")
    assert parts == [f"{fake_home}/.local/share/mise/shims", f"{fake_home}/.local/bin", "/usr/bin"] or \
        parts == [f"{fake_home}/.local/bin", f"{fake_home}/.local/share/mise/shims", "/usr/bin"]
    assert len(parts) == len(set(parts))


def test_path_block_with_changed_folders_is_replaced_in_place(fake_home, fake_runner, monkeypatch):
    _posix(monkeypatch)
    (fake_home / ".local/bin").mkdir(parents=True)
    old = f"{b.PATH_MARKER}\nPATH=\"$HOME/old\":\"$PATH\"\nexport PATH\n{b.PATH_END}\n"
    (fake_home / ".bashrc").write_text("# top\n" + old + "# bottom\n")
    (fake_home / ".profile").write_text("# p\n")
    out, changed = b.setup_path(None)
    assert changed
    text = (fake_home / ".bashrc").read_text()
    assert text.startswith("# top\n" + b.PATH_MARKER) and text.endswith(b.PATH_END + "\n# bottom\n")
    assert "$HOME/old" not in text and '"$HOME/.local/bin"' in text and text.count(b.PATH_MARKER + "\n") == 1
    assert b.setup_path(None) == ([], False)


def _win(monkeypatch, fake_home):
    monkeypatch.setattr(paths, "platform_key", lambda: "windows")
    monkeypatch.setenv("LOCALAPPDATA", str(fake_home / "AppData/Local"))
    (fake_home / ".local/bin").mkdir(parents=True)


def _sets(fake_runner):
    return [c for c in fake_runner.calls if "SetValue" in " ".join(c)]


def test_windows_user_path_is_extended_once_and_keeps_expand_entries(fake_home, fake_runner, monkeypatch):
    _win(monkeypatch, fake_home)
    fake_runner.responses[GET] = runner.Result(0, "C:\\Tools;%USERPROFILE%\\bin\r\n", "")
    out, changed = b.setup_path(None)
    sets = _sets(fake_runner)
    assert len(sets) == 1 and changed and out
    assert str(fake_home / ".local/bin") in sets[0][-1] and "%USERPROFILE%\\bin" in sets[0][-1]
    assert "ExpandString" in sets[0][-1]
    assert "was: C:\\Tools;%USERPROFILE%\\bin" in out[0]


def test_windows_entry_written_with_variable_counts_as_present(fake_home, fake_runner, monkeypatch):
    _win(monkeypatch, fake_home)
    fake_runner.responses[GET] = runner.Result(0, "%userprofile%\\.LOCAL\\bin\r\n", "")
    assert b.setup_path(None) == ([], False)
    assert not _sets(fake_runner)


def test_windows_already_present_entry_does_not_write(fake_home, fake_runner, monkeypatch):
    _win(monkeypatch, fake_home)
    fake_runner.responses[GET] = runner.Result(0, str(fake_home / ".local/bin").upper() + ";C:\\x", "")
    assert b.setup_path(None) == ([], False)
    assert not _sets(fake_runner)


def test_windows_empty_user_path(fake_home, fake_runner, monkeypatch):
    _win(monkeypatch, fake_home)
    fake_runner.responses[GET] = runner.Result(0, "\r\n", "")
    out, changed = b.setup_path(None)
    assert changed and "was: empty" in out[0]
    assert _sets(fake_runner)[0][-1].count(str(fake_home / ".local/bin")) == 1


def test_windows_single_quote_in_value_is_doubled(fake_home, fake_runner, monkeypatch):
    _win(monkeypatch, fake_home)
    fake_runner.responses[GET] = runner.Result(0, "C:\\O'Brien\\bin", "")
    b.setup_path(None)
    assert "C:\\O''Brien\\bin" in _sets(fake_runner)[0][-1]


def test_windows_failed_write_is_not_reported_as_success(fake_home, fake_runner, monkeypatch):
    _win(monkeypatch, fake_home)
    fake_runner.responses[GET] = runner.Result(0, "C:\\Tools", "")
    real = runner.run
    def run(cmd, *a, **k):
        if "SetValue" in " ".join(cmd):
            fake_runner.calls.append(list(cmd))
            return runner.Result(1, "", "denied")
        return real(cmd, *a, **k)
    monkeypatch.setattr(runner, "run", run)
    out, changed = b.setup_path(None)
    assert not changed and out and out[0].startswith("could not update your user PATH; add ")


def test_windows_read_failure_changes_nothing(fake_home, fake_runner, monkeypatch):
    _win(monkeypatch, fake_home)
    fake_runner.responses[GET] = runner.Result(1, "", "boom")
    out, changed = b.setup_path(None)
    assert not changed and out and not _sets(fake_runner)
