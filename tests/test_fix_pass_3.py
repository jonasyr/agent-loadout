"""Fix pass 3 for the adopt/own tools: per-hook three-way merge, restored line-rule secrets, UTF-16 views."""
import json
import os

import pytest

from loadout import adopt, backup, inventory, own, paths, settings_merge as sm
from fixtures import author_machine


@pytest.fixture
def machine(fake_home, fake_runner):
    author_machine(fake_home)
    return fake_home


def _get(kind, name):
    vs = inventory.classify(inventory.collect(with_versions=False))
    return next(v for v in vs if v.item.kind == kind and v.item.name == name)


def S():
    return json.loads((paths.claude_home() / "settings.json").read_text())


def wS(d):
    (paths.claude_home() / "settings.json").write_text(json.dumps(d))


def P():
    p = paths.personal_root() / "settings.json"
    return json.loads(p.read_text()) if p.exists() else {}


def wP(d):
    p = paths.personal_root() / "settings.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d))


def SNAP():
    p = paths.state_dir() / "managed-settings.json"
    return json.loads(p.read_text()) if p.exists() else {}


def _hooks_of(data):
    for event, groups in (data.get("hooks") or {}).items():
        for g in groups:
            for h in g.get("hooks", []):
                yield event, g, h


def cnt(cmd="my-own-linter"):
    return sum(1 for _, _, h in _hooks_of(S()) if h.get("command") == cmd)


def merge():
    bk = backup.Backup()
    sm.backup_snapshot(bk)
    sm.apply_settings()
    return bk


LINT = {"type": "command", "command": "my-own-linter"}
HAND_HOOKS = ["rtk hook claude", "serena-hooks remind --client=claude-code",
              "'/home/x/.claude/hooks/sonar-secrets/build-scripts/pretool-secrets.sh'",
              "python3 /home/x/.claude/plugins/cache/severity1-marketplace/auto-memory/0.9.2/scripts/trigger.py"]


def _users_hooks_intact(*extra):
    for cmd in [*HAND_HOOKS, *extra]:
        assert cnt(cmd) == 1, (cmd, json.dumps(S().get("hooks")))


# ---------------------------------------------------------------------------------------------------------
# Part 1: sequences from the re-review (/tmp/claude-1000/rr3/test_merge_seq.py), ported with assertions


