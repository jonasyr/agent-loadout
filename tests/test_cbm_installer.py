"""The files `codebase-memory-mcp install` writes next to loadout's plugin: named by check, removed by adopt on a yes."""
import json

import pytest

from loadout import adopt, backup, cbm_installer, check, codex, duplicates, inventory, maintenance, paths, targets
from loadout.jsonio import save_json

START, END = cbm_installer.AGENTS_START, cbm_installer.AGENTS_END
PLUGIN_ON = '[plugins."loadout@agent-loadout"]\nenabled = true\n'
INLINE = ('\n[[hooks.PreToolUse]]\nmatcher = "Grep"\n\n[[hooks.PreToolUse.hooks]]\ntype = "command"\n'
          'command = "codebase-memory-mcp hook-augment"\n')
SECRET = "SECRET-CONTENT-XYZ"  # file text that must never reach a row or an adopt line
ECHO = {"hooks": {"SessionStart": [{"matcher": "startup|resume", "hooks": [
    {"type": "command", "command": f'echo "{SECRET}: use codebase-memory-mcp tools first"'}]}],
    "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "my-own-linter"}]}]}}
BEFORE = "# Mine\r\nkeep this\r\n\r\n"
BLOCK = f"{START}\r\n{SECRET} use codebase-memory-mcp\r\n{END}"
AFTER = "\r\n## After\r\nlast line"  # CRLF, no trailing newline


def _w(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8") if isinstance(text, str) else json.dumps(text, indent=2).encode())


@pytest.fixture
def machine(fake_home, fake_runner, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    targets.set_agents({"claude": True, "codex": True})
    monkeypatch.setattr(duplicates, "plugin_enabled", lambda: True)
    _w(fake_home / ".claude/plugins/installed_plugins.json",  # installed in Claude Code, not only wanted
       {"plugins": {"loadout@agent-loadout": [{"scope": "user", "version": "1"}]}})
    _w(paths.codex_home() / "config.toml", PLUGIN_ON)
    return fake_home


def _everything(home):
    _w(home / ".claude/settings.json", {"hooks": {"SessionStart": [{"hooks": [
        {"type": "command", "command": "~/.claude/hooks/codebase-memory-session.sh"}]}]}})
    _w(home / ".claude/hooks/codebase-memory-session.sh", f"#!/bin/sh\n# {SECRET}\n")
    _w(home / ".claude/hooks/codebase-memory-coverage.sh", f"#!/bin/sh\n# {SECRET}\n")  # no hook runs it
    _w(home / ".claude/agents/codebase-memory.md", f"---\nname: codebase-memory\n---\n{SECRET}\n")
    _w(paths.codex_home() / "AGENTS.md", BEFORE + BLOCK + AFTER)
    _w(paths.codex_home() / "hooks.json", ECHO)
    _w(paths.codex_home() / "config.toml", PLUGIN_ON + INLINE)


def test_find_lists_each_artefact(machine):
    _everything(machine)
    found = cbm_installer.find()
    kinds = sorted(a.kind for a in found)
    assert kinds == ["claude-agent", "claude-hook", "claude-script", "codex-agents-block", "codex-hook",
                     "codex-inline-hook"]
    (script,) = [a for a in found if a.kind == "claude-script"]
    assert script.path.name == "codebase-memory-coverage.sh"  # the session script is run by a hook: not stray
    assert {a.kind for a in found if not a.removable} == {"codex-inline-hook", "claude-agent"}  # the agent: by name
    assert {a.agent for a in found if a.kind.startswith("codex")} == {"codex"}


def test_the_agents_block_is_removed_exactly_between_markers(machine):
    path = paths.codex_home() / "AGENTS.md"
    _w(path, BEFORE + BLOCK + AFTER)
    original = path.read_bytes()
    (a,) = [a for a in cbm_installer.find() if a.kind == "codex-agents-block"]
    assert a.removable
    bk = backup.Backup(description="adopt")
    line = cbm_installer.remove(a, bk)
    assert SECRET not in line
    assert path.read_bytes() == (BEFORE + AFTER[2:]).encode()  # the block and one following CRLF, nothing else
    lines, ok, _ = backup.restore(bk.root)
    assert ok, lines
    assert path.read_bytes() == original


def test_an_unclosed_block_is_left_alone(machine):
    path = paths.codex_home() / "AGENTS.md"
    for text in (BEFORE + START + "\r\nno end\r\n", BEFORE + BLOCK + AFTER + BLOCK):
        _w(path, text)
        (a,) = [a for a in cbm_installer.find() if a.kind == "codex-agents-block"]
        assert not a.removable
        with pytest.raises(ValueError):
            cbm_installer.remove(a, backup.Backup(description="t"))
        assert not [i for i in inventory.collect(with_versions=False) if i.kind == "installer"]
        assert path.read_bytes() == text.encode()


def test_a_codex_echo_hook_is_found_and_removed_with_a_backup(machine):
    path = paths.codex_home() / "hooks.json"
    _w(path, ECHO)
    original = path.read_bytes()
    (a,) = [a for a in cbm_installer.find() if a.kind == "codex-hook"]
    assert a.removable and a.path == path
    bk = backup.Backup(description="adopt")
    line = cbm_installer.remove(a, bk)
    assert SECRET not in line and "hooks.json" in line
    kept = {"hooks": {"PreToolUse": ECHO["hooks"]["PreToolUse"]}}
    assert path.read_bytes() == json.dumps(kept, indent=2).encode()  # the file's own style, the empty event gone
    lines, ok, _ = backup.restore(bk.root)
    assert ok, lines
    assert path.read_bytes() == original
    _w(path, json.dumps(ECHO, indent=3))  # a layout loadout cannot reproduce byte for byte
    (a,) = [a for a in cbm_installer.find() if a.kind == "codex-hook"]
    assert not a.removable


def test_loadouts_own_codex_hooks_are_never_artefacts(machine):
    group = {"hooks": [{"type": "command", "command": "codebase-memory-mcp hook-session"}]}
    _w(paths.codex_home() / "hooks.json", {"hooks": {"SessionStart": [group]}})
    record = codex.record_path()
    record.parent.mkdir(parents=True, exist_ok=True)
    save_json(record, {"hooks": [{"event": "SessionStart", "group": json.dumps(group, sort_keys=True)}]})
    assert not [a for a in cbm_installer.find() if a.kind == "codex-hook"]


def test_an_inline_config_hook_is_named_not_removable(machine):
    _w(paths.codex_home() / "config.toml", PLUGIN_ON + INLINE)
    (a,) = [a for a in cbm_installer.find() if a.kind == "codex-inline-hook"]
    assert not a.removable and a.path == paths.codex_home() / "config.toml"
    with pytest.raises(ValueError):
        cbm_installer.remove(a, backup.Backup(description="t"))
    (row,) = [r for r in check.run_checks() if r.name == "codebase-memory installer"]
    assert row.fix == "remove it from config.toml by hand"


def test_an_agent_that_is_off_is_not_read(machine, monkeypatch):
    _everything(machine)

    def never():
        raise AssertionError("read an agent's files while it is off")
    targets.set_agents({"claude": True, "codex": False})
    with monkeypatch.context() as m:
        m.setattr(paths, "codex_home", never)
        assert {a.agent for a in cbm_installer.find()} == {"claude"}
    targets.set_agents({"claude": False, "codex": True})
    with monkeypatch.context() as m:
        m.setattr(paths, "claude_home", never)
        m.setattr(duplicates, "plugin_enabled", never)
        assert {a.agent for a in cbm_installer.find()} == {"codex"}


def test_the_plugin_off_finds_nothing(machine, monkeypatch):
    _everything(machine)
    monkeypatch.setattr(duplicates, "plugin_enabled", lambda: False)
    _w(paths.codex_home() / "config.toml", '[plugins."loadout@agent-loadout"]\nenabled = false\n' + INLINE)
    assert cbm_installer.find() == []


def test_check_names_each_artefact_without_content(machine, monkeypatch):
    _everything(machine)
    monkeypatch.setattr(codex, "checks", lambda: [])
    rows = [r for r in check.run_checks() if r.name == "codebase-memory installer"]
    assert len(rows) == 6
    for a, row in zip(cbm_installer.find(), rows):
        assert not row.ok and row.severity == "warn"
        assert row.detail.startswith(f"{a.label} (") and a.path.name in row.detail
        assert row.detail.split(": doubles loadout's ")[1] in ("routing", "project pointer", "hooks")
        assert SECRET not in row.detail + row.fix
        assert row.fix == ("loadout adopt" if a.removable else a.fix) and (a.removable or a.fix != "loadout adopt")


def test_adopt_offers_and_removes_with_a_yes_only(machine, capsys):
    _everything(machine)
    before = {p: p.read_bytes() for p in machine.rglob("*") if p.is_file() and "loadout" not in p.parts}
    items = [i for i in inventory.collect(with_versions=False) if i.kind == "installer"]
    assert sorted(i.detail for i in items) == ["claude-script", "codex-agents-block", "codex-hook"]  # not the agent
    verdicts = [v for v in inventory.classify(items)]
    assert {(v.action, v.entry_id, v.reason) for v in verdicts} == {
        ("migrate", "mcp-codebase-memory", "Written by codebase-memory-mcp install; loadout's plugin provides the same.")}
    assert adopt.run(False, None, set(), False, lambda q: "", with_versions=False, interactive=False) == 0
    assert {p: p.read_bytes() for p in before} == before  # a dry run changes nothing
    capsys.readouterr()
    assert adopt.run(True, {"migrate"}, set(), False, lambda q: "", with_versions=False, interactive=False) == 0
    assert SECRET not in capsys.readouterr().out
    assert (machine / ".claude/agents/codebase-memory.md").exists()  # named by its file name only: never removed
    assert not (machine / ".claude/hooks/codebase-memory-coverage.sh").exists()
    assert (paths.codex_home() / "AGENTS.md").read_bytes() == (BEFORE + AFTER[2:]).encode()
    assert "SessionStart" not in json.loads((paths.codex_home() / "hooks.json").read_text())["hooks"]
    assert "hooks" not in json.loads((machine / ".claude/settings.json").read_text())  # the Claude hook: migrate too
    assert (paths.codex_home() / "config.toml").read_text() == PLUGIN_ON + INLINE  # inline: named only
    assert [a.kind for a in cbm_installer.find()] == ["claude-script", "claude-agent", "codex-inline-hook"]  # the session script, now stray


def test_update_leaves_the_installers_new_scripts_alone(machine):
    hooks = {"hooks": {"SessionStart": [{"hooks": [
        {"type": "command", "command": "~/.claude/hooks/codebase-memory-session.sh"}]}]}}
    _w(machine / ".claude/settings.json", hooks)
    _w(machine / ".claude/hooks/codebase-memory-session.sh", "#!/bin/sh\n")
    _w(machine / ".claude/hooks/codebase-memory-coverage.sh", "#!/bin/sh\n")
    removed, reported = maintenance.undo_reregistered(backup.Backup(description="t"))
    assert removed == [] and reported == []
    assert json.loads((machine / ".claude/settings.json").read_text()) == hooks
    assert (machine / ".claude/hooks/codebase-memory-session.sh").exists()
    assert (machine / ".claude/hooks/codebase-memory-coverage.sh").exists()
    assert not set(cbm_installer.NEW_SCRIPTS) & {s + ".sh" for s in duplicates.LEGACY_SCRIPTS}


# --- fix round 1


def _hook_settings(home, *commands):
    _w(home / ".claude/settings.json", {"hooks": {"SessionStart": [{"hooks": [
        {"type": "command", "command": c} for c in commands]}]}})


def _installer_rows():
    return [r for r in check.run_checks() if r.name == "codebase-memory installer"]


def test_a_hook_augment_hook_gets_one_row(machine, monkeypatch):
    monkeypatch.setattr(codex, "checks", lambda: [])
    _w(machine / ".claude/settings.json", {"hooks": {"PreToolUse": [{"matcher": "Grep", "hooks": [
        {"type": "command", "command": "codebase-memory-mcp hook-augment"}]}]}})
    rows = [r for r in check.run_checks() if not r.ok and "codebase-memory" in r.name and "hook" in r.detail]
    assert [r.name for r in rows] == ["codebase-memory hooks"]


def test_a_left_artefact_gets_no_row(machine, monkeypatch):
    from loadout import own
    monkeypatch.setattr(codex, "checks", lambda: [])
    _w(machine / ".claude/agents/codebase-memory.md", "x\n")
    _hook_settings(machine, "~/.claude/hooks/codebase-memory-session.sh")
    assert len(_installer_rows()) == 2
    for a in cbm_installer.find():
        own.remember_leave(cbm_installer.adopt_item(a))
    assert _installer_rows() == []
    assert {v.action for v in inventory.classify(inventory.collect(with_versions=False))
            if v.item.kind == "installer" or "codebase-memory-session" in str(v.item.detail)} == {"keep"}


def test_only_the_installers_script_path_is_offered(machine):
    home = str(machine)
    offered = [f"~/.claude/hooks/codebase-memory-session.sh", f"$HOME/.claude/hooks/codebase-memory-coverage.sh",
               f"{home}/.claude/hooks/codebase-memory-session.sh"]
    others = ["/opt/other/codebase-memory-session.sh", "echo codebase-memory-session.sh",
              'echo "run ~/.claude/hooks/codebase-memory-coverage.sh"']
    _hook_settings(machine, *offered, *others)
    verdicts = {v.item.detail: v.action for v in inventory.classify(inventory.collect(with_versions=False))
                if v.item.kind == "hook"}
    assert {c: verdicts[c] for c in offered} == {c: "migrate" for c in offered}
    assert all(verdicts[c] != "migrate" for c in others), verdicts
    assert len([a for a in cbm_installer.find() if a.kind == "claude-hook"]) == len(offered)


def test_a_hooks_file_that_changed_shape_is_not_done(machine):
    path = paths.codex_home() / "hooks.json"
    for broken in ("[]", None, '{"hooks": []}'):
        _w(path, ECHO)
        (item,) = [i for i in inventory.collect(with_versions=False) if i.detail == "codex-hook"]
        if broken is None:
            path.unlink()
        else:
            _w(path, broken)
        verdict = inventory.Verdict(item, "migrate", inventory.INSTALLER_REASON, "mcp-codebase-memory")
        not_done = []
        (line,) = adopt.apply([verdict], backup.Backup(description="t"), not_done=not_done)
        assert isinstance(line, adopt.NotDone) and not_done == [item]


@pytest.mark.parametrize("text, expected", [
    ("# Mine\n\n" + START + "\nx\n" + END + "\n\nafter\n", "# Mine\n\n\nafter\n"),  # LF only
    ("# Mine\r\n" + START + "\r\nx\r\n" + END, "# Mine\r\n"),                       # the block ends the file
    (START + "\nx\n" + END, ""),
])
def test_the_block_is_cut_exactly_in_other_shapes(machine, text, expected):
    path = paths.codex_home() / "AGENTS.md"
    _w(path, text)
    (a,) = [a for a in cbm_installer.find() if a.kind == "codex-agents-block"]
    cbm_installer.remove(a, backup.Backup(description="t"))
    assert path.read_bytes() == expected.encode()


@pytest.mark.parametrize("command, runs", [
    ("codebase-memory-mcp hook-augment", True), ("cd /x && codebase-memory-mcp hook-augment", True),
    ("env A=1 codebase-memory-mcp hook-augment", True),
    ("echo see codebase-memory-mcp hooks", False), ("echo Use codebase-memory-mcp tools", False),
    ("printf '%s' codebase-memory-mcp", False), ("tool --server codebase-memory-mcp hook-augment", False)])
def test_only_a_command_word_runs_codebase_memory(command, runs):
    from loadout import cbm_installer
    from loadout.duplicates import _split
    assert cbm_installer.claude_hook_words(_split(command)) is runs


def test_a_users_own_cbm_cli_hook_in_codex_is_not_the_installers():
    from loadout import cbm_installer
    assert not cbm_installer._is_cbm_hook({"type": "command",
                                           "command": "codebase-memory-mcp cli index_repository --repo-path ."})
    assert cbm_installer._is_cbm_hook({"type": "command", "command": "codebase-memory-mcp hook-augment"})


def test_the_guard_and_loadout_agree_on_command_positions():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins" / "loadout" / "hooks"))
    import mcp_guard
    from loadout import duplicates
    for line in ("a b", "cd x && a", "env A=1 a", "echo a", "x --y a", "A=1 a", "exec a", "a | b"):
        words = line.split()
        for i in range(len(words)):
            assert mcp_guard._at_command(words, i) == duplicates.at_command(words, i), (line, i)


def test_a_script_a_codex_hook_still_runs_is_not_removable(fake_home, monkeypatch):
    from loadout import cbm_installer, targets
    monkeypatch.setattr(targets, "OVERRIDE", {"claude": True, "codex": True})
    monkeypatch.setattr(cbm_installer, "_claude_plugin_on", lambda: True)
    hooks = fake_home / ".claude" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "codebase-memory-session.sh").write_text("#!/bin/sh\n")
    (fake_home / ".codex").mkdir()
    (fake_home / ".codex" / "config.toml").write_text(
        '[[hooks.SessionStart]]\n[[hooks.SessionStart.hooks]]\ntype = "command"\n'
        f'command = "{hooks / "codebase-memory-session.sh"}"\n')
    scripts = [a for a in cbm_installer.find() if a.kind == "claude-script"]
    assert all(not a.removable for a in scripts)


def test_no_claude_artefacts_while_the_plugin_is_not_installed(fake_home, monkeypatch):
    import json as _json
    from loadout import cbm_installer, duplicates, targets
    monkeypatch.setattr(targets, "OVERRIDE", {"claude": True, "codex": False})
    monkeypatch.setattr(duplicates, "plugin_enabled", lambda: True)  # wanted by the kit's settings...
    (fake_home / ".claude" / "agents").mkdir(parents=True)
    (fake_home / ".claude" / "agents" / "codebase-memory.md").write_text("x\n")
    assert not cbm_installer._claude_plugin_on()  # ...but not installed
    plugins = fake_home / ".claude" / "plugins"
    plugins.mkdir(parents=True)
    (plugins / "installed_plugins.json").write_text(_json.dumps(
        {"plugins": {"loadout@agent-loadout": [{"scope": "user", "version": "1"}]}}))
    assert cbm_installer._claude_plugin_on()


def test_the_agent_file_is_named_never_removable(fake_home, monkeypatch):
    from loadout import cbm_installer, targets
    monkeypatch.setattr(targets, "OVERRIDE", {"claude": True, "codex": False})
    monkeypatch.setattr(cbm_installer, "_claude_plugin_on", lambda: True)
    (fake_home / ".claude" / "agents").mkdir(parents=True)
    (fake_home / ".claude" / "agents" / "codebase-memory.md").write_text("my own agent\n")
    (agent,) = [a for a in cbm_installer.find() if a.kind == "claude-agent"]
    assert not agent.removable
