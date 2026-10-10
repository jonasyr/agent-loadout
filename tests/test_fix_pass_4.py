"""Fix pass 4: re-review 4 sequences for the per-hook three-way merge (ported from /tmp/claude-1000/rr4/test_seq4.py,
with assertions where the probe only printed), plus the tombstone (C1), slot replacement (C2), non-list event (M1)
and user-edit (M2) rules."""
import json
import pytest
from loadout import adopt, backup, inventory, own, paths, settings_merge as sm
from fixtures import author_machine

LINT = {"type": "command", "command": "my-own-linter"}


@pytest.fixture
def machine(fake_home, fake_runner):
    author_machine(fake_home)
    return fake_home


def _get(kind, name):
    vs = inventory.classify(inventory.collect(with_versions=False))
    return next(v for v in vs if v.item.kind == kind and v.item.name == name)


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
def wSNAP(d):
    p = paths.state_dir() / "managed-settings.json"; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(d))


def hooks(data=None, event=None):
    data = S() if data is None else data
    for ev, groups in (data.get("hooks") or {}).items():
        for g in groups:
            for h in g.get("hooks", []):
                if event is None or ev == event:
                    yield ev, g.get("matcher", ""), h


def cnt(cmd="my-own-linter", matcher=None):
    return sum(1 for _, m, h in hooks() if h.get("command") == cmd and (matcher is None or (m or "") == matcher))


def merge():
    """Production order (adopt.py:557-561) plus an idempotency check after every merge."""
    bk = backup.Backup()
    t = paths.claude_home() / "settings.json"
    if t.exists() and sm.would_change():
        bk.save_copy(t, "settings.json before loadout merge")
    sm.backup_snapshot(bk)
    sm.apply_settings()
    s1, n1 = S(), SNAP()
    sm.apply_settings()
    assert S() == s1, "second apply changed settings.json:\n" + json.dumps(s1.get("hooks")) + "\n->\n" + json.dumps(S().get("hooks"))
    assert SNAP() == n1, "second apply changed the snapshot"
    assert not [d for d in sm.drift() if d.startswith("hooks")], sm.drift()
    return bk


def hand_intact():
    for c in ["rtk hook claude", "serena-hooks remind --client=claude-code"]:
        assert cnt(c) == 1, c