def test_s4_record_on_B_with_different_timeout_after_A(machine):
    # personal layer already has A's group (timeout 5); B has the same hook by hand without a timeout
    wP({"hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [{**LINT, "timeout": 5}]}]}})
    merge()
    assert cnt() == 1
    v = _get("hook", "PreToolUse:Edit")
    adopt.apply_own([(v, own.Choice("global"))], backup.Backup())
    assert sum(1 for _, _, h in _hooks_of(P()) if h.get("command") == "my-own-linter") == 1, P()
    merge()
    assert cnt() == 1, "duplicate on B"
    _users_hooks_intact()


def test_s13_personal_adds_command_to_group_B_handcopy(machine):
    s = S()
    s["hooks"]["PreToolUse"][3]["hooks"].append({"type": "command", "command": "fmt"})
    wS(s)  # B: multi-hook hand group
    wP({"hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [LINT]}]}})
    merge()
    assert cnt() == 1
    wP({"hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [LINT, {"type": "command", "command": "lint2"}]}]}})
    merge()
    assert cnt() == 1, "linter twice after personal group gained a hook"
    assert cnt("lint2") == 1 and cnt("fmt") == 1
    _users_hooks_intact()


def test_s13_lint2_lands_in_the_hand_group_and_leaves_with_the_personal_layer(machine):
    s = S()
    s["hooks"]["PreToolUse"][3]["hooks"].append({"type": "command", "command": "fmt"})
    wS(s)
    wP({"hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [LINT, {"type": "command", "command": "lint2"}]}]}})
    merge()
    edit = [g for g in S()["hooks"]["PreToolUse"] if g.get("matcher") == "Edit"]
    assert len(edit) == 1 and [h["command"] for h in edit[0]["hooks"]] == ["my-own-linter", "fmt", "lint2"]
    wP({})
    merge()
    assert cnt() == 1 and cnt("fmt") == 1 and cnt("lint2") == 0
    _users_hooks_intact()


def test_s_seq_A_record_timeout_remove(machine):
    v = _get("hook", "PreToolUse:Edit")
    adopt.apply_own([(v, own.Choice("global"))], backup.Backup())
    assert cnt() == 1
    p = P()
    p["hooks"]["PreToolUse"][0]["hooks"][0]["timeout"] = 9
    wP(p)
    merge()
    assert cnt() == 1
    assert '"timeout": 9' in json.dumps(S())
    wP({})
    merge()
    assert cnt() == 0
    _users_hooks_intact()


def test_s_seq_A_record_restore_then_merge(machine):
    v = _get("hook", "PreToolUse:Edit")
    bk = backup.Backup()
    adopt.apply_own([(v, own.Choice("global"))], bk)
    p = P()
    p["hooks"]["PreToolUse"][0]["hooks"][0]["timeout"] = 9
    wP(p)
    merge()
    backup.restore(bk.root)
    merge()
    assert cnt() == 1
    _users_hooks_intact()


def test_s_seq_A_record_timeout_restore_timeout_backup(machine):
    v = _get("hook", "PreToolUse:Edit")
    adopt.apply_own([(v, own.Choice("global"))], backup.Backup())
    p = P()
    p["hooks"]["PreToolUse"][0]["hooks"][0]["timeout"] = 9
    wP(p)
    bk2 = merge()
    backup.restore(bk2.root)  # snapshot back to the version without the timeout; settings.json keeps it
    merge()
    assert cnt() == 1
    wP({})
    merge()
    assert cnt() == 0, json.dumps(S()["hooks"])
    _users_hooks_intact()


def test_B_hand_multi_then_timeout_then_remove(machine):
    s = S()
    s["hooks"]["PreToolUse"][3]["hooks"].append({"type": "command", "command": "fmt"})
    wS(s)
    wP({"hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [LINT]}]}})
    merge()
    assert cnt() == 1
    wP({"hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [{**LINT, "timeout": 4}]}]}})
    merge()
    assert cnt() == 1
    wP({})
    merge()
    assert cnt() == 1
    assert cnt("fmt") == 1
    _users_hooks_intact()


def test_B_hand_then_user_removes_own_then_remove(machine):
    wP({"hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [LINT]}]}})
    merge()
    assert cnt() == 1
    s = S()
    s["hooks"]["PreToolUse"].pop(3)
    wS(s)
    merge()
    assert cnt() == 1
    wP({"hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [{**LINT, "timeout": 4}]}]}})
    merge()
    assert cnt() == 1
    assert '"timeout": 4' in json.dumps(S())
    wP({})
    merge()
    assert cnt() == 0
    _users_hooks_intact()


def test_B_hand_copy_differs_matcher_missing_vs_empty(machine):
    s = S()
    s["hooks"]["Stop"].append({"hooks": [{"type": "command", "command": "x-stop"}]})
    wS(s)
    wP({"hooks": {"Stop": [{"matcher": "", "hooks": [{"type": "command", "command": "x-stop"}]}]}})
    merge()
    assert cnt("x-stop") == 1
    _users_hooks_intact()


def test_A_applied_user_edits_own_copy_add_hook(machine):
    # loadout applied the group on this machine; the user then adds a hook into that same group by hand
    wS({"hooks": {}})
    wP({"hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [LINT]}]}})
    merge()
    assert cnt() == 1
    s = S()
    s["hooks"]["PreToolUse"][0]["hooks"].append({"type": "command", "command": "mine"})
    wS(s)
    merge()
    assert cnt() == 1, "applied group edited by user -> duplicate"
    wP({})
    merge()
    assert cnt("mine") == 1
    assert cnt() == 0


def test_A_applied_user_edits_timeout_then_remove(machine):
    wS({"hooks": {}})
    wP({"hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [LINT]}]}})
    merge()
    s = S()
    s["hooks"]["PreToolUse"][0]["hooks"][0]["timeout"] = 7
    wS(s)
    merge()
    assert S()["hooks"]["PreToolUse"][0]["hooks"] == [{**LINT, "timeout": 7}], "user's timeout edit overwritten"
    wP({})
    merge()
    assert S()["hooks"]["PreToolUse"][0]["hooks"] == [{**LINT, "timeout": 7}], "user-edited hook removed"


# ---------------------------------------------------------------------------------------------------------
# Part 1: the per-hook rules on merge_settings directly

E = {"type": "command", "command": "echo hi"}


def test_user_deleted_applied_hook_is_not_readded_and_leaves_the_snapshot():
    prev = {"hooks": {"Stop": [{"hooks": [E]}]}}
    desired = {"hooks": {"Stop": [{"hooks": [E]}]}}
    assert sm.merge_settings({"hooks": {}}, desired, prev) == {"hooks": {}}
    assert "hooks" not in sm.effective_desired({"hooks": {}}, desired, prev)


def test_duplicate_identities_in_desired_collapse_last_wins():
    desired = {"hooks": {"Stop": [{"matcher": "", "hooks": [E]}, {"hooks": [{**E, "timeout": 3}]}]}}
    out = sm.merge_settings({}, desired, {})
    assert [h for _, _, h in _hooks_of(out)] == [{**E, "timeout": 3}]
    snap = sm.effective_desired({}, desired, {})
    assert [h for _, _, h in _hooks_of(snap)] == [{**E, "timeout": 3}]


def test_hooks_in_neither_desired_nor_previous_are_never_touched():
    mine = {"hooks": {"Stop": [{"matcher": "x", "hooks": [E, {"type": "command", "command": "a"}]}]}}
    desired = {"hooks": {"Stop": [{"matcher": "x", "hooks": [{"type": "command", "command": "b"}]}]}}
    out = sm.merge_settings(mine, desired, {})
    assert out["hooks"]["Stop"] == [{"matcher": "x", "hooks": [E, {"type": "command", "command": "a"},
                                                               {"type": "command", "command": "b"}]}]
    assert sm.merge_settings(out, {}, sm.effective_desired(mine, desired, {})) == mine


def test_removed_hook_leaves_no_empty_group():
    g = {"matcher": "Bash", "hooks": [E]}
    other = {"matcher": "Read", "hooks": [{"type": "command", "command": "x"}]}
    out = sm.merge_settings({"hooks": {"Stop": [g, other]}}, {}, {"hooks": {"Stop": [g]}})
    assert out == {"hooks": {"Stop": [other]}}


def test_non_hook_keys_keep_the_three_way_merge():
    current = {"effortLevel": "high", "permissions": {"allow": ["a", "u"]}, "hooks": {"Stop": [{"hooks": [E]}]}}
    previous = {"permissions": {"allow": ["a", "b"]}, "effortLevel": "high"}
    desired = {"permissions": {"allow": ["c"]}}
    out = sm.merge_settings(current, desired, previous)
    assert out == {"permissions": {"allow": ["u", "c"]}, "hooks": {"Stop": [{"hooks": [E]}]}}


def test_old_snapshot_format_still_counts_as_applied(machine):
    """Fix pass 2 stored whole desired groups (multi-hook too) in the snapshot; they still count as applied."""
    wS({"hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [LINT, {"type": "command", "command": "lint2"}]}]}})
    wP({"hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [LINT, {"type": "command", "command": "lint2"}]}]}})
    snap = paths.state_dir() / "managed-settings.json"
    snap.parent.mkdir(parents=True, exist_ok=True)
    snap.write_text(json.dumps({"hooks": {"PreToolUse": [
        {"matcher": "Edit", "hooks": [LINT, {"type": "command", "command": "lint2"}]}]}}))
    wP({"hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [{**LINT, "timeout": 2}]}]}})
    merge()
    assert cnt() == 1 and '"timeout": 2' in json.dumps(S()), "applied hook from the old snapshot not updated"
    assert cnt("lint2") == 0, "applied hook from the old snapshot not removed"
    wP({})
    merge()
    assert "hooks" not in S() or cnt() == 0


def test_snapshot_records_exactly_the_applied_hooks(machine):
    s = S()
    s["hooks"]["PreToolUse"][3]["hooks"].append({"type": "command", "command": "fmt"})
    wS(s)
    wP({"hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [LINT, {"type": "command", "command": "lint2"}]}]}})
    merge()
    recorded = [(e, g.get("matcher", ""), h) for e, g, h in _hooks_of(SNAP())]
    assert recorded == [("PreToolUse", "Edit", {"type": "command", "command": "lint2"})]


# ---------------------------------------------------------------------------------------------------------
# Part 1: new sequences (each hook runs exactly once, user hooks never lost)


def test_seq_record_pull_on_B_user_adds_hook_timeout_remove(machine, tmp_path, monkeypatch):
    # machine A records the hook; the personal layer is what B pulls
    v = _get("hook", "PreToolUse:Edit")
    adopt.apply_own([(v, own.Choice("global"))], backup.Backup())
    pulled = P()
    assert cnt() == 1
    # machine B: own HOME, hand copy of the hook inside a multi-hook group, same personal layer
    home_b = tmp_path / "home_b"
    home_b.mkdir()
    monkeypatch.setenv("HOME", str(home_b))
    monkeypatch.setenv("USERPROFILE", str(home_b))
    author_machine(home_b)
    s = S()
    s["hooks"]["PreToolUse"][3]["hooks"].append({"type": "command", "command": "fmt"})
    wS(s)
    wP(pulled)
    merge()
    assert cnt() == 1 and cnt("fmt") == 1
    s = S()
    s["hooks"]["PreToolUse"][3]["hooks"].append({"type": "command", "command": "mine2"})
    wS(s)
    merge()
    assert cnt() == 1 and cnt("mine2") == 1
    p = P()
    p["hooks"]["PreToolUse"][0]["hooks"][0]["timeout"] = 11
    wP(p)
    merge()
    assert cnt() == 1
    wP({})
    merge()
    assert cnt() == 1, "B's own hand copy lost"
    _users_hooks_intact("fmt", "mine2")


def test_seq_restore_of_an_older_backup_midway(machine):
    wS({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "keep-me"}]}]}})
    wP({"hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [LINT]}]}})
    old = merge()  # backup with the snapshot before the first apply (none)
    s = S()
    s["hooks"]["PreToolUse"][0]["hooks"].append({"type": "command", "command": "mine"})
    wS(s)
    wP({"hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [{**LINT, "timeout": 3}]}]}})
    merge()
    assert cnt() == 1
    backup.restore(old.root)  # the snapshot goes back to "nothing applied"; settings.json keeps the hook
    merge()
    assert cnt() == 1, json.dumps(S()["hooks"])
    assert cnt("mine") == 1 and cnt("keep-me") == 1
    wP({"hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [{**LINT, "timeout": 8}]}]}})
    merge()
    assert cnt() == 1
    wP({})
    merge()
    assert cnt() <= 1 and cnt("mine") == 1 and cnt("keep-me") == 1


EXEC = {"type": "command", "command": "node", "args": ["/opt/tools/check.js", "--fast"]}


def test_seq_exec_form_hook(machine):
    s = S()
    s["hooks"]["Stop"].append({"matcher": "", "hooks": [{"type": "command", "command": "node", "args": ["/opt/mine.js"]}]})
    wS(s)
    wP({"hooks": {"Stop": [{"hooks": [EXEC]}]}})
    merge()

    def n(args):
        return sum(1 for _, _, h in _hooks_of(S()) if h.get("args") == args)

    assert n(EXEC["args"]) == 1 and n(["/opt/mine.js"]) == 1
    merge()
    assert n(EXEC["args"]) == 1
    wP({"hooks": {"Stop": [{"hooks": [{**EXEC, "timeout": 4}]}]}})
    merge()
    assert n(EXEC["args"]) == 1 and '"timeout": 4' in json.dumps(S())
    wP({})
    merge()
    assert n(EXEC["args"]) == 0 and n(["/opt/mine.js"]) == 1
    _users_hooks_intact()


def test_exec_form_hand_copy_is_the_users():
    mine = {"hooks": {"Stop": [{"hooks": [EXEC]}]}}
    desired = {"hooks": {"Stop": [{"matcher": "", "hooks": [{**EXEC, "timeout": 1}]}]}}
    assert sm.merge_settings(mine, desired, {}) == mine
    other_args = {**EXEC, "args": ["/opt/tools/other.js"]}
    out = sm.merge_settings(mine, {"hooks": {"Stop": [{"hooks": [other_args]}]}}, {})
    assert [h for _, _, h in _hooks_of(out)] == [EXEC, other_args]


def test_record_global_replaces_personal_hook_with_same_identity(machine):
    wP({"hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [{**LINT, "timeout": 5}]},
                                 {"matcher": "Bash", "hooks": [{"type": "command", "command": "other"}]}]}})
    merge()
    v = _get("hook", "PreToolUse:Edit")
    adopt.apply_own([(v, own.Choice("global"))], backup.Backup())
    groups = P()["hooks"]["PreToolUse"]
    assert len(groups) == 2, groups
    assert sum(1 for _, _, h in _hooks_of(P()) if h.get("command") == "my-own-linter") == 1


# ---------------------------------------------------------------------------------------------------------
# hook script proofs (/tmp/claude-1000/rr/pt/test_hooks_proof.py), ported with assertions

@pytest.fixture
def script_home(fake_home, fake_runner):
    (fake_home / "bin").mkdir()
    (fake_home / ".ssh").mkdir()
    (fake_home / "bin/h.sh").write_text("#!/bin/sh\necho hi\n")
    os.chmod(fake_home / "bin/h.sh", 0o755)
    (fake_home / "bin/a.js").write_text("console.log(1)\n")
    (fake_home / "bin/h.js").write_text("console.log(2)\n")
    (fake_home / ".ssh/id_rsa").write_text("x")
    (fake_home / "notes.txt").write_text("n")
    os.symlink(fake_home / ".ssh/id_rsa", fake_home / "bin/link.sh")
    return fake_home


REFUSED = ["cat ~/.ssh/config", '"$HOME"/.ssh/id_rsa', "~/bin/link.sh", "~/bin/h.sh; cat ~/.s''sh/id_ed",
           "cat ~/.s\"\"sh/config"]
ACCEPTED = {"~/bin/h.sh ~/notes.txt": ["h.sh"], "node --require ~/bin/a.js ~/bin/h.js": ["h.js"],
            "bash -c 'cat ~/notes.txt'": [], "~/bin/h.sh $(cat ~/notes.txt)": [], "FOO=1 ~/bin/h.sh": []}


@pytest.mark.parametrize("cmd", REFUSED)
def test_hook_naming_a_private_file_is_refused(script_home, cmd):
    with pytest.raises(own.Collision):
        own._portable_hook({"type": "command", "command": cmd}, backup.Backup(), "x")
    assert not (paths.personal_root() / "hooks").exists() or not any((paths.personal_root() / "hooks").iterdir())


@pytest.mark.parametrize("cmd", list(ACCEPTED))
def test_hook_copies_only_its_script(script_home, cmd):
    own._portable_hook({"type": "command", "command": cmd}, backup.Backup(), "x")
    d = paths.personal_root() / "hooks"
    assert (sorted(p.name for p in d.glob("*")) if d.exists() else []) == ACCEPTED[cmd]
