"""Which home each VS Code window reads, the PATH of a Remote-WSL window, the MCP commands (spec Part 1)."""
import json
from pathlib import Path

import pytest

from loadout import paths, vscode, wsl


@pytest.fixture
def vs(fake_home, fake_runner, monkeypatch):
    for var in ("APPDATA", "XDG_CONFIG_HOME", "VSCODE_EXTENSIONS"):
        monkeypatch.delenv(var, raising=False)
    return fake_home


def _install(where: str, root: Path) -> vscode.Install:
    return vscode.Install(where, None if where == "remote-wsl" else root / "User", root / ".vscode" / "extensions")


def _ext(agent: str, install: vscode.Install) -> vscode.Extension:
    return vscode.Extension(agent, install, install.extensions / "x-1.0.0", "1.0.0", None)


def test_local_and_remote_windows_read_the_homes_loadout_set_up(vs):
    for where in ("local", "remote-wsl"):
        assert vscode.reads_home(_ext("claude", _install(where, vs))) == paths.claude_home()
        assert vscode.reads_home(_ext("codex", _install(where, vs))) == paths.codex_home()


def test_windows_window_reads_the_windows_homes(vs, tmp_path):
    win = tmp_path / "c" / "Users" / "ada"
    install = vscode.Install("windows", win / "AppData/Roaming/Code/User", win / ".vscode" / "extensions")
    assert vscode.reads_home(_ext("claude", install)) == win / ".claude"
    assert vscode.reads_home(_ext("codex", install)) == win / ".codex"


def test_windows_window_with_the_wsl_switch_reads_the_wsl_codex_home(vs, tmp_path):
    win = tmp_path / "c" / "Users" / "ada"
    settings = wsl.vscode_settings(win)
    settings.parent.mkdir(parents=True)
    settings.write_text('{"chatgpt.runCodexInWindowsSubsystemForLinux": true}')
    install = vscode.Install("windows", settings.parent, win / ".vscode" / "extensions")
    assert vscode.reads_home(_ext("codex", install)) == paths.codex_home()
    assert vscode.reads_home(_ext("claude", install)) == win / ".claude"  # the switch is Codex's only


def test_remote_path_is_the_system_folders_without_server_env_setup(vs):
    assert vscode.remote_path_dirs() == list(vscode.SYSTEM_DIRS)


def test_remote_path_adds_what_server_env_setup_exports(vs):
    env = vs / vscode.SERVER_ENV
    env.parent.mkdir(parents=True)
    env.write_text('export PATH="$HOME/.local/bin:${HOME}/.local/share/mise/shims:~/bin:$PATH"\n# PATH=/nope\n')
    dirs = vscode.remote_path_dirs()
    home = str(vs)
    assert f"{home}/.local/bin" in dirs and f"{home}/.local/share/mise/shims" in dirs and f"{home}/bin" in dirs
    assert "/nope" not in dirs and "$PATH" not in dirs


def test_findable(tmp_path):
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "serena").write_text("x")
    (tmp_path / "bin" / "serena").chmod(0o755)
    assert vscode.findable("serena", [str(tmp_path / "bin")])
    assert vscode.findable(str(tmp_path / "bin" / "serena"), [])
    assert not vscode.findable("uvx", [str(tmp_path / "bin")])
    assert not vscode.findable(str(tmp_path / "missing"), [str(tmp_path / "bin")])


def test_mcp_commands_for_codex_from_config_toml(vs):
    paths.codex_home().mkdir()
    (paths.codex_home() / "config.toml").write_text(
        '[mcp_servers.serena]\ncommand = "/home/USER/.local/bin/serena"\nargs = ["start-mcp-server"]\n'
        '[mcp_servers.web]\nurl = "https://example.com/mcp"\n')
    assert vscode.mcp_commands("codex") == {"serena": "/home/USER/.local/bin/serena"}  # url servers start nothing


def test_mcp_commands_for_claude_from_claude_json_and_the_plugin(vs):
    paths.claude_json().write_text(json.dumps({"mcpServers": {"mine": {"command": "uvx", "args": ["x"]},
                                                              "remote": {"type": "http", "url": "https://e"}}}))
    found = vscode.mcp_commands("claude")
    assert found["mine"] == "uvx" and "remote" not in found
    assert found["serena"] == "serena" and found["codebase-memory-mcp"] == "codebase-memory-mcp"  # the plugin's


@pytest.mark.parametrize("text", ["not toml [[[", '[mcp_servers]\nserena = 3\n'])
def test_mcp_commands_survive_a_broken_config(vs, text):
    paths.codex_home().mkdir()
    (paths.codex_home() / "config.toml").write_text(text)
    assert vscode.mcp_commands("codex") == {}
