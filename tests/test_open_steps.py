"""\"Now do this\": the steps a person still has to do, per agent, shown at that agent's next session until done."""
import json

import pytest

from loadout import codex, maintenance as m, paths, runner, steps, targets
from loadout.__main__ import main


@pytest.fixture(autouse=True)
def quiet(fake_home, monkeypatch):
    monkeypatch.setattr(m, "_spawn_background", lambda: None)
    monkeypatch.setattr(codex, "refresh_instructions", lambda: None)
    monkeypatch.setattr(steps, "_plugin_copy_differs", lambda: False)
    monkeypatch.setattr(codex, "hooks_status", lambda remember=False: "trusted")
    monkeypatch.setattr(runner, "have", lambda binary: True)  # the Codex CLI is on PATH unless a test says not
    targets.set_agents({"claude": True, "codex": True})


def _ids(found):
    return [s.id for s in found]


def _write_mcp(path, servers):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"mcpServers": servers}), encoding="utf-8")


def test_an_upgraded_mcp_binary_gives_a_reconnect_step(monkeypatch, tmp_path):
    monkeypatch.setenv("LOADOUT_ROOT", str(tmp_path))
    _write_mcp(tmp_path / "plugins" / "loadout" / ".mcp.json",
               {"serena": {"command": "serena"}, "codebase-memory-mcp": {"command": "codebase-memory-mcp"}})
    monkeypatch.setattr(steps, "_claude_wants_plugin", lambda: True)
    assert steps.mcp_servers_started_by("serena")["claude"] == ["plugin:loadout:serena"]
    found = steps.derive(set(), ["serena"], True, True)
    assert "claude/mcp:plugin:loadout:serena" in _ids(found)
    assert "codex/restart" in _ids(found)
    text = next(s.text for s in found if s.id.startswith("claude/mcp:"))
    assert text == "run /mcp and reconnect plugin:loadout:serena (it was upgraded)"


def test_a_personal_and_a_uvx_server_match_by_command(monkeypatch, tmp_path):
    monkeypatch.setenv("LOADOUT_ROOT", str(tmp_path))
    _write_mcp(paths.personal_root() / "mcp.json",
               {"mine": {"command": "/home/x/.local/bin/serena.exe"},
                "viauv": {"command": "uvx", "args": ["--from", "git+https://github.com/oraios/serena", "start-mcp-server"]},
                "other": {"command": "node"}})
    got = steps.mcp_servers_started_by("serena")
    assert sorted(got["claude"]) == ["mine", "viauv"]


def test_plugin_changes_give_reload_and_hooks_steps():
    found = steps.derive({"claude_plugins_updated", "codex_plugins_installed"}, [], True, True)
    assert "claude/reload-plugins" in _ids(found) and "codex/restart" in _ids(found)  # hooks are approved
    assert next(s.text for s in found if s.id == "codex/restart") == "restart Codex (it loads plugins per session)"
    assert steps.derive({"serena_hooks_added"}, [], True, True)[0].id == "codex/hooks"


def test_codex_plugin_changes_name_the_hooks_when_they_are_not_approved(monkeypatch):
    monkeypatch.setattr(codex, "hooks_status", lambda remember=False: "changed")
    found = steps.derive({"codex_plugins_updated"}, [], False, True)
    assert _ids(found) == ["codex/hooks"]
    assert found[0].text == "restart Codex and approve the changed hooks in /hooks"


def test_unapproved_or_changed_codex_hooks_give_the_hooks_step(monkeypatch):
    assert steps.derive(set(), [], True, True) == []
    monkeypatch.setattr(codex, "hooks_status", lambda remember=False: "changed")
    found = steps.derive(set(), [], True, True)
    assert _ids(found) == ["codex/hooks"] and "/hooks" in found[0].text


def test_a_plugin_copy_that_differs_gives_the_reload_step(monkeypatch):
    monkeypatch.setattr(steps, "_plugin_copy_differs", lambda: True)
    assert _ids(steps.derive(set(), [], True, False)) == ["claude/reload-plugins"]


