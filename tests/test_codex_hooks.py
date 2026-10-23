"""The plugin's Codex hooks: every Claude hook has a Codex counterpart or a stated reason; the type check."""
import io
import json
import os
import sys

import pytest
from pathlib import Path

from loadout import paths

PLUGIN = paths.kit_root() / "plugins" / "loadout"
sys.path.insert(0, str(PLUGIN / "hooks"))
import typecheck  # noqa: E402

# Claude hooks with no Codex counterpart, and why
OMITTED = {
    "codebase-memory-mcp hook-augment": "Codex has no Grep/Glob tools to augment",
    "tool_hint.sh": "Codex has its own entries with other matchers (shell only), checked in test_tool_hint_wiring.py",
    "reload_check.py":"compares Claude's installed_plugins.json; Codex loads plugins per session",
    "serena-hooks": "Codex gets Serena's documented hooks in ~/.codex/hooks.json (ADR 0028), never from the plugin",
}
# Claude events with no Codex counterpart, and why
OMITTED_EVENTS = {"SubagentStop": "Codex refreshes codebase-memory at Stop only; a subagent's edits wait for the "
                                  "parent's Stop (or the 20-file limit)"}
CODEX_ARGS = {"--client=claude-code": "--client=codex", "rtk hook claude": "rtk hook codex",
              "--agent claude": "--agent codex", 'subagent-context.sh" claude': 'subagent-context.sh" codex',
              "mcp__plugin_loadout_serena__": "mcp__serena__", "Write|Edit|MultiEdit": "Edit|Write"}


def _commands(path):
    hooks = json.loads(path.read_text(encoding="utf-8"))["hooks"]
    return {(event, g.get("matcher", ""), h["command"]) for event, groups in hooks.items() for g in groups for h in g["hooks"]}


def _codexify(text):
    for a, b in CODEX_ARGS.items():
        text = text.replace(a, b)
    return text


def test_manifest_points_codex_to_its_hooks():
    manifest = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "loadout" and manifest["hooks"] == "./hooks/codex.json"


def test_every_claude_hook_has_a_codex_counterpart_or_a_reason():
    codex_hooks = _commands(PLUGIN / "hooks" / "codex.json")
    for event, matcher, command in _commands(PLUGIN / "hooks" / "hooks.json"):
        if any(key in command for key in OMITTED) or event in OMITTED_EVENTS:
            continue
        assert (event, _codexify(matcher), _codexify(command)) in codex_hooks, (event, matcher, command)
    assert not any("--client=claude-code" in c or "rtk hook claude" in c for _, _, c in codex_hooks)


def test_codex_hooks_add_the_type_check_after_edits():
    assert any(e == "PostToolUse" and m == "Edit|Write" and "typecheck.py" in c
               for e, m, c in _commands(PLUGIN / "hooks" / "codex.json"))


def test_changed_files_from_apply_patch_and_claude_edits(tmp_path):
    patch = "*** Begin Patch\n*** Update File: src/a.py\n@@\n-x\n+y\n*** Add File: b.ts\n+z\n*** End Patch\n"
    event = {"cwd": str(tmp_path), "tool_name": "apply_patch", "tool_input": {"command": patch}}
    assert typecheck.changed_files(event) == [tmp_path / "src/a.py", tmp_path / "b.ts"]
    absolute = tmp_path / "abs" / "c.rs"
    assert typecheck.changed_files({"cwd": "/elsewhere", "tool_input": {"file_path": str(absolute)}}) == [absolute]


def _fake_tool(bin_dir, name, exit_code, output):
    script = bin_dir / name
    script.write_text(f"#!/bin/sh\necho '{output}'\nexit {exit_code}\n", encoding="utf-8")
    script.chmod(0o755)


