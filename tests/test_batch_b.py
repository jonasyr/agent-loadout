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


# 7. configure set own exits non-zero when nothing was recorded

def test_set_own_exits_1_when_the_record_is_skipped(machine, capsys):
    from loadout import configure
    assert configure.set_own("mystery@somewhere", "global") == 1  # marketplace source unknown: skipped
    assert "skipped:" in capsys.readouterr().out


def test_set_own_exits_0_when_recorded(machine):
    from loadout import configure
    assert configure.set_own("my-skill", "leave") == 0


# 8. repo offer

def _repo_with_local_settings_only(machine):
    repo = machine / "code/localonly"
    (repo / ".claude").mkdir(parents=True)
    (repo / ".claude/settings.local.json").write_text(json.dumps({"x": "omarchy-kb"}))
    return repo


def _known_repos(machine, *repos):
    cfg = json.loads((machine / ".claude.json").read_text())
    cfg["projects"] = {str(r): {} for r in repos}
    (machine / ".claude.json").write_text(json.dumps(cfg))


def _offer(machine, monkeypatch, answers):
    from loadout import project
    applied, asked = [], []
    monkeypatch.setattr(project, "add_profile", lambda repo, name: applied.append((repo, name)))
    it = iter(answers)

    def ask(q):
        asked.append(q)
        return next(it)

    item = _get("mcp", "omarchy-kb").item
    adopt._offer_profiles({"mine": [item]}, ask)
    return applied, asked


def test_settings_local_json_is_not_evidence(machine):
    repo = _repo_with_local_settings_only(machine)
    _known_repos(machine, repo)
    assert own.candidate_repos(_get("mcp", "omarchy-kb").item) == []


def test_repo_offer_y_means_the_detected_repos(machine, monkeypatch, capsys):
    repo = machine / "code/app"
    repo.mkdir(parents=True)
    (repo / ".mcp.json").write_text(json.dumps({"mcpServers": {"omarchy-kb": {}}}))
    _known_repos(machine, repo)
    applied, asked = _offer(machine, monkeypatch, ["y"])
    assert asked == ["  apply to these repos? [y/N/paths]: "]
    assert [r for r, _ in applied] == [repo]
    out = capsys.readouterr().out
    assert out.count("is not undone by loadout restore") == 1
    assert "(applying writes the repo's committed .claude/settings.json / .mcp.json and is not undone by loadout restore)" in out


@pytest.mark.parametrize("answer", ["", "n", "N"])
def test_repo_offer_enter_or_n_means_none(machine, monkeypatch, answer):
    repo = machine / "code/app"
    repo.mkdir(parents=True)
    (repo / ".mcp.json").write_text(json.dumps({"mcpServers": {"omarchy-kb": {}}}))
    _known_repos(machine, repo)
    applied, _ = _offer(machine, monkeypatch, [answer])
    assert applied == []


def test_repo_offer_anything_else_is_paths(machine, monkeypatch):
    a, c = machine / "code/a", machine / "code/c"
    a.mkdir(parents=True)
    c.mkdir(parents=True)
    repo = machine / "code/app"
    repo.mkdir()
    (repo / ".mcp.json").write_text(json.dumps({"mcpServers": {"omarchy-kb": {}}}))
    _known_repos(machine, repo)
    applied, _ = _offer(machine, monkeypatch, [f"{a}, {c}"])
    assert [r for r, _ in applied] == [a, c]


def test_repo_offer_without_detected_repos_asks_for_paths(machine, monkeypatch):
    _known_repos(machine)
    applied, asked = _offer(machine, monkeypatch, [""])
    assert asked == ["  repos (comma-separated paths; Enter: none): "]
    assert applied == []


# 9. minor fixes

def test_a_failing_removal_does_not_skip_the_machine_steps(machine, monkeypatch):
    pairs = [(_get("hook", "PreToolUse:Edit"), own.Choice("global")), (_get("skill", "my-skill"), own.Choice("remove"))]

    def boom(*a, **k):
        raise OSError("boom")

    monkeypatch.setattr(adopt, "apply", boom)
    out, _ = adopt.apply_own(pairs, backup.Backup())
    assert any("failed: boom" in line for line in out), out
    assert (paths.state_dir() / "managed-settings.json").exists()  # apply_settings still ran
    assert "my-own-linter" in (paths.personal_root() / "settings.json").read_text()


def _decision_steps(bk):
    return [s for s in bk.steps if "own-decisions.json" in json.dumps(s)]


def test_remove_without_a_prior_decision_adds_no_decisions_backup_step(machine):
    bk = backup.Backup()
    adopt.apply_own([(_get("skill", "my-skill"), own.Choice("remove"))], bk)
    assert _decision_steps(bk) == []


def test_remove_with_a_prior_decision_backs_the_decisions_file_up(machine):
    own.remember_leave(_get("skill", "my-skill").item)
    v = next(x for x in inventory.classify(inventory.collect(with_versions=False)) if x.item.name == "my-skill")
    bk = backup.Backup()
    adopt.apply_own([(v, own.Choice("remove"))], bk)
    assert len(_decision_steps(bk)) == 1
    assert own.decisions() == {}


def test_no_backup_line_when_nothing_was_recorded(machine, capsys):
    from loadout import configure
    configure.set_own("mystery@somewhere", "global")  # skipped
    assert "backup:" not in capsys.readouterr().out


def test_set_own_prints_the_kit_profile_note(machine, capsys):
    from loadout import configure
    assert (paths.kit_root() / "profiles/sonar.json").exists()
    configure.set_own("omarchy-kb", "project:sonar")
    assert "is a kit profile" in capsys.readouterr().out


def test_adopt_own_spec_prints_the_kit_profile_note(machine, capsys):
    adopt.run(True, None, set(), False, lambda q: "", with_versions=False, interactive=False, own_spec="omarchy-kb=project:sonar")
    assert "is a kit profile" in capsys.readouterr().out


def _dup_mcp(machine):
    for f in (machine / ".claude.json", machine / ".claude/.mcp.json"):
        d = json.loads(f.read_text())
        d["mcpServers"]["dupsrv"] = {"command": "dup"}
        f.write_text(json.dumps(d))


def _dups():
    return {v.item.location: v for v in _verdicts() if v.item.kind == "mcp" and v.item.name == "dupsrv"}


def test_mcp_decision_key_includes_the_location_of_a_claude_mcp_json_server(machine):
    _dup_mcp(machine)
    d = _dups()
    assert len(d) == 2 and all(v.action == "own" for v in d.values())
    user, local = d["~/.claude.json"], d["~/.claude/.mcp.json"]
    assert own.decision_key(user.item) == "mcp:dupsrv"
    assert own.decision_key(local.item) == "mcp:.mcp.json:dupsrv"
    own.remember_leave(local.item)
    d = _dups()
    assert d["~/.claude/.mcp.json"].action == "keep" and d["~/.claude.json"].action == "own"


def test_old_mcp_decision_key_is_still_read(machine):
    _dup_mcp(machine)
    own._decisions_path().parent.mkdir(parents=True, exist_ok=True)
    own._decisions_path().write_text(json.dumps({"mcp:dupsrv": "leave"}))
    assert {v.action for v in _dups().values()} == {"keep"}
