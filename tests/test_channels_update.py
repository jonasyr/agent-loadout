"""`loadout update` on stable follows releases; `loadout channel` switches between stable and dev (one restore
point per move)."""
import json
import os
import time

import pytest

from loadout import backup, bootstrap, channels, check, codex, commands, locks, maintenance, paths, runner, targets, \
    update

PULLED = "LOADOUT_UPDATE_PULLED"
SHA = "c" * 40  # the kit's HEAD before a move
SHA3 = "d" * 40  # v0.3.0
SHA4 = "e" * 40  # v0.4.0
SLUG = "jonasyr/agent-loadout"
CHANGELOG = "# Changelog\n\n## 0.3.0\n\n- first fix\n- second fix\n\n## 0.2.0\n\n- old\n"
OK_STATUS = '{"urgent": [], "withdrawn": []}'


def _kit(tmp_path, monkeypatch):
    """A kit checkout of its own: the real kit's files, a .git folder of its own (every git call is faked)."""
    kit = tmp_path / "kit"
    kit.mkdir()
    for item in paths.kit_root().iterdir():
        if item.name != ".git":
            (kit / item.name).symlink_to(item)
    (kit / ".git").mkdir()
    monkeypatch.setenv("LOADOUT_ROOT", str(kit))
    return kit


def _g(kit, *args):
    return ("git", "-C", str(kit), *args)


def _world(monkeypatch, claude=True, codex_on=False):
    monkeypatch.setattr(targets, "OVERRIDE", {"claude": claude, "codex": codex_on})
    monkeypatch.setattr(codex, "unavailable", lambda *a, **k: None)
    monkeypatch.setattr(codex, "apply_plugins", lambda bk, **kw: [])
    monkeypatch.setattr(maintenance, "find_outdated", lambda: [])
    monkeypatch.setattr(bootstrap, "missing_tools", lambda *a, **k: [])
    monkeypatch.setattr(check, "run_checks", lambda *a, **k: [])
    monkeypatch.setattr(locks, "FOREGROUND_LIMIT", 1.0)
    monkeypatch.setattr(locks, "POLL", 0.02)


def _git(fake, kit, tags=None, current="v0.2.0", branch="", status="", log=""):
    """The kit's git as faked answers: the remote's release tags, the release HEAD is on, local work."""
    tags = {"v0.3.0": SHA3} if tags is None else tags
    r = fake.responses
    r[_g(kit, "ls-remote")] = runner.Result(0, "".join(f"{s}\trefs/tags/{t}\n" for t, s in tags.items()), "")
    r[_g(kit, "show", "FETCH_HEAD:release-status.json")] = runner.Result(0, OK_STATUS, "")
    r[_g(kit, "show", "v0.3.0:CHANGELOG.md")] = runner.Result(0, CHANGELOG, "")
    r[_g(kit, "describe")] = runner.Result(0, current + "\n", "") if current else runner.Result(128, "", "no tag")
    r[_g(kit, "rev-parse", "HEAD")] = runner.Result(0, SHA + "\n", "")
    r[_g(kit, "rev-parse", "FETCH_HEAD^{commit}")] = runner.Result(0, SHA3 + "\n", "")
    r[_g(kit, "symbolic-ref")] = (runner.Result(0, branch + "\n", "") if branch
                                  else runner.Result(1, "", "not a symbolic ref"))
    r[_g(kit, "status")] = runner.Result(0, status, "")
    r[_g(kit, "log")] = runner.Result(0, log, "")
    r[_g(kit, "remote")] = runner.Result(0, f"https://github.com/{SLUG}.git\n", "")


def _soaked(*names, age=4 * maintenance.DAY):
    channels.record_seen({n: {"v0.3.0": SHA3, "v0.4.0": SHA4}[n] for n in names}, time.time() - age)


def _verbs(fake, kit):
    return [c[3] for c in fake.calls if c[:3] == ["git", "-C", str(kit)]]


