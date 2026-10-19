"""The apply steps bootstrap, configure and update share (cli/loadout/apply.py), and the facts each one reports."""
import json

import pytest

from loadout import apply, backup, bootstrap as b, catalog, codex, codex_hooks, link, paths, runner, targets


def _bk():
    return backup.Backup(description="t")


def _codex_parts(monkeypatch, instructions="instructions up to date", config=(), hooks=(), skills=(), plugins=()):
    seen = {}
    monkeypatch.setattr(codex, "apply_instructions", lambda bk: instructions)
    monkeypatch.setattr(codex, "apply_config", lambda bk, dry_run=False: list(config))

    def hooks_apply(bk, keep=False, dry_run=False):
        seen["keep"] = keep
        return list(hooks)

    def plugins_apply(bk, refresh=False, say=None, auto=False):
        seen.update(refresh=refresh, auto=auto)
        return list(plugins)
    monkeypatch.setattr(codex_hooks, "apply", hooks_apply)
    monkeypatch.setattr(codex, "apply_skills", lambda bk: list(skills))
    monkeypatch.setattr(codex, "apply_plugins", plugins_apply)
    return seen


def test_codex_step_facts_come_from_what_each_part_did(fake_home, fake_runner, monkeypatch):
    _codex_parts(monkeypatch, instructions="instructions written to ~/.codex/AGENTS.md",
                 hooks=["hooks.json: added Serena's hooks (SessionStart); approve them in Codex: /hooks"],
                 skills=["linked /a -> /b"], plugins=["plugin x@y: installed"])
    r = apply.codex_step(_bk(), refresh_plugins=False, auto=False, keep=False, on=True)
    assert r.name == "Codex"
    assert r.facts == {"codex_block_written", "serena_hooks_added", "codex_skills_linked", "codex_plugins_installed"}
    assert r.level == "ok" and "instructions written to ~/.codex/AGENTS.md" in r.lines


def test_codex_step_reports_removed_hooks_and_failures(fake_home, fake_runner, monkeypatch):
    _codex_parts(monkeypatch, hooks=["hooks.json: removed loadout's Serena hooks; if Codex asks about your other "
                                     "hooks, review them in /hooks"],
                 plugins=["plugin x@y: failed: no network"])
    r = apply.codex_step(_bk(), refresh_plugins=False, auto=False, keep=False, on=True)
    assert r.facts == {"codex_hooks_removed", "failed:codex"} and r.level == "warn"
    assert r.summary == "1 problem(s) (below)"


def test_codex_step_sees_a_config_change_without_a_line(fake_home, fake_runner, monkeypatch):
    _codex_parts(monkeypatch)

    def write_config(bk, dry_run=False):
        (paths.codex_home()).mkdir(parents=True, exist_ok=True)
        (paths.codex_home() / "config.toml").write_text("[mcp_servers.x]\ncommand = \"x\"\n", encoding="utf-8")
        return []
    monkeypatch.setattr(codex, "apply_config", write_config)
    r = apply.codex_step(_bk(), refresh_plugins=False, auto=False, keep=False, on=True)
    assert r.facts == {"codex_config_changed"}


def test_codex_step_sees_updated_plugins_on_a_refresh(fake_home, fake_runner, monkeypatch):
    _codex_parts(monkeypatch)
    versions = iter([{"x@y": "1.0"}, {"x@y": "1.1"}])
    monkeypatch.setattr(codex, "plugin_versions", lambda: next(versions))
    r = apply.codex_step(_bk(), refresh_plugins=True, auto=False, keep=False, on=True)
    assert r.facts == {"codex_plugins_updated"}


def test_apply_parts_splits_the_flags_that_apply_all_ties_together(fake_home, fake_runner, monkeypatch):
    seen = _codex_parts(monkeypatch, instructions="instructions written to ~/.codex/AGENTS.md",
                        plugins=["plugin x@y: installed"])
    parts = codex.apply_parts(_bk(), refresh=True, auto=False, keep=False)
    assert set(parts) == {"instructions", "config", "hooks", "skills", "plugins"}
    assert parts["instructions"] == ["instructions written to ~/.codex/AGENTS.md"]
    assert parts["plugins"] == ["plugin x@y: installed"]
    assert seen == {"keep": False, "refresh": True, "auto": False}
    # apply_all keeps today's coupling: refresh is also the daily sync's auto and keep
    assert codex.apply_all(_bk(), refresh=True) == ["instructions written to ~/.codex/AGENTS.md", "plugin x@y: installed"]
    assert seen == {"keep": True, "refresh": True, "auto": True}


def test_apply_parts_accepts_skip_unchanged(fake_home, fake_runner, monkeypatch):
    _codex_parts(monkeypatch)
    assert codex.apply_parts(_bk(), refresh=True, auto=False, keep=False, skip_unchanged=True)["plugins"] == []


