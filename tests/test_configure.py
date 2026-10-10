import json

from loadout import configure, paths, personal_mcp, runner


def _personal_settings():
    p = paths.personal_root() / "settings.json"
    return json.loads(p.read_text()) if p.exists() else {}


def test_addons_include_kit_defaults_profile_plugins_and_offers(fake_home):
    keys = {a.key: a for a in configure.addons()}
    assert keys["plugin:superpowers@claude-plugins-official"].default_on is True
    assert keys["plugin:deepeval@claude-plugins-official"].default_on is False
    assert keys["plugin:hookify@claude-plugins-official"].category == "workflow"
    assert keys["mcp:addon-dbhub-global"].kind == "mcp"


def test_set_plugin_opt_out_and_back_keeps_personal_clean(fake_home):
    configure.set_plugin("superpowers@claude-plugins-official", False)
    assert _personal_settings()["enabledPlugins"] == {"superpowers@claude-plugins-official": False}
    configure.set_plugin("superpowers@claude-plugins-official", True)
    assert _personal_settings().get("enabledPlugins", {}) == {}


def test_set_plugin_opt_in_global(fake_home):
    configure.set_plugin("hookify@claude-plugins-official", True)
    assert _personal_settings()["enabledPlugins"]["hookify@claude-plugins-official"] is True


def test_set_pref_parses_json(fake_home):
    configure.set_pref("effortLevel", '"high"')
    configure.set_pref("alwaysThinkingEnabled", "false")
    assert _personal_settings()["effortLevel"] == "high"
    assert _personal_settings()["alwaysThinkingEnabled"] is False


