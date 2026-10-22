"""Open Codex steps are named where the user works (bootstrap, configure, check) and automated where Codex allows it."""
import json
import sys

import pytest

from loadout import bootstrap, check, codex, paths, runner



PLUGIN_ON = '[plugins."loadout@agent-loadout"]\nenabled = true\n\n'  # the plugin is installed: its hooks count


def _plugin_on():
    path = paths.codex_home() / "config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(PLUGIN_ON, encoding="utf-8")


def _trust(keys, hash_="sha256:aa"):
    path = paths.codex_home() / "config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(PLUGIN_ON + "".join(f'[hooks.state.{codex.toml_value(k)}]\ntrusted_hash = "{hash_}"\n\n' for k in keys), encoding="utf-8")


def test_expected_hook_keys_follow_codex_json():
    keys = codex.hook_keys()
    assert len(keys) == 6  # Serena's hooks live in ~/.codex/hooks.json (ADR 0028)
    assert "loadout@agent-loadout:hooks/codex.json:pre_tool_use:0:0" in keys
    assert "loadout@agent-loadout:hooks/codex.json:subagent_start:0:0" in keys


def test_hooks_status_needs_the_serena_hooks_in_hooks_json_approved_too(fake_home, fake_runner, monkeypatch):
    from loadout import backup, codex_hooks
    monkeypatch.setattr(runner, "have", lambda b: b == "serena-hooks")
    codex_hooks.apply(backup.Backup(description="t"))
    _trust(codex.hook_keys())
    assert codex.hooks_status() == "untrusted"  # Codex runs hooks.json entries only after /hooks too
    hooks_json = str(codex_hooks.path())
    owned = {f"{hooks_json}:{ev}:0:0" for ev in ("pre_tool_use", "post_tool_use", "session_start",
                                                 "user_prompt_submit", "session_end")} | {f"{hooks_json}:pre_tool_use:1:0"}
    assert codex_hooks.trust_keys() == owned
    _trust(codex.hook_keys() | owned)
    assert codex.hooks_status() == "trusted"


def test_hooks_status_untrusted_trusted_and_changed(fake_home, fake_runner, monkeypatch):
    _plugin_on()
    assert codex.hooks_status() == "untrusted"
    _trust(codex.hook_keys())
    assert codex.hooks_status(remember=True) == "trusted"
    monkeypatch.setattr(codex, "_hooks_digest", lambda: "new-content")
    assert codex.hooks_status() == "changed", "same approvals, different hooks: approve again"
    _trust(codex.hook_keys(), hash_="sha256:bb")  # the user approved again
    assert codex.hooks_status(remember=True) == "trusted"


def test_still_to_do_names_hooks_only_while_not_approved(fake_home, fake_runner):
    codex.set_enabled(True)
    fake_runner.responses[("codex", "mcp", "list")] = runner.Result(0, "[]", "")
    _plugin_on()
    assert any("/hooks" in line for line in bootstrap.still_to_do("linux"))
    _trust(codex.hook_keys())
    assert not any("/hooks" in line for line in bootstrap.still_to_do("linux"))


def test_servers_that_need_a_login_are_named(fake_home, fake_runner):
    codex.set_enabled(True)
    fake_runner.responses[("codex", "mcp", "list")] = runner.Result(0, json.dumps([
        {"name": "x-docs", "auth_status": "not_logged_in"}, {"name": "serena", "auth_status": "unsupported"}]), "")
    assert codex.logins_needed() == ["x-docs"]
    assert any("codex mcp login x-docs" in line for line in bootstrap.still_to_do("linux"))


def test_check_reports_hooks_and_logins(fake_home, fake_runner, monkeypatch):
    codex.set_enabled(True)
    monkeypatch.setattr(codex, "unavailable", lambda: None)
    monkeypatch.setattr(codex, "installed_plugins", lambda: {"loadout@agent-loadout"})
    monkeypatch.setattr(codex, "drift", lambda: [])
    fake_runner.responses[("codex", "mcp", "list")] = runner.Result(0, json.dumps([{"name": "x-docs", "auth_status": "not_logged_in"}]), "")
    _plugin_on()
    results = {r.name: r for r in check.run_checks() if r.name.startswith("Codex")}
    assert not results["Codex hooks"].ok and "/hooks" in results["Codex hooks"].fix
    assert not results["Codex logins"].ok and "codex mcp login x-docs" in results["Codex logins"].fix


def test_context7_needs_no_login_in_codex(fake_home, monkeypatch):
    from loadout import settings_merge
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: {"enabledPlugins": {"context7@claude-plugins-official": True}})
    tables, _ = codex.desired_tables()
    assert 'url = "https://mcp.context7.com/mcp"' in tables["context7"]
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: {"enabledPlugins": {}})
    assert "context7" not in codex.desired_tables()[0]


def test_servers_loadout_set_up_are_not_reported_as_needing_a_login(fake_home, fake_runner):
    """Codex reports not_logged_in for any server that offers OAuth, also when it answers without a login
    (Context7's plain address, verified live). loadout's own servers are known to work without one."""
    codex.set_enabled(True)
    codex.record_path().parent.mkdir(parents=True, exist_ok=True)
    codex.record_path().write_text(json.dumps({"tables": {"context7": "x"}, "keys": {}}))
    fake_runner.responses[("codex", "mcp", "list")] = runner.Result(0, json.dumps([
        {"name": "context7", "auth_status": "not_logged_in"}, {"name": "other", "auth_status": "not_logged_in"}]), "")
    assert codex.logins_needed() == ["other"]
    assert codex.logins_optional() == ["context7"]
    steps = codex.open_steps()
    assert any("optional" in s and "codex mcp login context7" in s and "higher limits" in s for s in steps)
    assert any(s.startswith("log in to other") for s in steps)


def test_an_identical_existing_server_is_not_a_conflict(fake_home):
    """The user's own serena that already has the Codex context: nothing to report, nothing to claim."""
    from loadout import backup
    path = paths.codex_home() / "config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('[mcp_servers.serena]\ncommand = "serena"\nargs = ["start-mcp-server", "--context=codex", "--project-from-cwd"]\n',
                    encoding="utf-8")
    lines = codex.apply_config(backup.Backup(description="t"))
    assert not any("serena" in l for l in lines)
    assert "serena" not in json.loads(codex.record_path().read_text())["tables"]


def test_set_target_offers_to_commit_the_personal_layer(fake_home, fake_runner, monkeypatch):
    from loadout import configure
    from loadout.__main__ import main
    offered = []
    monkeypatch.setattr(configure, "offer_commit", lambda ask: offered.append(1))
    monkeypatch.setattr(codex, "unavailable", lambda: None)
    monkeypatch.setattr(codex, "apply_all", lambda bk, refresh=False, **kw: [])
    monkeypatch.setattr(codex, "open_steps", lambda: [])
    main(["configure", "set", "target", "codex", "on"])
    assert offered == [1]
