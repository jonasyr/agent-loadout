"""Task 6 review: writers of codex-config.json hold the Codex lock; an entry reverted to loadout's text is loadout's
again; explain with Codex off or CODEX_HOME; the sync's release notice."""
import json
import os

import pytest

from loadout import backup, codex, maintenance, paths
from loadout.explain import explain


@pytest.fixture(autouse=True)
def _no_background_run(monkeypatch):
    monkeypatch.setattr(maintenance, "_spawn_background", lambda: None)


def _codex_on(on=True):
    paths.personal_root().mkdir(parents=True, exist_ok=True)
    (paths.personal_root() / "targets.json").write_text(json.dumps({"claude": True, "codex": on}))


def _personal_mcp(servers):
    (paths.personal_root() / "mcp.json").write_text(json.dumps({"mcpServers": servers}), encoding="utf-8")


def _cfg():
    return paths.codex_home() / "config.toml"


def _apply():
    return codex.apply_config(backup.Backup(description="t"))


def _message(out):
    return json.loads(out)["systemMessage"] if out else ""


def _lock_held() -> bool:
    return (paths.state_dir() / codex.LOCK).exists()


# 1. the two foreground writers of codex-config.json take the Codex lock

def test_profile_plugins_hold_the_codex_lock_while_they_write_the_record(fake_home, fake_runner, monkeypatch):
    from loadout import codex_project, profiles, runner, settings_merge
    held = []
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: {"enabledPlugins": {}})
    monkeypatch.setattr(codex, "apply_config", lambda bk, dry_run=False: held.append(_lock_held()) or [])
    fake_runner.responses[("codex", "plugin", "list")] = runner.Result(0, json.dumps({"installed": []}), "")
    fake_runner.responses[("codex", "plugin", "marketplace", "add", codex.OFFICIAL)] = runner.Result(
        0, json.dumps({"marketplaceName": "claude-plugins-official", "alreadyAdded": True}), "")
    prof = profiles.Profile(name="thesis", description="", install=["deepeval@claude-plugins-official"],
                            settings={"enabledPlugins": {"deepeval@claude-plugins-official": True}})
    codex_project.plugins(prof, dry_run=False)
    assert held == [True] and not _lock_held()


def test_a_busy_lock_makes_profile_plugins_say_so_and_write_nothing(fake_home, fake_runner, monkeypatch):
    from loadout import codex_project, locks, profiles
    monkeypatch.setattr(locks, "foreground_wait", lambda: 0)
    monkeypatch.setattr(codex, "apply_config", lambda bk, dry_run=False: pytest.fail("ran without the lock"))
    prof = profiles.Profile(name="thesis", description="", install=["deepeval@claude-plugins-official"],
                            settings={"enabledPlugins": {"deepeval@claude-plugins-official": True}})
    other = codex._lock(0, "bootstrap")
    try:
        lines = codex_project.plugins(prof, dry_run=False)
    finally:
        other.release()
    assert any("still running" in line for line in lines)


def test_adopt_holds_the_codex_lock_while_it_hands_a_table_to_loadout(fake_home, fake_runner, monkeypatch):
    from loadout import own, targets
    from loadout.inventory import Item, Verdict
    monkeypatch.setattr(targets, "codex_enabled", lambda: True)
    monkeypatch.setattr(targets, "claude_enabled", lambda: False)
    held = []
    monkeypatch.setattr(codex, "apply_config", lambda bk, dry_run=False: held.append(_lock_held()) or [])
    real_remove = codex.remove_server
    monkeypatch.setattr(codex, "remove_server", lambda name, bk: held.append(_lock_held()) or real_remove(name, bk))
    _cfg().parent.mkdir(parents=True)
    _cfg().write_text('[mcp_servers.mine]\ncommand = "m"\n')
    v = Verdict(Item("mcp", "mine", "m", codex.CONFIG_LOCATION, {"config": {"type": "stdio", "command": "m"},
                                                                 "problem": ""}), "own", "")
    own.record_global(v, backup.Backup(description="t")).machine()
    assert held == [True, True] and not _lock_held()


# 2. an entry you put back to loadout's exact text is loadout's again

def test_a_table_put_back_to_loadouts_text_is_loadouts_again(fake_home, fake_runner):
    _codex_on()
    _personal_mcp({"gh": {"command": "gh-mcp"}})
    _apply()
    original = _cfg().read_bytes()
    _cfg().write_bytes(original.replace(b'command = "gh-mcp"', b'command = "gh-mcp"\nstartup_timeout_sec = 30'))
    assert "mcp gh" in _message(maintenance.session_start(0))
    _cfg().write_bytes(original)  # you undo your edit
    maintenance.session_start(0)
    record = codex.read_record()
    assert "gh" in record["tables"] and "released" not in record
    _personal_mcp({"gh": {"command": "gh-mcp2"}})  # loadout's change applies again
    assert _apply() == [] and 'command = "gh-mcp2"' in _cfg().read_text()
    _cfg().write_bytes(_cfg().read_bytes().replace(b'command = "gh-mcp2"', b'command = "gh-mcp3"'))
    assert "mcp gh" in _message(maintenance.session_start(0))  # a later edit: one new note


def test_a_table_put_back_is_taken_back_by_a_run_too(fake_home, fake_runner):
    _codex_on()
    _personal_mcp({"gh": {"command": "gh-mcp"}})
    _apply()
    original = _cfg().read_bytes()
    _cfg().write_bytes(original.replace(b'command = "gh-mcp"', b'command = "gh-mcp-mine"'))
    _apply()
    _cfg().write_bytes(original)
    assert _apply() == []
    assert "gh" in codex.read_record()["tables"] and "released" not in codex.read_record()


