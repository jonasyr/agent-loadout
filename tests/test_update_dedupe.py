"""`loadout update` undoes exact duplicates an installer re-registers (codebase-memory-mcp update)."""
import json

from loadout import backup, catalog, maintenance as m, paths, runner, versions

CBM = "/home/x/.local/bin/codebase-memory-mcp"


def _entry():
    return next(e for e in catalog.binaries() if e["id"] == "codebase-memory-mcp")


def _w(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data) if not isinstance(data, str) else data)


def _installer_side_effects(home):
    """What codebase-memory-mcp update did on the author's machine."""
    cj = json.loads((home / ".claude.json").read_text())
    cj["mcpServers"]["codebase-memory-mcp"] = {"command": CBM}
    _w(home / ".claude.json", cj)
    _w(home / ".claude/.mcp.json", {"mcpServers": {"codebase-memory-mcp": {"command": CBM}}})
    for name in ("cbm-code-discovery-gate", "cbm-session-reminder"):
        _w(home / ".claude/hooks" / name, "#!/bin/sh\n")


def _machine(home):
    _w(home / ".claude.json", {"mcpServers": {
        "sonarqube": {"command": "sonar", "args": ["run", "mcp"]},       # scope-down: never touched here
        "omarchy-kb": {"command": "docker", "args": ["exec", "kb"]},     # unknown: never touched
    }})
    _w(home / ".claude/settings.json", {"hooks": {"PreToolUse": [
        {"matcher": "Edit", "hooks": [{"type": "command", "command": "my-own-linter"}]},
        {"matcher": "Grep", "hooks": [{"type": "command", "command": "~/.claude/hooks/cbm-code-discovery-gate"}]},
    ]}})
    _w(home / ".claude/hooks/my-hook.sh", "#!/bin/sh\n")


def _run_update(fake_home, fake_runner, monkeypatch, side_effects=True):
    monkeypatch.setattr(paths, "platform_key", lambda: "posix")
    monkeypatch.setattr(m, "find_outdated", lambda: [(_entry(), (0, 10, 0), (0, 11, 0))])
    monkeypatch.setattr(versions, "local_version", lambda e: (0, 11, 0))

    def run(cmd, cwd=None, timeout=300, env=None):
        if cmd[:2] == ["codebase-memory-mcp", "update"] and side_effects:
            _installer_side_effects(fake_home)
        return fake_runner(cmd, cwd, timeout, env)

    monkeypatch.setattr(runner, "run", run)
    return m.update(yes=True, ask=lambda q: "")


def test_update_undoes_reregistered_duplicates_only(fake_home, fake_runner, monkeypatch, capsys):
    _machine(fake_home)
    assert _run_update(fake_home, fake_runner, monkeypatch) == 0
    out = capsys.readouterr().out
    removes = [c for c in fake_runner.calls if c[:3] == ["claude", "mcp", "remove"]]
    assert removes == [["claude", "mcp", "remove", "-s", "user", "codebase-memory-mcp"]]
    assert not (fake_home / ".claude/.mcp.json").exists()
    hooks = json.loads((fake_home / ".claude/settings.json").read_text())["hooks"]["PreToolUse"]
    assert [g["matcher"] for g in hooks] == ["Edit"]  # my-own-linter kept, cbm hook gone
    hook_dir = fake_home / ".claude/hooks"
    assert sorted(p.name for p in hook_dir.iterdir()) == ["my-hook.sh"]
    assert "undid duplicates" in out and "loadout restore" in out
    root = next(p for p in paths.backups_root().iterdir()
                if "re-registered" in json.loads((p / "manifest.json").read_text())["description"])
    manifest = json.loads((root / "manifest.json").read_text())
    labels = " ".join(s["label"] for s in manifest["steps"])
    assert "mcp codebase-memory-mcp" in labels and "cbm-session-reminder" in labels
    # the undo brings everything back
    lines, ok, _ = backup.restore(root)
    assert ok, lines
    assert (hook_dir / "cbm-session-reminder").exists() and (fake_home / ".claude/.mcp.json").exists()


def test_referenced_cbm_hook_script_stays(fake_home, fake_runner, monkeypatch):
    _machine(fake_home)
    _w(fake_home / ".claude/settings.local.json", {"hooks": {"Stop": [
        {"hooks": [{"type": "command", "command": "~/.claude/hooks/cbm-session-reminder"}]}]}})
    _run_update(fake_home, fake_runner, monkeypatch)
    assert (fake_home / ".claude/hooks/cbm-session-reminder").exists()


def test_no_cleanup_when_no_update_ran(fake_home, fake_runner, monkeypatch):
    _machine(fake_home)
    _installer_side_effects(fake_home)
    monkeypatch.setattr(m, "find_outdated", lambda: [])
    m.update(yes=True, ask=lambda q: "")
    assert (fake_home / ".claude/.mcp.json").exists()
    assert not [c for c in fake_runner.calls if c[:3] == ["claude", "mcp", "remove"]]


def test_codebase_memory_skill_is_kept(fake_home, fake_runner):
    from loadout import inventory
    (fake_home / ".claude/skills/codebase-memory").mkdir(parents=True)
    v = [v for v in inventory.classify(inventory.collect(with_versions=False)) if v.item.name == "codebase-memory"]
    assert v and v[0].action == "keep"


