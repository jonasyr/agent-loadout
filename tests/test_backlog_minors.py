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


def test_demo_sandbox_commits_as_demo_with_a_relative_home(tmp_path):
    """The sandbox's git identity must come from its own file, whatever HOME_DIR looks like (relative paths too)."""
    import os
    import subprocess
    import pytest
    from loadout import paths
    if os.name == "nt":
        pytest.skip("bash script")
    env = {"PATH": os.environ["PATH"], "HOME": str(tmp_path / "outer-home")}  # never the real home
    p = subprocess.run(["bash", str(paths.kit_root() / "demo/sandbox.sh"), "demo-home"], cwd=tmp_path, env=env,
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    author = subprocess.run(["git", "-C", str(tmp_path / "demo-home/my-app"), "log", "-1", "--format=%an <%ae>"],
                            capture_output=True, text=True, env=env).stdout.strip()
    assert author == "demo <demo@example.com>"
    assert not (tmp_path / "outer-home/.gitconfig").exists()


def test_calm_bootstrap_says_once_that_files_are_copied(fake_home, fake_runner, monkeypatch, capsys):
    """Without symlinks loadout copies files, which behaves differently (edits in place are lost on refresh)."""
    from loadout import link, out
    monkeypatch.setattr(out, "VERBOSE", False)
    (fake_home / ".config/loadout/personal").mkdir(parents=True)
    copied = [f"copied /kit/rules/{n}.md -> /home/.claude/rules/loadout/{n}.md (symlinks unavailable)" for n in ("a", "b")]
    monkeypatch.setattr(link, "link_all", lambda bk, retry_symlinks=False: copied)
    bootstrap.bootstrap(install=False, yes=True, plugins=False, adopt_step=False, ask=lambda q: "", interactive=False)
    text = capsys.readouterr().out
    warnings = [line for line in text.splitlines() if "symlinks unavailable" in line]
    assert len(warnings) == 1 and "copies" in warnings[0] and "Developer Mode" in warnings[0], text


def test_failed_install_line_names_the_tool(fake_home, fake_runner):
    """The note prints after the status line, away from its "installing …" line, so it must say which tool failed."""
    from loadout import catalog
    # a wanted tool with an install command on this platform and no prerequisites (rtk has none on Windows)
    entry = next(e for e in catalog.binaries() if e["status"] in ("core", "recommended") and not e.get("helper") and not e.get("needs")
                 and catalog.platform_cmds(e, "install"))
    name = entry["id"]
    fake_runner.missing.add(name)
    for cmd in catalog.platform_cmds(entry, "install"):
        fake_runner.responses[tuple(cmd[:2])] = runner.Result(1, "", "network down")
    notes = []
    bootstrap.check_prereqs(True, lambda q: "", notes=notes)
    failed = [n for n in notes if n.startswith("failed")]
    assert failed and all(name in n for n in failed), notes
    assert all(not line.startswith(" ") for note in notes for line in note.splitlines()[:1])


def test_anchors_ignore_comments_in_code_blocks(tmp_path):
    """A `# comment` in a bash block is not a heading; counting it could hide a broken link."""
    from test_repo_static import _anchors
    page = tmp_path / "page.md"
    page.write_text("# Real heading\n\n```bash\n# log in to GitHub\ngh auth login\n```\n", encoding="utf-8")
    assert _anchors(page) == {"real-heading"}
