"""With Claude Code off, adopt and update never act on Claude Code's files."""
import json

from loadout import adopt, codex, inventory, maintenance, paths, runner, targets
from loadout.jsonio import save_json


def _codex_only(monkeypatch):
    monkeypatch.setattr(targets, "claude_enabled", lambda: False)
    monkeypatch.setattr(targets, "codex_enabled", lambda: True)
    monkeypatch.setattr(codex, "_plugin_servers", lambda: set())


def test_inventory_has_no_claude_items_when_claude_code_is_off(fake_home, monkeypatch):
    _codex_only(monkeypatch)
    save_json(paths.claude_json(), {"mcpServers": {"context7": {"command": "x"}}})
    (paths.claude_home() / "skills" / "mine").mkdir(parents=True)
    kinds = {(i.kind, i.location) for i in inventory.collect(with_versions=False)}
    assert not any(loc in ("~/.claude.json",) or "/.claude/" in loc for _, loc in kinds)


def test_adopt_apply_never_runs_claude_when_claude_code_is_off(fake_home, fake_runner, monkeypatch):
    _codex_only(monkeypatch)
    save_json(paths.claude_json(), {"mcpServers": {"context7": {"command": "npx", "args": ["-y", "@upstash/context7-mcp"]}}})
    adopt.run(apply_changes=True, groups=None, skip=set(), yes=True, ask=lambda q: "", with_versions=False, interactive=False)
    assert not any(c[:1] == ["claude"] for c in fake_runner.calls)


def test_a_codex_skill_is_listed_even_if_claude_code_has_a_leftover_of_that_name(fake_home, monkeypatch):
    _codex_only(monkeypatch)
    (paths.agents_skills() / "solo").mkdir(parents=True)
    (paths.claude_home() / "skills" / "solo").mkdir(parents=True)
    assert "solo" in {p.name for p in codex.codex_only_skills()}


def test_update_leaves_claude_settings_and_servers_alone_when_claude_code_is_off(fake_home, fake_runner, monkeypatch):
    _codex_only(monkeypatch)
    settings = paths.claude_home() / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text("{}")
    entry = {"id": "x"}

    def outdated():
        settings.write_text(json.dumps({"installer": True}))  # what an installer does
        return [(entry, (1,), (2,))]
    monkeypatch.setattr(maintenance, "find_outdated", outdated)
    monkeypatch.setattr(maintenance.pkgmgr, "update_plan", lambda e: ([["true"]], "catalog"))
    monkeypatch.setattr(maintenance.versions, "local_version", lambda e: (2,))
    called = []
    monkeypatch.setattr(maintenance, "undo_reregistered", lambda bk: called.append(1) or ([], []))
    maintenance.update(True, lambda q: "")
    assert json.loads(settings.read_text()) == {"installer": True}
    assert called == []


def test_update_never_reads_claude_settings_when_claude_code_is_off(fake_home, fake_runner, monkeypatch):
    _codex_only(monkeypatch)
    settings = paths.claude_home() / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text("{not json")
    monkeypatch.setattr(maintenance, "find_outdated", lambda: [])
    assert maintenance.update(True, lambda q: "") == 0


def test_codex_only_adopt_ignores_a_broken_claude_settings_file(fake_home, monkeypatch):
    _codex_only(monkeypatch)
    settings = paths.claude_home() / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text("{not json")
    (paths.agents_skills() / "solo").mkdir(parents=True)
    verdicts = inventory.classify(inventory.collect(with_versions=False))
    assert any(v.item.name == "solo" for v in verdicts)


def test_groups_secrets_moves_secrets_without_yes(fake_home, fake_runner, monkeypatch):
    from loadout import adopt, secrets
    targets.set_agents({"claude": True, "codex": False})
    finding = secrets.Finding("s", "env", "TOKEN", "v", "~/.claude.json", True)
    monkeypatch.setattr(secrets, "scan_all", lambda: [finding])
    moved = []
    monkeypatch.setattr(adopt, "fix_secrets", lambda found, bk: moved.append(found) or [])
    adopt.run(apply_changes=True, groups={"secrets"}, skip=set(), yes=False, ask=lambda q: "",
              with_versions=False, interactive=False)
    assert moved  # naming the group is the consent, as for the other groups
