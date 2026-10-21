"""A preference stored in the personal layer's loadout.json (target {"loadout": "codex.serena_approval"}), and a
preference for one agent only ("agents": ["codex"]) that is skipped while that agent is off (spec fix 5, ADR 0036)."""
import json

import pytest

from loadout import answers, backup, bootstrap, configure, paths, preferences, targets

PID = "codex_serena_approval"


@pytest.fixture
def codex_on(monkeypatch):
    monkeypatch.setattr(targets, "OVERRIDE", {"claude": True, "codex": True})


@pytest.fixture
def codex_off(monkeypatch):
    monkeypatch.setattr(targets, "OVERRIDE", {"claude": True, "codex": False})


def _file():
    return paths.personal_root() / "loadout.json"


def _asker(answers_=None):
    asked, queue = [], list(answers_ or [])

    def ask(q):
        asked.append(q)
        return queue.pop(0) if queue else ""
    return ask, asked


def test_the_preference_and_its_question():
    pref = preferences.by_id(PID)
    assert pref["agents"] == ["codex"]
    assert pref["default"] == "ask"
    assert [(o["value"], o["label"]) for o in pref["options"]] == [("ask", "ask each time"),
                                                                    ("approve", "approve automatically")]
    assert "serena_repl" in pref["question"] and "runs code" in pref["question"]
    assert pref["target"] == {"loadout": "codex.serena_approval"}
    assert paths.personal_loadout_json() == paths.personal_root() / "loadout.json"


def test_round_trip_keeps_unknown_keys(fake_home, codex_on):
    _file().parent.mkdir(parents=True)
    _file().write_text(json.dumps({"other": 1, "codex": {"later": [2]}}), encoding="utf-8")
    bk = backup.Backup(description="t")
    out = preferences.set_choice(PID, "approve", bk=bk)
    assert out == [f"{PID}: approve"]
    assert json.loads(_file().read_text(encoding="utf-8")) == {
        "other": 1, "codex": {"later": [2], "serena_approval": "approve"}}
    assert not bk.empty, "the old file is backed up"
    st = preferences.detect()[PID]
    assert st.value == "approve" and "loadout.json" in st.source
    assert preferences.set_choice(PID, "approve") == [f"{PID}: already approve"]
    preferences.set_choice(PID, "ask")
    assert json.loads(_file().read_text(encoding="utf-8"))["codex"]["serena_approval"] == "ask"


def test_missing_file_is_unset_and_a_write_creates_it(fake_home, codex_on):
    assert not preferences.detect()[PID].is_set
    bk = backup.Backup(description="t")
    preferences.set_choice(PID, "approve", bk=bk)
    assert json.loads(_file().read_text(encoding="utf-8")) == {"codex": {"serena_approval": "approve"}}
    assert not bk.empty, "a created file is recorded, so restore removes it"


def test_broken_file_reads_unset_and_a_write_refuses(fake_home, codex_on):
    _file().parent.mkdir(parents=True)
    _file().write_text("{not json", encoding="utf-8")
    assert not preferences.detect()[PID].is_set  # a session start must not fail on it
    with pytest.raises(ValueError, match="loadout.json"):
        preferences.set_choice(PID, "approve")
    assert _file().read_text(encoding="utf-8") == "{not json"


def test_broken_file_refuses_before_me_md_is_written(fake_home, codex_on):
    _file().parent.mkdir(parents=True)
    _file().write_text("[]", encoding="utf-8")
    ask, _ = _asker()
    given = {PID: ("approve", ""), "answer_style": ("detailed", "")}
    with pytest.raises(ValueError, match="loadout.json"):
        preferences.ask_all(ask, fill_defaults=False, interactive=False, given=given)
    assert not (paths.personal_root() / "rules" / "me.md").exists()


def test_codex_off_is_not_asked_in_configure_prefs(fake_home, codex_off):
    ask, asked = _asker()
    preferences.ask_all(ask, fill_defaults=True, interactive=True)
    assert not any(q.startswith(PID) for q in asked)
    assert not _file().exists()
    assert not any(PID in line for line in preferences.show_lines())


def test_codex_on_is_asked_in_configure_prefs(fake_home, codex_on):
    ask, asked = _asker()
    preferences.ask_all(ask, fill_defaults=False, interactive=True)
    assert any(q.startswith(PID) for q in asked)
    assert any(PID in line for line in preferences.show_lines())


def test_codex_off_quick_defaults_do_not_show_it(fake_home, codex_off, capsys):
    configure._quick_defaults(lambda q: "")
    assert PID not in capsys.readouterr().out


def test_codex_on_quick_defaults_show_it(fake_home, codex_on, capsys):
    configure._quick_defaults(lambda q: "")
    assert PID in capsys.readouterr().out


def test_codex_off_answers_file_is_not_applied(tmp_path, fake_home, codex_off):
    f = tmp_path / "answers.json"
    f.write_text(json.dumps({"preferences": {PID: "approve"}}), encoding="utf-8")
    given = answers.load(f).prefs
    assert given == {PID: ("approve", "")}
    preferences.ask_all(lambda q: "", fill_defaults=True, interactive=False, given=given)
    assert not _file().exists()


def test_codex_on_answers_file_is_applied(tmp_path, fake_home, codex_on):
    f = tmp_path / "answers.json"
    f.write_text(json.dumps({"preferences": {PID: "approve"}}), encoding="utf-8")
    preferences.ask_all(lambda q: "", fill_defaults=True, interactive=False, given=answers.load(f).prefs)
    assert json.loads(_file().read_text(encoding="utf-8")) == {"codex": {"serena_approval": "approve"}}


def test_bootstrap_starter_with_codex_off_does_not_ask(fake_home, fake_runner, codex_off):
    ask, asked = _asker(["", "Max", "Student", "Python", "", "n"])  # n: walk through each preference
    bootstrap.ensure_personal(ask, interactive=True)
    assert any(q.startswith("answer_language") for q in asked)
    assert not any(q.startswith(PID) for q in asked)
    assert not _file().exists()


def test_bootstrap_starter_with_codex_on_asks(fake_home, fake_runner, codex_on):
    ask, asked = _asker(["", "Max", "Student", "Python", "", "n"])
    bootstrap.ensure_personal(ask, interactive=True)
    assert any(q.startswith(PID) for q in asked)


@pytest.mark.parametrize("nested", ['{"codex": "x"}', '{"codex": []}'])
def test_nested_non_object_is_refused_before_anything_is_written(fake_home, codex_on, nested):
    _file().parent.mkdir(parents=True)
    _file().write_text(nested, encoding="utf-8")
    assert not preferences.detect()[PID].is_set
    given = {PID: ("approve", ""), "answer_style": ("detailed", ""), "effort_level": ("high", "")}
    with pytest.raises(ValueError, match="loadout.json"):
        preferences.ask_all(lambda q: "", fill_defaults=False, interactive=False, given=given)
    assert not (paths.personal_root() / "rules" / "me.md").exists()
    assert not (paths.personal_root() / "settings.json").exists()
    assert _file().read_text(encoding="utf-8") == nested
