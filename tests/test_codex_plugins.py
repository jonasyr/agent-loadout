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


@pytest.mark.parametrize("url", ["git@github.com:obra/superpowers.git", "ssh://git@github.com/obra/superpowers.git",
                                 "file:///home/x/superpowers", "/home/x/superpowers"])
def test_an_external_source_that_cannot_be_compared_is_re_added(fake_home, fake_runner, monkeypatch, tmp_path, url):
    src = {"source": "url", "url": url}
    _setup(fake_home, fake_runner, monkeypatch, tmp_path / "m", plugin_sources=src)
    _record(fake_home, "aaaaaaa1")
    _heads(fake_runner, URL, "aaaaaaa1")
    calls = _apply(fake_runner)
    assert not [c for c in calls if c[:4] == ["codex", "plugin", "marketplace", "upgrade"]]  # the marketplace did not move
    assert ["codex", "plugin", "add", "loadout@agent-loadout", "--json"] in calls


def test_a_planned_plugin_skip_holds_when_the_plugin_list_fails(fake_home, fake_runner, monkeypatch, tmp_path):
    _setup(fake_home, fake_runner, monkeypatch, tmp_path / "m")
    _record(fake_home, "aaaaaaa1")
    fake_runner.responses[("codex", "plugin", "list")] = runner.Result(1, "", "codex: busy")  # the second look fails
    codex.apply_plugins(backup.Backup(description="t"), refresh=True, skip_unchanged=True,
                        skips=(frozenset({"jonasyr/agent-loadout"}), frozenset({"loadout@agent-loadout"})))
    assert not [c for c in fake_runner.calls if c[:3] == ["codex", "plugin", "add"]]
    assert not [c for c in fake_runner.calls if c[:4] == ["codex", "plugin", "marketplace", "add"]]


@pytest.mark.parametrize("raw", [b'{"plugins": [', b'\xff\xfe{"plugins": []}'], ids=["malformed", "not-utf8"])
def test_an_unreadable_cached_marketplace_json_refreshes_the_route(fake_home, fake_runner, monkeypatch, tmp_path, raw):
    _setup(fake_home, fake_runner, monkeypatch, tmp_path / "m")
    (tmp_path / "m" / ".claude-plugin" / "marketplace.json").write_bytes(raw)
    _record(fake_home, "aaaaaaa1")
    _heads(fake_runner, URL, "aaaaaaa1")
    skip_m, skip_p = codex.unchanged_routes({"jonasyr/agent-loadout": ["loadout"]})
    assert skip_m == set() and skip_p == set()
    calls = _apply(fake_runner)
    assert ["codex", "plugin", "marketplace", "upgrade", "agent-loadout"] in calls


def test_the_codex_plugin_item_runs_alone_without_item_1(fake_home, fake_runner, monkeypatch, tmp_path, capsys):
    from loadout import bootstrap, check, maintenance, paths, targets, ui, update
    _setup(fake_home, fake_runner, monkeypatch, tmp_path / "m")
    _record(fake_home, "aaaaaaa1")
    _heads(fake_runner, URL, "bbbbbbb2")  # upstream moved: the plan refreshes it
    targets.set_agents({"claude": False, "codex": True})
    monkeypatch.setattr(codex, "unavailable", lambda *a, **k: None)
    monkeypatch.setattr(maintenance, "find_outdated", lambda: [])
    monkeypatch.setattr(bootstrap, "missing_tools", lambda *a, **k: [])
    monkeypatch.setattr(check, "run_checks", lambda *a, **k: [])
    monkeypatch.setattr(ui, "is_interactive", lambda: True)
    shown = []
    real_build = update.build_plan

    def build(*a, **k):
        plan = real_build(*a, **k)
        shown.extend(c for i in plan if i.kind == "codex-plugins" for _, cmds in i.groups for c in cmds)
        return plan
    monkeypatch.setattr(update, "build_plan", build)
    update.run(False, lambda q: "1", argv=[])  # leave out item 1 only
    assert shown
    ran = [c for c in fake_runner.calls if c[:2] == ["codex", "plugin"] and c[2:3] in (["add"], ["marketplace"])
           and "list" not in c]
    assert ran == shown
    assert not (paths.codex_home() / "AGENTS.md").exists() and not (paths.codex_home() / "config.toml").exists()
    text = capsys.readouterr().out
    assert "rules, plugins, MCP servers and skills set up" not in text
    assert "plugins refreshed; rules, config, hooks and skills left as they are (item 1 was left out)" in text


