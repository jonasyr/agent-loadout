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


def test_a_file_that_is_not_json_is_refused(tmp_path, fake_home):
    with pytest.raises(ValueError, match="answers.json"):
        answers.load(_file(tmp_path, "{not json"))


def test_a_missing_file_is_refused(tmp_path, fake_home):
    with pytest.raises(ValueError, match="cannot read"):
        answers.load(tmp_path / "nope.json")
