from loadout import paths, recommend, runner, vscode, wsl
from loadout.recommend import Cell

BOTH = {"claude": True, "codex": True}
CLAUDE = {"claude": True, "codex": False}


def _linux(monkeypatch):
    monkeypatch.setattr(wsl, "detect", lambda: None)
    monkeypatch.setattr(paths, "platform_key", lambda: "posix")


def _wsl(monkeypatch):
    monkeypatch.setattr(wsl, "detect", lambda: 2)
    monkeypatch.setattr(paths, "platform_key", lambda: "posix")


def test_matrix_pins_every_flag():
    for key in recommend.matrix_keys():
        assert recommend.FLAGS[key] == recommend.matrix_flags(key), key


def test_every_matrix_cell_has_flags():
    assert set(recommend.matrix_keys()) == set(recommend.FLAGS)


def test_cell_linux_cli(fake_home, fake_runner, monkeypatch):
    _linux(monkeypatch)
    cell = recommend.detect(BOTH, found=[])
    assert cell == Cell("linux", ("claude", "codex"), "cli", None)
    assert recommend.flags(cell) == "--install --agents claude,codex"
    assert recommend.anchor(cell).endswith("#linux-and-macos")
    assert recommend.describe(cell) == "Linux · Claude Code + Codex · CLI"


def test_cell_none_falls_back_to_cli_row(fake_home, fake_runner, monkeypatch):
    _linux(monkeypatch)
    fake_runner.missing |= {"claude", "codex"}
    cell = recommend.detect(CLAUDE, found=[])
    assert cell.surface == "none"
    assert recommend.flags(cell) == "--install --agents claude"
    assert "no CLI or VS Code extension found yet" in recommend.describe(cell)


def test_cell_wsl_codex_windows_side(fake_home, fake_runner, monkeypatch):
    _wsl(monkeypatch)
    cell = recommend.detect(BOTH, cs=wsl.CodexSide("windows"), found=[])
    assert cell == Cell("wsl", ("claude", "codex"), "cli", "windows")
    assert recommend.flags(cell) == "--install --agents claude,codex --codex-side windows"
    assert recommend.anchor(cell).endswith("#codex-on-windows-or-on-both-sides")


def test_wsl_claude_only_uses_wsl_table(fake_home, fake_runner, monkeypatch):
    _wsl(monkeypatch)
    cell = recommend.detect(CLAUDE, cs=wsl.CodexSide("windows"), found=[])
    assert cell.codex_side is None
    assert recommend.flags(cell) == "--install --agents claude"
    assert recommend.anchor(cell).endswith("#wsl-2")


def test_codex_windows_override(fake_home, fake_runner, monkeypatch):
    _wsl(monkeypatch)
    cell = recommend.detect(BOTH, cs=wsl.CodexSide("wsl"), codex_windows=True, found=[])
    assert cell.codex_side == "windows"


def test_codex_both_sides(fake_home, fake_runner, monkeypatch):
    _wsl(monkeypatch)
    cell = recommend.detect(BOTH, cs=wsl.CodexSide("both"), found=[])
    assert recommend.flags(cell) == "--install --agents claude,codex"


def test_codex_off_reads_no_codex_extension(fake_home, fake_runner, monkeypatch):
    _linux(monkeypatch)
    seen = []
    monkeypatch.setattr(vscode, "extensions", lambda on, **kw: seen.append(dict(on)) or [])
    recommend.detect(CLAUDE)
    assert seen and seen[0]["codex"] is False


def _ext(agent, where):
    ins = vscode.Install(where, None, fake_path())
    return vscode.Extension(agent, ins, fake_path(), "1.0.0", None)


def fake_path():
    from pathlib import Path
    return Path("/nonexistent")


def test_wsl_windows_window(fake_home, fake_runner, monkeypatch):
    _wsl(monkeypatch)
    monkeypatch.setattr(vscode, "runs_in_wsl", lambda e: False)
    cell = recommend.detect(BOTH, found=[_ext("codex", "windows")])
    assert cell.surface == "windows-window"
    assert recommend.flags(cell) == "--install --agents claude,codex --vscode-wsl"
    claude = recommend.detect(CLAUDE, found=[_ext("claude", "windows")])
    assert recommend.flags(claude) == "--install --agents claude"
    remote = recommend.detect(BOTH, found=[_ext("codex", "windows"), _ext("claude", "remote-wsl")])
    assert remote.surface == "vscode+cli"


def test_extension_with_and_without_cli(fake_home, fake_runner, monkeypatch):
    _linux(monkeypatch)
    ext = [_ext("claude", "local")]
    assert recommend.detect(CLAUDE, found=ext).surface == "vscode+cli"
    fake_runner.missing.add("claude")
    assert recommend.detect(CLAUDE, found=ext).surface == "vscode"


def test_cell_native_windows(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(wsl, "detect", lambda: None)
    monkeypatch.setattr(paths, "platform_key", lambda: "windows")
    cell = recommend.detect(CLAUDE, found=[])
    assert cell.platform == "windows"
    assert "(experimental)" in recommend.describe(cell)
    assert recommend.flags(cell) == "--install --agents claude"
    assert recommend.anchor(cell).endswith("#native-windows-experimental")


def test_differences(fake_home, fake_runner, monkeypatch):
    _linux(monkeypatch)
    cell = Cell("linux", ("claude", "codex"), "cli", None)
    wcell = Cell("wsl", ("claude", "codex"), "windows-window", None)
    b = recommend.differences(wcell, BOTH, False)
    assert len(b) == 1 and "--vscode-wsl" in b[0]
    assert recommend.differences(wcell, BOTH, True) == []
    c = recommend.differences(Cell("linux", ("claude",), "cli", None), CLAUDE, False)
    assert len(c) == 1 and "Codex CLI is on PATH" in c[0] and "not chosen" in c[0]
    fake_runner.missing.add("codex")
    assert recommend.differences(cell, BOTH, False) == []


def test_windows_side_has_no_vscode_wsl_difference(fake_home, fake_runner):
    # review #1: the Codex-on-Windows cell recommends the Windows side; it must not also ask for --vscode-wsl
    cell = Cell("wsl", ("codex",), "windows-window", "windows")
    lines = recommend.differences(cell, {"claude": False, "codex": True}, False)
    assert not any("--vscode-wsl" in line for line in lines)


def test_wsl_1_is_a_wsl_cell(fake_home, fake_runner, monkeypatch):
    # Codex review on #70: WSL 1 is WSL, not Linux (its own WSL row tells the user to move to WSL 2)
    monkeypatch.setattr(wsl, "detect", lambda: 1)
    cell = recommend.detect({"claude": True, "codex": False}, found=[])
    assert cell.platform == "wsl" and recommend.anchor(cell).endswith("#wsl-2")