# --- a large clone is honest: a longer timeout, a warning, and a row for what Codex lacks

def _timeouts(fake_runner, prefix):
    return [t for c, t in zip(fake_runner.calls, fake_runner.timeouts) if c[:len(prefix)] == list(prefix)]


def test_marketplace_add_and_upgrade_get_1800_seconds(fake_home, fake_runner, monkeypatch):
    from loadout import settings_merge
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: SETTINGS)
    _fake(fake_runner, installed=["superpowers@claude-plugins-official"])
    codex.apply_plugins(backup.Backup(description="t"), refresh=True)
    assert set(_timeouts(fake_runner, ("codex", "plugin", "marketplace", "add"))) == {1800}
    assert set(_timeouts(fake_runner, ("codex", "plugin", "marketplace", "upgrade"))) == {1800}
    assert set(_timeouts(fake_runner, ("codex", "plugin", "add"))) == {600}


def test_progress_line_warns_about_large_clones(fake_home, fake_runner, monkeypatch):
    from loadout import settings_merge
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: {
        "enabledPlugins": {"impeccable@impeccable": True}, "extraKnownMarketplaces": SETTINGS["extraKnownMarketplaces"]})
    _fake(fake_runner)
    said = []
    codex.apply_plugins(backup.Backup(description="t"), say=said.append)
    assert ("  adding marketplace pbakaus/impeccable, a git clone (1 of 2; large repositories can take several "
            "minutes)…") in said


IMPECCABLE = {"enabledPlugins": {"impeccable@impeccable": True},
              "extraKnownMarketplaces": {"impeccable": {"source": {"source": "github", "repo": "pbakaus/impeccable"}}}}


def _codex_has(fake_runner, markets=(), installed=()):
    items = [{"name": name, "root": "/nowhere", "marketplaceSource": {"sourceType": "git", "source": src}}
             for name, src in markets]
    fake_runner.responses[("codex", "plugin", "marketplace", "list")] = runner.Result(
        0, json.dumps({"marketplaces": items}), "")
    fake_runner.responses[("codex", "plugin", "list")] = runner.Result(
        0, json.dumps({"installed": [{"pluginId": p} for p in installed], "available": []}), "")


def _checks_on(monkeypatch, settings):
    from loadout import settings_merge
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: settings)
    monkeypatch.setattr(codex, "enabled", lambda: True)
    monkeypatch.setattr(codex, "unavailable", lambda *a, **k: None)
    monkeypatch.setattr(codex, "hooks_status", lambda remember=False: "trusted")
    monkeypatch.setattr(codex, "logins_needed", lambda: [])
    monkeypatch.setattr(codex, "logins_optional", lambda: [])
    monkeypatch.setattr(codex, "drift", lambda: [])


def test_check_names_what_codex_lacks(fake_home, fake_runner, monkeypatch):
    _checks_on(monkeypatch, IMPECCABLE)
    _codex_has(fake_runner)
    (row,) = [r for r in codex.checks() if r.name == "Codex plugins missing"]
    assert not row.ok and row.severity == "warn"
    assert "pbakaus/impeccable" in row.detail and "impeccable" in row.detail.replace("pbakaus/impeccable", "")
    assert row.fix == "loadout update (retries them)"
    assert codex.missing_routes() == (["pbakaus/impeccable"], ["impeccable (from pbakaus/impeccable)"])


