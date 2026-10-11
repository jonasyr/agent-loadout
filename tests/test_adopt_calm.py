"""The calm adopt view (default); verbose keeps today's full plan."""
import pytest

from loadout import adopt, inventory, out, runner
from loadout.inventory import Item, Verdict
from fixtures import author_machine


@pytest.fixture
def machine(fake_home, fake_runner, monkeypatch):
    author_machine(fake_home)
    monkeypatch.setattr(out, "VERBOSE", False)
    return fake_home


def _verdicts():
    return inventory.classify(inventory.collect(with_versions=False))


def test_render_calm_headings_short_reasons_and_keep_count(machine):
    v = _verdicts()
    text = adopt.render_calm(v, [])
    keep = sum(1 for x in v if x.action == "keep")
    assert f"({keep} other items are fine)" in text.splitlines()[0]
    assert "Remove: superseded by something better" in text
    assert "REMOVE" not in text and "KEEP" not in text and "binaries:" not in text
    assert "the gh CLI does this with less context" in text  # short, not the long reason
    assert "Archived reference server" not in text


def test_calm_reason_falls_back_to_first_sentence():
    text = adopt.calm_group("remove", [Verdict(Item("mcp", "x"), "remove", "First part. Second part.", "")])
    assert "First part" in text and "Second" not in text


def test_calm_apply_shows_each_group_before_its_question(machine, capsys):
    asked = []

    def ask(q):
        asked.append((q, capsys.readouterr().out))
        return "n"

    adopt.run(True, None, set(), False, ask, with_versions=False, interactive=True)
    question, shown_before = asked[0]
    assert "[a]ll / [n]one / [p]ick" in question
    assert "Remove: superseded by something better" in shown_before
    assert "Already provided by loadout" not in shown_before  # the next group comes with its own question


def test_calm_yes_still_prints_the_plan(machine, capsys):
    adopt.run(True, None, set(), True, lambda q: "", with_versions=False, interactive=False)
    text = capsys.readouterr().out
    assert "Remove: superseded by something better" in text
    assert "Removed: " in text and "backup:" not in text
    assert adopt.UNDO_LINE in text


def test_calm_apply_prints_details_when_something_failed(machine, fake_runner, capsys):
    fake_runner.responses[("claude", "mcp", "remove")] = runner.Result(1, "", "boom")
    adopt.run(True, {"remove"}, set(), True, lambda q: "", with_versions=False, interactive=False)
    text = capsys.readouterr().out
    assert "Some changes did not complete" in text and "failed: boom" in text


def test_binary_skip_is_not_done(machine):
    entry = {"id": "rtk", "install": {"posix": [["echo", "x"]], "windows": [["echo", "x"]]}}
    v = Verdict(Item("binary", "rtk", extra={"entry": entry}), "install", "", "rtk")
    assert isinstance(adopt._apply_binary(v, lambda q: "n", confirm_cmds=True), adopt.NotDone)


def test_verbose_keeps_the_full_plan(machine, monkeypatch, capsys):
    monkeypatch.setattr(out, "VERBOSE", True)
    adopt.run(False, None, set(), False, lambda q: "", with_versions=False)
    assert "REMOVE (" in capsys.readouterr().out


def test_calm_names_drop_the_marketplace_suffixes():
    assert adopt._calm_name(Verdict(Item("plugin", "auto-memory@severity1-marketplace"), "remove", "")) == "auto-memory plugin"
    assert adopt._calm_name(Verdict(Item("marketplace", "severity1-marketplace"), "remove", "")) == "severity1 marketplace"


def test_calm_summary_names_the_profile_for_scope_down(machine):
    v = next(x for x in _verdicts() if x.action == "scope-down")
    line = adopt.calm_summary([v], [])[0]
    assert "Disabled globally" in line and "loadout profile" in line


def test_embedded_adopt_leaves_undo_and_restart_to_the_caller(machine, capsys):
    adopt.LAST_BACKUP = None
    adopt.run(True, None, set(), True, lambda q: "", with_versions=False, interactive=False, embedded=True)
    text = capsys.readouterr().out
    assert adopt.UNDO_LINE not in text and adopt.RESTART_NOTE not in text
    assert adopt.LAST_BACKUP is not None
