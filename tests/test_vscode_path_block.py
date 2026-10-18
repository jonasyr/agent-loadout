"""bootstrap --vscode-path: loadout's tool folders on PATH for VS Code's Remote-WSL windows (spec Part 3.2)."""
import pytest

from loadout import backup, bootstrap, check, paths, vscode, wsl

pytestmark = pytest.mark.skipif(__import__("os").name == "nt", reason="a Remote-WSL server is a Linux folder")


@pytest.fixture
def server(fake_home, monkeypatch):
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)
    (fake_home / ".vscode-server").mkdir()
    for d in (".local/bin", ".local/share/mise/shims"):
        (fake_home / d).mkdir(parents=True)
    return fake_home / vscode.SERVER_ENV


def test_vscode_path_creates_the_file_and_restore_removes_it(server):
    bk = backup.Backup(description="t")
    line = bootstrap.setup_vscode_path(bk)
    assert line.startswith("created") and bootstrap.PATH_MARKER in server.read_text()
    dirs = vscode.remote_path_dirs()
    assert dirs[:2] == [str(paths.home() / ".local/bin"), str(paths.home() / ".local/share/mise/shims")]
    _, ok, _ = backup.restore(bk.root)
    assert ok and not server.exists()


def test_vscode_path_keeps_a_file_without_trailing_newline(server):
    mine = b"# mine\r\nexport FOO=1"
    server.write_bytes(mine)
    bk = backup.Backup(description="t")
    assert bootstrap.setup_vscode_path(bk).startswith("added")
    assert server.read_bytes().startswith(mine + b"\n" + bootstrap.PATH_MARKER.encode())
    _, ok, _ = backup.restore(bk.root)
    assert ok and server.read_bytes() == mine


def test_vscode_path_twice_changes_nothing(server):
    bootstrap.setup_vscode_path(backup.Backup(description="t"))
    before = server.read_bytes()
    bk = backup.Backup(description="t2")
    assert bootstrap.setup_vscode_path(bk) == ""
    assert server.read_bytes() == before and bk.empty


def test_vscode_path_refreshes_its_block(server, fake_home):
    (fake_home / ".local/share/mise/shims").rmdir()
    server.write_text("export A=1\n")
    bootstrap.setup_vscode_path(backup.Backup(description="t"))
    (fake_home / ".local/share/mise/shims").mkdir()
    server.write_text(server.read_text() + "export B=2\n")
    assert bootstrap.setup_vscode_path(backup.Backup(description="t2")).startswith("updated")
    text = server.read_text()
    assert text.startswith("export A=1\n") and text.endswith("export B=2\n") and ".local/share/mise/shims" in text
    assert text.count(bootstrap.PATH_MARKER + "\n") == 1


def test_flag_writes_without_asking(server, fake_runner, capsys):
    bootstrap._vscode_path_step(lambda q: pytest.fail("asked"), False, True, backup.Backup(description="t"))
    assert server.is_file() and "WSL: Restart" in capsys.readouterr().out


def test_terminal_asks_and_no_leaves_it(server, fake_runner):
    asked = []
    bootstrap._vscode_path_step(lambda q: asked.append(q) or "n", True, False, backup.Backup(description="t"))
    assert asked and bootstrap.SERVER_ENV_QUESTION.strip() in asked[0] and not server.exists()


def test_no_terminal_no_flag_writes_nothing(server, fake_runner):
    bootstrap._vscode_path_step(lambda q: pytest.fail("asked"), False, False, backup.Backup(description="t"))
    assert not server.exists()


def test_no_question_when_the_folders_are_already_on_the_remote_path(server, fake_home, fake_runner):
    server.write_text('export PATH="$HOME/.local/bin:$HOME/.local/share/mise/shims:$PATH"\n')
    bootstrap._vscode_path_step(lambda q: pytest.fail("asked"), True, False, backup.Backup(description="t"))
    assert bootstrap.PATH_MARKER not in server.read_text()


def test_flag_outside_wsl_says_nothing_changed(fake_home, fake_runner, capsys):
    bootstrap._vscode_path_step(lambda q: pytest.fail("asked"), False, True, backup.Backup(description="t"))
    assert "nothing changed" in capsys.readouterr().out and not (fake_home / vscode.SERVER_ENV).exists()


def test_check_names_the_flag(server, fake_home, monkeypatch):
    monkeypatch.setattr(vscode, "mcp_commands", lambda *a, **k: {"serena": "serena"})
    ext = vscode.Extension("codex", vscode.Install("remote-wsl", None, fake_home / ".vscode-server/extensions"),
                           fake_home, "26.1", None)
    rows = check._vscode_path([ext])
    assert rows and "loadout bootstrap --vscode-path" in rows[0].fix


def test_a_users_conditional_case_arm_is_not_read_as_path(server, fake_home):
    server.write_text('case "$TERM" in xterm*) PATH=/opt/x ;; esac\n')
    assert vscode.remote_path_dirs() == list(vscode.SYSTEM_DIRS)
    server.write_text('case $X in a*) PATH="$HOME/.local/bin:$PATH" ;; esac\n')
    assert str(fake_home / ".local/bin") not in vscode.remote_path_dirs()


def test_vscode_path_adds_to_an_existing_file_atomically(server, monkeypatch):
    """The live file is never opened for append: a cut-off write must not leave half a block in it."""
    mine = b"export FOO=1\n"
    server.write_bytes(mine)
    real_open = type(server).open

    def no_append(self, mode="r", *a, **k):
        if self == server and "a" in mode:
            raise AssertionError("appended to the live file")
        return real_open(self, mode, *a, **k)
    monkeypatch.setattr(type(server), "open", no_append)
    assert bootstrap.setup_vscode_path(backup.Backup(description="t")).startswith("added")
    assert server.read_bytes().startswith(mine + bootstrap.PATH_MARKER.encode())
