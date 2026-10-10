import json

import pytest

from loadout import adopt, backup, inventory, own, paths
from fixtures import FAKE_DEVIN, author_machine


@pytest.fixture
def machine(fake_home, fake_runner):
    author_machine(fake_home)
    return fake_home


def _verdicts():
    return inventory.classify(inventory.collect(with_versions=False))


def test_render_plan_groups_and_reasons(machine):
    text = adopt.render_plan(_verdicts(), [])
    assert text.index("REMOVE") < text.index("MIGRATE") < text.index("SCOPE-DOWN")
    assert "github-server" in text and "gh CLI" in text


def test_select_by_groups_with_skip(machine):
    chosen = adopt.select(_verdicts(), {"remove"}, {"gpt-taste"}, ask=lambda q: "")
    names = {v.item.name for v in chosen}
    assert "github-server" in names and "gpt-taste" not in names
    assert all(v.action == "remove" for v in chosen)


def test_select_interactive_defaults(machine):
    chosen = adopt.select(_verdicts() + [_outdated()], None, set(), ask=lambda q: "")
    actions = {v.action for v in chosen}
    assert actions <= {"remove", "migrate", "scope-down"}
    assert "own" not in actions and "update" not in actions


def test_apply_runs_cli_and_records_undo(machine, fake_runner):
    bk = backup.Backup()
    chosen = [v for v in _verdicts() if v.item.name in {"github-server", "auto-memory@severity1-marketplace",
                                                          "sonarqube@claude-plugins-official", "claude-code-templates"}]
    adopt.apply(chosen, bk)
    assert ["claude", "mcp", "remove", "-s", "user", "github-server"] in fake_runner.calls
    assert ["claude", "plugin", "uninstall", "auto-memory@severity1-marketplace", "--scope", "user", "--keep-data"] in fake_runner.calls
    assert ["claude", "plugin", "disable", "sonarqube@claude-plugins-official", "--scope", "user"] in fake_runner.calls
    assert ["claude", "plugin", "marketplace", "remove", "claude-code-templates"] in fake_runner.calls
    manifest = json.loads((bk.root / "manifest.json").read_text())
    undo_cmds = [s["undo"].get("run") for s in manifest["steps"]]
    assert any(c and c[:4] == ["claude", "mcp", "add-json", "-s"] for c in undo_cmds)


def test_apply_removes_hooks_and_skills_restorably(machine):
    bk = backup.Backup()
    chosen = [v for v in _verdicts() if (v.item.kind, v.item.name) in {("hook", "PreToolUse:"), ("hook", "Stop:"), ("skill", "gpt-taste")}]
    adopt.apply(chosen, bk)
    settings = json.loads((machine / ".claude/settings.json").read_text())
    commands = [h["command"] for groups in settings["hooks"].values() for g in groups for h in g["hooks"]]
    assert not any("serena-hooks remind" in c for c in commands)
    assert "Stop" not in settings["hooks"]
    assert "my-own-linter" in commands
    assert not (machine / ".claude/skills/gpt-taste").exists()
    assert (machine / ".agents/skills/gpt-taste").exists()  # shared source stays for other agents
    backup.restore(bk.root)
    assert (machine / ".claude/skills/gpt-taste/SKILL.md").exists()
    restored = json.loads((machine / ".claude/settings.json").read_text())
    assert "Stop" in restored["hooks"]


def test_migrate_claude_md(machine):
    bk = backup.Backup()
    adopt.migrate_claude_md(bk)
    me = (paths.personal_root() / "rules/me.md").read_text()
    assert "Skill Check Rule" in me
    assert (machine / ".claude/CLAUDE.md").read_text().startswith("<!--")


def test_fix_secrets_moves_env_value_to_secrets_file(machine, fake_runner):
    from loadout import secrets
    found = secrets.scan(json.loads((machine / ".claude.json").read_text()))
    adopt.fix_secrets(found, backup.Backup())
    text = paths.secrets_file().read_text()
    assert f"MCP_DOCKER_DEVIN_API_KEY='{FAKE_DEVIN}'" in text
    add = [c for c in fake_runner.calls if c[:3] == ["claude", "mcp", "add-json"]][0]
    assert "${MCP_DOCKER_DEVIN_API_KEY}" in add[-1]


