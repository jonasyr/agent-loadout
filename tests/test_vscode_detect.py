"""vscode.py finds VS Code, the agents' extensions and their bundled binaries, read-only (spec Part 1)."""
from pathlib import Path

import pytest

from conftest import linux_codex_bin

from loadout import runner, vscode, wsl


LINUX_BIN = linux_codex_bin()


@pytest.fixture
def vs(fake_home, fake_runner, monkeypatch):
    for var in ("APPDATA", "XDG_CONFIG_HOME", "VSCODE_EXTENSIONS"):
        monkeypatch.delenv(var, raising=False)  # never the real VS Code folders
    return fake_home


def _ext(root: Path, name: str, binary: str | None = None) -> Path:
    folder = root / name
    folder.mkdir(parents=True)
    if binary:
        (folder / binary).parent.mkdir(parents=True, exist_ok=True)
        (folder / binary).write_text("bin")
    return folder


def test_local_install_on_linux_and_macos(vs):
    (vs / ".vscode" / "extensions").mkdir(parents=True)
    linux = vscode.installs("linux")
    assert [(i.where, i.user_dir, i.extensions) for i in linux] == [
        ("local", vs / ".config" / "Code" / "User", vs / ".vscode" / "extensions")]
    assert vscode.installs("darwin")[0].user_dir == vs / "Library" / "Application Support" / "Code" / "User"


def test_local_install_on_windows_uses_appdata(vs, monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    (tmp_path / "Roaming" / "Code" / "User").mkdir(parents=True)
    assert vscode.installs("win32")[0].user_dir == tmp_path / "Roaming" / "Code" / "User"


def test_no_vscode_no_install(vs):
    assert vscode.installs("linux") == []


def test_vscode_extensions_variable_is_honoured(vs, monkeypatch, tmp_path):
    monkeypatch.setenv("VSCODE_EXTENSIONS", str(tmp_path / "ext"))
    (tmp_path / "ext").mkdir()
    assert vscode.installs("linux")[0].extensions == tmp_path / "ext"


def test_wsl_sees_the_windows_install_and_the_remote_server(vs, monkeypatch, tmp_path):
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)
    win = tmp_path / "c" / "Users" / "ada"
    (win / ".vscode" / "extensions").mkdir(parents=True)
    (vs / ".vscode-server" / "extensions").mkdir(parents=True)
    found = {i.where: i for i in vscode.installs("linux", win_home=win)}
    assert set(found) == {"windows", "remote-wsl"}
    assert found["windows"].user_dir == win / "AppData" / "Roaming" / "Code" / "User"
    assert found["remote-wsl"].extensions == vs / ".vscode-server" / "extensions"


def test_newest_version_folder_by_number(tmp_path):
    for v in ("2.1.9", "2.1.10", "2.1.217-linux-x64"):
        (tmp_path / f"anthropic.claude-code-{v}").mkdir()
    (tmp_path / "anthropic.claude-code-notaversion").mkdir()
    (tmp_path / "other.ext-9.9.9").mkdir()
    folder, version = vscode.newest(tmp_path, "anthropic.claude-code")
    assert version == "2.1.217" and folder.name == "anthropic.claude-code-2.1.217-linux-x64"
    assert vscode.newest(tmp_path / "missing", "anthropic.claude-code") is None


def test_extensions_with_their_bundled_binaries(vs):
    root = vs / ".vscode" / "extensions"
    _ext(root, "anthropic.claude-code-2.1.217-linux-x64", "resources/native-binary/claude")
    _ext(root, "openai.chatgpt-26.715.61943-linux-x64", LINUX_BIN)
    found = {e.agent: e for e in vscode.extensions({"claude": True, "codex": True}, "linux")}
    assert found["claude"].binary == root / "anthropic.claude-code-2.1.217-linux-x64/resources/native-binary/claude"
    assert found["claude"].version == "2.1.217"
    assert found["codex"].binary.name == "codex"
    assert vscode.row_name(found["codex"]) == "VS Code (Codex)"


