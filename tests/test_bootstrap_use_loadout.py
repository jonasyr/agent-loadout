"""bootstrap --use-loadout / --keep-own: the Serena pass, its rollback and the "still to do" line (spec start-clean)."""
import argparse
import json

import pytest

from loadout import apply, bootstrap, codex, commands, paths, runner, targets
from loadout.jsonio import save_json

PLAIN = ('[mcp_servers.my-serena]\ncommand = "serena"\n'
         'args = ["start-mcp-server", "--project-from-cwd", "--context=codex"]\nstartup_timeout_sec = 15\n')
TWICE = "Serena runs twice: loadout adopt --apply --use-loadout (or leave yours: loadout configure own)"


def _plain(fake_home, fake_runner):
    (fake_home / ".config/loadout/personal").mkdir(parents=True)
    codex.set_enabled(True)
    fake_runner.responses[("codex", "--version")] = runner.Result(0, "codex-cli 0.162.1\n", "")
    cfg = paths.codex_home() / "config.toml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(PLAIN, encoding="utf-8")


def _fake_remove(monkeypatch, events):
    """`codex mcp remove` does not run under the fake runner: do what it does to the file, and note the order."""
    def remove(name, bk):
        cfg = paths.codex_home() / "config.toml"
        bk.save_copy(cfg, f"Codex config.toml before removing mcp {name}")
        events.append("remove")
        cfg.write_text(cfg.read_text(encoding="utf-8").replace(PLAIN, ""), encoding="utf-8")
        return f"mcp {name}: removed from Codex"
    monkeypatch.setattr(codex, "remove_server", remove)


def _boot(**kw):
    args = dict(install=False, yes=True, plugins=False, adopt_step=False, ask=lambda q: pytest.fail("asked"),
                interactive=False, agents="codex")
    args.update(kw)
    return bootstrap.bootstrap(**args)


def test_flag_replaces_the_codex_serena_in_one_run(fake_home, fake_runner, monkeypatch, capsys):
    _plain(fake_home, fake_runner)
    events = []
    _fake_remove(monkeypatch, events)
    real = apply.codex_step
    monkeypatch.setattr(apply, "codex_step", lambda *a, **k: events.append("codex_step") or real(*a, **k))
    _boot(use_loadout=True)
    text = capsys.readouterr().out
    assert events == ["remove", "codex_step"]
    cfg = (paths.codex_home() / "config.toml").read_text(encoding="utf-8")
    assert "my-serena" not in cfg and "[mcp_servers.serena]" in cfg
    assert "serena" in codex.read_record()["tables"]
    assert "put your server back" not in text


def test_codex_only_machine_runs_the_pass(fake_home, fake_runner, monkeypatch):
    _plain(fake_home, fake_runner)
    events = []
    _fake_remove(monkeypatch, events)
    _boot(use_loadout=True, agents="codex")
    assert events == ["remove"]


def test_rollback_when_codex_step_does_not_write_serena(fake_home, fake_runner, monkeypatch, capsys):
    _plain(fake_home, fake_runner)
    _fake_remove(monkeypatch, [])
    monkeypatch.setattr(apply, "codex_step", lambda *a, **k: apply.StepResult("Codex", "failed", ["boom"], level="fail"))
    _boot(use_loadout=True)
    text = capsys.readouterr().out
    assert (paths.codex_home() / "config.toml").read_text(encoding="utf-8").strip() == PLAIN.strip()
    assert "put your server back" in text


def test_rollback_failure_names_the_backup(fake_home, fake_runner, monkeypatch, capsys):
    _plain(fake_home, fake_runner)
    _fake_remove(monkeypatch, [])
    monkeypatch.setattr(apply, "codex_step", lambda *a, **k: apply.StepResult("Codex", "failed", []))
    monkeypatch.setattr(codex, "reinsert_table", lambda text: "Serena: could not put your server back (X); "
                                                              "restore it with: loadout restore <dir>")
    _boot(use_loadout=True)
    text = capsys.readouterr().out
    assert "loadout restore" in text and "<dir>" not in text
    assert str(paths.backups_root() if hasattr(paths, "backups_root") else "backup") in text


def test_yes_alone_leaves_the_codex_serena(fake_home, fake_runner, monkeypatch, capsys):
    _plain(fake_home, fake_runner)
    events = []
    _fake_remove(monkeypatch, events)
    _boot()
    assert events == []
    assert codex.SERENA_KEPT in capsys.readouterr().out
    assert "my-serena" in (paths.codex_home() / "config.toml").read_text(encoding="utf-8")


def test_keep_own_removes_nothing(fake_home, fake_runner, monkeypatch):
    _plain(fake_home, fake_runner)
    events = []
    _fake_remove(monkeypatch, events)
    _boot(keep_own=True)
    assert events == []


def test_both_flags_exit_2(fake_home, fake_runner, capsys):
    p = argparse.ArgumentParser()
    commands._register_bootstrap(p.add_subparsers())
    a = p.parse_args(["bootstrap", "--use-loadout", "--keep-own"])
    assert a.func(a) == 2
    assert "--use-loadout and --keep-own exclude each other" in capsys.readouterr().out
    assert not fake_runner.calls


def test_non_interactive_names_the_next_step(fake_home, fake_runner, monkeypatch, capsys):
    _plain(fake_home, fake_runner)
    _boot()
    assert TWICE in capsys.readouterr().out


def test_no_next_step_without_a_duplicate(fake_home, fake_runner, capsys):
    (fake_home / ".config/loadout/personal").mkdir(parents=True)
    codex.set_enabled(True)
    fake_runner.responses[("codex", "--version")] = runner.Result(0, "codex-cli 0.162.1\n", "")
    _boot()
    assert "Serena runs twice" not in capsys.readouterr().out


def test_check_fix_names_use_loadout(fake_home, fake_runner, tmp_path, monkeypatch):
    from loadout import check
    monkeypatch.chdir(tmp_path)
    (fake_home / ".claude.json").write_text(json.dumps({"mcpServers": {"my-serena": {
        "command": "uvx", "args": ["--from", "git+https://github.com/oraios/serena", "serena", "start-mcp-server"]}}}))
    [r] = [r for r in check.run_checks() if r.name == "Serena servers"]
    assert "loadout adopt --apply --use-loadout" in r.fix
