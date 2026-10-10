"""Final minor findings on the per-hook merge and hook adoption: a user duplicate before loadout's copy (S7),
skipped scopes keep their snapshot entries (S8), exec-form hooks are found by identity, and a null matcher."""
import json

import pytest

from loadout import adopt, backup, inventory, own, paths, settings_merge as sm
from fixtures import author_machine

LINT = {"type": "command", "command": "my-own-linter"}
OTHER = {"type": "command", "command": "other-hook"}


@pytest.fixture
def machine(fake_home, fake_runner):
    author_machine(fake_home)
    return fake_home


def S(): return json.loads((paths.claude_home() / "settings.json").read_text())
def wS(d): (paths.claude_home() / "settings.json").write_text(json.dumps(d))
def P():
    p = paths.personal_root() / "settings.json"
    return json.loads(p.read_text()) if p.exists() else {}
def wP(d):
    p = paths.personal_root() / "settings.json"; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(d))
def SNAP():
    p = paths.state_dir() / "managed-settings.json"
    return json.loads(p.read_text()) if p.exists() else {}


def _hooks(data):
    return [h for _, _, _, _, h, _ in sm._iter_hooks(data)]


def _step(cur, want, prev):
    """One merge: (merged settings, new snapshot)."""
    return sm.merge_settings(cur, want, prev), sm.effective_desired(cur, want, prev)


# S7: the user inserts an edited duplicate of an applied hook BEFORE loadout's copy
def test_user_duplicate_before_applied_copy_keeps_loadouts_copy_tracked():
    want = {"hooks": {"Stop": [{"hooks": [LINT]}]}}
    cur, snap = _step({}, want, {})
    assert _hooks(cur) == [LINT] and _hooks(snap) == [LINT]
    mine = {**LINT, "timeout": 55}
    cur = {"hooks": {"Stop": [{"hooks": [mine]}, *cur["hooks"]["Stop"]]}}
    after, snap = _step(cur, want, snap)
    assert after == cur, "the merge must leave both copies alone"
    assert _hooks(snap) == [LINT], "loadout's copy must stay tracked"
    after, snap = _step(after, {}, snap)  # removed from the personal layer
    assert _hooks(after) == [mine], "only loadout's copy goes; the user's copy stays untouched"
    assert not _hooks(snap)


def test_user_duplicate_before_applied_copy_kit_update_hits_loadouts_copy():
    want = {"hooks": {"Stop": [{"hooks": [LINT]}]}}
    cur, snap = _step({}, want, {})
    mine = {**LINT, "timeout": 55}
    cur = {"hooks": {"Stop": [{"hooks": [mine]}, *cur["hooks"]["Stop"]]}}
    new = {"hooks": {"Stop": [{"hooks": [{**LINT, "timeout": 3}]}]}}
    after, snap = _step(cur, new, snap)
    assert _hooks(after) == [mine, {**LINT, "timeout": 3}]
    assert _hooks(snap) == [{**LINT, "timeout": 3}]


# S8: a scope the merge skips (a non-list event value, a non-dict `hooks`) keeps its snapshot entries
def _applied_and_tombstoned():
    """LINT applied and still in settings.json; OTHER applied and then deleted by the user (a tombstone)."""
    want = {"hooks": {"Stop": [{"hooks": [LINT, OTHER]}]}}
    cur, snap = _step({}, want, {})
    cur = {"hooks": {"Stop": [{"hooks": [LINT]}]}}  # the user deletes OTHER
    cur, snap = _step(cur, want, snap)
    assert _hooks(snap) == [LINT] and _hooks({"hooks": snap[sm.TOMBSTONES]}) == [OTHER]
    return want, cur, snap


@pytest.mark.parametrize("skipped", [
    lambda cur: {"hooks": {**cur["hooks"], "Stop": {"weird": 1}}},  # a non-list event value
    lambda cur: {"hooks": "not a hooks section"},                   # a non-dict hooks section
], ids=["non-list-event", "non-dict-hooks"])
def test_skipped_scope_keeps_applied_hooks_and_tombstones(skipped):
    want, cur, snap = _applied_and_tombstoned()
    before = snap
    odd = skipped(cur)
    after, snap = _step(odd, want, snap)
    assert after == odd, "a skipped scope is left exactly as it is"
    assert snap == before, "the skipped scope's applied hooks and tombstones carry over unchanged"
    after, snap = _step(odd, want, snap)  # a second merge while it stays skipped
    assert snap == before
    after, snap = _step(cur, want, snap)  # a list again
    assert _hooks(after) == [LINT], "the deleted hook must not be re-added"
    assert snap == before
    after, snap = _step(after, {}, snap)  # removed from the personal layer: the applied hook goes
    assert _hooks(after) == [] and not _hooks(snap) and sm.TOMBSTONES not in snap


def _hook_verdicts(name):
    vs = inventory.classify(inventory.collect(with_versions=False))
    return [v for v in vs if v.item.kind == "hook" and v.item.name == name]


# exec-form hooks are found by identity (command plus args), not by command alone
def test_adopting_the_second_exec_hook_records_the_second_one(machine):
    A = {"type": "command", "command": "node", "args": ["/a.js"]}
    B = {"type": "command", "command": "node", "args": ["/b.js"]}
    s = S(); s["hooks"]["SubagentStop"] = [{"matcher": "x", "hooks": [A, B]}]; wS(s)
    vs = _hook_verdicts("SubagentStop:x")
    assert [v.item.detail for v in vs] == ["node", "node"], "displayed names and details stay as they were"
    second = next(v for v in vs if v.item.extra.get("args") == ["/b.js"])
    not_done: list = []
    lines, _ = adopt.apply_own([(second, own.Choice("global"))], backup.Backup(), not_done=not_done)
    assert not not_done, lines
    assert _hooks(P()) == [B], "the second exec hook must be recorded, not the first"
    assert [h for g in S()["hooks"]["SubagentStop"] for h in g["hooks"]] == [A, B]
    assert B in _hooks(SNAP()) and A not in _hooks(SNAP()), "the second one is tracked as applied"


def _merge():
    bk = backup.Backup()
    sm.backup_snapshot(bk)
    sm.apply_settings()
    first = S(), SNAP()
    sm.apply_settings()
    assert (S(), SNAP()) == first, "a second merge changed something"


# a group with "matcher": null reads like a missing matcher: name `Stop:`, adoptable, merged without a duplicate
def test_null_matcher_hook_is_named_without_matcher_and_can_be_adopted(machine):
    s = S(); s["hooks"]["SubagentStop"] = [{"matcher": None, "hooks": [LINT]}]; wS(s)
    assert not _hook_verdicts("SubagentStop:None")
    v, = _hook_verdicts("SubagentStop:")
    assert own.display_name(v.item) == "SubagentStop (no matcher)"
    not_done: list = []
    lines, _ = adopt.apply_own([(v, own.Choice("global"))], backup.Backup(), not_done=not_done)
    assert not not_done, lines
    assert _hooks(P()) == [LINT]
    _merge()
    assert [h for g in S()["hooks"]["SubagentStop"] for h in g["hooks"]] == [LINT], "no duplicate after the merge"
    assert LINT in _hooks(SNAP())
    wP({}); _merge()
    assert "SubagentStop" not in S()["hooks"], "tracked: removing it from the personal layer removes it here"