def _restarts(monkeypatch):
    seen = []

    def fake_exec(argv):
        seen.append((list(argv), os.environ.get(PULLED), os.environ.get(update.CONTINUED)))
        return 0
    monkeypatch.setattr(update, "_exec", fake_exec)
    return seen


def test_update_on_stable_moves_to_the_eligible_release_and_restarts(fake_home, fake_runner, tmp_path, monkeypatch,
                                                                      capsys):
    _world(monkeypatch)
    monkeypatch.delenv(PULLED, raising=False)
    kit = _kit(tmp_path, monkeypatch)
    channels.set_channel("stable")
    _git(fake_runner, kit)
    _soaked("v0.3.0")
    seen = _restarts(monkeypatch)
    assert update.run(True, lambda q: "", argv=["--yes"]) == 0
    text = capsys.readouterr().out
    assert "kit: v0.2.0 → v0.3.0" in text and "first fix" in text and "second fix" in text
    assert [c for c in fake_runner.calls if c[3:4] == ["checkout"]] == [[*_g(kit), "checkout", "--detach", SHA3]]
    assert "pull" not in _verbs(fake_runner, kit)  # stable never pulls the kit
    assert len(seen) == 1 and seen[0][:2] == (["update", "--yes"], "release:v0.3.0")
    root = seen[0][2]
    manifest = json.loads((tmp_path / root / "manifest.json").read_text())
    assert manifest["description"] == "loadout update: kit to v0.3.0"
    assert manifest["steps"][0]["undo"] == {"run": [*_g(kit), "checkout", "--detach", SHA]}

    # the restarted run: names the move and re-applies, adding to the same restore point
    monkeypatch.setenv(PULLED, seen[0][1])
    monkeypatch.setenv(update.CONTINUED, root)
    fake_runner.responses[_g(kit, "describe")] = runner.Result(0, "v0.3.0\n", "")
    settings = fake_home / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text('{"mine": 1}\n')
    assert update.run(True, lambda q: "", argv=["--yes"]) == 0
    text = capsys.readouterr().out.split("What changed", 1)[1]
    assert "kit: moved to v0.3.0 (this run continued in it" in text and f"loadout restore {root}" in text
    data = json.loads(settings.read_text())
    assert data["extraKnownMarketplaces"]["agent-loadout"]["source"]["ref"] == "v0.3.0" and data["mine"] == 1
    steps = json.loads((tmp_path / root / "manifest.json").read_text())["steps"]
    assert steps[0]["undo"]["run"][3] == "checkout" and len(steps) > 1  # the settings copy joined it


def test_update_on_stable_without_a_release_changes_nothing_and_lists_no_failure(fake_home, fake_runner, tmp_path,
                                                                                 monkeypatch, capsys):
    _world(monkeypatch)
    monkeypatch.delenv(PULLED, raising=False)
    kit = _kit(tmp_path, monkeypatch)
    channels.set_channel("stable")
    _git(fake_runner, kit)  # v0.3.0 is seen for the first time now: not soaked
    monkeypatch.setattr(update, "_exec", lambda argv: pytest.fail("restarted without a move"))
    assert update.run(True, lambda q: "", argv=["--yes"]) == 0
    text = capsys.readouterr().out.split("What changed", 1)[1]
    assert not [l for l in text.splitlines() if l.strip().startswith("kit")]
    assert "detached" not in text and "fix:" not in text
    assert not {"checkout", "pull", "switch"} & set(_verbs(fake_runner, kit))
    assert channels._tags(channels._load_releases())["v0.3.0"]["sha"] == SHA3  # recorded for the soak


def test_update_on_stable_detached_on_a_release_is_not_a_failed_pull(fake_home, fake_runner, tmp_path, monkeypatch,
                                                                     capsys):
    _world(monkeypatch)
    monkeypatch.delenv(PULLED, raising=False)
    kit = _kit(tmp_path, monkeypatch)
    channels.set_channel("stable")
    _git(fake_runner, kit, tags={}, current="v0.3.0")
    monkeypatch.setattr(update, "_exec", lambda argv: pytest.fail("restarted without a move"))
    assert update.run(True, lambda q: "", argv=["--yes"]) == 0
    assert "detached HEAD" not in capsys.readouterr().out