def test_steps_of_an_agent_that_is_off_are_never_shown(monkeypatch):
    found = steps.derive({"claude_plugins_updated", "codex_plugins_updated"}, [], True, False)
    assert _ids(found) == ["claude/reload-plugins"]
    steps.save([steps.Step("claude/reload-plugins", "claude", "run /reload-plugins", "x"),
                steps.Step("codex/restart", "codex", "restart Codex", "x")])
    targets.set_agents({"claude": False, "codex": True})
    assert steps.render(steps.pending("claude") + steps.pending("codex"), False, True) == [
        "1. Codex: restart Codex"]
    assert m.session_start(0.0, "claude", source="startup") is None
    assert _ids(steps.pending("claude")) == ["claude/reload-plugins"]  # not shown, not cleared
    assert m.session_start(0.0, "codex") is None  # the Codex start is the restart: cleared, not shown
    assert steps.pending("codex") == []


def test_bootstrap_only_needs_name_bootstrap(monkeypatch):
    from loadout.check import CheckResult
    rows = [CheckResult("secrets.env", False, "missing", "loadout bootstrap", "warn"),
            CheckResult("gh auth", False)]
    found = steps.derive(set(), [], True, True, results=rows)
    assert _ids(found) == ["claude/bootstrap", "codex/bootstrap"]
    assert found[0].text == "run loadout bootstrap"


def test_claude_steps_clear_only_at_a_fresh_start():
    steps.save([steps.Step("claude/reload-plugins", "claude", "run /reload-plugins", "plugins updated")])
    shown = json.loads(m.session_start(0.0, "claude", source="resume"))["systemMessage"]
    assert "Now do this" in shown and "run /reload-plugins" in shown
    assert _ids(steps.pending("claude")) == ["claude/reload-plugins"]
    for source in ("clear", "compact", None):
        assert m.session_start(0.0, "claude", source=source) is not None
    assert _ids(steps.pending("claude")) == ["claude/reload-plugins"]
    # a fresh start loaded the new plugins: cleared without telling this session to reload them
    assert m.session_start(0.0, "claude", source="startup") is None
    assert steps.pending("claude") == []


def test_a_fresh_start_shows_only_the_steps_it_does_not_settle():
    steps.save([steps.Step("claude/reload-plugins", "claude", "run /reload-plugins", "x"),
                steps.Step("claude/mcp:serena", "claude", "run /mcp and reconnect serena", "x"),
                _bootstrap_step("claude")])
    shown = json.loads(m.session_start(0.0, "claude", source="startup"))["systemMessage"]
    assert "run loadout bootstrap" in shown and "/reload-plugins" not in shown and "/mcp" not in shown
    assert _ids(steps.pending("claude")) == ["claude/bootstrap"]
    steps.save([steps.Step("codex/restart", "codex", "restart Codex", "x")])
    assert m.session_start(0.0, "codex") is None  # this Codex session is the restart
    assert steps.pending("codex") == []


def test_codex_hooks_step_clears_when_trusted(monkeypatch):
    steps.save([steps.Step("codex/hooks", "codex", "start codex and approve the changed hooks in /hooks", "x"),
                steps.Step("codex/restart", "codex", "restart Codex", "x")])
    monkeypatch.setattr(codex, "hooks_status", lambda remember=False: "changed")
    shown = json.loads(m.session_start(0.0, "codex"))["systemMessage"]
    assert "/hooks" in shown and "restart Codex" not in shown  # this start is the restart
    assert _ids(steps.pending("codex")) == ["codex/hooks"]  # the restart step is done: a Codex session started
    monkeypatch.setattr(codex, "hooks_status", lambda remember=False: "trusted")
    assert m.session_start(0.0, "codex") is None
    assert steps.pending("codex") == []