# 1. user deletes an applied hook: not re-added on this merge NOR the next one
def test_deleted_applied_hook_stays_deleted_over_two_merges(machine):
    s = S(); s["hooks"]["PreToolUse"].pop(3); wS(s)  # no hand copy
    wP({"hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [LINT]}]}})
    merge(); assert cnt() == 1
    s = S(); s["hooks"]["PreToolUse"] = [g for g in s["hooks"]["PreToolUse"] if g.get("matcher") != "Edit"]; wS(s)
    sm.apply_settings(); assert cnt() == 0, "re-added on first merge"
    sm.apply_settings(); assert cnt() == 0, "re-added on second merge"


# 1b. same, but user deletes and the personal layer then changes the timeout
def test_deleted_then_timeout_change(machine):
    s = S(); s["hooks"]["PreToolUse"].pop(3); wS(s)
    wP({"hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [LINT]}]}})
    merge()
    s = S(); s["hooks"]["PreToolUse"] = [g for g in s["hooks"]["PreToolUse"] if g.get("matcher") != "Edit"]; wS(s)
    wP({"hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [{**LINT, "timeout": 7}]}]}})
    sm.apply_settings(); first = cnt()
    sm.apply_settings(); second = cnt()
    assert (first, second) == (0, 0), (first, second)


# 1c. user changes the matcher of an applied hook (Edit -> Edit|Write): must not run twice for Edit
def test_user_changes_matcher_of_applied_hook(machine):
    s = S(); s["hooks"]["PreToolUse"].pop(3); wS(s)
    wP({"hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [LINT]}]}})
    merge()
    s = S()
    for g in s["hooks"]["PreToolUse"]:
        if g.get("matcher") == "Edit": g["matcher"] = "Edit|Write"
    wS(s)
    sm.apply_settings(); sm.apply_settings()
    assert cnt() == 1, json.dumps(S()["hooks"]["PreToolUse"])


# 2. user edits an applied hook; personal timeout edit afterwards
def test_user_edit_then_personal_timeout(machine):
    s = S(); s["hooks"]["PreToolUse"].pop(3); wS(s)
    wP({"hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [LINT]}]}})
    merge()
    s = S()
    for _, _, h in hooks(s):
        if h.get("command") == "my-own-linter": h["timeout"] = 99
    wS(s)
    merge()
    assert [h.get("timeout") for _, _, h in hooks() if h.get("command") == "my-own-linter"] == [99]
    wP({"hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [{**LINT, "timeout": 5}]}]}})
    merge()
    t = [h.get("timeout") for _, _, h in hooks() if h.get("command") == "my-own-linter"]
    assert t == [99], "M2: the user's edit must survive a personal-layer change"
    assert not [h for _, _, h in hooks(SNAP()) if h.get("command") == "my-own-linter"], SNAP()
    wP({}); merge()
    assert [h.get("timeout") for _, _, h in hooks() if h.get("command") == "my-own-linter"] == [99]


# 3. record on A, pull on B (B: hand copy inside a multi-hook group), then edits/removal
def test_A_record_B_multi_group(fake_home, fake_runner, tmp_path, monkeypatch):
    personal = tmp_path / "personal"; personal.mkdir()
    monkeypatch.setenv("LOADOUT_PERSONAL", str(personal))
    A = fake_home; author_machine(A)
    v = _get("hook", "PreToolUse:Edit")
    adopt.apply_own([(v, own.Choice("global"))], backup.Backup())
    merge(); assert cnt() == 1
    B = tmp_path / "B"; B.mkdir(); monkeypatch.setenv("HOME", str(B)); author_machine(B)
    s = S()
    s["hooks"]["PreToolUse"][3]["hooks"] = [{"type": "command", "command": "fmt"}, LINT, {"type": "command", "command": "z"}]
    wS(s)
    merge(); assert cnt() == 1 and cnt("fmt") == 1 and cnt("z") == 1
    assert not list(hooks(SNAP())), SNAP()  # B's copy is the user's, not recorded
    p = P(); p["hooks"]["PreToolUse"][0]["hooks"][0]["timeout"] = 3; wP(p)
    merge(); assert cnt() == 1
    # B's hand copy untouched (no timeout) – the personal change must not modify it
    assert [h.get("timeout") for _, _, h in hooks() if h.get("command") == "my-own-linter"] == [None]
    wP({}); merge()
    assert cnt() == 1 and cnt("fmt") == 1 and cnt("z") == 1
    hand_intact()
    monkeypatch.setenv("HOME", str(A))
    merge(); assert cnt() == 0, "A keeps the hook after removal"
    hand_intact()


# 4. matcher missing vs "": personal group without matcher, hand copy with matcher ""
def test_matcher_missing_vs_empty(machine):
    s = S(); s["hooks"]["Stop"][0]["matcher"] = ""; wS(s)
    trig = s["hooks"]["Stop"][0]["hooks"][0]
    wP({"hooks": {"Stop": [{"hooks": [trig]}]}})
    merge(); assert cnt(trig["command"]) == 1
    wP({"hooks": {"Stop": [{"matcher": None, "hooks": [{**trig, "timeout": 2}]}]}})
    merge(); assert cnt(trig["command"]) == 1
    wP({}); merge(); assert cnt(trig["command"]) == 1


# 5. exec form: same command, different args are different hooks; same args is the user's copy
def test_exec_form(machine):
    E1 = {"type": "command", "command": "node", "args": ["/a.js"]}
    E2 = {"type": "command", "command": "node", "args": ["/b.js"]}
    s = S(); s["hooks"]["Stop"][0]["hooks"].append(E1); wS(s)
    wP({"hooks": {"Stop": [{"hooks": [E1, E2]}]}})
    merge()
    a = [h for _, _, h in hooks() if h.get("args") == ["/a.js"]]
    b = [h for _, _, h in hooks() if h.get("args") == ["/b.js"]]
    assert len(a) == 1 and len(b) == 1
    wP({"hooks": {"Stop": [{"hooks": [{**E2, "timeout": 4}]}]}}); merge()
    assert [h.get("timeout") for _, _, h in hooks() if h.get("args") == ["/b.js"]] == [4]
    wP({}); merge()
    assert len([h for _, _, h in hooks() if h.get("args") == ["/a.js"]]) == 1
    assert len([h for _, _, h in hooks() if h.get("args") == ["/b.js"]]) == 0


# 6. two personal groups with the same identity
def test_two_personal_groups_same_identity(machine):
    s = S(); s["hooks"]["PreToolUse"].pop(3); wS(s)
    wP({"hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [{**LINT, "timeout": 1}]},
                                 {"matcher": "Edit", "hooks": [{**LINT, "timeout": 2}]}]}})
    merge(); assert cnt() == 1
    wP({"hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [{**LINT, "timeout": 2}]}]}}); merge(); assert cnt() == 1
    wP({}); merge(); assert cnt() == 0


# 7. old-format snapshot (fix pass 2: whole desired groups) upgrade
def test_old_snapshot_upgrade_with_hand_copy(machine):
    # fix pass 2 skipped a group whose commands all existed (hand copy) -> not in old snapshot.
    # group [LINT, lint2] with LINT by hand -> fix pass 2 applied the whole group (LINT twice) and recorded it.
    s = S(); s["hooks"]["PreToolUse"].append({"matcher": "Edit", "hooks": [LINT, {"type": "command", "command": "lint2"}]}); wS(s)
    wSNAP({"hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [LINT, {"type": "command", "command": "lint2"}]}]}})
    wP({"hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [LINT, {"type": "command", "command": "lint2"}]}]}})
    merge()
    wP({}); merge()
    assert cnt() == 1 and cnt("lint2") == 0, json.dumps(S()["hooks"]["PreToolUse"])
    hand_intact()


# 8. restore of the adopt backup on A
def test_restore_adopt_backup(machine):
    v = _get("hook", "PreToolUse:Edit")
    before = S()
    bk = backup.Backup()
    adopt.apply_own([(v, own.Choice("global"))], bk)
    merge()
    backup.restore(bk.root)
    assert S() == before, json.dumps(S()["hooks"])
    merge()
    assert cnt() == 1 and S()["hooks"] == before["hooks"]
    assert not list(hooks(SNAP()))


# 9. restore of a merge backup, then continue
def test_restore_merge_backup(machine):
    v = _get("hook", "PreToolUse:Edit")
    adopt.apply_own([(v, own.Choice("global"))], backup.Backup())
    p = P(); p["hooks"]["PreToolUse"][0]["hooks"][0]["timeout"] = 9; wP(p)
    bk = merge()
    backup.restore(bk.root)
    assert [h.get("timeout") for _, _, h in hooks() if h.get("command") == "my-own-linter"] == [None]
    merge(); assert cnt() == 1
    assert [h.get("timeout") for _, _, h in hooks() if h.get("command") == "my-own-linter"] == [9]
    wP({}); merge(); assert cnt() == 0
    hand_intact()


# 10. adopt on A when the same command also sits under another matcher (user's own)
def test_adopt_with_same_command_under_other_matcher(machine):
    s = S(); s["hooks"]["PreToolUse"][0]["hooks"].append(LINT); wS(s)  # Bash group also runs my-own-linter
    v = _get("hook", "PreToolUse:Edit")
    adopt.apply_own([(v, own.Choice("global"))], backup.Backup())
    assert cnt(matcher="Bash") == 1, "user's Bash hook lost"
    assert cnt(matcher="Edit") == 1, "adopted Edit hook lost"
    merge()
    assert cnt(matcher="Bash") == 1 and cnt(matcher="Edit") == 1


# 11. record_global when the personal layer has the command under another matcher
def test_record_global_other_matcher_in_personal(machine):
    wP({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [LINT]}]}})
    merge()
    v = _get("hook", "PreToolUse:Edit")
    adopt.apply_own([(v, own.Choice("global"))], backup.Backup())
    ms = [g.get("matcher") for g in P()["hooks"]["PreToolUse"]]
    assert "Edit" in ms and "Bash" in ms, ms


# 12. user re-adds a deleted applied hook by hand, then the personal layer drops it -> user's copy stays
def test_user_readds_by_hand_then_personal_drops(machine):
    s = S(); s["hooks"]["PreToolUse"].pop(3); wS(s)
    wP({"hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [LINT]}]}})
    merge()
    s = S(); s["hooks"]["PreToolUse"] = [g for g in s["hooks"]["PreToolUse"] if g.get("matcher") != "Edit"]; wS(s)
    sm.apply_settings()
    s = S(); s["hooks"]["PreToolUse"].append({"matcher": "Edit", "hooks": [LINT]}); wS(s)
    sm.apply_settings()
    assert cnt() == 1
    wP({}); sm.apply_settings()
    assert cnt() == 1, "the user's re-added copy is theirs and stays"


# 13. non-list event value in current is not clobbered
def test_non_list_event_value(machine):
    s = S(); s["hooks"]["PostToolUse"] = {"weird": 1}; wS(s)
    wP({"hooks": {"PostToolUse": [{"matcher": "Edit", "hooks": [LINT]}]}})
    sm.apply_settings()
    assert S()["hooks"]["PostToolUse"] == {"weird": 1}


# 14. idempotency/drift over the full author machine with a busy personal layer
def test_busy_idempotent(machine):
    wP({"hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [LINT, {"type": "command", "command": "rtk hook claude"}]},
                                 {"matcher": "Bash", "hooks": [{"type": "command", "command": "rtk hook claude"}]},
                                 {"hooks": [{"type": "command", "command": "serena-hooks remind --client=claude-code"}]}],
                  "Stop": [{"hooks": [{"type": "prompt", "prompt": "x"}]}]}})
    merge(); merge()
    assert cnt("rtk hook claude", "Bash") == 1 and cnt("serena-hooks remind --client=claude-code") == 1
    wP({}); merge()
    assert cnt("rtk hook claude", "Bash") == 1 and cnt("serena-hooks remind --client=claude-code") == 1 and cnt() == 1
    assert cnt("rtk hook claude", "Edit") == 0


def test_record_global_other_matcher_effect_on_settings(machine):
    wP({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [LINT]}]}})
    merge()
    assert cnt(matcher="Edit") == 1 and cnt(matcher="Bash") == 1
    v = _get("hook", "PreToolUse:Edit")
    adopt.apply_own([(v, own.Choice("global"))], backup.Backup())
    assert (cnt(matcher="Edit"), cnt(matcher="Bash")) == (1, 1)
    sm.apply_settings()
    assert (cnt(matcher="Edit"), cnt(matcher="Bash")) == (1, 1)


def test_adopt_other_matcher_then_merges(machine):
    s = S(); s["hooks"]["PreToolUse"][0]["hooks"].append(LINT); wS(s)
    v = _get("hook", "PreToolUse:Edit")
    adopt.apply_own([(v, own.Choice("global"))], backup.Backup())
    r = []
    for _ in range(3):
        sm.apply_settings(); r.append((cnt(matcher="Edit"), cnt(matcher="Bash")))
    assert r == [(1, 1)] * 3


# C1: the tombstone holds over three merges, also when the personal layer changes the hook meanwhile,
# and goes when the hook leaves desired.
def test_tombstone_three_merges_then_leaves_desired(machine):
    s = S(); s["hooks"]["PreToolUse"].pop(3); wS(s)
    wP({"hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [LINT]}]}})
    merge(); assert cnt() == 1
    s = S(); s["hooks"]["PreToolUse"] = [g for g in s["hooks"]["PreToolUse"] if g.get("matcher") != "Edit"]; wS(s)
    for timeout in (None, 7, 8):
        if timeout:
            wP({"hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [{**LINT, "timeout": timeout}]}]}})
        merge(); assert cnt() == 0
    assert "my-own-linter" in json.dumps(SNAP())  # the tombstone
    wP({}); merge()
    assert cnt() == 0 and "my-own-linter" not in json.dumps(SNAP())
    # back in desired after the tombstone went: a new hook, added again
    wP({"hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [LINT]}]}})
    merge(); assert cnt() == 1
    hand_intact()


def test_tombstone_two_merges_via_merge_settings():
    prev = {"hooks": {"Stop": [{"hooks": [LINT]}]}}
    want = {"hooks": {"Stop": [{"hooks": [LINT]}]}}
    cur = {"effortLevel": "low"}
    snap = sm.effective_desired(cur, want, prev)
    assert sm.merge_settings(cur, want, prev) == cur
    assert sm.merge_settings(cur, want, snap) == cur
    snap2 = sm.effective_desired(cur, want, snap)
    assert snap2 == snap and sm.merge_settings(cur, want, snap2) == cur
    assert sm.effective_desired(cur, {}, snap2) == {}


# C1c via merge_settings: matcher change is a deletion plus a user hook
def test_matcher_change_is_delete_plus_user_hook():
    prev = {"hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [LINT]}]}}
    cur = {"hooks": {"PreToolUse": [{"matcher": "Edit|Write", "hooks": [LINT]}]}}
    want = prev
    for _ in range(3):
        assert sm.merge_settings(cur, want, prev) == cur
        prev = sm.effective_desired(cur, want, prev)
    assert sm.merge_settings(cur, {}, prev) == cur


# M1: a non-list event value is skipped for adding and for removing
def test_non_list_event_value_left_alone_on_removal():
    prev = {"hooks": {"Stop": [{"hooks": [LINT]}]}}
    cur = {"hooks": {"Stop": {"weird": 1}}}
    assert sm.merge_settings(cur, {}, prev) == cur
    assert sm.merge_settings(cur, prev, {}) == cur
    assert "Stop" not in json.dumps(sm.effective_desired(cur, prev, {}).get("hooks", {}))


# M2 via merge_settings: an edited applied hook is the user's and leaves the snapshot
def test_user_edited_applied_hook_is_theirs():
    applied = {"hooks": {"Stop": [{"hooks": [LINT]}]}}
    cur = {"hooks": {"Stop": [{"hooks": [{**LINT, "timeout": 99}]}]}}
    new = {"hooks": {"Stop": [{"hooks": [{**LINT, "timeout": 5}]}]}}
    assert sm.merge_settings(cur, applied, applied) == cur
    assert sm.merge_settings(cur, new, applied) == cur
    assert sm.merge_settings(cur, {}, applied) == cur
    assert sm.effective_desired(cur, new, applied).get("hooks") is None


# C2: _replace_hook replaces exactly the slot and drops only copies of the new identity
def test_replace_hook_exact_slot():
    other = {"type": "command", "command": "x"}
    groups = [{"matcher": "Bash", "hooks": [LINT, other]},
              {"matcher": "Edit", "hooks": [other, LINT]},
              {"matcher": "Edit", "hooks": [{**LINT, "timeout": 1}]}]
    new = {**LINT, "timeout": 3}
    own._replace_hook(groups, "PreToolUse", 1, 1, new)
    assert groups == [{"matcher": "Bash", "hooks": [LINT, other]},
                      {"matcher": "Edit", "hooks": [other, new]}]


def test_replace_hook_keeps_the_old_command_under_its_own_identity():
    raw = {"type": "command", "command": "/home/x/.claude/hooks/a.sh"}
    port = {"type": "command", "command": '"$HOME/.claude/hooks/personal/a.sh"'}
    groups = [{"matcher": "Edit", "hooks": [raw]}, {"matcher": "Write", "hooks": [raw, port]}]
    own._replace_hook(groups, "PreToolUse", 0, 0, port)
    assert groups == [{"matcher": "Edit", "hooks": [port]}, {"matcher": "Write", "hooks": [raw, port]}]
