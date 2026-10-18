"""Final-review findings for VS Code PR 1: each pinned by a test that failed first."""
import json
from pathlib import Path

import pytest

from conftest import host_arch, host_claude_bin, host_codex_bin, linux_codex_bin

from loadout import check, paths, runner, targets, vscode, wsl


@pytest.fixture
def vs(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(targets, "OVERRIDE", {"claude": True, "codex": True})
    return fake_home


def _ext(root: Path, name: str, *binaries: str) -> Path:
    folder = root / name
    folder.mkdir(parents=True)
    for b in binaries:
        (folder / b).parent.mkdir(parents=True, exist_ok=True)
        (folder / b).write_text("bin")
        (folder / b).chmod(0o755)  # shipped executable
    return folder


def _cs(win, side="wsl"):
    return type("CS", (), {"windows_home": win, "side": side, "shared_home": False})()


def test_claude_windows_window_is_ok_once_loadout_set_up_windows(vs, monkeypatch, tmp_path):
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)
    win = tmp_path / "c" / "Users" / "ada"
    _ext(win / ".vscode" / "extensions", "anthropic.claude-code-2.1.217-win32-x64", "resources/native-binary/claude.exe")
    (win / ".claude" / "rules" / "loadout").mkdir(parents=True)  # bootstrap.ps1 linked the kit's rules there
    (row,) = check._vscode_surfaces(_cs(win))
    assert row.ok


def test_claude_windows_window_fix_names_the_remote_wsl_only_case(vs, monkeypatch, tmp_path):
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)
    win = tmp_path / "c" / "Users" / "ada"
    _ext(win / ".vscode" / "extensions", "anthropic.claude-code-2.1.217-win32-x64", "resources/native-binary/claude.exe")
    (row,) = check._vscode_surfaces(_cs(win))
    assert not row.ok and "only Remote-WSL windows" in row.fix


def test_windows_only_codex_remote_wsl_row_and_no_wsl_codex_config_read(vs, fake_runner, monkeypatch, tmp_path):
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)
    win = tmp_path / "c" / "Users" / "ada"
    win.mkdir(parents=True)
    _ext(vs / ".vscode-server" / "extensions", "openai.chatgpt-26.715.61943-linux-x64", linux_codex_bin())
    fake_runner.missing.add("codex")
    monkeypatch.setattr(vscode, "mcp_commands", lambda agent: pytest.fail("read the WSL Codex config"))
    rows = check._vscode_surfaces(_cs(win, side="windows"))
    assert [r.name for r in rows] == ["VS Code (Codex, Remote-WSL window)"]
    assert "does not set up" in rows[0].detail and "plugins do not load" not in rows[0].detail
    assert "--codex-side wsl" in rows[0].fix


@pytest.mark.parametrize("platform,where,expected", [("win32", "local", "codex.exe"), ("linux", "local", "codex"),
                                                     ("linux", "remote-wsl", "codex"), ("linux", "windows", "codex.exe")])
def test_bundled_codex_matches_the_platform(vs, monkeypatch, tmp_path, platform, where, expected):
    folder = _ext(tmp_path / "ext", "openai.chatgpt-26.1.1", f"bin/linux-{host_arch()}/codex", f"bin/windows-{host_arch()}/codex.exe")
    assert vscode._binary("codex", folder, vscode._os_of(where, platform)).name == expected


def test_check_survives_permission_errors_on_odd_filesystems(vs, fake_runner, monkeypatch):
    _ext(vs / ".vscode" / "extensions", "openai.chatgpt-26.715.61943-linux-x64", "bin/linux-x86_64/codex")
    (vs / ".codex").mkdir()
    (vs / ".codex" / "config.toml").write_text('[mcp_servers.s]\ncommand = "/root/bin/s"\n')

    def boom(self, *a, **k):
        raise PermissionError(13, "denied", str(self))
    monkeypatch.setattr(Path, "is_file", boom)
    monkeypatch.setattr(Path, "is_dir", boom)
    check._vscode_surfaces()  # no exception
    assert vscode.findable("/root/bin/s", ["/root/bin"]) is False


