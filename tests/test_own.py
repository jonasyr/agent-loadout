import json

import pytest

from loadout import backup, inventory, own, paths
from fixtures import author_machine


@pytest.fixture
def machine(fake_home, fake_runner):
    author_machine(fake_home)
    return fake_home


def _verdicts():
    return inventory.classify(inventory.collect(with_versions=False))


def _by(verdicts):
    return {(v.item.kind, v.item.name): v for v in verdicts}


def _personal(name, data):
    path = paths.personal_root() / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return path


def test_own_action_replaces_unknown(machine):
    v = _by(_verdicts())
    assert v[("plugin", "mystery@somewhere")].action == "own"
    assert all(x.action != "unknown" for x in v.values())


def test_personal_layer_items_are_keep(machine):
    _personal("settings.json", {"enabledPlugins": {"mystery@somewhere": True},
                                "hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [{"type": "command", "command": "my-own-linter"}]}]}})
    cfg = json.loads((machine / ".claude.json").read_text())["mcpServers"]["omarchy-kb"]
    _personal("mcp.json", {"mcpServers": {"omarchy-kb": cfg}})
    (paths.personal_root() / "skills/my-skill").mkdir(parents=True)
    v = _by(_verdicts())
    for key in [("plugin", "mystery@somewhere"), ("mcp", "omarchy-kb"), ("skill", "my-skill"), ("hook", "PreToolUse:Edit")]:
        assert v[key].action == "keep" and v[key].reason == own.PERSONAL_REASON, key


def test_kit_plugin_reason_is_kit_not_personal(machine):
    assert _by(_verdicts())[("plugin", "superpowers@claude-plugins-official")].reason == "Enabled by the kit."


def test_personal_profile_items_are_keep(machine):
    _personal("profiles/mine.json", {"install": ["mystery@somewhere"]})
    v = _by(_verdicts())[("plugin", "mystery@somewhere")]
    assert v.action == "keep" and "mine" in v.reason


def test_left_items_are_keep_and_listed_with_all(machine):
    item = _by(_verdicts())[("skill", "my-skill")].item
    own.remember_leave(item)
    v = _by(_verdicts())
    assert v[("skill", "my-skill")].action == "keep" and v[("skill", "my-skill")].reason == own.LEFT_REASON
    assert item not in [x.item for x in own.unmanaged(_verdicts())]
    assert item in [x.item for x in own.unmanaged(_verdicts(), include_left=True)]
    own.forget(item)
    assert _by(_verdicts())[("skill", "my-skill")].action == "own"


def test_hook_decision_key_includes_command(machine):
    hook = _by(_verdicts())[("hook", "PreToolUse:Edit")].item
    assert own.decision_key(hook) == "hook:PreToolUse:Edit:my-own-linter"


def _v(kind, name):
    return _by(_verdicts())[(kind, name)]


def _run_machine(rec):
    return rec.machine() if rec.machine else []


def test_global_plugin_records_plugin_and_marketplace(machine):
    (machine / ".claude/plugins/known_marketplaces.json").write_text(json.dumps({
        "somewhere": {"source": {"source": "github", "repo": "me/somewhere"}}}))
    bk = backup.Backup()
    rec = own.record_global(_v("plugin", "mystery@somewhere"), bk)
    assert rec.ok
    data = json.loads((paths.personal_root() / "settings.json").read_text())
    assert data["enabledPlugins"]["mystery@somewhere"] is True
    assert data["extraKnownMarketplaces"]["somewhere"] == {"source": {"source": "github", "repo": "me/somewhere"}}
    assert _v("plugin", "mystery@somewhere").action == "keep"


def test_global_plugin_marketplace_collision_skips(machine):
    (machine / ".claude/plugins/known_marketplaces.json").write_text(json.dumps({
        "somewhere": {"source": {"source": "github", "repo": "me/somewhere"}}}))
    _personal("settings.json", {"extraKnownMarketplaces": {"somewhere": {"source": {"source": "github", "repo": "other/x"}}}})
    rec = own.record_global(_v("plugin", "mystery@somewhere"), backup.Backup())
    assert not rec.ok and "skipped" in rec.lines[0]
    assert "enabledPlugins" not in json.loads((paths.personal_root() / "settings.json").read_text())


def test_global_mcp_plain_server_is_recorded_and_managed(machine, fake_runner):
    from loadout import personal_mcp
    rec = own.record_global(_v("mcp", "omarchy-kb"), backup.Backup())
    assert rec.ok
    _run_machine(rec)
    cfg = json.loads((machine / ".claude.json").read_text())["mcpServers"]["omarchy-kb"]
    assert json.loads((paths.personal_root() / "mcp.json").read_text())["mcpServers"]["omarchy-kb"] == cfg
    assert json.loads((paths.state_dir() / "managed-mcp.json").read_text())["mcpServers"]["omarchy-kb"] == cfg
    fake_runner.calls.clear()
    assert personal_mcp.apply_mcp() == []           # no "skipped, not managed" and no re-add
    assert fake_runner.calls == []


def test_global_mcp_secret_goes_to_secrets_env(machine, fake_runner):
    cfg = json.loads((machine / ".claude.json").read_text())
    cfg["mcpServers"]["mine"] = {"command": "x", "env": {"API_KEY": "k" * 20}}
    (machine / ".claude.json").write_text(json.dumps(cfg))
    rec = own.record_global(_v("mcp", "mine"), backup.Backup())
    _run_machine(rec)
    recorded = (paths.personal_root() / "mcp.json").read_text()
    assert "k" * 20 not in recorded and "${MINE_API_KEY}" in recorded
    assert "MINE_API_KEY=" in paths.secrets_file().read_text()
    add = [c for c in fake_runner.calls if c[:3] == ["claude", "mcp", "add-json"]][-1]
    assert "${MINE_API_KEY}" in add[-1]


def _as_own(kind, name):
    return inventory.Verdict(_v(kind, name).item, "own", "")


def _hook(detail):
    return inventory.Verdict(next(x.item for x in _verdicts() if x.item.kind == "hook" and x.item.detail == detail), "own", "")


def test_global_mcp_unfixable_secret_blocked(machine, fake_runner):
    rec = own.record_global(_as_own("mcp", "github-server"), backup.Backup())
    assert not rec.ok and "by hand" in rec.lines[0]
    assert not (paths.personal_root() / "mcp.json").exists()


def test_global_skill_dir_restore(machine):
    (machine / ".claude/skills/my-skill/SKILL.md").write_text("mine")
    bk = backup.Backup()
    rec = own.record_global(_v("skill", "my-skill"), bk)
    _run_machine(rec)
    from loadout import link
    link.link_all(bk)
    assert (paths.personal_root() / "skills/my-skill/SKILL.md").read_text() == "mine"
    assert (machine / ".claude/skills/my-skill").is_symlink()
    backup.restore(bk.root)
    restored = machine / ".claude/skills/my-skill"
    assert not restored.is_symlink() and (restored / "SKILL.md").read_text() == "mine"


def test_global_skill_symlink_becomes_pointer(machine):
    skills = machine / ".claude/skills"
    shared = machine / "shared/omarchy"
    shared.mkdir(parents=True)
    (skills / "omarchy").symlink_to(shared)
    rec = own.record_global(_v("skill", "omarchy"), backup.Backup())
    assert rec.ok and rec.machine is None
    assert json.loads((paths.personal_root() / "skills.json").read_text()) == {"omarchy": str(shared)}


def _settings():
    return json.loads((paths.claude_home() / "settings.json").read_text())


def test_global_hook_plain_command(machine):
    rec = own.record_global(_v("hook", "PreToolUse:Edit"), backup.Backup())
    _run_machine(rec)
    groups = json.loads((paths.personal_root() / "settings.json").read_text())["hooks"]["PreToolUse"]
    assert groups == [{"matcher": "Edit", "hooks": [{"type": "command", "command": "my-own-linter"}]}]


def test_global_hook_local_script_copied_and_rewritten(machine):
    script = machine / "bin/notify.sh"
    script.parent.mkdir()
    script.write_text("#!/bin/sh\necho hi\n")
    data = _settings()
    data["hooks"]["Notification"] = [{"hooks": [{"type": "command", "command": f"bash '{script}' --loud"}]}]
    (paths.claude_home() / "settings.json").write_text(json.dumps(data))
    rec = own.record_global(_v("hook", "Notification:"), backup.Backup())
    _run_machine(rec)
    assert (paths.personal_root() / "hooks/notify.sh").read_text() == script.read_text()
    assert script.exists()   # original stays
    want = 'bash "$HOME/.claude/hooks/personal/notify.sh" --loud'
    personal = json.loads((paths.personal_root() / "settings.json").read_text())["hooks"]["Notification"]
    assert personal[0]["hooks"][0]["command"] == want
    assert _settings()["hooks"]["Notification"][0]["hooks"][0]["command"] == want


def test_global_hook_exec_form_recorded_as_is(machine):
    data = _settings()
    data["hooks"]["Stop"] = [{"hooks": [{"type": "command", "command": "x", "args": ["/opt/x"]}]}]
    (paths.claude_home() / "settings.json").write_text(json.dumps(data))
    rec = own.record_global(_hook("x"), backup.Backup())
    assert rec.ok and any("exec form" in line for line in rec.lines)


def test_global_hook_no_duplicate_after_merge(machine):
    from loadout import settings_merge
    data = _settings()
    data["hooks"]["PreToolUse"][3]["hooks"].append({"type": "command", "command": "other"})  # the Edit group
    (paths.claude_home() / "settings.json").write_text(json.dumps(data))
    rec = own.record_global(_hook("my-own-linter"), backup.Backup())
    _run_machine(rec)
    settings_merge.apply_settings()
    commands = [h["command"] for g in _settings()["hooks"]["PreToolUse"] for h in g["hooks"]]
    assert commands.count("my-own-linter") == 1


def _set_hook(machine, event, command):
    data = _settings()
    data["hooks"][event] = [{"hooks": [{"type": "command", "command": command}]}]
    (paths.claude_home() / "settings.json").write_text(json.dumps(data))


def _personal_empty():
    root = paths.personal_root()
    return not root.exists() or not any(p.is_file() for p in root.rglob("*"))


def test_global_hook_interpreter_outside_home_still_copies_script(machine):
    script = machine / "bin/run.sh"
    script.parent.mkdir()
    script.write_text("#!/bin/sh\necho hi\n")
    _set_hook(machine, "Notification", f"/bin/sh '{script}'")
    rec = own.record_global(_v("hook", "Notification:"), backup.Backup())
    _run_machine(rec)
    assert (paths.personal_root() / "hooks/run.sh").read_text() == script.read_text()
    assert not any("outside your home" in line for line in rec.lines)
    got = json.loads((paths.personal_root() / "settings.json").read_text())["hooks"]["Notification"][0]["hooks"][0]["command"]
    assert got == '/bin/sh "$HOME/.claude/hooks/personal/run.sh"'


def test_global_skill_relative_symlink_becomes_absolute_pointer(machine):
    from loadout import link
    skills = machine / ".claude/skills"
    shared = machine / ".claude/shared/rel"
    shared.mkdir(parents=True)
    (skills / "rel").symlink_to("../shared/rel")
    own.record_global(_v("skill", "rel"), backup.Backup())
    ptr = json.loads((paths.personal_root() / "skills.json").read_text())["rel"]
    assert ptr == str(shared)
    assert any(dest.name == "rel" and src == shared for src, dest in link.LINKS()) or \
        any(shared in pair for pair in link.LINKS())


def test_global_hook_gone_before_machine_step_is_not_readded(machine):
    rec = own.record_global(_v("hook", "PreToolUse:Edit"), backup.Backup())
    data = _settings()
    for g in data["hooks"]["PreToolUse"]:
        g["hooks"] = [h for h in g["hooks"] if h["command"] != "my-own-linter"]
    data["hooks"]["PreToolUse"] = [g for g in data["hooks"]["PreToolUse"] if g["hooks"]]
    (paths.claude_home() / "settings.json").write_text(json.dumps(data))
    lines = _run_machine(rec)
    assert any("left as is" in line for line in lines)
    cmds = [h["command"] for g in _settings()["hooks"]["PreToolUse"] for h in g["hooks"]]
    assert "my-own-linter" not in cmds


def test_global_hook_unrewritable_path_notes(machine):
    script = machine / "bin/odd.sh"
    script.parent.mkdir()
    script.write_text("x")
    _set_hook(machine, "Notification", str(script).replace("odd", 'od"d"'))
    rec = own.record_global(_v("hook", "Notification:"), backup.Backup())
    assert any("could not rewrite" in line for line in rec.lines)


def test_global_hook_secret_refused(machine):
    _set_hook(machine, "Notification", 'curl -H "Authorization: Bearer abcdefgh12345678" x')
    rec = own.record_global(_v("hook", "Notification:"), backup.Backup())
    assert not rec.ok and "secret" in rec.lines[0]
    assert _personal_empty()


def test_global_hook_script_secret_refused(machine):
    script = machine / "bin/s.sh"
    script.parent.mkdir()
    script.write_text("KEY=sk-" + "a" * 30 + "\n")
    _set_hook(machine, "Notification", f"bash '{script}'")
    rec = own.record_global(_v("hook", "Notification:"), backup.Backup())
    assert not rec.ok and "secret" in rec.lines[0]
    assert _personal_empty()


def test_global_skill_secret_refused(machine):
    (machine / ".claude/skills/my-skill/SKILL.md").write_text("token sk-" + "a" * 30)
    rec = own.record_global(_v("skill", "my-skill"), backup.Backup())
    assert not rec.ok and "secret" in rec.lines[0]
    assert not (paths.personal_root() / "skills/my-skill").exists()


def test_global_mcp_unkeyed_url_secret_refused(machine, fake_runner):
    cfg = json.loads((machine / ".claude.json").read_text())
    cfg["mcpServers"]["db"] = {"command": "x", "env": {"DB": "postgres://u:hunter2secret@h/db"}}
    (machine / ".claude.json").write_text(json.dumps(cfg))
    rec = own.record_global(_v("mcp", "db"), backup.Backup())
    assert not rec.ok and "secret" in rec.lines[0]
    assert _personal_empty()


def test_skill_scan_fails_closed_on_large_and_binary_files(machine):
    skill = machine / ".claude/skills/my-skill"
    (skill / "big.txt").write_text("x" * 1_100_000 + " sk-" + "a" * 30)
    rec = own.record_global(_v("skill", "my-skill"), backup.Backup())
    assert not rec.ok and "secret" in rec.lines[0]
    (skill / "big.txt").unlink()
    (skill / "blob.bin").write_bytes(b"\0\1binary sk-" + b"b" * 30)
    rec = own.record_global(_v("skill", "my-skill"), backup.Backup())
    assert not rec.ok
    assert not (paths.personal_root() / "skills/my-skill").exists()


def test_skill_scan_refuses_unreadable_file(machine, monkeypatch):
    import os
    if os.name == "nt" or os.geteuid() == 0:
        pytest.skip("permissions")
    f = machine / ".claude/skills/my-skill/locked.txt"
    f.write_text("x")
    f.chmod(0)
    rec = own.record_global(_v("skill", "my-skill"), backup.Backup())
    f.chmod(0o600)
    assert not rec.ok and "could not be read" in rec.lines[0]


def _profile(name):
    return json.loads((paths.personal_root() / f"profiles/{name}.json").read_text())


def test_project_plugin(machine):
    (machine / ".claude/plugins/known_marketplaces.json").write_text(json.dumps({
        "somewhere": {"source": {"source": "github", "repo": "me/somewhere"}}}))
    rec = own.record_project(_v("plugin", "mystery@somewhere"), "mine", backup.Backup())
    assert rec.ok and rec.machine is None
    prof = _profile("mine")
    assert prof["install"] == ["mystery@somewhere"]
    assert prof["settings"]["enabledPlugins"] == {"mystery@somewhere": True}
    assert "somewhere" in prof["settings"]["extraKnownMarketplaces"]


def test_project_mcp_rewrites_secret(machine):
    cfg = json.loads((machine / ".claude.json").read_text())
    cfg["mcpServers"]["mine"] = {"command": "x", "env": {"API_KEY": "k" * 20}}
    (machine / ".claude.json").write_text(json.dumps(cfg))
    own.record_project(_v("mcp", "mine"), "mine", backup.Backup())
    text = (paths.personal_root() / "profiles/mine.json").read_text()
    assert "${MINE_API_KEY}" in text and "k" * 20 not in text


def test_project_skill_goes_to_profile_skills(machine):
    (machine / ".claude/skills/my-skill/SKILL.md").write_text("mine")
    own.record_project(_v("skill", "my-skill"), "mine", backup.Backup())
    assert (paths.personal_root() / "profiles/skills/my-skill/SKILL.md").read_text() == "mine"
    assert not (paths.personal_root() / "skills/my-skill").exists()   # not linked globally
    assert _profile("mine")["skills"] == ["my-skill"]


def test_project_hook(machine):
    own.record_project(_v("hook", "PreToolUse:Edit"), "mine", backup.Backup())
    assert _profile("mine")["settings"]["hooks"]["PreToolUse"] == [
        {"matcher": "Edit", "hooks": [{"type": "command", "command": "my-own-linter"}]}]


def test_project_hook_with_secret_refused_and_nothing_written(machine):
    _set_hook(machine, "Notification", "curl -H 'Authorization: Bearer abcdefgh12345678' x")
    rec = own.record_project(_v("hook", "Notification:"), "mine", backup.Backup())
    assert not rec.ok
    assert "abcdefgh12345678" not in " ".join(rec.lines)
    assert not (paths.personal_root() / "profiles/mine.json").exists()


def test_project_on_kit_profile_name_starts_from_kit_copy(machine, kit_root):
    assert own.profile_note("db")
    own.record_project(_v("hook", "PreToolUse:Edit"), "db", backup.Backup())
    kit = json.loads((kit_root / "profiles/db.json").read_text())
    assert _profile("db")["mcp"] == kit["mcp"]


def test_project_bad_profile_name(machine):
    with pytest.raises(ValueError):
        own.record_project(_v("hook", "PreToolUse:Edit"), "../evil", backup.Backup())


def test_project_not_offered_for_marketplace(machine):
    with pytest.raises(ValueError):
        own.record_project(_as_own("marketplace", "severity1-marketplace"), "mine", backup.Backup())


def test_parse_spec_and_choice():
    assert own.parse_spec("foo@bar=global, hook:PreToolUse:Edit=project:mine,x=leave") == [
        (None, "foo@bar", own.Choice("global")),
        ("hook", "PreToolUse:Edit", own.Choice("project", "mine")),
        (None, "x", own.Choice("leave"))]
    for bad in ("x", "x=", "x=keep", "x=project", "x=project:../a"):
        with pytest.raises(ValueError):
            own.parse_spec(bad)


def test_resolve_errors(machine):
    (machine / ".claude/plugins/known_marketplaces.json").write_text(json.dumps({
        "somewhere": {"source": {"source": "github", "repo": "me/somewhere"}}}))
    vs = _verdicts()
    with pytest.raises(ValueError, match="no unmanaged item"):
        own.resolve(own.parse_spec("nothing=leave"), vs)
    with pytest.raises(ValueError, match="not available"):
        own.resolve(own.parse_spec("somewhere=project:x"), vs)


def test_resolve_ambiguous_needs_kind(machine):
    (machine / ".claude/skills/omarchy-kb").mkdir()
    vs = _verdicts()
    with pytest.raises(ValueError, match="mcp:omarchy-kb"):
        own.resolve(own.parse_spec("omarchy-kb=leave"), vs)
    assert len(own.resolve(own.parse_spec("skill:omarchy-kb=leave"), vs)) == 1


def test_resolve_allows_keep_global_for_scope_down_plugin(machine):
    pairs = own.resolve(own.parse_spec("sonarqube@claude-plugins-official=global"), _verdicts())
    assert pairs[0][1] == own.Choice("global")
    with pytest.raises(ValueError):
        own.resolve(own.parse_spec("sonarqube@claude-plugins-official=leave"), _verdicts())


def test_ask_choices_leave_all_is_default(machine):
    vs = own.unmanaged(_verdicts())
    pairs = own.ask_choices(vs, ask=lambda q: "")
    assert {c.action for _, c in pairs} == {"leave"} and len(pairs) == len(vs)


def test_ask_choices_each(machine):
    vs = [v for v in own.unmanaged(_verdicts()) if v.item.name in ("mystery@somewhere", "my-skill")]
    answers = iter(["c", "p", "mine", "g"])
    pairs = own.ask_choices(vs, ask=lambda q: next(answers))
    got = {v.item.name: c for v, c in pairs}
    assert got == {"mystery@somewhere": own.Choice("project", "mine"), "my-skill": own.Choice("global")}


def test_candidate_repos(machine):
    repo = machine / "code/app"
    repo.mkdir(parents=True)
    (repo / ".mcp.json").write_text(json.dumps({"mcpServers": {"omarchy-kb": {}}}))
    cfg = json.loads((machine / ".claude.json").read_text())
    cfg["projects"] = {str(repo): {}, str(machine / "code/gone"): {}}
    (machine / ".claude.json").write_text(json.dumps(cfg))
    assert own.candidate_repos(_v("mcp", "omarchy-kb").item) == [repo]
