"""Repo JSON is rewritten only in the exact layout it already has (spec Part 0)."""
import json

import pytest

from loadout.jsonio import dumps_like, json_style


@pytest.mark.parametrize("indent", [2, 4, "\t"])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_a_standard_layout_round_trips(indent, newline):
    data = {"b": 1, "a": {"x": [1, 2]}, "s": "ü"}
    text = (json.dumps(data, indent=indent, ensure_ascii=False) + "\n").replace("\n", newline)
    style = json_style(text)
    assert style is not None and dumps_like(style, json.loads(text)) == text


def test_style_detects_ensure_ascii():
    text = json.dumps({"a": "\u00e9"}, indent=4) + "\n"
    assert "\\u00e9" in text
    style = json_style(text)
    assert style is not None and style.ensure_ascii and dumps_like(style, json.loads(text)) == text


def test_new_keys_keep_the_style():
    text = '{\r\n    "a": 1\r\n}\r\n'
    style = json_style(text)
    assert dumps_like(style, {"a": 1, "b": [True]}) == '{\r\n    "a": 1,\r\n    "b": [\r\n        true\r\n    ]\r\n}\r\n'


def test_no_final_newline_is_kept():
    assert dumps_like(json_style('{\n  "a": 1\n}'), {"a": 2}) == '{\n  "a": 2\n}'


@pytest.mark.parametrize("text", [
    '{"a":[1,2]}\n',                   # compact without spaces (json.dumps' one-line default is kept)
    '{\n  "a": 1, "b": 2\n}\n',        # hand layout
    '{\n  // note\n  "a": 1\n}\n',     # comments (JSONC)
    '{\n  "a": 1\r\n}\n',              # mixed line endings
    'not json',
])
def test_any_other_layout_is_not_rewritten(text):
    assert json_style(text) is None


def test_an_empty_file_has_no_style():
    assert json_style("") is None