def test_update_refusal_names_local_changes_and_keeps_the_pin(fake_home, fake_runner, tmp_path, monkeypatch, capsys):
    _world(monkeypatch)
    monkeypatch.delenv(PULLED, raising=False)
    kit = _kit(tmp_path, monkeypatch)
    channels.set_channel("stable")
    _git(fake_runner, kit, status=" M cli/loadout/x.py\n")
    _soaked("v0.3.0")
    monkeypatch.setattr(update, "_exec", lambda argv: pytest.fail("restarted after a refusal"))
    assert update.run(True, lambda q: "", argv=["--yes"]) == 0
    text = capsys.readouterr().out.split("What changed", 1)[1]
    line = next(l for l in text.splitlines() if "not moved to v0.3.0" in l)
    assert "cli/loadout/x.py" in line and f"fix: commit or remove them in {kit}, then run loadout update" in line
    assert "checkout" not in _verbs(fake_runner, kit)
    data = json.loads((fake_home / ".claude" / "settings.json").read_text())
    assert data["extraKnownMarketplaces"]["agent-loadout"]["source"]["ref"] == "v0.2.0"
    assert channels.get() == "stable"


def test_channel_without_argument_prints_state(fake_home, fake_runner, tmp_path, monkeypatch, capsys):
    kit = _kit(tmp_path, monkeypatch)
    _git(fake_runner, kit, current="v0.3.0")
    assert commands.channel(None) == 0
    assert capsys.readouterr().out.strip() == "dev, main"
    channels.set_channel("stable")
    assert commands.channel(None) == 0
    assert capsys.readouterr().out.strip() == "stable, v0.3.0"


def test_channel_stable_with_no_ready_release_stays_dev(fake_home, fake_runner, tmp_path, monkeypatch, capsys):
    kit = _kit(tmp_path, monkeypatch)
    _git(fake_runner, kit, current=None, branch="main")
    fake_runner.responses[_g(kit, "for-each-ref")] = runner.Result(0, f"{int(time.time()) - 3600}\n", "")
    monkeypatch.setattr(update, "_exec", lambda argv: pytest.fail("restarted without a move"))
    assert commands.channel("stable", yes=True) == 1
    assert "no release is ready yet; you stay on dev" in capsys.readouterr().out
    assert not (paths.state_dir() / "channel.json").exists()
    assert not {"checkout", "switch"} & set(_verbs(fake_runner, kit))


def test_channel_stable_falls_back_to_tagger_date_once(fake_home, fake_runner, tmp_path, monkeypatch, capsys):
    kit = _kit(tmp_path, monkeypatch)
    _git(fake_runner, kit, tags={"v0.3.0": SHA3, "v0.4.0": SHA4}, current=None, branch="main")
    now = int(time.time())
    fmt = "--format=%(taggerdate:unix)"
    fake_runner.responses[_g(kit, "for-each-ref", fmt, "refs/tags/v0.4.0")] = runner.Result(0, f"{now - 86400}\n", "")
    fake_runner.responses[_g(kit, "for-each-ref", fmt, "refs/tags/v0.3.0")] = runner.Result(0, f"{now - 5 * 86400}\n", "")
    seen = _restarts(monkeypatch)
    assert commands.channel("stable", yes=True) == 0
    assert [c for c in fake_runner.calls if c[3:4] == ["checkout"]] == [[*_g(kit), "checkout", "--detach", SHA3]]
    assert channels.get() == "stable"
    assert seen and seen[0][:2] == (["update", "--yes"], "channel:v0.3.0")
    assert "kit: dev (main) → v0.3.0" in capsys.readouterr().out
    # the tag date was a one-time trust: the soak for v0.4.0 still counts from this machine's first sight
    assert channels.eligible((0, 3, 0), time.time(), channels.Status()) is None