def test_set_mcp_writes_personal_mcp_and_warns_missing_env(fake_home, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    warnings = configure.set_mcp("addon-dbhub-global", True)
    data = json.loads((paths.personal_root() / "mcp.json").read_text())
    assert "dbhub" in data["mcpServers"]
    assert any("DATABASE_URL" in w for w in warnings)
    configure.set_mcp("addon-dbhub-global", False)
    assert json.loads((paths.personal_root() / "mcp.json").read_text())["mcpServers"] == {}


def test_apply_mcp_adds_and_removes_only_managed(fake_home, fake_runner):
    (paths.personal_root()).mkdir(parents=True)
    (paths.personal_root() / "mcp.json").write_text(json.dumps({"mcpServers": {"dbhub": {"command": "npx"}}}))
    personal_mcp.apply_mcp()
    assert ["claude", "mcp", "add-json", "-s", "user", "dbhub", json.dumps({"command": "npx"})] in fake_runner.calls
    # simulate it is now present in ~/.claude.json alongside a user's own server
    paths.claude_json().write_text(json.dumps({"mcpServers": {"dbhub": {"command": "npx"}, "mine": {"command": "x"}}}))
    (paths.personal_root() / "mcp.json").write_text(json.dumps({"mcpServers": {}}))
    fake_runner.calls.clear()
    personal_mcp.apply_mcp()
    assert fake_runner.calls == [["claude", "mcp", "remove", "-s", "user", "dbhub"]]


def test_wizard_toggles_and_applies(fake_home, fake_runner, monkeypatch):
    applied = []
    monkeypatch.setattr(configure, "apply_all", lambda ask, **k: applied.append(1))
    (paths.personal_root() / "rules").mkdir(parents=True)
    (paths.personal_root() / "rules/me.md").write_text("me")  # existing profile: wizard skips about-you
    menu = configure.addons()
    idx = [a.key for a in menu].index("plugin:hookify@claude-plugins-official") + 1
    answers = iter([str(idx), ""])  # no terminal: preferences are not asked; toggle hookify, done
    configure.wizard(lambda q: next(answers), first_run=False, interactive=False)
    assert _personal_settings()["enabledPlugins"]["hookify@claude-plugins-official"] is True
    assert applied == [1]


def test_show_marks_overrides(fake_home):
    configure.set_plugin("superpowers@claude-plugins-official", False)
    text = configure.show()
    assert "superpowers@claude-plugins-official" in text and "off (personal)" in text


# --- apply_mcp never clobbers servers it does not manage (R-E) ---

def _mcp_setup(desired, current, previous=None):
    paths.personal_root().mkdir(parents=True, exist_ok=True)
    (paths.personal_root() / "mcp.json").write_text(json.dumps({"mcpServers": desired}))
    paths.claude_json().write_text(json.dumps({"mcpServers": current}))
    if previous is not None:
        snap = paths.state_dir() / "managed-mcp.json"
        snap.parent.mkdir(parents=True, exist_ok=True)
        snap.write_text(json.dumps({"mcpServers": previous}))


def _snapshot():
    return json.loads((paths.state_dir() / "managed-mcp.json").read_text())["mcpServers"]


def test_apply_mcp_skips_unmanaged_same_named_server(fake_home, fake_runner):
    _mcp_setup({"github": {"command": "npx", "args": ["kit"]}}, {"github": {"command": "mine", "env": {"T": "x"}}})
    out = personal_mcp.apply_mcp()
    assert fake_runner.calls == []
    assert any("github" in line and "not managed by loadout" in line for line in out)
    assert "github" not in _snapshot()


def test_apply_mcp_readds_previous_config_when_add_fails(fake_home, fake_runner):
    old = {"command": "npx", "args": ["v1"]}
    new = {"command": "npx", "args": ["v2"]}
    _mcp_setup({"dbhub": new}, {"dbhub": old}, previous={"dbhub": old})
    fake_runner.responses[("claude", "mcp", "add-json", "-s", "user", "dbhub", json.dumps(new))] = runner.Result(1, "", "bad")
    out = personal_mcp.apply_mcp()
    assert fake_runner.calls[-1] == ["claude", "mcp", "add-json", "-s", "user", "dbhub", json.dumps(old)]
    assert any("failed" in line for line in out)
    assert _snapshot() == {"dbhub": old}


def test_apply_mcp_snapshot_only_records_successes(fake_home, fake_runner):
    _mcp_setup({"a": {"command": "a"}, "b": {"command": "b"}}, {})
    fake_runner.responses[("claude", "mcp", "add-json", "-s", "user", "b")] = runner.Result(1, "", "nope")
    personal_mcp.apply_mcp()
    assert _snapshot() == {"a": {"command": "a"}}


def test_apply_mcp_keeps_failed_removal_managed(fake_home, fake_runner):
    _mcp_setup({}, {"x": {"command": "x"}}, previous={"x": {"command": "x"}})
    fake_runner.responses[("claude", "mcp", "remove")] = runner.Result(1, "", "busy")
    personal_mcp.apply_mcp()
    assert _snapshot() == {"x": {"command": "x"}}


# --- me.md is never overwritten silently (R-F) ---

def _existing_me():
    me = paths.personal_root() / "rules/me.md"
    me.parent.mkdir(parents=True, exist_ok=True)
    me.write_text("# About me\n\n## Migrated from ~/.claude/CLAUDE.md\nprecious\n")
    return me


def test_first_run_keeps_existing_me_md_by_default(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(configure, "apply_all", lambda ask, **k: None)
    me = _existing_me()
    configure.wizard(lambda q: "", first_run=True)
    assert "precious" in me.read_text()


def test_first_run_replace_backs_up_me_md(fake_home, fake_runner, monkeypatch, capsys):
    from loadout import backup
    monkeypatch.setattr(configure, "apply_all", lambda ask, **k: None)
    me = _existing_me()
    answers = iter(["y", "Max", "Dev", "Python", "short"] + [""] * 10)
    configure.wizard(lambda q: next(answers), first_run=True)
    assert "Max" in me.read_text()
    out = capsys.readouterr().out
    assert "loadout restore" in out
    root = out.split("loadout restore ")[1].split(")")[0].split()[0]
    backup.restore(paths.home() / root if not root.startswith("/") else __import__("pathlib").Path(root))
    assert "precious" in me.read_text()



# --- configure set/show (R-J) ---
import pytest
from loadout.__main__ import main


@pytest.mark.parametrize("word,expected", [("ON", True), ("true", True), ("Yes", True), ("off", False), ("FALSE", False), ("no", False)])
def test_set_plugin_accepts_switch_words(fake_home, fake_runner, word, expected):
    assert main(["configure", "set", "plugin", "hookify@claude-plugins-official", word]) == 0
    assert _personal_settings().get("enabledPlugins", {}).get("hookify@claude-plugins-official", False) is expected


def test_set_plugin_rejects_other_values(fake_home, fake_runner, capsys):
    assert main(["configure", "set", "plugin", "superpowers@claude-plugins-official", "1"]) == 1
    assert "on|off" in capsys.readouterr().err
    assert _personal_settings() == {}


def test_set_mcp_accepts_server_name(fake_home, fake_runner):
    configure.set_mcp("dbhub", True)
    assert "dbhub" in json.loads((paths.personal_root() / "mcp.json").read_text())["mcpServers"]


def test_show_prints_settable_ids(fake_home):
    text = configure.show()
    assert "mcp addon-dbhub-global" in text
    assert "plugin hookify@claude-plugins-official" in text


def test_configure_own_lists_and_set_own(fake_home, fake_runner, capsys):
    from fixtures import author_machine
    author_machine(fake_home)
    text = "\n".join(configure.own_lines(False))
    assert "mystery@somewhere" in text and "options: global, project, leave, remove" in text
    assert configure.set_own("my-skill", "leave") == 0
    assert "my-skill" not in "\n".join(configure.own_lines(False))
    assert "my-skill" in "\n".join(configure.own_lines(True))
    assert configure.set_own("nothing", "leave") == 2
    assert configure.set_own("mystery@somewhere", "keep") == 2


def test_cli_configure_own(fake_home, fake_runner, capsys):
    from fixtures import author_machine
    from loadout.__main__ import main
    author_machine(fake_home)
    assert main(["configure", "own"]) == 0
    assert "options:" in capsys.readouterr().out
    assert main(["configure", "set", "own", "nothing", "leave"]) == 2
