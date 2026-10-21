import json

from loadout import bootstrap, check, paths, runner

LIST = ("claude", "plugin", "marketplace", "list")
OFFICIAL = ("claude-plugins-official", "anthropics/claude-plugins-official")


def _listed(fake_runner, names):
    fake_runner.responses[LIST] = runner.Result(0, json.dumps([
        {"name": n, "source": "github", "repo": f"o/{n}", "installLocation": f"/x/{n}"} for n in names]), "")


def _markets():
    _, markets, plugins = bootstrap.plugins_plan()
    return markets, plugins


def test_fresh_home_adds_the_official_marketplace_before_its_plugins(fake_home, fake_runner):
    _listed(fake_runner, [])
    markets, plugins = _markets()
    assert OFFICIAL in markets
    assert "superpowers@claude-plugins-official" in plugins
    assert ["claude", "plugin", "marketplace", "list", "--json"] in fake_runner.calls


def test_a_known_official_marketplace_is_not_added_again(fake_home, fake_runner):
    _listed(fake_runner, ["claude-plugins-official"])
    markets, _ = _markets()
    assert "claude-plugins-official" not in [n for n, _ in markets]


def test_a_substring_name_does_not_count(fake_home, fake_runner):
    _listed(fake_runner, ["claude-plugins-official-mirror"])
    markets, _ = _markets()
    assert OFFICIAL in markets


def test_text_fallback_stops_at_claude_ai_section(fake_home, fake_runner):
    text = ("Configured marketplaces:\n\n"
            "  ❯ impeccable\n    Source: GitHub (pbakaus/impeccable)\n\n"
            "From claude.ai:\n\n"
            "  ❯ claude-plugins-official (available from claude.ai, account — not added)\n"
            "    Source: GitHub (anthropics/claude-plugins-official)\n")
    fake_runner.responses[LIST] = runner.Result(0, text, "")
    assert bootstrap.listed_marketplaces() == {"impeccable"}
    markets, _ = _markets()
    names = [n for n, _ in markets]
    assert "claude-plugins-official" in names and "impeccable" not in names


def test_listed_marketplaces_edge_cases(fake_home, fake_runner):
    fake_runner.responses[LIST] = runner.Result(0, "", "")
    assert bootstrap.listed_marketplaces() == set()
    fake_runner.responses[LIST] = runner.Result(0, "claude-plugins-official\nimpeccable\n", "")
    assert bootstrap.listed_marketplaces() == {"claude-plugins-official", "impeccable"}
    fake_runner.responses[LIST] = runner.Result(1, "", "boom")
    assert bootstrap.listed_marketplaces() is None


def test_a_declared_marketplace_no_enabled_plugin_uses_is_not_cloned(fake_home, fake_runner):
    _listed(fake_runner, [])
    markets, _ = _markets()
    names = [n for n, _ in markets]
    assert "life-sciences" not in names and "agent-loadout" in names
    paths.personal_root().mkdir(parents=True, exist_ok=True)
    (paths.personal_root() / "settings.json").write_text(json.dumps(
        {"enabledPlugins": {"wiley-scholar-gateway@life-sciences": True}}))
    markets, _ = _markets()
    assert ("life-sciences", "anthropics/life-sciences") in markets


def _row():
    return {r.name: r for r in check._plugins()}["plugins installed"]


def test_plugins_row_names_a_missing_marketplace(fake_home, fake_runner):
    known = fake_home / ".claude/plugins/known_marketplaces.json"
    known.parent.mkdir(parents=True, exist_ok=True)
    known.write_text(json.dumps({"agent-loadout": {"source": {"source": "github", "repo": "jonasyr/agent-loadout"}}}))
    r = _row()
    assert not r.ok and r.severity == "warn"
    assert "superpowers@claude-plugins-official" in r.detail and "claude-plugins-official" in r.detail.split(";")[-1]
    assert r.fix == "run loadout update (adds the marketplace, then installs them)"
    assert "automatically" not in r.detail + r.fix


def test_plugins_row_without_a_missing_marketplace(fake_home, fake_runner):
    known = fake_home / ".claude/plugins/known_marketplaces.json"
    known.parent.mkdir(parents=True, exist_ok=True)
    known.write_text(json.dumps({n: {} for n in ("agent-loadout", "claude-plugins-official", "impeccable")}))
    r = _row()
    assert not r.ok and "marketplace" not in r.detail
    assert "loadout update" in r.fix and "automatically" not in r.fix


def test_plugins_row_broken_known_marketplaces_is_invalid_json(fake_home, fake_runner):
    known = fake_home / ".claude/plugins/known_marketplaces.json"
    known.parent.mkdir(parents=True, exist_ok=True)
    known.write_text("{ broken")
    r = _row()
    assert not r.ok and "invalid JSON" in r.detail and r.fix == "fix the JSON syntax"


def test_an_older_claude_without_json_falls_back_to_the_plain_list(fake_home, fake_runner):
    fake_runner.responses[LIST + ("--json",)] = runner.Result(1, "", "error: unknown option '--json'")
    fake_runner.responses[LIST] = runner.Result(
        0, "Configured marketplaces:\n\n  ❯ agent-loadout\n  ❯ claude-plugins-official\n  ❯ impeccable\n", "")
    assert bootstrap.listed_marketplaces() == {"agent-loadout", "claude-plugins-official", "impeccable"}
    assert list(LIST) in fake_runner.calls
    markets, _ = _markets()
    assert not {"agent-loadout", "claude-plugins-official", "impeccable"} & {n for n, _ in markets}


def test_both_lists_failing_is_none(fake_home, fake_runner):
    fake_runner.responses[LIST] = runner.Result(1, "", "boom")
    assert bootstrap.listed_marketplaces() is None
    assert fake_runner.calls.count(list(LIST)) == 1 and fake_runner.calls.count(list(LIST) + ["--json"]) == 1


ARS_ID = "academic-research-skills@academic-research-skills"


def _enable_personal(plugin_id):
    paths.personal_root().mkdir(parents=True, exist_ok=True)
    (paths.personal_root() / "settings.json").write_text(json.dumps({"enabledPlugins": {plugin_id: True}}))


def test_a_personal_plugin_whose_marketplace_only_a_profile_declares_plans_that_marketplace(fake_home, fake_runner):
    _listed(fake_runner, [])
    _enable_personal(ARS_ID)
    markets, plugins = _markets()
    assert ("academic-research-skills", "Imbad0202/academic-research-skills") in markets
    assert ARS_ID in plugins
    from loadout import settings_merge
    assert "academic-research-skills" not in settings_merge.desired_settings().get("extraKnownMarketplaces", {})


def test_a_profile_marketplace_already_added_is_not_planned(fake_home, fake_runner):
    _listed(fake_runner, ["academic-research-skills"])
    _enable_personal(ARS_ID)
    markets, _ = _markets()
    assert "academic-research-skills" not in [n for n, _ in markets]


def test_plugins_row_for_a_marketplace_no_one_declares_says_to_declare_it(fake_home, fake_runner):
    known = fake_home / ".claude/plugins/known_marketplaces.json"
    known.parent.mkdir(parents=True, exist_ok=True)
    known.write_text(json.dumps({n: {} for n in ("agent-loadout", "claude-plugins-official", "impeccable")}))
    _enable_personal("x@nowhere")
    r = _row()
    assert "marketplace not added: nowhere" in r.detail
    assert "extraKnownMarketplaces" in r.fix and "nowhere" in r.fix
    _enable_personal(ARS_ID)
    r = _row()
    assert "academic-research-skills" in r.detail
    assert r.fix == "run loadout update (adds the marketplace, then installs them)"
