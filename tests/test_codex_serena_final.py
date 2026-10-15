"""Final-review fixes for PR A: no second Serena from the personal layer, drift, background runs, notices."""
import json

import pytest

from loadout import backup, codex, codex_hooks, maintenance, paths, runner, settings_merge, targets


@pytest.fixture
def cfg(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: {"enabledPlugins": {}})
    monkeypatch.setattr(codex, "installed_plugins", lambda: set())
    path = paths.codex_home() / "config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _personal(servers):
    p = paths.personal_root() / "mcp.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"mcpServers": servers}))


SERENA = {"command": "serena", "args": ["start-mcp-server", "--context=claude-code"]}


def test_a_personal_serena_plus_the_users_codex_serena_is_still_one(cfg):
    _personal({"serena": SERENA})
    cfg.write_text('[mcp_servers.serena-mine]\ncommand = "serena"\nargs = ["start-mcp-server"]\n')
    codex.apply_config(backup.Backup(description="t"))
    assert cfg.read_text().count("start-mcp-server") == 1


def test_two_personal_serenas_give_one_and_a_line(cfg):
    _personal({"serena-a": SERENA, "serena-b": SERENA})
    lines = codex.apply_config(backup.Backup(description="t"))
    assert cfg.read_text().count("start-mcp-server") == 1
    assert any("serena-b" in l and "second Serena" in l for l in lines)


def test_trust_covers_the_users_own_serena_hooks(fake_home):
    p = codex_hooks.path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"hooks": {"SessionStart": [{"matcher": "startup|resume", "hooks": [
        {"type": "command", "command": "echo hi"},
        {"type": "command", "command": "serena-hooks activate --client=codex"}]}]}}, indent=2) + "\n", newline="\n")
    assert codex_hooks.trust_keys() == {f"{p}:session_start:0:1"}


def test_every_rewrite_of_an_existing_hooks_json_has_a_backup(hooks, monkeypatch):
    codex_hooks.apply(backup.Backup(description="t"))  # creates the file
    monkeypatch.setattr(runner, "have", lambda b: False)
    bk = backup.Backup(description="t")
    codex_hooks.apply(bk)  # removes loadout's entries from the existing file
    assert any(step["label"].startswith("Codex hooks.json") and "move" not in step["undo"] for step in bk.steps)


def test_an_edited_approved_serena_hook_counts_as_changed(hooks):
    from loadout import codex
    codex_hooks.apply(backup.Backup(description="t"))
    keys = codex.hook_keys() | codex_hooks.trust_keys()
    cfgp = paths.codex_home() / "config.toml"
    cfgp.write_text("".join(f'[hooks.state.{codex.toml_value(k)}]\ntrusted_hash = "sha256:aa"\n\n' for k in keys))
    assert codex.hooks_status(remember=True) == "trusted"
    data = json.loads(hooks.read_text())
    data["hooks"]["SessionEnd"][0]["hooks"][0]["timeout"] = 2
    hooks.write_text(json.dumps(data, indent=2) + "\n", newline="\n")
    assert codex.hooks_status() == "changed"


def test_removing_loadouts_serena_table_saves_a_copy_first(cfg):
    codex.apply_config(backup.Backup(description="t"))
    cfg.write_text(cfg.read_text() + '\n[mcp_servers.my-serena]\ncommand = "serena"\nargs = ["start-mcp-server"]\n')
    bk = backup.Backup(description="t")
    codex.apply_config(bk)
    assert "[mcp_servers.serena]" not in cfg.read_text()
    assert any("config.toml" in step["label"] and "move" not in step["undo"] for step in bk.steps)


def test_an_edited_once_owned_serena_counts_as_the_users_in_the_same_run(cfg):
    _personal({"my-serena": SERENA})
    codex.apply_config(backup.Backup(description="t"))  # loadout owns [mcp_servers.my-serena]
    _personal({})
    cfg.write_text(cfg.read_text().replace('"--context=claude-code"', '"--context=codex"'))  # the user edits it
    codex.apply_config(backup.Backup(description="t"))
    assert cfg.read_text().count("start-mcp-server") == 1


def test_a_moved_serena_hook_needs_approval_again(hooks):
    from loadout import codex
    hooks.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo mine"}]}]}},
                                indent=2) + "\n", newline="\n")
    codex_hooks.apply(backup.Backup(description="t"))
    cfgp = paths.codex_home() / "config.toml"

    def trust(mapping):
        cfgp.write_text("".join(f'[hooks.state.{codex.toml_value(k)}]\ntrusted_hash = "{v}"\n\n' for k, v in mapping.items()))

    base = {k: "sha256:p" for k in codex.hook_keys()}
    mine = f"{hooks}:stop:0:0"
    serena_keys = codex_hooks.trust_keys()
    trust({**base, mine: "sha256:mine", **{k: "sha256:s-" + k for k in serena_keys}})
    assert codex.hooks_status(remember=True) == "trusted"
    data = json.loads(hooks.read_text())  # cleanup moves to Stop position 0, the user's hook to position 1
    cleanup = data["hooks"].pop("SessionEnd")[0]
    data["hooks"]["Stop"].insert(0, cleanup)
    hooks.write_text(json.dumps(data, indent=2) + "\n", newline="\n")
    moved = {k for k in serena_keys if ":session_end:" not in k}
    trust({**base, mine: "sha256:mine", f"{hooks}:stop:1:0": "sha256:mine2", **{k: "sha256:s-" + k for k in moved}})
    assert codex.hooks_status() == "changed"  # Stop:0 still holds the hash Codex gave the user's hook


