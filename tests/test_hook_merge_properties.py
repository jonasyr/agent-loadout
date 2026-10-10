"""Seeded model test for the per-hook settings merge (settings_merge._merge_hooks) and the hook recording path
(own.record_global, own._regroup_machine_hook, settings_merge.record_applied_hook).

Random sequences of personal-layer edits, hand edits in ~/.claude/settings.json, merges, records, backup
restores and pulls on a second HOME run against a small pool of hook identities. A ground-truth model tracks,
per HOME and identity, who owns the hook (the user or loadout) and whether the user deleted a hook loadout
applied (a tombstone). After every merge the files must match the model:
  (a) every identity appears at most once in settings.json;
  (b) every user-made hook (added or edited by hand, not adopted) is present and byte-identical;
  (c) a hook the user deleted after loadout applied it is not re-added while it stays desired;
  (d) loadout-applied hooks that left desired are gone (and loadout-applied hooks that stay desired are present,
      equal to the desired hook);
  (e) a second apply_settings changes nothing;
  (f) the snapshot's hooks are exactly the loadout-applied identities, its tombstones exactly the desired
      identities the user deleted.
A restore directly after a merge or record must also put the files back byte for byte.

Model conventions (see the fix pass 4 report): hand edits set a timeout from 50-59 and the personal layer one
from 1-9, so a hand edit never equals a desired hook by chance (an edit that equals desired is treated as in
sync). A hand add never reuses an identity the user deleted since the last merge (the file would be identical
to never having touched it). A restore only runs directly after the merge or record whose backup it replays.
On failure the test prints the seed and a shrunk operation list.
"""
from __future__ import annotations

import copy
import json
import os
import random

import pytest

from loadout import backup, own, paths, settings_merge as sm
from loadout.inventory import Item, Verdict

SEEDS = int(os.environ.get("LOADOUT_PROPERTY_SEEDS", "2000"))  # override to search further offline
FIRST_SEED = int(os.environ.get("LOADOUT_PROPERTY_FIRST_SEED", "0"))
EVENTS = ("PreToolUse", "Stop")
MATCHERS = ("", "Edit", "Edit|Write")
COMMANDS = ("lint-a", "lint-b", "EXEC")
POOL = [(e, m, c) for e in EVENTS for m in MATCHERS for c in COMMANDS]
OPS = {"p_add": 3, "p_field": 2, "p_remove": 2, "u_add": 2, "u_add_group": 1, "u_edit": 2, "u_delete": 2,
       "u_matcher": 1, "merge": 4, "record": 2, "restore": 1, "pull": 2}
KINDS = [k for k, w in OPS.items() for _ in range(w)]


def _hook(cmd: str, timeout: int | None = None) -> dict:
    h = {"type": "command", "command": "node", "args": ["/h.js"]} if cmd == "EXEC" else {"type": "command", "command": cmd}
    if timeout is not None:
        h["timeout"] = timeout
    return h


def _hid(spec) -> tuple:
    e, m, c = spec
    return sm.hook_id(e, {"matcher": m}, _hook(c))


def _load(p):
    return json.loads(p.read_text()) if p.exists() else {}


def _save(p, d):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d))


def _settings():
    return paths.claude_home() / "settings.json"


def _snap():
    return paths.state_dir() / "managed-settings.json"


def _personal():
    return paths.personal_root() / "settings.json"


def _occurrences(d) -> dict:
    """{identity: [(event, gi, hi, hook)]} of a settings dict."""
    out: dict = {}
    for event, gi, hi, _, hook, hid in sm._iter_hooks(d):
        out.setdefault(hid, []).append((event, gi, hi, hook))
    return out


def _drop(d, event, gi, hi):
    groups = d["hooks"][event]
    del groups[gi]["hooks"][hi]
    if not groups[gi]["hooks"]:
        del groups[gi]
        if not groups:
            del d["hooks"][event]


