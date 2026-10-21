"""Codex asks once whether it approves Serena's tools automatically: `approve` writes approval_mode = "approve" in
[mcp_servers.serena.tools.serena_repl] while loadout owns the serena table (spec fix 5, ADR 0036)."""
import json
import tomllib

from loadout import backup, codex, paths

TABLE = ("mcp_servers", "serena", "tools", "serena_repl")
DOTTED = "mcp_servers.serena.tools.serena_repl.approval_mode"
HEADER = "[mcp_servers.serena.tools.serena_repl]"
NOTE = ('Serena is your own server in config.toml; to approve its tools, choose "Always allow" in Codex')


def _cfg():
    return paths.codex_home() / "config.toml"


def _answer(value):
    f = paths.personal_root() / "loadout.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"codex": {"serena_approval": value}}), encoding="utf-8")


def _apply(bk=None):
    return codex.apply_config(bk or backup.Backup(description="t"))


def _text():
    return _cfg().read_text(encoding="utf-8")


def test_desired_keys_has_the_approval_only_for_approve(fake_home):
    key = (TABLE, "approval_mode", "approve", False)
    assert key not in codex.desired_keys(switches=False)
    _answer("approve")
    assert key in codex.desired_keys(switches=False)
    _answer("ask")
    assert key not in codex.desired_keys(switches=False)


def test_approve_writes_and_records_the_key_and_serena_stays_owned(fake_home):
    _answer("approve")
    assert _apply() == []
    data = tomllib.loads(_text())
    assert data["mcp_servers"]["serena"]["tools"]["serena_repl"] == {"approval_mode": "approve"}
    record = codex.read_record()
    assert record["keys"][DOTTED] == 'approval_mode = "approve"'
    assert "serena" in record["tables"] and "released" not in record and "kept" not in record
    assert _text().index("[mcp_servers.serena]") < _text().index(HEADER)
    after = _text()
    assert _apply() == [] and _text() == after


def test_refresh_record_leaves_loadouts_approval_alone(fake_home, monkeypatch):
    from loadout import targets
    monkeypatch.setattr(targets, "OVERRIDE", {"claude": True, "codex": True})
    _answer("approve")
    _apply()
    record = codex.read_record()
    assert codex.refresh_record() == []
    assert codex.read_record() == record


def test_switching_to_ask_removes_the_key_and_the_header_loadout_added(fake_home):
    _answer("ask")
    _apply()
    plain = _text()
    _answer("approve")
    _apply()
    assert HEADER in _text()
    _answer("ask")
    bk = backup.Backup(description="t")
    assert _apply(bk) == []
    assert _text() == plain
    assert not bk.empty, "the removal is backed up"
    record = codex.read_record()
    assert DOTTED not in record["keys"] and "serena" in record["tables"]
    assert _apply() == [] and _text() == plain


def test_a_user_section_gets_only_loadouts_line_and_keeps_the_rest(fake_home):
    _answer("ask")
    _apply()
    mine = _text() + f"\n{HEADER}\n# mine\nenabled = true\n"
    _cfg().write_text(mine, encoding="utf-8")
    _answer("approve")
    assert _apply() == []
    data = tomllib.loads(_text())
    assert data["mcp_servers"]["serena"]["tools"]["serena_repl"] == {"enabled": True, "approval_mode": "approve"}
    assert codex.read_record()["keys"][DOTTED] == 'approval_mode = "approve"'
    assert "serena" in codex.read_record()["tables"]
    _answer("ask")
    _apply()
    assert _text() == mine, "only loadout's line goes; your header and key stay"
    assert DOTTED not in codex.read_record()["keys"]


def test_a_user_written_approval_mode_stays(fake_home):
    _answer("ask")
    _apply()
    mine = _text() + f"\n{HEADER}\napproval_mode = \"approve\"\n"
    _cfg().write_text(mine, encoding="utf-8")
    _answer("approve")
    assert _apply() == []
    assert _text() == mine
    assert DOTTED not in codex.read_record()["keys"]
    _answer("ask")
    assert _apply() == []
    assert _text() == mine, "your own approval_mode is not loadout's to remove"


def test_dropped_serena_table_takes_loadouts_approval_with_it(fake_home, monkeypatch):
    _answer("approve")
    _apply()
    monkeypatch.setattr(codex, "desired_tables", lambda skip_serena=False: ({}, []))
    lines = _apply()
    assert not any(codex.KEPT in l for l in lines), lines
    assert "serena" not in _text()
    assert DOTTED not in codex.read_record()["keys"]


