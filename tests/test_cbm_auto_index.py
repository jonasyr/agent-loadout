"""codebase-memory indexes a new git repo by itself (cbm_auto_index): applied with `config set auto_index`, undoable,
and a value the user set is never changed."""
import json

from loadout import backup, cbm, check, paths, runner

GET = ("codebase-memory-mcp", "config", "get", "auto_index")
SET_TRUE = ["codebase-memory-mcp", "config", "set", "auto_index", "true"]
SET_FALSE = ["codebase-memory-mcp", "config", "set", "auto_index", "false"]
ON_LINE = "codebase-memory: auto_index on (new git repos are indexed at their first session)"


def _answer(value):
    f = paths.personal_root() / "loadout.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"cbm": {"auto_index": value}}), encoding="utf-8")


def _record():
    return paths.state_dir() / "cbm-auto-index.json"


def _value(fake_runner, text):
    fake_runner.responses[GET] = runner.Result(0, text, "")


def _sets(fake_runner):
    return [c for c in fake_runner.calls if c[:3] == ["codebase-memory-mcp", "config", "set"]]


def test_auto_index_turned_on_with_undo(fake_home, fake_runner):
    _value(fake_runner, "false\n")
    bk = backup.Backup(description="t")
    assert cbm.apply_auto_index(bk) == [ON_LINE]
    assert _sets(fake_runner) == [SET_TRUE]
    manifest = json.loads((bk.root / "manifest.json").read_text(encoding="utf-8"))
    assert {"run": SET_FALSE} in [s["undo"] for s in manifest["steps"]]
    assert json.loads(_record().read_text(encoding="utf-8")) == {"set": "true"}
    _value(fake_runner, "true\n")  # a second run changes nothing
    assert cbm.apply_auto_index(backup.Backup(description="t")) == []
    assert len(_sets(fake_runner)) == 1


def test_auto_index_respects_users_own_value(fake_home, fake_runner):
    _record().parent.mkdir(parents=True, exist_ok=True)
    _record().write_text(json.dumps({"set": "true"}), encoding="utf-8")
    _value(fake_runner, "false\n")
    bk = backup.Backup(description="t")
    assert cbm.apply_auto_index(bk) == ["codebase-memory: auto_index off (yours)"]
    assert _sets(fake_runner) == [] and bk.empty


def test_auto_index_off_answer_reverts_only_ours(fake_home, fake_runner):
    _answer("off")
    _value(fake_runner, "true\n")
    assert cbm.apply_auto_index(backup.Backup(description="t")) == []  # not ours: left alone
    assert _sets(fake_runner) == []
    _record().parent.mkdir(parents=True, exist_ok=True)
    _record().write_text(json.dumps({"set": "true"}), encoding="utf-8")
    bk = backup.Backup(description="t")
    lines = cbm.apply_auto_index(bk)
    assert _sets(fake_runner) == [SET_FALSE] and not _record().exists() and lines
    manifest = json.loads((bk.root / "manifest.json").read_text(encoding="utf-8"))
    assert {"run": SET_TRUE} in [s["undo"] for s in manifest["steps"]]


def test_auto_index_dry_run_changes_nothing(fake_home, fake_runner):
    _value(fake_runner, "false\n")
    bk = backup.Backup(description="t")
    assert cbm.apply_auto_index(bk, dry=True) == [ON_LINE]
    assert _sets(fake_runner) == [] and bk.empty and not _record().exists()


def test_auto_index_binary_missing_says_nothing(fake_home, fake_runner):
    fake_runner.responses[GET] = runner.Result(127, "", "codebase-memory-mcp: not found")
    assert cbm.apply_auto_index(backup.Backup(description="t")) == []
    assert _sets(fake_runner) == []


def test_restore_replays_auto_index_undo(fake_home, fake_runner):
    _value(fake_runner, "false\n")
    bk = backup.Backup(description="t")
    cbm.apply_auto_index(bk)
    fake_runner.calls.clear()
    lines, ok, _ = backup.restore(bk.root)
    assert ok, lines
    assert SET_FALSE in fake_runner.calls
    assert not _record().exists()
    for bad in (["codebase-memory-mcp", "config", "set", "auto_index", "maybe"],
                ["codebase-memory-mcp", "config", "set", "other", "true"],
                ["codebase-memory-mcp", "config", "set", "auto_index", "true", "x"]):
        assert not backup._allowed_run(bad)


def test_check_row_auto_index(fake_home, fake_runner):
    _value(fake_runner, "true\n")
    row, = check._cbm_auto_index()
    assert (row.name, row.ok, row.detail) == ("codebase-memory auto_index", True, "on")
    _value(fake_runner, "false\n")
    assert check._cbm_auto_index()[0].detail == "off (loadout turns it on at the next update)"
    _record().parent.mkdir(parents=True, exist_ok=True)
    _record().write_text(json.dumps({"set": "true"}), encoding="utf-8")
    assert check._cbm_auto_index()[0].detail == "off (yours)"
    _answer("off")
    row = check._cbm_auto_index()[0]
    assert row.ok and row.detail == "off (your answer)"
    fake_runner.missing.add("codebase-memory-mcp")
    assert check._cbm_auto_index() == []


def test_unreadable_preferences_change_nothing(fake_home, fake_runner):
    f = paths.personal_root() / "loadout.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("{not json", encoding="utf-8")
    _value(fake_runner, "false\n")
    assert cbm.apply_auto_index(backup.Backup(description="t")) == []
    assert _sets(fake_runner) == [] and not _record().exists()


def test_record_that_is_not_an_object_is_no_record(fake_home, fake_runner):
    _record().parent.mkdir(parents=True, exist_ok=True)
    _record().write_text("[1]", encoding="utf-8")
    _value(fake_runner, "false\n")
    assert cbm.apply_auto_index(backup.Backup(description="t")) == [ON_LINE]


def test_configure_set_pref_choice_off_reverts_ours_at_once(fake_home, fake_runner):
    from loadout.__main__ import main
    _value(fake_runner, "false\n")
    cbm.apply_auto_index(backup.Backup(description="t"))
    _value(fake_runner, "true\n")
    fake_runner.calls.clear()
    assert main(["configure", "set", "pref-choice", "cbm_auto_index", "off"]) == 0
    assert SET_FALSE in fake_runner.calls and not _record().exists()
