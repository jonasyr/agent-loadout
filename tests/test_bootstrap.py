import json
import os
import subprocess
import sys

from loadout import bootstrap as b, paths


def test_personal_wizard_renders_template(fake_home, fake_runner):
    answers = iter(["", "Max", "Student", "Python", "short answers"])
    b.ensure_personal(lambda q: next(answers))
    me = (paths.personal_root() / "rules/me.md").read_text()
    assert "Max" in me and "Python" in me and "{{" not in me
    assert json.loads((paths.personal_root() / "settings.json").read_text()) == {}


def test_personal_clone(fake_home, fake_runner):
    answers = iter(["git@github.com:me/loadout-personal.git"])
    b.ensure_personal(lambda q: next(answers))
    assert ["git", "clone", "git@github.com:me/loadout-personal.git", str(paths.personal_root())] in fake_runner.calls


def test_secrets_setup_idempotent(fake_home, fake_runner):
    (fake_home / ".bashrc").write_text("# mine\n")
    b.setup_secrets()
    b.setup_secrets()
    rc = (fake_home / ".bashrc").read_text()
    assert rc.count(b.RC_MARKER) == 1
    if os.name != "nt":
        assert oct(paths.secrets_file().stat().st_mode & 0o777) == "0o600"


def test_setup_plugins_adds_marketplaces_and_installs_missing(fake_home, fake_runner):
    (paths.personal_root()).mkdir(parents=True)
    from loadout import runner
    fake_runner.responses[("claude", "plugin", "marketplace", "list")] = runner.Result(0, "claude-plugins-official\nimpeccable\n", "")
    b.setup_plugins()
    assert ["claude", "plugin", "marketplace", "add", "jonasyr/agent-loadout"] in fake_runner.calls
    assert ["claude", "plugin", "marketplace", "add", "pbakaus/impeccable"] not in fake_runner.calls
    assert ["claude", "plugin", "install", "loadout@agent-loadout", "--scope", "user"] in fake_runner.calls


def test_fresh_home_bootstrap_end_to_end(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home)}
    script = paths.kit_root() / "bin" / "loadout"
    proc = subprocess.run([sys.executable, str(script), "bootstrap", "--yes", "--no-plugins", "--no-adopt"],
                          input="\nTester\nDev\nPython\nnone\n", env=env, capture_output=True, text=True, timeout=120)
    assert (home / ".claude/rules/loadout/tooling.md").exists(), proc.stdout + proc.stderr
    assert (home / ".claude/rules/personal/me.md").exists()
    settings = json.loads((home / ".claude/settings.json").read_text())
    assert settings["enabledPlugins"]["loadout@agent-loadout"] is True
    assert (home / ".config/loadout/secrets.env").exists()


def test_bootstrap_backs_up_existing_settings(fake_home, fake_runner):
    (fake_home / ".claude").mkdir()
    (fake_home / ".claude/settings.json").write_text('{"theme": "dark"}\n')
    answers = iter(["", "Max", "Dev", "Python", "none"])
    b.bootstrap(False, True, False, False, lambda q: next(answers))
    manifests = list(paths.backups_root().rglob("manifest.json"))
    assert manifests
    steps = [s for m in manifests for s in json.loads(m.read_text())["steps"]]
    restore = [s for s in steps if "restore-file" in s["undo"]
               and s["undo"]["restore-file"][1] == str(fake_home / ".claude/settings.json")]
    assert restore
    assert json.loads(open(restore[0]["undo"]["restore-file"][0]).read()) == {"theme": "dark"}


def test_bootstrap_rerun_makes_no_new_backup(fake_home, fake_runner, capsys):
    (fake_home / ".claude").mkdir()
    (fake_home / ".claude/settings.json").write_text('{"theme": "dark"}\n')
    answers = lambda q: "x"
    b.bootstrap(False, True, False, False, answers)
    before = sorted(paths.backups_root().iterdir())
    capsys.readouterr()
    b.bootstrap(False, True, False, False, answers)
    assert sorted(paths.backups_root().iterdir()) == before
    assert "backup:" not in capsys.readouterr().out


def test_secrets_creates_rc_from_shell(fake_home, fake_runner, monkeypatch):
    monkeypatch.setenv("SHELL", "/bin/zsh")
    b.setup_secrets()
    b.setup_secrets()
    assert (fake_home / ".zshrc").read_text().count(b.RC_MARKER) == 1
    assert not (fake_home / ".bashrc").exists()
