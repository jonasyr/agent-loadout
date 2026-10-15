"""Codex: Serena's server as `serena setup codex` writes it, and never a second one (spec PR A)."""
import pytest

from loadout import backup, codex, settings_merge


@pytest.fixture
def cfg(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: {"enabledPlugins": {}})
    monkeypatch.setattr(codex, "installed_plugins", lambda: set())
    path = codex.paths.codex_home() / "config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def test_loadouts_serena_table_is_the_documented_one(cfg):
    codex.apply_config(backup.Backup(description="t"))
    text = cfg.read_text()
    assert ('[mcp_servers.serena]\ncommand = "serena"\n'
            'args = ["start-mcp-server", "--project-from-cwd", "--context=codex"]\nstartup_timeout_sec = 15\n') in text


@pytest.mark.parametrize("table", [
    '[mcp_servers.serena]\nstartup_timeout_sec = 15\ncommand = "serena"\nargs = ["start-mcp-server", "--project-from-cwd", "--context=codex"]\n',
    '[mcp_servers.serena-mine]\ncommand = "uvx"\nargs = ["--from", "git+https://github.com/oraios/serena", "serena", "start-mcp-server", "--context", "codex"]\n',
    '[mcp_servers.s]\ncommand = "/home/u/.local/bin/serena"\nargs = ["start-mcp-server"]\n',
])
def test_a_users_serena_is_used_and_no_second_one_is_added(cfg, table):
    cfg.write_text(table)
    lines = codex.apply_config(backup.Backup(description="t"))
    assert cfg.read_text().count("start-mcp-server") == 1
    assert not any("left as is" in l for l in lines)
    assert codex.apply_config(object(), dry_run=True) == []  # loadout check stays quiet


def test_loadouts_earlier_serena_goes_when_the_user_adds_their_own(cfg):
    codex.apply_config(backup.Backup(description="t"))
    cfg.write_text(cfg.read_text() + '\n[mcp_servers.my-serena]\ncommand = "serena"\nargs = ["start-mcp-server"]\n')
    codex.apply_config(backup.Backup(description="t"))
    text = cfg.read_text()
    assert "[mcp_servers.serena]" not in text and "[mcp_servers.my-serena]" in text


def test_a_serena_table_that_is_not_serena_names_the_rename_fix(cfg, monkeypatch):
    cfg.write_text('[mcp_servers.serena]\ncommand = "something-else"\n')
    lines = codex.apply_config(object(), dry_run=True)
    assert any("left as is" in l for l in lines)
    monkeypatch.setattr(codex, "enabled", lambda: True)
    monkeypatch.setattr(codex, "installed_plugins", lambda: {"loadout@agent-loadout"})
    monkeypatch.setattr(codex, "unavailable", lambda: None)
    monkeypatch.setattr(codex, "hooks_status", lambda: "trusted")
    monkeypatch.setattr(codex, "logins_needed", lambda: [])
    monkeypatch.setattr(codex, "drift", lambda: [])
    (r,) = [r for r in codex.checks() if r.name == "Codex config"]
    assert not r.ok and "rename" in r.fix