def _files():
    return tuple((p.exists(), p.read_bytes() if p.exists() else b"") for p in (_settings(), _snap(), _personal()))


class Home:
    def __init__(self, root):
        self.root = root
        self.owner: dict = {}      # identity -> "user" | "loadout"
        self.user_dict: dict = {}  # identity -> expected dict of a user-owned hook
        self.tomb: set = set()
        self.snap: set = set()     # identities in the snapshot as of the last merge or record
        self.pending_del: set = set()

    def state(self):
        return copy.deepcopy((self.owner, self.user_dict, self.tomb, self.snap, self.pending_del))

    def set_state(self, st):
        self.owner, self.user_dict, self.tomb, self.snap, self.pending_del = copy.deepcopy(st)


class Run:
    def __init__(self, base):
        self.base = base
        self.homes = [Home(base / "A"), Home(base / "B")]
        self.cur = 0
        self.nbk = 0
        self.restore_next = False  # set by _run: the next operation is a restore
        self.last = None  # (home index, backup root, model state before, files before) of the last merge/record
        os.environ["LOADOUT_PERSONAL"] = str(base / "personal")
        for h in self.homes:
            self._use(h)
            _save(_settings(), {})
        self._use(self.homes[0])

    def _use(self, home):
        os.environ["HOME"] = str(home.root)
        os.environ["USERPROFILE"] = str(home.root)

    @property
    def home(self) -> Home:
        return self.homes[self.cur]

    def desired(self) -> dict:
        return {hid: hook for hid, (hook, _) in sm._hook_map(_load(_personal())).items()}

    def bk(self):
        self.nbk += 1
        return backup.Backup(root=self.base / "bk" / str(self.nbk))

    # -- operations -------------------------------------------------------------------------------------
    def op(self, kind, r):
        rnd = random.Random(r)
        home = self.home
        last, self.last = self.last, None
        if kind in ("p_add", "p_field", "p_remove"):
            p = _load(_personal())
            occ = _occurrences(p)
            if kind == "p_add":
                free = [s for s in POOL if _hid(s) not in occ]
                if not free:
                    return
                e, m, c = rnd.choice(free)
                hook = _hook(c, rnd.choice([None, rnd.randint(1, 9)]))
                groups = p.setdefault("hooks", {}).setdefault(e, [])
                same = [g for g in groups if g.get("matcher") in ((m,) if m else ("", None))]
                if same and rnd.random() < 0.5:
                    same[0]["hooks"].append(hook)  # into an existing group
                elif m or rnd.random() < 0.5:
                    groups.append({"matcher": m, "hooks": [hook]})
                else:
                    groups.append({"hooks": [hook]})  # a missing matcher equals ""
            else:
                if not occ:
                    return
                hid = rnd.choice(sorted(occ, key=repr))
                if kind == "p_field":
                    for e, gi, hi, hook in occ[hid]:
                        old = hook.get("timeout")
                        hook["timeout"] = rnd.choice([t for t in range(1, 10) if t != old])
                else:
                    for e, gi, hi, _ in reversed(occ[hid]):
                        _drop(p, e, gi, hi)
            _save(_personal(), p)
            return
        if kind in ("u_add", "u_add_group", "u_edit", "u_delete", "u_matcher"):
            s = _load(_settings())
            occ = _occurrences(s)
            if kind in ("u_add", "u_add_group"):
                free = [sp for sp in POOL if _hid(sp) not in occ and _hid(sp) not in home.pending_del]
                if kind == "u_add_group":
                    free = [sp for sp in free if any(isinstance(g, dict) and g.get("matcher", "") == sp[1]
                                                     for g in (s.get("hooks") or {}).get(sp[0]) or [])]
                if not free:
                    return
                e, m, c = rnd.choice(free)
                hook = _hook(c, rnd.choice([None, rnd.randint(50, 59)]))
                groups = s.setdefault("hooks", {}).setdefault(e, [])
                target = next((g for g in groups if g.get("matcher", "") == m), None) if kind == "u_add_group" else None
                if target is not None:
                    target["hooks"].append(hook)
                else:
                    groups.append({"matcher": m, "hooks": [hook]} if m or rnd.random() < 0.5 else {"hooks": [hook]})
                hid = _hid((e, m, c))
                home.owner[hid], home.user_dict[hid] = "user", copy.deepcopy(hook)
            else:
                if not occ:
                    return
                hid = rnd.choice(sorted(occ, key=repr))
                (e, gi, hi, hook), = occ[hid]
                if kind == "u_edit":
                    old = hook.get("timeout")
                    hook["timeout"] = rnd.choice([t for t in range(50, 60) if t != old])
                    home.owner[hid], home.user_dict[hid] = "user", copy.deepcopy(hook)
                else:
                    new_hid = None
                    if kind == "u_matcher":
                        cmd = "EXEC" if "args" in hook else hook["command"]
                        options = [m for m in MATCHERS if m != hid[1] and _hid((e, m, cmd)) not in occ
                                   and _hid((e, m, cmd)) not in home.pending_del]
                        if not options:
                            return
                        m = rnd.choice(options)
                        group = s["hooks"][e][gi]
                        if len(group["hooks"]) == 1:
                            group["matcher"] = m
                        else:
                            del group["hooks"][hi]
                            s["hooks"][e].append({"matcher": m, "hooks": [hook]})
                        new_hid = _hid((e, m, cmd))
                    else:
                        _drop(s, e, gi, hi)
                    home.owner.pop(hid, None)
                    home.user_dict.pop(hid, None)
                    if hid in home.snap:
                        home.tomb.add(hid)
                    home.pending_del.add(hid)
                    if new_hid is not None:
                        home.owner[new_hid], home.user_dict[new_hid] = "user", copy.deepcopy(hook)
            _save(_settings(), s)
            return
        if kind == "pull":
            self.cur = 1 - self.cur
            self._use(self.home)
            return self.merge()
        if kind == "merge":
            return self.merge()
        if kind == "record":
            users = sorted((hid for hid, o in home.owner.items() if o == "user"), key=repr)
            if not users:
                return
            hid = rnd.choice(users)
            event, matcher = hid[0], hid[1]
            hook = home.user_dict[hid]
            item = Item("hook", f"{event}:{matcher}", hook["command"], "~/.claude/settings.json", {"event": event})
            before = (home.state(), _files())
            bk = self.bk()
            rec = own.record_global(Verdict(item, "own", "test"), bk)
            assert rec.ok, rec.lines
            rec.machine()
            home.owner[hid] = "loadout"
            home.user_dict.pop(hid, None)
            home.tomb.discard(hid)
            home.snap.add(hid)
            self.merge(bk, before)
            return
        if kind == "restore":
            if last is None or last[0] != self.cur:
                return
            _, root, st, files = last
            if not (root / "manifest.json").exists():
                return
            lines, ok, _ = backup.restore(root)
            assert ok, lines
            assert _files() == files, "restore did not put the files back"
            home.set_state(st)
            return
        raise AssertionError(kind)

    def merge(self, bk=None, before=None):
        """A merge in the order adopt and update use (back up settings.json and the snapshot, then apply).
        The backup is only taken when a restore follows (it costs time and is checked by that restore)."""
        home = self.home
        if bk is not None or self.restore_next:
            if before is None:
                before = (home.state(), _files())
            bk = bk or self.bk()
            if _settings().exists() and sm.would_change():
                bk.save_copy(_settings(), "settings.json before loadout merge")
            sm.backup_snapshot(bk)
        want = self.desired()
        # predict
        for hid in set(home.owner) | home.tomb | set(want):
            owner = home.owner.get(hid)
            if owner == "user":
                if hid not in want:
                    home.tomb.discard(hid)
            elif owner == "loadout":
                if hid not in want:
                    del home.owner[hid]
            elif hid in want:
                if hid not in home.tomb:
                    home.owner[hid] = "loadout"
            else:
                home.tomb.discard(hid)
        home.pending_del.clear()
        home.snap = {hid for hid, o in home.owner.items() if o == "loadout"}
        sm.apply_settings()
        self.check(want)
        if bk is not None:
            self.last = (self.cur, bk.root, *before)

    def check(self, want):
        home = self.home
        s = _load(_settings())
        occ = _occurrences(s)
        for hid, places in occ.items():
            assert len(places) == 1, f"(a) {hid} appears {len(places)} times"
        for hid in set(occ) | set(home.owner) | home.tomb | set(want):
            owner = home.owner.get(hid)
            got = occ[hid][0][3] if hid in occ else None
            if owner == "user":
                assert got == home.user_dict[hid], f"(b) user hook {hid}: {got} != {home.user_dict[hid]}"
            elif owner == "loadout":
                assert got == want[hid], f"(d) applied hook {hid}: {got} != desired {want[hid]}"
            elif hid in home.tomb:
                assert got is None, f"(c) deleted hook {hid} re-added"
            else:
                assert got is None, f"(d) hook {hid} should be gone, found {got}"
        files = _files()
        sm.apply_settings()
        assert _files() == files, "(e) second apply_settings changed something"
        snap = _load(_snap())
        applied = set(sm._hook_map(snap))
        tombs = set(sm._hook_map({"hooks": snap.get(sm.TOMBSTONES)}))
        assert applied == home.snap, f"(f) snapshot hooks {applied} != applied {home.snap}"
        assert tombs == home.tomb, f"(f) tombstones {tombs} != {home.tomb}"


