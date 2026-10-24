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
