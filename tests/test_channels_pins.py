import json

from loadout import backup, bootstrap, channels, codex, paths, runner, settings_merge, targets

TAG = "v0.3.0"
SLUG = "jonasyr/agent-loadout"


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
    assert channels.codex_source(SLUG) == f"{SLUG}@{TAG}"
    assert channels.claude_origin("other/repo") == "other/repo"
    assert channels.codex_source("other/repo") == "other/repo"
    fake_runner.responses[("git", "-C", str(kit), "describe")] = runner.Result(1, "", "no tag")
    assert channels.pin() is None and channels.claude_origin(SLUG) == SLUG


def test_undo_command_with_a_tag_is_allowed():
    assert backup._allowed_run(["claude", "plugin", "marketplace", "add", f"{SLUG}#{TAG}"])


def test_codex_add_passes_the_tag_and_head_checks_it(fake_home, fake_runner, tmp_path, monkeypatch):
    _stable(fake_runner, _kit(tmp_path, monkeypatch))
    refs = []
    monkeypatch.setattr(codex, "remote_head", lambda url, ref: refs.append((url, ref)) or "a" * 40)
    fake_runner.responses[("codex", "--version")] = runner.Result(0, "codex-cli 0.162.1\n", "")
    fake_runner.responses[("codex", "plugin", "marketplace", "add")] = _added()
    codex._install_routes({SLUG: [], "o/other": []}, None, refresh=False, say=lambda line: None, listed=None)
    adds = [c for c in fake_runner.calls if c[1:4] == ["plugin", "marketplace", "add"]]
    assert [c[4] for c in adds] == [f"{SLUG}@{TAG}", "o/other"]
    assert (f"https://github.com/{SLUG}.git", TAG) in refs and ("https://github.com/o/other.git", None) in refs


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
