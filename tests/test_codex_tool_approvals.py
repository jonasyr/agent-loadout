"""Codex's "Always allow" writes [mcp_servers.<name>.tools.<tool>] under a table loadout owns: those sub-tables are
the user's text inside a table loadout keeps managing (spec fix 4, ADR 0036)."""
import json
import tomllib

from loadout import backup, codex, paths, settings_merge

SUB = '[mcp_servers.serena.tools.serena_repl]\napproval_mode = "approve"\n'


def _cfg():
    return paths.codex_home() / "config.toml"


def _apply():
    return codex.apply_config(backup.Backup(description="t"))


def _with_sub(name: str, sub: str, comment: str = "") -> str:
    """The file as Codex leaves it after "Always allow": the parent, one blank line, the sub-table, one blank line,
    the next table."""
    text = _cfg().read_text(encoding="utf-8")
    parent = codex.read_record()["tables"][name]
    assert parent in text
    new = text.replace(parent, parent + "\n" + comment + sub, 1)
    _cfg().write_text(new, encoding="utf-8")
    return new


def _sub_lines(text: str, sub: str) -> bool:
    return sub.rstrip("\n") in text


def test_is_tool_section():
    assert codex.is_tool_section(("mcp_servers", "serena", "tools", "serena_repl"), "serena")
    assert not codex.is_tool_section(("mcp_servers", "serena", "tools"), "serena")
    assert not codex.is_tool_section(("mcp_servers", "serena", "env"), "serena")
    assert not codex.is_tool_section(("mcp_servers", "other", "tools", "x"), "serena")
    assert not codex.is_tool_section(None, "serena")


def test_always_allow_subtable_keeps_loadout_managing_serena(fake_home, monkeypatch):
    _apply()
    before = _with_sub("serena", SUB)
    serena_at = before.index("[mcp_servers.serena]")
    monkeypatch.setattr(codex, "SERENA", {**codex.SERENA, "args": [*codex.SERENA["args"], "--mode=x"]})
    lines = _apply()
    after = _cfg().read_text(encoding="utf-8")
    assert not any("left as is" in l for l in lines), lines
    assert "serena" in codex.read_record()["tables"] and "released" not in codex.read_record()
    assert '"--mode=x"' in after and _sub_lines(after, SUB)
    assert after.index("[mcp_servers.serena]") == serena_at, "replaced in place, not moved to the end"
    assert after.index("[mcp_servers.serena]") < after.index("[mcp_servers.serena.tools.serena_repl]")
    assert tomllib.loads(after)["mcp_servers"]["serena"]["tools"]["serena_repl"] == {"approval_mode": "approve"}
    assert _apply() == [] and _cfg().read_text(encoding="utf-8") == after


def test_in_place_replacement_is_backed_up(fake_home, monkeypatch):
    _apply()
    _with_sub("serena", SUB)
    monkeypatch.setattr(codex, "SERENA", {**codex.SERENA, "args": [*codex.SERENA["args"], "--mode=x"]})
    bk = backup.Backup(description="t")
    codex.apply_config(bk)
    assert not bk.empty


def test_user_comment_above_the_subtable_stays_with_it(fake_home, monkeypatch):
    _apply()
    comment = "# approved in Codex on Monday\n"
    _with_sub("serena", SUB, comment)
    assert _apply() == [], "the comment is not part of loadout's table"
    monkeypatch.setattr(codex, "SERENA", {**codex.SERENA, "args": [*codex.SERENA["args"], "--mode=x"]})
    lines = _apply()
    after = _cfg().read_text(encoding="utf-8")
    assert not any("left as is" in l for l in lines), lines
    assert (comment + SUB).rstrip("\n") in after
    assert "serena" in codex.read_record()["tables"]


def test_refresh_record_keeps_ownership_with_tools_subtable(fake_home, monkeypatch):
    from loadout import targets
    _apply()
    _with_sub("serena", "# mine\n" + SUB)
    monkeypatch.setattr(targets, "codex_enabled", lambda: True)
    assert codex.refresh_record() == []
    record = codex.read_record()
    assert "serena" in record["tables"] and "released" not in record
    assert any("mcp serena  loadout's value" in l for l in codex.explain_config())


def test_env_subtable_still_releases(fake_home):
    _apply()
    _with_sub("serena", '[mcp_servers.serena.env]\nX = "1"\n')
    lines = _apply()
    assert any("mcp serena: left as is in config.toml (it has sub-tables)" in l for l in lines), lines
    assert "serena" not in codex.read_record()["tables"] and codex.read_record()["released"] == ["serena"]


def test_dropping_a_table_with_tools_subtables_keeps_both_and_says_it_once(fake_home, monkeypatch):
    from loadout import targets
    monkeypatch.setattr(targets, "codex_enabled", lambda: True)
    _apply()
    assert "context7" in codex.read_record()["tables"]
    sub = '[mcp_servers.context7.tools.resolve-library-id]\napproval_mode = "approve"\n'
    written = _with_sub("context7", sub)
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: {"enabledPlugins": {}})
    lines = _apply()
    line = "mcp context7: kept in config.toml: your tool approvals ([mcp_servers.context7.tools.*]) need it"
    assert lines == [line] and codex.is_release(line)
    assert _cfg().read_text(encoding="utf-8") == written, "both stay, byte for byte"
    assert _apply() == [] and codex.apply_config(object(), dry_run=True) == [], "said once; check stays quiet"
    assert any("mcp context7  " in l and "kept" in l for l in codex.explain_config())
    # the approvals gone: loadout's table goes as any other it no longer wants
    _cfg().write_text(written.replace(sub, ""), encoding="utf-8")
    assert _apply() == []
    assert "context7" not in _cfg().read_text(encoding="utf-8") and "kept" not in codex.read_record()


def test_kept_table_wanted_again_is_quietly_loadouts(fake_home, monkeypatch):
    _apply()
    _with_sub("context7", '[mcp_servers.context7.tools.x]\napproval_mode = "approve"\n')
    real = settings_merge.desired_settings
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: {"enabledPlugins": {}})
    _apply()
    monkeypatch.setattr(settings_merge, "desired_settings", real)
    assert _apply() == [] and "kept" not in codex.read_record()
    assert "context7" in codex.read_record()["tables"]


def test_released_for_tools_only_is_managed_again(fake_home, monkeypatch):
    _apply()
    _with_sub("serena", SUB)
    record = codex.read_record()
    record["tables"].pop("serena")
    record["released"] = ["serena"]  # what a run before this change recorded
    codex.record_path().write_text(json.dumps(record), encoding="utf-8")
    assert _apply() == []
    record = codex.read_record()
    assert "serena" in record["tables"] and "released" not in record
    monkeypatch.setattr(codex, "SERENA", {**codex.SERENA, "args": [*codex.SERENA["args"], "--mode=x"]})
    _apply()
    assert '"--mode=x"' in _cfg().read_text(encoding="utf-8") and _sub_lines(_cfg().read_text(encoding="utf-8"), SUB)


def test_parse_guard_sees_the_approvals(fake_home):
    _apply()
    text = _with_sub("serena", SUB)
    tl = codex._tomllib()
    owned = set(codex.read_record()["tables"])
    before = tl.loads(text)
    kept = codex._without_owned(before, owned, [], tl)
    assert kept["mcp_servers"]["serena"] == {"tools": {"serena_repl": {"approval_mode": "approve"}}}
    dropped = tl.loads(text.replace(SUB, ""))  # a writer bug that loses the sub-table
    assert codex._without_owned(dropped, owned, [], tl) != kept, "the guard refuses such a write"
