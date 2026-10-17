"""loadout restore picks a backup (spec Part 6)."""
import pytest

from loadout import __main__ as cli, backup, restore_cmd

NOW = 2_000_000_000.0


def make(desc, ago, tmp_path, repo=None):
    f = tmp_path / f"{desc}.txt"
    f.write_text(desc)
    bk = backup.Backup(description=desc, repo=repo)
    bk._created_at = NOW - ago
    bk.record_created(f, f"{desc} (created)")
    return f


def answers(*values):
    it = iter(values)
    asked = []
    return asked, (lambda q: asked.append(q) or next(it))


def test_it_shows_ten_numbered_then_more_then_restores_the_pick(fake_home, fake_runner, tmp_path, capsys):
    files = [make(f"b{i}", 3600 * (i + 1), tmp_path) for i in range(12)]  # b0 newest
    asked, ask = answers("m", "12", "y")
    assert restore_cmd.run(None, False, False, None, False, ask, True, now=NOW) == 0
    printed = capsys.readouterr().out
    assert asked[0] == "Restore which? [1-10, m = more, Enter = cancel] "
    assert asked[1] == "Restore which? [1-12, m = more, Enter = cancel] " and asked[2] == restore_cmd.CONFIRM
    assert " 1  1 hour ago" in printed and "12  12 hours ago" in printed and "home" in printed and "1 file" in printed
    assert "take away" in printed and str(files[11]) in printed
    assert not files[11].exists() and files[0].exists()


def test_enter_cancels_and_no_restores_nothing(fake_home, fake_runner, tmp_path, capsys):
    f = make("a", 60, tmp_path)
    _, ask = answers("")
    assert restore_cmd.run(None, False, False, None, False, ask, True, now=NOW) == 0
    _, ask = answers("1", "n")
    assert restore_cmd.run(None, False, False, None, False, ask, True, now=NOW) == 0
    assert f.exists() and capsys.readouterr().out.count("nothing restored") == 2


@pytest.mark.parametrize("bad", ["0", "2", "abc"])
def test_a_wrong_answer_is_asked_again_three_times_at_most(fake_home, fake_runner, tmp_path, bad):
    f = make("a", 60, tmp_path)
    asked, ask = answers(bad, bad, bad)
    assert restore_cmd.run(None, False, False, None, False, ask, True, now=NOW) == 0
    assert len(asked) == 3 and f.exists()


def test_more_when_there_is_no_more_says_so(fake_home, fake_runner, tmp_path, capsys):
    make("a", 60, tmp_path)
    _, ask = answers("m", "")
    restore_cmd.run(None, False, False, None, False, ask, True, now=NOW)
    assert "no more backups" in capsys.readouterr().out


def test_an_already_restored_pick_is_refused_before_the_question(fake_home, fake_runner, tmp_path, capsys):
    make("a", 60, tmp_path)
    backup.restore(backup.backups()[0].path)
    asked, ask = answers("1")
    assert restore_cmd.run(None, False, False, None, False, ask, True, now=NOW) == 1
    assert len(asked) == 1 and "--force" in capsys.readouterr().out


def test_without_a_terminal_nothing_is_picked(fake_home, fake_runner, tmp_path, capsys):
    f = make("a", 60, tmp_path)
    assert restore_cmd.run(None, False, False, None, False, lambda q: pytest.fail("asked"), False, now=NOW) == 0
    printed = capsys.readouterr().out
    assert "--last" in printed and f.exists()


def test_last_restores_the_newest_and_shows_what_goes_back(fake_home, fake_runner, tmp_path, capsys):
    old, new = make("old", 7200, tmp_path), make("new", 60, tmp_path)
    assert restore_cmd.run(None, False, True, None, False, lambda q: pytest.fail("asked"), False, now=NOW) == 0
    assert not new.exists() and old.exists() and "take away" in capsys.readouterr().out


def test_repo_filters_and_list_prints(fake_home, fake_runner, tmp_path, capsys):
    repo = tmp_path / "repo"
    make("home-one", 60, tmp_path)
    make("repo-one", 120, tmp_path, repo=repo)
    assert restore_cmd.run(None, True, False, str(repo), False, lambda q: "", False, now=NOW) == 0
    printed = capsys.readouterr().out
    assert "repo-one" in printed and "home-one" not in printed


def test_the_cli_flags_reach_the_picker(fake_home, monkeypatch):
    got = {}
    monkeypatch.setattr(restore_cmd, "run", lambda *a, **k: got.update(args=a) or 0)
    assert cli.main(["restore", "--last", "--repo", "x"]) == 0
    path, list_only, last, repo, force = got["args"][:5]
    assert (path, list_only, last, repo, force) == (None, False, True, "x", False)