def test_run_dry_run_changes_nothing(machine, fake_runner, capsys):
    before = (machine / ".claude/settings.json").read_text()
    assert adopt.run(False, None, set(), False, ask=lambda q: "", with_versions=False) == 0
    assert (machine / ".claude/settings.json").read_text() == before
    assert [c for c in fake_runner.calls if c[:1] == ["claude"]] == []
    assert "dry run" in capsys.readouterr().out


def test_fix_secrets_two_secrets_one_server_keeps_both(machine, fake_runner):
    from loadout import secrets
    cfg = json.loads((machine / ".claude.json").read_text())
    cfg["mcpServers"]["multi"] = {"command": "x", "env": {"A_API_KEY": "k" * 20, "B_TOKEN": "t" * 20}}
    (machine / ".claude.json").write_text(json.dumps(cfg))
    found = [f for f in secrets.scan(cfg) if f.server == "multi"]
    adopt.fix_secrets(found, backup.Backup())
    add = [c for c in fake_runner.calls if c[:3] == ["claude", "mcp", "add-json"] and c[5] == "multi"][0]
    assert "${MULTI_A_API_KEY}" in add[-1] and "${MULTI_B_TOKEN}" in add[-1]


def test_mcp_json_with_unselected_servers_is_edited_not_moved(machine):
    (machine / ".claude/.mcp.json").write_text(json.dumps({"mcpServers": {
        "codebase-memory-mcp": {"command": "a"}, "other": {"command": "b"}}}))
    bk = backup.Backup()
    chosen = [v for v in _verdicts() if v.item.location == "~/.claude/.mcp.json" and v.item.name == "codebase-memory-mcp"]
    adopt.apply(chosen, bk)
    assert list(json.loads((machine / ".claude/.mcp.json").read_text())["mcpServers"]) == ["other"]
    backup.restore(bk.root)
    assert "codebase-memory-mcp" in json.loads((machine / ".claude/.mcp.json").read_text())["mcpServers"]


def test_unselected_unknown_hook_survives(machine):
    chosen = [v for v in _verdicts() if v.action == "remove" and v.item.kind == "hook"]
    adopt.apply(chosen, backup.Backup())
    settings = json.loads((machine / ".claude/settings.json").read_text())
    assert "my-own-linter" in json.dumps(settings)


def test_own_remove_by_name_removes_and_restores(machine, fake_runner):
    pairs = own.resolve(own.parse_spec("omarchy-kb=remove,PreToolUse:Edit=remove"), _verdicts())
    bk = backup.Backup()
    adopt.apply_own(pairs, bk)
    assert ["claude", "mcp", "remove", "-s", "user", "omarchy-kb"] in fake_runner.calls
    assert "my-own-linter" not in (machine / ".claude/settings.json").read_text()
    backup.restore(bk.root)
    assert "my-own-linter" in (machine / ".claude/settings.json").read_text()
    assert any(c[:6] == ["claude", "mcp", "add-json", "-s", "user", "omarchy-kb"] for c in fake_runner.calls)


def test_groups_own_is_refused(machine, fake_runner, capsys):
    with pytest.raises(ValueError, match=r"group 'own': decide per item with --own NAME=CHOICE,\.\.\. \(see loadout configure own\)"):
        adopt.select(_verdicts(), {"own"}, set(), ask=lambda q: "")
    from loadout.__main__ import main
    assert main(["adopt", "--apply", "--yes", "--groups", "own", "--no-versions"]) == 1
    assert "group 'own'" in capsys.readouterr().err
    assert [c for c in fake_runner.calls if c[:2] == ["claude", "mcp"]] == []


