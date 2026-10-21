"""Bootstrap names a kept own Serena once; apply_config adds no such line (live-tour fixes, spec fix 11)."""
import pytest

from loadout import backup, bootstrap, codex, paths, runner

OWN = '[mcp_servers.my-serena]\ncommand = "uvx"\nargs = ["--from", "serena", "serena", "start-mcp-server"]\n'
LINE = "Serena: your own server in config.toml kept"


def _codex(fake_home, fake_runner):
    (fake_home / ".config/loadout/personal").mkdir(parents=True)
    codex.set_enabled(True)
    fake_runner.responses[("codex", "--version")] = runner.Result(0, "codex-cli 0.162.1\n", "")
    path = paths.codex_home() / "config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(OWN, encoding="utf-8")


def _run():
    bootstrap.bootstrap(install=False, yes=True, plugins=False, adopt_step=False,
                        ask=lambda q: pytest.fail("asked"), interactive=False, agents="codex")


def test_bootstrap_names_a_kept_own_serena_once(fake_home, fake_runner, capsys):
    _codex(fake_home, fake_runner)
    _run()
    text = capsys.readouterr().out
    assert text.count("your own server in config.toml kept") == 1
    assert LINE in text and LINE == codex.SERENA_KEPT
    assert "my-serena" in (paths.codex_home() / "config.toml").read_text(encoding="utf-8")


def test_no_line_without_an_own_serena(fake_home, fake_runner, capsys):
    (fake_home / ".config/loadout/personal").mkdir(parents=True)
    codex.set_enabled(True)
    fake_runner.responses[("codex", "--version")] = runner.Result(0, "codex-cli 0.162.1\n", "")
    _run()
    assert "your own server in config.toml kept" not in capsys.readouterr().out


def test_apply_config_adds_no_kept_line(fake_home, fake_runner):
    _codex(fake_home, fake_runner)
    lines = codex.apply_config(backup.Backup(description="t"))
    assert not [l for l in lines if "kept" in l and "Serena" in l]