def test_an_agent_that_is_off_is_not_read(vs):
    root = vs / ".vscode" / "extensions"
    _ext(root, "openai.chatgpt-26.715.61943-linux-x64", LINUX_BIN)
    assert vscode.extensions({"claude": True, "codex": False}, "linux") == []


def test_missing_binary_is_none(vs):
    _ext(vs / ".vscode" / "extensions", "openai.chatgpt-26.715.61943-linux-x64")
    (ext,) = vscode.extensions({"codex": True}, "linux")
    assert ext.binary is None


def test_bundled_codex_version_and_age(vs, fake_runner):
    _ext(vs / ".vscode" / "extensions", "openai.chatgpt-26.715.61943-linux-x64", LINUX_BIN)
    (ext,) = vscode.extensions({"codex": True}, "linux")
    fake_runner.responses[(str(ext.binary), "--version")] = runner.Result(0, "codex-cli 0.145.0-alpha.27\n", "")
    assert vscode.bundled_version(ext) == "0.145.0"
    assert fake_runner.calls[-1] == [str(ext.binary), "--version"]
    assert vscode.too_old("0.145.0") and not vscode.too_old("0.161.0") and not vscode.too_old("1.0.0")


def test_bundled_codex_without_a_version_is_unknown(vs, fake_runner):
    _ext(vs / ".vscode" / "extensions", "openai.chatgpt-26.715.61943-linux-x64", LINUX_BIN)
    (ext,) = vscode.extensions({"codex": True}, "linux")
    fake_runner.responses[(str(ext.binary), "--version")] = runner.Result(124, "", "timed out")
    assert vscode.bundled_version(ext) is None


def test_claude_version_is_the_extension_version_without_running_it(vs, fake_runner):
    _ext(vs / ".vscode" / "extensions", "anthropic.claude-code-2.1.217-linux-x64", "resources/native-binary/claude")
    (ext,) = vscode.extensions({"claude": True}, "linux")
    assert vscode.bundled_version(ext) == "2.1.217" and fake_runner.calls == []


@pytest.mark.parametrize("raw", [
    b'{\n  // a comment\n  "a": 1, /* block */ "b": [1, 2,],\n}\n',
    b'\xef\xbb\xbf{"a": 1, "b": [1, 2]}',
    b'{\r\n\t"a": 1,\r\n\t"b": [1, 2]\r\n}\r\n',
])
def test_read_jsonc_accepts_what_vscode_accepts(tmp_path, raw):
    path = tmp_path / "settings.json"
    path.write_bytes(raw)
    assert vscode.read_jsonc(path) == {"a": 1, "b": [1, 2]}


@pytest.mark.parametrize("raw", [b"{not json", b"[1, 2]", b"\xff\xfe", b""])
def test_read_jsonc_gives_none_for_what_it_cannot_read(tmp_path, raw):
    path = tmp_path / "settings.json"
    path.write_bytes(raw)
    assert vscode.read_jsonc(path) is None
    assert vscode.read_jsonc(tmp_path / "missing.json") is None


def test_comment_markers_inside_strings_stay(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"url": "https://example.com/a,]", "b": 1}')
    assert vscode.read_jsonc(path) == {"url": "https://example.com/a,]", "b": 1}


def test_setting_reads_the_user_settings(vs):
    user = vs / ".config" / "Code" / "User"
    user.mkdir(parents=True)
    (user / "settings.json").write_text('{"claudeCode.claudeProcessWrapper": "/opt/claude"}')
    (install,) = vscode.installs("linux")
    assert vscode.setting(install, "claudeCode.claudeProcessWrapper") == "/opt/claude"
    assert vscode.setting(install, "claudeCode.useTerminal") is None
    assert vscode.settings_files(install) == [user / "settings.json"]
