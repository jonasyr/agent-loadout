"""loadout needs Python 3.11 or newer everywhere it checks."""
import re

from loadout import link, paths

KIT = paths.kit_root()


def test_every_version_check_says_3_11():
    files = ["bin/loadout", "plugins/loadout/hooks/run.sh", "bootstrap.sh", "bootstrap.ps1", "pyproject.toml"]
    for rel in files:
        text = (KIT / rel).read_text(encoding="utf-8")
        assert "3.10" not in text and "(3, 10)" not in text, rel
    assert "(3, 11)" in link.PY_OK and ">=3.11" in link.UV_FIND and ">=3.11" in link.UV_INSTALL


def test_bin_loadout_refuses_3_10(capsys):
    import importlib.machinery
    import importlib.util
    loader = importlib.machinery.SourceFileLoader("binloadout", str(KIT / "bin/loadout"))
    spec = importlib.util.spec_from_loader("binloadout", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    try:
        mod.require_python((3, 10, 0))
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("did not exit")
    assert "3.11 or newer" in capsys.readouterr().err


def test_no_code_path_for_a_missing_tomllib():
    for rel in ("cli/loadout/codex.py", "cli/loadout/codex_project.py", "cli/loadout/own.py"):
        assert not re.search(r"_tomllib\(\) is None|needs Python 3\.11", (KIT / rel).read_text(encoding="utf-8")), rel
