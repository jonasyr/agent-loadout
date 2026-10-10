import json

from loadout import detect, paths, profiles, project, scaffold


def test_detect_profiles(tmp_path):
    p = tmp_path / "my-thesis"
    (p / "app").mkdir(parents=True)
    (p / "sonar-project.properties").write_text("sonar.projectKey=x")
    (p / "app/build.gradle.kts").write_text('plugins { id("com.android.application") }')
    (p / "package.json").write_text(json.dumps({"dependencies": {"react": "19"}}))
    (p / ".env.example").write_text("DATABASE_URL=postgres://x\n")
    assert detect.detect_profiles(p) == ["sonar", "android", "web", "db", "thesis"]


def test_detect_ignores_vendored_dirs(tmp_path):
    (tmp_path / "node_modules/x").mkdir(parents=True)
    (tmp_path / "node_modules/x/build.gradle").write_text("com.android")
    (tmp_path / "node_modules/x/paper.tex").write_text("")
    assert detect.detect_profiles(tmp_path) == []


def test_apply_profile_merges_and_is_idempotent(tmp_path):
    proj = tmp_path / "p"
    (proj / ".claude").mkdir(parents=True)
    (proj / ".claude/settings.json").write_text(json.dumps({"permissions": {"allow": ["Bash(x)"]}}))
    prof = profiles.load_profile("web")
    changed = profiles.apply_profile(prof, proj)
    assert {c.name for c in changed} == {"settings.json", ".mcp.json"}
    settings = json.loads((proj / ".claude/settings.json").read_text())
    assert settings["permissions"] == {"allow": ["Bash(x)"]}
    assert settings["disabledMcpjsonServers"] == ["chrome-devtools"]
    assert profiles.apply_profile(prof, proj) == []


def test_personal_profile_overrides_kit(fake_home, tmp_path):
    pdir = fake_home / ".config/loadout/personal/profiles"
    pdir.mkdir(parents=True)
    (pdir / "web.json").write_text(json.dumps({"description": "mine"}))
    assert profiles.load_profile("web").description == "mine"


def test_unknown_profile_raises():
    try:
        profiles.load_profile("nope")
    except ValueError as err:
        assert "available" in str(err)
    else:
        raise AssertionError("expected ValueError")


def test_scaffold_creates_missing_never_overwrites(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/README.md").write_text("mine")
    created, notes = scaffold.scaffold(tmp_path)
    names = {c.relative_to(tmp_path).as_posix() for c in created}
    assert names == {"AGENTS.md", "CLAUDE.md", "docs/adr/README.md"}
    assert (tmp_path / "docs/README.md").read_text() == "mine"
    assert tmp_path.name in (tmp_path / "AGENTS.md").read_text()
    assert scaffold.scaffold(tmp_path)[0] == []


def test_scaffold_skips_agents_when_claude_md_exists(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# existing instructions")
    created, notes = scaffold.scaffold(tmp_path)
    names = {c.relative_to(tmp_path).as_posix() for c in created}
    assert "AGENTS.md" not in names and "CLAUDE.md" not in names
    assert any("onboard" in n for n in notes)


def test_gitignore_idempotent(tmp_path):
    (tmp_path / ".gitignore").write_text("node_modules")
    assert scaffold.ensure_gitignore(tmp_path) == [".claude/settings.local.json", ".serena/cache/"]
    assert scaffold.ensure_gitignore(tmp_path) == []
    assert (tmp_path / ".gitignore").read_text().startswith("node_modules\n")


def test_init_applies_profiles_installs_and_scaffolds(tmp_path, fake_runner):
    proj = tmp_path / "p"
    proj.mkdir()
    (proj / ".git").mkdir()
    rc = project.init(proj, ["sonar"], yes=True, install=True, dry_run=False, ask=lambda q: "")
    assert rc == 0
    assert ["claude", "plugin", "install", "sonarqube@claude-plugins-official", "--scope", "project"] in fake_runner.calls
    assert (proj / "AGENTS.md").exists()


def test_init_dry_run_changes_nothing(tmp_path, fake_runner):
    proj = tmp_path / "p"
    proj.mkdir()
    (proj / ".git").mkdir()
    project.init(proj, ["db"], yes=True, install=True, dry_run=True, ask=lambda q: "")
    assert list(proj.iterdir()) == [proj / ".git"]
    assert fake_runner.calls == []


def test_init_offers_git_init(tmp_path, fake_runner):
    proj = tmp_path / "p"
    proj.mkdir()
    project.init(proj, [], yes=False, install=False, dry_run=False, ask=lambda q: "y" if "git init" in q else "-")
    assert ["git", "init"] in fake_runner.calls


def test_init_non_interactive_applies_no_profiles(tmp_path, fake_home, fake_runner, capsys):
    from loadout import project
    (tmp_path / "proj").mkdir()
    (tmp_path / "proj/paper.tex").write_text("x")
    project.init(tmp_path / "proj", [], False, True, False, lambda q: "", interactive=False)
    out = capsys.readouterr().out
    assert "non-interactive" in out
    assert not [c for c in fake_runner.calls if c[:3] == ["claude", "plugin", "install"]]
    assert ["git", "init"] not in fake_runner.calls


def test_init_validates_all_profile_names_first(tmp_path, fake_home, fake_runner):
    import pytest
    from loadout import project
    (tmp_path / "p").mkdir()
    with pytest.raises(ValueError, match="thesi"):
        project.init(tmp_path / "p", ["web", "thesi"], True, False, False, lambda q: "")
    assert not (tmp_path / "p/.claude/settings.json").exists()


def test_detect_tolerates_odd_package_json(tmp_path):
    for content in ("[]", '{"dependencies": null}', '"x"', "{bad"):
        (tmp_path / "package.json").write_text(content)
        assert "web" not in detect.detect_profiles(tmp_path)


def test_profile_skills_are_copied_and_never_overwritten(fake_home, fake_runner, tmp_path):
    personal = paths.personal_root()
    (personal / "profiles/skills/notes").mkdir(parents=True)
    (personal / "profiles/skills/notes/SKILL.md").write_text("new")
    (personal / "profiles/mine.json").write_text(json.dumps({"description": "m", "skills": ["notes", "missing"]}))
    repo = tmp_path / "repo"
    (repo / ".claude/skills/kept").mkdir(parents=True)
    project.add_profile(repo, "mine", install=False)
    assert (repo / ".claude/skills/notes/SKILL.md").read_text() == "new"
    (repo / ".claude/skills/notes/SKILL.md").write_text("edited")
    project.add_profile(repo, "mine", install=False)
    assert (repo / ".claude/skills/notes/SKILL.md").read_text() == "edited"


def test_profile_skill_messages(fake_home, tmp_path):
    personal = paths.personal_root()
    (personal / "profiles").mkdir(parents=True)
    (personal / "profiles/mine.json").write_text(json.dumps({"skills": ["missing"]}))
    msgs = profiles.copy_skills(profiles.load_profile("mine"), tmp_path)
    assert msgs == ["skill missing: not found in profiles/skills/ (personal layer or kit)"]