def test_a_key_put_back_to_loadouts_value_is_loadouts_again(fake_home, fake_runner):
    _codex_on()
    _apply()
    original = _cfg().read_bytes()
    _cfg().write_bytes(original.replace(b'model_reasoning_effort = "medium"', b'model_reasoning_effort = "high"'))
    assert "model_reasoning_effort" in _message(maintenance.session_start(0))
    _cfg().write_bytes(original)
    maintenance.session_start(0)
    record = codex.read_record()
    assert "released_keys" not in record and "model_reasoning_effort" in record["keys"]
    _cfg().write_bytes(original.replace(b'model_reasoning_effort = "medium"', b'model_reasoning_effort = "low"'))
    assert "model_reasoning_effort" in _message(maintenance.session_start(0))


def test_a_key_put_back_is_taken_back_by_a_run_too(fake_home, fake_runner):
    _codex_on()
    _apply()
    original = _cfg().read_bytes()
    _cfg().write_bytes(original.replace(b'model_reasoning_effort = "medium"', b'model_reasoning_effort = "high"'))
    _apply()
    _cfg().write_bytes(original)
    assert _apply() == []
    assert "released_keys" not in codex.read_record() and "model_reasoning_effort" in codex.read_record()["keys"]


# 3. a Codex-off explain never resolves anything in ~/.codex

def test_codex_off_explain_does_not_resolve_codex_paths(fake_home, fake_runner, monkeypatch, capsys):
    _codex_on(False)
    real = os.path.realpath

    def guarded(p, *a, **kw):
        if str(paths.codex_home()) in str(p):
            pytest.fail(f"Codex is off: {p} must not be resolved")
        return real(p, *a, **kw)
    monkeypatch.setattr(os.path, "realpath", guarded)
    assert explain(str(_cfg())) == 0
    assert "Codex is off" in capsys.readouterr().out


# 4. explain lists a released name only while its section is there

def test_explain_lists_released_names_only_while_their_section_exists(fake_home, fake_runner, capsys):
    _codex_on()
    _personal_mcp({"gh": {"command": "gh-mcp"}})
    _apply()
    _cfg().write_bytes(_cfg().read_bytes().replace(b'command = "gh-mcp"', b'command = "gh-mcp-mine"'))
    maintenance.session_start(0)
    _cfg().write_text(_cfg().read_text().replace('[mcp_servers.gh]\ncommand = "gh-mcp-mine"\n', ""))
    capsys.readouterr()
    explain(str(_cfg()))
    assert "mcp gh" not in capsys.readouterr().out


# 5. with CODEX_HOME set, ~/.codex/FILE means the real Codex file

def test_with_codex_home_a_tilde_codex_path_means_codex_home(fake_home, fake_runner, monkeypatch, capsys):
    monkeypatch.setenv("CODEX_HOME", str(fake_home / "elsewhere"))
    _codex_on()
    _apply()
    for arg in ("~/.codex/config.toml", str(fake_home / ".codex" / "config.toml")):
        assert explain(arg, cwd=fake_home) == 0
        out = capsys.readouterr().out
        assert "elsewhere" in out and "model_reasoning_effort" in out


# 7. the release lines and the sync's notice

def test_is_release_matches_apply_configs_release_lines(fake_home, fake_runner):
    _codex_on()
    _personal_mcp({"gh": {"command": "gh-mcp"}, "sub": {"command": "s"}})
    _apply()
    text = _cfg().read_text().replace('command = "gh-mcp"', 'command = "gh-mcp-mine"')
    text = text.replace('model_reasoning_effort = "medium"', 'model_reasoning_effort = "high"')
    _cfg().write_text(text + '\n[mcp_servers.sub.tools.x]\nenabled = true\n')
    lines = _apply()
    released = [l for l in lines if codex.is_release(l)]
    assert len(released) == 3 and len(lines) == 3, lines
    assert not codex.is_release("mcp gh: left as is, config.toml already has a server of that name")
    assert not codex.is_release("plugin x@y: failed: network")


def test_the_sync_notes_a_release_once(fake_home, fake_runner, monkeypatch):
    codex.set_enabled(True)
    monkeypatch.setattr(codex, "unavailable", lambda: None)
    line = "mcp gh: left as is in config.toml (changed by you); loadout no longer manages it"
    monkeypatch.setattr(codex, "apply_all", lambda bk, refresh=False, **kw: [line, "mcp x: left as is, config.toml "
                                                                             "already has a server of that name"])
    monkeypatch.setattr(codex, "drift", lambda: [])
    monkeypatch.setattr(maintenance, "pull_if_clean", lambda root: True)
    monkeypatch.setattr(maintenance, "find_outdated", lambda: [])
    from loadout import link, personal_mcp, settings_merge
    monkeypatch.setattr(settings_merge, "apply_settings", lambda: (None, None))
    monkeypatch.setattr(personal_mcp, "apply_mcp", lambda: [])
    monkeypatch.setattr(link, "link_all", lambda bk, retry_symlinks=False: [])
    (paths.personal_root() / ".git").mkdir(parents=True)
    maintenance._maintain(0)
    notice = (paths.state_dir() / "pending-notice").read_text(encoding="utf-8")
    assert f"loadout (Codex): {line}" in notice and "mcp x" not in notice
