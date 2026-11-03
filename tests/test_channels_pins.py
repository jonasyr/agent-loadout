import json

import pytest

from loadout import backup, bootstrap, channels, codex, paths, runner, settings_merge, targets

TAG = "v0.3.0"
SLUG = "jonasyr/agent-loadout"
SHA = "d" * 40  # the commit the kit checkout (and so the release) is on


def _kit(tmp_path, monkeypatch):
    kit = tmp_path / "kit"
    (kit / ".git").mkdir(parents=True)
    for name in ("settings.base.json", "catalog.json"):
        (kit / name).write_bytes((paths.kit_root() / name).read_bytes())
    monkeypatch.setenv("LOADOUT_ROOT", str(kit))
    return kit


def _stable(fake_runner, kit, tag=TAG):
    channels.set_channel("stable")
    fake_runner.responses[("git", "-C", str(kit), "describe")] = runner.Result(0, tag + "\n", "")
    fake_runner.responses[("git", "-C", str(kit), "rev-parse", "HEAD")] = runner.Result(0, SHA + "\n", "")
    fake_runner.responses[("git", "-C", str(kit), "remote")] = runner.Result(0, f"https://github.com/{SLUG}.git\n", "")


def _added(name="agent-loadout"):
    return runner.Result(0, json.dumps({"marketplaceName": name, "alreadyAdded": False}), "")


def test_stable_settings_pin_the_kit_marketplace(fake_home, fake_runner, tmp_path, monkeypatch):
    _stable(fake_runner, _kit(tmp_path, monkeypatch))
    markets = settings_merge.desired_settings()["extraKnownMarketplaces"]
    assert markets["agent-loadout"]["source"]["ref"] == TAG
    assert markets["agent-loadout"]["source"]["repo"] == SLUG
    assert [n for n, m in markets.items() if "ref" in m["source"]] == ["agent-loadout"]


def test_dev_settings_have_no_ref(fake_home, fake_runner, tmp_path, monkeypatch):
    _kit(tmp_path, monkeypatch)
    channels.set_channel("dev")
    markets = settings_merge.desired_settings()["extraKnownMarketplaces"]
    assert not any("ref" in m["source"] for m in markets.values())
    assert not any(c[0] == "git" for c in fake_runner.calls)


def test_claude_marketplace_add_passes_the_tag(fake_home, fake_runner, tmp_path, monkeypatch):
    _stable(fake_runner, _kit(tmp_path, monkeypatch))
    fake_runner.responses[("claude", "plugin", "marketplace", "list")] = runner.Result(0, "[]", "")
    _, markets, _ = bootstrap.plugins_plan()
    assert ("agent-loadout", f"{SLUG}#{TAG}") in markets
    assert ("claude-plugins-official", "anthropics/claude-plugins-official") in markets
    bootstrap.setup_plugins(planned=(tuple(markets), ()))
    adds = [c for c in fake_runner.calls if c[:4] == ["claude", "plugin", "marketplace", "add"]]
    assert ["claude", "plugin", "marketplace", "add", f"{SLUG}#{TAG}"] in adds
    assert ["claude", "plugin", "marketplace", "add", "anthropics/claude-plugins-official"] in adds


def test_origins_unchanged_on_dev_and_for_other_repos(fake_home, fake_runner, tmp_path, monkeypatch):
    kit = _kit(tmp_path, monkeypatch)
    channels.set_channel("dev")
    assert channels.claude_origin(SLUG) == SLUG and channels.codex_source(SLUG) == SLUG
    _stable(fake_runner, kit)
    assert channels.claude_origin(SLUG) == f"{SLUG}#{TAG}"
    assert channels.codex_source(SLUG) == f"{SLUG}@{SHA}"
    assert channels.claude_origin("other/repo") == "other/repo"
    assert channels.codex_source("other/repo") == "other/repo"
    fake_runner.responses[("git", "-C", str(kit), "describe")] = runner.Result(1, "", "no tag")
    assert channels.pin() is None and channels.claude_origin(SLUG) == SLUG


def test_undo_command_with_a_tag_is_allowed():
    assert backup._allowed_run(["claude", "plugin", "marketplace", "add", f"{SLUG}#{TAG}"])


def test_codex_add_pins_the_release_sha_and_never_asks_the_remote(fake_home, fake_runner, tmp_path, monkeypatch):
    """A tag the remote force-moves must not reach Codex: the pin is the commit, which Codex never re-resolves."""
    _stable(fake_runner, _kit(tmp_path, monkeypatch))
    channels._record_current(TAG, SHA)
    refs = []
    monkeypatch.setattr(codex, "remote_head", lambda url, ref: refs.append((url, ref)) or "a" * 40)
    fake_runner.responses[("codex", "--version")] = runner.Result(0, "codex-cli 0.162.1\n", "")
    fake_runner.responses[("codex", "plugin", "marketplace", "add")] = _added()
    codex._install_routes({SLUG: [], "o/other": []}, None, refresh=False, say=lambda line: None, listed=None)
    adds = [c for c in fake_runner.calls if c[1:4] == ["plugin", "marketplace", "add"]]
    assert [c[4] for c in adds] == [f"{SLUG}@{SHA}", "o/other"]
    assert refs == [("https://github.com/o/other.git", None)]  # the kit's pin is a commit: no ls-remote
    entry = json.loads((paths.state_dir() / "codex-marketplaces.json").read_text())[SLUG]
    assert entry["ref"] == SHA and entry["head"] == SHA


