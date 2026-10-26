"""`loadout check` warns when Codex's marketplace staging folder grows (abandoned clones of failed upgrades,
openai/codex#39421); it reads only and never runs codex."""
import os
import sys

import pytest

from loadout import check, targets

ROW = "Codex marketplace staging"
FIX = ("quit Codex, then empty that folder (abandoned clones of failed marketplace upgrades, openai/codex#39421)")


def _staging(fake_home):
    return fake_home / ".codex/.tmp/marketplaces/.staging"


def _rows(monkeypatch, codex_on=True):
    monkeypatch.setattr(targets, "OVERRIDE", {"claude": True, "codex": codex_on})
    return [r for r in check.run_checks() if r.name == ROW]


def _fill(root, folders, size):
    for i in range(folders):
        d = root / f"marketplace-upgrade-{i}"
        d.mkdir(parents=True)
        (d / "f").write_bytes(b"x" * size)


def test_missing_staging_is_ok(fake_home, fake_runner, monkeypatch):
    [r] = _rows(monkeypatch)
    assert (r.ok, r.detail) == (True, "empty")
    assert not [c for c in fake_runner.calls if c and c[0] == "codex" and "marketplace" in c]


def test_small_staging_is_ok(fake_home, fake_runner, monkeypatch):
    _fill(_staging(fake_home), 2, 100)
    [r] = _rows(monkeypatch)
    assert r.ok and r.detail != "empty"


def test_large_staging_warns(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(check, "STAGING_WARN_BYTES", 10)
    _fill(_staging(fake_home), 3, 8)
    [r] = _rows(monkeypatch)
    assert (r.ok, r.severity) == (False, "warn")
    assert r.detail.startswith("over ") and "in 3 folders in ~/.codex/.tmp/marketplaces/.staging" in r.detail
    assert r.fix == FIX


@pytest.mark.skipif(sys.platform == "win32" or getattr(os, "geteuid", lambda: 1)() == 0,
                    reason="needs POSIX permissions and a non-root user")
def test_staging_walk_stops_at_the_threshold_and_survives_errors(tmp_path):
    root = tmp_path / "s"
    (root / "a").mkdir(parents=True)
    (root / "a" / "f").write_bytes(b"x" * 50)
    (root / "loop").symlink_to(root, target_is_directory=True)
    locked = root / "locked"
    locked.mkdir()
    (locked / "g").write_bytes(b"y" * 50)
    locked.chmod(0)
    try:
        assert check._dir_size_capped(root, 10**9) == (50, False)
        total, reached = check._dir_size_capped(root, 20)
        assert reached and total >= 20
    finally:
        locked.chmod(0o755)


def test_no_row_with_codex_off(fake_home, fake_runner, monkeypatch):
    _fill(_staging(fake_home), 1, 10)
    assert _rows(monkeypatch, codex_on=False) == []