def test_own_serena_table_is_never_changed_and_the_note_comes_once(fake_home, monkeypatch):
    from loadout import targets
    monkeypatch.setattr(targets, "OVERRIDE", {"claude": True, "codex": True})
    _cfg().parent.mkdir(parents=True, exist_ok=True)
    own = '[mcp_servers.serena]\ncommand = "serena"\nargs = ["start-mcp-server", "--context=codex"]\n'
    _cfg().write_text(own, encoding="utf-8")
    _apply()
    before = _text()
    _answer("approve")
    lines = _apply()
    assert _text() == before
    assert [l for l in lines if NOTE in l] == [NOTE]
    assert DOTTED not in codex.read_record()["keys"]
    assert NOTE not in " ".join(_apply()), "said once"
    assert _text() == before
    assert codex.refresh_record() == []
    assert _text() == before and DOTTED not in codex.read_record()["keys"]


def test_serena_you_changed_keeps_the_approval_line_as_yours(fake_home):
    _answer("approve")
    _apply()
    mine = _text().replace('"--context=codex"', '"--context=codex", "--mine"', 1)
    assert mine != _text()
    _cfg().write_text(mine, encoding="utf-8")
    lines = _apply()
    assert any("changed by you" in l for l in lines), lines
    assert _text() == mine, "your table and the approval under it stay as they are"
    assert DOTTED not in codex.read_record()["keys"]


SETUP_SHAPE = '[mcp_servers.serena]\ncommand = "serena"\nargs = ["start-mcp-server", "--context=codex"]\n'


def _replace_serena_with_own():
    """loadout's serena table replaced by the shape `serena setup codex` writes; the approval under it stays."""
    text = _text()
    parent = codex.read_record()["tables"]["serena"]
    mine = text.replace(parent, SETUP_SHAPE, 1)
    assert mine != text
    _cfg().write_text(mine, encoding="utf-8")
    return mine


def test_ask_never_touches_the_approval_once_serena_is_yours_in_the_same_run(fake_home):
    _answer("approve")
    _apply()
    mine = _replace_serena_with_own()
    _answer("ask")
    _apply()
    assert _text() == mine, "your own Serena and the approval under it stay"
    record = codex.read_record()
    assert DOTTED not in record["keys"] and "added_headers" not in record
    _answer("approve")
    _apply()
    _answer("ask")
    _apply()
    assert _text() == mine


def test_ask_never_touches_the_approval_once_refresh_released_serena(fake_home, monkeypatch):
    from loadout import targets
    monkeypatch.setattr(targets, "OVERRIDE", {"claude": True, "codex": True})
    _answer("approve")
    _apply()
    mine = _replace_serena_with_own()
    codex.refresh_record()
    record = codex.read_record()
    assert DOTTED not in record["keys"] and "added_headers" not in record
    _answer("ask")
    _apply()
    assert _text() == mine


def test_no_note_when_loadouts_serena_was_just_released(fake_home):
    _answer("approve")
    _apply()
    _replace_serena_with_own()
    lines = _apply()
    assert not any(NOTE in l for l in lines), lines


def test_a_deleted_serena_table_keeps_loadouts_approval_whether_or_not_refresh_ran(fake_home, monkeypatch):
    from loadout import targets
    monkeypatch.setattr(targets, "OVERRIDE", {"claude": True, "codex": True})
    results = []
    for refresh in (False, True):
        _cfg().unlink(missing_ok=True)
        codex.record_path().unlink(missing_ok=True)
        _answer("ask")
        _apply()
        plain = _text()
        _answer("approve")
        _apply()
        parent = codex.read_record()["tables"]["serena"]
        _cfg().write_text(_text().replace(parent, "", 1), encoding="utf-8")  # only the [mcp_servers.serena] block
        if refresh:
            codex.refresh_record()
            assert DOTTED in codex.read_record()["keys"], "a gone table is no release: the line stays loadout's"
        _apply()
        assert "serena" in codex.read_record()["tables"]
        _answer("ask")
        _apply()
        assert 'approval_mode = "approve"' not in _text()
        assert DOTTED not in codex.read_record()["keys"]
        results.append(tomllib.loads(_text()) == tomllib.loads(plain))
    assert results == [True, True]
