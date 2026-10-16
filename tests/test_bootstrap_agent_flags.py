"""Bootstrap needs no terminal: --personal and --answers, and no question without one (spec PR C)."""
import json

import pytest

from loadout import bootstrap, paths, runner


def _never(q):
    pytest.fail(f"asked without a terminal: {q}")


def _answers(tmp_path, data):
    p = tmp_path / "answers.json"
    p.write_text(json.dumps(data))
    return str(p)


def _run(**kw):
    kw.setdefault("ask", _never)
    kw.setdefault("interactive", False)
    return bootstrap.bootstrap(False, kw.pop("yes", False), False, False, agents="claude", **kw)


def test_no_terminal_never_asks_and_creates_a_starter(fake_home, fake_runner):
    _run()
    assert (paths.personal_root() / "rules" / "me.md").exists()


def test_yes_in_a_terminal_asks_nothing(fake_home, fake_runner):
    _run(interactive=True, yes=True)
    assert (paths.personal_root() / "settings.json").exists()


def test_personal_url_is_cloned(fake_home, fake_runner):
    _run(personal="git@github.com:me/personal.git")
    clone = [c for c in fake_runner.calls if c[:2] == ["git", "clone"]]
    assert clone and clone[0][-2:] == ["git@github.com:me/personal.git", str(paths.personal_root())]


def test_a_failed_clone_exits_1_with_the_access_hint(fake_home, fake_runner, capsys):
    fake_runner.responses[("git", "clone")] = runner.Result(128, "", "Permission denied (publickey)")
    assert _run(personal="git@github.com:me/personal.git") == 1
    assert "SSH URL" in capsys.readouterr().out


def test_personal_new_never_clones(fake_home, fake_runner):
    _run(personal="new", interactive=True, ask=lambda q: "")
    assert not [c for c in fake_runner.calls if c[:2] == ["git", "clone"]]


@pytest.mark.parametrize("value", ["", "-upload-pack=x", "--x"])
def test_a_bad_personal_value_is_refused_first(fake_home, fake_runner, value):
    with pytest.raises(ValueError, match="--personal"):
        _run(personal=value)
    assert not paths.personal_root().exists()


def test_answers_fill_the_starter(fake_home, fake_runner, tmp_path):
    _run(answers=_answers(tmp_path, {"about": {"name": "Jonas"}, "preferences": {"answer_language": "german"}}))
    me = (paths.personal_root() / "rules" / "me.md").read_text()
    assert "Jonas" in me and "always answer in German" in me


def test_bad_answers_stop_before_anything_changes(fake_home, fake_runner, tmp_path):
    with pytest.raises(ValueError, match="klingon|answer_language"):
        _run(answers=_answers(tmp_path, {"preferences": {"answer_language": "klingon"}}))
    assert not paths.personal_root().exists()


def test_an_existing_layer_says_the_flags_are_not_used(fake_home, fake_runner, tmp_path, capsys):
    paths.personal_root().mkdir(parents=True)
    _run(personal="new", answers=_answers(tmp_path, {"about": {"name": "Jonas"}}))
    out = capsys.readouterr().out
    assert "apply only to a new one" in out
    assert not (paths.personal_root() / "rules" / "me.md").exists()


def test_the_flags_reach_bootstrap_from_the_cli(fake_home, fake_runner, monkeypatch, tmp_path):
    from loadout import __main__ as main
    seen = {}
    monkeypatch.setattr(bootstrap, "bootstrap", lambda *a, **k: seen.update(k) or 0)
    main.main(["bootstrap", "--personal", "new", "--answers", "a.json"])
    assert seen["personal"] == "new" and seen["answers"] == "a.json"


def test_unused_flags_are_named_in_calm_mode_too(fake_home, fake_runner, tmp_path, capsys, monkeypatch):
    from loadout import out
    monkeypatch.setattr(out, "VERBOSE", False)
    paths.personal_root().mkdir(parents=True)
    _run(personal="new", answers=_answers(tmp_path, {"about": {"name": "Jonas"}}))
    assert "apply only to a new one" in capsys.readouterr().out


def test_answers_with_a_cloned_layer_are_named_as_unused(fake_home, fake_runner, tmp_path, capsys, monkeypatch):
    from loadout import out
    monkeypatch.setattr(out, "VERBOSE", False)
    _run(personal="git@github.com:me/personal.git", answers=_answers(tmp_path, {"about": {"name": "Jonas"}}))
    assert "--answers" in capsys.readouterr().out


def test_personal_is_stripped(fake_home, fake_runner):
    _run(personal="  new ")
    assert not [c for c in fake_runner.calls if c[:2] == ["git", "clone"]]


def test_a_token_in_the_clone_url_is_not_printed(fake_home, fake_runner, capsys):
    token = "ghp" + "_" + "a1b2c3d4e5" * 4  # built at runtime: no token-shaped text in the repo
    _run(personal=f"https://user:{token}@github.com/me/p.git")
    assert token not in capsys.readouterr().out


def test_personal_new_in_any_case_is_a_starter(fake_home, fake_runner):
    _run(personal="New")
    assert not [c for c in fake_runner.calls if c[:2] == ["git", "clone"]]


def test_without_a_terminal_the_answers_are_named_as_applied(fake_home, fake_runner, tmp_path, capsys):
    _run(answers=_answers(tmp_path, {"preferences": {"answer_language": "german"}}))
    assert "your answers and the defaults applied" in capsys.readouterr().out
