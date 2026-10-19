"""loadout check: a dirty kit or personal checkout is fine; only a refusal recorded by the daily pull is a warning."""
import json
import os

import pytest

from loadout import check, paths


def _repos(fake_home, monkeypatch, tmp_path):
    kit = tmp_path / "kit"
    (kit / ".git").mkdir(parents=True)
    monkeypatch.setenv("LOADOUT_ROOT", str(kit))
    return kit


def test_dirty_alone_is_not_a_warning(fake_home, fake_runner, monkeypatch, tmp_path):
    _repos(fake_home, monkeypatch, tmp_path)
    fake_runner.responses[("git", "-C", str(tmp_path / "kit"), "status", "--porcelain")] = check.runner.Result(0, " M x\n", "")
    (res,) = [r for r in check._repos() if r.name == "kit repo clean"]
    assert res.ok


def test_check_names_the_paused_files(fake_home, fake_runner, monkeypatch, tmp_path):
    kit = _repos(fake_home, monkeypatch, tmp_path)
    state = paths.state_dir()
    state.mkdir(parents=True, exist_ok=True)
    (state / "sync-paused.json").write_text(json.dumps({str(kit): {
        "reason": "local changes the pull would overwrite", "files": ["a\x1b[31mb.txt", "ok.md"], "at": 1}}))
    (res,) = [r for r in check._repos() if r.name == "kit repo clean"]
    assert not res.ok and res.severity == "warn"
    assert "a\\x1b[31mb.txt" in res.detail and "ok.md" in res.detail and "\x1b" not in res.detail
    assert "loadout update" in res.fix and str(kit) in res.fix



def _paused_without_files(monkeypatch, kit):
    (kit / ".git").mkdir(parents=True)
    monkeypatch.setenv("LOADOUT_ROOT", str(kit))
    state = paths.state_dir()
    state.mkdir(parents=True, exist_ok=True)
    (state / "sync-paused.json").write_text(json.dumps({str(kit): {"reason": "the branch diverged", "at": 1}}))
    (res,) = [r for r in check._repos() if r.name == "kit repo clean"]
    return res


def test_a_refusal_without_files_is_not_told_to_commit(fake_home, fake_runner, monkeypatch, tmp_path):
    res = _paused_without_files(monkeypatch, tmp_path / "kit")
    assert "commit or stash" not in res.fix and "resolve it in" in res.fix


@pytest.mark.skipif(os.name == "nt", reason="Windows file names cannot hold control characters")
def test_the_paused_root_is_escaped_in_the_fix(fake_home, fake_runner, monkeypatch, tmp_path):
    res = _paused_without_files(monkeypatch, tmp_path / "ki\x1bt")
    assert "\x1b" not in res.fix and "ki\\x1bt" in res.fix