def test_keep_never_acts(machine, fake_runner):
    kept = [v for v in _verdicts() if v.action == "keep"]
    assert kept
    adopt.apply(kept, backup.Backup())
    assert [c for c in fake_runner.calls if c[:1] == ["claude"]] == []


def test_secret_fix_undo_removes_then_readds_original(machine, fake_runner):
    from loadout import secrets
    found = [f for f in secrets.scan(json.loads((machine / ".claude.json").read_text())) if f.fixable]
    bk = backup.Backup()
    adopt.fix_secrets(found, bk)
    fake_runner.calls.clear()
    backup.restore(bk.root)
    srv = found[0].server
    kinds = [(c[2], c[5]) for c in fake_runner.calls if c[:1] == ["claude"]]
    assert kinds[:2] == [("remove", srv), ("add-json", srv)]
    assert found[0].value in fake_runner.calls[1][-1]


def test_marketplace_without_source_is_skipped(machine, fake_runner):
    v = [x for x in _verdicts() if x.item.kind == "marketplace"][0]
    v.item.extra["source"] = {}
    out = adopt.apply([adopt.Verdict(v.item, "remove", "x")], backup.Backup())
    assert "skipped (no source to restore from)" in out[0]
    assert fake_runner.calls == []


def test_unknown_group_name_rejected(machine):
    with pytest.raises(ValueError, match="unknown group 'bogus'"):
        adopt.select(_verdicts(), {"bogus"}, set(), ask=lambda q: "")


def test_migrate_claude_md_symlink_skipped(machine):
    md = machine / ".claude/CLAUDE.md"
    real = machine / "real.md"
    real.write_text("x")
    md.unlink()
    md.symlink_to(real)
    assert "symlink" in adopt.migrate_claude_md(backup.Backup())[0]


def test_migrate_claude_md_is_idempotent(machine):
    adopt.migrate_claude_md(backup.Backup())
    adopt.migrate_claude_md(backup.Backup())
    me = (paths.personal_root() / "rules/me.md").read_text()
    assert me.count("Migrated from") == 1


# --- non-interactive input and prompt UX (R-A, R-B) ---

def _outdated(action="update"):
    from loadout import catalog
    entry = next(e for e in catalog.binaries() if e["id"] == "rtk")
    item = inventory.Item("binary", "rtk", "0.1.0 -> 0.2.0", "PATH", {"entry": entry, "state": "outdated"})
    return adopt.Verdict(item, action, entry["reason"], entry["id"])


@pytest.mark.parametrize("word", ["a", "all", "y", "YES", "Yes"])
def test_group_prompt_accepts_yes_words(machine, word):
    chosen = adopt.select(_verdicts(), None, set(), ask=lambda q: word if "[a]ll" in q else "")
    assert {v.action for v in chosen} >= {"remove"}
    assert "own" not in {v.action for v in chosen}  # own items are chosen via own.ask_choices


def test_group_prompt_reasks_on_invalid_answer(machine, capsys):
    answers = iter(["maybe", "none"] + ["n"] * 20)
    chosen = adopt.select(_verdicts(), None, set(), ask=lambda q: next(answers))
    assert chosen == []
    assert "please answer" in capsys.readouterr().out


def test_group_prompts_name_the_action(machine):
    questions = []
    adopt.select(_verdicts(), None, set(), ask=lambda q: (questions.append(q), "p" if "[a]ll" in q else "")[1])
    text = "\n".join(questions)
    assert "remove skill gpt-taste? [y/N]" in text
    assert "disable globally plugin sonarqube@claude-plugins-official? [y/N]" in text


def test_plan_headers_explain_each_action(machine):
    text = adopt.render_plan(_verdicts() + [_outdated()], [])
    assert "REMOVE (" in text and "uninstall/remove; restorable." in text
    assert "remove your copy, because the loadout plugin provides it." in text
    assert "disable globally; enable per project with `loadout profile X`." in text
    assert "picking removes it; restorable." in text
    assert "plugins from a removed marketplace stay installed unless picked" in text


