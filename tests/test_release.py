import json
from pathlib import Path

import pytest

from loadout import paths, release, runner

SHA = "c" * 40
R = runner.Result
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
        self.respond(*self.git("log"), result=R(0, "feat(cli): add x\nchore: tidy\nfix(y): repair\nrefactor!: break\ndocs: words\n", ""))
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
    section = log.split("## 0.3.0", 1)[1]
    assert section.startswith(" (")
    for bullet in ("- feat(cli): add x", "- fix(y): repair", "- refactor!: break"):
        assert bullet in section
    assert "chore: tidy" not in section and "docs: words" not in section
    wanted = [
        list(repo.git("add", "--", "pyproject.toml", "CHANGELOG.md", "release-status.json")),
        list(repo.git("commit", "-m", "chore(release): v0.3.0")),
        list(repo.git("tag", "-a", "v0.3.0", "-m", "loadout 0.3.0")),
        list(repo.git("push", "origin", "main", "v0.3.0")),
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


def test_edit_opens_the_editor_on_the_section(repo, monkeypatch):
    seen = {}
    fake = repo.fr

    def editor(cmd, cwd=None, timeout=300, env=None):
        if cmd[0] == "myeditor":
            seen["cmd"] = list(cmd)
            Path(cmd[-1]).write_text("## 0.3.0 (edited)\n\n- hand written\n", encoding="utf-8")
            return R(0, "", "")
        return fake(cmd, cwd=cwd, timeout=timeout, env=env)

    monkeypatch.setattr(runner, "run", editor)
    assert cut(edit=True) == 0
    assert seen["cmd"][:2] == ["myeditor", "--wait"]
    assert not Path(seen["cmd"][-1]).is_relative_to(repo.root)
    assert "- hand written" in repo.read("CHANGELOG.md")


def test_edit_without_editor_refuses_before_anything(repo, capsys, monkeypatch):
    monkeypatch.delenv("EDITOR", raising=False)
    refuses(repo, capsys, "EDITOR", edit=True)


def test_a_failing_push_stops_before_the_github_release(repo, capsys):
    repo.respond(*repo.git("push"), result=R(1, "", "rejected"))
    assert cut() == 1
    assert not any(c[:3] == ["gh", "release", "create"] for c in repo.fr.calls)
    assert "rejected" in capsys.readouterr().out


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
