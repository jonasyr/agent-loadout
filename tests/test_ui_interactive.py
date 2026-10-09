import io
import types

from loadout import ui


class _Tty(io.StringIO):
    def isatty(self):
        return True


def test_tty_stdin_is_interactive_on_posix(monkeypatch):
    monkeypatch.setattr(ui, "os", types.SimpleNamespace(name="posix"))
    monkeypatch.setattr(ui.sys, "stdin", _Tty())
    assert ui.is_interactive()


def test_windows_nul_device_is_not_interactive(monkeypatch):
    # Windows reports NUL as a tty; only a real console handle counts
    monkeypatch.setattr(ui, "os", types.SimpleNamespace(name="nt"))
    monkeypatch.setattr(ui.sys, "stdin", _Tty())
    monkeypatch.setattr(ui, "_windows_console_stdin", lambda: False)
    assert not ui.is_interactive()
    monkeypatch.setattr(ui, "_windows_console_stdin", lambda: True)
    assert ui.is_interactive()


def test_piped_stdin_is_not_interactive(monkeypatch):
    monkeypatch.setattr(ui.sys, "stdin", io.StringIO(""))
    assert not ui.is_interactive()