def test_plan_redacts_secrets(machine):
    from fixtures import FAKE_PAT
    text = adopt.render_plan(_verdicts(), [])
    assert FAKE_PAT not in text and "***" in text


def test_non_interactive_apply_changes_nothing_and_exits_2(machine, fake_runner, capsys):
    rc = adopt.run(True, None, set(), False, ask=lambda q: "", with_versions=False, interactive=False)
    assert rc == 2
    assert [c for c in fake_runner.calls if c[:1] == ["claude"]] == []
    assert "non-interactive: re-run with --yes, --groups GROUP,... or --own" in capsys.readouterr().out
    assert not paths.backups_root().exists()


def test_interactive_apply_needs_final_confirmation(machine, fake_runner, capsys):
    rc = adopt.run(True, None, set(), False, ask=lambda q: "", with_versions=False, interactive=True)
    assert rc == 0
    assert [c for c in fake_runner.calls if c[:1] == ["claude"]] == []
    assert "nothing changed" in capsys.readouterr().out


def test_interactive_apply_confirmed(machine, fake_runner):
    asked = []
    def ask(q):
        asked.append(q)
        return "y" if q.startswith("Apply") else ""
    adopt.run(True, None, set(), False, ask=ask, with_versions=False, interactive=True)
    assert any(q.startswith("Apply ") and "[y/N]" in q for q in asked)
    assert ["claude", "mcp", "remove", "-s", "user", "github-server"] in fake_runner.calls


def test_yes_never_selects_binary_updates(machine):
    chosen = adopt.select(_verdicts() + [_outdated()], adopt.DEFAULT_ALL, set(), ask=lambda q: "")
    assert "update" not in {v.action for v in chosen}


def test_binary_update_shown_and_confirmed_unless_yes_with_groups(machine, fake_runner, capsys, monkeypatch):
    monkeypatch.setattr(paths, "platform_key", lambda: "posix")  # rtk ships a posix-only update command
    asked = []
    out = adopt.apply([_outdated()], backup.Backup(), ask=lambda q: (asked.append(q), "")[1], confirm_cmds=True)
    assert asked and "run it?" in asked[0]
    assert "skipped" in out[0]
    assert not [c for c in fake_runner.calls if c[:1] != ["claude"]]
    assert "command:" in capsys.readouterr().out
    adopt.apply([_outdated()], backup.Backup(), ask=lambda q: "", confirm_cmds=False)
    assert [c for c in fake_runner.calls if c[:1] != ["claude"]]


def test_adopt_cli_yes_with_groups_update_runs_without_prompt(machine, fake_runner, monkeypatch):
    monkeypatch.setattr(paths, "platform_key", lambda: "posix")  # rtk ships a posix-only update command
    monkeypatch.setattr(inventory, "classify", lambda items: [_outdated()])
    rc = adopt.run(True, {"update"}, set(), True, ask=lambda q: (_ for _ in ()).throw(AssertionError(q)),
                   with_versions=False, interactive=False)
    assert rc == 0
    assert [c for c in fake_runner.calls if c[:1] != ["claude"]]


def test_marketplace_undo_records_full_source(machine, fake_runner):
    v = [x for x in _verdicts() if x.item.name == "claude-code-templates"][0]
    v.item.extra["source"]["ref"] = "v2"
    bk = backup.Backup()
    adopt.apply([v], bk)
    step = [s for s in bk.steps if "marketplace" in s["label"]][0]
    assert step["source"] == {"source": "git", "url": "https://github.com/davila7/claude-code-templates.git", "ref": "v2"}
    assert step["undo"]["run"][-1] == "https://github.com/davila7/claude-code-templates.git"


def test_migrate_rewrites_relative_imports_that_exist(machine):
    (machine / ".claude/RTK.md").write_text("rtk rules")
    out = adopt.migrate_claude_md(backup.Backup())
    me = (paths.personal_root() / "rules/me.md").read_text()
    assert "@~/.claude/RTK.md" in me and "\n@RTK.md" not in me
    assert not any(line.startswith("warning") for line in out)