def test_channel_dev_from_stable_refuses_local_commits(fake_home, fake_runner, tmp_path, monkeypatch, capsys):
    kit = _kit(tmp_path, monkeypatch)
    channels.set_channel("stable")
    _git(fake_runner, kit, current="v0.3.0", log="abc1234 wip thing\n")
    monkeypatch.setattr(update, "_exec", lambda argv: pytest.fail("restarted after a refusal"))
    assert commands.channel("dev", yes=True) == 1
    assert "commit abc1234 wip thing" in capsys.readouterr().out
    assert channels.get() == "stable"
    assert not {"switch", "pull", "checkout"} & set(_verbs(fake_runner, kit))


def test_restore_after_channel_switch_puts_the_old_checkout_and_setting_back(fake_home, fake_runner, tmp_path,
                                                                             monkeypatch, capsys):
    _world(monkeypatch)
    kit = _kit(tmp_path, monkeypatch)
    channels.set_channel("stable")
    _git(fake_runner, kit, current="v0.3.0")
    settings = fake_home / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    before = b'{"mine": 1}\n'
    settings.write_bytes(before)
    channel_before = (paths.state_dir() / "channel.json").read_bytes()

    def restarted(argv):  # the new process, in this one
        assert os.environ[PULLED] == "channel:dev"
        fake_runner.responses[_g(kit, "describe")] = runner.Result(128, "", "no tag")  # now on main
        return update.run(True, lambda q: "", argv=argv[1:])
    monkeypatch.setattr(update, "_exec", restarted)
    assert commands.channel("dev", yes=True) == 0
    assert channels.get() == "dev"
    data = json.loads(settings.read_text())
    assert "ref" not in data["extraKnownMarketplaces"]["agent-loadout"]["source"]  # the pin is gone on dev
    text = capsys.readouterr().out.split("What changed", 1)[1]
    assert "channel: dev" in text
    roots = [b.path for b in backup.backups() if b.description.startswith("loadout channel dev")]
    assert len(roots) == 1 and f"loadout restore {roots[0]}" in text

    fake_runner.calls.clear()
    lines, ok, _ = backup.restore(roots[0])
    assert ok, lines
    assert [*_g(kit), "checkout", "--detach", SHA] in fake_runner.calls
    assert (paths.state_dir() / "channel.json").read_bytes() == channel_before
    assert settings.read_bytes() == before


def test_codex_kit_marketplace_is_refreshed_when_its_pin_changes(fake_home, fake_runner, tmp_path, monkeypatch):
    """stable -> dev: the record remembers the ref it refreshed at, so an unchanged head under another ref is not
    skipped (the re-add without @tag removes the pin)."""
    kit = _kit(tmp_path, monkeypatch)
    channels.set_channel("stable")
    _git(fake_runner, kit, current="v0.3.0")
    monkeypatch.setattr(codex, "marketplaces",
                        lambda: {"agent-loadout": {"source": f"https://github.com/{SLUG}.git"}})
    monkeypatch.setattr(codex, "remote_head", lambda url, ref: SHA)
    monkeypatch.setattr(codex, "_sha_less_plugins", lambda info: {})
    codex._remember(SLUG, "agent-loadout", SHA, ref=SHA)  # stable: the pin is the release commit (HEAD)
    routes, installed = {SLUG: ["loadout"]}, {"loadout@agent-loadout"}
    assert codex.unchanged_routes(routes, installed)[0] == {SLUG}
    channels.set_channel("dev")
    assert codex.unchanged_routes(routes, installed)[0] == set()


PINNED = ('[marketplaces.agent-loadout]\nsource_type = "git"\nsource = "https://github.com/jonasyr/agent-loadout.git"\n'
          'ref = "v0.3.0"\n')
