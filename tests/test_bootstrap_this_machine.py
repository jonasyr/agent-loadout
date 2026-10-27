"""bootstrap's "This machine" block: the cell, the recommended flags, the differences; never a question (spec 2026-10-27)."""
import pytest

from loadout import bootstrap, out, recommend


@pytest.fixture
def calm(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(out, "VERBOSE", False)
    (fake_home / ".config/loadout/personal").mkdir(parents=True)
    return fake_home


def _run(**kw):
    args = dict(install=False, yes=True, plugins=False, adopt_step=False, ask=lambda q: "", interactive=False)
    args.update(kw)
    return bootstrap.bootstrap(**args)


def _block(text):
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if "This machine" in line)
    end = next(i for i, line in enumerate(lines) if "Prerequisites" in line)
    assert start < end, text
    return "\n".join(lines[start:end])


def test_block_shows_cell_and_flags(calm, capsys):
    _run()
    block = _block(capsys.readouterr().out)
    cell = recommend.detect({"claude": True, "codex": False}, found=[])
    assert recommend.describe(cell) in block
    assert f"recommended: {recommend.flags(cell)}" in block
    assert recommend.anchor(cell) in block


def test_block_names_differences(calm, capsys, fake_runner):
    fake_runner.missing.add("serena")
    _run()
    block = _block(capsys.readouterr().out)
    assert "serena" in block and "--install" in block


def test_block_never_asks(calm, capsys):
    def ask(q):
        raise AssertionError(f"asked: {q}")
    code = _run(ask=ask)
    assert "This machine" in capsys.readouterr().out
    assert code in (0, 1)


def test_block_on_every_run(calm, capsys):
    _run()
    capsys.readouterr()
    _run()
    assert "This machine" in capsys.readouterr().out


def test_block_never_breaks_bootstrap(calm, capsys, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("no")
    monkeypatch.setattr(recommend, "detect", boom)
    first = _run()
    monkeypatch.undo()
    assert "Prerequisites" in capsys.readouterr().out
    assert first in (0, 1)
