import json

import pytest

from loadout import adopt, backup, inventory, paths
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
    assert "unknown" not in actions and "update" not in actions


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
    assert not (machine / ".agents/skills/gpt-taste").exists()
    backup.restore(bk.root)
    assert (machine / ".agents/skills/gpt-taste/SKILL.md").exists()
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


def test_groups_unknown_removes_and_restores(machine, fake_runner):
    chosen = adopt.select(_verdicts(), {"unknown"}, set(), ask=lambda q: "")
    bk = backup.Backup()
    adopt.apply(chosen, bk)
    assert ["claude", "mcp", "remove", "-s", "user", "omarchy-kb"] in fake_runner.calls
    assert "my-own-linter" not in (machine / ".claude/settings.json").read_text()
    backup.restore(bk.root)
    assert "my-own-linter" in (machine / ".claude/settings.json").read_text()
    assert any(c[:6] == ["claude", "mcp", "add-json", "-s", "user", "omarchy-kb"] for c in fake_runner.calls)


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
    assert {v.action for v in chosen} >= {"remove", "unknown"}


def test_group_prompt_reasks_on_invalid_answer(machine, capsys):
    answers = iter(["maybe", "none"] + ["n"] * 20)
    chosen = adopt.select(_verdicts(), None, set(), ask=lambda q: next(answers))
    assert chosen == []
    assert "please answer" in capsys.readouterr().out


def test_group_prompts_name_the_action(machine):
    questions = []
    adopt.select(_verdicts(), None, set(), ask=lambda q: (questions.append(q), "p" if "[a]ll" in q else "")[1])
    text = "\n".join(questions)
    assert "remove mcp omarchy-kb? [y/N]" in text
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
    assert "non-interactive: re-run with --yes or --groups" in capsys.readouterr().out
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


def test_binary_update_shown_and_confirmed_unless_yes_with_groups(machine, fake_runner, capsys):
    asked = []
    out = adopt.apply([_outdated()], backup.Backup(), ask=lambda q: (asked.append(q), "")[1], confirm_cmds=True)
    assert asked and "run it?" in asked[0]
    assert "skipped" in out[0]
    assert not [c for c in fake_runner.calls if c[:1] != ["claude"]]
    assert "command:" in capsys.readouterr().out
    adopt.apply([_outdated()], backup.Backup(), ask=lambda q: "", confirm_cmds=False)
    assert [c for c in fake_runner.calls if c[:1] != ["claude"]]


def test_adopt_cli_yes_with_groups_update_runs_without_prompt(machine, fake_runner, monkeypatch):
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
