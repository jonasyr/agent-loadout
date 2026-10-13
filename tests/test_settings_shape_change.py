"""The settings merge survives a key whose shape changes between kit versions."""
import json

import pytest

from loadout import paths, settings_merge as sm


def _run(monkeypatch, current, previous, desired):
    (paths.claude_home()).mkdir(parents=True, exist_ok=True)
    paths.state_dir().mkdir(parents=True, exist_ok=True)
    sm._target().write_text(json.dumps(current))
    sm._snapshot().write_text(json.dumps(previous))
    monkeypatch.setattr(sm, "desired_settings", lambda: desired)
    sm.apply_settings()
    after = json.loads(sm._target().read_text())
    sm.apply_settings()  # idempotent and still no exception
    assert json.loads(sm._target().read_text()) == after
    return after


@pytest.mark.parametrize("new", ["x", ["a"], 3, None])
def test_object_becomes_non_object(fake_home, monkeypatch, new):
    old = {"env": {"A": "1"}, "permissions": {"allow": ["Read"], "deny": ["Bash"]}}
    cur = {**old, "mine": 1}
    after = _run(monkeypatch, cur, old, {"env": new, "permissions": ["p"]})
    assert after["env"] == new
    assert after["permissions"] == ["p"]
    assert after["mine"] == 1


def test_nested_object_becomes_scalar(fake_home, monkeypatch):
    old = {"a": {"b": {"c": 1}}}
    after = _run(monkeypatch, {"a": {"b": {"c": 1}, "own": 2}, "mine": 1}, old, {"a": {"b": "x"}})
    assert after["a"]["b"] == "x"
    assert after["a"]["own"] == 2 and after["mine"] == 1


def test_scalar_becomes_object(fake_home, monkeypatch):
    after = _run(monkeypatch, {"env": "x", "mine": 1}, {"env": "x"}, {"env": {"A": "1"}})
    assert after == {"env": {"A": "1"}, "mine": 1}


def test_list_becomes_object(fake_home, monkeypatch):
    after = _run(monkeypatch, {"permissions": ["p"], "mine": 1}, {"permissions": ["p"]},
                 {"permissions": {"allow": ["Read"]}})
    assert after == {"permissions": {"allow": ["Read"]}, "mine": 1}


def test_user_scalar_where_kit_wants_nested_key(fake_home, monkeypatch):
    # the user turned the object into a scalar; the kit still wants a key inside it
    after = _run(monkeypatch, {"env": "mine"}, {"env": {"A": "1"}}, {"env": {"A": "1"}})
    assert after["env"] == {"A": "1"}


def test_prune_through_user_scalar(fake_home, monkeypatch):
    # the kit applied env.A, the user replaced env by a scalar, the kit dropped env.A
    after = _run(monkeypatch, {"env": "mine"}, {"env": {"A": "1"}}, {})
    assert after == {"env": "mine"}
