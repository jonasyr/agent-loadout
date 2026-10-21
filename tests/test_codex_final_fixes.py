"""Final review findings for the Codex target (PR 1)."""
import json
import sys

import pytest

from loadout import backup, codex, paths, runner



def _personal_mcp(servers):
    path = paths.personal_root() / "mcp.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"mcpServers": servers}), encoding="utf-8")


def _apply():
    return codex.apply_config(backup.Backup(description="t"))


def test_owned_server_with_a_subtable_is_kept_not_orphaned(fake_home):
    """Codex refuses to start when [mcp_servers.foo.tools.bar] remains without [mcp_servers.foo]."""
    _personal_mcp({"foo": {"command": "foo"}})
    _apply()
    path = paths.codex_home() / "config.toml"
    path.write_text(path.read_text(encoding="utf-8") + '\n[mcp_servers.foo.tools.bar]\napproval_mode = "approve"\n', encoding="utf-8")
    _personal_mcp({})
    lines = _apply()
    import tomllib
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    assert data["mcp_servers"]["foo"]["command"] == "foo", "the server stays with its subtable"
    assert any("mcp foo: kept in config.toml" in l for l in lines), lines  # ADR 0036


def test_a_users_matching_key_stays_the_users(fake_home, monkeypatch):
    path = paths.codex_home() / "config.toml"
    path.parent.mkdir(parents=True)
    path.write_text('model_reasoning_effort = "medium"\n', encoding="utf-8")
    _apply()
    assert "model_reasoning_effort" not in json.loads(codex.record_path().read_text())["keys"]
    monkeypatch.setattr(codex, "desired_keys", lambda: [((), "model_reasoning_effort", "high", False)])
    _apply()
    assert 'model_reasoning_effort = "medium"' in path.read_text(encoding="utf-8")


def test_set_target_on_sets_codex_up_now(fake_home, fake_runner, monkeypatch, capsys):
    from loadout import configure
    from loadout.__main__ import main
    claude = []
    monkeypatch.setattr(configure, "apply_all", lambda ask: claude.append(1))
    monkeypatch.setattr(codex, "unavailable", lambda: None)
    monkeypatch.setattr(codex, "apply_all", lambda bk, refresh=False, **kw: ["instructions written to ~/.codex/AGENTS.md"])
    assert main(["configure", "set", "target", "codex", "on"]) == 0
    out = capsys.readouterr().out
    assert "instructions written" in out and claude == [] and codex.HOOKS_TODO in out


@pytest.fixture
def real_codex_home_exported(monkeypatch, tmp_path):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "real-codex-home"))


def test_fake_home_never_points_at_a_real_codex_home(real_codex_home_exported, fake_home):
    """A developer or CI job with CODEX_HOME exported must not get test files in it."""
    assert paths.codex_home() == fake_home / ".codex"


def test_no_undo_is_recorded_when_the_plugin_list_failed(fake_home, fake_runner, monkeypatch):
    from loadout import settings_merge
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: {"enabledPlugins": {"superpowers@claude-plugins-official": True}})
    fake_runner.responses[("codex", "plugin", "list")] = runner.Result(1, "", "boom")
    fake_runner.responses[("codex", "plugin", "marketplace", "add")] = runner.Result(
        0, json.dumps({"marketplaceName": "claude-plugins-official", "alreadyAdded": True}), "")
    bk = backup.Backup(description="t")
    codex.apply_plugins(bk)
    assert not any(s["undo"].get("run", [""])[:3] == ["codex", "plugin", "remove"] for s in bk.steps)


def test_marketplace_sources_must_be_owner_repo():
    settings = {"enabledPlugins": {"a@m1": True, "b@m2": True, "c@m3": True},
                "extraKnownMarketplaces": {"m1": {"source": {"source": "github", "repo": "--evil"}},
                                           "m2": {"source": {"source": "github", "repo": 7}},
                                           "m3": {"source": {"source": "github", "repo": "good-owner/good.repo"}}}}
    routes, missing = codex.plugin_routes(settings)
    assert routes == {"good-owner/good.repo": ["c"]} and sorted(missing) == ["a@m1", "b@m2"]


def test_restore_runs_only_codex_plugin_removals(fake_home, fake_runner):
    bk = backup.Backup(description="t")
    bk.record_command("ok", ["codex", "plugin", "marketplace", "remove", "m"])
    bk.record_command("bad", ["codex", "exec", "rm -rf ~"])
    lines, ok, _ = backup.restore(bk.root)
    assert ["codex", "plugin", "marketplace", "remove", "m"] in fake_runner.calls
    assert ["codex", "exec", "rm -rf ~"] not in fake_runner.calls and not ok


def test_slow_type_check_does_not_block(tmp_path, monkeypatch):
    sys.path.insert(0, str(paths.kit_root() / "plugins/loadout/hooks"))
    import io
    import typecheck
    monkeypatch.setattr(typecheck, "checks", lambda files: [(["sleep", "5"], tmp_path)])
    monkeypatch.setattr(typecheck, "LIMIT", 0.2)
    (tmp_path / "a.py").write_text("x = 1\n")
    out = io.StringIO()
    typecheck.main(io.StringIO(json.dumps({"cwd": str(tmp_path), "tool_input": {"command": "*** Update File: a.py\n"}})), out)
    reply = json.loads(out.getvalue()) if out.getvalue() else {}
    assert reply.get("decision") != "block"
    assert "skipped" in reply.get("hookSpecificOutput", {}).get("additionalContext", "")


def test_session_end_hook_fits_codex_limit():
    hooks = json.loads((paths.kit_root() / "plugins/loadout/hooks/codex.json").read_text())["hooks"]
    assert all(h.get("timeout", 1) <= 3 for g in hooks.get("SessionEnd", []) for h in g["hooks"])


def test_sync_does_not_notify_intentional_left_as_is_lines():
    from loadout import maintenance
    assert not maintenance.codex_notice("gh: left as is in config.toml (your value)")
    assert maintenance.codex_notice("plugin x@y: failed: network")
