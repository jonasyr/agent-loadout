"""Every plugin enabled for Claude Code goes into Codex through the same marketplace source."""
import json

from loadout import backup, codex, runner

SETTINGS = {
    "enabledPlugins": {"loadout@agent-loadout": True, "superpowers@claude-plugins-official": True,
                       "impeccable@impeccable": True, "hookify@claude-plugins-official": False,
                       "local-thing@my-dir": True},
    "extraKnownMarketplaces": {"agent-loadout": {"source": {"source": "github", "repo": "jonasyr/agent-loadout"}},
                               "impeccable": {"source": {"source": "github", "repo": "pbakaus/impeccable"}},
                               "my-dir": {"source": {"source": "directory", "path": "/x"}}},
}


def test_routes_follow_the_marketplace_source():
    routes, missing = codex.plugin_routes(SETTINGS)
    assert routes == {"jonasyr/agent-loadout": ["loadout"], codex.OFFICIAL: ["superpowers"],
                      "pbakaus/impeccable": ["impeccable"]}
    assert missing == ["local-thing@my-dir"]


def _fake(fake_runner, installed=()):
    def add(src, name, already=False):
        fake_runner.responses[("codex", "plugin", "marketplace", "add", src)] = runner.Result(
            0, json.dumps({"marketplaceName": name, "alreadyAdded": already}), "")
    add("jonasyr/agent-loadout", "agent-loadout")
    add(codex.OFFICIAL, "claude-plugins-official", already=True)
    add("pbakaus/impeccable", "impeccable")
    fake_runner.responses[("codex", "plugin", "list")] = runner.Result(
        0, json.dumps({"installed": [{"pluginId": p} for p in installed], "available": []}), "")


def test_installs_what_is_missing_and_records_undo(fake_home, fake_runner, monkeypatch):
    from loadout import settings_merge
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: SETTINGS)
    _fake(fake_runner, installed=["superpowers@claude-plugins-official"])
    bk = backup.Backup(description="t")
    lines = codex.apply_plugins(bk)
    adds = [c[3] for c in fake_runner.calls if c[:3] == ["codex", "plugin", "add"]]
    assert adds == ["loadout@agent-loadout", "impeccable@impeccable"]
    undo = [s["undo"]["run"] for s in bk.steps]
    assert ["codex", "plugin", "marketplace", "remove", "agent-loadout"] in undo
    assert ["codex", "plugin", "remove", "loadout@agent-loadout"] in undo
    assert ["codex", "plugin", "marketplace", "remove", "claude-plugins-official"] not in undo  # already there
    assert any("local-thing@my-dir" in l and "no Codex route" in l for l in lines)


def test_refresh_upgrades_marketplaces_and_reinstalls(fake_home, fake_runner, monkeypatch):
    from loadout import settings_merge
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: {"enabledPlugins": {"loadout@agent-loadout": True},
                                                                     "extraKnownMarketplaces": SETTINGS["extraKnownMarketplaces"]})
    _fake(fake_runner, installed=["loadout@agent-loadout"])
    fake_runner.responses[("codex", "plugin", "marketplace", "add", "jonasyr/agent-loadout")] = runner.Result(
        0, json.dumps({"marketplaceName": "agent-loadout", "alreadyAdded": True}), "")
    codex.apply_plugins(backup.Backup(description="t"), refresh=True)
    assert ["codex", "plugin", "marketplace", "upgrade", "agent-loadout"] in fake_runner.calls
    assert ["codex", "plugin", "add", "loadout@agent-loadout", "--json"] in fake_runner.calls


def test_failed_marketplace_is_reported_and_others_continue(fake_home, fake_runner, monkeypatch):
    from loadout import settings_merge
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: SETTINGS)
    _fake(fake_runner)
    fake_runner.responses[("codex", "plugin", "marketplace", "add", "pbakaus/impeccable")] = runner.Result(1, "", "network down")
    lines = codex.apply_plugins(backup.Backup(description="t"))
    assert any("pbakaus/impeccable" in l and "failed" in l for l in lines)
    assert ["codex", "plugin", "add", "loadout@agent-loadout", "--json"] in fake_runner.calls


def _frozen_settings():
    markets = json.loads(json.dumps(SETTINGS["extraKnownMarketplaces"]))
    markets["agent-loadout"]["autoUpdate"] = False
    return {"enabledPlugins": {"loadout@agent-loadout": True, "fresh@agent-loadout": True},
            "extraKnownMarketplaces": markets}


