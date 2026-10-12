"""loadout's own tables and keys in ~/.codex/config.toml: written, updated, removed only while unchanged."""
import json
import sys

import pytest

from loadout import backup, codex, paths


def _personal_mcp(servers):
    path = paths.personal_root() / "mcp.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"mcpServers": servers}), encoding="utf-8")


def _config():
    return (paths.codex_home() / "config.toml").read_text(encoding="utf-8")


def _apply():
    return codex.apply_config(backup.Backup(description="t"))


def test_values_are_toml():
    assert codex.toml_value('a "quoted"\\path\n') == '"a \\"quoted\\"\\\\path\\n"'
    assert codex.toml_value(True) == "true" and codex.toml_value(["a", "b"]) == '["a", "b"]'
    assert codex.toml_value({"K": "v", "with.dot": "x"}) == '{ K = "v", "with.dot" = "x" }'
    with pytest.raises(codex.Refused):
        codex.toml_value(3)


def test_stdio_server_forwards_secrets_by_name():
    s = codex.server("gh", {"command": "gh-mcp", "args": ["--x"], "env": {"GITHUB_TOKEN": "${GITHUB_TOKEN}", "MODE": "ro"}})
    assert s == {"command": "gh-mcp", "args": ["--x"], "env": {"MODE": "ro"}, "env_vars": ["GITHUB_TOKEN"]}


def test_http_server_maps_bearer_and_headers():
    s = codex.server("api", {"type": "http", "url": "https://x.example/mcp",
                             "headers": {"Authorization": "Bearer ${API_TOKEN}", "X-Team": "${TEAM_ID}", "X-Mode": "ro"}})
    assert s == {"url": "https://x.example/mcp", "bearer_token_env_var": "API_TOKEN",
                 "http_headers": {"X-Mode": "ro"}, "env_http_headers": {"X-Team": "TEAM_ID"}}


def test_plaintext_secret_is_refused():
    with pytest.raises(codex.Refused, match="secrets.env"):
        codex.server("gh", {"command": "gh-mcp", "env": {"GITHUB_TOKEN": "ghp_" + "a1B2" * 9}})


def test_renamed_variable_is_refused():
    with pytest.raises(codex.Refused, match="own name"):
        codex.server("gh", {"command": "gh-mcp", "env": {"GITHUB_TOKEN": "${GH_PAT}"}})


def test_unsupported_keys_are_refused():
    with pytest.raises(codex.Refused, match="timeout"):
        codex.server("x", {"command": "x", "timeout": 5})


def test_writes_servers_serena_and_keys(fake_home):
    _personal_mcp({"gh": {"command": "gh-mcp", "env": {"GITHUB_TOKEN": "${GITHUB_TOKEN}"}}})
    _apply()
    text = _config()
    assert "[mcp_servers.gh]\ncommand = \"gh-mcp\"\nenv_vars = [\"GITHUB_TOKEN\"]\n" in text
    assert '[mcp_servers.serena]\ncommand = "serena"\nargs = ["start-mcp-server", "--context=codex", "--project-from-cwd"]\n' in text
    assert text.startswith('model_reasoning_effort = "medium"\n')
    assert "[tui]\nnotifications = true\n" in text
    record = json.loads(codex.record_path().read_text())
    assert set(record["tables"]) == {"gh", "serena"} and set(record["keys"]) == {"model_reasoning_effort", "tui.notifications"}


def test_second_run_changes_nothing(fake_home):
    _personal_mcp({"gh": {"command": "gh-mcp"}})
    _apply()
    before = _config()
    assert _apply() == [] and _config() == before


def test_removed_server_disappears_and_changed_one_is_replaced(fake_home):
    _personal_mcp({"a": {"command": "a"}, "b": {"command": "b"}})
    _apply()
    _personal_mcp({"b": {"command": "b2"}})
    _apply()
    text = _config()
    assert "[mcp_servers.a]" not in text and 'command = "b2"' in text and 'command = "b"\n' not in text


def test_foreign_table_and_key_are_left_alone(fake_home):
    path = paths.codex_home() / "config.toml"
    path.parent.mkdir(parents=True)
    mine = 'model_reasoning_effort = "high"\n\n[mcp_servers.gh]\ncommand = "my-own-gh"\n'
    path.write_text(mine, encoding="utf-8")
    _personal_mcp({"gh": {"command": "gh-mcp"}})
    lines = _apply()
    text = _config()
    assert 'model_reasoning_effort = "high"' in text and 'command = "my-own-gh"' in text and "gh-mcp" not in text
    assert any("gh" in l and "left as is" in l for l in lines)
    assert any("model_reasoning_effort" in l and "left as is" in l for l in lines)


def test_user_edit_of_an_owned_table_is_kept(fake_home):
    _personal_mcp({"gh": {"command": "gh-mcp"}})
    _apply()
    path = paths.codex_home() / "config.toml"
    path.write_text(_config().replace('command = "gh-mcp"', 'command = "gh-mcp"\nstartup_timeout_sec = 30'), encoding="utf-8")
    _personal_mcp({})
    lines = _apply()
    assert "startup_timeout_sec = 30" in _config() and any("changed by you" in l for l in lines)


def test_existing_tui_table_gets_the_key(fake_home):
    path = paths.codex_home() / "config.toml"
    path.parent.mkdir(parents=True)
    path.write_text('[tui]\ntheme = "dark"\n', encoding="utf-8")
    _apply()
    text = _config()
    assert text.count("[tui]") == 1 and "[tui]\ntheme = \"dark\"\nnotifications = true\n" in text


@pytest.mark.skipif(sys.version_info < (3, 11), reason="the parse check needs tomllib")
def test_unparseable_result_writes_nothing(fake_home):
    path = paths.codex_home() / "config.toml"
    path.parent.mkdir(parents=True)
    weird = 'tui.notifications = false\n'  # a dotted key: adding a [tui] table would redefine it
    path.write_text(weird, encoding="utf-8")
    lines = _apply()
    assert path.read_text(encoding="utf-8") == weird
    assert any(l.startswith("skipped") and "parse" in l for l in lines)


def test_dry_run_reports_pending_changes_without_writing(fake_home):
    _personal_mcp({"gh": {"command": "gh-mcp"}})
    assert codex.apply_config(backup.Backup(description="t"), dry_run=True) == ["config.toml: changes pending"]
    assert not (paths.codex_home() / "config.toml").exists()
