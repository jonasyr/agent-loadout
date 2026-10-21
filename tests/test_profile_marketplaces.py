"""academic-research-skills comes with the thesis profile (spec fix 6, ADR 0037)."""
import json

import pytest

from loadout import backup, codex_project, inventory, own, paths, profiles, project, runner, targets
from fixtures import author_machine

ARS = "academic-research-skills"
ADD = ["claude", "plugin", "marketplace", "add", "Imbad0202/academic-research-skills"]
INSTALL = ["claude", "plugin", "install", f"{ARS}@{ARS}", "--scope", "project"]
LIST = ("claude", "plugin", "marketplace", "list", "--json")


@pytest.fixture
def repo(fake_home, tmp_path):
    p = tmp_path / "repo"
    (p / ".git").mkdir(parents=True)
    return p


def _listed(fake_runner, names):
    fake_runner.responses[LIST] = runner.Result(0, json.dumps([{"name": n} for n in names]), "")


def _plan(repo, capsys, name="thesis"):
    assert project.add_profile(repo, name, install=True, dry_run=True) == 0
    return capsys.readouterr().out


def test_base_settings_no_longer_declare_academic_research_skills():
    base = json.loads((paths.kit_root() / "settings.base.json").read_text())
    assert ARS not in base["extraKnownMarketplaces"]
    assert "life-sciences" in base["extraKnownMarketplaces"]  # declared, cloned only when a plugin uses it
    thesis = json.loads((paths.kit_root() / "profiles" / "thesis.json").read_text())
    assert thesis["settings"]["extraKnownMarketplaces"][ARS] == {
        "source": {"source": "github", "repo": "Imbad0202/academic-research-skills"}, "autoUpdate": True}


def test_profile_plan_adds_a_missing_marketplace_before_installing(repo, fake_runner, capsys):
    _listed(fake_runner, ["claude-plugins-official", "agent-loadout"])
    out = _plan(repo, capsys)
    add = next(i for i, l in enumerate(out.splitlines()) if l.strip().startswith("run") and " ".join(ADD) in l)
    install = next(i for i, l in enumerate(out.splitlines()) if " ".join(INSTALL) in l)
    assert add < install
    assert "restore cannot undo it" in out.splitlines()[add]
    assert not [c for c in fake_runner.calls if c[:4] == ADD[:4] or c[:3] == INSTALL[:3]]  # a dry run runs nothing


def test_profile_run_adds_the_marketplace_before_the_install(repo, fake_runner):
    _listed(fake_runner, ["claude-plugins-official"])
    project.add_profile(repo, "thesis", install=True, approve=lambda plan: True)
    assert ADD in fake_runner.calls and INSTALL in fake_runner.calls
    assert fake_runner.calls.index(ADD) < fake_runner.calls.index(INSTALL)


def test_profile_applied_at_once_adds_the_marketplace_before_the_install(repo, fake_runner):
    _listed(fake_runner, [])
    assert project.add_profile(repo, "thesis", install=True) == 0  # adopt and init: already asked
    assert fake_runner.calls.index(ADD) < fake_runner.calls.index(INSTALL)


def test_a_listed_marketplace_is_not_added_again(repo, fake_runner, capsys):
    _listed(fake_runner, [ARS, "claude-plugins-official"])
    out = _plan(repo, capsys)
    assert " ".join(ADD) not in out and " ".join(INSTALL) in out
    project.add_profile(repo, "thesis", install=True)
    assert ADD not in fake_runner.calls and INSTALL in fake_runner.calls


def test_a_failed_list_still_plans_the_add(repo, fake_runner, capsys):
    fake_runner.responses[LIST] = runner.Result(1, "", "boom")
    assert " ".join(ADD) in _plan(repo, capsys)


def test_claude_off_for_you_adds_nothing(repo, fake_runner, capsys, monkeypatch):
    monkeypatch.setattr(targets, "claude_enabled", lambda: False)
    out = _plan(repo, capsys)
    assert " ".join(ADD) not in out and " ".join(INSTALL) not in out
    project.add_profile(repo, "thesis", install=True)
    assert not [c for c in fake_runner.calls if c[:2] == ["claude", "plugin"]]


def test_a_codex_only_repo_adds_nothing(repo, fake_runner, capsys):
    (repo / ".loadout.json").write_text('{\n  "agents": [\n    "codex"\n  ]\n}\n')
    out = _plan(repo, capsys)
    assert " ".join(ADD) not in out and " ".join(INSTALL) not in out
    project.add_profile(repo, "thesis", install=True)
    assert not [c for c in fake_runner.calls if c[:2] == ["claude", "plugin"]]


def test_only_marketplaces_of_installed_plugins_are_added(repo, fake_runner, capsys, monkeypatch):
    prof = profiles.Profile(name="mine", description="", install=["a@used"], settings={
        "enabledPlugins": {"a@used": True, "b@unused": True},
        "extraKnownMarketplaces": {
            "used": {"source": {"source": "github", "repo": "me/used"}},
            "unused": {"source": {"source": "github", "repo": "me/unused"}}}})
    monkeypatch.setattr(profiles, "load_profile", lambda name: prof)
    out = _plan(repo, capsys, "mine")
    assert "claude plugin marketplace add me/used" in out
    assert not [l for l in out.splitlines() if "marketplace add" in l and "unused" in l]


def test_an_origin_that_looks_like_a_flag_is_never_run(repo, fake_runner, capsys, monkeypatch):
    prof = profiles.Profile(name="mine", description="", install=["a@flag"], settings={
        "extraKnownMarketplaces": {"flag": {"source": {"source": "git", "url": "--upload-pack=x"}}}})
    monkeypatch.setattr(profiles, "load_profile", lambda name: prof)
    out = _plan(repo, capsys, "mine")
    assert not [l for l in out.splitlines() if "marketplace add" in l and l.strip().startswith("run")]
    assert "marketplace flag" in out


@pytest.fixture
def machine(fake_home, fake_runner):
    author_machine(fake_home)
    known = fake_home / ".claude/plugins/known_marketplaces.json"
    data = json.loads(known.read_text())
    data[ARS] = {"source": {"source": "github", "repo": "Imbad0202/academic-research-skills"}}
    known.write_text(json.dumps(data))
    return fake_home


def test_profile_marketplace_counts_as_kit_in_inventory(machine):
    v = {(x.item.kind, x.item.name): x for x in inventory.classify(inventory.collect(with_versions=False))}
    assert v[("marketplace", ARS)].action == "keep"
    assert ARS in profiles.kit_marketplaces() and "agent-loadout" in profiles.kit_marketplaces()


def test_adopt_still_declares_an_adopted_plugins_marketplace(machine):
    item = inventory.Item("plugin", f"{ARS}@{ARS}", "", "user", {})
    rec = own.record_global(inventory.Verdict(item, "own", "mine"), backup.Backup())
    assert rec.ok
    data = json.loads((paths.personal_root() / "settings.json").read_text())
    assert data["extraKnownMarketplaces"][ARS] == {
        "source": {"source": "github", "repo": "Imbad0202/academic-research-skills"}}


def test_codex_project_still_routes_the_thesis_plugin(fake_home, fake_runner):
    lines = codex_project.plugins(profiles.load_profile("thesis"), dry_run=True)
    assert f"would install plugin {ARS} for Codex (from Imbad0202/academic-research-skills)" in lines
