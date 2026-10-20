"""The update plan: one numbered list, one question, numbers leave items out (spec decision 7)."""
import pytest
import json

from loadout import apply, bootstrap, catalog, codex, maintenance as m, paths, pkgmgr, targets, update, versions

PROMPT = "Apply all? [Y/n, or the numbers to leave out, e.g. 3 5] "


def _entry(eid):
    return next(e for e in catalog.binaries() if e["id"] == eid)


def _plan_world(monkeypatch, outdated=(), missing=(), claude=True, codex_on=False):
    monkeypatch.setattr(targets, "OVERRIDE", {"claude": claude, "codex": codex_on})
    monkeypatch.setattr(m, "find_outdated", lambda: list(outdated))
    monkeypatch.setattr(bootstrap, "missing_tools", lambda *a, **k: list(missing))
    monkeypatch.setattr(pkgmgr, "update_plan", lambda e: ([[e["id"], "self-update"]], "catalog"))
    monkeypatch.setattr(apply, "claude_plugins_step", lambda **k: apply.StepResult("Plugins", ""))
    monkeypatch.setattr(apply, "codex_step", lambda *a, **k: apply.StepResult("Codex", ""))


def _plan(monkeypatch, fake_home, fake_runner, **kw):
    _plan_world(monkeypatch, **kw)
    return update.build_plan(kw.get("claude", True), kw.get("codex_on", False))


def test_plan_numbers_items_and_shows_each_tool_command(fake_home, fake_runner, monkeypatch):
    plan = _plan(monkeypatch, fake_home, fake_runner,
                 outdated=[(_entry("uv"), (0, 8, 23), (0, 9, 0))],
                 missing=[(_entry("pyright"), [["npm", "i", "-g", "pyright"]], True)])
    assert [i.n for i in plan] == list(range(1, len(plan) + 1))
    assert plan[0].kind == "reapply"
    text = "\n".join(update.render(plan))
    assert "uv: 0.8.23 -> 0.9.0" in text and "uv self-update" in text
    tool_install = [i for i in plan if i.kind == "tool-install"][0]
    assert tool_install.optional and tool_install.key == "pyright"
    assert "npm i -g pyright" in text


def _items():
    return [update.PlanItem(1, "reapply", "a", []), update.PlanItem(2, "tool-update", "b", [], key="b"),
            update.PlanItem(3, "tool-update", "c", [], key="c"),
            update.PlanItem(4, "tool-install", "d", [], optional=True, key="d")]


def test_answer_numbers_leave_items_out():
    plan = _items()
    assert [i.n for i in update.choose(plan, "")] == [1, 2, 3]
    assert [i.n for i in update.choose(plan, "Y")] == [1, 2, 3]
    assert update.choose(plan, "n") == []
    assert [i.n for i in update.choose(plan, "2")] == [1, 3]
    assert [i.n for i in update.choose(plan, "2, 3")] == [1]
    assert [i.n for i in update.choose(plan, "3 2")] == [1]
    assert [i.n for i in update.choose(plan, "4")] == [1, 2, 3, 4]  # an optional item's number keeps it
    assert [i.n for i in update.choose(plan, "yes 4")] == [1, 2, 3, 4]


def test_a_bad_answer_asks_again(capsys):
    plan = _items()
    assert update.choose(plan, "maybe") is None
    assert update.choose(plan, "9") is None
    assert update.choose(plan, "0") is None
    answers = iter(["what", "9", "2"])
    asked = []

    def ask(q):
        asked.append(q)
        return next(answers)
    chosen = update.confirm(plan, False, ask, interactive=True)
    assert [i.n for i in chosen] == [1, 3]
    assert asked == [PROMPT] * 3


def test_n_declines_and_the_weekly_notice_goes_quiet_until_newer(fake_home, fake_runner, monkeypatch):
    uv, pyright = _entry("uv"), _entry("pyright")
    m.decline("uv", (1, 0, 1))
    assert json.loads((paths.state_dir() / "declined-updates.json").read_text()) == {"uv": "1.0.1"}
    offered = [(pyright, (0, 1, 0), (1, 0, 1))]
    m.decline("pyright", (1, 0, 1))
    assert m.worth_notifying(offered) == []
    assert m.worth_notifying([(pyright, (0, 1, 0), (1, 0, 2))]) == [(pyright, (0, 1, 0), (1, 0, 2))]
    fake_runner.paths["uv"] = "/home/u/.local/share/mise/installs/uv/0.8.23/uv"
    assert m.worth_notifying([(uv, (0, 8, 23), (1, 0, 1))]) == []  # a mise entry too
    assert m.worth_notifying([(uv, (0, 8, 23), (1, 0, 2))]) != []
    # the answer n itself declines every offered update; an installed version removes the entry
    plan = [update.PlanItem(1, "reapply", "a", []),
            update.PlanItem(2, "tool-update", "x", [], key="pyright", latest=(1, 0, 3))]
    assert update.confirm(plan, False, lambda q: "n", interactive=True) == []
    assert json.loads((paths.state_dir() / "declined-updates.json").read_text())["pyright"] == "1.0.3"
    m._remember_refused("pyright", None)
    assert "pyright" not in json.loads((paths.state_dir() / "declined-updates.json").read_text())


