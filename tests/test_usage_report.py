"""usage.metrics / change / report: windows, shares and arrows over Session records."""
import json
import os

from loadout import paths, targets, usage
from loadout.usage_sessions import Session

DAY = 86400


def S(calls=10, start=0.0, lookups=(0, 0), searches=0, denials=0, followed=0, kind="main", fam=None, prompted=None,
      agent="claude", sid="x"):
    return Session(sid, agent, kind, start, dict(fam or {}), calls,
                   {"serena": lookups[0], "codebase-memory": lookups[1]}, searches, denials, followed, prompted)


def test_tiny_sessions_are_left_out_and_counted():
    m = usage.metrics([S(3), S(10)], 5)
    assert m["sessions"] == 1 and m["tiny"] == 1 and m["calls"] == 10


def test_code_tool_share():
    m = usage.metrics([S(lookups=(3, 1), searches=4)], 5)
    assert m["code_tool_share"] == 0.5 and m["lookups"] == {"serena": 3, "codebase-memory": 1}


def test_follow_through_share():
    m = usage.metrics([S(denials=4, followed=1)], 5)
    assert m["follow_through"] == 0.25 and m["serena_denials"] == 1 and m["denials"] == 4


def test_arrows_use_points_for_shares_and_percent_for_rates():
    def row(share=0.0, rate=0.0, n=20):
        m = usage.metrics([], 5)
        m.update(sessions=n, code_tool_share=share, per_session={"symbol_searches": rate, "calls": 10.0})
        return m
    assert usage.change(row(0.10), row(0.14), 20)["code_tool_share"] == "="
    assert usage.change(row(0.10), row(0.16), 20)["code_tool_share"] == "↑"
    assert usage.change(row(0.16), row(0.10), 20)["code_tool_share"] == "↓"
    assert usage.change(row(rate=10), row(rate=7.9), 20)["per_session.symbol_searches"] == "↓"
    assert usage.change(row(rate=10), row(rate=8.5), 20)["per_session.symbol_searches"] == "="
    assert usage.change(row(rate=0), row(rate=2), 20)["per_session.symbol_searches"] == "new"
    assert usage.change(row(share=None), row(0.2), 20)["code_tool_share"] == "—"


def test_too_few_sessions_guard():
    a = usage.metrics([S() for _ in range(19)], 5)
    b = usage.metrics([S() for _ in range(25)], 5)
    ch = usage.change(a, b, 20)
    assert ch and set(ch.values()) == {"too few sessions"}
    assert set(usage.change(b, a, 20).values()) == {"too few sessions"}


