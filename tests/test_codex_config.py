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
    assert codex.toml_value(15) == "15" and codex.toml_value(True) == "true" and codex.toml_value(["a", "b"]) == '["a", "b"]'
    assert codex.toml_value({"K": "v", "with.dot": "x"}) == '{ K = "v", "with.dot" = "x" }'
    with pytest.raises(codex.Refused):
        codex.toml_value(3.5)


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
    assert '[mcp_servers.serena]\ncommand = "serena"\nargs = ["start-mcp-server", "--project-from-cwd", "--context=codex"]\nstartup_timeout_sec = 15\n' in text
    assert text.startswith('model_reasoning_effort = "medium"\n')
    assert "[tui]\nnotifications = true\n" in text
    record = json.loads(codex.record_path().read_text())
    assert set(record["tables"]) == {"gh", "serena", "context7"}  # context7: the kit enables it and set(record["keys"]) == {"model_reasoning_effort", "tui.notifications"}


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


# --- review findings (Task 3): the user's file must stay intact, secrets must never reach it



def _write(text):
    path = paths.codex_home() / "config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_header_inside_a_multiline_string_is_not_a_table(fake_home):
    user = 'instructions = """\nfoo\n[tui]\nnotifications = false\n[mcp_servers.serena]\ncommand = "evil"\n"""\n'
    _write(user)
    _apply()
    text = _config()
    import tomllib
    data = tomllib.loads(text)
    assert data["instructions"] == tomllib.loads(user)["instructions"], "the user's string is untouched"
    assert data["model_reasoning_effort"] == "medium" and data["tui"] == {"notifications": True}
    assert data["mcp_servers"]["serena"]["command"] == "serena"


def test_header_inside_a_multiline_array_and_stray_bracket_line_are_safe(fake_home):
    user = 'notify = [\n  "a",\n]\nx = """\n[unclosed\n"""\n'
    _write(user)
    _apply()  # must not raise
    assert 'notify = [\n  "a",\n]\nx = """\n[unclosed\n"""' in _config()


def test_an_edit_that_would_change_user_content_writes_nothing(fake_home):
    user = '[mcp_servers.gh]\ncommand = "mine"\n\n[mcp_servers.gh.env]\nX = "1"\n'
    path = _write(user)
    _personal_mcp({"gh": {"command": "gh-mcp"}})
    _apply()
    assert 'command = "mine"' in path.read_text(encoding="utf-8") and "gh-mcp" not in path.read_text(encoding="utf-8")


def test_secrets_in_args_and_url_are_refused():
    with pytest.raises(codex.Refused, match="secret"):
        codex.server("gh", {"command": "gh-mcp", "args": ["--token", "ghp_" + "a1B2" * 9]})
    with pytest.raises(codex.Refused, match="secret"):
        codex.server("api", {"url": "https://x.example/mcp?api_key=" + "Zq9x" * 12})


def test_variables_codex_would_not_expand_are_refused():
    with pytest.raises(codex.Refused, match="expand"):
        codex.server("gh", {"command": "gh-mcp", "args": ["--token=${GH}"]})
    with pytest.raises(codex.Refused, match="expand"):
        codex.server("api", {"url": "https://x.example/${TEAM}/mcp"})


@pytest.mark.parametrize("cfg", [None, {"command": "x", "env": {"PORT": 8080}}, {"command": "x", "env": ["A"]},
                                 {"url": "https://x", "headers": {"X": 1}}, {"command": "x", "args": [1]}])
def test_malformed_personal_configs_are_refused_not_crashing(cfg):
    with pytest.raises(codex.Refused):
        codex.server("x", cfg)


def test_del_character_is_escaped():
    assert codex.toml_value("a\x7fb") == '"a\\u007fb"'


def test_unencodable_value_leaves_the_file_intact(fake_home):
    path = _write('model_reasoning_effort = "high"\n')
    _personal_mcp({"x": {"command": "x", "args": ["a\ud800"]}})
    lines = _apply()
    text = path.read_text(encoding="utf-8")
    assert "[mcp_servers.x]" not in text and 'model_reasoning_effort = "high"' in text
    assert any("mcp x" in l and "skipped" in l for l in lines)


def test_release_is_remembered_even_when_the_file_does_not_change(fake_home):
    _personal_mcp({"gh": {"command": "gh-mcp"}})
    _apply()
    path = paths.codex_home() / "config.toml"
    path.write_text(_config().replace('command = "gh-mcp"', 'command = "gh-mcp"\nstartup_timeout_sec = 30'), encoding="utf-8")
    first = _apply()
    second = _apply()
    assert len(first) == 1 and "changed by you" in first[0]  # one line for one table, no "already has a server"
    assert second == []


def test_a_released_table_stays_quiet_until_you_remove_it(fake_home):
    _personal_mcp({"gh": {"command": "gh-mcp"}})
    _apply()
    path = paths.codex_home() / "config.toml"
    path.write_text(_config().replace('command = "gh-mcp"', 'command = "gh-mcp"\nstartup_timeout_sec = 30'), encoding="utf-8")
    mine = path.read_bytes()
    _apply()
    assert codex.apply_config(object(), dry_run=True) == []  # check and the update plan say nothing about it
    assert codex.read_record()["released"] == ["gh"] and path.read_bytes() == mine
    path.write_text(_config().replace('[mcp_servers.gh]\ncommand = "gh-mcp"\nstartup_timeout_sec = 30\n', ""),
                    encoding="utf-8")
    _apply()
    assert '[mcp_servers.gh]\ncommand = "gh-mcp"\n' in _config() and "released" not in codex.read_record()


def test_dry_run_does_not_promise_an_edit_that_would_be_skipped(fake_home):
    _write('tui.notifications = false\n')
    assert not any("changes pending" in l for l in codex.apply_config(backup.Backup(description="t"), dry_run=True))
