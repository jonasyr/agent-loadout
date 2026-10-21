"""`loadout check` names codebase-memory-mcp's daemon conflict from the log the failing session wrote (read only)."""
import json
import time

import pytest

from loadout import check

NAME = "codebase-memory-mcp daemon"
CACHE_DETAIL = ("a codebase-memory-mcp session with a different cache folder could not start "
                "(another one already runs for your account)")
CACHE_FIX = ("close the other sessions (Codex, Claude Code, VS Code) or give them the same CBM_CACHE_DIR; "
             "codebase-memory-mcp daemon stop retires the daemon once no session uses it")


@pytest.fixture
def cache(fake_home, fake_runner, monkeypatch):
    monkeypatch.delenv("CBM_CACHE_DIR", raising=False)
    d = fake_home / ".cache/codebase-memory-mcp/logs"
    d.mkdir(parents=True)
    return d


def _cache_record(age_s=600, **kw):
    rec = {"event": "daemon.version_conflict", "timestamp_unix_s": int(time.time()) - age_s, "reason": "cache_root",
           "active_cache": "/home/x/.cache/codebase-memory-mcp", "requested_cache": "/tmp/other",
           "active_version": "0.12.1", "requested_version": "0.12.1"}
    rec.update(kw)
    return rec


def _version_record(age_s=600):
    return {"event": "daemon.version_conflict", "timestamp_unix_s": int(time.time()) - age_s,
            "active_version": "0.12.1", "requested_version": "0.13.0"}


def _write(d, *records, name="daemon-conflicts.ndjson"):
    (d / name).write_text("".join((r if isinstance(r, str) else json.dumps(r)) + "\n" for r in records))


def test_recent_cache_conflict_is_named(cache):
    _write(cache, _cache_record())
    [r] = check._cbm_conflict()
    assert (r.name, r.ok, r.severity, r.detail, r.fix) == (NAME, False, "warn", CACHE_DETAIL, CACHE_FIX)


def test_registered_in_run_checks(cache):
    _write(cache, _cache_record())
    assert NAME in {r.name for r in check.run_checks()}


def test_version_conflict_names_both_versions(cache):
    _write(cache, _version_record())
    [r] = check._cbm_conflict()
    assert not r.ok and r.severity == "warn"
    assert "0.12.1" in r.detail and "0.13.0" in r.detail


def test_old_record_is_ignored(cache):
    _write(cache, _cache_record(age_s=25 * 3600))
    assert check._cbm_conflict() == []


def test_malformed_lines_are_skipped(cache):
    _write(cache, "not json", "[1, 2]", '{"timestamp_unix_s": "soon"}', '{"timestamp_unix_s": true}',
           json.dumps(_cache_record(requested_version=None)), _cache_record())
    with (cache / "daemon-conflicts.ndjson").open("ab") as f:
        f.write(b"\xff\xfe broken\n")
    [r] = check._cbm_conflict()
    assert r.detail == CACHE_DETAIL


def test_only_malformed_lines_give_nothing(cache):
    _write(cache, "{", '{"reason": "cache_root"}', "\x00")
    assert check._cbm_conflict() == []


def test_only_the_last_64_kib_are_read(cache):
    # a recent record at the head of a file far larger than 64 KiB is not read; old filler fills the tail
    filler = json.dumps(_cache_record(age_s=48 * 3600))
    _write(cache, _cache_record(), *([filler] * (70 * 1024 // len(filler) + 10)))
    assert (cache / "daemon-conflicts.ndjson").stat().st_size > 64 * 1024
    assert check._cbm_conflict() == []


def test_recent_record_in_tail_of_large_file_is_found(cache):
    filler = json.dumps(_cache_record(age_s=48 * 3600))
    _write(cache, *([filler] * (70 * 1024 // len(filler) + 10)), _cache_record())
    [r] = check._cbm_conflict()
    assert r.detail == CACHE_DETAIL


def test_rotated_log_is_read(cache):
    _write(cache, _cache_record(), name="daemon-conflicts.ndjson.1")
    [r] = check._cbm_conflict()
    assert r.detail == CACHE_DETAIL


def test_no_file_gives_nothing(cache):
    assert check._cbm_conflict() == []


def test_no_cache_folder_gives_nothing(fake_home, fake_runner, monkeypatch):
    monkeypatch.delenv("CBM_CACHE_DIR", raising=False)
    assert check._cbm_conflict() == []


def test_windows_gives_nothing(cache, monkeypatch):
    _write(cache, _cache_record())
    monkeypatch.setattr(check.os, "name", "nt")
    assert check._cbm_conflict() == []


def test_cbm_cache_dir_of_checks_environment_is_read(fake_home, fake_runner, monkeypatch, tmp_path):
    own = tmp_path / "cbm"
    (own / "logs").mkdir(parents=True)
    monkeypatch.setenv("CBM_CACHE_DIR", str(own))
    _write(own / "logs", _cache_record())
    [r] = check._cbm_conflict()
    assert r.detail.startswith(CACHE_DETAIL)
    assert str(own) in r.detail and "CBM_CACHE_DIR" in r.detail and "own environment" in r.detail
    assert r.fix == CACHE_FIX


def test_default_folder_is_read_next_to_cbm_cache_dir(cache, monkeypatch, tmp_path):
    monkeypatch.setenv("CBM_CACHE_DIR", str(tmp_path / "empty"))
    _write(cache, _cache_record())
    [r] = check._cbm_conflict()
    assert r.detail == CACHE_DETAIL


def test_check_never_runs_the_binary(cache, fake_runner):
    _write(cache, _cache_record())
    check._cbm_conflict()
    assert not any("codebase-memory-mcp" in " ".join(map(str, c)) for c in fake_runner.calls)


def test_record_starting_exactly_at_the_tail_is_read(cache):
    head = json.dumps(_cache_record(age_s=48 * 3600)) + "\n"
    rec = json.dumps(_cache_record())
    rec = rec[:-1] + ', "pad": "' + "x" * (64 * 1024 - len(rec) - 10 - 2) + '"}'
    assert len(rec) + 1 == 64 * 1024
    (cache / "daemon-conflicts.ndjson").write_text(head * 3 + rec + "\n")
    [r] = check._cbm_conflict()
    assert r.detail == CACHE_DETAIL


def test_huge_integer_timestamp_is_skipped(cache):
    _write(cache, '{"timestamp_unix_s": 1' + "0" * 400 + "}", _cache_record())
    [r] = check._cbm_conflict()
    assert r.detail == CACHE_DETAIL


def test_non_finite_timestamp_is_skipped(cache):
    _write(cache, '{"timestamp_unix_s": NaN}', '{"timestamp_unix_s": Infinity}', _cache_record())
    [r] = check._cbm_conflict()
    assert r.detail == CACHE_DETAIL


def test_deeply_nested_line_is_skipped(cache):
    _write(cache, "[" * 30000 + "]" * 30000, _cache_record())
    [r] = check._cbm_conflict()
    assert r.detail == CACHE_DETAIL