UNPINNED = PINNED.replace('ref = "v0.3.0"\n', "")
REAL_APPLY_PLUGINS = codex.apply_plugins


def _codex_world(fake, monkeypatch, add_drops_ref=True):
    """codex as faked answers: `marketplace add` of the kit's source without @tag rewrites the table without its
    ref (add_drops_ref), or keeps it until the marketplace is removed and added again."""
    cfg = paths.codex_home() / "config.toml"
    removed = []

    def run(cmd, cwd=None, timeout=300, env=None):
        if cmd[:4] == ["codex", "plugin", "marketplace", "add"]:
            fake.calls.append(list(cmd))
            if cmd[4] == SLUG and (add_drops_ref or removed):
                cfg.write_text(UNPINNED)
            name = "agent-loadout" if cmd[4].startswith(SLUG) else cmd[4].split("/")[-1].split("@")[0]
            return runner.Result(0, json.dumps({"marketplaceName": name, "alreadyAdded": not removed}), "")
        if cmd[:4] == ["codex", "plugin", "marketplace", "remove"]:
            fake.calls.append(list(cmd))
            removed.append(cmd[4])
            return runner.Result(0, "", "")
        return fake(cmd, cwd, timeout, env)
    monkeypatch.setattr(runner, "run", run)
    monkeypatch.setattr(codex, "program", lambda: "codex")
    return cfg, removed


def _pinned_codex(fake, kit, monkeypatch, add_drops_ref=True):
    channels.set_channel("stable")
    _git(fake, kit, current="v0.3.0")
    cfg, removed = _codex_world(fake, monkeypatch, add_drops_ref)
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(PINNED)
    codex._remember(SLUG, "agent-loadout", SHA, ref=SHA)  # stable: the pin is the release commit (HEAD)
    return cfg, removed


@pytest.mark.parametrize("drops", [True, False])
def test_codex_pin_move_is_backed_up_and_verified(fake_home, fake_runner, tmp_path, monkeypatch, drops):
    kit = _kit(tmp_path, monkeypatch)
    cfg, removed = _pinned_codex(fake_runner, kit, monkeypatch, add_drops_ref=drops)
    channels.set_channel("dev")
    bk = backup.Backup(description="test")
    lines, _ = codex._install_routes({SLUG: ["loadout"]}, bk, True, lambda line: None, {"loadout@agent-loadout"})
    assert cfg.read_text() == UNPINNED, lines
    assert removed == ([] if drops else ["agent-loadout"])  # only a kept ref is removed and added again
    assert not [l for l in lines if "agent-loadout" in l and "fail" in l], lines
    msgs, ok, _ = backup.restore(bk.root)
    assert ok, msgs
    assert cfg.read_text() == PINNED


def test_codex_pin_still_wrong_after_readd_names_the_backup(fake_home, fake_runner, tmp_path, monkeypatch):
    kit = _kit(tmp_path, monkeypatch)
    _pinned_codex(fake_runner, kit, monkeypatch, add_drops_ref=False)
    channels.set_channel("dev")
    monkeypatch.setattr(codex, "_readd", lambda exe, src, market, bk: (True, ""))  # Codex keeps the ref anyway
    bk = backup.Backup(description="test")
    lines, _ = codex._install_routes({SLUG: ["loadout"]}, bk, True, lambda line: None, {"loadout@agent-loadout"})
    line = next(l for l in lines if "agent-loadout" in l and "v0.3.0" in l)
    assert str(bk.root) in line


