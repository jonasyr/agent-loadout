import io
import sys

from loadout import out


class Stream(io.StringIO):
    def __init__(self, tty=False, encoding="utf-8"):
        super().__init__()
        self._tty, self._enc = tty, encoding

    def isatty(self):
        return self._tty

    @property
    def encoding(self):
        return self._enc


def test_plain_when_not_a_terminal(monkeypatch):
    monkeypatch.setattr(sys, "stdout", Stream(tty=False))
    out.status("Plugins", "14 kit plugins ready")
    assert sys.stdout.getvalue() == "✓ Plugins            14 kit plugins ready\n"


def test_colour_on_a_terminal_unless_no_color(monkeypatch):
    monkeypatch.setattr(sys, "stdout", Stream(tty=True))
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    assert out.paint("x", "ok") == "\033[32mx\033[0m"
    monkeypatch.setenv("NO_COLOR", "1")
    assert out.paint("x", "ok") == "x"


def test_ascii_symbols_when_stdout_cannot_encode(monkeypatch):
    monkeypatch.setattr(sys, "stdout", Stream(encoding="cp1252"))
    assert (out.sym("ok"), out.sym("bullet"), out.sym("arrow")) == ("ok", "-", "->")


def test_detail_only_when_verbose(monkeypatch, capsys):
    monkeypatch.setattr(out, "VERBOSE", False)
    out.detail("linked x")
    out.problem("plugin y: failed")
    assert capsys.readouterr().out == "  plugin y: failed\n"
    monkeypatch.setattr(out, "VERBOSE", True)
    out.detail("linked x")
    assert capsys.readouterr().out == "  linked x\n"