def test_a_codex_session_does_not_see_or_clear_claude_steps():
    steps.save([steps.Step("claude/reload-plugins", "claude", "run /reload-plugins", "x")])
    assert m.session_start(0.0, "codex") is None
    assert _ids(steps.pending("claude")) == ["claude/reload-plugins"]


def test_an_old_hook_without_agent_keeps_todays_behaviour():
    steps.save([steps.Step("claude/reload-plugins", "claude", "run /reload-plugins", "x")])
    notice = paths.state_dir() / "pending-notice"
    notice.write_text("updates available")
    assert json.loads(m.session_start(0.0)) == {"systemMessage": "updates available"}
    assert _ids(steps.pending("claude")) == ["claude/reload-plugins"]


def test_save_merges_by_id_and_a_notice_comes_first(monkeypatch):
    steps.save([steps.Step("codex/restart", "codex", "restart Codex", "a")])
    steps.save([steps.Step("codex/restart", "codex", "restart Codex", "b"),
                steps.Step("codex/hooks", "codex", "approve", "c")])
    assert _ids(steps.pending("codex")) == ["codex/restart", "codex/hooks"]
    (paths.state_dir() / "pending-notice").write_text("news")
    monkeypatch.setattr(codex, "hooks_status", lambda remember=False: "changed")
    msg = json.loads(m.session_start(0.0, "codex"))["systemMessage"]
    assert msg.startswith("news") and "Now do this" in msg


def test_a_broken_steps_file_is_ignored():
    (paths.state_dir()).mkdir(parents=True, exist_ok=True)
    (paths.state_dir() / "open-steps.json").write_text("not json")
    assert steps.pending("claude") == []
    assert m.session_start(0.0, "claude", source="startup") is None


def test_the_hook_command_reads_the_source_from_stdin(monkeypatch):
    import io
    steps.save([steps.Step("claude/reload-plugins", "claude", "run /reload-plugins", "x")])
    for text in ("", "not json", "{}", '{"source": "resume"}', '[1]'):
        monkeypatch.setattr("sys.stdin", io.StringIO(text))
        assert main(["hook-session-start", "--agent", "claude"]) == 0
    assert _ids(steps.pending("claude")) == ["claude/reload-plugins"]
    monkeypatch.setattr("sys.stdin", io.StringIO('{"source": "startup"}'))
    assert main(["hook-session-start", "--agent", "claude"]) == 0
    assert steps.pending("claude") == []


def test_render_numbers_across_agents_and_skips_agents_that_are_off():
    both = [steps.Step("claude/reload-plugins", "claude", "run /reload-plugins", "x"),
            steps.Step("codex/restart", "codex", "restart Codex", "x")]
    assert steps.render(both, True, True) == ["1. Claude Code: run /reload-plugins", "2. Codex: restart Codex"]
    assert steps.render(both, False, True) == ["1. Codex: restart Codex"]


def _bootstrap_step(agent):
    return steps.Step(f"{agent}/bootstrap", agent, "run loadout bootstrap", "secrets.env: loadout bootstrap")


def test_a_bootstrap_step_clears_when_its_rows_pass_for_both_agents():
    steps.save([_bootstrap_step("claude"), _bootstrap_step("codex")])
    assert not paths.secrets_file().exists()
    assert "Now do this" in json.loads(m.session_start(0.0, "claude", source="startup"))["systemMessage"]
    assert "run loadout bootstrap" in json.loads(m.session_start(0.0, "codex"))["systemMessage"]
    assert _ids(steps.pending("claude")) == ["claude/bootstrap"] and _ids(steps.pending("codex")) == ["codex/bootstrap"]
    paths.secrets_file().parent.mkdir(parents=True, exist_ok=True)
    paths.secrets_file().write_text("X=1\n")
    paths.secrets_file().chmod(0o600)
    assert m.session_start(0.0, "codex") is None
    assert steps.pending("codex") == [] and steps.pending("claude") == []  # the rows pass for both
    assert m.session_start(0.0, "claude", source="startup") is None


