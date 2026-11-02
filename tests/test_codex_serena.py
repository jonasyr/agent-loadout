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


SRC = ('# my serena\n[mcp_servers.serena]\ncommand = "serena"\nargs = ["start-mcp-server", "--context=ide"]\n\n'
       '[mcp_servers.serena.env]\nSERENA_LOG = "debug"\n')
BACK = "Serena: put your server back in config.toml"


def test_table_source_takes_the_table_with_its_subtables(cfg, fake_home):
    cfg.write_text('model = "x"\n\n' + SRC + '\n[mcp_servers.other]\ncommand = "o"\n')
    src = codex.table_source("serena")
    assert "[mcp_servers.serena.env]" in src and "SERENA_LOG" in src and "other" not in src
    assert src.startswith("[mcp_servers.serena]\n") and src.endswith('SERENA_LOG = "debug"\n')


def test_table_source_keeps_inner_comments_and_tool_subtables(cfg, fake_home):
    body = ('[mcp_servers.serena]\n# why\ncommand = "serena"  # inline\n\n'
            '# approved by me\n[mcp_servers.serena.tools.find_symbol]\napproval_mode = "approve"\n')
    cfg.write_text(body + '\n[mcp_servers.other]\ncommand = "o"\n')
    assert codex.table_source("serena") == body


def test_table_source_none_when_absent_dotted_or_inline(cfg, fake_home):
    cfg.write_text('[mcp_servers.other]\ncommand = "o"\n')
    assert codex.table_source("serena") is None
    cfg.write_text('[mcp_servers]\nserena = { command = "serena" }\n')
    assert codex.table_source("serena") is None
    cfg.write_text('mcp_servers.serena = { command = "serena" }\n')
    assert codex.table_source("serena") is None


def test_table_source_none_when_unreadable_or_missing(cfg, fake_home):
    assert codex.table_source("serena") is None  # no file
    cfg.write_bytes(b"\xff\xfe[mcp_servers.serena]\n")
    assert codex.table_source("serena") is None


def test_table_source_of_a_crlf_file_is_lf_and_reinsert_restores_crlf(cfg, fake_home):
    cfg.write_bytes(SRC.replace("\n", "\r\n").encode())
    src = codex.table_source("serena")
    assert "\r" not in src
    cfg.write_bytes(b'model = "x"\r\n')
    assert BACK in codex.reinsert_table(src)
    assert cfg.read_bytes() == b'model = "x"\r\n' + src.replace("\n", "\r\n").encode()


def test_reinsert_puts_back_exactly_the_text(cfg, fake_home):
    cfg.write_text('model = "x"\n')
    assert BACK in codex.reinsert_table(SRC)
    assert cfg.read_text() == 'model = "x"\n' + SRC


def test_reinsert_into_a_file_without_trailing_newline(cfg, fake_home):
    cfg.write_bytes(b'model = "x"')
    assert BACK in codex.reinsert_table(SRC)
    assert cfg.read_text() == 'model = "x"\n' + SRC


def test_reinsert_into_a_missing_file_creates_it(cfg, fake_home):
    assert BACK in codex.reinsert_table(SRC)
    assert cfg.read_text() == SRC


def test_reinsert_never_raises_and_names_the_restore(cfg, fake_home, monkeypatch):
    cfg.write_bytes(b"\xff\xfe")
    out = codex.reinsert_table(SRC)
    assert "could not put your server back" in out and "loadout restore <dir>" in out
    assert cfg.read_bytes() == b"\xff\xfe"
    cfg.write_text("a = 1\n")
    monkeypatch.setattr("loadout.jsonio.write_atomic_bytes", lambda *a, **k: (_ for _ in ()).throw(OSError("disk")))
    out = codex.reinsert_table(SRC)
    assert "could not put your server back" in out and "loadout restore <dir>" in out