def test_the_automatic_refresh_skips_a_marketplace_set_to_no_auto_update(fake_home, fake_runner, monkeypatch):
    from loadout import settings_merge
    monkeypatch.setattr(settings_merge, "desired_settings", _frozen_settings)
    _fake(fake_runner, installed=["loadout@agent-loadout"])
    fake_runner.responses[("codex", "plugin", "marketplace", "add", "jonasyr/agent-loadout")] = runner.Result(
        0, json.dumps({"marketplaceName": "agent-loadout", "alreadyAdded": True}), "")
    codex.apply_plugins(backup.Backup(description="t"), refresh=True, auto=True)
    assert ["codex", "plugin", "marketplace", "upgrade", "agent-loadout"] not in fake_runner.calls
    assert ["codex", "plugin", "add", "loadout@agent-loadout", "--json"] not in fake_runner.calls
    assert ["codex", "plugin", "add", "fresh@agent-loadout", "--json"] in fake_runner.calls, "a first install still happens"


def test_an_explicit_update_still_updates_it(fake_home, fake_runner, monkeypatch):
    from loadout import settings_merge
    monkeypatch.setattr(settings_merge, "desired_settings", _frozen_settings)
    _fake(fake_runner, installed=["loadout@agent-loadout"])
    fake_runner.responses[("codex", "plugin", "marketplace", "add", "jonasyr/agent-loadout")] = runner.Result(
        0, json.dumps({"marketplaceName": "agent-loadout", "alreadyAdded": True}), "")
    codex.apply_plugins(backup.Backup(description="t"), refresh=True)
    assert ["codex", "plugin", "marketplace", "upgrade", "agent-loadout"] in fake_runner.calls


def test_apply_all_refresh_honours_auto_update(fake_home, fake_runner, monkeypatch):
    seen = []
    monkeypatch.setattr(codex, "apply_plugins", lambda bk, refresh=False, say=None, auto=False, skip_unchanged=False: seen.append((refresh, auto)) or [])
    monkeypatch.setattr(codex, "apply_instructions", lambda bk: "ok")
    monkeypatch.setattr(codex, "apply_config", lambda bk: [])
    monkeypatch.setattr(codex, "apply_skills", lambda bk: [])
    codex.apply_all(backup.Backup(description="t"), refresh=True)
    assert seen == [(True, True)]


# --- skip what did not change upstream (loadout update) ---

import pytest

URL = "https://github.com/jonasyr/agent-loadout.git"
ONE = {"enabledPlugins": {"loadout@agent-loadout": True},
       "extraKnownMarketplaces": {"agent-loadout": SETTINGS["extraKnownMarketplaces"]["agent-loadout"]}}


def _state(fake_home):
    from loadout import paths
    return paths.state_dir() / "codex-marketplaces.json"


def _record(fake_home, head="aaaaaaa1", plugins=None):
    f = _state(fake_home)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"jonasyr/agent-loadout": {"name": "agent-loadout", "url": URL, "head": head, "at": 1,
                                                       "plugins": plugins or {}}}))


def _listing(fake_runner, root, present=True):
    items = [{"name": "agent-loadout", "root": str(root), "marketplaceSource": {"sourceType": "git", "source": URL}}]
    fake_runner.responses[("codex", "plugin", "marketplace", "list")] = runner.Result(
        0, json.dumps({"marketplaces": items if present else []}), "")


def _heads(fake_runner, url, sha):
    fake_runner.responses[("git", "ls-remote", url)] = runner.Result(
        0, f"{sha}\tHEAD\n" if sha else "", "") if sha else runner.Result(128, "", "fatal")