def test_codex_pin_skip_compares_the_sha(fake_home, fake_runner, tmp_path, monkeypatch):
    _stable(fake_runner, _kit(tmp_path, monkeypatch))
    channels._record_current(TAG, SHA)
    monkeypatch.setattr(codex, "remote_head", lambda url, ref: pytest.fail(f"ls-remote {url} {ref}"))
    (paths.state_dir()).mkdir(parents=True, exist_ok=True)
    (paths.state_dir() / "codex-marketplaces.json").write_text(json.dumps(
        {SLUG: {"name": "agent-loadout", "head": SHA, "ref": SHA}}))
    monkeypatch.setattr(codex, "marketplaces", lambda: {"agent-loadout": {"root": None, "source": SLUG}})
    monkeypatch.setattr(codex, "_same_source", lambda listed, url: True)
    monkeypatch.setattr(codex, "_sha_less_plugins", lambda listed: {})
    skip_m, _ = codex.unchanged_routes({SLUG: []}, installed=set())
    assert skip_m == {SLUG}
    monkeypatch.setattr(codex, "_market_table", lambda market: {"ref": SHA})
    assert codex._table_blockers("agent-loadout", channels.codex_source(SLUG)) == []


def test_stable_settings_turn_off_auto_update_of_the_kit_marketplace(fake_home, fake_runner, tmp_path, monkeypatch):
    """Claude Code's autoUpdate follows the ref's latest commit: a moved tag would install unverified hooks."""
    _stable(fake_runner, _kit(tmp_path, monkeypatch))
    markets = settings_merge.desired_settings()["extraKnownMarketplaces"]
    assert markets["agent-loadout"]["source"]["ref"] == TAG and markets["agent-loadout"]["autoUpdate"] is False
    assert markets["claude-plugins-official"]["autoUpdate"] is True


def test_dev_settings_keep_auto_update(fake_home, fake_runner, tmp_path, monkeypatch):
    _kit(tmp_path, monkeypatch)
    channels.set_channel("dev")
    kit = settings_merge.desired_settings()["extraKnownMarketplaces"]["agent-loadout"]
    assert kit["autoUpdate"] is True and "ref" not in kit["source"]


def test_pin_keeps_a_moved_current_tag(fake_home, fake_runner, tmp_path, monkeypatch):
    _stable(fake_runner, _kit(tmp_path, monkeypatch))
    channels.record_seen({TAG: "e" * 40}, 1.0)
    channels.record_seen({TAG: SHA}, 2.0)  # the remote moved the tag
    assert channels.moved_tags() == [TAG]
    assert channels.pin() == TAG  # never None: that would drop the pin and follow main
    assert channels.claude_origin(SLUG) == f"{SLUG}#{TAG}"


def test_a_moved_current_tag_stops_the_claude_kit_marketplace_refresh(fake_home, fake_runner, tmp_path, monkeypatch,
                                                                      capsys):
    from loadout import update
    _stable(fake_runner, _kit(tmp_path, monkeypatch))
    channels.record_seen({TAG: "e" * 40}, 1.0)
    channels.record_seen({TAG: SHA}, 2.0)
    pid = "loadout@agent-loadout"
    item = update.PlanItem(n=1, kind="claude-plugins-refresh", label="", commands=[], ids=(pid, "x@claude-plugins-official"))
    update._refresh_claude_plugins(item, update.Summary())
    calls = [c for c in fake_runner.calls if c[0] == "claude"]
    assert ["claude", "plugin", "marketplace", "update"] not in calls
    assert not any(c[:4] == ["claude", "plugin", "marketplace", "update"] and "agent-loadout" in c for c in calls)
    assert ["claude", "plugin", "marketplace", "update", "claude-plugins-official"] in calls
    assert not any(pid in c for c in calls)
    assert "changed after it was released" in capsys.readouterr().out


def test_after_a_verified_move_the_claude_refresh_runs_as_before(fake_home, fake_runner, tmp_path, monkeypatch):
    from loadout import update
    _stable(fake_runner, _kit(tmp_path, monkeypatch))
    channels.record_seen({TAG: SHA}, 1.0)
    item = update.PlanItem(n=1, kind="claude-plugins-refresh", label="", commands=[], ids=("loadout@agent-loadout",))
    update._refresh_claude_plugins(item, update.Summary())
    assert ["claude", "plugin", "marketplace", "update"] in fake_runner.calls
    assert ["claude", "plugin", "update", "loadout@agent-loadout", "--scope", "user"] in fake_runner.calls


