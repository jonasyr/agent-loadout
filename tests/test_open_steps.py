"""\"Now do this\": the steps a person still has to do, per agent, shown at that agent's next session until done."""
import json

import pytest

from loadout import codex, maintenance as m, paths, steps, targets
from loadout.__main__ import main


@pytest.fixture(autouse=True)
def quiet(fake_home, monkeypatch):
    monkeypatch.setattr(m, "_spawn_background", lambda: None)
    monkeypatch.setattr(codex, "refresh_instructions", lambda: None)
    monkeypatch.setattr(steps, "_plugin_copy_differs", lambda: False)
    monkeypatch.setattr(codex, "hooks_status", lambda remember=False: "trusted")
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
    assert "claude/reload-plugins" in _ids(found) and "codex/hooks" in _ids(found)
    assert steps.derive({"serena_hooks_added"}, [], True, True)[0].id == "codex/hooks"


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
    assert "restart Codex" in json.loads(m.session_start(0.0, "codex"))["systemMessage"]


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
    assert m.session_start(0.0, "claude", source="startup") is not None  # shown one last time, then cleared
    assert steps.pending("claude") == []
    assert m.session_start(0.0, "claude", source="startup") is None


def test_codex_hooks_step_clears_when_trusted(monkeypatch):
    steps.save([steps.Step("codex/hooks", "codex", "start codex and approve the changed hooks in /hooks", "x"),
                steps.Step("codex/restart", "codex", "restart Codex", "x")])
    monkeypatch.setattr(codex, "hooks_status", lambda remember=False: "changed")
    shown = json.loads(m.session_start(0.0, "codex"))["systemMessage"]
    assert "/hooks" in shown and "restart Codex" in shown
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


def test_save_merges_by_id_and_a_notice_comes_first():
    steps.save([steps.Step("codex/restart", "codex", "restart Codex", "a")])
    steps.save([steps.Step("codex/restart", "codex", "restart Codex", "b"),
                steps.Step("codex/hooks", "codex", "approve", "c")])
    assert _ids(steps.pending("codex")) == ["codex/restart", "codex/hooks"]
    (paths.state_dir() / "pending-notice").write_text("news")
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
