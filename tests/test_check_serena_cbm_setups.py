"""Check rows for a Serena or codebase-memory setup next to the plugin's own (hooks, second servers)."""
import importlib.util
import json

from loadout import check, duplicates, paths

REMIND = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
    {"type": "command", "command": "serena-hooks remind --client=claude-code"}]}]}}
MINE = {"hooks": {"PreToolUse": [{"hooks": [
    {"type": "command", "command": "/opt/bin/serena-hooks", "args": ["--quiet", "remind"]}]}],
    "SessionStart": [{"hooks": [{"type": "command", "command": "echo serena-hooks activate"}]}]}}


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def rows(name):
    return [r for r in check.run_checks() if r.name == name]


def test_row_names_users_equivalent_serena_hook(fake_home, fake_runner, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write(fake_home / ".claude" / "settings.json", MINE)
    [r] = rows("Serena hooks")
    assert r.ok and r.detail == "yours in ~/.claude/settings.json; the plugin's copy stays silent"
    assert r.fix == "loadout configure own"


def test_row_warns_on_second_serena_server(fake_home, fake_runner, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write(fake_home / ".claude.json", {"mcpServers": {"my-serena": {
        "command": "uvx", "args": ["--from", "git+https://github.com/oraios/serena", "serena", "start-mcp-server"]}}})
    [r] = rows("Serena servers")
    assert not r.ok and r.severity == "warn"
    assert r.detail == "two Serena servers: the plugin's and yours (my-serena in ~/.claude.json)"


def test_exact_duplicate_server_is_not_a_second_server(fake_home, fake_runner, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(duplicates, "plugin_enabled", lambda: True)
    ours = duplicates.plugin_servers()
    _write(fake_home / ".claude.json", {"mcpServers": {"serena": ours["serena"],
                                                       "codebase-memory-mcp": ours["codebase-memory-mcp"]}})
    _write(fake_home / ".claude" / "settings.json", {"hooks": {"PreToolUse": [{
        "matcher": "Bash|Read|Grep|Glob|mcp__plugin_loadout_serena__.*|mcp__serena__.*", "hooks": [
            {"type": "command", "command": "serena-hooks remind --client=claude-code"}]}]}})
    assert not rows("Serena servers") and not rows("codebase-memory servers")
    assert not rows("Serena hooks")  # an exact copy (event, matcher, command): `loadout update` removes it


def test_rows_absent_in_default_setup(fake_home, fake_runner, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    names = {"Serena hooks", "Serena servers", "codebase-memory servers", "codebase-memory hooks"}
    assert not names & {r.name for r in check.run_checks()}


def test_cbm_second_server_row(fake_home, fake_runner, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write(tmp_path / ".mcp.json", {"mcpServers": {"cbm": {"command": "/home/x/bin/codebase-memory-mcp"}}})
    [r] = rows("codebase-memory servers")
    assert not r.ok and r.severity == "warn"
    assert r.detail == "two codebase-memory servers: the plugin's and yours (cbm in .mcp.json)"
    assert "plugin:loadout:codebase-memory-mcp" in r.fix and "loadout configure own" in r.fix


def test_cbm_own_hook_row(fake_home, fake_runner, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write(fake_home / ".claude" / "settings.json", {"hooks": {
        "PreToolUse": [{"hooks": [{"type": "command", "command": "/x/codebase-memory-mcp", "args": ["hook-augment"]}]}],
        "PostToolUse": [{"hooks": [{"type": "command", "command": "codebase-memory-mcp hook-augment"}]}]}})
    [r] = rows("codebase-memory hooks")
    assert not r.ok and r.severity == "warn"
    assert r.detail == ("codebase-memory's own hooks (2 in ~/.claude/settings.json) add up to 2 s per call and "
                        "print nothing in codebase-memory 0.12 (upstream #2683)")
    assert r.fix == "loadout configure own (remove, or leave them)"


def test_guard_and_check_agree_on_the_same_settings(fake_home, tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("mcp_guard", paths.kit_root() / "plugins/loadout/hooks/mcp_guard.py")
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    monkeypatch.chdir(tmp_path)
    _write(fake_home / ".claude" / "settings.json", MINE)  # remind (flag first, args), activate only echoed
    _write(tmp_path / ".claude" / "settings.local.json", {"hooks": {"SessionEnd": [{"hooks": [
        {"type": "command", "command": "serena-hooks cleanup"}]}]}})
    _write(tmp_path / ".claude" / "settings.json", {"hooks": {"PreToolUse": [{"hooks": [
        {"type": "command", "command": "serena-hooks auto-approve"}]}]}})
    found = duplicates.equivalent_user_hooks(str(tmp_path))
    seen = set()
    for event, inner in duplicates.plugin_guarded_hooks("serena-hooks"):
        argv = [w for w in inner.split() if not w.startswith("-")]
        theirs = guard.users_hook_runs(event, argv, str(tmp_path), fake_home)
        ours = any(e == event and argv[1] in c.split() for e, c, _ in found)
        assert theirs == ours, (event, inner)
        seen.add((argv[1], theirs))
    assert {("remind", True), ("cleanup", True), ("activate", False)} <= seen


def _my_serena(fake_home, extra=None):
    _write(fake_home / ".claude.json", {"mcpServers": {"my-serena": {
        "command": "uvx", "args": ["--from", "git+https://github.com/oraios/serena", "serena", "start-mcp-server"]}},
        **(extra or {})})


def test_second_server_row_clears_when_the_plugins_server_is_off_here(fake_home, fake_runner, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _my_serena(fake_home, {"projects": {str(tmp_path): {"disabledMcpServers": ["plugin:loadout:serena"]}}})
    assert not rows("Serena servers")


def test_second_server_row_clears_when_you_chose_to_leave_yours(fake_home, fake_runner, tmp_path, monkeypatch):
    from loadout import own
    from loadout.inventory import Item
    monkeypatch.chdir(tmp_path)
    _my_serena(fake_home)
    item = Item("mcp", "my-serena", "", "~/.claude.json", {})
    monkeypatch.setattr(own, "decisions", lambda: {own.decision_key(item): "leave"})
    assert not rows("Serena servers")


def test_second_server_fix_names_ways_that_exist(fake_home, fake_runner, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _my_serena(fake_home)
    [r] = rows("Serena servers")
    assert "/mcp" in r.fix and "plugin:loadout:serena" in r.fix and "loadout configure own" in r.fix
