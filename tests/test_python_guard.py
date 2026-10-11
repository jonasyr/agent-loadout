import importlib.machinery
import importlib.util
import sys

import pytest

from loadout import check, paths


def _bin():
    path = paths.kit_root() / "bin" / "loadout"
    loader = importlib.machinery.SourceFileLoader("bin_loadout", str(path))
    spec = importlib.util.spec_from_loader("bin_loadout", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)  # must not run main(): the entry point is guarded by __name__
    return mod


def test_require_python_rejects_3_9(capsys):
    with pytest.raises(SystemExit) as exc:
        _bin().require_python((3, 9, 18))
    assert exc.value.code == 1
    assert "loadout needs Python 3.10 or newer (found 3.9)" in capsys.readouterr().err


def test_require_python_accepts_3_10_and_current():
    mod = _bin()
    mod.require_python((3, 10, 0))
    mod.require_python()


def test_bin_loadout_has_no_syntax_newer_than_3_6():
    import ast
    src = (paths.kit_root() / "bin" / "loadout").read_text(encoding="utf-8")
    ast.parse(src, feature_version=(3, 6))


def test_check_shows_python_version(fake_home, fake_runner):
    names = [r.name for r in check.run_checks()]
    assert f"Python {sys.version_info[0]}.{sys.version_info[1]}" in names
