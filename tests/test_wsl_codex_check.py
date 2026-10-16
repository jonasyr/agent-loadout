"""loadout check in WSL reports the Windows Codex side read-only and checks only the agents that are on."""
import pytest

from loadout import check, codex, targets, wsl


@pytest.fixture
def wsl2(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)
    return fake_runner


def test_claude_off_skips_claude_and_its_sandbox(wsl2):
    targets.set_agents({"claude": False, "codex": True})
    wsl2.paths["claude"] = "/mnt/c/Users/u/AppData/Roaming/npm/claude"
    wsl2.missing.update({"bwrap", "socat"})
    text = " ".join(p for p, _ in wsl.problems(2, None))
    assert "claude" not in text and "sandbox" not in text


def test_claude_on_still_checks_claude_and_its_sandbox(wsl2):
    targets.set_agents({"claude": True, "codex": False})
    wsl2.paths["claude"] = "/mnt/c/Users/u/AppData/Roaming/npm/claude"
    wsl2.missing.update({"bwrap", "socat"})
    text = " ".join(p for p, _ in wsl.problems(2, None))
    assert "claude resolves" in text and "sandbox" in text


def _windows_side(monkeypatch, home, used=True):
    monkeypatch.setattr(wsl, "codex_side", lambda **k: wsl.CodexSide("both", ["x"], home, used, False))


def test_a_used_windows_side_without_loadout_is_reported(wsl2, tmp_path, monkeypatch):
    targets.set_agents({"claude": False, "codex": True})
    home = tmp_path / "winhome"
    (home / ".codex").mkdir(parents=True)
    _windows_side(monkeypatch, home)
    (r,) = [r for r in check._codex_side() if r.name == "Codex (Windows side)"]
    assert not r.ok and "bootstrap.ps1" in r.fix


def test_a_windows_side_with_loadouts_block_is_ok(wsl2, tmp_path, monkeypatch):
    targets.set_agents({"claude": False, "codex": True})
    home = tmp_path / "winhome"
    (home / ".codex").mkdir(parents=True)
    (home / ".codex" / "AGENTS.md").write_text(f"{codex.START}\nx\n{codex.END}\n")
    _windows_side(monkeypatch, home)
    (r,) = [r for r in check._codex_side() if r.name == "Codex (Windows side)"]
    assert r.ok


def test_an_unused_windows_side_is_not_mentioned(wsl2, tmp_path, monkeypatch):
    targets.set_agents({"claude": False, "codex": True})
    _windows_side(monkeypatch, tmp_path / "winhome", used=False)
    assert check._codex_side() == []


def test_a_shared_codex_home_is_a_warning(wsl2, monkeypatch):
    targets.set_agents({"claude": False, "codex": True})
    monkeypatch.setattr(wsl, "codex_side",
                        lambda **k: wsl.CodexSide("wsl", ["CODEX_HOME points into Windows"], None, False, True))
    assert any(r.name == "Codex home" and not r.ok for r in check._codex_side())


def test_codex_off_reads_no_side(wsl2, monkeypatch):
    targets.set_agents({"claude": True, "codex": False})
    monkeypatch.setattr(wsl, "codex_side", lambda **k: pytest.fail("read with Codex off"))
    assert check._codex_side() == []


def test_outside_wsl_reads_no_side(fake_home, fake_runner, monkeypatch):
    targets.set_agents({"claude": False, "codex": True})
    monkeypatch.setattr(wsl, "codex_side", lambda **k: pytest.fail("read outside WSL"))
    assert check._codex_side() == []


def test_run_checks_includes_the_windows_side(wsl2, tmp_path, monkeypatch):
    targets.set_agents({"claude": False, "codex": True})
    home = tmp_path / "winhome"
    (home / ".codex").mkdir(parents=True)
    _windows_side(monkeypatch, home)
    assert any(r.name == "Codex (Windows side)" for r in check.run_checks())


def _repo(tmp_path, *parts):
    repo = tmp_path.joinpath(*parts)
    (repo / ".git").mkdir(parents=True)
    return repo


def _empty_profile(monkeypatch):
    from loadout import profiles
    monkeypatch.setattr(profiles, "load_profile", lambda name: profiles.Profile(name="web", description=""))


def test_profile_notes_a_repo_on_the_windows_drive(wsl2, tmp_path, monkeypatch, capsys):
    from loadout import project
    repo = _repo(tmp_path, "mnt", "d", "git", "thesis")
    monkeypatch.setattr(wsl, "MOUNT", str(tmp_path / "mnt") + "/")
    _empty_profile(monkeypatch)
    assert project.add_profile(repo, "web", install=False) == 0
    assert capsys.readouterr().out.count("Windows drive") == 1


def test_a_repo_in_the_linux_home_gets_no_note(wsl2, tmp_path, monkeypatch, capsys):
    from loadout import project
    repo = _repo(tmp_path, "home", "u", "thesis")
    monkeypatch.setattr(wsl, "MOUNT", str(tmp_path / "mnt") + "/")
    _empty_profile(monkeypatch)
    project.add_profile(repo, "web", install=False)
    assert "Windows drive" not in capsys.readouterr().out


def test_outside_wsl_no_note(fake_home, fake_runner, tmp_path, monkeypatch):
    repo = _repo(tmp_path, "mnt", "d", "thesis")
    monkeypatch.setattr(wsl, "MOUNT", str(tmp_path / "mnt") + "/")
    assert wsl.repo_note(repo) is None


def test_init_with_two_profiles_notes_the_drive_once(wsl2, tmp_path, monkeypatch, capsys):
    from loadout import project
    repo = _repo(tmp_path, "mnt", "d", "thesis")
    monkeypatch.setattr(wsl, "MOUNT", str(tmp_path / "mnt") + "/")
    _empty_profile(monkeypatch)
    project.init(repo, ["web", "web"], yes=True, install=False, dry_run=False, ask=lambda q: "", interactive=False)
    assert capsys.readouterr().out.count("Windows drive") == 1


def test_a_program_that_cannot_start_is_a_result_not_a_crash(tmp_path, monkeypatch):
    import os
    import sys
    from loadout import runner
    if sys.platform.startswith("win"):
        pytest.skip("POSIX exec")
    bad = tmp_path / "bin" / "cmd.exe"
    bad.parent.mkdir()
    bad.write_bytes(b"MZ\x90\x00 not an ELF binary")  # what WSL sees when Windows interop is off
    bad.chmod(0o755)
    monkeypatch.setenv("PATH", str(bad.parent) + os.pathsep + os.environ.get("PATH", ""))
    res = runner.run(["cmd.exe", "/c", "echo", "%USERPROFILE%"])
    assert res.returncode == 126 and "cmd.exe" in res.stderr


def test_the_windows_side_choice_gets_one_line_not_a_wall_of_warnings(wsl2, tmp_path, monkeypatch):
    targets.set_agents({"claude": False, "codex": True})
    wsl2.paths["codex"] = "/mnt/c/Users/u/AppData/Roaming/npm/codex"
    home = tmp_path / "winhome"
    (home / ".codex").mkdir(parents=True)
    (home / ".codex" / "AGENTS.md").write_text(f"{codex.START}\nx\n{codex.END}\n")
    monkeypatch.setattr(wsl, "codex_side", lambda **k: wsl.CodexSide("windows", ["x"], home, True, False))
    rows = [r for r in check.run_checks() if "codex" in (r.name + r.detail).lower()]
    assert [r.name for r in rows if not r.ok] == []
    assert any(r.name == "Codex" and r.ok and "bootstrap.ps1" in r.detail for r in rows)