def test_no_windows_lookup_when_both_agents_are_off_or_it_is_known(vs, monkeypatch):
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)
    monkeypatch.setattr(wsl, "windows_home", lambda: pytest.fail("ran cmd.exe"))
    assert vscode.extensions({"claude": False, "codex": False}) == []
    check._vscode_surfaces(_cs(None))  # Codex on in WSL: codex_side already looked and found no Windows home


def _repo(tmp_path, monkeypatch, fake_runner, mcp, agents=None):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / ".mcp.json").write_text(json.dumps(mcp))
    if agents is not None:
        (repo / ".loadout.json").write_text(json.dumps({"agents": agents}))
    monkeypatch.chdir(repo)
    fake_runner.responses[("git", "-C", str(repo), "ls-files", "--error-unmatch", ".mcp.json")] = runner.Result(0, "", "")
    return repo


def test_mcp_json_row_only_for_a_repo_with_claude_code(vs, fake_runner, monkeypatch, tmp_path):
    _repo(tmp_path, monkeypatch, fake_runner, {"mcpServers": {"s": {"command": "/home/a/x"}}}, agents=["codex"])
    assert check._repo_mcp_paths() == []


def test_linuxbrew_is_shared_not_one_persons_home(vs, fake_runner, monkeypatch, tmp_path):
    _repo(tmp_path, monkeypatch, fake_runner, {"mcpServers": {"s": {"command": "/home/linuxbrew/.linuxbrew/bin/uvx"}}})
    assert check._repo_mcp_paths() == []


def test_server_env_setup_line_with_a_trailing_comment(vs):
    env = vs / vscode.SERVER_ENV
    env.parent.mkdir(parents=True)
    env.write_text('export PATH="$HOME/x:$PATH" # mine\n')
    assert f"{vs}/x" in vscode.remote_path_dirs()


def test_disabled_codex_servers_are_not_counted(vs):
    paths.codex_home().mkdir()
    (paths.codex_home() / "config.toml").write_text('[mcp_servers.off]\ncommand = "x"\nenabled = false\n')
    assert vscode.mcp_commands("codex") == {}


