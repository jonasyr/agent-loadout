"""Open Codex steps are named where the user works (bootstrap, configure, check) and automated where Codex allows it."""
import json
import sys

import pytest

from loadout import bootstrap, check, codex, paths, runner

needs_tomllib = pytest.mark.skipif(sys.version_info < (3, 11), reason="reads config.toml with tomllib")


def _trust(keys, hash_="sha256:aa"):
    path = paths.codex_home() / "config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f'[hooks.state."{k}"]\ntrusted_hash = "{hash_}"\n\n' for k in keys), encoding="utf-8")


def test_expected_hook_keys_follow_codex_json():
    keys = codex.hook_keys()
    assert len(keys) == 9
    assert "loadout@agent-loadout:hooks/codex.json:pre_tool_use:0:0" in keys
    assert "loadout@agent-loadout:hooks/codex.json:subagent_start:0:0" in keys


@needs_tomllib
def test_hooks_status_untrusted_trusted_and_changed(fake_home, monkeypatch):
    assert codex.hooks_status() == "untrusted"
    _trust(codex.hook_keys())
    assert codex.hooks_status(remember=True) == "trusted"
    monkeypatch.setattr(codex, "_hooks_digest", lambda: "new-content")
    assert codex.hooks_status() == "changed", "same approvals, different hooks: approve again"
    _trust(codex.hook_keys(), hash_="sha256:bb")  # the user approved again
    assert codex.hooks_status(remember=True) == "trusted"


@needs_tomllib
def test_still_to_do_names_hooks_only_while_not_approved(fake_home, fake_runner):
    codex.set_enabled(True)
    fake_runner.responses[("codex", "mcp", "list")] = runner.Result(0, "[]", "")
    assert any("/hooks" in line for line in bootstrap.still_to_do("linux"))
    _trust(codex.hook_keys())
    assert not any("/hooks" in line for line in bootstrap.still_to_do("linux"))


def test_servers_that_need_a_login_are_named(fake_home, fake_runner):
    codex.set_enabled(True)
    fake_runner.responses[("codex", "mcp", "list")] = runner.Result(0, json.dumps([
        {"name": "x-docs", "auth_status": "not_logged_in"}, {"name": "serena", "auth_status": "unsupported"}]), "")
    assert codex.logins_needed() == ["x-docs"]
    assert any("codex mcp login x-docs" in line for line in bootstrap.still_to_do("linux"))


@needs_tomllib
def test_check_reports_hooks_and_logins(fake_home, fake_runner, monkeypatch):
    codex.set_enabled(True)
    monkeypatch.setattr(codex, "unavailable", lambda: None)
    monkeypatch.setattr(codex, "installed_plugins", lambda: {"loadout@agent-loadout"})
    monkeypatch.setattr(codex, "drift", lambda: [])
    fake_runner.responses[("codex", "mcp", "list")] = runner.Result(0, json.dumps([{"name": "x-docs", "auth_status": "not_logged_in"}]), "")
    results = {r.name: r for r in check.run_checks() if r.name.startswith("Codex")}
    assert not results["Codex hooks"].ok and "/hooks" in results["Codex hooks"].fix
    assert not results["Codex logins"].ok and "codex mcp login x-docs" in results["Codex logins"].fix


@needs_tomllib
def test_context7_needs_no_login_in_codex(fake_home, monkeypatch):
    from loadout import settings_merge
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: {"enabledPlugins": {"context7@claude-plugins-official": True}})
    tables, _ = codex.desired_tables()
    assert 'url = "https://mcp.context7.com/mcp"' in tables["context7"]
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: {"enabledPlugins": {}})
    assert "context7" not in codex.desired_tables()[0]