def test_restore_after_switch_with_codex_on_brings_back_the_pinned_table(fake_home, fake_runner, tmp_path,
                                                                        monkeypatch, capsys):
    _world(monkeypatch, claude=False, codex_on=True)
    monkeypatch.setattr(codex, "apply_plugins", REAL_APPLY_PLUGINS)
    kit = _kit(tmp_path, monkeypatch)
    cfg, _ = _pinned_codex(fake_runner, kit, monkeypatch)

    def restarted(argv):
        fake_runner.responses[_g(kit, "describe")] = runner.Result(128, "", "no tag")
        return update.run(True, lambda q: "", argv=argv[1:])
    monkeypatch.setattr(update, "_exec", restarted)
    assert commands.channel("dev", yes=True) == 0
    assert 'ref = "v0.3.0"' not in cfg.read_text()
    [root] = [b.path for b in backup.backups() if b.description.startswith("loadout channel dev")]
    msgs, ok, _ = backup.restore(root)
    assert ok, msgs
    assert 'ref = "v0.3.0"' in cfg.read_text()


def test_restart_markers_show_only_valid_tags(fake_home):
    for marker, want in (("release:v0.3.0", "kit: moved to v0.3.0"),
                         ("release:evil\x1b[2J", "kit: moved to a new release"),
                         ("channel:dev", "channel: dev"), ("channel:v0.3.0", "channel: stable; kit: moved to v0.3.0"),
                         ("channel:bogus", "kit: pulled new commits"), ("1", "kit: pulled new commits"),
                         ("personal", "personal layer: pulled new commits")):
        summary = update.Summary()
        update._after_restart(summary, marker)
        text = "\n".join(summary.changed)
        assert want in text, (marker, text)
        assert "bogus" not in text and "evil" not in text
        assert marker == "channel:v0.3.0" or "stable" not in text


def test_reopen_takes_only_a_kit_move_backup(fake_home):
    other = backup.Backup(description="update: re-apply the setup")
    other.record_created(fake_home / "x", "x")
    assert backup.Backup.reopen(other.root) is None
    for description in ("loadout update: kit to v0.3.0", "loadout channel dev: kit to main"):
        bk = backup.Backup(description=description)
        bk.record_created(fake_home / "y", "y")
        assert backup.Backup.reopen(bk.root) is not None


def test_update_on_stable_follows_releases_with_no_auto_pull(fake_home, fake_runner, tmp_path, monkeypatch, capsys):
    """LOADOUT_NO_AUTO_PULL stops automatic pulls; update is the explicit step the release notice points to."""
    _world(monkeypatch)
    monkeypatch.delenv(PULLED, raising=False)
    monkeypatch.setenv("LOADOUT_NO_AUTO_PULL", "1")
    kit = _kit(tmp_path, monkeypatch)
    (paths.personal_root() / ".git").mkdir(parents=True)
    pulled = []
    monkeypatch.setattr(maintenance, "pull", lambda root: pulled.append(root))
    channels.set_channel("stable")
    _git(fake_runner, kit)
    _soaked("v0.3.0")
    seen = _restarts(monkeypatch)
    assert update.run(True, lambda q: "", argv=["--yes"]) == 0
    text = capsys.readouterr().out
    assert "Pull skipped (LOADOUT_NO_AUTO_PULL=1)" in " ".join(text.split()) and pulled == []  # the personal layer
    assert [c for c in fake_runner.calls if c[3:4] == ["checkout"]] == [[*_g(kit), "checkout", "--detach", SHA3]]
    assert len(seen) == 1 and seen[0][1] == "release:v0.3.0"


def test_channel_stable_off_a_release_points_to_update(fake_home, fake_runner, tmp_path, monkeypatch, capsys):
    kit = _kit(tmp_path, monkeypatch)
    channels.set_channel("stable")
    _git(fake_runner, kit, current="")
    assert update.channel("stable", True, lambda q: "") == 0
    assert ("channel: stable, but the kit is not on a release; run loadout update to move it to the newest one"
            in capsys.readouterr().out)


def test_channel_stable_on_a_release_says_already(fake_home, fake_runner, tmp_path, monkeypatch, capsys):
    kit = _kit(tmp_path, monkeypatch)
    channels.set_channel("stable")
    _git(fake_runner, kit)
    assert update.channel("stable", True, lambda q: "") == 0
    assert "channel: stable, v0.2.0 (already)" in capsys.readouterr().out
