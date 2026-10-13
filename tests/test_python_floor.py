"""loadout needs Python 3.11 or newer everywhere it checks."""
import re

from loadout import link, paths

KIT = paths.kit_root()


def test_every_version_check_says_3_11():
    files = ["bin/loadout", "plugins/loadout/hooks/run.sh", "bootstrap.sh", "bootstrap.ps1", "pyproject.toml"]
    for rel in files:
        text = (KIT / rel).read_text(encoding="utf-8")
        assert "3.10" not in text and "(3, 10)" not in text, rel
    assert "(3, 11)" in link.PY_OK and ">=3.11" in link.UV_FIND and ">=3.11" in link.UV_INSTALL


def test_bin_loadout_refuses_3_10(capsys):
    import importlib.machinery
    import importlib.util
    loader = importlib.machinery.SourceFileLoader("binloadout", str(KIT / "bin/loadout"))
    spec = importlib.util.spec_from_loader("binloadout", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    try:
        mod.require_python((3, 10, 0))
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("did not exit")
    assert "3.11 or newer" in capsys.readouterr().err


def test_no_code_path_for_a_missing_tomllib():
    for rel in ("cli/loadout/codex.py", "cli/loadout/codex_project.py", "cli/loadout/own.py"):
        assert not re.search(r"_tomllib\(\) is None|needs Python 3\.11", (KIT / rel).read_text(encoding="utf-8")), rel


def _bin_loadout():
    import importlib.machinery
    import importlib.util
    loader = importlib.machinery.SourceFileLoader("binloadout2", str(KIT / "bin/loadout"))
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("binloadout2", loader))
    loader.exec_module(mod)
    return mod


def test_an_old_python_switches_to_a_uv_python(tmp_path, monkeypatch):
    import os
    newer = tmp_path / "python3.12"
    newer.write_text("")
    uv = tmp_path / "bin" / "uv"
    uv.parent.mkdir()
    uv.write_text(f"#!/bin/sh\necho {newer}\n")
    uv.chmod(0o755)
    monkeypatch.setenv("PATH", str(uv.parent))
    monkeypatch.delenv("LOADOUT_REEXEC", raising=False)
    mod = _bin_loadout()
    seen = []
    monkeypatch.setattr(os, "execv", lambda exe, args: seen.append((exe, args)))
    mod.reexec_with_uv(["check"])
    assert seen and seen[0][0] == str(newer) and seen[0][1][-1] == "check"
    monkeypatch.delenv("LOADOUT_REEXEC", raising=False)


def test_the_message_names_bootstrap_when_no_newer_python_exists(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PATH", str(tmp_path))
    mod = _bin_loadout()
    try:
        mod.require_python((3, 10, 0))
    except SystemExit:
        pass
    assert "bootstrap" in capsys.readouterr().err


def test_on_windows_the_newer_python_runs_as_a_child_and_its_exit_code_is_kept(tmp_path, monkeypatch):
    import subprocess
    newer = tmp_path / "py dir" / "python.exe"
    newer.parent.mkdir()
    newer.write_text("")
    mod = _bin_loadout()
    calls = []
    monkeypatch.setattr(subprocess, "call", lambda args: calls.append(args) or 3)
    try:
        mod.continue_under(str(newer), ["check", "a b"], windows=True)
    except SystemExit as exc:
        assert exc.code == 3
    assert calls and calls[0][0] == str(newer) and calls[0][-1] == "a b"


def test_the_uv_lookup_ignores_an_active_virtualenv():
    text = (KIT / "bin/loadout").read_text(encoding="utf-8")
    assert '"python", "find", "--system", "--no-config", "--no-project"' in text  # like link.UV_FIND