def test_deeply_nested_settings_give_none(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("[" * 100000 + "]" * 100000)
    assert vscode.read_jsonc(path) is None


def test_fixtures_hide_the_real_vscode_variables():
    import os
    assert not any(os.environ.get(v) for v in ("APPDATA", "XDG_CONFIG_HOME", "VSCODE_EXTENSIONS"))


def test_only_the_target_platforms_codex_counts(vs, tmp_path):
    folder = _ext(tmp_path / "ext", "openai.chatgpt-26.1.1", "bin/windows-x86_64/codex.exe")
    assert vscode._binary("codex", folder, "linux", "x86_64") is None  # a foreign build is "no bundled Codex for this platform"
    assert vscode._binary("codex", folder, "windows", "x86_64").name == "codex.exe"


def test_unknown_bin_layout_still_finds_codex(vs, tmp_path):
    folder = _ext(tmp_path / "ext", "openai.chatgpt-26.1.1", "bin/x86_64/codex")
    assert vscode._binary("codex", folder, "linux", "x86_64").name == "codex"


@pytest.mark.parametrize("value", ["/no/such/claude", 3, "", None, "DIR"])
def test_a_wrapper_that_is_not_a_file_does_not_count(vs, fake_runner, tmp_path, value):
    import sys
    _ext(vs / ".vscode" / "extensions", "anthropic.claude-code-2.1.217-linux-x64")
    user = vscode._user_dir(vs, sys.platform)
    user.mkdir(parents=True)
    value = str(tmp_path) if value == "DIR" else value
    (user / "settings.json").write_text(json.dumps({"claudeCode.claudeProcessWrapper": value}))
    fake_runner.missing.add("claude")
    (row,) = check._vscode_surfaces()
    assert not row.ok


@pytest.mark.skipif(__import__("os").name == "nt", reason="execute permission is POSIX")
def test_a_command_without_execute_permission_is_not_findable(tmp_path):
    cmd = tmp_path / "serena"
    cmd.write_text("x")
    cmd.chmod(0o644)
    assert not vscode.findable(str(cmd), []) and not vscode.findable("serena", [str(tmp_path)])
    cmd.chmod(0o755)
    assert vscode.findable(str(cmd), []) and vscode.findable("serena", [str(tmp_path)])


@pytest.mark.parametrize("machine,expected", [("x86_64", "linux-x86_64"), ("AMD64", "linux-x86_64"),
                                              ("aarch64", "linux-aarch64"), ("arm64", "linux-aarch64")])
def test_bundled_codex_matches_the_host_architecture(tmp_path, machine, expected):
    folder = _ext(tmp_path / "ext", "openai.chatgpt-26.1.1", "bin/linux-aarch64/codex", "bin/linux-x86_64/codex")
    assert vscode._binary("codex", folder, "linux", machine).parent.name == expected


def test_a_foreign_architecture_only_is_no_bundled_codex(tmp_path):
    folder = _ext(tmp_path / "ext", "openai.chatgpt-26.1.1", "bin/linux-aarch64/codex")
    assert vscode._binary("codex", folder, "linux", "x86_64") is None


def test_a_wrapper_only_in_a_vscode_profile_is_named_but_does_not_clear_the_warning(vs, fake_runner, tmp_path):
    import sys
    _ext(vs / ".vscode" / "extensions", "anthropic.claude-code-2.1.217-linux-x64")
    wrapper = tmp_path / "claude"
    wrapper.write_text("x")
    wrapper.chmod(0o755)
    profile = vscode._user_dir(vs, sys.platform) / "profiles" / "abc123"
    profile.mkdir(parents=True)
    (profile / "settings.json").write_text(json.dumps({"claudeCode.claudeProcessWrapper": str(wrapper)}))
    fake_runner.missing.add("claude")
    (row,) = check._vscode_surfaces()
    assert not row.ok and "profile" in row.detail and "user settings" in row.fix


def test_a_windows_home_mounted_in_wsl_counts_as_one_persons_home(vs, fake_runner, monkeypatch, tmp_path):
    _repo(tmp_path, monkeypatch, fake_runner, {"mcpServers": {"s": {"command": "/mnt/c/Users/Ana/bin/serena"}}})
    (row,) = check._repo_mcp_paths()
    assert not row.ok and "/mnt/c/Users/Ana/" in row.detail


def test_a_claude_cli_on_path_does_not_stand_in_for_the_missing_bundled_binary(vs, fake_runner):
    _ext(vs / ".vscode" / "extensions", "anthropic.claude-code-2.1.217-linux-x64")
    fake_runner.paths["claude"] = "/usr/bin/claude"  # the extension never uses the claude on PATH
    (row,) = check._vscode_surfaces()
    assert not row.ok and "claudeProcessWrapper" in row.fix


@pytest.mark.parametrize("text,has,lacks", [
    ('export PATH="$HOME/tools"\n', ["{home}/tools"], ["/usr/bin"]),
    ('PATH="$HOME/a:$PATH"\nexport PATH="$HOME/b"\n', ["{home}/b"], ["{home}/a", "/usr/bin"]),
    ('export PATH="$PATH:$HOME/c"\n', ["/usr/bin", "{home}/c"], []),
])
def test_server_env_setup_path_assignments_apply_in_order(vs, text, has, lacks):
    env = vs / vscode.SERVER_ENV
    env.parent.mkdir(parents=True)
    env.write_text(text)
    dirs = vscode.remote_path_dirs()
    for d in has:
        assert d.format(home=vs) in dirs
    for d in lacks:
        assert d.format(home=vs) not in dirs


def test_a_set_up_windows_window_still_needs_a_launchable_claude(vs, monkeypatch, tmp_path):
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)
    win = tmp_path / "c" / "Users" / "ada"
    _ext(win / ".vscode" / "extensions", "anthropic.claude-code-2.1.217-win32-x64")  # no bundled claude.exe
    (win / ".claude" / "rules" / "loadout").mkdir(parents=True)
    (row,) = check._vscode_surfaces(_cs(win))
    assert not row.ok and "cannot start Claude" in row.detail


