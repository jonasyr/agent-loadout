"""`loadout check` compares the codebase-memory-mcp binaries on PATH and the cache folders Claude Code's and
Codex's servers use (read only; only `--version` is run, through runner.run)."""
import importlib.util
import json
import os
from pathlib import Path

import pytest

from loadout import check, paths, runner, targets

BIN, CACHE = "codebase-memory-mcp binaries", "codebase-memory cache folders"
NAME = "codebase-memory-mcp.exe" if os.name == "nt" else "codebase-memory-mcp"


def _stub(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    f = folder / NAME
    f.write_text("#!/bin/sh\n")
    f.chmod(0o755)
    return f


def _path(monkeypatch, *folders):
    monkeypatch.setenv("PATH", os.pathsep.join(str(f) for f in folders))


def _both(monkeypatch):
    from loadout import codex
    monkeypatch.setattr(targets, "OVERRIDE", {"claude": True, "codex": True})
    monkeypatch.setattr(codex, "plugin_serves_cbm", lambda installed=None: True)  # Codex runs the plugin's server


def _rows(name):
    return [r for r in check.run_checks() if r.name == name]


def test_one_binary_is_ok(fake_home, fake_runner, monkeypatch, tmp_path):
    a = _stub(tmp_path / "a")
    _path(monkeypatch, tmp_path / "a")
    [r] = _rows(BIN)
    assert (r.ok, r.detail) == (True, "1 on PATH")
    assert not [c for c in fake_runner.calls if c[0] == str(a)], "one binary: nothing to compare, no --version run"


def test_two_binaries_with_different_versions_warn(fake_home, fake_runner, monkeypatch, tmp_path):
    a, b = _stub(tmp_path / "a"), _stub(tmp_path / "b")
    _path(monkeypatch, tmp_path / "a", tmp_path / "b", tmp_path / "a")  # a twice: one binary
    fake_runner.responses[(str(a), "--version")] = runner.Result(0, "codebase-memory-mcp 0.12.1\n", "")
    fake_runner.responses[(str(b), "--version")] = runner.Result(0, "v0.11.0", "")
    [r] = _rows(BIN)
    assert (r.ok, r.severity) == (False, "warn")
    assert r.detail == f"{a} 0.12.1; {b} 0.11.0"
    assert r.fix == f"the first one runs ({a}); remove the others or make them the same version"
    assert all(c[1:] == ["--version"] for c in fake_runner.calls if c[0] in (str(a), str(b)))


def test_equal_versions_are_ok_and_a_failed_version_is_unknown(fake_home, fake_runner, monkeypatch, tmp_path):
    a, b = _stub(tmp_path / "a"), _stub(tmp_path / "b")
    _path(monkeypatch, tmp_path / "a", tmp_path / "b")
    fake_runner.responses[(str(a), "--version")] = runner.Result(0, "0.12.1", "")
    fake_runner.responses[(str(b), "--version")] = runner.Result(0, "0.12.1", "")
    [r] = _rows(BIN)
    assert (r.ok, r.detail) == (True, "2 on PATH, version 0.12.1")
    fake_runner.responses[(str(b), "--version")] = runner.Result(1, "", "boom")
    [r] = _rows(BIN)
    assert not r.ok and r.detail == f"{a} 0.12.1; {b} ?"


def test_no_binary_no_row(fake_home, fake_runner, monkeypatch, tmp_path):
    _path(monkeypatch, tmp_path / "empty")
    assert _rows(BIN) == []


def test_cache_folders_equal_by_default(fake_home, fake_runner, monkeypatch):
    _both(monkeypatch)
    [r] = _rows(CACHE)
    assert r.ok


def test_an_exported_cache_dir_splits_claude_from_codex(fake_home, fake_runner, monkeypatch, tmp_path):
    _both(monkeypatch)
    monkeypatch.setenv("CBM_CACHE_DIR", str(tmp_path / "mine"))
    [r] = _rows(CACHE)
    assert (r.ok, r.severity) == (False, "warn")
    assert r.detail == (f"two cache folders: {tmp_path / 'mine'} (Claude Code) and "
                        f"{fake_home / '.cache/codebase-memory-mcp'} (Codex); the servers and the project pointer "
                        "see different indexes")
    assert r.fix == ("leave CBM_CACHE_DIR unset everywhere, or set the same folder for both "
                     "(Codex: env in your [mcp_servers] table)")


def test_a_codex_table_env_matching_the_export_is_ok(fake_home, fake_runner, monkeypatch, tmp_path):
    _both(monkeypatch)
    from loadout import codex
    monkeypatch.setattr(codex, "plugin_serves_cbm", lambda installed=None: False)  # your table is Codex's only one
    mine = tmp_path / "mine"
    monkeypatch.setenv("CBM_CACHE_DIR", str(mine))
    (fake_home / ".codex").mkdir()
    (fake_home / ".codex/config.toml").write_text(
        f'[mcp_servers.cbm]\ncommand = "codebase-memory-mcp"\n[mcp_servers.cbm.env]\nCBM_CACHE_DIR = \'{mine}\'\n')
    [r] = _rows(CACHE)
    assert r.ok


def test_a_codex_table_passing_the_variable_through_is_ok(fake_home, fake_runner, monkeypatch, tmp_path):
    _both(monkeypatch)
    from loadout import codex
    monkeypatch.setattr(codex, "plugin_serves_cbm", lambda installed=None: False)  # your table is Codex's only one
    monkeypatch.setenv("CBM_CACHE_DIR", str(tmp_path / "mine"))
    (fake_home / ".codex").mkdir()
    (fake_home / ".codex/config.toml").write_text(
        '[mcp_servers.cbm]\ncommand = "codebase-memory-mcp"\nenv_vars = ["CBM_CACHE_DIR"]\n')
    [r] = _rows(CACHE)
    assert r.ok


def test_a_claude_server_env_is_read(fake_home, fake_runner, monkeypatch, tmp_path):
    _both(monkeypatch)
    (fake_home / ".claude.json").write_text(json.dumps({"mcpServers": {"cbm": {
        "command": "codebase-memory-mcp", "env": {"CBM_CACHE_DIR": str(tmp_path / "x")}}}}))
    [r] = _rows(CACHE)
    assert not r.ok and f"{tmp_path / 'x'} (Claude Code)" in r.detail


@pytest.mark.parametrize("on", [{"claude": True, "codex": False}, {"claude": False, "codex": True}])
def test_cache_row_absent_with_one_agent_off(fake_home, fake_runner, monkeypatch, tmp_path, on):
    monkeypatch.setattr(targets, "OVERRIDE", on)
    monkeypatch.setenv("CBM_CACHE_DIR", str(tmp_path / "mine"))
    assert _rows(CACHE) == []


def test_rows_absent_with_codex_off(fake_home, fake_runner, monkeypatch, tmp_path):
    monkeypatch.setattr(targets, "OVERRIDE", {"claude": True, "codex": False})
    monkeypatch.setenv("CBM_CACHE_DIR", str(tmp_path / "mine"))
    (fake_home / ".codex").mkdir()
    (fake_home / ".codex/config.toml").write_text('[mcp_servers.cbm]\ncommand = "codebase-memory-mcp"\n')
    assert _rows(CACHE) == []


def test_rows_absent_with_both_agents_off(fake_home, fake_runner, monkeypatch, tmp_path):
    a = _stub(tmp_path / "a")
    _path(monkeypatch, tmp_path / "a")
    monkeypatch.setattr(targets, "OVERRIDE", {"claude": False, "codex": False})
    assert _rows(BIN) == [] and _rows(CACHE) == []


def test_default_folder_agrees_with_the_hook(fake_home):
    src = Path(__file__).resolve().parent.parent / "plugins/loadout/hooks/cbm_project.py"
    spec = importlib.util.spec_from_file_location("cbm_project_t", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert Path(mod.cache_dir()) == check._cbm_default_cache() == paths.home() / ".cache/codebase-memory-mcp"


def test_a_switched_off_codex_table_does_not_count_for_the_cache(fake_home, fake_runner, monkeypatch, tmp_path):
    _both(monkeypatch)
    (fake_home / ".codex").mkdir()
    (fake_home / ".codex/config.toml").write_text(
        '[mcp_servers.cbm]\ncommand = "codebase-memory-mcp"\nenabled = false\n'
        f'[mcp_servers.cbm.env]\nCBM_CACHE_DIR = \'{tmp_path / "other"}\'\n')
    [r] = _rows(CACHE)
    assert r.ok


def test_unknown_versions_never_prove_equality(fake_home, fake_runner, monkeypatch, tmp_path):
    a, b = _stub(tmp_path / "a"), _stub(tmp_path / "b")
    _path(monkeypatch, tmp_path / "a", tmp_path / "b")
    fake_runner.responses[(str(a), "--version")] = runner.Result(1, "", "boom")
    fake_runner.responses[(str(b), "--version")] = runner.Result(0, "no version here", "")
    [r] = _rows(BIN)
    assert not r.ok and r.detail == f"{a} ?; {b} ?"


def test_every_active_codex_server_is_compared(fake_home, fake_runner, monkeypatch, tmp_path):
    import json as _json
    from loadout import codex
    _both(monkeypatch)
    mine = tmp_path / "mine"
    monkeypatch.setenv("CBM_CACHE_DIR", str(mine))  # Claude Code: mine
    monkeypatch.setattr(codex, "plugin_serves_cbm", lambda installed=None: True)  # the plugin's server: default
    (fake_home / ".codex").mkdir()
    (fake_home / ".codex/config.toml").write_text(
        f'[mcp_servers.cbm]\ncommand = "codebase-memory-mcp"\n[mcp_servers.cbm.env]\nCBM_CACHE_DIR = \'{mine}\'\n')
    [r] = _rows(CACHE)
    assert not r.ok  # Claude's and the user table's folder agree, but the plugin's Codex server uses the default


def test_no_codex_server_means_no_second_folder(fake_home, fake_runner, monkeypatch, tmp_path):
    from loadout import codex
    _both(monkeypatch)
    monkeypatch.setattr(codex, "plugin_serves_cbm", lambda installed=None: False)
    monkeypatch.setenv("CBM_CACHE_DIR", str(tmp_path / "mine"))
    [r] = _rows(CACHE)
    assert r.ok  # only Claude Code runs codebase-memory: one folder
