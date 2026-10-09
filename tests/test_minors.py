"""Cheap, safe fixes from the deferred-minor triage (followups-report.md lists each one)."""
import json
import os
import shutil
import time

import pytest

from loadout import adopt, backup, bootstrap, check, configure, inventory, link, maintenance as m, paths, runner, secrets
from fixtures import author_machine


def _by_name(results):
    return {r.name: r for r in results}


# --- maintenance lock (A-I8) ---------------------------------------------------------------

def test_maintenance_skips_while_another_run_holds_the_lock(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(m, "pull_if_clean", lambda root: False)
    monkeypatch.setattr(m, "find_outdated", lambda: [({"id": "serena"}, (1, 0, 0), (2, 0, 0))])
    lock = paths.state_dir() / "maintenance.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text("123")
    m.maintain(100.0)
    assert not (paths.state_dir() / "pending-notice").exists()
    assert lock.exists()  # someone else's lock is left alone


def test_stale_lock_is_taken_over_and_released(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(m, "pull_if_clean", lambda root: False)
    monkeypatch.setattr(m, "find_outdated", lambda: [({"id": "serena"}, (1, 0, 0), (2, 0, 0))])
    lock = paths.state_dir() / "maintenance.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text("123")
    old = time.time() - 2 * 3600
    os.utime(lock, (old, old))
    m.maintain(100.0)
    assert "serena" in (paths.state_dir() / "pending-notice").read_text()
    assert not lock.exists()


def test_session_start_keeps_notice_when_spawn_fails(fake_home, monkeypatch):
    def boom():
        raise OSError("no python")
    monkeypatch.setattr(m, "_spawn_background", boom)
    m.notify("hello")
    out = m.session_start(0.0)
    assert "hello" in json.loads(out)["systemMessage"]


def test_no_reapply_after_noop_pull(fake_home, fake_runner, tmp_path):
    fake_runner.responses[("git", "-C", str(tmp_path), "rev-parse", "HEAD")] = runner.Result(0, "abc\n", "")
    assert m.pull_if_clean(tmp_path) is False  # pull ok, HEAD unchanged: nothing to re-apply


# --- backup manifest written before the move (A-M1) ---------------------------------------

def test_backup_records_intent_before_moving(fake_home, monkeypatch):
    f = fake_home / "a.txt"
    f.write_text("x")
    bk = backup.Backup()
    seen = {}
    real_move = shutil.move

    def spy(src, dst):
        seen["labels"] = [s["label"] for s in json.loads((bk.root / "manifest.json").read_text())["steps"]]
        return real_move(src, dst)

    monkeypatch.setattr(shutil, "move", spy)
    bk.move(f, "move a")
    assert seen["labels"] == ["move a"]


def test_backup_failed_move_leaves_no_step(fake_home, monkeypatch):
    f = fake_home / "a.txt"
    f.write_text("x")
    bk = backup.Backup()

    def fail(src, dst):
        raise PermissionError("denied")

    monkeypatch.setattr(shutil, "move", fail)
    with pytest.raises(PermissionError):
        bk.move(f, "move a")
    assert bk.empty and json.loads((bk.root / "manifest.json").read_text())["steps"] == []


# --- copy mode (A-M3, marker, check) ------------------------------------------------------

def _copy_mode(fake_home):
    (paths.personal_root() / "rules").mkdir(parents=True)
    (paths.personal_root() / "rules/me.md").write_text("me")
    marker = paths.state_dir() / "copy-mode"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("copy\n")
    link.link_all(backup.Backup())
    return fake_home / ".claude/rules/personal"


def test_copy_mode_refresh_backs_up_an_edited_copy(fake_home):
    dest = _copy_mode(fake_home)
    (dest / "me.md").write_text("edited in the copy")
    (paths.personal_root() / "rules/me.md").write_text("me v2")  # a pull changed the source
    bk = backup.Backup()
    link.link_all(bk)
    assert (dest / "me.md").read_text() == "me v2"
    assert not bk.empty and any(p.read_text() == "edited in the copy" for p in bk.root.rglob("me.md"))


def test_copy_mode_refresh_of_unedited_copy_needs_no_backup(fake_home):
    dest = _copy_mode(fake_home)
    (paths.personal_root() / "rules/me.md").write_text("me v2")
    bk = backup.Backup()
    link.link_all(bk)
    assert (dest / "me.md").read_text() == "me v2" and bk.empty


def test_bootstrap_link_step_clears_copy_mode_when_symlinks_work(fake_home):
    dest = _copy_mode(fake_home)
    bk = backup.Backup()
    lines = link.link_all(bk, retry_symlinks=True)
    assert not link.is_copy_mode()
    assert dest.is_symlink() and any("linked" in x for x in lines)


def test_check_copy_mode_link_requires_kit_copy(fake_home, fake_runner):
    dest = _copy_mode(fake_home)
    assert _by_name(check._links())["link rules/personal"].ok
    shutil.rmtree(dest)
    dest.mkdir()
    assert not _by_name(check._links())["link rules/personal"].ok


# --- adopt -------------------------------------------------------------------------------

@pytest.fixture
def machine(fake_home):
    author_machine(fake_home)
    return fake_home


def test_skill_removal_keeps_shared_agents_source(machine):
    v = [v for v in inventory.classify(inventory.collect(with_versions=False)) if v.item.name == "gpt-taste"]
    adopt.apply(v, backup.Backup())
    assert not (machine / ".claude/skills/gpt-taste").exists()
    assert (machine / ".agents/skills/gpt-taste/SKILL.md").exists()  # Codex and other agents still use it


def test_scope_down_apply_prints_profile_hint(machine, fake_runner):
    v = [v for v in inventory.classify(inventory.collect(with_versions=False))
         if v.action == "scope-down" and v.item.name == "sonarqube@claude-plugins-official"]
    out = adopt.apply(v, backup.Backup())
    assert "loadout profile sonar" in out[0]


def test_keep_binaries_collapsed_to_one_line(machine, fake_runner):
    verdicts = inventory.classify(inventory.collect(with_versions=False))
    plan = adopt.render_plan(verdicts, [])
    keep = plan.split("KEEP")[1]
    assert "[binary] git" not in keep and "binaries:" in keep and "git" in keep


def test_inventory_tolerates_malformed_plugin_and_marketplace_files(fake_home, fake_runner):
    p = fake_home / ".claude/plugins"
    p.mkdir(parents=True)
    (p / "installed_plugins.json").write_text(json.dumps({"plugins": {"a@b": "x", "c@d": [], "e@f": [{"scope": "user"}]}}))
    (p / "known_marketplaces.json").write_text(json.dumps({"m": "x", "n": {"source": "y"}}))
    items = inventory.collect(with_versions=False)
    assert [i.name for i in items if i.kind == "plugin"] == ["e@f"]
    assert sorted(i.name for i in items if i.kind == "marketplace") == ["n"]


def test_inventory_tolerates_non_dict_plugins_value(fake_home, fake_runner):
    p = fake_home / ".claude/plugins"
    p.mkdir(parents=True)
    (p / "installed_plugins.json").write_text(json.dumps({"plugins": ["x"]}))
    inventory.collect(with_versions=False)
    assert _by_name(check._plugins())["plugins installed"].severity == "warn"


def test_fix_secrets_tolerates_non_dict_mcp_servers(fake_home):
    paths.claude_json().write_text(json.dumps({"mcpServers": ["x"]}))
    f = secrets.Finding("srv", "env", "API_TOKEN", "x" * 20, "~/.claude.json", True)
    assert "not found" in adopt.fix_secrets([f], backup.Backup())[0]


# --- restore --list ----------------------------------------------------------------------

def test_restore_list_shows_time_and_home_relative_path(fake_home):
    f = fake_home / "a.txt"
    f.write_text("x")
    bk = backup.Backup(description="adopt")
    bk.move(f, "move a")
    rows = backup.list_backups()
    assert rows[0].startswith("~/.claude/backups/loadout-") or rows[0].startswith("~\\.claude\\backups\\loadout-")
    assert time.strftime("%Y-%m-%d") in rows[0] and "adopt" in rows[0]


# --- configure / secrets ------------------------------------------------------------------

def test_configure_show_redacts_preferences(fake_home, fake_runner):
    root = paths.personal_root()
    root.mkdir(parents=True)
    (root / "settings.json").write_text(json.dumps({"env": {"API_TOKEN": "ghp_" + "a" * 30}}))
    assert "ghp_" not in configure.show()


def test_configure_show_marks_profile_plugins(fake_home, fake_runner):
    text = configure.show()
    line = next(x for x in text.splitlines() if "sonarqube@claude-plugins-official" in x)
    assert "per project" in line


def test_redact_masks_dsn_credentials():
    text = "npx dbhub --dsn postgres://admin:hunter2secret@db.local/app"
    out = secrets.redact(text)
    assert "hunter2secret" not in out and "db.local/app" in out


def test_personal_push_refused_when_env_file_would_be_committed(fake_home, fake_runner, capsys):
    root = paths.personal_root()
    (root / ".git").mkdir(parents=True)
    fake_runner.responses[("git", "-C", str(root), "status", "--porcelain", "-uall")] = runner.Result(0, "?? new/x.env\n", "")
    configure.apply_all(lambda q: "y", setup=False)
    assert not [c for c in fake_runner.calls if "push" in c or "commit" in c]
    assert "new/x.env" in capsys.readouterr().out


# --- Windows / platform -------------------------------------------------------------------

def test_runner_hides_console_windows_on_windows(monkeypatch):
    import subprocess
    seen = {}
    monkeypatch.setattr(runner, "_is_windows", lambda: True)
    monkeypatch.setattr(shutil, "which", lambda n: "/bin/echo")
    monkeypatch.setattr(subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)

    def fake_run(cmd, **kw):
        seen.update(kw)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    runner.run(["echo", "x"])
    assert seen.get("creationflags") == 0x08000000


def test_windows_profile_with_undecodable_byte_does_not_crash(fake_home, monkeypatch):
    import locale
    monkeypatch.setattr(locale, "getpreferredencoding", lambda do_setlocale=True: "cp1252")
    rc = fake_home / "profile.ps1"
    rc.write_bytes(b"Write-Host 'caf\x81'\r\n")  # 0x81 is undefined in cp1252
    bk = backup.Backup()
    assert bootstrap._add_block(rc, bootstrap.PS_BLOCK, bk, windows=True)
    assert bootstrap.RC_MARKER.encode() in rc.read_bytes()
    assert any(p.read_bytes() == b"Write-Host 'caf\x81'\r\n" for p in bk.root.rglob("*profile.ps1"))


def test_gh_setup_git_is_announced(fake_home, fake_runner, capsys):
    bootstrap.check_prereqs(False, lambda q: "")
    assert ["gh", "auth", "setup-git"] in fake_runner.calls
    assert "gh auth setup-git" in capsys.readouterr().out


def test_update_waits_for_background_maintenance(fake_home, fake_runner, capsys):
    lock = paths.state_dir() / "maintenance.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text("1")
    assert m.update(yes=True, ask=lambda q: "") == 1
    assert fake_runner.calls == [] and "try" in capsys.readouterr().out


def test_stale_lock_taken_by_someone_else_in_between_is_given_back(fake_home, monkeypatch):
    lock = paths.state_dir() / "maintenance.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text("old")
    old = time.time() - 2 * 3600
    os.utime(lock, (old, old))
    real_rename = os.rename

    def racing_rename(src, dst):
        os.utime(lock, None)  # another run replaced the stale lock with a fresh one just now
        return real_rename(src, dst)

    monkeypatch.setattr(os, "rename", racing_rename)
    assert m._acquire_lock() is False
    assert lock.exists() and not list(lock.parent.glob("maintenance.lock.stale-*"))


def test_lock_taken_over_is_not_released_by_the_old_owner(fake_home):
    assert m._acquire_lock()
    lock = paths.state_dir() / "maintenance.lock"
    lock.write_text("99999999")  # our run looked stale; another run took the lock over
    m._release_lock()
    assert lock.exists() and lock.read_text() == "99999999"
    lock.unlink()


def test_lock_is_refreshed_during_a_run(fake_home):
    assert m._acquire_lock()
    lock = paths.state_dir() / "maintenance.lock"
    old = time.time() - 1800
    os.utime(lock, (old, old))
    m._touch_lock()
    assert time.time() - lock.stat().st_mtime < 60
    m._release_lock()
    assert not lock.exists()
