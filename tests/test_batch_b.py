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


# 2. maintenance links after a pull in every mode

def test_maintain_links_pulled_skills_and_hook_scripts_in_symlink_mode(fake_home, fake_runner, monkeypatch):
    from loadout import maintenance as m

    personal = paths.personal_root()
    (personal / ".git").mkdir(parents=True)
    (personal / "hooks").mkdir()
    (personal / "hooks/x.sh").write_text("#!/bin/sh\n")
    (personal / "skills/foo").mkdir(parents=True)
    (personal / "skills/foo/SKILL.md").write_text("x")
    (personal / "settings.json").write_text(json.dumps({"hooks": {"Stop": [{"hooks": [
        {"type": "command", "command": '"$HOME/.claude/hooks/personal/x.sh"'}]}]}}))
    monkeypatch.setattr(m, "pull_if_clean", lambda root: True)
    monkeypatch.setattr(m, "find_outdated", lambda: [])
    monkeypatch.setattr(m, "notify", lambda text: None)
    m._maintain(100.0)
    assert (paths.claude_home() / "skills/foo").is_symlink()
    assert (paths.claude_home() / "hooks/personal").is_symlink()
    assert (paths.claude_home() / "hooks/personal/x.sh").exists()


# 3. a recorded hook must not run twice when the user already has it in a group with others

def _second_machine(extra=True):
    s = _settings()
    if extra:
        s["hooks"]["PreToolUse"][3]["hooks"].append({"type": "command", "command": "other"})
    (paths.claude_home() / "settings.json").write_text(json.dumps(s))
    p = paths.personal_root() / "settings.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [
        {"type": "command", "command": "my-own-linter"}]}]}}))
    return p


def _cmds():
    return [h["command"] for g in _settings()["hooks"]["PreToolUse"] for h in g["hooks"]]


def test_second_machine_hook_runs_twice(machine):
    _second_machine()
    settings_merge.apply_settings()
    assert _cmds().count("my-own-linter") == 1, _cmds()


@pytest.mark.parametrize("extra", [True, False])
def test_removing_the_hook_from_the_personal_layer_keeps_the_users_own_copy(machine, extra):
    p = _second_machine(extra)
    settings_merge.apply_settings()
    p.write_text("{}")
    settings_merge.apply_settings()
    assert _cmds().count("my-own-linter") == 1, _cmds()


def test_a_hook_the_kit_applied_is_still_removed_with_the_personal_layer(machine):
    p = paths.personal_root() / "settings.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "kit-added"}]}]}}))
    settings_merge.apply_settings()
    settings_merge.apply_settings()  # a second run must keep it recorded
    assert "kit-added" in json.dumps(_settings())
    p.write_text("{}")
    settings_merge.apply_settings()
    assert "kit-added" not in json.dumps(_settings())


def test_no_drift_for_a_hook_the_user_already_has_in_a_group(machine):
    _second_machine()
    settings_merge.apply_settings()
    assert not any(d.startswith("hooks") for d in settings_merge.drift())


# 4. personal-profile membership only counts for an item that is inactive globally

def test_kit_named_profile_seed_hides_scope_down(machine):
    before = _get("plugin", "sonarqube@claude-plugins-official")
    v = _get("mcp", "omarchy-kb")
    adopt.apply_own([(v, own.Choice("project", "sonar"))], backup.Backup())
    after = _get("plugin", "sonarqube@claude-plugins-official")
    assert after.action == before.action == "scope-down", (before.action, after.action, after.reason)


def _profile(name, data):
    p = paths.personal_root() / "profiles" / f"{name}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data))


def test_profile_member_plugin_is_kept_only_when_disabled_globally(machine):
    _profile("mine", {"install": ["mystery@somewhere"]})
    assert _get("plugin", "mystery@somewhere").action == "own"  # installed and not disabled: still active
    s = _settings()
    s["enabledPlugins"] = {"mystery@somewhere": False}
    (paths.claude_home() / "settings.json").write_text(json.dumps(s))
    v = _get("plugin", "mystery@somewhere")
    assert v.action == "keep" and "personal profile mine" in v.reason


def test_profile_member_mcp_server_still_in_user_scope_is_not_kept(machine):
    _profile("mine", {"mcp": {"mcpServers": {"omarchy-kb": {"command": "x"}}}})
    assert _get("mcp", "omarchy-kb").action == "own"


def test_profile_member_skill_and_hook_still_present_are_not_kept(machine):
    _profile("mine", {"skills": ["my-skill"], "settings": {"hooks": {"PreToolUse": [
        {"matcher": "Edit", "hooks": [{"type": "command", "command": "my-own-linter"}]}]}}})
    assert _get("skill", "my-skill").action == "own"
    assert _get("hook", "PreToolUse:Edit").action == "own"


def test_personal_layer_global_membership_still_keeps(machine):
    p = paths.personal_root() / "settings.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [
        {"type": "command", "command": "my-own-linter"}]}]}}))
    assert _get("hook", "PreToolUse:Edit").action == "keep"


def test_hook_with_a_list_command_does_not_crash(machine):
    s = _settings()
    s["hooks"]["Stop"].append({"hooks": [{"type": "command", "command": ["a", "b"]}, {"type": "command", "command": 5}]})
    (paths.claude_home() / "settings.json").write_text(json.dumps(s))
    _profile("mine", {"settings": {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": ["a"]}]}]}}})
    hooks = [v for v in _verdicts() if v.item.kind == "hook" and not isinstance(v.item.detail, str)]
    assert len(hooks) == 2 and all(v.action == "own" for v in hooks)
    assert own.candidate_repos(hooks[0].item) == []


# 5. a hook name shared by several hooks needs a #n qualifier

def _two_edit_hooks():
    p = paths.claude_home() / "settings.json"
    s = json.loads(p.read_text())
    s["hooks"]["PreToolUse"][3]["hooks"].append({"type": "command", "command": "keep-me"})
    p.write_text(json.dumps(s))
    return _verdicts()


def test_one_hook_name_hits_all_hooks_of_matcher(machine):
    vs = _two_edit_hooks()
    with pytest.raises(ValueError) as exc:
        own.resolve(own.parse_spec("PreToolUse:Edit=remove"), vs)
    assert "PreToolUse:Edit#1" in str(exc.value) and "PreToolUse:Edit#2" in str(exc.value)


def test_hook_qualifier_picks_one_hook(machine):
    vs = _two_edit_hooks()
    pairs = own.resolve(own.parse_spec("PreToolUse:Edit#2=remove"), vs)
    assert [v.item.detail for v, _ in pairs] == ["keep-me"]
    pairs = own.resolve(own.parse_spec("hook:PreToolUse:Edit#1=leave"), vs)
    assert [v.item.detail for v, _ in pairs] == ["my-own-linter"]
    with pytest.raises(ValueError):
        own.resolve(own.parse_spec("PreToolUse:Edit#3=remove"), vs)


def test_unshared_hook_name_still_needs_no_qualifier(machine):
    pairs = own.resolve(own.parse_spec("PreToolUse:Edit=remove"), _verdicts())
    assert [v.item.detail for v, _ in pairs] == ["my-own-linter"]


def test_configure_own_lists_numbered_names_for_shared_hooks(machine):
    from loadout import configure
    _two_edit_hooks()
    text = "\n".join(configure.own_lines(False))
    assert "PreToolUse:Edit#1" in text and "PreToolUse:Edit#2" in text
