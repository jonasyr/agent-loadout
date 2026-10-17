"""loadout check: a row per agent extension and window type, the Remote-WSL PATH, a committed .mcp.json with a
person's home path (spec Part 4). Every row is a warning; nothing is changed."""
import json
import sys
from pathlib import Path

import pytest

from loadout import check, runner, targets, vscode, wsl


@pytest.fixture
def vs(fake_home, fake_runner, monkeypatch):
    for var in ("APPDATA", "XDG_CONFIG_HOME", "VSCODE_EXTENSIONS"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(targets, "OVERRIDE", {"claude": True, "codex": True})
    return fake_home


def _ext(root: Path, name: str, binary: str | None = None) -> Path:
    folder = root / name
    folder.mkdir(parents=True)
    if binary:
        (folder / binary).parent.mkdir(parents=True, exist_ok=True)
        (folder / binary).write_text("bin")
    return folder


def _codex_ext(vs, fake_runner, version="0.162.1", root=None):
    root = root or vs / ".vscode" / "extensions"
    folder = _ext(root, "openai.chatgpt-26.715.61943-linux-x64", "bin/linux-x86_64/codex")
    fake_runner.responses[(str(folder / "bin/linux-x86_64/codex"), "--version")] = runner.Result(
        0, f"codex-cli {version}\n", "")
    return folder


def _rows(results, prefix="VS Code ("):
    return [r for r in results if r.name.startswith(prefix)]


def test_no_vscode_no_rows(vs):
    assert check._vscode_surfaces() == []


def test_codex_extension_with_the_cli_is_ok(vs, fake_runner):
    _codex_ext(vs, fake_runner)
    fake_runner.paths["codex"] = "/usr/bin/codex"
    (row,) = check._vscode_surfaces()
    assert (row.name, row.ok) == ("VS Code (Codex)", True)


def test_codex_extension_without_the_cli_names_what_is_missing_and_the_fix(vs, fake_runner):
    _codex_ext(vs, fake_runner)
    fake_runner.missing.add("codex")
    (row,) = check._vscode_surfaces()
    assert not row.ok and row.severity == "warn"
    assert "plugins do not load" in row.detail and "/hooks" in row.detail
    assert "Codex CLI alongside VS Code" in row.fix and "loadout bootstrap --install" in row.fix


def test_old_bundled_codex_warns_with_the_update_fix(vs, fake_runner):
    _codex_ext(vs, fake_runner, version="0.145.0-alpha.27")
    fake_runner.paths["codex"] = "/usr/bin/codex"
    (row,) = check._vscode_surfaces()
    assert not row.ok and "0.145.0" in row.detail and "0.161" in row.detail
    assert "update the Codex extension" in row.fix


def test_bundled_codex_that_gives_no_version_is_not_reported(vs, fake_runner):
    folder = _codex_ext(vs, fake_runner)
    fake_runner.responses[(str(folder / "bin/linux-x86_64/codex"), "--version")] = runner.Result(124, "", "")
    fake_runner.paths["codex"] = "/usr/bin/codex"
    (row,) = check._vscode_surfaces()
    assert row.ok


def test_claude_extension_with_its_bundled_binary_is_ok(vs, fake_runner):
    _ext(vs / ".vscode" / "extensions", "anthropic.claude-code-2.1.217-linux-x64", "resources/native-binary/claude")
    fake_runner.missing.add("claude")
    (row,) = check._vscode_surfaces()
    assert (row.name, row.ok) == ("VS Code (Claude Code)", True)


def test_claude_extension_without_any_binary_warns(vs, fake_runner):
    _ext(vs / ".vscode" / "extensions", "anthropic.claude-code-2.1.217-linux-x64")
    fake_runner.missing.add("claude")
    (row,) = check._vscode_surfaces()
    assert not row.ok and "no bundled Claude Code" in row.detail and "claudeProcessWrapper" in row.fix


def test_claude_extension_without_a_binary_but_with_a_wrapper_is_ok(vs, fake_runner):
    _ext(vs / ".vscode" / "extensions", "anthropic.claude-code-2.1.217-linux-x64")
    user = vscode._user_dir(vs, sys.platform)  # where this OS keeps VS Code's user settings
    user.mkdir(parents=True)
    wrapper = vs / "opt" / "claude"
    wrapper.parent.mkdir()
    wrapper.write_text("x")
    (user / "settings.json").write_text(json.dumps({"claudeCode.claudeProcessWrapper": str(wrapper)}))
    fake_runner.missing.add("claude")
    (row,) = check._vscode_surfaces()
    assert row.ok


def test_agent_off_no_row(vs, fake_runner, monkeypatch):
    _codex_ext(vs, fake_runner)
    monkeypatch.setattr(targets, "OVERRIDE", {"claude": True, "codex": False})
    assert check._vscode_surfaces() == []
    assert not any(c[0].endswith("codex") for c in fake_runner.calls)  # the bundled binary was not run


def test_claude_in_a_windows_window_seen_from_wsl_reads_the_windows_home(vs, fake_runner, monkeypatch, tmp_path):
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)
    win = tmp_path / "c" / "Users" / "ada"
    _ext(win / ".vscode" / "extensions", "anthropic.claude-code-2.1.217-win32-x64",
         "resources/native-binary/claude.exe")
    (row,) = check._vscode_surfaces(type("CS", (), {"windows_home": win})())
    assert row.name == "VS Code (Claude Code, Windows window)" and not row.ok
    assert ".claude" in row.detail and "code ." in row.fix