def _setup(fake_home, fake_runner, monkeypatch, root, installed=("loadout@agent-loadout",), plugin_sources=None):
    from loadout import settings_merge
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: ONE)
    _fake(fake_runner, installed=installed)
    fake_runner.responses[("codex", "plugin", "marketplace", "add", "jonasyr/agent-loadout")] = runner.Result(
        0, json.dumps({"marketplaceName": "agent-loadout", "alreadyAdded": True}), "")
    _listing(fake_runner, root)
    (root / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    (root / ".claude-plugin" / "marketplace.json").write_text(json.dumps(
        {"plugins": [{"name": "loadout", "source": plugin_sources or "./plugins/loadout"}]}))


def _apply(fake_runner, **kw):
    codex.apply_plugins(backup.Backup(description="t"), refresh=True, skip_unchanged=True, **kw)
    return fake_runner.calls


def test_an_unchanged_marketplace_is_not_upgraded_or_re_added(fake_home, fake_runner, monkeypatch, tmp_path):
    _setup(fake_home, fake_runner, monkeypatch, tmp_path / "m")
    _record(fake_home, "aaaaaaa1")
    _heads(fake_runner, URL, "aaaaaaa1")
    calls = _apply(fake_runner)
    assert not [c for c in calls if c[:4] == ["codex", "plugin", "marketplace", "add"]]
    assert not [c for c in calls if c[:4] == ["codex", "plugin", "marketplace", "upgrade"]]
    assert not [c for c in calls if c[:3] == ["codex", "plugin", "add"]]
    env = fake_runner.envs[[c[:2] for c in calls].index(["git", "ls-remote"])]
    assert env["GIT_TERMINAL_PROMPT"] == "0" and env["GCM_INTERACTIVE"] == "never"


def test_a_changed_head_refreshes_and_records_the_new_head(fake_home, fake_runner, monkeypatch, tmp_path):
    _setup(fake_home, fake_runner, monkeypatch, tmp_path / "m")
    _record(fake_home, "aaaaaaa1")
    _heads(fake_runner, URL, "bbbbbbb2")
    calls = _apply(fake_runner)
    assert ["codex", "plugin", "marketplace", "upgrade", "agent-loadout"] in calls
    assert ["codex", "plugin", "add", "loadout@agent-loadout", "--json"] in calls
    assert json.loads(_state(fake_home).read_text())["jonasyr/agent-loadout"]["head"] == "bbbbbbb2"


def test_a_changed_plugin_source_is_re_added_alone(fake_home, fake_runner, monkeypatch, tmp_path):
    src = {"source": "url", "url": "https://github.com/obra/superpowers.git"}
    _setup(fake_home, fake_runner, monkeypatch, tmp_path / "m", plugin_sources=src)
    _record(fake_home, "aaaaaaa1", {"loadout@agent-loadout": {"url": src["url"], "ref": None, "head": "1111111a"}})
    _heads(fake_runner, URL, "aaaaaaa1")
    _heads(fake_runner, src["url"], "2222222b")
    calls = _apply(fake_runner)
    assert not [c for c in calls if c[:4] == ["codex", "plugin", "marketplace", "add"]]
    assert not [c for c in calls if c[:4] == ["codex", "plugin", "marketplace", "upgrade"]]
    assert ["codex", "plugin", "add", "loadout@agent-loadout", "--json"] in calls
    rec = json.loads(_state(fake_home).read_text())["jonasyr/agent-loadout"]
    assert rec["plugins"]["loadout@agent-loadout"]["head"] == "2222222b" and rec["head"] == "aaaaaaa1"


def test_a_plugin_source_with_a_sha_is_covered_by_the_marketplace_head(fake_home, fake_runner, monkeypatch, tmp_path):
    src = {"source": "url", "url": "https://github.com/obra/superpowers.git", "sha": "x"}
    _setup(fake_home, fake_runner, monkeypatch, tmp_path / "m", plugin_sources=src)
    _record(fake_home, "aaaaaaa1")
    _heads(fake_runner, URL, "aaaaaaa1")
    calls = _apply(fake_runner)
    assert not [c for c in calls if c[:3] == ["codex", "plugin", "add"]]
    assert not [c for c in calls if c[:2] == ["git", "ls-remote"] and c[2] != URL]


def test_a_missing_plugin_is_installed_even_when_the_head_did_not_move(fake_home, fake_runner, monkeypatch, tmp_path):
    _setup(fake_home, fake_runner, monkeypatch, tmp_path / "m", installed=())
    _record(fake_home, "aaaaaaa1")
    _heads(fake_runner, URL, "aaaaaaa1")
    assert ["codex", "plugin", "add", "loadout@agent-loadout", "--json"] in _apply(fake_runner)


@pytest.mark.parametrize("case", ["ls-remote fails", "no record", "not listed", "list unparsable"])
def test_whatever_cannot_be_compared_refreshes_as_today(fake_home, fake_runner, monkeypatch, tmp_path, case):
    _setup(fake_home, fake_runner, monkeypatch, tmp_path / "m")
    if case != "no record":
        _record(fake_home, "aaaaaaa1")
    _heads(fake_runner, URL, None if case == "ls-remote fails" else "aaaaaaa1")
    if case == "not listed":
        _listing(fake_runner, tmp_path / "m", present=False)
    if case == "list unparsable":
        fake_runner.responses[("codex", "plugin", "marketplace", "list")] = runner.Result(0, "garbage", "")
    calls = _apply(fake_runner)
    assert ["codex", "plugin", "marketplace", "upgrade", "agent-loadout"] in calls
    assert ["codex", "plugin", "add", "loadout@agent-loadout", "--json"] in calls


def test_ls_remote_failure_refreshes_as_today(fake_home, fake_runner, monkeypatch, tmp_path):
    _setup(fake_home, fake_runner, monkeypatch, tmp_path / "m")
    _record(fake_home, "aaaaaaa1")
    _heads(fake_runner, URL, None)
    calls = _apply(fake_runner)
    assert ["codex", "plugin", "add", "loadout@agent-loadout", "--json"] in calls
    assert json.loads(_state(fake_home).read_text())["jonasyr/agent-loadout"]["head"] == "aaaaaaa1"  # nothing to record


def test_without_skip_unchanged_nothing_is_compared(fake_home, fake_runner, monkeypatch, tmp_path):
    _setup(fake_home, fake_runner, monkeypatch, tmp_path / "m")
    _record(fake_home, "aaaaaaa1")
    _heads(fake_runner, URL, "aaaaaaa1")
    codex.apply_plugins(backup.Backup(description="t"), refresh=True)
    assert ["codex", "plugin", "add", "loadout@agent-loadout", "--json"] in fake_runner.calls


def test_the_record_is_written_only_after_success(fake_home, fake_runner, monkeypatch, tmp_path):
    _setup(fake_home, fake_runner, monkeypatch, tmp_path / "m", installed=())
    _heads(fake_runner, URL, "ccccccc3")
    fake_runner.responses[("codex", "plugin", "add")] = runner.Result(1, "", "boom")
    codex.apply_plugins(backup.Backup(description="t"), refresh=True, skip_unchanged=True)
    rec = json.loads(_state(fake_home).read_text()) if _state(fake_home).exists() else {}
    assert "loadout@agent-loadout" not in rec.get("jonasyr/agent-loadout", {}).get("plugins", {})
    fake_runner.responses[("codex", "plugin", "marketplace", "add", "jonasyr/agent-loadout")] = runner.Result(1, "", "net")
    _state(fake_home).unlink(missing_ok=True)
    codex.apply_plugins(backup.Backup(description="t"), refresh=True, skip_unchanged=True)
    assert not _state(fake_home).exists()


def test_apply_parts_passes_skip_unchanged_on(fake_home, fake_runner, monkeypatch):
    seen = {}
    monkeypatch.setattr(codex, "apply_plugins", lambda bk, **kw: seen.update(kw) or [])
    codex.apply_parts(backup.Backup(description="t"), refresh=True, auto=False, keep=False, skip_unchanged=True)
    assert seen["skip_unchanged"] is True


@pytest.mark.parametrize("source,skipped", [("https://GitHub.com/jonasyr/agent-loadout", True),
                                            ("https://github.com/jonasyr/agent-loadout.git/", True),
                                            ("https://github.com/someone/other-repo.git", False),
                                            (None, False)])
def test_a_marketplace_listed_from_another_source_is_refreshed(fake_home, fake_runner, monkeypatch, tmp_path, source,
                                                                skipped):
    _setup(fake_home, fake_runner, monkeypatch, tmp_path / "m")
    item = {"name": "agent-loadout", "root": str(tmp_path / "m")}
    if source is not None:
        item["marketplaceSource"] = {"sourceType": "git", "source": source}
    fake_runner.responses[("codex", "plugin", "marketplace", "list")] = runner.Result(
        0, json.dumps({"marketplaces": [item]}), "")
    _record(fake_home, "aaaaaaa1")
    _heads(fake_runner, URL, "aaaaaaa1")
    calls = _apply(fake_runner)
    refreshed = ["codex", "plugin", "marketplace", "upgrade", "agent-loadout"] in calls
    assert refreshed is not skipped


def test_update_runs_the_codex_commands_the_plan_showed_when_ls_remote_flips(fake_home, fake_runner, monkeypatch,
                                                                            tmp_path, capsys):
    from loadout import bootstrap, check, maintenance, targets, update
    _setup(fake_home, fake_runner, monkeypatch, tmp_path / "m")
    _record(fake_home, "aaaaaaa1")
    targets.set_agents({"claude": False, "codex": True})
    monkeypatch.setattr(codex, "unavailable", lambda *a, **k: None)
    monkeypatch.setattr(maintenance, "find_outdated", lambda: [])
    monkeypatch.setattr(bootstrap, "missing_tools", lambda *a, **k: [])
    monkeypatch.setattr(check, "run_checks", lambda *a, **k: [])
    shown = []
    real_build = update.build_plan

    def build(*a, **k):
        plan = real_build(*a, **k)
        shown.extend(c for i in plan if i.kind == "codex-plugins" for _, cmds in i.groups for c in cmds)
        fake_runner.responses[("git", "ls-remote", URL)] = runner.Result(128, "", "fatal: offline")  # flips after
        return plan
    monkeypatch.setattr(update, "build_plan", build)
    _heads(fake_runner, URL, "aaaaaaa1")  # the plan sees the head unchanged: skip
    update.run(True, lambda q: "", argv=["--yes"])
    assert shown == []  # the plan skipped the marketplace and its plugin
    ran = [c for c in fake_runner.calls if c[:2] == ["codex", "plugin"] and c[2:3] in (["add"], ["marketplace"])
           and "list" not in c]
    assert ran == shown