def test_codex_off_touches_no_codex_config(fake_home, fake_runner, tmp_path, monkeypatch):
    _stable(fake_runner, _kit(tmp_path, monkeypatch))
    targets.set_agents({"claude": True})
    fake_runner.responses[("claude", "plugin", "marketplace", "list")] = runner.Result(0, "[]", "")
    settings_merge.desired_settings()
    bootstrap.plugins_plan()
    assert not any(c[0] == "codex" for c in fake_runner.calls)
    assert not paths.codex_home().exists()


def test_claude_off_runs_no_claude_marketplace_add(fake_home, fake_runner, tmp_path, monkeypatch):
    _stable(fake_runner, _kit(tmp_path, monkeypatch))
    targets.set_agents({"codex": True})
    monkeypatch.setattr(codex, "remote_head", lambda url, ref: "a" * 40)
    fake_runner.responses[("codex", "--version")] = runner.Result(0, "codex-cli 0.162.1\n", "")
    fake_runner.responses[("codex", "plugin", "marketplace", "add")] = _added()
    codex._install_routes({SLUG: []}, None, refresh=False, say=lambda line: None, listed=None)
    assert not any(c[0] == "claude" for c in fake_runner.calls)
    assert not paths.claude_home().exists()


# --- a release tag the remote moved: no kit marketplace add by its name ---

def _moved(fake_runner, kit):
    _stable(fake_runner, kit)
    channels.record_seen({TAG: "e" * 40}, 1.0)
    channels.record_seen({TAG: SHA}, 2.0)  # the remote moved the tag


def test_bootstrap_adds_no_kit_marketplace_while_its_tag_is_moved(fake_home, fake_runner, tmp_path, monkeypatch):
    _moved(fake_runner, _kit(tmp_path, monkeypatch))
    fake_runner.responses[("claude", "plugin", "marketplace", "list")] = runner.Result(0, "[]", "")
    lines, markets, _ = bootstrap.plugins_plan()
    assert "agent-loadout" not in [n for n, _ in markets]
    assert ("claude-plugins-official", "anthropics/claude-plugins-official") in markets
    assert any("v0.3.0 was changed after it was released" in line for line in lines)
    out = bootstrap.setup_plugins(planned=((("agent-loadout", SLUG),), ()))  # a plan from before: held too
    assert not [c for c in fake_runner.calls if c[:4] == ["claude", "plugin", "marketplace", "add"]]
    assert any("changed after it was released" in line for line in out)
    assert settings_merge.desired_settings()["extraKnownMarketplaces"]["agent-loadout"]["source"]["ref"] == TAG


def test_profile_adds_no_kit_marketplace_while_its_tag_is_moved(fake_home, fake_runner, tmp_path, monkeypatch):
    from loadout import profiles
    _moved(fake_runner, _kit(tmp_path, monkeypatch))
    fake_runner.responses[("claude", "plugin", "marketplace", "list")] = runner.Result(0, "[]", "")
    market = {"source": {"source": "github", "repo": SLUG}}
    prof = profiles.Profile(name="p", description="", settings={"extraKnownMarketplaces": {"agent-loadout": market}},
                            install=["loadout@agent-loadout"])
    cmds, bad = profiles.marketplace_adds(prof)
    assert cmds == [] and any("v0.3.0 was changed after it was released" in line for line in bad)


def test_codex_adds_no_kit_marketplace_by_a_moved_tag_name(fake_home, fake_runner, tmp_path, monkeypatch):
    kit = _kit(tmp_path, monkeypatch)
    _moved(fake_runner, kit)
    fake_runner.responses[("git", "-C", str(kit), "rev-parse", "HEAD")] = runner.Result(128, "", "broken")
    assert channels.codex_source(SLUG) == f"{SLUG}@{TAG}"  # git cannot name HEAD: the tag name is the fallback
    monkeypatch.setattr(codex, "remote_head", lambda url, ref: "a" * 40)
    fake_runner.responses[("codex", "--version")] = runner.Result(0, "codex-cli 0.162.1\n", "")
    fake_runner.responses[("codex", "plugin", "marketplace", "add")] = _added()
    lines, _ = codex._install_routes({SLUG: []}, None, refresh=False, say=lambda line: None, listed=None)
    assert not [c for c in fake_runner.calls if c[1:4] == ["plugin", "marketplace", "add"]]
    assert any("changed after it was released" in line for line in lines)


def test_codex_sha_pin_is_added_even_with_a_moved_tag(fake_home, fake_runner, tmp_path, monkeypatch):
    _moved(fake_runner, _kit(tmp_path, monkeypatch))
    monkeypatch.setattr(codex, "remote_head", lambda url, ref: "a" * 40)
    fake_runner.responses[("codex", "--version")] = runner.Result(0, "codex-cli 0.162.1\n", "")
    fake_runner.responses[("codex", "plugin", "marketplace", "add")] = _added()
    codex._install_routes({SLUG: []}, None, refresh=False, say=lambda line: None, listed=None)
    adds = [c for c in fake_runner.calls if c[1:4] == ["plugin", "marketplace", "add"]]
    assert [c[4] for c in adds] == [f"{SLUG}@{SHA}"]
