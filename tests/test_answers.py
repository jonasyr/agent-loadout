"""--answers FILE: the starter layer's answers, validated before bootstrap changes anything (spec PR C)."""
import json

import pytest

from loadout import answers


def _file(tmp_path, data):
    p = tmp_path / "answers.json"
    p.write_text(json.dumps(data) if not isinstance(data, str) else data, encoding="utf-8")
    return p


def test_a_full_file_loads(tmp_path, fake_home):
    a = answers.load(_file(tmp_path, {
        "about": {"name": "Jonas", "role": "student", "languages": "Python", "preferences": "short"},
        "preferences": {"answer_language": "other:French", "commit_style": "conventional"}}))
    assert a.about == {"name": "Jonas", "role": "student", "languages": "Python", "preferences": "short"}
    assert a.prefs == {"answer_language": ("other", "French"), "commit_style": ("conventional", "")}


def test_an_empty_object_is_no_answers(tmp_path, fake_home):
    a = answers.load(_file(tmp_path, {}))
    assert a.about == {} and a.prefs == {}


@pytest.mark.parametrize("data, word", [
    ({"abuot": {}}, "abuot"),
    ({"about": {"nmae": "x"}}, "nmae"),
    ({"preferences": {"no_such_pref": "x"}}, "no_such_pref"),
    ({"preferences": {"answer_language": "klingon"}}, "answer_language"),
    ({"preferences": {"answer_language": "other"}}, "answer_language"),
    ({"preferences": {"commit_style": 1}}, "commit_style"),
    ({"about": {"name": 3}}, "name"),
    ({"about": []}, "about"),
    ({"preferences": {"automode_trust": "generate"}}, "automode_trust"),
    ([], "object"),
])
def test_bad_answers_are_refused_with_the_key(tmp_path, fake_home, data, word):
    with pytest.raises(ValueError, match=word):
        answers.load(_file(tmp_path, data))


_TOKEN = "ghp" + "_" + "a1b2c3d4e5" * 4  # built at runtime, so no scanner sees a token here


@pytest.mark.parametrize("data, word", [
    ({"about": {"preferences": "my GitHub token is " + _TOKEN}}, "about.preferences"),
    ({"about": {"name": "password=" + "hunter2hunter2"}}, "about.name"),
    ({"about": {"role": "dev " + "Zq8xLp2Vt9" * 5}}, "about.role"),
    ({"preferences": {"answer_language": "other:" + _TOKEN}}, "preferences.answer_language"),
])
def test_a_secret_in_an_answer_is_refused(tmp_path, fake_home, capsys, data, word):
    with pytest.raises(ValueError) as exc:
        answers.load(_file(tmp_path, data))
    msg = str(exc.value)
    assert word in msg and "secret" in msg and "secrets.env" in msg
    assert _TOKEN not in msg and "hunter2" not in msg and _TOKEN not in capsys.readouterr().out


def test_plain_prose_answers_are_not_secrets(tmp_path, fake_home):
    a = answers.load(_file(tmp_path, {"about": {
        "preferences": "short answers; ask before deleting tokens or keys; I use an API key from secrets.env",
        "languages": "Python, TypeScript, Rust, Kotlin"}}))
    assert a.about["languages"].startswith("Python")


def test_a_file_that_is_not_json_is_refused(tmp_path, fake_home):
    with pytest.raises(ValueError, match="answers.json"):
        answers.load(_file(tmp_path, "{not json"))


def test_a_missing_file_is_refused(tmp_path, fake_home):
    with pytest.raises(ValueError, match="cannot read"):
        answers.load(tmp_path / "nope.json")


from loadout import backup, configure, paths, preferences


def test_given_about_answers_are_written_without_asking(fake_home):
    paths.personal_root().mkdir(parents=True)
    configure._about_you(lambda q: pytest.fail(f"asked: {q}"), backup.Backup(description="t"),
                         given={"name": "Jonas", "role": "student", "languages": "Python", "preferences": "short"})
    text = (paths.personal_root() / "rules" / "me.md").read_text()
    assert "Jonas" in text and "student" in text and "Python" in text


def test_missing_about_answers_take_defaults_without_asking_when_told(fake_home):
    paths.personal_root().mkdir(parents=True)
    configure._about_you(lambda q: pytest.fail(f"asked: {q}"), backup.Backup(description="t"),
                         given={"name": "Jonas"}, ask_missing=False)
    assert "Jonas" in (paths.personal_root() / "rules" / "me.md").read_text()


def test_missing_about_answers_are_asked_in_a_terminal(fake_home):
    paths.personal_root().mkdir(parents=True)
    asked = []
    configure._about_you(lambda q: asked.append(q) or "", backup.Backup(description="t"), given={"name": "Jonas"})
    assert len(asked) == 3 and not any("name" in q.lower() for q in asked)


def test_given_preferences_win_over_defaults_without_a_terminal(fake_home):
    paths.personal_root().mkdir(parents=True)
    (paths.personal_root() / "settings.json").write_text("{}\n")
    configure._about_you(lambda q: "", backup.Backup(description="t"), ask_missing=False)
    preferences.ask_all(lambda q: pytest.fail(q), fill_defaults=True, interactive=False,
                        bk=backup.Backup(description="t"), given={"answer_language": ("german", "")})
    assert "always answer in German" in (paths.personal_root() / "rules" / "me.md").read_text()


def test_given_preferences_are_not_asked_in_a_terminal(fake_home):
    paths.personal_root().mkdir(parents=True)
    (paths.personal_root() / "settings.json").write_text("{}\n")
    configure._about_you(lambda q: "", backup.Backup(description="t"), ask_missing=False)
    asked = []
    preferences.ask_all(lambda q: asked.append(q) or "", fill_defaults=True, interactive=True,
                        bk=backup.Backup(description="t"), given={"answer_language": ("german", "")})
    assert asked and not any(q.startswith("answer_language") for q in asked)


def test_the_one_screen_summary_shows_the_given_answers(fake_home, capsys):
    paths.personal_root().mkdir(parents=True)
    (paths.personal_root() / "settings.json").write_text("{}\n")
    configure._about_you(lambda q: "", backup.Backup(description="t"), ask_missing=False)
    configure.ask_preferences(lambda q: "", fill_defaults=True, interactive=True, bk=backup.Backup(description="t"),
                              quick=True, given={"answer_language": ("german", "")})
    import re
    assert re.search(r"answer_language\s+german", capsys.readouterr().out.split("Working preferences")[1])
