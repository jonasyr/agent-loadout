"""Adopt inside bootstrap with --yes: one line instead of an unselected list."""
import pytest

from loadout import adopt, inventory, out, secrets
from loadout.inventory import Item, Verdict


def _v(name, action):
    return Verdict(Item("binary", name), action, "r", name)


@pytest.fixture
def setup(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(out, "VERBOSE", False)
    monkeypatch.setattr(inventory, "collect", lambda with_versions=True: [])
    for fn in ("scan_all", "scan_personal", "scan_codex"):
        monkeypatch.setattr(secrets, fn, lambda: [])

    def put(verdicts):
        monkeypatch.setattr(inventory, "classify", lambda items: verdicts)
    return put


def _run(embedded):
    return adopt.run(apply_changes=True, groups=None, skip=set(), yes=True, ask=lambda q: "",
                     with_versions=False, interactive=True, embedded=embedded)


def test_embedded_yes_prints_one_line_and_no_nothing_selected(setup, capsys):
    setup([_v("a", "update"), _v("b", "update"), _v("c", "install"), _v("d", "keep")])
    assert _run(True) == 0
    text = capsys.readouterr().out
    assert "nothing selected" not in text and "suggestion" not in text
    assert text.strip().splitlines() == [
        "Your existing setup: 2 tool updates (loadout update), 1 tool to install (loadout adopt)"]


def test_embedded_yes_all_fine_prints_nothing(setup, capsys):
    setup([_v("d", "keep")])
    assert _run(True) == 0
    assert capsys.readouterr().out.strip() == ""


def test_not_embedded_yes_unchanged(setup, capsys):
    setup([_v("a", "update"), _v("d", "keep")])
    assert _run(False) == 0
    text = capsys.readouterr().out
    assert "suggestion" in text and "nothing selected" in text


def test_yes_line_counts_review_and_own():
    line = adopt.yes_line([_v("a", "review"), _v("b", "own"), _v("c", "remove")], [])
    assert line == "Your existing setup: 2 to review (loadout adopt)"
    assert adopt.yes_line([_v("c", "remove")], []) is None


def _boot(**kw):
    from loadout import bootstrap
    args = dict(install=False, yes=True, plugins=False, adopt_step=True, ask=lambda q: "", interactive=False,
                agents="claude", personal="new")
    args.update(kw)
    return bootstrap.bootstrap(**args)


def test_adopt_step_silent_when_nothing(setup, capsys, monkeypatch):
    setup([_v("d", "keep")])
    monkeypatch.setattr(out, "VERBOSE", False)
    _boot(interactive=True)
    text = capsys.readouterr().out
    assert "Adopt existing setup" not in text
    assert "\n\n\n" not in text  # no empty step's blank lines left behind


def test_adopt_step_prints_when_secrets(setup, capsys, monkeypatch):
    setup([_v("d", "keep")])
    finding = secrets.Finding("srv", "env", "TOKEN", "x" * 40, "project .mcp.json", False)
    monkeypatch.setattr(secrets, "scan_all", lambda: [finding])
    monkeypatch.setattr(out, "VERBOSE", False)
    _boot(interactive=True)
    text = capsys.readouterr().out
    assert "Plaintext secrets" in text and "srv" in text and "TOKEN" in text
    monkeypatch.setattr(out, "VERBOSE", True)
    _boot(interactive=True)
    assert "== Adopt existing setup" in capsys.readouterr().out


def test_adopt_output_survives_an_error(fake_home, fake_runner, monkeypatch, capsys):
    # final review: lines adopt printed before it raised must not vanish with the held-back buffer
    import pytest
    from loadout import adopt, bootstrap, out
    monkeypatch.setattr(out, "VERBOSE", False)
    (fake_home / ".config/loadout/personal").mkdir(parents=True, exist_ok=True)

    def run(**k):
        print("removed duplicate x (backup kept)")
        raise RuntimeError("broken file")
    monkeypatch.setattr(adopt, "run", run)
    with pytest.raises(RuntimeError):
        bootstrap.bootstrap(install=False, yes=True, plugins=False, adopt_step=True, ask=lambda q: "",
                            interactive=False)
    assert "removed duplicate x (backup kept)" in capsys.readouterr().out