def test_codex_in_a_windows_window_is_left_to_the_existing_vs_code_row(vs, fake_runner, monkeypatch, tmp_path):
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)
    win = tmp_path / "c" / "Users" / "ada"
    _codex_ext(vs, fake_runner, root=win / ".vscode" / "extensions")
    rows = check._vscode_surfaces(type("CS", (), {"windows_home": win})())
    assert [r.name for r in rows] == ["VS Code (Codex, Windows window)"]
    assert all("plugins do not load" not in r.detail for r in rows)  # its home and side: the existing "VS Code" row


def test_remote_wsl_codex_mcp_command_not_on_the_server_path(vs, fake_runner, monkeypatch, tmp_path):
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)
    monkeypatch.setattr(wsl, "windows_home", lambda: None)
    _codex_ext(vs, fake_runner, root=vs / ".vscode-server" / "extensions")
    fake_runner.paths["codex"] = "/usr/bin/codex"
    (vs / ".codex").mkdir()
    (vs / ".codex" / "config.toml").write_text('[mcp_servers.serena]\ncommand = "serena"\n')
    rows = check._vscode_surfaces()
    path = [r for r in rows if r.name == "VS Code PATH"]
    assert len(path) == 1 and not path[0].ok and path[0].severity == "warn"
    assert "may not find" in path[0].detail and "serena" in path[0].detail
    assert "server-env-setup" in path[0].fix


def test_remote_wsl_absolute_command_that_exists_is_fine(vs, fake_runner, monkeypatch):
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)
    monkeypatch.setattr(wsl, "windows_home", lambda: None)
    _codex_ext(vs, fake_runner, root=vs / ".vscode-server" / "extensions")
    fake_runner.paths["codex"] = "/usr/bin/codex"
    serena = vs / ".local" / "bin" / "serena"
    serena.parent.mkdir(parents=True)
    serena.write_text("x")
    serena.chmod(0o755)
    (vs / ".codex").mkdir()
    (vs / ".codex" / "config.toml").write_text(f'[mcp_servers.serena]\ncommand = "{serena.as_posix()}"\n')
    assert [r for r in check._vscode_surfaces() if r.name == "VS Code PATH"] == []


def _repo(tmp_path, monkeypatch, fake_runner, mcp: str | None, committed=True):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    if mcp is not None:
        (repo / ".mcp.json").write_text(mcp)
    monkeypatch.chdir(repo)
    fake_runner.responses[("git", "-C", str(repo), "ls-files", "--error-unmatch", ".mcp.json")] = runner.Result(
        0 if committed else 1, ".mcp.json\n" if committed else "", "")
    return repo


def test_committed_mcp_json_with_a_home_path_warns_and_names_only_the_server(vs, fake_runner, monkeypatch, tmp_path):
    _repo(tmp_path, monkeypatch, fake_runner, json.dumps({"mcpServers": {"serena": {
        "command": "/home/niko/.local/bin/serena",
        "args": ["start-mcp-server", "--project", "/home/niko/projects/x", "--token=sk-secret-1234567890"]}}}))
    (row,) = check._repo_mcp_paths()
    assert not row.ok and row.severity == "warn" and "serena" in row.detail and "/home/niko/" in row.detail
    assert "sk-secret" not in row.detail and "sk-secret" not in row.fix
    assert "local scope" in row.fix and "does not change" in row.fix


@pytest.mark.parametrize("cmd", ["C:\\Users\\Ana\\bin\\serena.exe", "/Users/ana/bin/serena"])
def test_windows_and_macos_home_paths_count_too(vs, fake_runner, monkeypatch, tmp_path, cmd):
    _repo(tmp_path, monkeypatch, fake_runner, json.dumps({"mcpServers": {"s": {"command": cmd}}}))
    (row,) = check._repo_mcp_paths()
    assert not row.ok


@pytest.mark.parametrize("mcp", [json.dumps({"mcpServers": {"s": {"command": "serena"}}}), "{not json",
                                 json.dumps({"mcpServers": ["x"]}), None])
def test_no_row_for_portable_broken_or_missing_mcp_json(vs, fake_runner, monkeypatch, tmp_path, mcp):
    _repo(tmp_path, monkeypatch, fake_runner, mcp)
    assert check._repo_mcp_paths() == []


def test_uncommitted_mcp_json_is_the_persons_own(vs, fake_runner, monkeypatch, tmp_path):
    _repo(tmp_path, monkeypatch, fake_runner, json.dumps({"mcpServers": {"s": {"command": "/home/a/x"}}}),
          committed=False)
    assert check._repo_mcp_paths() == []


def test_run_checks_includes_the_rows_and_never_exits_1_for_them(vs, fake_runner):
    _codex_ext(vs, fake_runner, version="0.145.0")
    fake_runner.missing.add("codex")
    results = check.run_checks()
    rows = _rows(results)
    assert rows and all(r.severity == "warn" for r in rows if not r.ok)


def test_repo_text_with_control_characters_is_shown_escaped(vs, fake_runner, monkeypatch, tmp_path):
    _repo(tmp_path, monkeypatch, fake_runner, json.dumps({"mcpServers": {"evil\x1b]0;pwned\x07": {
        "command": "/home/niko\x1b[2J/bin/serena"}}}))
    (row,) = check._repo_mcp_paths()
    assert "\x1b" not in row.detail and "\x07" not in row.detail


def test_mcp_server_names_from_config_are_shown_escaped(vs, fake_runner, monkeypatch):
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)
    monkeypatch.setattr(wsl, "windows_home", lambda: None)
    _codex_ext(vs, fake_runner, root=vs / ".vscode-server" / "extensions")
    fake_runner.paths["codex"] = "/usr/bin/codex"
    (vs / ".codex").mkdir()
    (vs / ".codex" / "config.toml").write_text('[mcp_servers."x\\u001b[31m"]\ncommand = "serena"\n')
    (row,) = [r for r in check._vscode_surfaces() if r.name == "VS Code PATH"]
    assert "\x1b" not in row.detail