@pytest.mark.skipif(os.name == "nt", reason="fake checkers are shell scripts")
def test_errors_are_reported_and_clean_files_are_silent(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    (tmp_path / "a.py").write_text("x: int = 'no'\n")
    event = {"cwd": str(tmp_path), "tool_input": {"command": "*** Update File: a.py\n"}}
    _fake_tool(bin_dir, "pyright", 1, "a.py:1:10 - error: str is not int")
    out = io.StringIO()
    typecheck.main(io.StringIO(json.dumps(event)), out)
    reply = json.loads(out.getvalue())
    assert reply["decision"] == "block" and "str is not int" in reply["reason"]
    _fake_tool(bin_dir, "pyright", 0, "0 errors")
    out = io.StringIO()
    typecheck.main(io.StringIO(json.dumps(event)), out)
    assert out.getvalue() == ""


@pytest.mark.skipif(os.name == "nt", reason="fake checkers are shell scripts")
def test_slow_checker_is_reported_as_skipped(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    (bin_dir / "pyright").write_text("#!/bin/sh\nsleep 5\n", encoding="utf-8")
    (bin_dir / "pyright").chmod(0o755)
    monkeypatch.setattr(typecheck, "LIMIT", 0.5)
    (tmp_path / "a.py").write_text("x = 1\n")
    out = io.StringIO()
    typecheck.main(io.StringIO(json.dumps({"cwd": str(tmp_path), "tool_input": {"command": "*** Update File: a.py\n"}})), out)
    reply = json.loads(out.getvalue())
    assert "decision" not in reply and "skipped (timeout" in reply["hookSpecificOutput"]["additionalContext"]


def test_missing_checker_and_bad_input_are_silent(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))  # no checkers at all
    (tmp_path / "a.py").write_text("x = 1\n")
    out = io.StringIO()
    typecheck.main(io.StringIO(json.dumps({"cwd": str(tmp_path), "tool_input": {"command": "*** Update File: a.py\n"}})), out)
    typecheck.main(io.StringIO("not json"), out)
    assert out.getvalue() == ""


def test_checks_pick_the_project_folder(tmp_path, monkeypatch):
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "tsconfig.json").write_text("{}")
    (tmp_path / "crate" / "src").mkdir(parents=True)
    (tmp_path / "crate" / "Cargo.toml").write_text("")
    monkeypatch.setattr(typecheck, "_which", lambda name: f"/usr/bin/{name}")
    found = typecheck.checks([tmp_path / "web" / "x.ts", tmp_path / "crate" / "src" / "lib.rs"])
    assert (["/usr/bin/tsc", "--noEmit", "-p", str(tmp_path / "web")], tmp_path / "web") in found
    assert (["/usr/bin/cargo", "check", "--quiet", "--message-format=short"], tmp_path / "crate") in found


def test_codex_gets_no_serena_from_the_plugin():
    # Codex starts an active plugin's MCP servers by bare name; with the user's Serena under another name the
    # plugin's `serena` (context claude-code) would run as a second one
    manifest = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    servers = json.loads((PLUGIN / manifest["mcpServers"]).read_text(encoding="utf-8"))["mcpServers"]
    assert "serena" not in servers and "codebase-memory-mcp" in servers
    # the only Serena hook in the plugin is the guarded remind (it skips harmless searches, ADR 0040)
    text = (PLUGIN / "hooks" / "codex.json").read_text(encoding="utf-8")
    assert text.count("serena-hooks") == 1 and "--agent codex serena serena-hooks remind --client=codex" in text


def test_codex_session_start_passes_its_agent():
    commands = [c for e, _, c in _commands(PLUGIN / "hooks" / "codex.json") if e == "SessionStart"]
    assert any("hook-session-start --agent codex" in c for c in commands)


# --- Serena's remind moves from ~/.codex/hooks.json into the plugin once its Codex copy carries the guarded one

def _remind_hooks(fake_home, fake_runner, monkeypatch):
    from loadout import codex_hooks, runner
    monkeypatch.setattr(runner, "have", lambda b: b == "serena-hooks")
    codex_hooks.path().parent.mkdir(parents=True, exist_ok=True)
    return codex_hooks.path()


def _plugin_copy(fake_home, *, remind=True, enabled=True):
    """A Codex copy of loadout@agent-loadout in the plugin cache, and config.toml switching it on (or off)."""
    hooks = json.loads((PLUGIN / "hooks" / "codex.json").read_text(encoding="utf-8"))
    if not remind:
        hooks["hooks"]["PreToolUse"] = [g for g in hooks["hooks"]["PreToolUse"]
                                        if not any("serena-hooks remind" in h["command"] for h in g["hooks"])]
    copy = fake_home / ".codex" / "plugins" / "cache" / "agent-loadout" / "loadout" / "local" / "hooks"
    copy.mkdir(parents=True, exist_ok=True)
    (copy / "codex.json").write_text(json.dumps(hooks, indent=2), encoding="utf-8")
    (fake_home / ".codex" / "config.toml").write_text(
        f'[plugins."loadout@agent-loadout"]\nenabled = {"true" if enabled else "false"}\n', encoding="utf-8")