def _sequence(seed):
    rnd = random.Random(seed)
    ops = [(rnd.choice(KINDS), rnd.randrange(1 << 30)) for _ in range(rnd.randint(5, 11))]
    return ops + [("merge", 0)]


def _run(base, ops):
    """None when the sequence holds every invariant, else the failure message."""
    base.mkdir(parents=True)
    run = Run(base)
    try:
        for i, (kind, r) in enumerate(ops):
            run.restore_next = i + 1 < len(ops) and ops[i + 1][0] == "restore"
            run.op(kind, r)
    except AssertionError as exc:
        return f"{type(exc).__name__}: {exc}"
    return None


def _shrink(tmp, ops):
    n = [0]

    def fails(seq):
        n[0] += 1
        return _run(tmp / f"shrink{n[0]}", seq)

    msg = fails(ops)
    changed = True
    while changed:
        changed = False
        for i in range(len(ops)):
            trial = ops[:i] + ops[i + 1:]
            m = fails(trial)
            if m is not None:
                ops, msg, changed = trial, m, True
                break
    return ops, msg


def test_hook_merge_invariants_hold_for_random_sequences(tmp_path, monkeypatch, fake_runner):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("LOADOUT_PERSONAL", str(tmp_path / "personal"))
    kit = tmp_path / "kit"  # a small kit (the real one has no hooks; its other keys only cost time here)
    _save(kit / "settings.base.json", {"env": {"MCP_TIMEOUT": "60000"}, "permissions": {"allow": ["Bash(x:*)"]}})
    monkeypatch.setenv("LOADOUT_ROOT", str(kit))
    steps = 0
    for seed in range(FIRST_SEED, FIRST_SEED + SEEDS):
        ops = _sequence(seed)
        steps += len(ops)
        msg = _run(tmp_path / f"s{seed}", ops)
        if msg is not None:
            small, small_msg = _shrink(tmp_path / f"shrink-{seed}", ops)
            pytest.fail(f"seed {seed}: {msg}\nshrunk to {len(small)} ops: {small}\n-> {small_msg}")
    assert steps >= SEEDS * 6