def test_migrate_warns_about_missing_import_by_name(machine):
    out = adopt.migrate_claude_md(backup.Backup())
    assert any(line.startswith("warning") and "@RTK.md" in line for line in out)
    assert "@RTK.md" in (paths.personal_root() / "rules/me.md").read_text()


def test_migrate_new_me_md_is_undone_by_restore(machine):
    bk = backup.Backup()
    adopt.migrate_claude_md(bk)
    me = paths.personal_root() / "rules/me.md"
    assert me.exists()
    backup.restore(bk.root)
    assert not me.exists()
    assert "Skill Check Rule" in (machine / ".claude/CLAUDE.md").read_text()


def test_non_interactive_groups_never_prompts_for_secrets(machine, fake_runner):
    asked = []
    adopt.run(True, {"remove"}, set(), False, ask=lambda q: asked.append(q) or "", with_versions=False, interactive=False)
    assert asked == []
    assert not paths.secrets_file().exists()


from loadout import own


def _own_pairs(spec):
    return own.resolve(own.parse_spec(spec), _verdicts())


def test_apply_own_project_disables_and_removes(machine, fake_runner):
    (machine / ".claude/plugins/known_marketplaces.json").write_text(json.dumps({
        "somewhere": {"source": {"source": "github", "repo": "me/somewhere"}}}))
    bk = backup.Backup()
    lines, profiles = adopt.apply_own(_own_pairs("mystery@somewhere=project:mine,omarchy-kb=project:mine"), bk)
    assert ["claude", "plugin", "disable", "mystery@somewhere", "--scope", "user"] in fake_runner.calls
    assert ["claude", "mcp", "remove", "-s", "user", "omarchy-kb"] in fake_runner.calls
    assert set(profiles) == {"mine"}
    assert any("loadout profile mine" in line for line in lines)


def test_apply_own_leave_and_remove(machine, fake_runner):
    adopt.apply_own(_own_pairs("my-skill=leave,omarchy-kb=remove"), backup.Backup())
    assert own.is_left([v for v in _verdicts() if v.item.name == "my-skill"][0].item)
    assert ["claude", "mcp", "remove", "-s", "user", "omarchy-kb"] in fake_runner.calls


def test_apply_own_two_hooks_one_group(machine):
    data = json.loads((machine / ".claude/settings.json").read_text())
    data["hooks"]["PreToolUse"][3]["hooks"].append({"type": "command", "command": "second-linter"})
    (machine / ".claude/settings.json").write_text(json.dumps(data))
    pairs = [(v, own.Choice("global") if v.item.detail == "my-own-linter" else own.Choice("remove"))
             for v in own.unmanaged(_verdicts()) if v.item.kind == "hook"]
    adopt.apply_own(pairs, backup.Backup())
    commands = [h["command"] for g in json.loads((machine / ".claude/settings.json").read_text())["hooks"]["PreToolUse"]
                for h in g["hooks"]]
    assert commands.count("my-own-linter") == 1 and "second-linter" not in commands
    assert "rtk hook claude" in commands


def test_rerun_asks_nothing(machine, fake_runner):
    (machine / ".claude/plugins/known_marketplaces.json").write_text(json.dumps({
        "somewhere": {"source": {"source": "github", "repo": "me/somewhere"}}}))
    pairs = [(v, own.Choice("global") if "global" in own.options(v.item) else own.Choice("leave"))
             for v in own.unmanaged(_verdicts())]
    adopt.apply_own(pairs, backup.Backup())
    assert own.unmanaged(_verdicts()) == []


def test_select_pick_keep_global(machine):
    keep = []
    answers = iter(["p", "k", "n"])
    adopt.select([v for v in _verdicts() if v.action == "scope-down" and v.item.kind == "plugin"], None, set(),
                 ask=lambda q: next(answers, ""), keep_global=keep)
    assert len(keep) == 1 and keep[0].item.kind == "plugin"