def _subs(p):
    data = json.loads(p.read_text(encoding="utf-8"))["hooks"]
    return sorted(h["command"].split()[1] for groups in data.values() for g in groups for h in g["hooks"])


SIX = sorted(["remind", "plan-guard", "reset", "activate", "plan-context", "cleanup"])


def test_remind_leaves_hooks_json_when_the_plugin_runs_it(fake_home, fake_runner, monkeypatch):
    from loadout import backup, codex, codex_hooks
    p = _remind_hooks(fake_home, fake_runner, monkeypatch)
    codex_hooks.apply(backup.Backup(description="t"))
    assert _subs(p) == SIX
    six = p.read_bytes()
    _plugin_copy(fake_home)
    assert codex.plugin_runs_remind()
    bk = backup.Backup(description="t")
    assert codex_hooks.apply(bk)
    assert _subs(p) == sorted(s for s in SIX if s != "remind")
    assert not any("remind" in o["group"] for o in codex.read_record().get("hooks", []))
    assert codex_hooks.apply(backup.Backup(description="t")) == []  # done: a second run changes nothing
    backup.restore(bk.root)  # the removal was backed up
    assert p.read_bytes() == six


def test_old_plugin_copy_keeps_remind_in_hooks_json(fake_home, fake_runner, monkeypatch):
    from loadout import backup, codex, codex_hooks
    p = _remind_hooks(fake_home, fake_runner, monkeypatch)
    codex_hooks.apply(backup.Backup(description="t"))
    six = p.read_bytes()
    _plugin_copy(fake_home, remind=False)
    assert not codex.plugin_runs_remind()
    assert codex_hooks.apply(backup.Backup(description="t")) == []
    assert p.read_bytes() == six


def test_switched_off_plugin_keeps_remind(fake_home, fake_runner, monkeypatch):
    from loadout import backup, codex, codex_hooks
    p = _remind_hooks(fake_home, fake_runner, monkeypatch)
    codex_hooks.apply(backup.Backup(description="t"))
    six = p.read_bytes()
    _plugin_copy(fake_home, enabled=False)
    assert not codex.plugin_runs_remind()
    assert codex_hooks.apply(backup.Backup(description="t")) == []
    assert p.read_bytes() == six
    _plugin_copy(fake_home)  # switched on: remind moves to the plugin
    codex_hooks.apply(backup.Backup(description="t"))
    assert "remind" not in _subs(p)
    _plugin_copy(fake_home, enabled=False)  # switched off again: remind comes back to hooks.json
    codex_hooks.apply(backup.Backup(description="t"))
    assert _subs(p) == SIX


def test_background_sync_keeps_remind(fake_home, fake_runner, monkeypatch):
    from loadout import backup, codex, codex_hooks
    p = _remind_hooks(fake_home, fake_runner, monkeypatch)
    codex_hooks.apply(backup.Backup(description="t"))
    six = p.read_bytes()
    _plugin_copy(fake_home)
    assert codex.plugin_runs_remind()
    assert codex_hooks.apply(backup.Backup(description="t"), keep=True) == []
    assert p.read_bytes() == six


def test_users_own_remind_stays(fake_home, fake_runner, monkeypatch):
    from loadout import backup, codex_hooks
    p = _remind_hooks(fake_home, fake_runner, monkeypatch)
    codex_hooks.apply(backup.Backup(description="t"))
    codex_hooks.paths.state_dir().joinpath("codex-config.json").unlink()  # as if the user wrote them all
    users = p.read_bytes()
    _plugin_copy(fake_home)
    assert codex_hooks.apply(backup.Backup(description="t")) == []
    assert p.read_bytes() == users


def test_migration_finishes_in_one_run(fake_home, fake_runner, monkeypatch):
    from loadout import backup, codex, codex_hooks
    p = _remind_hooks(fake_home, fake_runner, monkeypatch)
    codex_hooks.apply(backup.Backup(description="t"))
    assert "remind" in _subs(p)
    monkeypatch.setattr(codex, "apply_instructions", lambda bk: "instructions up to date")
    monkeypatch.setattr(codex, "apply_config", lambda bk, dry_run=False: [])
    monkeypatch.setattr(codex, "apply_skills", lambda bk: [])
    monkeypatch.setattr(codex, "apply_plugins", lambda bk, **kw: _plugin_copy(fake_home) or ["plugin loadout: upgraded"])
    parts = codex.apply_parts(backup.Backup(description="t"), refresh=True, auto=False, keep=False)
    assert "remind" not in _subs(p) and len(_subs(p)) == 5
    assert parts["hooks"] and parts["plugins"] == ["plugin loadout: upgraded"]


