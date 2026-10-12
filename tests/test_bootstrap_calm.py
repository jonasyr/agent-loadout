"""Calm bootstrap output (default): one status line per step, problems always, details with --verbose."""
import pytest

from loadout import bootstrap, check, out


@pytest.fixture
def calm(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(out, "VERBOSE", False)
    (fake_home / ".config/loadout/personal").mkdir(parents=True)
    return fake_home


def _run(**kw):
    args = dict(install=False, yes=True, plugins=False, adopt_step=False, ask=lambda q: "", interactive=False)
    args.update(kw)
    return bootstrap.bootstrap(**args)


def _status_names(text):
    return [line.split(maxsplit=1)[-1] for line in text.splitlines() if line[:1] in ("✓", "!", "✗")]


def test_calm_bootstrap_is_one_line_per_step(calm, capsys):
    _run()
    text = capsys.readouterr().out
    assert text.startswith(bootstrap.INTRO)
    names = _status_names(text)
    for name in ("Prerequisites", "Personal layer", "Rules and settings", "Secrets", "PATH", "Health check"):
        assert any(n.startswith(name) for n in names), (name, text)
    assert "== " not in text and "[ok  ]" not in text and "linked " not in text
    assert "Next: run `claude`" in text


def test_calm_bootstrap_shows_failed_plugin_line(calm, capsys, monkeypatch):
    monkeypatch.setattr(bootstrap, "setup_plugins", lambda **kw: ["plugin x@y: failed: no network"])
    _run(plugins=True)
    text = capsys.readouterr().out
    assert "  plugin x@y: failed: no network" in text
    assert any(line.startswith("! Plugins") for line in text.splitlines()), text


def test_calm_bootstrap_lists_failed_checks(calm, capsys, monkeypatch):
    monkeypatch.setattr(check, "run_checks", lambda: [check.CheckResult("a", True), check.CheckResult("b", False, "bad", "fix")])
    assert _run() == 1
    text = capsys.readouterr().out
    assert "1 of 2 OK" in text and "[FAIL] b: bad" in text


def test_verbose_bootstrap_keeps_the_details(calm, capsys, monkeypatch):
    monkeypatch.setattr(out, "VERBOSE", True)
    _run()
    text = capsys.readouterr().out
    assert "== Prerequisites" in text and "[ok  ]" in text


def test_calm_bootstrap_prints_one_undo_line_after_adopt(calm, capsys, monkeypatch):
    from loadout import adopt
    calls = []

    def fake_run(**kw):
        calls.append(kw)
        adopt.LAST_BACKUP = calm / "bk"
        return 0

    monkeypatch.setattr(adopt, "run", fake_run)
    _run(adopt_step=True)
    text = capsys.readouterr().out
    assert calls and calls[0]["embedded"] is True
    assert text.count(adopt.UNDO_LINE) == 1


def test_calm_bootstrap_has_no_separate_new_terminal_line(calm, capsys, monkeypatch):
    monkeypatch.setattr(bootstrap, "setup_path", lambda bk: (["added the tool folders to PATH in ~/.bashrc"], True))
    _run()
    text = capsys.readouterr().out
    assert "Open a new terminal" not in text and "Next: run `claude` in a new terminal." in text
