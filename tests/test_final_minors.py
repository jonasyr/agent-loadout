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