def test_update_never_auto_removes_a_migrate_skill(fake_home, fake_runner, monkeypatch):
    from loadout import inventory
    _machine(fake_home)
    skill = fake_home / ".claude/skills/dup-skill"
    skill.mkdir(parents=True)
    real = inventory.classify

    def classify(items):  # pretend the catalog marks this skill as a kit duplicate
        out = real(items)
        for v in out:
            if v.item.kind == "skill" and v.item.name == "dup-skill":
                v.action = "migrate"
        return out

    monkeypatch.setattr(inventory, "classify", classify)
    _run_update(fake_home, fake_runner, monkeypatch)
    assert skill.exists()
    assert not (fake_home / ".claude/.mcp.json").exists()  # MCP duplicates are still undone


# --- only exact duplicates of the enabled loadout plugin (review C1) ----------------------

SERENA = {"type": "stdio", "command": "serena", "args": ["--project-from-cwd", "start-mcp-server", "--context=claude-code"]}


def _servers(home, servers):
    _w(home / ".claude.json", {"mcpServers": servers})


def _removed(fake_runner):
    return sorted(c[-1] for c in fake_runner.calls if c[:3] == ["claude", "mcp", "remove"])


def _personal(home, settings=None, mcp=None):
    root = paths.personal_root()
    root.mkdir(parents=True, exist_ok=True)
    if settings is not None:
        _w(root / "settings.json", settings)
    if mcp is not None:
        _w(root / "mcp.json", {"mcpServers": mcp})


def test_exact_serena_duplicate_is_removed_args_order_insensitive(fake_home, fake_runner, monkeypatch):
    _servers(fake_home, {"serena": SERENA})
    _run_update(fake_home, fake_runner, monkeypatch, side_effects=False)
    assert _removed(fake_runner) == ["serena"]


def test_own_context7_server_is_left_alone(fake_home, fake_runner, monkeypatch, capsys):
    _personal(fake_home, settings={"enabledPlugins": {"context7@claude-plugins-official": False}})
    _servers(fake_home, {"context7": {"type": "http", "url": "https://mcp.context7.com/mcp",
                                      "headers": {"CONTEXT7_API_KEY": "${C7}"}}})
    _run_update(fake_home, fake_runner, monkeypatch, side_effects=False)
    assert _removed(fake_runner) == []
    assert "context7" in capsys.readouterr().out  # reported, not removed


def test_forked_serena_is_left_alone(fake_home, fake_runner, monkeypatch):
    _servers(fake_home, {"serena": {"command": "uvx", "args": ["--from", "git+https://github.com/me/serena-fork",
                                                               "serena", "start-mcp-server", "--context", "ide-assistant"]}})
    _run_update(fake_home, fake_runner, monkeypatch, side_effects=False)
    assert _removed(fake_runner) == []


def test_personal_managed_server_is_left_alone(fake_home, fake_runner, monkeypatch):
    _personal(fake_home, mcp={"serena": SERENA, "my-serena": SERENA})
    _servers(fake_home, {"serena": SERENA, "my-serena": SERENA})
    _run_update(fake_home, fake_runner, monkeypatch, side_effects=False)
    assert _removed(fake_runner) == []


def test_nothing_removed_when_loadout_plugin_disabled(fake_home, fake_runner, monkeypatch):
    _personal(fake_home, settings={"enabledPlugins": {"loadout@agent-loadout": False}})
    _machine(fake_home)
    _w(fake_home / ".claude/settings.json", {"hooks": {"PreToolUse": [
        {"matcher": "Bash", "hooks": [{"type": "command", "command": "rtk hook claude"}]}]}})
    _run_update(fake_home, fake_runner, monkeypatch)
    assert _removed(fake_runner) == []
    assert "rtk hook claude" in (fake_home / ".claude/settings.json").read_text()
    assert (fake_home / ".claude/hooks/cbm-session-reminder").exists()


def test_rtk_hook_removed_only_when_identical_and_plugin_enabled(fake_home, fake_runner, monkeypatch):
    _servers(fake_home, {})
    _w(fake_home / ".claude/settings.json", {"hooks": {"PreToolUse": [
        {"matcher": "Bash", "hooks": [{"type": "command", "command": "rtk  hook claude"}]},
        {"matcher": "Bash", "hooks": [{"type": "command", "command": "rtk hook claude --verbose"}]}]}})
    _run_update(fake_home, fake_runner, monkeypatch, side_effects=False)
    text = (fake_home / ".claude/settings.json").read_text()
    assert "rtk hook claude --verbose" in text and '"rtk  hook claude"' not in text


def test_lookalike_hook_script_file_is_kept(fake_home, fake_runner, monkeypatch):
    _machine(fake_home)
    for name in ("my-cbm-session-reminder-wrapper.sh", "cbm-session-reminder.bak"):
        _w(fake_home / ".claude/hooks" / name, "x")
    _run_update(fake_home, fake_runner, monkeypatch)
    names = sorted(p.name for p in (fake_home / ".claude/hooks").iterdir())
    assert names == ["cbm-session-reminder.bak", "my-cbm-session-reminder-wrapper.sh", "my-hook.sh"]