def test_codex_step_dry_changes_nothing(fake_home, fake_runner, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("dry ran a writing step")
    monkeypatch.setattr(codex, "apply_all", boom)
    monkeypatch.setattr(codex, "apply_parts", boom)
    r = apply.codex_step(_bk(), refresh_plugins=True, auto=False, keep=False, on=True, dry=True)
    assert "codex_block_written" in r.facts  # no AGENTS.md yet: the block would be written
    assert not (paths.codex_home() / "AGENTS.md").exists()
    assert not any(c[:3] in (["codex", "plugin", "add"], ["codex", "plugin", "marketplace"]) for c in fake_runner.calls)


def _plugins_wanted(fake_home):
    personal = paths.personal_root()
    personal.mkdir(parents=True, exist_ok=True)
    (personal / "settings.json").write_text(json.dumps({
        "extraKnownMarketplaces": {"mine": {"source": {"source": "github", "repo": "me/mine"}}},
        "enabledPlugins": {"tool@mine": True}}), encoding="utf-8")


def test_claude_plugins_step_dry_runs_no_install(fake_home, fake_runner):
    _plugins_wanted(fake_home)
    r = apply.claude_plugins_step(dry=True, on=True)
    assert any("tool@mine" in line for line in r.lines) and any("me/mine" in line for line in r.lines)
    assert not any(c[:3] == ["claude", "plugin", "install"] for c in fake_runner.calls)
    assert not any(c[:4] == ["claude", "plugin", "marketplace", "add"] for c in fake_runner.calls)


def test_claude_plugins_step_facts(fake_home, fake_runner):
    _plugins_wanted(fake_home)
    r = apply.claude_plugins_step(on=True)
    assert {"claude_plugins_installed", "claude_marketplace_added"} <= r.facts
    assert "plugin tool@mine: installed" in r.lines and r.level == "ok"
    assert r.name == "Plugins" and r.summary.endswith("kit plugins ready")


def test_claude_plugins_step_failure(fake_home, fake_runner):
    _plugins_wanted(fake_home)
    fake_runner.responses[("claude", "plugin", "install")] = runner.Result(1, "", "boom")
    r = apply.claude_plugins_step(on=True)
    assert "failed:claude_plugins" in r.facts and "claude_plugins_installed" not in r.facts
    assert r.level == "warn" and "failed (below)" in r.summary


def test_settings_step_facts(fake_home, fake_runner):
    personal = paths.personal_root()
    personal.mkdir(parents=True)
    (personal / "settings.json").write_text("{}\n", encoding="utf-8")
    (personal / "mcp.json").write_text(json.dumps({"mcpServers": {"srv": {"command": "srv"}}}), encoding="utf-8")
    r = apply.settings_step(_bk(), on=True)
    assert {"settings_changed", "mcp_changed"} <= r.facts
    assert r.lines[0] == "settings updated" and "mcp srv: added" in r.lines
    again = apply.settings_step(_bk(), on=True)
    assert "settings_changed" not in again.facts and again.lines[0] == "settings already up to date"


def test_link_step_without_claude_links_only_the_launcher(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(link, "link_all", lambda bk, **k: pytest.fail("Claude Code is off"))
    monkeypatch.setattr(link, "link_bin", lambda bk: ["wrote launcher /x"])
    r = apply.link_step(_bk(), claude_on=False)
    assert r.lines == ["wrote launcher /x"] and r.facts == set()


def test_link_step_reports_linked_rules(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(link, "link_all", lambda bk, retry_symlinks=False: ["linked /a -> /b"])
    monkeypatch.setattr(link, "link_bin", lambda bk: [])
    assert apply.link_step(_bk(), claude_on=True).facts == {"rules_linked"}


def _forbid(monkeypatch, *names):
    def boom(*a, **k):
        raise AssertionError("read an agent that is off")
    for mod, name in names:
        monkeypatch.setattr(mod, name, boom)


def test_claude_off_gives_empty_claude_steps_and_reads_nothing(fake_home, fake_runner, monkeypatch):
    from loadout import personal_mcp, settings_merge
    paths.personal_root().mkdir(parents=True)
    targets.set_agents({"claude": False, "codex": True})
    _forbid(monkeypatch, (settings_merge, "desired_settings"), (settings_merge, "apply_settings"),
            (settings_merge, "would_change"), (personal_mcp, "apply_mcp"), (b, "setup_plugins"), (b, "plugins_plan"))
    for r in (apply.settings_step(_bk()), apply.claude_plugins_step(), apply.claude_plugins_step(dry=True)):
        assert (r.lines, r.facts) == ([], set())
    assert fake_runner.calls == [] and not paths.claude_home().exists()


def test_codex_off_gives_an_empty_codex_step_and_reads_nothing(fake_home, fake_runner, monkeypatch):
    paths.personal_root().mkdir(parents=True)
    targets.set_agents({"claude": True, "codex": False})
    _forbid(monkeypatch, (codex, "apply_all"), (codex, "apply_parts"), (codex, "render_instructions"),
            (codex, "apply_config"), (codex_hooks, "apply"))
    for r in (apply.codex_step(_bk(), refresh_plugins=True, auto=False, keep=False),
              apply.codex_step(_bk(), refresh_plugins=True, auto=False, keep=False, dry=True)):
        assert (r.lines, r.facts) == ([], set())
    assert fake_runner.calls == [] and not paths.codex_home().exists()


def _only(monkeypatch, entries):
    monkeypatch.setattr(catalog, "binaries", lambda: entries)


def _bin(i, needs=(), required=True, helper=False, status="core"):
    e = {"id": i, "kind": "binary", "status": status, "required": required, "needs": list(needs),
         "install": {"posix": [[f"install-{i}"]], "windows": [[f"install-{i}"]]}, "version": {"cmd": [i, "--version"]}}
    if helper:
        e["helper"] = True
    return e


def test_missing_tools_lists_required_and_optional_without_installing(fake_home, fake_runner, monkeypatch):
    _only(monkeypatch, [_bin("node", ["mise"]), _bin("mise", helper=True, required=False),
                        _bin("rg", required=False, status="recommended"), _bin("uv"), _bin("codex")])
    fake_runner.missing.update({"node", "mise", "rg", "codex"})
    found = b.missing_tools(set(), {"codex"})
    assert [(e["id"], cmds, optional) for e, cmds, optional in found] == [
        ("mise", [["install-mise"]], False), ("node", [["install-node"]], False),
        ("rg", [["install-rg"]], True), ("codex", [["install-codex"]], True)]
    assert [e["id"] for e, _, _ in b.missing_tools({"codex"}, set())] == ["mise", "node", "rg"]
    assert not any(c[0].startswith("install-") for c in fake_runner.calls)


def test_install_tool_reports_ok_and_failure(fake_home, fake_runner, monkeypatch):
    entry = _bin("rg")
    fake_runner.missing.add("rg")

    def run(cmd, cwd=None, timeout=300, env=None):
        fake_runner.calls.append(list(cmd))
        fake_runner.missing.discard("rg")
        return runner.Result(0, "", "")
    monkeypatch.setattr(runner, "run", run)
    assert b.install_tool(entry, [["install-rg"]]) == (True, [])

    fake_runner.missing.add("rg")
    monkeypatch.setattr(runner, "run", fake_runner)
    fake_runner.responses[("install-rg",)] = runner.Result(1, "", "boom")
    ok, lines = b.install_tool(entry, [["install-rg"]])
    assert not ok and lines[0] == "failed to install rg: boom"


def test_codex_step_passes_command_and_on_wait_to_the_lock(fake_home, fake_runner, monkeypatch):
    from loadout import locks
    _codex_parts(monkeypatch)
    held = locks.acquire(codex.LOCK, "bootstrap", 0)
    monkeypatch.setattr(locks, "foreground_wait", lambda: 0.1)
    waits = []
    r = apply.codex_step(_bk(), refresh_plugins=True, auto=False, keep=False, on=True, command="update",
                         on_wait=lambda: waits.append(1))
    held.release()
    assert waits, "on_wait never reached the Codex lock"
    assert r.facts == {"skipped:codex"} and r.lines[0].startswith("skipped: ") and r.level == "warn"


def test_codex_step_names_its_command(fake_home, fake_runner, monkeypatch):
    seen = {}
    monkeypatch.setattr(codex, "apply_all", lambda bk, refresh=False, **kw: seen.update(kw) or [])
    apply.codex_step(_bk(), refresh_plugins=False, auto=False, keep=False, on=True, command="update")
    assert seen["command"] == "update" and seen["on_wait"] is None


def test_codex_dry_follows_keep_and_the_frozen_marketplaces(fake_home, fake_runner, monkeypatch):
    seen = {}
    monkeypatch.setattr(codex_hooks, "apply", lambda bk, dry_run=False, keep=False: seen.update(keep=keep) or [])
    monkeypatch.setattr(codex, "apply_config", lambda bk, dry_run=False: [])
    monkeypatch.setattr(codex, "installed_plugins", lambda: set())
    from loadout import settings_merge
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: {
        "extraKnownMarketplaces": {"frozen": {"source": {"source": "github", "repo": "me/frozen"}, "autoUpdate": False},
                                   "live": {"source": {"source": "github", "repo": "me/live"}}},
        "enabledPlugins": {"a@frozen": True, "b@live": True}})
    r = apply.codex_step(_bk(), refresh_plugins=True, auto=True, keep=True, on=True, dry=True)
    assert seen == {"keep": True}
    assert "marketplace me/live: to refresh" in r.lines and "marketplace me/frozen: to refresh" not in r.lines
    assert "plugin a: to install" in r.lines  # a missing plugin is still installed from a frozen marketplace
    r = apply.codex_step(_bk(), refresh_plugins=True, auto=False, keep=False, on=True, dry=True)
    assert "marketplace me/frozen: to refresh" in r.lines


def test_failed_matches_what_loadout_prints_not_names(fake_home, fake_runner, monkeypatch):
    _codex_parts(monkeypatch, skills=["linked /x/failed-ideas -> /y/failed-ideas"])
    assert "failed:codex" not in apply.codex_step(_bk(), refresh_plugins=False, auto=False, keep=False, on=True).facts
    _codex_parts(monkeypatch, plugins=["plugin x@y: failed: boom"])
    assert "failed:codex" in apply.codex_step(_bk(), refresh_plugins=False, auto=False, keep=False, on=True).facts