def _write(name, ts, sub=False, n=6, prompt=None):
    folder = paths.claude_home() / "projects" / "-repo"
    path = folder / (f"{name}/subagents/a.jsonl" if sub else f"{name}.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    recs = []
    if prompt:
        recs.append({"type": "user", "timestamp": ts, "message": {"content": prompt}})
    for _ in range(n):
        recs.append({"type": "assistant", "timestamp": ts, "message": {"content": [
            {"type": "tool_use", "name": "Read", "input": {}}]}})
    path.write_text("\n".join(json.dumps(r) for r in recs) + "\n")
    return path


def test_sessions_belong_to_the_window_of_their_start(fake_home):
    _write("old", "2026-10-01T00:00:00Z")
    _write("bef", "2026-10-10T00:00:00Z")
    _write("aft", "2026-10-20T00:00:00Z")
    from datetime import datetime, timezone
    t = lambda s: datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp()
    for p in (paths.claude_home() / "projects" / "-repo").glob("*.jsonl"):
        os.utime(p, (t("2026-10-21T00:00:00"),) * 2)
    r = usage.report(t("2026-10-15T00:00:00"), t("2026-10-22T00:00:00"), t("2026-10-08T00:00:00"),
                     now=t("2026-10-23T00:00:00"))
    c = r["claude"]
    assert c["main"]["sessions"] == 1 and c["before"]["main"]["sessions"] == 1
    assert r["windows"]["before"]["days"] == 7 and r["windows"]["after"]["partial"] is False


def test_partial_after_window_is_labelled_and_normalised(fake_home):
    now = 1_000_000_000.0
    p = _write("aft", "2026-10-20T00:00:00Z")
    os.utime(p, (now, now))
    start = now - 2 * DAY
    from datetime import datetime, timezone
    ts = datetime.fromtimestamp(now - DAY, timezone.utc).isoformat()
    _write("aft", ts)
    os.utime(p, (now, now))
    r = usage.report(start, start + 7 * DAY, None, now=now)
    w = r["windows"]["after"]
    assert w["partial"] is True and w["days"] == 2 and r["days"] == 7
    assert r["claude"]["main"]["per_session"]["calls"] == 6.0


def test_empty_and_zero_rows_never_divide_by_zero(fake_home):
    m = usage.metrics([], 5)
    assert m["sessions"] == 0 and m["code_tool_share"] is None and m["follow_through"] is None
    assert m["per_session"] == {"symbol_searches": 0.0, "calls": 0.0}
    assert set(usage.change(m, m, 20).values()) == {"too few sessions"}
    z = usage.metrics([S() for _ in range(20)], 5)
    assert usage.change(z, z, 20)["code_tool_share"] == "—"
    assert usage.change(z, z, 20)["per_session.symbol_searches"] == "="
    r = usage.report(1.0, 2.0, 0.0, now=3.0)
    assert r["hint_sessions"] == 0 and "claude" not in r


def test_prompted_split_rows(fake_home):
    now = 1_000_000_000.0
    from datetime import datetime, timezone
    ts = datetime.fromtimestamp(now - 100, timezone.utc).isoformat()
    for i, text in enumerate(["use serena", "use find_symbol please", "just fix it"]):
        p = _write(f"s{i}", ts, sub=True, prompt=text)
        os.utime(p, (now, now))
    r = usage.report(now - DAY, now + DAY, None, now=now)
    c = r["claude"]
    assert c["prompted_known"] is True
    assert (c["subagent"]["sessions"], c["subagent_prompted"]["sessions"],
            c["subagent_unprompted"]["sessions"]) == (3, 2, 1)
    # Codex main sessions carry no prompt: the split stays empty
    sess = [S(kind="subagent", agent="codex"), S(kind="main", agent="codex")]
    assert usage._agent_block(sess, [0], 5, None)["prompted_known"] is False


def test_the_rate_rule_is_symmetric_at_exactly_20_percent():
    assert usage._arrow_rate(10, 12) == "↑" and usage._arrow_rate(10, 8) == "↓"
    assert usage._arrow_rate(10, 11.9) == "=" and usage._arrow_rate(10, 8.1) == "="
    assert usage._arrow_share(0.10, 0.15) == "↑" and usage._arrow_share(0.15, 0.10) == "↓"


def test_an_after_start_in_the_future_gives_an_empty_window(fake_home):
    now = 1_800_000_000.0
    rep = usage.report(now + 86400, now + 8 * 86400, None, now=now)
    assert rep["windows"]["after"]["days"] == 0 and rep["windows"]["after"]["end"] >= rep["windows"]["after"]["start"]


# ---- CLI ----

import pytest
from datetime import datetime

from loadout.__main__ import main


def _on(monkeypatch, claude=True, codex=False):
    monkeypatch.setattr(targets, "claude_enabled", lambda: claude)
    monkeypatch.setattr(targets, "codex_enabled", lambda: codex)


def _day(offset_days):
    """An ISO timestamp (UTC) a number of days from now, plus the epoch for os.utime."""
    import time
    t = time.time() + offset_days * DAY
    return datetime.fromtimestamp(t, tz=__import__("datetime").timezone.utc).isoformat(), t


def _seed(name, offset, **kw):
    ts, t = _day(offset)
    p = _write(name, ts, **kw)
    os.utime(p, (t, t))
    return p


def _local_date(offset):
    import time
    return datetime.fromtimestamp(time.time() + offset * DAY).strftime("%Y-%m-%d")


def test_parse_moment():
    assert usage.parse_moment("2026-10-15") == datetime(2026, 10, 15).timestamp()
    assert usage.parse_moment("2026-10-15T13:30") == datetime(2026, 10, 15, 13, 30).timestamp()
    with pytest.raises(ValueError, match="use YYYY-MM-DD or YYYY-MM-DDTHH:MM"):
        usage.parse_moment("15.10.2026")


def test_cli_around_shows_both_windows_and_arrows(fake_home, monkeypatch, capsys):
    _on(monkeypatch)
    for i in range(2):
        _seed(f"b{i}", -9 - i)  # plain Read calls before
        _seed(f"a{i}", -2 - i)
    ts, t = _day(-1)
    p = paths.claude_home() / "projects" / "-repo" / "serena.jsonl"
    recs = [{"type": "assistant", "timestamp": ts, "message": {"content": [
        {"type": "tool_use", "name": "mcp__serena__find_symbol", "input": {}}]}} for _ in range(6)]
    p.write_text("\n".join(json.dumps(r) for r in recs) + "\n")
    os.utime(p, (t, t))
    around, before_start = _local_date(-5), _local_date(-10)
    assert main(["usage", "--around", around, "--days", "5", "--min-sessions", "1"]) == 0
    out = capsys.readouterr().out
    assert before_start in out and around in out and "↑" in out and "→" in out


def test_cli_since_shows_one_window(fake_home, monkeypatch, capsys):
    _on(monkeypatch)
    _seed("a", -1)
    assert main(["usage", "--since", _local_date(-3)]) == 0
    out = capsys.readouterr().out
    assert "after" in out and "before" not in out and "→" not in out


def test_cli_legacy_matches_collect(fake_home, monkeypatch, capsys):
    _on(monkeypatch)
    _seed("a", -1)
    assert main(["usage", "--legacy", "--json", "--days", "7"]) == 0
    got = json.loads(capsys.readouterr().out)
    want = usage.collect(7)
    assert got["claude"] == want["claude"] and got["days"] == 7 and got["hint_sessions"] == want["hint_sessions"]


def test_cli_sessions_lists_ids_and_numbers_only(fake_home, monkeypatch, capsys):
    _on(monkeypatch)
    _seed("sess-one", -1, prompt="SECRET-PROMPT")
    _seed("sess-sub", -1, sub=True, prompt="SECRET-PROMPT use serena")
    assert main(["usage", "--sessions"]) == 0
    out = capsys.readouterr().out
    assert "SECRET-PROMPT" not in out and "sess-one" in out
    line = next(l for l in out.splitlines() if l.startswith("sess-one"))
    assert line.split("  ")[1:6] == ["claude", "main", "counted", "after", "lookups=0/0"]
    assert "prompted=—" in line and "share=—" in line
    assert "prompted=yes" in out


def test_json_keeps_todays_keys(fake_home, monkeypatch, capsys):
    _on(monkeypatch)
    _seed("a", -1)
    assert main(["usage", "--json"]) == 0
    c = json.loads(capsys.readouterr().out)["claude"]["main"]
    for key in ("sessions", "calls", "symbol_searches", "serena_denials"):
        assert isinstance(c[key], int)
    assert set(c["families"]) == set(usage.NAMES)
    assert all(set(v) == {"calls", "sessions"} for v in c["families"].values())


def test_table_fits_100_columns(fake_home, monkeypatch, capsys):
    _on(monkeypatch, codex=True)
    for i in range(3):
        _seed(f"b{i}", -9 - i)
        _seed(f"a{i}", -2 - i)
        _seed(f"sb{i}", -2 - i, sub=True, prompt="use serena")
    cx = paths.codex_home() / "sessions" / "2026" / "10" / "14" / "r.jsonl"
    cx.parent.mkdir(parents=True, exist_ok=True)
    cx.write_text(json.dumps({"type": "session_meta", "payload": {"timestamp": _day(-2)[0]}}) + "\n")
    for args in (["--around", _local_date(-5), "--days", "5"], ["--days", "5"]):
        assert main(["usage", *args]) == 0
        out = capsys.readouterr().out
        assert out.strip() and max(len(l) for l in out.splitlines()) <= 100


def test_around_and_since_are_exclusive(fake_home, monkeypatch):
    with pytest.raises(SystemExit):
        main(["usage", "--around", "2026-10-01", "--since", "2026-10-02"])


def test_legacy_refuses_window_flags(fake_home, monkeypatch, capsys):
    _on(monkeypatch)
    for extra in (["--around", "2026-10-01"], ["--since", "2026-10-01"], ["--sessions"]):
        assert main(["usage", "--legacy", *extra]) == 2
        assert "--legacy" in capsys.readouterr().err


def test_bad_moment_is_rejected(fake_home):
    with pytest.raises(SystemExit):
        main(["usage", "--around", "yesterday"])


def test_a_row_without_counted_sessions_shows_dashes():
    empty = usage.metrics([S(calls=2)], min_calls=5)
    assert usage._cell(empty, "serena").startswith("—") and usage._cell(empty, "symbol") == "—"


def test_the_codex_note_needs_codex_subagents(fake_home):
    rep = {"windows": {"after": {"start": 0, "end": 86400, "days": 1, "partial": False}},
           "thresholds": {"min_calls": 5, "follow_within": 5, "min_sessions": 20}, "hint_sessions": 0,
           "codex": {r: usage.metrics([], 5) for r in usage.ROWS} | {"prompted_known": False, "skipped_lines": 0}}
    assert "not split" not in usage.render_report(rep)
