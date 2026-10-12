"""Small fixes from the review backlog (2026-10-12)."""
from loadout import bootstrap, check, runner


def test_gh_login_hints_work_in_windows_powershell(fake_home, fake_runner):
    """Windows PowerShell 5.1 has no &&; the hints name the two commands in order instead."""
    fake_runner.responses[("gh", "auth", "status")] = runner.Result(1, "", "not logged in")
    todo = [line for line in bootstrap.still_to_do("windows") if "gh auth" in line]
    assert todo and all("&&" not in line for line in todo)
    assert "`gh auth login`, then `gh auth setup-git`" in todo[0]
    fix = [r for r in check.run_checks() if r.name == "gh auth"][0].fix
    assert "&&" not in fix and "gh auth login" in fix and "gh auth setup-git" in fix


def test_prerequisite_notes_follow_their_status_line(fake_home, fake_runner, monkeypatch, capsys):
    """A 'missing …' line explains the Prerequisites status, so it belongs under that line, not above it."""
    from loadout import out
    monkeypatch.setattr(out, "VERBOSE", False)
    (fake_home / ".config/loadout/personal").mkdir(parents=True)
    fake_runner.missing.add("rtk")
    bootstrap.bootstrap(install=False, yes=True, plugins=False, adopt_step=False, ask=lambda q: "", interactive=False)
    lines = capsys.readouterr().out.splitlines()
    status = next(i for i, line in enumerate(lines) if "Prerequisites" in line)
    note = next(i for i, line in enumerate(lines) if line.strip().startswith("missing rtk:"))
    assert note > status, "\n".join(lines[: note + 2])