def test_project_codex_servers_count_in_the_remote_wsl_path_check(vs, fake_runner, monkeypatch, tmp_path):
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)
    monkeypatch.setattr(wsl, "windows_home", lambda: None)
    _ext(vs / ".vscode-server" / "extensions", "openai.chatgpt-26.715.61943-linux-x64", linux_codex_bin())
    fake_runner.paths["codex"] = "/usr/bin/codex"
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / ".codex").mkdir()
    (repo / ".codex" / "config.toml").write_text('[mcp_servers.proj]\ncommand = "projtool"\n')
    (vs / ".codex").mkdir(exist_ok=True)
    (vs / ".codex" / "config.toml").write_text(f'[projects.{json.dumps(str(repo.resolve()))}]\ntrust_level = "trusted"\n')
    monkeypatch.chdir(repo)
    (row,) = [r for r in check._vscode_surfaces() if r.name == "VS Code PATH"]
    assert "proj" in row.detail


@pytest.mark.skipif(__import__("os").name == "nt", reason="execute permission is POSIX")
def test_a_bundled_binary_without_execute_permission_is_none(tmp_path):
    folder = _ext(tmp_path / "ext", "openai.chatgpt-26.1.1", "bin/linux-x86_64/codex")
    (folder / "bin/linux-x86_64/codex").chmod(0o644)
    assert vscode._binary("codex", folder, "linux", "x86_64") is None
    claude = _ext(tmp_path / "ext", "anthropic.claude-code-2.1.1", "resources/native-binary/claude")
    (claude / "resources/native-binary/claude").chmod(0o644)
    assert vscode._binary("claude", claude, "linux") is None



def test_codex_windows_window_with_the_wsl_switch_runs_the_linux_codex(vs, fake_runner, monkeypatch, tmp_path):
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)
    win = tmp_path / "c" / "Users" / "ada"
    settings = wsl.vscode_settings(win)
    settings.parent.mkdir(parents=True)
    settings.write_text('{"chatgpt.runCodexInWindowsSubsystemForLinux": true}')
    folder = _ext(win / ".vscode" / "extensions", "openai.chatgpt-26.715.61943-win32-x64",
                  f"bin/windows-{host_arch()}/codex.exe", linux_codex_bin())
    (ext,) = vscode.extensions({"codex": True}, "linux", win_home=win)
    assert ext.binary == folder / linux_codex_bin()
    fake_runner.missing.add("codex")
    rows = check._vscode_surfaces(_cs(win))
    assert any("plugins do not load" in r.detail for r in rows)


@pytest.mark.parametrize("os_name,present,expected", [("linux", ["claude.exe"], None), ("windows", ["claude"], None),
                                                      ("windows", ["claude", "claude.exe"], "claude.exe")])
def test_claude_binary_matches_the_target_os(tmp_path, os_name, present, expected):
    folder = _ext(tmp_path / "ext", "anthropic.claude-code-2.1.1", *[f"resources/native-binary/{n}" for n in present])
    found = vscode._binary("claude", folder, os_name)
    assert (found.name if found else None) == expected


def test_a_windows_wrapper_path_is_checked_through_its_wsl_mount(vs, fake_runner, monkeypatch, tmp_path):
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)
    monkeypatch.setattr(wsl, "MOUNT", str(tmp_path / "mnt") + "/")
    win = tmp_path / "mnt" / "c" / "Users" / "ana"
    exe = win / "bin" / "claude.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("x")
    settings = wsl.vscode_settings(win)
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"claudeCode.claudeProcessWrapper": "C:\\Users\\ana\\bin\\claude.exe"}))
    _ext(win / ".vscode" / "extensions", "anthropic.claude-code-2.1.217-win32-x64")
    (win / ".claude" / "rules" / "loadout").mkdir(parents=True)
    (row,) = check._vscode_surfaces(_cs(win))
    assert row.ok


