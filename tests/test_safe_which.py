"""Programs are never taken from the current folder (Windows searches it first)."""
import os

from loadout import maintenance, runner


def _tool(folder, name="tool"):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (name + (".cmd" if os.name == "nt" else ""))
    path.write_text("@echo off\n" if os.name == "nt" else "#!/bin/sh\n")
    path.chmod(0o755)
    return path


def test_a_program_in_the_current_folder_is_never_found(tmp_path, monkeypatch):
    _tool(tmp_path / "repo")
    monkeypatch.chdir(tmp_path / "repo")
    monkeypatch.setenv("PATH", os.pathsep.join([".", "", str(tmp_path / "empty")]))
    assert runner.which("tool") is None
    assert runner.have("tool") is False
    assert runner.run(["tool"]).returncode == 127


def test_a_relative_path_entry_is_ignored(tmp_path, monkeypatch):
    _tool(tmp_path / "repo" / "node_modules" / ".bin")
    monkeypatch.chdir(tmp_path / "repo")
    monkeypatch.setenv("PATH", os.path.join("node_modules", ".bin"))
    assert runner.which("tool") is None


def test_the_real_program_is_still_found_behind_a_planted_one(tmp_path, monkeypatch):
    _tool(tmp_path / "repo")  # planted in the repo
    real = _tool(tmp_path / "bin")
    monkeypatch.chdir(tmp_path / "repo")
    monkeypatch.setenv("PATH", os.pathsep.join([".", str(tmp_path / "bin")]))
    assert os.path.normcase(runner.which("tool")) == os.path.normcase(str(real))


def test_a_path_folder_that_is_also_the_current_folder_still_works(tmp_path, monkeypatch):
    real = _tool(tmp_path / "bin")
    monkeypatch.chdir(tmp_path / "bin")
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))
    assert os.path.normcase(runner.which("tool")) == os.path.normcase(str(real))


def test_windows_lookup_skips_the_current_folder(monkeypatch):
    monkeypatch.setattr(runner, "_is_windows", lambda: True)
    monkeypatch.delenv("NoDefaultCurrentDirectoryInExePath", raising=False)
    runner.which("git")
    assert os.environ.get("NoDefaultCurrentDirectoryInExePath") == "1"
    monkeypatch.delenv("NoDefaultCurrentDirectoryInExePath", raising=False)


def test_maintenance_starts_from_home(monkeypatch, fake_home):
    seen = {}
    monkeypatch.setattr(runner.subprocess, "Popen", lambda cmd, **kw: seen.update(kw))
    maintenance._spawn_background()
    assert seen["cwd"] == str(fake_home)


def test_typecheck_hook_uses_the_absolute_path(tmp_path, monkeypatch):
    import importlib.util
    from loadout import paths
    spec = importlib.util.spec_from_file_location("tc", paths.kit_root() / "plugins/loadout/hooks/typecheck.py")
    tc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tc)
    _tool(tmp_path / "repo", "pyright")  # planted in the project
    real = _tool(tmp_path / "bin", "pyright")
    monkeypatch.chdir(tmp_path / "repo")
    (tmp_path / "repo" / "a.py").write_text("x = 1\n")
    monkeypatch.setenv("PATH", ".")
    assert tc.checks([tmp_path / "repo" / "a.py"]) == []  # a pyright in the project folder is not used
    monkeypatch.setenv("PATH", os.pathsep.join([".", str(tmp_path / "bin")]))
    assert os.path.normcase(tc.checks([tmp_path / "repo" / "a.py"])[0][0][0]) == os.path.normcase(str(real))


def test_typecheck_never_passes_cmd_metacharacters_to_a_windows_shim(tmp_path, monkeypatch):
    import importlib.util
    from loadout import paths
    spec = importlib.util.spec_from_file_location("tc2", paths.kit_root() / "plugins/loadout/hooks/typecheck.py")
    tc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tc)
    monkeypatch.setattr(tc, "_is_windows", lambda: True)
    folder = tmp_path / "npm"
    folder.mkdir()
    shim = folder / "pyright.cmd"
    shim.write_text("@echo off\n")
    shim.chmod(0o755)
    monkeypatch.setattr(tc, "_which", lambda name: str(shim))
    bad = tmp_path / "a&calc&.py"
    good = tmp_path / "b.py"
    assert tc.checks([bad]) == []          # cmd.exe would run "calc"
    assert tc.checks([good])[0][0][0] == str(shim)


def test_a_hand_built_env_still_skips_the_current_folder(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(runner, "_is_windows", lambda: True)
    monkeypatch.setattr(runner, "_resolve", lambda name: "/usr/bin/git")
    monkeypatch.setattr(runner.subprocess, "CREATE_NO_WINDOW", 0, raising=False)
    monkeypatch.setattr(runner.subprocess, "run", lambda cmd, **kw: seen.update(kw) or runner.subprocess.CompletedProcess(cmd, 0, "", ""))
    runner.run(["git", "pull"], env={"PATH": "/usr/bin"})
    assert seen["env"]["NoDefaultCurrentDirectoryInExePath"] == "1"
    monkeypatch.delenv("NoDefaultCurrentDirectoryInExePath", raising=False)


def test_windows_lookup_adds_pathext_itself(tmp_path, monkeypatch):
    # Python 3.11's shutil.which does not try PATHEXT for a path with a folder: loadout must
    folder = tmp_path / "bin"
    folder.mkdir()
    (folder / "git.EXE").write_text("")
    monkeypatch.setattr(runner, "_is_windows", lambda: True)
    monkeypatch.setenv("PATHEXT", ".COM;.EXE;.BAT;.CMD")
    monkeypatch.setenv("PATH", str(folder))
    assert runner.which("git") == str(folder / "git.EXE")
    monkeypatch.delenv("NoDefaultCurrentDirectoryInExePath", raising=False)


def test_typecheck_lookup_adds_pathext_itself(tmp_path, monkeypatch):
    import importlib.util
    from loadout import paths
    spec = importlib.util.spec_from_file_location("tc3", paths.kit_root() / "plugins/loadout/hooks/typecheck.py")
    tc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tc)
    folder = tmp_path / "npm"
    folder.mkdir()
    (folder / "pyright.CMD").write_text("")
    monkeypatch.setattr(tc, "_is_windows", lambda: True)
    monkeypatch.setenv("PATHEXT", ".EXE;.CMD")
    monkeypatch.setenv("PATH", str(folder))
    assert tc._which("pyright") == str(folder / "pyright.CMD")
    monkeypatch.delenv("NoDefaultCurrentDirectoryInExePath", raising=False)