def test_without_a_terminal_the_plan_is_shown_and_nothing_runs(capsys):
    plan = _items()

    def ask(q):
        raise AssertionError("no question without a terminal")
    assert update.confirm(plan, False, ask, interactive=False) is None
    out = capsys.readouterr().out
    assert "1." in out and "nothing changed (run loadout update --yes to apply)" in out
    # --yes takes every non-optional item
    assert [i.n for i in update.confirm(plan, True, ask, interactive=False)] == [1, 2, 3]


def test_an_agent_that_is_off_is_not_in_the_plan(fake_home, fake_runner, monkeypatch):
    _plan_world(monkeypatch, claude=False, codex_on=True)
    touched = []
    monkeypatch.setattr(apply, "claude_plugins_step", lambda **k: touched.append("claude") or apply.StepResult("P", ""))
    monkeypatch.setattr(codex, "unavailable", lambda *a, **k: "no codex")
    plan = update.build_plan(False, True)
    assert touched == []
    assert not [i for i in plan if i.kind.startswith("claude")]
    plan = update.build_plan(False, False)
    assert [i.kind for i in plan] == ["reapply"]
    assert "Claude" not in "\n".join(update.render(plan)) and "Codex" not in "\n".join(update.render(plan))


def test_the_codex_item_shows_what_runs_per_marketplace_and_plugin(fake_home, fake_runner, monkeypatch):
    from loadout import settings_merge
    _plan_world(monkeypatch, claude=False, codex_on=True)
    monkeypatch.setattr(codex, "unavailable", lambda *a, **k: None)
    monkeypatch.setattr(settings_merge, "desired_settings", lambda: {})
    monkeypatch.setattr(codex, "plugin_routes", lambda s: ({"o/a": ["p1", "p2"], "o/b": ["q1", "q2"], "o/c": ["r1"]}, []))
    monkeypatch.setattr(codex, "installed_plugins", lambda: {"p1@a-m", "q1@b-m", "q2@b-m"})
    monkeypatch.setattr(codex, "unchanged_routes", lambda routes, installed=None: ({"o/b"}, {"q1@b-m"}))
    monkeypatch.setattr(codex, "marketplaces", lambda: {"a-m": {"root": None, "source": None},
                                                        "b-m": {"root": None, "source": None}})
    monkeypatch.setattr(codex, "_load_record", lambda: {"o/a": {"name": "a-m", "at": 0},
                                                        "o/b": {"name": "b-m", "at": 1_699_956_800}})
    plan = update.build_plan(False, True)
    text = "\n".join(update.render(plan))
    lines = [l.strip() for l in text.splitlines()]
    assert "refresh marketplace o/a" in lines and "skip marketplace o/b (unchanged since 2023-11-14)" in lines
    assert "command: codex plugin marketplace add o/a --json" in lines
    assert "command: codex plugin marketplace upgrade a-m" in lines
    assert "command: codex plugin marketplace upgrade o/a" not in lines
    assert "re-add plugin p1@a-m" in lines and "add plugin p2@a-m" in lines
    assert "command: codex plugin add p2@a-m --json" in lines
    assert "re-add plugin q2@b-m" in lines and not any("q1@b-m" in l for l in lines)
    assert "add or refresh marketplace o/c" in lines and "add plugin r1@<o/c's marketplace>" in lines
    assert "command: codex plugin marketplace upgrade <o/c's marketplace> (only when Codex had it)" in lines