INLINE = "".join(f'[[hooks.{e}]]\n{f"matcher = {json.dumps(m)}" + chr(10) if m else ""}'
                 f'[[hooks.{e}.hooks]]\ntype = "command"\ncommand = "serena-hooks {s} --client=codex"\n\n'
                 for e, m, s, _ in codex_hooks.SERENA_HOOKS)


def test_inline_serena_hooks_in_config_toml_count_as_present(hooks):
    (paths.codex_home() / "config.toml").write_text(INLINE)
    assert codex_hooks.apply(backup.Backup(description="t")) == []
    assert not hooks.exists()


def test_with_other_inline_hooks_loadout_creates_no_hooks_json(hooks):
    (paths.codex_home() / "config.toml").write_text('[[hooks.Stop]]\n[[hooks.Stop.hooks]]\ntype = "command"\ncommand = "echo hi"\n')
    lines = codex_hooks.apply(backup.Backup(description="t"))
    assert not hooks.exists() and any("add these yourself" in l and "config.toml" in l for l in lines)


def test_a_personal_serena_under_another_name_replaces_loadouts(cfg):
    _personal({"my-serena": SERENA})
    codex.apply_config(backup.Backup(description="t"))
    text = cfg.read_text()
    assert text.count("start-mcp-server") == 1 and "[mcp_servers.my-serena]" in text


def test_drift_does_not_ask_to_adopt_the_users_serena(cfg, monkeypatch):
    targets.set_agents({"claude": True, "codex": True})
    cfg.write_text('[mcp_servers.serena-mine]\ncommand = "serena"\nargs = ["start-mcp-server"]\n')
    monkeypatch.setattr(codex, "mcp_names", lambda: {"serena-mine"})
    assert not any("serena-mine" in line for line in codex.drift())


def test_plugin_servers_follow_the_codex_manifest(fake_home):
    root = paths.codex_home() / "plugins" / "cache" / "agent-loadout" / "loadout" / "local"
    (root / ".codex-plugin").mkdir(parents=True)
    (root / ".codex-plugin" / "plugin.json").write_text(json.dumps({"mcpServers": "./.codex-mcp.json"}))
    (root / ".codex-mcp.json").write_text(json.dumps({"mcpServers": {"codebase-memory-mcp": {"command": "x"}}}))
    (root / ".mcp.json").write_text(json.dumps({"mcpServers": {"serena": {"command": "serena"}}}))
    assert codex._plugin_servers() == {"codebase-memory-mcp"}


@pytest.fixture
def hooks(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(runner, "have", lambda b: b in ("serena-hooks", "serena"))
    p = codex_hooks.path()
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def test_a_background_run_never_removes_loadouts_hooks(hooks, monkeypatch):
    codex_hooks.apply(backup.Backup(description="t"))
    before = hooks.read_text()
    monkeypatch.setattr(runner, "have", lambda b: False)  # a short PATH: neither serena nor serena-hooks
    assert codex_hooks.apply(backup.Backup(description="t"), keep=True) == []
    assert hooks.read_text() == before


def test_apply_all_keeps_hooks_in_a_refresh(hooks, monkeypatch):
    seen = []
    monkeypatch.setattr(codex_hooks, "apply", lambda bk, dry_run=False, keep=False: seen.append(keep) or [])
    for name in ("apply_instructions", "apply_config", "apply_skills", "apply_plugins"):
        monkeypatch.setattr(codex, name, lambda *a, **k: [] if name != "apply_instructions" else "ok")
    codex.apply_all(object(), refresh=True)
    codex.apply_all(object())
    assert seen == [True, False]


def test_the_approve_line_reaches_the_session_notice():
    assert maintenance.codex_notice("hooks.json: added Serena's hooks (remind); approve them in Codex: /hooks")


def test_a_group_without_a_hooks_list_is_a_line_not_a_crash(hooks):
    text = '{\n  "hooks": {\n    "Stop": [\n      {\n        "hooks": null\n      }\n    ]\n  }\n}\n'
    hooks.write_text(text)
    lines = codex_hooks.apply(backup.Backup(description="t"))  # no TypeError
    assert lines and json.loads(hooks.read_text())["hooks"]["Stop"][0] == {"hooks": None}  # the user's group stays


def test_the_add_yourself_line_names_matchers_and_timeouts(hooks):
    hooks.write_text('{"hooks": {}}')
    (line,) = codex_hooks.apply(backup.Backup(description="t"))
    assert '"matcher": "Bash"' in line and '"timeout": 5' in line and "hooks.md" in line
