"""The Serena pass: loadout's Serena replaces a user's own one, only with a yes, backed up (spec start-clean)."""
import json

import pytest

from loadout import adopt, cbm_installer, codex, own, paths, runner, targets
from loadout.backup import Backup
from loadout.jsonio import save_json

PLAIN = ('[mcp_servers.serena]\ncommand = "serena"\n'
         'args = ["start-mcp-server", "--project-from-cwd", "--context=codex"]\nstartup_timeout_sec = 15\n')
TUNED = '[mcp_servers.serena]\ncommand = "serena"\nargs = ["start-mcp-server", "--context=ide"]\n'
CLAUDE_PLAIN = {"type": "stdio", "command": "serena",
                "args": ["start-mcp-server", "--context=claude-code", "--project-from-cwd"]}


@pytest.fixture
def codex_on(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(targets, "OVERRIDE", {"claude": False, "codex": True})
    monkeypatch.setattr(codex, "_plugin_servers", lambda: {"codebase-memory-mcp"})
    fake_runner.responses[("codex", "--version")] = runner.Result(0, "codex-cli 0.162.1\n", "")
    return fake_runner


@pytest.fixture
def both_on(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(targets, "OVERRIDE", {"claude": True, "codex": True})
    monkeypatch.setattr(codex, "_plugin_servers", lambda: {"codebase-memory-mcp"})
    fake_runner.responses[("codex", "--version")] = runner.Result(0, "codex-cli 0.162.1\n", "")
    return fake_runner


def _config(text):
    cfg = paths.codex_home() / "config.toml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(text)
    return cfg


def _claude_json(servers):
    save_json(paths.claude_json(), {"mcpServers": servers})


def _removes(runner_):
    return [c for c in runner_.calls if c[1:3] == ["mcp", "remove"]]


def _bk():
    return Backup(description="test")


def test_flag_removes_a_plain_codex_serena_with_backup(codex_on):
    _config(PLAIN)
    bk = _bk()
    lines, texts = adopt.serena_pass(bk, lambda q: "", False, True, False)
    assert _removes(codex_on) == [[codex.program(), "mcp", "remove", "serena"]]
    assert texts == [PLAIN]
    assert any(s["label"].startswith("Codex config.toml before removing mcp serena") for s in bk.steps)
    assert any("removed" in ln for ln in lines)


@pytest.mark.parametrize("answer,removed,left", [("y", True, False), ("n", False, True), ("", False, False),
                                                 ("later", False, False)])
def test_interactive_y_removes_n_remembers_enter_does_nothing(codex_on, answer, removed, left):
    _config(PLAIN)
    asked = []
    lines, texts = adopt.serena_pass(_bk(), lambda q: asked.append(q) or answer, True, False, False)
    assert len(asked) == 1
    assert 'Codex config.toml "serena"' in asked[0] and "Use loadout's and remove yours?" in asked[0]
    assert bool(_removes(codex_on)) is removed and bool(texts) is removed
    assert ("leave" in own.decisions().values()) is left


def test_tuned_codex_serena_is_kept_under_the_flag(codex_on):
    _config(TUNED)
    lines, texts = adopt.serena_pass(_bk(), lambda q: "", False, True, False)
    assert not _removes(codex_on) and texts == []
    assert any("--own serena=remove" in ln for ln in lines)


def test_missing_serena_command_keeps_the_codex_table(codex_on):
    _config(PLAIN)
    codex_on.missing.add("serena")
    bk = _bk()
    lines, texts = adopt.serena_pass(bk, lambda q: "y", True, True, False)
    assert not _removes(codex_on) and texts == [] and bk.empty
    assert lines == ["Serena: yours kept: loadout's needs the serena command, which is missing"]


def test_leave_beats_the_flag(codex_on):
    _config(PLAIN)
    adopt.serena_pass(_bk(), lambda q: "n", True, False, False)  # remembers a leave
    codex_on.calls.clear()
    lines, texts = adopt.serena_pass(_bk(), lambda q: "y", False, True, False)
    assert lines == ["Serena: kept (you chose leave)"] and texts == []
    assert not _removes(codex_on)


def test_keep_own_does_nothing_and_stores_nothing(codex_on):
    _config(PLAIN)
    asked = []
    bk = _bk()
    assert adopt.serena_pass(bk, lambda q: asked.append(q) or "y", True, True, True) == ([], [])
    assert not asked and not codex_on.calls and bk.empty and own.decisions() == {}


def test_claude_serena_only_with_the_flag_and_the_plugin(both_on, monkeypatch):
    _claude_json({"serena": CLAUDE_PLAIN})
    monkeypatch.setattr(cbm_installer, "claude_plugin_on", lambda: False)
    lines, _ = adopt.serena_pass(_bk(), lambda q: "y", True, False, False)  # no flag: not touched
    assert lines == [] and not _removes(both_on)
    lines, _ = adopt.serena_pass(_bk(), lambda q: "", False, True, False)  # flag, no plugin
    assert lines == ["Serena: yours kept: loadout's plugin is not installed yet"] and not _removes(both_on)
    monkeypatch.setattr(cbm_installer, "claude_plugin_on", lambda: True)
    bk = _bk()
    lines, texts = adopt.serena_pass(bk, lambda q: "", False, True, False)
    assert _removes(both_on) == [["claude", "mcp", "remove", "-s", "user", "serena"]] and texts == []
    step = bk.steps[0]
    assert step["undo"]["run"][:5] == ["claude", "mcp", "add-json", "-s", "user"]
    assert json.loads(open(step["undo"]["config-file"]).read())["command"] == "serena"


def test_claude_off_reads_nothing_of_claude(codex_on, monkeypatch):
    _claude_json({"serena": CLAUDE_PLAIN})
    before = paths.claude_json().read_bytes()
    monkeypatch.setattr(cbm_installer, "claude_plugin_on", lambda: pytest.fail("read Claude's plugins"))
    lines, _ = adopt.serena_pass(_bk(), lambda q: "y", False, True, False)
    assert lines == [] and not codex_on.calls and paths.claude_json().read_bytes() == before


def test_codex_off_reads_nothing_of_codex(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(targets, "OVERRIDE", {"claude": True, "codex": False})
    cfg = _config(PLAIN)
    monkeypatch.setattr(codex, "table_source", lambda n: pytest.fail("read Codex's config"))
    monkeypatch.setattr(codex, "user_servers", lambda: pytest.fail("read Codex's config"))
    lines, texts = adopt.serena_pass(_bk(), lambda q: "y", True, True, False)
    assert (lines, texts) == ([], []) and not fake_runner.calls and cfg.read_text() == PLAIN


def test_symlinked_config_toml_is_skipped(codex_on, tmp_path):
    real = tmp_path / "dotfiles" / "config.toml"
    real.parent.mkdir()
    real.write_text(PLAIN)
    cfg = paths.codex_home() / "config.toml"
    cfg.parent.mkdir(parents=True)
    cfg.symlink_to(real)
    bk = _bk()
    lines, texts = adopt.serena_pass(bk, lambda q: "y", True, True, False)
    assert not _removes(codex_on) and texts == [] and bk.empty
    assert len(lines) == 1 and "symlink" in lines[0]


def test_inline_table_is_not_removed(codex_on):
    _config('mcp_servers.serena = { command = "serena", args = ["start-mcp-server", "--project-from-cwd", '
            '"--context=codex"] }\n')
    bk = _bk()
    lines, texts = adopt.serena_pass(bk, lambda q: "y", False, True, False)
    assert not _removes(codex_on) and texts == [] and bk.empty
    assert any("edit config.toml yourself" in ln for ln in lines)


def test_no_duplicate_no_output(codex_on):
    _config('[mcp_servers.other]\ncommand = "x"\n')
    asked = []
    assert adopt.serena_pass(_bk(), lambda q: asked.append(q) or "y", True, True, False) == ([], [])
    assert not asked and not codex_on.calls


def test_adopt_rejects_both_flags(fake_home, fake_runner, capsys):
    rc = adopt.run(True, None, set(), True, lambda q: "", with_versions=False, use_loadout=True, keep_own=True)
    assert rc == 2
    assert "--use-loadout and --keep-own exclude each other" in capsys.readouterr().out
    assert not fake_runner.calls


def test_output_never_shows_env_values(both_on, monkeypatch, capsys):
    _claude_json({"serena": {**CLAUDE_PLAIN, "env": {"TOKEN": "s3cret"}}})
    monkeypatch.setattr(cbm_installer, "claude_plugin_on", lambda: True)
    adopt.run(True, {"migrate"}, set(), True, lambda q: "", with_versions=False, use_loadout=True)
    captured = capsys.readouterr()
    assert "s3cret" not in captured.out + captured.err
    lines, _ = adopt.serena_pass(_bk(), lambda q: "", False, True, False)
    assert "s3cret" not in "\n".join(lines)


@pytest.mark.parametrize("answer,removed,left", [("Yes", True, False), (" YES ", True, False),
                                                 ("NO", False, True), ("no", False, True)])
def test_interactive_accepts_yes_and_no_words(codex_on, answer, removed, left):
    _config(PLAIN)
    adopt.serena_pass(_bk(), lambda q: answer, True, False, False)
    assert bool(_removes(codex_on)) is removed
    assert ("leave" in own.decisions().values()) is left


def test_failed_codex_removal_fails_the_run(codex_on):
    _config(PLAIN)
    codex_on.responses[(codex.program(), "mcp", "remove")] = runner.Result(1, "", "boom")
    lines, texts = adopt.serena_pass(_bk(), lambda q: "", False, True, False)
    assert texts == [] and any(isinstance(ln, adopt.NotDone) for ln in lines)
    assert adopt.run(True, None, set(), True, lambda q: "", with_versions=False, use_loadout=True) == 1


def test_failed_claude_removal_fails_the_run(both_on, monkeypatch):
    _claude_json({"serena": CLAUDE_PLAIN})
    monkeypatch.setattr(cbm_installer, "claude_plugin_on", lambda: True)
    both_on.responses[("claude", "mcp", "remove")] = runner.Result(1, "", "boom")
    lines, _ = adopt.serena_pass(_bk(), lambda q: "", False, True, False)
    assert any(isinstance(ln, adopt.NotDone) for ln in lines)
    assert adopt.run(True, None, set(), True, lambda q: "", with_versions=False, use_loadout=True) == 1


def test_yes_keeps_a_claude_serena_while_loadouts_plugin_is_missing(both_on, monkeypatch):
    _claude_json({"serena": CLAUDE_PLAIN})
    monkeypatch.setattr(cbm_installer, "claude_plugin_on", lambda: False)
    adopt.run(True, None, set(), True, lambda q: "", with_versions=False, use_loadout=True)
    adopt.run(True, None, set(), True, lambda q: "", with_versions=False)
    assert [c for c in _removes(both_on) if c[0] == "claude"] == []


def test_own_remove_names_a_tuned_codex_serena(codex_on, capsys):
    _config(TUNED)
    rc = adopt.run(True, None, set(), False, lambda q: "", with_versions=False, interactive=False,
                   own_spec="serena=remove")
    assert rc == 0, capsys.readouterr().out
    assert _removes(codex_on) == [[codex.program(), "mcp", "remove", "serena"]]
    assert any("config.toml" in p.name for p in adopt.LAST_BACKUP.rglob("*"))


def test_own_remove_refuses_a_serena_that_cannot_be_put_back(codex_on, capsys):
    _config('mcp_servers.serena = { command = "serena", args = ["start-mcp-server", "--context=ide"] }\n')
    rc = adopt.run(True, None, set(), False, lambda q: "", with_versions=False, interactive=False,
                   own_spec="serena=remove")
    assert rc == 1 and not _removes(codex_on)
    assert "edit config.toml yourself" in capsys.readouterr().out


def test_own_remove_names_a_tuned_claude_serena(both_on):
    _claude_json({"serena": {**CLAUDE_PLAIN, "command": "/opt/fork/serena"}})
    rc = adopt.run(True, None, set(), False, lambda q: "", with_versions=False, interactive=False,
                   own_spec="serena=remove")
    assert rc == 0 and _removes(both_on) == [["claude", "mcp", "remove", "-s", "user", "serena"]]


# ---- final-review fixes: adopt --use-loadout writes loadout's Codex Serena or rolls back ----

TWO = PLAIN + PLAIN.replace("[mcp_servers.serena]", "[mcp_servers.my-serena]")


def _fake_remove(monkeypatch, events=None, fail_on=None):
    """`codex mcp remove` does not run under the fake runner: do what it does to the file."""
    def remove(name, bk):
        cfg = paths.codex_home() / "config.toml"
        bk.save_copy(cfg, f"Codex config.toml before removing mcp {name}")
        if events is not None:
            events.append(name)
        if fail_on == name:
            raise KeyboardInterrupt
        text = cfg.read_text(encoding="utf-8")
        block = PLAIN.replace("[mcp_servers.serena]", f"[mcp_servers.{name}]")
        cfg.write_text(text.replace(block, ""), encoding="utf-8")
        return f"mcp {name}: removed from Codex"
    monkeypatch.setattr(codex, "remove_server", remove)


def _adopt_flag(**kw):
    return adopt.run(True, None, set(), True, lambda q: "", with_versions=False, use_loadout=True, **kw)


def test_adopt_use_loadout_writes_loadouts_codex_table(codex_on, monkeypatch, capsys):
    cfg = _config(PLAIN)
    _fake_remove(monkeypatch)
    wrote = []
    monkeypatch.setattr(codex, "apply_config", lambda bk, dry_run=False: wrote.append(1) or
                        cfg.write_text(cfg.read_text() + '[mcp_servers.serena]\ncommand = "loadout-serena"\n') and [])
    _adopt_flag()
    assert wrote and 'command = "loadout-serena"' in cfg.read_text()
    assert "put your server back" not in capsys.readouterr().out


def test_adopt_use_loadout_rolls_back_when_apply_config_writes_nothing(codex_on, monkeypatch, capsys):
    cfg = _config(PLAIN)
    _fake_remove(monkeypatch)
    monkeypatch.setattr(codex, "apply_config", lambda bk, dry_run=False: [])
    _adopt_flag()
    assert cfg.read_text().strip() == PLAIN.strip()
    assert "put your server back" in capsys.readouterr().out


def test_adopt_use_loadout_failed_reinsert_fails_the_run(codex_on, monkeypatch, capsys):
    _config(PLAIN)
    _fake_remove(monkeypatch)
    monkeypatch.setattr(codex, "apply_config", lambda bk, dry_run=False: [])
    monkeypatch.setattr(codex, "reinsert_table", lambda text: "Serena: could not put your server back (X); "
                                                              "restore it with: loadout restore <dir>")
    assert _adopt_flag() == 1
    out = capsys.readouterr().out
    assert "loadout restore" in out and "<dir>" not in out


def test_adopt_use_loadout_removes_nothing_when_codex_unavailable(codex_on, monkeypatch, capsys):
    cfg = _config(PLAIN)
    events = []
    _fake_remove(monkeypatch, events)
    monkeypatch.setattr(codex, "unavailable", lambda *a, **k: "Codex is not installed")
    _adopt_flag()
    assert events == [] and cfg.read_text() == PLAIN
    assert "Codex is not set up in this run" in capsys.readouterr().out


def test_adopt_exception_in_the_pass_rolls_back_earlier_removals(codex_on, monkeypatch, capsys):
    cfg = _config(TWO)
    _fake_remove(monkeypatch, fail_on="my-serena")
    with pytest.raises(KeyboardInterrupt):
        _adopt_flag()
    assert "[mcp_servers.serena]" in cfg.read_text() and "put your server back" in capsys.readouterr().out


def test_use_loadout_pass_that_changed_something_is_not_a_usage_exit(codex_on, monkeypatch, capsys):
    _config(PLAIN)
    _fake_remove(monkeypatch)
    monkeypatch.setattr(codex, "apply_config", lambda bk, dry_run=False: [])
    rc = adopt.run(True, None, set(), False, lambda q: "", with_versions=False, interactive=False, use_loadout=True)
    out = capsys.readouterr().out
    assert rc == 0 and "nothing changed" not in out and "Serena step applied" in out


def test_declined_apply_after_a_pass_change_does_not_say_nothing_changed(codex_on, monkeypatch, capsys):
    _config(PLAIN)
    _fake_remove(monkeypatch)
    monkeypatch.setattr(codex, "apply_config", lambda bk, dry_run=False: [])
    monkeypatch.setattr(adopt, "select", lambda *a, **k: [object()])
    monkeypatch.setattr(adopt.ui, "confirm", lambda ask, q: False)
    rc = adopt.run(True, None, set(), False, lambda q: "n", with_versions=False, interactive=True, use_loadout=True)
    assert rc == 0 and "nothing changed" not in capsys.readouterr().out
