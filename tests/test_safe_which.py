"""Programs are never taken from the current folder (Windows searches it first)."""
import os

from loadout import maintenance, runner


def test_which_drops_a_result_in_the_current_folder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner.shutil, "which", lambda name, path=None: str(tmp_path / "git.exe"))
    assert runner.which("git") is None
    assert runner.have("git") is False


def test_which_keeps_a_result_elsewhere(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner.shutil, "which", lambda name, path=None: "/usr/bin/git")
    assert runner.which("git") == "/usr/bin/git"


def test_windows_lookup_skips_the_current_folder(monkeypatch):
    monkeypatch.setattr(runner, "_is_windows", lambda: True)
    monkeypatch.delenv("NoDefaultCurrentDirectoryInExePath", raising=False)
    runner.which("git")
    assert os.environ.get("NoDefaultCurrentDirectoryInExePath") == "1"
    monkeypatch.delenv("NoDefaultCurrentDirectoryInExePath", raising=False)


def test_run_refuses_a_program_in_the_current_folder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner.shutil, "which", lambda name, path=None: str(tmp_path / "git.exe"))
    assert runner.run(["git", "status"]).returncode == 127


def test_maintenance_starts_from_home(monkeypatch, fake_home):
    seen = {}
    monkeypatch.setattr(maintenance.subprocess, "Popen", lambda cmd, **kw: seen.update(kw))
    maintenance._spawn_background()
    assert seen["cwd"] == str(fake_home)


def test_typecheck_hook_uses_the_absolute_path(tmp_path, monkeypatch):
    import importlib.util
    from loadout import paths
    spec = importlib.util.spec_from_file_location("tc", paths.kit_root() / "plugins/loadout/hooks/typecheck.py")
    tc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tc)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n")
    monkeypatch.setattr(tc.shutil, "which", lambda name, path=None: str(tmp_path / "pyright.cmd"))
    assert tc.checks([tmp_path / "a.py"]) == []  # a pyright in the project folder is not used
    monkeypatch.setattr(tc.shutil, "which", lambda name, path=None: "/opt/bin/pyright")
    assert tc.checks([tmp_path / "a.py"])[0][0][0] == "/opt/bin/pyright"
