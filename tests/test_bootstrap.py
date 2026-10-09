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
    assert ["git", "clone", "--", "git@github.com:me/loadout-personal.git", str(paths.personal_root())] in fake_runner.calls


def test_secrets_setup_idempotent(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(paths, "platform_key", lambda: "posix")  # rc files; the PowerShell branch is in test_secrets.py
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


STUBBED = ["claude", "uv", "node", "gh", "serena", "codebase-memory-mcp", "rtk", "playwright-cli",
           "pyright", "typescript-language-server", "rust-analyzer", "npm", "npx", "curl", "powershell", "pwsh"]


def _stub_path(tmp_path):
    """A PATH with logging stubs for every external tool, plus the real python and git only."""
    import shutil
    stub = tmp_path / "stub"
    stub.mkdir()
    log = tmp_path / "calls.log"
    for name in STUBBED:
        if os.name == "nt":
            (stub / f"{name}.cmd").write_text(f"@echo off\r\necho {name} %*>>\"{log}\"\r\nexit /b 0\r\n")
        else:
            f = stub / name
            f.write_text(f'#!/bin/sh\necho "{name} $*" >> "{log}"\nexit 0\n')
            f.chmod(0o755)
    git = shutil.which("git")
    if os.name == "nt":
        path = os.pathsep.join([str(stub), os.path.dirname(git), os.path.dirname(sys.executable)])
    else:
        (stub / "git").symlink_to(git)
        (stub / "python3").symlink_to(sys.executable)
        path = str(stub)
    return path, log


def test_fresh_home_bootstrap_end_to_end(tmp_path):
    """Hermetic: temp HOME, no LOADOUT_* variables, stubbed tools, no stdin (so not interactive)."""
    home = tmp_path / "home"
    home.mkdir()
    path, log = _stub_path(tmp_path)
    env = {"HOME": str(home), "USERPROFILE": str(home), "PATH": path, "LANG": "C.UTF-8"}
    for key in ("SYSTEMROOT", "SystemRoot", "TEMP", "TMP", "PATHEXT", "COMSPEC"):
        if key in os.environ:
            env[key] = os.environ[key]
    kit = paths.kit_root()
    status_before = subprocess.run(["git", "status", "--porcelain"], cwd=kit, capture_output=True, text=True).stdout
    proc = subprocess.run([sys.executable, str(kit / "bin" / "loadout"), "bootstrap", "--no-plugins"],
                          stdin=subprocess.DEVNULL, env=env, capture_output=True, text=True, timeout=120)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    assert "non-interactive: skipping adopt" in out and "non-interactive: skipping the configure prompt" in out
    assert (home / ".claude/rules/loadout/tooling.md").exists(), out
    assert (home / ".claude/rules/personal/me.md").exists()
    settings = json.loads((home / ".claude/settings.json").read_text())
    assert settings["enabledPlugins"]["loadout@agent-loadout"] is True
    assert (home / ".config/loadout/secrets.env").exists()
    assert "[warn] plugins installed" in out
    calls = log.read_text() if log.exists() else ""
    for mutating in ("plugin install", "plugin uninstall", "mcp add", "mcp remove", "self update", "upgrade"):
        assert mutating not in calls, calls
    # nothing outside the temp dir changed: the kit checkout is untouched
    assert subprocess.run(["git", "status", "--porcelain"], cwd=kit, capture_output=True, text=True).stdout == status_before


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
    monkeypatch.setattr(paths, "platform_key", lambda: "posix")
    monkeypatch.setenv("SHELL", "/bin/zsh")
    b.setup_secrets()
    b.setup_secrets()
    assert (fake_home / ".zshrc").read_text().count(b.RC_MARKER) == 1
    assert not (fake_home / ".bashrc").exists()


def test_bootstrap_non_interactive_skips_adopt_and_configure(fake_home, fake_runner, capsys):
    from loadout import adopt
    called = []
    import loadout.bootstrap as bmod
    orig = adopt.run
    adopt.run = lambda *a, **k: called.append(1)
    try:
        b.bootstrap(False, False, False, True, lambda q: "", interactive=False)
    finally:
        adopt.run = orig
    out = capsys.readouterr().out
    assert called == []
    assert "non-interactive" in out and "adopt" in out and "configure" in out


def test_bootstrap_clone_failure_sets_exit_code(fake_home, fake_runner, capsys, monkeypatch):
    from loadout import runner
    monkeypatch.setattr(b.check, "run_checks", lambda: [])
    fake_runner.responses[("git", "clone")] = runner.Result(128, "", "repository not found")
    answers = iter(["git@github.com:me/nope.git"] + [""] * 20)
    rc = b.bootstrap(False, True, False, False, lambda q: next(answers), interactive=False)
    assert rc == 1
    assert "clone failed" in capsys.readouterr().out


def test_bootstrap_new_personal_layer_is_recorded_as_created(fake_home, fake_runner):
    bk_steps = []
    b.bootstrap(False, True, False, False, lambda q: "", interactive=False)
    for m in paths.backups_root().rglob("manifest.json"):
        bk_steps += json.loads(m.read_text())["steps"]
    created = {s["undo"].get("created") for s in bk_steps}
    assert str(paths.personal_root() / "rules/me.md") in created
    assert str(paths.personal_root() / "settings.json") in created


def test_bootstrap_wizard_does_not_set_up_plugins_twice(fake_home, fake_runner, monkeypatch):
    from loadout import configure
    calls = []
    monkeypatch.setattr(b, "setup_plugins", lambda: calls.append(1) or [])
    monkeypatch.setattr(configure, "addons", lambda: [])
    answers = iter(["", "", "", "", "", "y"] + [""] * 20)
    b.bootstrap(False, False, True, False, lambda q: next(answers), interactive=True)
    assert calls == [1]
