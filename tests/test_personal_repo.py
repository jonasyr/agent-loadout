"""The personal layer as a private git repo: bootstrap points there, and a private clone never waits on a prompt."""
from loadout import bootstrap as b, paths, runner

HOWTO = "personal-repo.md"  # the full path uses the platform separator


def test_clone_never_waits_for_a_password_prompt(fake_home, fake_runner):
    """Captured output hides git's prompt; on a new machine it would hang bootstrap until the timeout."""
    b.ensure_personal(lambda q: "https://github.com/me/loadout-personal")
    i = next(n for n, c in enumerate(fake_runner.calls) if c[:2] == ["git", "clone"])
    env = fake_runner.envs[i]
    assert env and env.get("GIT_TERMINAL_PROMPT") == "0" and "PATH" in env


def test_failed_clone_names_both_ways_to_get_access(fake_home, fake_runner):
    fake_runner.responses[("git", "clone")] = runner.Result(128, "", "fatal: could not read Username")
    message, ok = b.ensure_personal(lambda q: "https://github.com/me/loadout-personal")
    assert not ok
    assert "`gh auth login`, then `gh auth setup-git`" in message  # no &&: Windows PowerShell 5.1 lacks it
    assert "SSH URL" in message and "re-run bootstrap" in message


def test_failed_clone_without_gh_does_not_suggest_gh_login(fake_home, fake_runner):
    """Plain `loadout bootstrap` installs nothing, so gh may be missing."""
    fake_runner.missing.add("gh")
    fake_runner.responses[("git", "clone")] = runner.Result(128, "", "fatal: could not read Username")
    message, ok = b.ensure_personal(lambda q: "https://github.com/me/loadout-personal")
    assert not ok and "gh auth login" not in message and "SSH URL" in message


def test_starter_message_points_to_the_how_to(fake_home, fake_runner):
    answers = iter(["", "Max", "Student", "Python", "short answers"])
    message, ok = b.ensure_personal(lambda q: next(answers))
    assert ok and "private git repo" in message and HOWTO in message


def test_still_to_do_suggests_a_repo_until_the_layer_is_one(fake_home, fake_runner):
    root = paths.personal_root()
    root.mkdir(parents=True)
    assert any("private git repo" in line and HOWTO in line for line in b.still_to_do("linux"))
    (root / ".git").mkdir()
    assert not any("private git repo" in line for line in b.still_to_do("linux"))


def test_still_to_do_says_nothing_without_a_personal_layer(fake_home, fake_runner):
    assert not any("private git repo" in line for line in b.still_to_do("linux"))


def test_failed_clone_leaves_no_personal_folder_so_the_next_run_asks_again(fake_home, fake_runner, monkeypatch):
    """Adopt (CLAUDE.md -> rules/me.md) and the preferences wizard write into the personal layer; after a failed
    clone they must not, or the next bootstrap finds a partial folder and never asks for the URL again."""
    from loadout import adopt, bootstrap
    fake_runner.responses[("git", "clone")] = runner.Result(128, "", "fatal: could not read Username")
    (fake_home / ".claude").mkdir(exist_ok=True)
    (fake_home / ".claude/CLAUDE.md").write_text("# my old global instructions\n")
    from loadout import configure
    ran = []
    monkeypatch.setattr(adopt, "run", lambda **kw: ran.append("adopt"))
    monkeypatch.setattr(configure, "wizard", lambda *a, **kw: ran.append("wizard"))
    answers = iter(["https://github.com/me/loadout-personal"])
    code = bootstrap.bootstrap(install=False, yes=False, plugins=False, adopt_step=True,
                               ask=lambda q: next(answers, "y"), interactive=True)
    assert code == 1
    assert not paths.personal_root().exists()
    assert ran == [], "neither the wizard nor adopt may run without a personal layer"