def test_an_optional_tool_brings_its_missing_prerequisite(fake_home, fake_runner, monkeypatch):
    mise = {"id": "mise", "helper": True}
    ra = {"id": "rust-analyzer", "needs": ["mise"]}
    plan = _plan(monkeypatch, fake_home, fake_runner,
                 missing=[(mise, [["curl", "mise.run"]], True), (ra, [["mise", "use", "-g", "rust-analyzer"]], True)])
    by_key = {i.key: i for i in plan}
    n_mise, n_ra = by_key["mise"].n, by_key["rust-analyzer"].n
    assert by_key["rust-analyzer"].needs == ("mise",)
    text = "\n".join(update.render(plan))
    assert f"needs mise (item {n_mise})" in text
    tools = lambda chosen: [i.key for i in chosen if i.kind == "tool-install"]  # noqa: E731
    assert tools(update.choose(plan, str(n_ra))) == ["mise", "rust-analyzer"]
    assert tools(update.choose(plan, "")) == []


def test_leaving_out_a_prerequisite_leaves_out_what_needs_it():
    plan = [update.PlanItem(1, "reapply", "a", []),
            update.PlanItem(2, "tool-install", "install mise", [], key="mise"),
            update.PlanItem(3, "tool-install", "install x", [], key="x", needs=("mise",)),
            update.PlanItem(4, "tool-install", "install y", [], optional=True, key="y", needs=("mise",))]
    assert [i.n for i in update.choose(plan, "2")] == [1]
    assert [i.n for i in update.choose(plan, "2 4")] == [1]
    assert [i.n for i in update.choose(plan, "4")] == [1, 2, 3, 4]


def test_the_plan_never_shows_a_credential_in_a_url():
    """A personal marketplace may come from https://user:token@host/...: the plan masks it; the command runs as is."""
    secret = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"  # built at runtime (test_repo_static flags literals)
    url = f"https://jonas:{secret}@example.com/team/market.git"
    plan = [update.PlanItem(1, "claude-plugin-install", f"marketplace from {url}",
                            [["claude", "plugin", "marketplace", "add", url]],
                            groups=[(f"add {url}", [["claude", "plugin", "marketplace", "add", url]])]),
            update.PlanItem(2, "tool-install", "x", [["sh", "-c", f"git clone {url}"]])]
    text = "\n".join(update.render(plan))
    assert secret not in text and "example.com/team/market.git" in text
    assert plan[0].commands[0][-1] == url  # what runs is unchanged



@pytest.mark.parametrize("off", ["claude", "codex"])
def test_an_agent_that_is_off_gets_no_tool_install_or_update(fake_home, fake_runner, monkeypatch, off):
    """The agent-off rule: an agent's own CLI (its catalog target) is neither installed nor updated while it is off."""
    on = {"claude": off != "claude", "codex": off != "codex"}
    targets.set_agents(on)
    fake_runner.missing.update({"claude", "codex"})
    assert off not in [e["id"] for e, _, _ in bootstrap.missing_tools()]
    fake_runner.missing.clear()  # both installed and outdated
    monkeypatch.setattr(versions, "local_version", lambda e: (1, 0, 0))
    monkeypatch.setattr(versions, "latest_version", lambda e: (2, 0, 0))
    monkeypatch.setattr(pkgmgr, "mise_tool", lambda e: None)
    outdated = [e["id"] for e, _, _ in m.find_outdated()]
    assert off not in outdated and (("codex" if off == "claude" else "claude") in outdated)


def test_a_first_update_names_codex_marketplaces_from_codex_list(fake_home, fake_runner, monkeypatch):
    """No codex-marketplaces.json yet: the marketplace name comes from Codex's own list (matched by source), so the
    plugin ids are real and an installed plugin is a re-add."""
    from loadout import settings_merge
    _plan_world(monkeypatch, claude=False, codex_on=True)
    monkeypatch.setattr(codex, "unavailable", lambda *a, **k: None)
    monkeypatch.setattr(settings_merge, "desired_settings",
                        lambda: {"enabledPlugins": {"superpowers@claude-plugins-official": True}})
    monkeypatch.setattr(codex, "installed_plugins", lambda: {"superpowers@claude-plugins-official"})
    monkeypatch.setattr(codex, "unchanged_routes", lambda routes, installed=None: (set(), set()))
    monkeypatch.setattr(codex, "marketplaces", lambda: {"claude-plugins-official": {
        "root": None, "source": "https://github.com/anthropics/claude-plugins-official.git"}})
    monkeypatch.setattr(codex, "_load_record", lambda: {})
    text = "\n".join(update.render(update.build_plan(False, True)))
    assert "re-add plugin superpowers@claude-plugins-official" in text
    assert "codex plugin marketplace upgrade claude-plugins-official" in text
    assert "plugins: re-add 1" in text and "no record to compare yet" in text
    assert "<" not in text