def test_a_project_can_switch_off_an_inherited_codex_server(vs, tmp_path):
    paths.codex_home().mkdir()
    project = tmp_path / "repo"
    (project / ".codex").mkdir(parents=True)
    (paths.codex_home() / "config.toml").write_text(
        f'[mcp_servers.s]\ncommand = "tool"\n[projects.{json.dumps(str(project.resolve()))}]\ntrust_level = "trusted"\n')
    (project / ".codex" / "config.toml").write_text('[mcp_servers.s]\nenabled = false\n')
    assert vscode.mcp_commands("codex", project) == {}


def test_terminal_mode_on_windows_needs_claude_on_path(vs, fake_runner, monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    user = tmp_path / "Roaming" / "Code" / "User"
    user.mkdir(parents=True)
    (user / "settings.json").write_text('{"claudeCode.useTerminal": true}')
    _ext(vs / ".vscode" / "extensions", "anthropic.claude-code-2.1.217-win32-x64", "resources/native-binary/claude.exe")
    fake_runner.missing.add("claude")
    (row,) = [r for e in vscode.extensions({"claude": True}, "win32") for r in check._surface_rows(e)]
    assert not row.ok and "terminal" in row.detail and "PATH" in row.detail


def test_a_settings_file_that_does_not_parse_is_reported(vs, fake_runner):
    import sys
    _ext(vs / ".vscode" / "extensions", "anthropic.claude-code-2.1.217-linux-x64",
         "resources/native-binary/claude.exe" if sys.platform == "win32" else "resources/native-binary/claude")
    user = vscode._user_dir(vs, sys.platform)
    user.mkdir(parents=True)
    (user / "settings.json").write_text('{"a": ')
    rows = check._vscode_surfaces()
    bad = [r for r in rows if r.name == "VS Code settings"]
    assert len(bad) == 1 and not bad[0].ok and bad[0].severity == "warn" and "does not parse" in bad[0].detail


@pytest.mark.skipif(__import__("os").name == "nt", reason="execute permission is POSIX")
def test_a_wrapper_without_execute_permission_does_not_count(vs, fake_runner, tmp_path):
    import sys
    _ext(vs / ".vscode" / "extensions", "anthropic.claude-code-2.1.217-linux-x64")
    wrapper = tmp_path / "claude"
    wrapper.write_text("x")
    wrapper.chmod(0o644)
    user = vscode._user_dir(vs, sys.platform)
    user.mkdir(parents=True)
    (user / "settings.json").write_text(json.dumps({"claudeCode.claudeProcessWrapper": str(wrapper)}))
    (row,) = check._vscode_surfaces()
    assert not row.ok


def _windows_terminal_mode(tmp_path):
    win = tmp_path / "c" / "Users" / "ada"
    settings = wsl.vscode_settings(win)
    settings.parent.mkdir(parents=True)
    settings.write_text('{"claudeCode.useTerminal": true}')
    _ext(win / ".vscode" / "extensions", "anthropic.claude-code-2.1.217-win32-x64", "resources/native-binary/claude.exe")
    (win / ".claude" / "rules" / "loadout").mkdir(parents=True)
    return win


def test_terminal_mode_in_vscode_on_windows_seen_from_wsl(vs, monkeypatch, tmp_path):
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)
    win = _windows_terminal_mode(tmp_path)
    (row,) = check._vscode_surfaces(_cs(win))
    assert not row.ok and "terminal" in row.detail and "may not find" in row.detail


@pytest.mark.parametrize("where", [".local/bin/claude.exe", "AppData/Roaming/npm/claude.cmd"])
def test_terminal_mode_in_vscode_on_windows_with_an_installed_claude(vs, monkeypatch, tmp_path, where):
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)
    win = _windows_terminal_mode(tmp_path)
    (win / where).parent.mkdir(parents=True, exist_ok=True)
    (win / where).write_text("x")
    (row,) = check._vscode_surfaces(_cs(win))
    assert row.ok