def test_apply_own_collision_skips_machine_step(machine, fake_runner):
    path = paths.personal_root() / "profiles/mine.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"mcp": {"mcpServers": {"omarchy-kb": {"command": "other"}}}}))
    # omarchy-kb is now "keep" (in a personal profile); wrap it as own to exercise the collision path
    v = [x for x in _verdicts() if x.item.name == "omarchy-kb"][0]
    lines, _ = adopt.apply_own([(inventory.Verdict(v.item, "own", ""), own.Choice("project", "mine"))], backup.Backup())
    assert any(line.startswith("skipped:") for line in lines)
    assert ["claude", "mcp", "remove", "-s", "user", "omarchy-kb"] not in fake_runner.calls


def test_apply_own_overlap_with_others_acts_once(machine, fake_runner):
    v = [x for x in _verdicts() if x.item.name == "omarchy-kb"][0]
    adopt.apply_own([(v, own.Choice("leave"))], backup.Backup(), others=[inventory.Verdict(v.item, "remove", "")])
    assert ["claude", "mcp", "remove", "-s", "user", "omarchy-kb"] not in fake_runner.calls
    adopt.apply_own([(v, own.Choice("remove"))], backup.Backup(), others=[inventory.Verdict(v.item, "remove", "")])
    assert fake_runner.calls.count(["claude", "mcp", "remove", "-s", "user", "omarchy-kb"]) == 1


def test_apply_own_record_error_keeps_other_items(machine, fake_runner):
    vs = {x.item.name: x for x in _verdicts()}
    path = paths.personal_root() / "profiles/mine.json"
    path.parent.mkdir(parents=True)
    path.write_text("{corrupt")
    pairs = [(vs["omarchy-kb"], own.Choice("project", "mine")), (vs["my-skill"], own.Choice("global"))]
    lines, _ = adopt.apply_own(pairs, backup.Backup())
    assert any("omarchy-kb: failed:" in line for line in lines)
    assert ["claude", "mcp", "remove", "-s", "user", "omarchy-kb"] not in fake_runner.calls
    assert (paths.personal_root() / "skills/my-skill").exists()


def test_apply_own_unreadable_skill_is_a_collision_and_continues(machine, fake_runner):
    import os
    if os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0):
        pytest.skip("permissions not enforced")
    vs = {x.item.name: x for x in _verdicts()}
    skill = machine / ".claude/skills/my-skill"
    files = [f for f in skill.rglob("*") if f.is_file()]
    for f in files:
        f.chmod(0)
    try:
        lines, _ = adopt.apply_own([(vs["my-skill"], own.Choice("global")),
                                    (vs["omarchy-kb"], own.Choice("remove"))], backup.Backup())
    finally:
        for f in files:
            f.chmod(0o644)
    assert ["claude", "mcp", "remove", "-s", "user", "omarchy-kb"] in fake_runner.calls
    assert any("my-skill" in line for line in lines)


def test_apply_own_backs_up_settings(machine, fake_runner):
    settings = machine / ".claude/settings.json"
    original = settings.read_text()
    bk = backup.Backup()
    v = [x for x in _verdicts() if x.item.kind == "plugin" and x.action == "scope-down"][0]
    adopt.apply_own([(v, own.Choice("global"))], bk)
    backup.restore(bk.root, force=True)
    assert settings.read_text() == original


def test_apply_own_leave_is_restorable(machine):
    v = [x for x in _verdicts() if x.item.name == "my-skill"][0]
    bk = backup.Backup()
    adopt.apply_own([(v, own.Choice("leave"))], bk)
    assert own.decisions()
    backup.restore(bk.root, force=True)
    assert not own.decisions()


def test_apply_own_record_exception_is_reported_and_isolated(machine, fake_runner, monkeypatch):
    vs = {x.item.name: x for x in _verdicts()}
    real = own.record_global

    def flaky(v, bk):
        if v.item.name == "omarchy-kb":
            raise PermissionError(f"denied token={FAKE_PAT}")
        return real(v, bk)

    from fixtures import FAKE_PAT
    monkeypatch.setattr(own, "record_global", flaky)
    lines, _ = adopt.apply_own([(vs["omarchy-kb"], own.Choice("global")),
                                (vs["my-skill"], own.Choice("global"))], backup.Backup())
    failed = [line for line in lines if "omarchy-kb: failed:" in line]
    assert failed and FAKE_PAT not in failed[0]
    assert ["claude", "mcp", "remove", "-s", "user", "omarchy-kb"] not in fake_runner.calls
    assert (paths.personal_root() / "skills/my-skill").exists()


