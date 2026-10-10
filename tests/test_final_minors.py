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