def test_background_sync_does_not_add_a_moved_remind_back(fake_home, fake_runner, monkeypatch):
    from loadout import backup, codex_hooks
    p = _remind_hooks(fake_home, fake_runner, monkeypatch)
    codex_hooks.apply(backup.Backup(description="t"))
    _plugin_copy(fake_home)
    lines = codex_hooks.apply(backup.Backup(description="t"))
    assert any("plugin runs it now" in l for l in lines)
    five = p.read_bytes()
    assert codex_hooks.apply(backup.Backup(description="t"), keep=True) == []
    assert p.read_bytes() == five


def test_an_unreadable_plugin_cache_keeps_remind_and_does_not_raise(fake_home, fake_runner, monkeypatch):
    from pathlib import Path
    from loadout import backup, codex, codex_hooks
    p = _remind_hooks(fake_home, fake_runner, monkeypatch)
    codex_hooks.apply(backup.Backup(description="t"))
    _plugin_copy(fake_home)
    real = Path.is_dir

    def is_dir(self):
        if "plugins" in self.parts and "cache" in self.parts:
            raise PermissionError(13, "denied")
        return real(self)
    monkeypatch.setattr(Path, "is_dir", is_dir)
    assert codex.loadout_copy() is None and not codex.plugin_runs_remind()
    assert codex_hooks.apply(backup.Backup(description="t")) == []
    assert "remind" in _subs(p)


def test_a_moved_remind_asks_for_the_hooks_approval(fake_home, fake_runner, monkeypatch):
    from loadout import apply, backup, codex_hooks, steps, update
    p = _remind_hooks(fake_home, fake_runner, monkeypatch)
    codex_hooks.apply(backup.Backup(description="t"))
    _plugin_copy(fake_home)
    facts = apply._codex_facts(codex_hooks.apply(backup.Backup(description="t")))
    assert "serena_remind_moved" in facts and "serena_remind_moved" in update.FACT_LINES
    monkeypatch.setattr("loadout.codex.hooks_status", lambda: "trusted")
    assert any(s.id == "codex/hooks" for s in steps.derive(facts, [], False, True))


def test_adding_and_moving_in_one_run_reports_both(fake_home, fake_runner, monkeypatch):
    from loadout import backup, codex_hooks
    p = _remind_hooks(fake_home, fake_runner, monkeypatch)
    codex_hooks.apply(backup.Backup(description="t"))
    data = json.loads(p.read_text(encoding="utf-8"))  # the user removed plan-guard meanwhile: it is added again
    data["hooks"]["PreToolUse"] = [g for g in data["hooks"]["PreToolUse"] if "plan-guard" not in json.dumps(g)]
    p.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    _plugin_copy(fake_home)
    lines = codex_hooks.apply(backup.Backup(description="t"))
    assert any("added Serena's hooks" in l for l in lines) and any("plugin runs it now" in l for l in lines)


def test_every_cached_version_must_carry_the_guarded_remind(fake_home, fake_runner, monkeypatch):
    import os
    import shutil
    from loadout import backup, codex, codex_hooks
    p = _remind_hooks(fake_home, fake_runner, monkeypatch)
    codex_hooks.apply(backup.Backup(description="t"))
    _plugin_copy(fake_home)  # writes .../loadout/local and config.toml
    base = fake_home / ".codex" / "plugins" / "cache" / "agent-loadout" / "loadout"
    shutil.move(str(base / "local"), str(base / "2.0.0"))
    old = base / "1.0.0" / "hooks"
    old.mkdir(parents=True)
    (old / "codex.json").write_text('{"hooks": {"PreToolUse": []}}', encoding="utf-8")
    os.utime(base / "1.0.0", (1, 1))  # older on disk, but Codex may still load it
    assert not codex.plugin_runs_remind()
    assert "remind" in _subs(p) and codex_hooks.apply(backup.Backup(description="t")) == []
