from loadout import cbm, check


def test_conflict_replaces_the_auto_index_row(fake_home, monkeypatch):
    monkeypatch.setattr(cbm, "query", lambda: cbm.UNREADABLE)
    monkeypatch.setattr(check, "cbm_conflict_detail", lambda: "a codebase-memory-mcp session with a different cache folder could not start (another one already runs for your account)")
    assert check._cbm_auto_index() == []


def test_unreadable_without_conflict_says_where_to_look(fake_home, monkeypatch):
    monkeypatch.setattr(cbm, "query", lambda: cbm.UNREADABLE)
    monkeypatch.setattr(check, "cbm_conflict_detail", lambda: None)
    [row] = check._cbm_auto_index()
    assert row.fix == check.CBM_UNREADABLE_FIX and "to see why" not in row.fix


def test_bootstrap_line_names_the_conflict(fake_home, monkeypatch):
    monkeypatch.setattr(cbm, "answer", lambda: "on"); monkeypatch.setattr(cbm, "query", lambda: cbm.UNREADABLE)
    monkeypatch.setattr(check, "cbm_conflict_detail", lambda: "X already runs")
    assert cbm.apply_auto_index(object()) == ["codebase-memory: could not read auto_index: X already runs (see loadout check)"]
