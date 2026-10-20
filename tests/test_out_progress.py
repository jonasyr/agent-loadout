import threading

import pytest

from loadout import out


@pytest.fixture
def calm(monkeypatch):
    monkeypatch.setattr(out, "VERBOSE", False)
    monkeypatch.setattr(out, "_shown", 0)
    monkeypatch.setattr(out, "_TICK", 3600.0)  # tests drive ticks by hand
    now = [100.0]
    monkeypatch.setattr(out, "_clock", lambda: now[0])
    return now


def test_tty_step_shows_elapsed_seconds(calm, monkeypatch, capsys):
    monkeypatch.setattr(out, "_tty", lambda: True)
    with out.step("plugins", total=3) as s:
        s.item("a")
        s.item("b")
        calm[0] += 2
        s.tick()
        text = capsys.readouterr().out
    assert "(2 of 3)" in text and "2s" in text and "plugins: b" in text


def test_no_tty_prints_plain_lines_without_a_thread(calm, monkeypatch, capsys):
    monkeypatch.setattr(out, "_tty", lambda: False)
    before = threading.active_count()
    with out.step("plugins", total=2) as s:
        assert threading.active_count() == before
        s.item("a")
        s.item("b")
    text = capsys.readouterr().out
    assert "\r" not in text
    assert text.splitlines() == ["plugins: a (1 of 2)", "plugins: b (2 of 2)"]


def test_verbose_on_a_tty_is_plain_lines(calm, monkeypatch, capsys):
    monkeypatch.setattr(out, "_tty", lambda: True)
    monkeypatch.setattr(out, "VERBOSE", True)
    before = threading.active_count()
    with out.step("x") as s:
        assert threading.active_count() == before
        s.item("a")
    assert capsys.readouterr().out == "x: a\n"


def test_slow_note_is_printed_once(calm, monkeypatch, capsys):
    monkeypatch.setattr(out, "_tty", lambda: True)
    with out.step("plugins", total=2, slow="this can take a minute") as s:
        s.item("a")
        s.item("b")
        s.tick()
    assert capsys.readouterr().out.count("this can take a minute") == 1


def test_an_exception_inside_the_step_clears_the_line_and_stops_the_thread(calm, monkeypatch, capsys):
    monkeypatch.setattr(out, "_tty", lambda: True)
    monkeypatch.setattr(out, "_TICK", 0.02)
    before = threading.active_count()
    for exc in (RuntimeError, KeyboardInterrupt):
        with pytest.raises(exc):
            with out.step("plugins", total=2) as s:
                s.item("a")
                assert threading.active_count() == before + 1
                raise exc()
        assert threading.active_count() == before
        assert out._shown == 0
        assert capsys.readouterr().out.endswith("\r")


@pytest.mark.parametrize("tty", [True, False])
def test_progress_text_is_redacted_and_escaped(calm, monkeypatch, capsys, tty):
    monkeypatch.setattr(out, "_tty", lambda: tty)
    token = "ghp_" + "abcdefghijklmnopqrstuvwxyz0123456789"  # built, so the repo scan finds no literal token
    with out.step("Plugins", total=1) as st:
        st.item(f"  adding marketplace https://jonas:{token}@github.com/o/r.git\x1b[31m, a git clone (1 of 1)…")
    out.progress(f"clone https://x:{token}@github.com/o/r\n1. fake")
    text = capsys.readouterr().out
    assert "ghp_" not in text and "\x1b[31m" not in text and "github.com/o/r" in text
    assert "\n1. fake" not in text