def test_same_name_from_another_market_is_still_missing(fake_home, fake_runner, monkeypatch):
    _checks_on(monkeypatch, {"enabledPlugins": {"superpowers@claude-plugins-official": True}})
    _codex_has(fake_runner, markets=[("openai-curated-remote", "https://github.com/openai/plugins.git"),
                                     ("claude-plugins-official", f"https://github.com/{codex.OFFICIAL}.git")],
               installed=["superpowers@openai-curated-remote"])
    assert codex.missing_routes() == ([], ["superpowers@claude-plugins-official"])
    (row,) = [r for r in codex.checks() if r.name == "Codex plugins missing"]
    assert "superpowers@claude-plugins-official" in row.detail


def test_open_steps_names_them_once(fake_home, fake_runner, monkeypatch):
    _checks_on(monkeypatch, IMPECCABLE)
    _codex_has(fake_runner)
    steps = [s for s in codex.open_steps() if "pbakaus/impeccable" in s]
    assert len(steps) == 1 and "loadout update" in steps[0] and "impeccable (from" in steps[0]
    assert sum(c[:4] == ["codex", "plugin", "marketplace", "list"] for c in fake_runner.calls) == 1
    assert sum(c[:3] == ["codex", "plugin", "list"] for c in fake_runner.calls) == 1


def test_nothing_missing_no_row_no_step(fake_home, fake_runner, monkeypatch):
    _checks_on(monkeypatch, IMPECCABLE)
    _codex_has(fake_runner, markets=[("impeccable", "https://github.com/pbakaus/impeccable.git")],
               installed=["impeccable@impeccable"])
    assert codex.missing_routes() == ([], [])
    assert not [r for r in codex.checks() if r.name == "Codex plugins missing"]
    assert not [s for s in codex.open_steps() if "loadout update" in s]


def test_without_the_cli_or_a_listing_nothing_is_reported(fake_home, fake_runner, monkeypatch):
    _checks_on(monkeypatch, IMPECCABLE)
    assert codex.missing_routes() == ([], [])  # the default fake prints no JSON: the listing fails
    _codex_has(fake_runner)
    fake_runner.missing.add("codex")
    assert codex.missing_routes() == ([], [])


def test_loadout_plugin_not_reported_twice(fake_home, fake_runner, monkeypatch):
    _checks_on(monkeypatch, {"enabledPlugins": {"loadout@agent-loadout": True},
                             "extraKnownMarketplaces": SETTINGS["extraKnownMarketplaces"]})
    _codex_has(fake_runner)
    assert codex.missing_routes() == ([], [])
    rows = {r.name: r for r in codex.checks()}
    assert not rows["Codex plugin"].ok and "Codex plugins missing" not in rows


# --- plain words: the summary names only what was set up (live-tour fixes, spec fix 11)

def test_codex_summary_names_skills_only_when_linked(fake_runner):
    from loadout import apply
    assert apply._codex_summary(["instructions written to ~/.codex/AGENTS.md"]) == "rules, plugins and MCP servers set up"
    assert apply._codex_summary(["linked ~/.codex/skills/x"]) == "rules, plugins, MCP servers and skills set up"
    assert apply._codex_summary(["copied ~/.codex/skills/x"]) == "rules, plugins, MCP servers and skills set up"
    assert apply._codex_summary([], plugins=False) == "rules and MCP servers set up"
    assert apply._codex_summary(["linked x"], plugins=False) == "rules, MCP servers and skills set up"


def test_codex_summary_extension_mode_names_skills_only_when_linked(codex_ext):
    from loadout import apply
    assert apply._codex_summary(["linked x"]) == (
        "rules, plugins, MCP servers and skills set up for VS Code's Codex extension")
    assert apply._codex_summary([]) == "rules, plugins and MCP servers set up for VS Code's Codex extension"


