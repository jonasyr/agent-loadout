import pytest

from loadout import jsonio, paths


def test_deep_merge_nested_dicts_overlay_wins():
    base = {"a": {"x": 1, "y": 2}, "b": 1}
    overlay = {"a": {"y": 3, "z": 4}}
    assert jsonio.deep_merge(base, overlay) == {"a": {"x": 1, "y": 3, "z": 4}, "b": 1}


def test_deep_merge_lists_union_preserving_order():
    assert jsonio.deep_merge({"l": [1, 2]}, {"l": [2, 3]}) == {"l": [1, 2, 3]}


def test_deep_merge_does_not_mutate_inputs():
    base = {"a": {"x": 1}}
    jsonio.deep_merge(base, {"a": {"y": 2}})
    assert base == {"a": {"x": 1}}


def test_load_missing_and_empty_file_is_empty_dict(tmp_path):
    assert jsonio.load_json(tmp_path / "nope.json") == {}
    (tmp_path / "empty.json").write_text("  \n")
    assert jsonio.load_json(tmp_path / "empty.json") == {}


def test_load_invalid_json_raises_with_path(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{ not json")
    with pytest.raises(jsonio.InvalidJSON) as err:
        jsonio.load_json(bad)
    assert str(bad) in str(err.value)


def test_save_json_format(tmp_path):
    target = tmp_path / "sub" / "x.json"
    jsonio.save_json(target, {"ü": 1})
    assert target.read_text(encoding="utf-8") == '{\n  "ü": 1\n}\n'


def test_paths_follow_home(fake_home):
    assert paths.claude_home() == fake_home / ".claude"
    assert paths.personal_root() == fake_home / ".config" / "loadout" / "personal"
    assert paths.secrets_file() == fake_home / ".config" / "loadout" / "secrets.env"


def test_personal_root_env_override(fake_home, monkeypatch, tmp_path):
    monkeypatch.setenv("LOADOUT_PERSONAL", str(tmp_path / "p"))
    assert paths.personal_root() == tmp_path / "p"
