import pytest

from loadout.__main__ import main


def _help(argv, capsys):
    with pytest.raises(SystemExit):
        main(argv)
    return capsys.readouterr().out


def test_top_level_help_hides_internal_commands(capsys):
    out = _help(["--help"], capsys)
    assert "==SUPPRESS==" not in out
    assert "hook-session-start" not in out and "{" not in out.splitlines()[0]
    for cmd in ("bootstrap", "adopt", "restore", "configure", "init", "profile", "check", "update"):
        assert cmd in out


def test_hidden_commands_still_parse(fake_home, monkeypatch):
    from loadout import maintenance
    monkeypatch.setattr(maintenance, "session_start", lambda now: None)
    assert main(["hook-session-start"]) == 0


def test_configure_help_shows_examples(capsys):
    out = _help(["configure", "--help"], capsys)
    assert "loadout configure set plugin" in out and "--first-run" in out


def test_adopt_help_mentions_own(capsys):
    out = _help(["adopt", "--help"], capsys)
    flat = " ".join(out.split())
    assert "--own" in flat and "your own tools stay as they are" in flat
