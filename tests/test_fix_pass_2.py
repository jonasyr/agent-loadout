"""Fix pass 2 for the adopt/own tools (regressions found by the re-review)."""
import json

import pytest

from loadout import adopt, backup, inventory, own, paths, settings_merge as sm
from fixtures import author_machine


@pytest.fixture
def machine(fake_home, fake_runner):
    author_machine(fake_home)
    return fake_home


def _verdicts():
    return inventory.classify(inventory.collect(with_versions=False))


def _get(kind, name):
    return next(v for v in _verdicts() if v.item.kind == kind and v.item.name == name)


def _settings():
    return json.loads((paths.claude_home() / "settings.json").read_text())


# 1. hook groups: three-way merge keyed by event + matcher + command set

H = {"type": "command", "command": "echo hi"}


def test_changed_field_of_an_applied_group_is_updated_in_place():
    old = {"matcher": "Bash", "hooks": [H]}
    new = {"matcher": "Bash", "hooks": [{**H, "timeout": 10}]}
    other = {"matcher": "Read", "hooks": [{"type": "command", "command": "x"}]}
    current = {"hooks": {"PreToolUse": [old, other]}}
    prev = {"hooks": {"PreToolUse": [old]}}
    desired = {"hooks": {"PreToolUse": [new]}}
    out = sm.merge_settings(current, desired, prev)
    assert out == {"hooks": {"PreToolUse": [new, other]}}
    snap = sm.effective_desired(current, desired, prev)
    assert snap == desired
    assert sm.merge_settings(out, desired, snap) == out


def test_user_copy_never_applied_is_skipped_and_survives_removal():
    mine = {"matcher": "Bash", "hooks": [H]}
    current = {"hooks": {"PreToolUse": [mine]}}
    desired = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{**H, "timeout": 3}]}]}}
    out = sm.merge_settings(current, desired, {})
    assert out == current
    snap = sm.effective_desired(current, desired, {})
    assert "hooks" not in snap
    assert sm.merge_settings(out, {}, snap) == current


def test_applied_group_no_longer_desired_removed_only_if_unchanged():
    g = {"matcher": "Bash", "hooks": [H]}
    assert sm.merge_settings({"hooks": {"Stop": [g]}}, {}, {"hooks": {"Stop": [g]}}) == {}
    edited = {"matcher": "Bash", "hooks": [{**H, "timeout": 9}]}
    assert sm.merge_settings({"hooks": {"Stop": [edited]}}, {}, {"hooks": {"Stop": [g]}}) == {"hooks": {"Stop": [edited]}}


def test_timeout_edit_keeps_hook(machine):
    p = paths.personal_root() / "settings.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "kit-added"}]}]}}))
    sm.apply_settings()
    p.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "kit-added", "timeout": 5}]}]}}))
    sm.apply_settings()
    s = json.dumps(_settings())
    assert "kit-added" in s, "hook vanished after editing its timeout"
    assert s.count("kit-added") == 1
    assert '"timeout": 5' in s


def test_machine_a_recorded_hook_removed_with_personal_layer(machine):
    v = _get("hook", "PreToolUse:Edit")
    bk = backup.Backup()
    adopt.apply_own([(v, own.Choice("global"))], bk)
    snap = json.loads((paths.state_dir() / "managed-settings.json").read_text())
    assert "my-own-linter" in json.dumps(snap.get("hooks", {}))
    assert json.dumps(_settings()).count("my-own-linter") == 1
    (paths.personal_root() / "settings.json").write_text("{}")
    sm.apply_settings()
    assert "my-own-linter" not in json.dumps(_settings().get("hooks", {})), "recorded hook lingers on machine A"


def test_machine_a_restore_puts_snapshot_back(machine):
    snap_path = paths.state_dir() / "managed-settings.json"
    v = _get("hook", "PreToolUse:Edit")
    bk = backup.Backup()
    adopt.apply_own([(v, own.Choice("global"))], bk)
    backup.restore(bk.root)
    assert not snap_path.exists() or "my-own-linter" not in snap_path.read_text()
    assert "my-own-linter" in json.dumps(_settings()["hooks"])
