"""Codex target: the switch in the personal layer, the version gate, restore of codex undo commands."""
import json

from loadout import backup, codex, paths, runner
from loadout.__main__ import main


def test_codex_home_follows_codex_home_env(fake_home, monkeypatch):
    assert paths.codex_home() == fake_home / ".codex"
    monkeypatch.setenv("CODEX_HOME", str(fake_home / "elsewhere"))
    assert paths.codex_home() == fake_home / "elsewhere"
    assert paths.agents_skills() == fake_home / ".agents" / "skills"


def test_switch_is_off_and_undecided_by_default(fake_home):
    assert not codex.enabled() and not codex.decided()


def test_configure_set_target_records_the_choice(fake_home, fake_runner, monkeypatch):
    from loadout import configure
    monkeypatch.setattr(configure, "apply_all", lambda ask: None)
    assert main(["configure", "set", "target", "codex", "on"]) == 0
    assert json.loads(codex.targets_path().read_text()) == {"codex": True}
    assert codex.enabled() and codex.decided()
    assert main(["configure", "set", "target", "codex", "off"]) == 0
    assert not codex.enabled() and codex.decided()


def test_configure_show_names_the_codex_switch(fake_home):
    from loadout import configure
    assert "Codex: off (set with: loadout configure set target codex on|off)" in configure.show()


def test_unavailable_names_missing_and_old_codex(fake_home, fake_runner):
    fake_runner.missing.add("codex")
    assert "not found" in codex.unavailable()
    fake_runner.missing.discard("codex")
    fake_runner.responses[("codex", "--version")] = runner.Result(0, "codex-cli 0.150.1\n", "")
    assert "0.150.1" in codex.unavailable() and "0.161" in codex.unavailable()
    fake_runner.responses[("codex", "--version")] = runner.Result(0, "codex-cli 0.162.1\n", "")
    assert codex.unavailable() is None


def test_restore_runs_codex_but_refuses_others(fake_home, fake_runner):
    bk = backup.Backup(description="test")
    bk.record_command("codex plugin x", ["codex", "plugin", "remove", "x@y"])
    bk.record_command("evil", ["sh", "-c", "rm -rf ~"])
    lines, ok, _ = backup.restore(bk.root)
    assert ["codex", "plugin", "remove", "x@y"] in fake_runner.calls
    assert not any(c[0] == "sh" for c in fake_runner.calls)
    assert any("refusing" in line for line in lines) and not ok