def test_derive_names_the_rows_in_the_bootstrap_reason():
    from loadout.check import CheckResult
    found = steps.derive(set(), [], True, False, results=[CheckResult("secrets.env", False, "x", "loadout bootstrap")])
    assert "secrets.env" in found[0].reason


def test_settle_drops_stale_steps(monkeypatch, tmp_path):
    monkeypatch.setenv("LOADOUT_ROOT", str(tmp_path))
    _write_mcp(tmp_path / "plugins" / "loadout" / ".mcp.json", {"serena": {"command": "serena"}})
    monkeypatch.setattr(steps, "_claude_wants_plugin", lambda: True)
    steps.save([steps.Step("claude/mcp:plugin:loadout:serena", "claude", "a", "x"),
                steps.Step("claude/mcp:gone", "claude", "b", "x"),
                steps.Step("codex/hooks", "codex", "approve", "x"),
                steps.Step("claude/reload-plugins", "claude", "reload", "x")])
    steps.settle(True, True)
    assert _ids(steps.pending("claude")) == ["claude/mcp:plugin:loadout:serena", "claude/reload-plugins"]
    assert steps.pending("codex") == []  # hooks are trusted
    targets.set_agents({"claude": False, "codex": True})
    steps.settle(False, True)
    assert steps.pending("claude") == []


def test_matching_strips_shim_extensions_and_wants_a_whole_segment():
    assert steps._starts({"command": "C:\\x\\serena.cmd"}, "serena")
    assert steps._starts({"command": "serena.BAT"}, "serena")
    assert steps._starts({"command": "uvx", "args": ["--from", "git+https://github.com/oraios/serena.git"]}, "serena")
    assert not steps._starts({"command": "uvx", "args": ["serena-agent"]}, "serena")
    assert not steps._starts({"command": "uv", "args": ["run", "myserenaish"]}, "serena")


def test_check_ends_with_pending_codex_steps(monkeypatch, capsys):
    from loadout import check
    monkeypatch.setattr(check, "run_checks", lambda *a, **k: [])
    steps.save([steps.Step("codex/hooks", "codex", "start codex and approve the changed hooks in /hooks", "x")])
    monkeypatch.setattr(codex, "hooks_status", lambda remember=False: "changed")
    main(["check"])
    assert "Now do this" in capsys.readouterr().out


def test_without_the_codex_cli_there_is_no_restart_step_and_the_hooks_step_says_how(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "have", lambda binary: binary != "codex")  # VS Code's Codex extension only
    monkeypatch.setenv("LOADOUT_ROOT", str(tmp_path))
    _write_mcp(tmp_path / "plugins" / "loadout" / ".mcp.json", {"serena": {"command": "serena"}})
    assert "codex/restart" not in _ids(steps.derive({"codex_plugins_updated"}, ["serena"], False, True))
    monkeypatch.setattr(codex, "hooks_status", lambda remember=False: "changed")
    found = steps.derive({"serena_hooks_added"}, [], False, True)
    assert [(s.id, s.text) for s in found] == [("codex/hooks", codex.HOOKS_NO_CLI)]
    steps.save([steps.Step("codex/restart", "codex", "restart Codex", "x")])  # saved while the CLI was there
    steps.settle(False, True)
    assert "codex/restart" not in _ids(steps.pending("codex"))


def test_a_server_name_cannot_forge_a_step_line(fake_home, fake_runner, monkeypatch):
    from loadout import steps
    evil = "x\n1. fake\x1b[31m"
    monkeypatch.setattr(steps, "mcp_servers_started_by", lambda b: {"claude": [evil], "codex": []})
    made = steps.derive(set(), ["serena"], True, False)
    texts = [s.text for s in made]
    assert texts and all("\n" not in t and "\x1b" not in t for t in texts)
    saved = steps.Step("claude/mcp:x", "claude", f"run /mcp and reconnect {evil}", "why")  # saved before the fix
    lines = steps.render([saved], True, False)
    assert len(lines) == 1 and "\x1b" not in lines[0] and "\n" not in lines[0]