def test_apply_own_machine_step_error_does_not_stop_later_steps(machine, fake_runner, monkeypatch):
    from loadout import settings_merge
    vs = {x.item.name: x for x in _verdicts()}
    ran = []

    def fake_record(v, bk):
        def step():
            if v.item.name == "omarchy-kb":
                raise OSError("disk gone")
            ran.append(v.item.name)
            return [f"{v.item.name}: machine step ran"]
        return own.Recorded(True, [], step)

    applied = []
    monkeypatch.setattr(own, "record_global", fake_record)
    monkeypatch.setattr(settings_merge, "apply_settings", lambda: applied.append(1) or ({}, {}))
    lines, _ = adopt.apply_own([(vs["omarchy-kb"], own.Choice("global")),
                                (vs["my-skill"], own.Choice("global"))], backup.Backup())
    assert any("omarchy-kb: failed: disk gone" in line for line in lines)
    assert ran == ["my-skill"] and applied


def test_run_yes_leaves_own_tools(machine, fake_runner):
    assert adopt.run(True, None, set(), True, ask=lambda q: "", with_versions=False, interactive=False) == 0
    assert ["claude", "mcp", "remove", "-s", "user", "omarchy-kb"] not in fake_runner.calls
    assert not own.decisions()   # --yes does not remember "leave" either


def test_run_non_interactive_without_flags_exits_2(machine, fake_runner):
    assert adopt.run(True, None, set(), False, ask=lambda q: "", with_versions=False, interactive=False) == 2


def test_run_own_spec_non_interactive(machine, fake_runner):
    code = adopt.run(True, None, set(), False, ask=lambda q: "", with_versions=False, interactive=False,
                     own_spec="omarchy-kb=project:mine")
    assert code == 0
    assert (paths.personal_root() / "profiles/mine.json").exists()
    assert ["claude", "mcp", "remove", "-s", "user", "github-server"] not in fake_runner.calls  # other groups untouched


@pytest.mark.parametrize("spec", ["nothing=global", "omarchy-kb=leave,omarchy-kb=global"])
def test_run_own_spec_error_exits_2_before_changes(machine, fake_runner, capsys, spec):
    code = adopt.run(True, None, set(), False, ask=lambda q: "", with_versions=False, interactive=False,
                     own_spec=spec)
    assert code == 2 and capsys.readouterr().err.startswith("loadout:")
    assert [c for c in fake_runner.calls if c[:1] == ["claude"]] == []
    assert not own.decisions()


def test_run_prints_backup_even_if_apply_raises(machine, fake_runner, monkeypatch, capsys):
    def boom(pairs, bk, *a, **kw):
        bk.save_copy(machine / ".claude/settings.json", "partial work")
        raise RuntimeError("boom")
    monkeypatch.setattr(adopt, "apply_own", boom)
    with pytest.raises(RuntimeError):
        adopt.run(True, None, set(), True, ask=lambda q: "", with_versions=False, interactive=False)
    assert "backup:" in capsys.readouterr().out


