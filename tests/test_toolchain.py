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
    assert "missing node: not installed because mise failed to install" in capsys.readouterr().out


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


def _ps(monkeypatch, fake_runner, rc, out, old=None):
    """A fake powershell: records the call, writes the backup file like the real script, prints `out`."""
    def run(cmd, cwd=None, timeout=300, env=None):
        fake_runner.calls.append(list(cmd))
        fake_runner.envs.append(env)
        if old is not None and env:
            Path(env["LOADOUT_PATH_BACKUP"]).write_bytes(old.encode("utf-8"))
        return runner.Result(rc, out, "")
    monkeypatch.setattr(runner, "run", run)


OLD_PATH = "C:\\Tools;%USERPROFILE%\\bin;C:\\Users\\J\u00f6rg\u2019s\\bin"


def test_windows_user_path_change_runs_one_script_with_values_in_env(fake_home, fake_runner, monkeypatch):
    from loadout.backup import Backup
    _win(monkeypatch, fake_home)
    _ps(monkeypatch, fake_runner, 0, "CHANGED 0\r\n", old=OLD_PATH)
    bk = Backup()
    out, changed = b.setup_path(bk)
    assert changed and out == [f"added {fake_home / '.local/bin'} to your user PATH (old value saved in the backup)"]
    assert len(fake_runner.calls) == 1
    cmd, env = fake_runner.calls[0], fake_runner.envs[0]
    assert cmd[:2] == ["powershell", "-NoProfile"] and "-EncodedCommand" in cmd
    joined = " ".join(cmd)
    assert ".local" not in joined and "Tools" not in joined and "\u2019" not in joined  # nothing spliced in
    assert env["LOADOUT_PATH_ADD"].split("\n") == [str(fake_home / ".local/bin")]
    assert env["PATH"] == os.environ["PATH"]  # the rest of the environment is passed on
    kept = [s for s in bk.steps if "kept" in s["undo"]]
    assert len(kept) == 1 and Path(kept[0]["undo"]["kept"]).read_text(encoding="utf-8") == OLD_PATH
    assert not Path(env["LOADOUT_PATH_BACKUP"]).exists()  # moved into the backup


def test_windows_path_script_is_what_runs():
    import base64
    cmd_arg = b._win_path_command()[-1]
    assert base64.b64decode(cmd_arg).decode("utf-16-le") == b.WIN_PATH_SCRIPT
    script = b.WIN_PATH_SCRIPT
    for needle in ("DoNotExpandEnvironmentNames", "ExpandEnvironmentVariables", "ToLowerInvariant",
                   "$env:LOADOUT_PATH_ADD", "$env:LOADOUT_PATH_BACKUP", "RegistryValueKind]::ExpandString",
                   "SetEnvironmentVariable('LOADOUT_PATH_REFRESH', $null, 'User')", "'UNCHANGED'", "'CHANGED"):
        assert needle in script, needle
    assert script.index("WriteAllText") < script.index("SetValue(")  # backup before the change
    assert script.index("SetValue(") < script.index("LOADOUT_PATH_REFRESH")  # broadcast after it


def test_windows_unchanged_path_writes_nothing(fake_home, fake_runner, monkeypatch):
    from loadout.backup import Backup
    _win(monkeypatch, fake_home)
    _ps(monkeypatch, fake_runner, 0, "UNCHANGED\r\n")
    bk = Backup()
    assert b.setup_path(bk) == ([], False)
    assert bk.empty and not Path(fake_runner.envs[0]["LOADOUT_PATH_BACKUP"]).exists()


def test_windows_failed_update_is_not_reported_as_success(fake_home, fake_runner, monkeypatch):
    from loadout.backup import Backup
    _win(monkeypatch, fake_home)
    for rc, out in ((1, ""), (0, ""), (0, "Fehler \ufffd\r\n")):
        _ps(monkeypatch, fake_runner, rc, out, old=OLD_PATH)
        bk = Backup()
        lines, changed = b.setup_path(bk)
        assert not changed and lines == [f"could not update your user PATH; add {fake_home / '.local/bin'} to it by hand"]
        assert bk.empty


def test_windows_path_reports_only_the_added_folders(fake_home, fake_runner, monkeypatch):
    _win(monkeypatch, fake_home)
    (fake_home / "AppData/Local/mise/shims").mkdir(parents=True)
    _ps(monkeypatch, fake_runner, 0, "CHANGED 1\r\n", old="")
    out, changed = b.setup_path(None)
    assert changed and out == [f"added {fake_home / 'AppData/Local/mise/shims'} to your user PATH (old value saved in the backup)"]


def test_kept_backup_file_is_reported_on_restore(fake_home, tmp_path):
    from loadout import backup
    f = tmp_path / "old.txt"
    f.write_text("C:\\x")
    bk = backup.Backup(description="t")
    bk.keep(f, "your user PATH before loadout changed it")
    lines, ok, _ = backup.restore(bk.root)
    assert ok and any("restore it by hand" in l and "user PATH" in l for l in lines), lines


def test_tool_dirs_on_windows_include_winget_links(fake_home, monkeypatch):
    monkeypatch.setattr(paths, "platform_key", lambda: "windows")
    local = fake_home / "AppData/Local"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    links = local / "Microsoft/WinGet/Links"
    links.mkdir(parents=True)
    assert links in paths.tool_dirs()


def test_still_to_do_lists_only_what_applies(fake_home, fake_runner):
    fake_runner.missing.add("git")
    fake_runner.responses[("gh", "auth", "status")] = runner.Result(1, "", "not logged in")
    lines = b.still_to_do("macos")
    assert "xcode-select --install" in "\n".join(lines)
    assert "gh auth login" in "\n".join(lines)
    assert any("claude" in l and "log in" in l for l in lines)


def test_still_to_do_windows_git_line(fake_home, fake_runner):
    fake_runner.missing.add("git")
    assert any("winget install --id Git.Git -e" in l for l in b.still_to_do("windows"))


def test_still_to_do_empty_when_all_done(fake_home, fake_runner):
    (fake_home / ".claude.json").write_text('{"oauthAccount": {"emailAddress": "x"}}')
    assert b.still_to_do("linux") == []
