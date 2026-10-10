"""Fix batch B (correctness and data safety) for the adopt/own tools."""
import json

import pytest

from loadout import adopt, backup, bootstrap as b, inventory, own, paths, settings_merge
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


# 1. restore time bomb: the managed-settings snapshot is backed up too

def test_restore_hook_global_then_later_merge_keeps_users_hook(machine):
    v = _get("hook", "PreToolUse:Edit")
    assert v.action == "own"
    bk = backup.Backup()
    adopt.apply_own([(v, own.Choice("global"))], bk)
    backup.restore(bk.root)
    assert "my-own-linter" in json.dumps(_settings()["hooks"])
    settings_merge.apply_settings()
    assert "my-own-linter" in json.dumps(_settings().get("hooks", {})), "user's hook deleted after restore"


def test_restore_plugin_global_then_later_merge_keeps_plugin_enabled(machine):
    home = machine
    ip = json.loads((home / ".claude/plugins/installed_plugins.json").read_text())
    ip["plugins"]["mine@severity1-marketplace"] = [{"scope": "user", "version": "1"}]
    (home / ".claude/plugins/installed_plugins.json").write_text(json.dumps(ip))
    s = _settings()
    s["enabledPlugins"] = {"mine@severity1-marketplace": True}
    (home / ".claude/settings.json").write_text(json.dumps(s))
    v = _get("plugin", "mine@severity1-marketplace")
    assert v.action == "own", v
    bk = backup.Backup()
    adopt.apply_own([(v, own.Choice("global"))], bk)
    backup.restore(bk.root)
    assert _settings()["enabledPlugins"] == {"mine@severity1-marketplace": True}
    settings_merge.apply_settings()
    assert _settings().get("enabledPlugins", {}).get("mine@severity1-marketplace") is True


def test_bootstrap_backs_up_the_settings_snapshot(fake_home, fake_runner):
    (fake_home / ".claude").mkdir()
    (fake_home / ".claude/settings.json").write_text('{"theme": "dark"}\n')
    b.bootstrap(False, True, False, False, lambda q: "x")
    snap = paths.state_dir() / "managed-settings.json"
    assert snap.exists()
    steps = [s for m in paths.backups_root().rglob("manifest.json") for s in json.loads(m.read_text())["steps"]]
    assert any(str(snap) in json.dumps(s["undo"]) for s in steps), steps
