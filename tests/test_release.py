import json
from pathlib import Path

import pytest

from loadout import paths, release, runner

SHA = "c" * 40
R = runner.Result


def log_out(*records):
    """first-parent log output (%s%x00%b%x1e): (subject, body) pairs or bare subjects."""
    return "".join(f"{r[0]}\0{r[1]}\x1e\n" if isinstance(r, tuple) else f"{r}\0\x1e\n" for r in records)
RELEASE_FILES = "pyproject.toml\nCHANGELOG.md\nrelease-status.json\n"


class Repo:
    """A fake kit checkout: files on disk, canned git/gh answers."""

    def __init__(self, tmp_path, fake_runner, monkeypatch):
        self.root = tmp_path / "kit"
        self.root.mkdir()
        (self.root / ".git").mkdir()
        (self.root / "pyproject.toml").write_text('[project]\nname = "agent-loadout"\nversion = "0.2.0"\n', encoding="utf-8")
        (self.root / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
        (self.root / "release-status.json").write_text('{"urgent": [], "withdrawn": []}\n', encoding="utf-8")
        monkeypatch.setattr(paths, "kit_root", lambda: self.root)
        monkeypatch.chdir(self.root)
        monkeypatch.setenv("EDITOR", "myeditor --wait")
        self.fr = fake_runner
        self.respond(*self.git("status", "--porcelain"), result=R(0, "", ""))
        self.respond(*self.git("rev-parse", "--abbrev-ref", "HEAD"), result=R(0, "main\n", ""))
        self.respond(*self.git("rev-parse", "HEAD"), result=R(0, SHA + "\n", ""))
        self.respond(*self.git("rev-parse", "origin/main"), result=R(0, SHA + "\n", ""))
        self.respond(*self.git("tag", "--list"), result=R(0, "v0.1.0\nv0.2.0\nnot-a-tag\n", ""))
        self.respond(*self.git("log"), result=R(0, log_out("feat(cli): add x (#11)", "chore: tidy (#12)", "fix(y): repair (#13)", "refactor!: break (#14)", "docs: words (#15)"), ""))
        self.respond(*self.git("diff", "--cached", "--name-only"), result=R(0, RELEASE_FILES, ""))
        self.respond("gh", "auth", "status", result=R(0, "", ""))
        self.respond("gh", "run", "list", result=R(0, json.dumps([{"status": "completed", "conclusion": "success"}]), ""))
        fake_runner.paths["gh"] = "/usr/bin/gh"

    def respond(self, *prefix, result):
        self.fr.responses[prefix] = result

    def git(self, *tail):
        return ("git", "-C", str(self.root)) + tail

    def mutating(self):
        return [c for c in self.fr.calls if c[:4] == ["git", "-C", str(self.root), "add"]
                or c[3:4] in (["commit"], ["push"]) or c[3:5] == ["tag", "-a"] or c[:3] == ["gh", "release", "create"]]

    def read(self, name):
        return (self.root / name).read_text(encoding="utf-8")


@pytest.fixture
def repo(tmp_path, fake_runner, monkeypatch):
    return Repo(tmp_path, fake_runner, monkeypatch)


def yes(_q):
    return "y"


def no(_q):
    return "n"


def cut(version="0.3.0", **kw):
    args = dict(urgent=False, yes=True, edit=False, ask=yes)
    args.update(kw)
    return release.cut(version, **args)


def refuses(repo, capsys, text, **kw):
    assert cut(**kw) == 1
    assert text in capsys.readouterr().out
    assert repo.mutating() == []
    assert repo.read("pyproject.toml").count('version = "0.2.0"') == 1
    assert repo.read("CHANGELOG.md") == "# Changelog\n"


def test_cut_refuses_outside_the_kit_checkout(repo, capsys, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    refuses(repo, capsys, "kit checkout")


def test_cut_refuses_a_kit_that_is_not_a_git_checkout(repo, capsys):
    (repo.root / ".git").rmdir()
    refuses(repo, capsys, "kit checkout")


def test_cut_refuses_a_branch_that_is_not_main(repo, capsys):
    repo.respond(*repo.git("rev-parse", "--abbrev-ref", "HEAD"), result=R(0, "feat/x\n", ""))
    refuses(repo, capsys, "not main")


def test_cut_refuses_a_dirty_tree(repo, capsys):
    repo.respond(*repo.git("status", "--porcelain"), result=R(0, " M cli/x.py\n", ""))
    refuses(repo, capsys, "not clean")


def test_cut_refuses_head_that_differs_from_origin_main(repo, capsys):
    repo.respond(*repo.git("rev-parse", "origin/main"), result=R(0, "d" * 40 + "\n", ""))
    refuses(repo, capsys, "origin/main")
    assert list(repo.git("fetch", "origin", "main")) in [c[:6] for c in repo.fr.calls]


def test_cut_refuses_when_the_fetch_fails(repo, capsys):
    repo.respond(*repo.git("fetch"), result=R(1, "", "offline"))
    refuses(repo, capsys, "origin/main")


@pytest.mark.parametrize("version", ["1.2", "v0.3.0", "0.3.0-rc1", "0.03.0", "x.y.z", "0.3.0 "])
def test_cut_refuses_a_malformed_version(repo, capsys, version):
    refuses(repo, capsys, "X.Y.Z", version=version)


@pytest.mark.parametrize("version", ["0.2.0", "0.1.5"])
def test_cut_refuses_a_version_not_newer_than_the_newest_tag(repo, capsys, version):
    refuses(repo, capsys, "newest tag", version=version)


def test_cut_refuses_a_version_not_newer_than_a_remote_only_tag(repo, capsys):
    sha = "e" * 40
    repo.respond(*repo.git("ls-remote"), result=R(0, f"{sha}\trefs/tags/v0.3.0\n", ""))
    refuses(repo, capsys, "newest tag")


def test_cut_refuses_a_version_below_the_floor(repo, capsys):
    repo.respond(*repo.git("tag", "--list"), result=R(0, "", ""))
    refuses(repo, capsys, "floor", version="0.1.9")


def test_cut_refuses_without_gh(repo, capsys):
    repo.fr.missing.add("gh")
    refuses(repo, capsys, "gh")


def test_cut_refuses_when_gh_is_not_logged_in(repo, capsys):
    repo.respond("gh", "auth", "status", result=R(1, "", "not logged in"))
    refuses(repo, capsys, "gh auth")


@pytest.mark.parametrize("answer", [
    [{"status": "completed", "conclusion": "failure"}],
    [{"status": "in_progress", "conclusion": ""}],
    [],
])
def test_cut_refuses_without_a_green_ci_run(repo, capsys, answer):
    repo.respond("gh", "run", "list", result=R(0, json.dumps(answer), ""))
    refuses(repo, capsys, "ci.yml")
    cmd = next(c for c in repo.fr.calls if c[:3] == ["gh", "run", "list"])
    assert cmd[3:] == ["--commit", SHA, "--workflow", "ci.yml", "--limit", "1", "--json", "conclusion,status"]


def test_cut_refuses_unreadable_ci_answer(repo, capsys):
    repo.respond("gh", "run", "list", result=R(0, "nope", ""))
    refuses(repo, capsys, "ci.yml")


def test_cut_declined_writes_nothing(repo, capsys):
    assert cut(yes=False, ask=no) == 1
    assert repo.mutating() == []
    assert repo.read("CHANGELOG.md") == "# Changelog\n"
    assert "0.3.0" in capsys.readouterr().out


def test_cut_writes_version_changelog_and_tags_in_order(repo):
    assert cut() == 0
    text = repo.read("pyproject.toml")
    assert 'version = "0.3.0"' in text and "0.2.0" not in text
    log = repo.read("CHANGELOG.md")
    assert log.startswith("# Changelog\n")
    section = log.split("## [0.3.0] - ", 1)[1]
    for bullet in ("- add x (#11)", "- repair (#13)", "- break (#14)"):
        assert bullet in section
    assert "tidy" not in section and "words" not in section
    wanted = [
        list(repo.git("add", "--", "pyproject.toml", "CHANGELOG.md", "release-status.json")),
        list(repo.git("commit", "-m", "chore(release): v0.3.0")),
        list(repo.git("tag", "-a", "v0.3.0", "-m", "loadout 0.3.0")),
        list(repo.git("push", "--atomic", "origin", "main", "v0.3.0")),
    ]
    calls = [c for c in repo.fr.calls if c in wanted or c[:3] == ["gh", "release", "create"]]
    assert calls[:4] == wanted
    gh = calls[4]
    assert len(calls) == 5
    assert gh[:6] == ["gh", "release", "create", "v0.3.0", "--title", "loadout 0.3.0"]
    assert gh[6] == "--notes-file" and gh[-2:] == ["bootstrap.sh", "bootstrap.ps1"]
    # the staged diff is checked after staging and before the commit
    heads = [c[3] for c in repo.fr.calls if c[0] == "git" and len(c) > 3]
    assert heads.index("add") < heads.index("diff") < heads.index("commit")
    assert json.loads(repo.read("release-status.json")) == {"urgent": [], "withdrawn": []}


def test_urgent_lists_the_version(repo):
    assert cut(urgent=True) == 0
    assert json.loads(repo.read("release-status.json"))["urgent"] == ["0.3.0"]


def test_cut_refuses_a_diff_outside_release_files(repo, capsys):
    repo.respond(*repo.git("diff", "--cached", "--name-only"), result=R(0, "pyproject.toml\ncli/loadout/x.py\n", ""))
    assert cut() == 1
    assert "cli/loadout/x.py" in capsys.readouterr().out
    assert not any(c[3:4] in (["commit"], ["push"]) or c[3:5] == ["tag", "-a"] or c[:3] == ["gh", "release", "create"] for c in repo.fr.calls)
    # the fake git cannot revert files; the command to do so must have run
    assert list(repo.git("restore", "--source=HEAD", "--staged", "--worktree", "--", *release.RELEASE_FILES)) in repo.fr.calls


def test_edit_runs_the_editor_on_the_terminal(repo, monkeypatch):
    seen = {}

    def editor(cmd, timeout=None):
        seen["cmd"] = list(cmd)
        Path(cmd[-1]).write_text("## [0.3.0] - 2026-11-03 (edited)\n\n- hand written\n", encoding="utf-8")
        return 0

    monkeypatch.setattr(runner, "run_interactive", editor)
    assert cut(edit=True) == 0
    assert seen["cmd"][:2] == ["myeditor", "--wait"]
    assert not Path(seen["cmd"][-1]).is_relative_to(repo.root)
    assert ["myeditor"] not in [c[:1] for c in repo.fr.calls]  # never through the capturing runner.run
    assert "- hand written" in repo.read("CHANGELOG.md")


def test_a_failing_editor_aborts_before_anything_is_written(repo, capsys, monkeypatch):
    monkeypatch.setattr(runner, "run_interactive", lambda cmd, timeout=None: 1)
    refuses(repo, capsys, "editor", edit=True)


def test_run_interactive_passes_no_capture(monkeypatch):
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"], seen["kw"] = cmd, kw
        return type("P", (), {"returncode": 3})()

    monkeypatch.setattr(runner, "_resolve", lambda b: "/bin/" + b)
    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    assert runner.run_interactive(["ed", "f"], timeout=5) == 3
    assert seen["cmd"] == ["/bin/ed", "f"]
    assert not {"capture_output", "stdout", "stderr", "stdin"} & set(seen["kw"])


def test_run_interactive_missing_binary_is_127(monkeypatch):
    monkeypatch.setattr(runner, "_resolve", lambda b: None)
    monkeypatch.setattr(runner, "_fallback", lambda b: None)
    assert runner.run_interactive(["nope"]) == 127


def test_edit_without_editor_refuses_before_anything(repo, capsys, monkeypatch):
    monkeypatch.delenv("EDITOR", raising=False)
    refuses(repo, capsys, "EDITOR", edit=True)


def test_a_failing_push_stops_before_the_github_release(repo, capsys):
    repo.respond(*repo.git("push"), result=R(1, "", "rejected"))
    assert cut() == 1
    assert not any(c[:3] == ["gh", "release", "create"] for c in repo.fr.calls)
    assert "rejected" in capsys.readouterr().out


# release notes

def sh(*records):
    return R(0, log_out(*records), "")


def test_only_first_parent_pr_subjects_count(repo):
    repo.respond(*repo.git("log"), result=sh("feat: add a (#5)", "Merge branch 'x'", "fix: direct push",
                                             "fix(b): repair (#6)", "docs: no number (#x)"))
    assert release.pr_subjects(repo.root, "v0.2.0") == [("feat: add a", 5), ("fix: direct push", None),
                                                        ("fix(b): repair", 6), ("docs: no number (#x)", None)]
    log = next(c for c in repo.fr.calls if c[3:4] == ["log"])
    assert log[4:] == ["--first-parent", "--format=%s%x00%b%x1e", "v0.2.0..HEAD"]


def test_merge_pull_request_commits_take_the_title_from_the_body(repo):
    repo.respond(*repo.git("log"), result=sh(("Merge pull request #29 from jonasyr/fix/x", "\n\nfix(security): harden things\n\nlonger text"),
                                             ("Merge pull request #30 from o/b", "")))
    assert release.pr_subjects(repo.root, None) == [("fix(security): harden things", 29)]


def test_plain_conventional_commits_count_without_a_number(repo):
    repo.respond(*repo.git("log"), result=sh("feat(wsl): Codex on WSL", "fix!: drop x", "Merge branch 'x'",
                                             "update stuff", "Release things (#3)"))
    assert release.pr_subjects(repo.root, None) == [("feat(wsl): Codex on WSL", None), ("fix!: drop x", None),
                                                    ("Release things", 3)]


def test_a_realistic_mixed_history_becomes_one_section(repo):
    repo.respond(*repo.git("log"), result=sh(
        "feat(release): notes (#81)", "Merge branch 'main' of github.com:o/r",
        ("Merge pull request #29 from o/fix/h", "fix(security): hardening 1"),
        "feat(wsl): Codex on Windows", "chore: tidy", "wip"))
    prs = release.pr_subjects(repo.root, None)
    text = release.notes_section("0.3.0", "2026-11-03", prs, "o/r", None)
    assert "- notes (#81)" in text and "- hardening 1 (#29)" in text and "- Codex on Windows\n" in text
    assert "tidy" not in text and "wip" not in text and "Merge" not in text


def test_without_a_previous_tag_the_whole_history_is_searched(repo):
    release.pr_subjects(repo.root, None)
    log = next(c for c in repo.fr.calls if c[3:4] == ["log"])
    assert log[-1] == "HEAD"


def test_a_failing_git_log_raises(repo):
    repo.respond(*repo.git("log"), result=R(1, "", "boom"))
    with pytest.raises(RuntimeError):
        release.pr_subjects(repo.root, None)


def test_range_starts_at_the_newest_tag_of_any_version(repo):
    repo.respond(*repo.git("tag", "--list"), result=R(0, "v0.1.0\nnot-a-tag\nv0.01.0\n", ""))
    assert release.base_tag(repo.root) == "v0.1.0"
    repo.respond(*repo.git("tag", "--list"), result=R(0, "v0.1.0\nv0.10.0\nv0.9.0\n", ""))
    assert release.base_tag(repo.root) == "v0.10.0"
    repo.respond(*repo.git("tag", "--list"), result=R(0, "", ""))
    assert release.base_tag(repo.root) is None


def test_cut_logs_from_a_tag_below_the_floor(repo):
    repo.respond(*repo.git("tag", "--list"), result=R(0, "v0.1.0\n", ""))
    assert cut(version="0.2.0") == 0
    log = next(c for c in repo.fr.calls if c[3:4] == ["log"])
    assert log[-1] == "v0.1.0..HEAD"


PRS = [("feat(cli): add x", 1), ("fix(y): repair", 2), ("fix(security): close hole", 3), ("feat!: new shape", 4),
       ("docs: words", 5), ("refactor(z): tidy up", 6), ("chore: bump", 7), ("fix: rotate secret", 8)]
SUMMARY = "<!-- one to three sentences for users: what this release brings -->"


def test_sections_follow_keep_a_changelog():
    text = release.notes_section("0.3.0", "2026-11-03", PRS, "o/r", "v0.2.0")
    assert text == f"""## [0.3.0] - 2026-11-03

{SUMMARY}

### Breaking

- new shape (#4)

### Added

- add x (#1)

### Changed

- tidy up (#6)

### Fixed

- repair (#2)

### Security

- close hole (#3)
- rotate secret (#8)

[0.3.0]: https://github.com/o/r/compare/v0.2.0...v0.3.0
"""


def test_a_breaking_footer_and_a_first_release_link():
    text = release.notes_section("0.2.0", "2026-11-03", [("feat: gone BREAKING CHANGE", 9)], "o/r", None)
    assert "### Breaking\n\n- gone BREAKING CHANGE (#9)" in text and "### Added" not in text
    assert text.endswith("[0.2.0]: https://github.com/o/r/releases/tag/v0.2.0\n")


def test_no_user_facing_prs_says_so():
    text = release.notes_section("0.3.0", "2026-11-03", [("docs: x", 1)], "o/r", "v0.2.0")
    assert f"{SUMMARY}\n\n- No user-facing changes.\n" in text and "###" not in text


def test_long_section_is_capped_at_15():
    prs = [(f"feat: item {i}", i) for i in range(1, 21)]
    text = release.notes_section("0.3.0", "2026-11-03", prs, "o/r", "v0.2.0")
    assert text.count("\n- item") == 15
    assert "- item 15 (#15)" in text and "item 16" not in text
    assert "- …and 5 more (see the compare link)" in text


def test_pr_subjects_are_printable_in_the_plan(repo, capsys):
    repo.respond(*repo.git("log"), result=sh("feat: evil \x1b[31mred (#9)"))
    assert cut(yes=False, ask=no) == 1
    out = capsys.readouterr().out
    assert "\x1b" not in out and "\\x1b[31mred" in out


def draft_file(repo):
    return repo.root.parent / "draft.md"


def test_draft_notes_runs_the_checks_and_changes_nothing(repo, capsys):
    out_file = draft_file(repo)
    repo.respond(*repo.git("status", "--porcelain"), result=R(0, " M x\n", ""))
    assert cut(draft_notes=out_file) == 1
    assert not out_file.exists()
    repo.respond(*repo.git("status", "--porcelain"), result=R(0, "", ""))
    capsys.readouterr()
    assert cut(draft_notes=out_file, yes=False, ask=lambda q: pytest.fail("asked")) == 0
    assert capsys.readouterr().out.strip() == f"draft notes for v0.3.0 written to {out_file}; nothing else changed"
    text = out_file.read_text(encoding="utf-8")
    assert text.startswith("## [0.3.0] - ") and "- add x (#11)" in text
    assert repo.mutating() == []
    heads = {c[3] for c in repo.fr.calls if c[0] == "git" and len(c) > 3}
    assert not heads & {"add", "commit", "push", "restore"}
    assert not any(c[3:5] == ["tag", "-a"] for c in repo.fr.calls)
    assert not any(c[:3] == ["gh", "release", "create"] for c in repo.fr.calls)
    assert repo.read("pyproject.toml").count('version = "0.2.0"') == 1
    assert repo.read("CHANGELOG.md") == "# Changelog\n"
    assert repo.read("release-status.json") == '{"urgent": [], "withdrawn": []}\n'


def test_draft_notes_refuses_a_red_ci_run(repo):
    repo.respond("gh", "run", "list", result=R(0, json.dumps([]), ""))
    assert cut(draft_notes=draft_file(repo)) == 1
    assert not draft_file(repo).exists()


def write_notes(repo, text):
    path = repo.root.parent / "notes.md"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.parametrize("text", [
    "## [0.4.0] - 2026-11-03\n\nhello\n",
    "",
    "no heading\n\nhello\n",
    "## [0.3.0] - 2026-11-03\n\n\n",
    "## 0.3.0 (2026-11-03)\n\nhello\n",
])
def test_notes_file_must_carry_this_version(repo, capsys, text):
    refuses(repo, capsys, "notes", notes=write_notes(repo, text))


def test_notes_file_must_exist(repo, capsys):
    refuses(repo, capsys, "notes", notes=repo.root.parent / "missing.md")


def test_notes_file_is_used_for_changelog_and_release_body(repo, monkeypatch):
    import datetime
    # dated today: the release dates the section the day it is released, whatever date the file had
    section = (f"## [0.3.0] - {datetime.date.today().isoformat()}\n\nWhat is new.\n\n### Added\n\n- thing (#1)\n\n"
               "[0.3.0]: https://github.com/o/r/compare/v0.2.0...v0.3.0\n")
    seen = {}
    fake = runner.run

    def spy(cmd, **kw):
        if cmd[:3] == ["gh", "release", "create"]:
            seen["body"] = Path(cmd[cmd.index("--notes-file") + 1]).read_text(encoding="utf-8")
        return fake(cmd, **kw)

    monkeypatch.setattr(runner, "run", spy)
    assert cut(notes=write_notes(repo, section)) == 0
    assert repo.read("CHANGELOG.md").startswith("# Changelog\n\n" + section.strip())
    assert not any(c[3:4] == ["log"] for c in repo.fr.calls)
    body = seen["body"]
    assert "## [" not in body and "[0.3.0]: " not in body and "- thing (#1)" in body
    assert body.endswith("**Full changelog:** https://github.com/o/r/compare/v0.2.0...v0.3.0\n")


def test_edit_and_notes_exclude_each_other(repo, capsys):
    refuses(repo, capsys, "--edit", edit=True, notes=write_notes(repo, "## [0.3.0] - 2026-11-03\n\nx\n"))


def test_draft_notes_and_notes_exclude_each_other(repo, capsys):
    refuses(repo, capsys, "--draft-notes", draft_notes=draft_file(repo),
            notes=write_notes(repo, "## [0.3.0] - 2026-11-03\n\nx\n"))


# withdraw

def withdraw(version="0.2.0", reason="broken", use="0.3.0", **kw):
    args = dict(yes=True, ask=yes)
    args.update(kw)
    return release.withdraw(version, reason, use, **args)


def only_status(repo):
    repo.respond(*repo.git("diff", "--cached", "--name-only"), result=R(0, "release-status.json\n", ""))


def test_withdraw_adds_the_entry_commits_and_pushes(repo):
    repo.respond(*repo.git("tag", "--list"), result=R(0, "v0.2.0\nv0.3.0\n", ""))
    only_status(repo)
    assert withdraw() == 0
    assert json.loads(repo.read("release-status.json"))["withdrawn"] == [
        {"version": "0.2.0", "reason": "broken", "use": "0.3.0"}]
    heads = [c[3] for c in repo.fr.calls if c[0] == "git" and len(c) > 3]
    assert heads.index("commit") < heads.index("push")
    sixes = [c[:6] for c in repo.fr.calls]
    assert list(repo.git("commit", "-m", "chore(release): withdraw v0.2.0")) in sixes
    assert list(repo.git("push", "origin", "main")) in sixes


def test_withdraw_requires_an_existing_newer_use(repo, capsys):
    repo.respond(*repo.git("tag", "--list"), result=R(0, "v0.2.0\nv0.3.0\n", ""))
    only_status(repo)
    for use in ("0.9.0", "0.2.0", "0.1.0", "junk"):
        assert withdraw(use=use) == 1
        assert "use" in capsys.readouterr().out
    assert repo.mutating() == []
    assert json.loads(repo.read("release-status.json"))["withdrawn"] == []


def test_withdraw_without_use_is_allowed(repo):
    only_status(repo)
    assert withdraw(use=None) == 0
    assert json.loads(repo.read("release-status.json"))["withdrawn"][0]["use"] is None


def test_withdraw_refuses_an_unknown_version(repo, capsys):
    assert withdraw(version="0.9.0", use=None) == 1
    assert "v0.9.0" in capsys.readouterr().out
    assert repo.mutating() == []


@pytest.mark.parametrize("setup,text", [
    (lambda r: r.respond(*r.git("rev-parse", "--abbrev-ref", "HEAD"), result=R(0, "dev\n", "")), "not main"),
    (lambda r: r.respond(*r.git("status", "--porcelain"), result=R(0, "?? x\n", "")), "not clean"),
    (lambda r: r.respond(*r.git("rev-parse", "origin/main"), result=R(0, "d" * 40 + "\n", "")), "origin/main"),
    (lambda r: (r.root / ".git").rmdir(), "kit checkout"),
])
def test_withdraw_shares_the_checkout_refusals(repo, capsys, setup, text):
    setup(repo)
    assert withdraw(use=None) == 1
    assert text in capsys.readouterr().out
    assert repo.mutating() == []


def test_withdraw_refuses_a_diff_outside_release_status(repo, capsys):
    assert withdraw(use=None) == 1  # the default diff answer lists pyproject.toml too
    assert not any(c[3:4] in (["commit"], ["push"]) for c in repo.fr.calls)
    assert list(repo.git("restore", "--source=HEAD", "--staged", "--worktree", "--", "release-status.json")) in repo.fr.calls


def test_withdraw_declined_writes_nothing(repo):
    assert withdraw(use=None, yes=False, ask=no) == 1
    assert repo.mutating() == []


# parser

def test_parser_routes_cut_and_withdraw(monkeypatch):
    from loadout.__main__ import build_parser
    calls = []
    monkeypatch.setattr(release, "cut", lambda *a, **k: calls.append(("cut", a, k)) or 0)
    monkeypatch.setattr(release, "withdraw", lambda *a, **k: calls.append(("withdraw", a, k)) or 0)
    p = build_parser()
    a = p.parse_args(["release", "0.3.0", "--urgent", "--edit", "--yes"])
    assert a.func(a) == 0
    a = p.parse_args(["release", "withdraw", "0.2.0", "--reason", "bad", "--use", "0.3.0", "--yes"])
    assert a.func(a) == 0
    assert [c[0] for c in calls] == ["cut", "withdraw"]
    assert calls[0][1][0] == "0.3.0" and calls[0][2]["urgent"] and calls[0][2]["edit"] and calls[0][2]["yes"]
    assert calls[1][1][:3] == ("0.2.0", "bad", "0.3.0")
    a = p.parse_args(["release", "withdraw", "0.2.0"])
    assert a.func(a) == 2


def test_draft_notes_inside_the_checkout_is_refused(repo, capsys):
    inside = repo.root / "sub" / "notes.md"
    assert cut(draft_notes=inside) == 1
    assert "write the draft outside the checkout" in capsys.readouterr().out
    assert not inside.exists() and not inside.parent.exists()


def test_notes_heading_gets_the_release_day(repo):
    import datetime
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    today = datetime.date.today().isoformat()
    section = f"## [0.3.0] - {yesterday}\n\nWhat is new.\n\n- thing (#1)\n"
    assert cut(notes=write_notes(repo, section)) == 0
    changelog = repo.read("CHANGELOG.md")
    assert f"## [0.3.0] - {today}\n" in changelog and yesterday not in changelog