def test_run_interactive_offers_repo_for_new_profile(machine, fake_runner, monkeypatch):
    from loadout import configure, project
    repo = machine / "code/app"
    repo.mkdir(parents=True)
    (repo / ".mcp.json").write_text(json.dumps({"mcpServers": {"omarchy-kb": {}}}))
    cfg = json.loads((machine / ".claude.json").read_text())
    cfg["projects"] = {str(repo): {}}
    (machine / ".claude.json").write_text(json.dumps(cfg))
    applied = []
    monkeypatch.setattr(project, "add_profile", lambda path, name, **kw: applied.append((path, name)) or 0)
    offered = []
    monkeypatch.setattr(configure, "offer_commit", lambda ask: offered.append(1))
    script = {"your own tools": "c", "mcp omarchy-kb": "p", "profile (": "mine", "Apply": "y", "repos": ""}

    def ask(q):
        return next((a for k, a in script.items() if k in q), "")
    adopt.run(True, None, set(), False, ask=ask, with_versions=False, interactive=True)
    assert applied == [(repo, "mine")]
    assert offered == [1]


def _scripted(script, asked):
    def ask(q):
        asked.append(q)
        return next((a for k, a in script.items() if k in q), "")
    return ask


def test_run_own_spec_never_offers_repo_or_commit(machine, fake_runner, monkeypatch, capsys):
    from loadout import configure
    monkeypatch.setattr(configure, "offer_commit", lambda ask: pytest.fail("commit offer"))
    asked = []
    ask = _scripted({"item(s)": "n", "Apply": "y"}, asked)
    adopt.run(True, None, set(), False, ask=ask, with_versions=False, interactive=True,
              own_spec="omarchy-kb=project:mine")
    assert any("Apply" in q for q in asked) and not any("repos" in q for q in asked)
    assert "enable it per project with `loadout profile mine`" in capsys.readouterr().out
    assert (paths.personal_root() / "profiles/mine.json").exists()


def test_run_interactive_leave_all_asks_nothing_more(machine, fake_runner, monkeypatch, capsys):
    from loadout import configure
    monkeypatch.setattr(configure, "offer_commit", lambda ask: pytest.fail("commit offer"))
    asked = []
    ask = _scripted({"item(s)": "n", "your own tools": "l"}, asked)
    adopt.run(True, None, set(), False, ask=ask, with_versions=False, interactive=True)
    assert "left on this machine" in capsys.readouterr().out
    assert own.decisions()
    assert not any("Apply" in q or "repos" in q for q in asked)


def test_run_interactive_enter_on_own_prompt_changes_nothing(machine, fake_runner, capsys):
    asked = []
    adopt.run(True, None, set(), False, ask=_scripted({"item(s)": "n"}, asked), with_versions=False, interactive=True)
    assert not own.decisions()
    assert "backup:" not in capsys.readouterr().out
    assert [c for c in fake_runner.calls if c[:1] == ["claude"]] == []


def test_run_declined_confirm_remembers_nothing(machine, fake_runner):
    asked = []
    ask = _scripted({"item(s)": "n", "your own tools": "c", " — ": "g", "Apply": "n"}, asked)
    adopt.run(True, None, set(), False, ask=ask, with_versions=False, interactive=True)
    assert any("Apply" in q for q in asked)
    assert not own.decisions()
    assert [c for c in fake_runner.calls if c[:1] == ["claude"]] == []


def test_offer_profiles_failure_does_not_stop_next_repo(machine, fake_runner, capsys):
    cfg = json.loads((machine / ".claude.json").read_text())
    cfg["projects"] = {}
    for name in ("a-bad", "b-good"):
        repo = machine / "code" / name
        (repo / ".claude").mkdir(parents=True)
        (repo / ".mcp.json").write_text(json.dumps({"mcpServers": {"omarchy-kb": {}}}))
        cfg["projects"][str(repo)] = {}
    (machine / "code/a-bad/.mcp.json").write_text('{"mcpServers": {"omarchy-kb": ')  # malformed, still mentions it
    (machine / ".claude.json").write_text(json.dumps(cfg))
    ask = _scripted({"item(s)": "n", "your own tools": "c", "mcp omarchy-kb": "p", "profile (": "mine", "Apply": "y"}, [])
    adopt.run(True, None, set(), False, ask=ask, with_versions=False, interactive=True)
    out = capsys.readouterr().out
    assert f"{(machine / 'code/a-bad').resolve()}: failed:" in out
    assert f"{(machine / 'code/b-good').resolve()}: profile mine applied" in out
