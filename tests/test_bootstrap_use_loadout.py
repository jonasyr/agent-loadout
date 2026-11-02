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


# --- review fixes: rollback on what config.toml holds, no removal without Codex, exceptions, exit code ---
def _reinsert_fails(monkeypatch):
    monkeypatch.setattr(codex, "reinsert_table", lambda text: "Serena: could not put your server back (X); "
                                                              "restore it with: loadout restore <dir>")


def test_stale_record_does_not_stop_the_rollback(fake_home, fake_runner, monkeypatch, capsys):
    _plain(fake_home, fake_runner)
    _fake_remove(monkeypatch, [])
    save_json(codex.record_path(), {"tables": {"serena": "[mcp_servers.serena]\n"}})  # left by an earlier run
    monkeypatch.setattr(apply, "codex_step",
                        lambda *a, **k: apply.StepResult("Codex", "skipped", [], facts={"skipped:codex"}))
    _boot(use_loadout=True)
    assert (paths.codex_home() / "config.toml").read_text(encoding="utf-8").strip() == PLAIN.strip()
    assert "put your server back" in capsys.readouterr().out


def test_rollback_when_apply_config_skips_its_write(fake_home, fake_runner, monkeypatch):
    _plain(fake_home, fake_runner)
    _fake_remove(monkeypatch, [])
    monkeypatch.setattr(codex, "apply_config", lambda *a, **k: [])
    _boot(use_loadout=True)
    assert "my-serena" in (paths.codex_home() / "config.toml").read_text(encoding="utf-8")


def test_keep_own_reaches_adopt(fake_home, fake_runner, monkeypatch):
    _plain(fake_home, fake_runner)
    seen = []
    monkeypatch.setattr(bootstrap.adopt, "run", lambda *a, **k: seen.append(k) or 0)
    _boot(keep_own=True, adopt_step=True, agents="claude,codex")
    assert seen and all(k.get("keep_own") is True for k in seen)


def test_no_codex_removal_when_codex_cannot_be_set_up(fake_home, fake_runner, monkeypatch, capsys):
    _plain(fake_home, fake_runner)
    events = []
    _fake_remove(monkeypatch, events)
    monkeypatch.setattr(codex, "unavailable", lambda *a, **k: "Codex is not installed")
    _boot(use_loadout=True)
    assert events == []
    assert "Serena: yours kept: Codex is not set up in this run" in capsys.readouterr().out
    assert "my-serena" in (paths.codex_home() / "config.toml").read_text(encoding="utf-8")


def test_exception_after_removal_still_rolls_back(fake_home, fake_runner, monkeypatch, capsys):
    _plain(fake_home, fake_runner)
    _fake_remove(monkeypatch, [])

    def boom(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(apply, "codex_step", boom)
    with pytest.raises(RuntimeError):
        _boot(use_loadout=True)
    assert (paths.codex_home() / "config.toml").read_text(encoding="utf-8").strip() == PLAIN.strip()
    assert "put your server back" in capsys.readouterr().out


def test_failed_removal_makes_bootstrap_return_1(fake_home, fake_runner, monkeypatch):
    _plain(fake_home, fake_runner)
    monkeypatch.setattr(codex, "remove_server", lambda name, bk: f"mcp {name}: failed: nope")
    assert _boot(use_loadout=True) == 1


def test_failed_rollback_makes_bootstrap_return_1(fake_home, fake_runner, monkeypatch):
    _plain(fake_home, fake_runner)
    _fake_remove(monkeypatch, [])
    monkeypatch.setattr(apply, "codex_step", lambda *a, **k: apply.StepResult("Codex", "failed", []))
    _reinsert_fails(monkeypatch)
    assert _boot(use_loadout=True) == 1


def test_exception_inside_the_serena_pass_rolls_back_earlier_removals(fake_home, fake_runner, monkeypatch, capsys):
    _plain(fake_home, fake_runner)
    cfg = paths.codex_home() / "config.toml"
    second = PLAIN.replace("my-serena", "serena")
    cfg.write_text(PLAIN + second, encoding="utf-8")
    _fake_remove(monkeypatch, [])
    asked = []

    def ask(q):
        if "Serena" not in q and "serena" not in q:
            return "n"
        asked.append(q)
        if len(asked) > 1:
            raise KeyboardInterrupt
        return "y"
    with pytest.raises(KeyboardInterrupt):
        _boot(ask=ask, interactive=True, yes=False)
    assert "my-serena" in cfg.read_text(encoding="utf-8")
    assert "put your server back" in capsys.readouterr().out