def _upgrade_fails(fake_runner, monkeypatch, *results):
    """agent-loadout is installed and already added; its `marketplace upgrade` answers with results in turn."""
    from loadout import settings_merge
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: {
        "enabledPlugins": {"loadout@agent-loadout": True, "fresh@agent-loadout": True},
        "extraKnownMarketplaces": SETTINGS["extraKnownMarketplaces"]})
    monkeypatch.setattr(codex, "UPGRADE_RETRY_WAIT", 0)
    _fake(fake_runner, installed=["loadout@agent-loadout"])
    fake_runner.responses[("codex", "plugin", "marketplace", "add", "jonasyr/agent-loadout")] = runner.Result(
        0, json.dumps({"marketplaceName": "agent-loadout", "alreadyAdded": True}), "")
    answers = list(results)
    inner = runner.run

    def run(cmd, **kw):
        if cmd[:4] == ["codex", "plugin", "marketplace", "upgrade"] and answers:
            inner(cmd, **kw)  # recorded in fake_runner.calls
            return answers.pop(0)
        return inner(cmd, **kw)
    monkeypatch.setattr(runner, "run", run)


def _upgrades(fake_runner):
    return [c for c in fake_runner.calls if c[:4] == ["codex", "plugin", "marketplace", "upgrade"]]


def test_a_failed_marketplace_upgrade_is_a_problem_line_with_codex_reason(fake_home, fake_runner, monkeypatch):
    err = runner.Result(1, "", "Failed to upgrade marketplace `agent-loadout`: git ls-remote failed")
    _upgrade_fails(fake_runner, monkeypatch, err, err)
    lines = codex.apply_plugins(backup.Backup(description="t"), refresh=True)
    problem = [l for l in lines if "agent-loadout" in l and "failed to upgrade" in l]
    assert problem and "git ls-remote failed" in problem[0]
    from loadout import apply
    assert apply.refused(lines), "update lists it among the problems"


def test_a_failed_upgrade_does_not_reinstall_from_the_old_snapshot(fake_home, fake_runner, monkeypatch):
    err = runner.Result(1, "", "boom")
    _upgrade_fails(fake_runner, monkeypatch, err, err)
    codex.apply_plugins(backup.Backup(description="t"), refresh=True)
    adds = [c[3] for c in fake_runner.calls if c[:3] == ["codex", "plugin", "add"]]
    assert "loadout@agent-loadout" not in adds, "re-adding would install the stale copy again"
    assert "fresh@agent-loadout" in adds, "a plugin that is missing is still installed"


def test_a_failed_upgrade_is_tried_once_more(fake_home, fake_runner, monkeypatch):
    _upgrade_fails(fake_runner, monkeypatch, runner.Result(1, "", "transient"), runner.Result(0, "", ""))
    lines = codex.apply_plugins(backup.Backup(description="t"), refresh=True)
    assert len(_upgrades(fake_runner)) == 2
    assert not [l for l in lines if "failed to upgrade" in l]
    assert ["codex", "plugin", "add", "loadout@agent-loadout", "--json"] in fake_runner.calls


def test_a_timed_out_upgrade_is_not_tried_again(fake_home, fake_runner, monkeypatch):
    _upgrade_fails(fake_runner, monkeypatch, runner.Result(124, "", "codex: timed out after 1800s"))
    lines = codex.apply_plugins(backup.Backup(description="t"), refresh=True)
    assert len(_upgrades(fake_runner)) == 1, "a second 30-minute wait helps nobody"
    assert any("failed to upgrade" in l and "timed out" in l for l in lines)


def test_a_failed_upgrade_adds_nothing_when_the_installed_list_is_unreadable(fake_home, fake_runner, monkeypatch):
    err = runner.Result(1, "", "boom")
    _upgrade_fails(fake_runner, monkeypatch, err, err)
    fake_runner.responses[("codex", "plugin", "list")] = runner.Result(1, "", "list failed")
    codex.apply_plugins(backup.Backup(description="t"), refresh=True)
    adds = [c[3] for c in fake_runner.calls if c[:3] == ["codex", "plugin", "add"]]
    assert not [a for a in adds if a.endswith("@agent-loadout")], "any of them may be installed: the old snapshot could downgrade it"
