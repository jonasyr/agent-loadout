"""`loadout check` flags an installed loadout plugin copy that differs from the kit's plugins/loadout."""
import json
import os

import pytest

from loadout import check, paths, targets


@pytest.fixture
def kit(tmp_path, monkeypatch):
    root = tmp_path / "kit"
    plugin = root / "plugins" / "loadout"
    (plugin / "hooks").mkdir(parents=True)
    (plugin / ".claude-plugin").mkdir()
    (plugin / "hooks" / "hooks.json").write_text('{"hooks": {}}')
    (plugin / "hooks" / "advisor.py").write_text("print('new')\n")
    (plugin / ".claude-plugin" / "plugin.json").write_text('{"name": "loadout"}')
    monkeypatch.setenv("LOADOUT_ROOT", str(root))
    return plugin


def _copy(src, dst):
    for f in src.rglob("*"):
        if f.is_file():
            target = dst / f.relative_to(src)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(f.read_bytes())
    return dst


def _claude_copy(home, kit):
    dst = _copy(kit, home / ".claude" / "plugins" / "cache" / "agent-loadout" / "loadout" / "abc123")
    record = home / ".claude" / "plugins" / "installed_plugins.json"
    record.write_text(json.dumps({"version": 2, "plugins": {
        "loadout@agent-loadout": [{"scope": "user", "installPath": str(dst), "gitCommitSha": "abc123"}]}}))
    return dst


def _codex_copy(kit):
    return _copy(kit, paths.codex_home() / "plugins" / "cache" / "agent-loadout" / "loadout" / "local")


def _results(name):
    return [r for r in check._plugin_copies() if r.name == name]


def test_an_identical_copy_is_ok(fake_home, kit):
    _claude_copy(fake_home, kit)
    (r,) = _results("loadout plugin (Claude Code)")
    assert r.ok


def test_a_changed_file_is_a_warning_with_the_fix(fake_home, kit):
    dst = _claude_copy(fake_home, kit)
    (dst / "hooks" / "advisor.py").write_text("print('old')\n")
    (r,) = _results("loadout plugin (Claude Code)")
    assert not r.ok and r.severity == "warn"
    assert "loadout update" in r.fix and "/reload-plugins" in r.fix


def test_a_file_missing_from_the_copy_is_a_warning(fake_home, kit):
    dst = _claude_copy(fake_home, kit)
    (dst / "hooks" / "advisor.py").unlink()
    (r,) = _results("loadout plugin (Claude Code)")
    assert not r.ok


def test_a_file_the_kit_removed_is_a_warning(fake_home, kit):
    # Codex loads every folder under skills/, so a skill the kit removed or renamed still runs from an old copy
    dst = _claude_copy(fake_home, kit)
    (dst / "skills" / "old-name").mkdir(parents=True)
    (dst / "skills" / "old-name" / "SKILL.md").write_text("---\nname: old-name\n---\n")
    (r,) = _results("loadout plugin (Claude Code)")
    assert not r.ok


@pytest.mark.skipif(os.name == "nt", reason="no executable bit on Windows")
def test_a_hook_script_that_lost_its_executable_bit_is_a_warning(fake_home, kit):
    script = kit / "hooks" / "run.sh"
    script.write_text("#!/bin/sh\n")
    script.chmod(0o755)
    dst = _claude_copy(fake_home, kit)
    (dst / "hooks" / "run.sh").chmod(0o755)
    (r,) = _results("loadout plugin (Claude Code)")
    assert r.ok
    (dst / "hooks" / "run.sh").chmod(0o644)
    (r,) = _results("loadout plugin (Claude Code)")
    assert not r.ok


def test_files_the_agents_add_do_not_count(fake_home, kit):
    dst = _claude_copy(fake_home, kit)
    (dst / ".in_use").write_text("")
    (dst / "hooks" / "__pycache__").mkdir()
    (dst / "hooks" / "__pycache__" / "advisor.cpython-312.pyc").write_bytes(b"\0")
    (kit / "hooks" / "__pycache__").mkdir()
    (kit / "hooks" / "__pycache__" / "tool_hint.cpython-312.pyc").write_bytes(b"\1")
    (r,) = _results("loadout plugin (Claude Code)")
    assert r.ok


def test_eval_folders_do_not_count(fake_home, kit):
    # eval runs write gitignored reports into the kit (evals/results/); a copy cloned from git never has them
    _claude_copy(fake_home, kit)
    for folder in ("evals", "evals-browser"):
        (kit / folder / "results").mkdir(parents=True)
        (kit / folder / "results" / "report.json").write_text("{}")
    (r,) = _results("loadout plugin (Claude Code)")
    assert r.ok


def test_no_installed_copy_gives_no_line(fake_home, kit):
    targets.set_agents({"claude": True, "codex": True})
    assert check._plugin_copies() == []


def test_a_record_pointing_nowhere_gives_no_line(fake_home, kit):
    dst = _claude_copy(fake_home, kit)
    for f in sorted(dst.rglob("*"), reverse=True):
        f.unlink() if f.is_file() else f.rmdir()
    dst.rmdir()
    assert _results("loadout plugin (Claude Code)") == []


def test_codex_copy_is_compared_when_codex_is_on(fake_home, kit):
    targets.set_agents({"claude": False, "codex": True})
    dst = _codex_copy(kit)
    (r,) = _results("loadout plugin (Codex)")
    assert r.ok
    (dst / "hooks" / "hooks.json").write_text("{}")
    (r,) = _results("loadout plugin (Codex)")
    assert not r.ok and "/hooks" in r.fix


def test_an_agent_that_is_off_is_not_read(fake_home, kit):
    _claude_copy(fake_home, kit)
    _codex_copy(kit)
    targets.set_agents({"claude": False, "codex": True})
    assert [r.name for r in check._plugin_copies()] == ["loadout plugin (Codex)"]
    targets.set_agents({"claude": True, "codex": False})
    assert [r.name for r in check._plugin_copies()] == ["loadout plugin (Claude Code)"]


def test_run_checks_includes_the_copy_check(fake_home, fake_runner, monkeypatch):
    called = []
    monkeypatch.setattr(check, "_plugin_copies", lambda: called.append(1) or [])
    check.run_checks()
    assert called
