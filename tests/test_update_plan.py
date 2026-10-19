"""The update plan: one numbered list, one question, numbers leave items out (spec decision 7)."""
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
