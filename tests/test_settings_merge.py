import json

import pytest

from loadout import jsonio, settings_merge as sm


def test_adds_desired_keys_and_keeps_user_keys():
    current = {"model": "opus", "enabledPlugins": {"mine@x": True}}
    desired = {"enabledPlugins": {"loadout@agent-loadout": True}}
    out = sm.merge_settings(current, desired, {})
    assert out == {"model": "opus", "enabledPlugins": {"mine@x": True, "loadout@agent-loadout": True}}


def test_removes_value_the_kit_dropped_when_unchanged_by_user():
    previous = {"enabledPlugins": {"old@m": True, "keep@m": True}}
    current = {"enabledPlugins": {"old@m": True, "keep@m": True}}
    desired = {"enabledPlugins": {"keep@m": True}}
    assert sm.merge_settings(current, desired, previous) == {"enabledPlugins": {"keep@m": True}}


def test_keeps_value_the_kit_dropped_when_user_changed_it():
    previous = {"effortLevel": "medium"}
    current = {"effortLevel": "high"}
    assert sm.merge_settings(current, {}, previous) == {"effortLevel": "high"}


def test_prunes_empty_parents_after_removal():
    previous = {"a": {"b": {"c": 1}}}
    assert sm.merge_settings({"a": {"b": {"c": 1}}}, {}, previous) == {}


def test_list_items_dropped_by_kit_are_removed_user_items_kept():
    previous = {"permissions": {"allow": ["Bash(a:*)", "Bash(b:*)"]}}
    current = {"permissions": {"allow": ["Bash(a:*)", "Bash(b:*)", "Bash(user:*)"]}}
    desired = {"permissions": {"allow": ["Bash(a:*)"]}}
    out = sm.merge_settings(current, desired, previous)
    assert out == {"permissions": {"allow": ["Bash(a:*)", "Bash(user:*)"]}}


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def test_apply_settings_writes_result_and_snapshot(fake_home, monkeypatch, tmp_path):
    kit = tmp_path / "kit"
    _write(kit / "settings.base.json", {"enabledPlugins": {"loadout@agent-loadout": True}})
    _write(fake_home / ".config/loadout/personal/settings.json", {"effortLevel": "medium"})
    _write(fake_home / ".claude/settings.json", {"model": "opus"})
    monkeypatch.setenv("LOADOUT_ROOT", str(kit))
    before, after = sm.apply_settings()
    assert before == {"model": "opus"}
    assert after == {"model": "opus", "enabledPlugins": {"loadout@agent-loadout": True}, "effortLevel": "medium"}
    snap = jsonio.load_json(fake_home / ".claude/.loadout/managed-settings.json")
    assert snap == {"enabledPlugins": {"loadout@agent-loadout": True}, "effortLevel": "medium"}


def test_apply_settings_refuses_invalid_json_and_writes_nothing(fake_home, monkeypatch, tmp_path):
    kit = tmp_path / "kit"
    _write(kit / "settings.base.json", {"a": 1})
    monkeypatch.setenv("LOADOUT_ROOT", str(kit))
    target = fake_home / ".claude/settings.json"
    target.parent.mkdir(parents=True)
    target.write_text("{ broken")
    with pytest.raises(jsonio.InvalidJSON):
        sm.apply_settings()
    assert target.read_text() == "{ broken"
    assert not (fake_home / ".claude/.loadout/managed-settings.json").exists()


def test_drift_lists_paths_differing_from_desired(fake_home, monkeypatch, tmp_path):
    kit = tmp_path / "kit"
    _write(kit / "settings.base.json", {"enabledPlugins": {"a@m": True, "b@m": True}, "permissions": {"allow": ["X"]}})
    _write(fake_home / ".claude/settings.json", {"enabledPlugins": {"a@m": True, "b@m": False}, "permissions": {"allow": ["X", "Y"]}})
    monkeypatch.setenv("LOADOUT_ROOT", str(kit))
    assert sm.drift() == ["enabledPlugins/b@m"]