def test_settings_come_from_the_user_settings_only_never_a_profile(vs, tmp_path):
    user = vs / ".config" / "Code" / "User"
    (user / "profiles" / "aaa").mkdir(parents=True)
    (user / "profiles" / "aaa" / "settings.json").write_text('{"claudeCode.useTerminal": true}')
    (install,) = vscode.installs("linux")
    assert vscode.setting(install, "claudeCode.useTerminal") is None  # which profile is active is not known
    (user / "settings.json").write_text('{"claudeCode.useTerminal": false}')
    assert vscode.setting(install, "claudeCode.useTerminal") is False


def test_usable_terminal_mode_is_a_way_to_start_claude(vs, fake_runner, monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    user = tmp_path / "Roaming" / "Code" / "User"
    user.mkdir(parents=True)
    (user / "settings.json").write_text('{"claudeCode.useTerminal": true}')
    _ext(vs / ".vscode" / "extensions", "anthropic.claude-code-2.1.217-win32-x64")  # no bundled claude.exe
    fake_runner.paths["claude"] = "C:/Users/a/.local/bin/claude.exe"
    (row,) = [r for e in vscode.extensions({"claude": True}, "win32") for r in check._surface_rows(e)]
    assert row.ok


@pytest.mark.skipif(__import__("os").name == "nt", reason="a /mnt/<drive> path is a WSL path")
def test_a_windows_codex_shim_in_wsl_is_not_the_wsl_codex_cli(vs, fake_runner, monkeypatch, tmp_path):
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)
    monkeypatch.setattr(wsl, "windows_home", lambda: None)
    _ext(vs / ".vscode-server" / "extensions", "openai.chatgpt-26.715.61943-linux-x64", linux_codex_bin())
    fake_runner.paths["codex"] = "/mnt/c/Users/a/AppData/Roaming/npm/codex"
    rows = check._vscode_surfaces(_cs(None))
    assert any("plugins do not load" in r.detail for r in rows)



def test_an_untrusted_projects_codex_servers_do_not_count(vs, tmp_path):
    paths.codex_home().mkdir()
    (paths.codex_home() / "config.toml").write_text('[mcp_servers.s]\ncommand = "tool"\n')
    project = tmp_path / "repo"
    (project / ".codex").mkdir(parents=True)
    (project / ".codex" / "config.toml").write_text('[mcp_servers.p]\ncommand = "projtool"\n[mcp_servers.s]\nenabled = false\n')
    assert vscode.mcp_commands("codex", project) == {"s": "tool"}  # Codex ignores an untrusted project's layer


def test_local_codex_extension_mcp_command_not_on_the_shell_path(vs, fake_runner):
    _ext(vs / ".vscode" / "extensions", "openai.chatgpt-26.715.61943-linux-x64", host_codex_bin())
    fake_runner.paths["codex"] = "/usr/bin/codex"
    paths.codex_home().mkdir()
    (paths.codex_home() / "config.toml").write_text('[mcp_servers.gone]\ncommand = "nosuchtool"\n')
    (row,) = [r for r in check._vscode_surfaces() if r.name == "VS Code PATH"]
    assert "gone" in row.detail and "Codex" in row.detail


def test_claude_extension_mcp_commands_are_checked_too(vs, fake_runner):
    _ext(vs / ".vscode" / "extensions", "anthropic.claude-code-2.1.217-linux-x64", host_claude_bin())
    paths.claude_json().write_text(json.dumps({"mcpServers": {"mine": {"command": "nosuchtool"}}}))
    fake_runner.paths.update({"serena": "/x/serena", "codebase-memory-mcp": "/x/cbm"})
    (row,) = [r for r in check._vscode_surfaces() if r.name == "VS Code PATH"]
    assert "mine" in row.detail and "Claude Code" in row.detail and "serena" not in row.detail


def test_a_found_command_gives_no_path_row(vs, fake_runner):
    _ext(vs / ".vscode" / "extensions", "openai.chatgpt-26.715.61943-linux-x64", host_codex_bin())
    fake_runner.paths.update({"codex": "/usr/bin/codex", "tool": "/usr/bin/tool"})
    paths.codex_home().mkdir()
    (paths.codex_home() / "config.toml").write_text('[mcp_servers.ok]\ncommand = "tool"\n')
    assert [r for r in check._vscode_surfaces() if r.name == "VS Code PATH"] == []
