"""Fix batch C: user-facing text of the adopt/own tools."""
import json

import pytest

from loadout import adopt, backup, check, configure, inventory, own, paths
from loadout.__main__ import main
from fixtures import author_machine


@pytest.fixture
def machine(fake_home, fake_runner):
    author_machine(fake_home)
    return fake_home


def _verdicts():
    return inventory.classify(inventory.collect(with_versions=False))


def _get(kind, name):
    return next(v for v in _verdicts() if v.item.kind == kind and v.item.name == name)


def _help(argv, capsys):
    with pytest.raises(SystemExit):
        main(argv)
    return capsys.readouterr().out


def _asks(answers):
    asked, it = [], iter(answers)

    def ask(q):
        asked.append(q)
        return next(it, "")
    return ask, asked


def test_first_prompt_and_legend(machine, capsys):
    vs = [_get("skill", "my-skill")]
    ask, asked = _asks(["c", ""])
    assert own.ask_choices(vs, ask) == []
    assert asked[0] == ("your own tools: [l]eave all (not asked again on this machine) / [c]hoose each "
                        "(Enter: decide later): ")
    assert asked[1].endswith("(Enter: decide later): ") and "default: skip" not in asked[1]
    out = capsys.readouterr().out
    assert out.count("global = personal layer, every machine") == 1
    assert "remove = into the backup (loadout restore)" in out


def test_profile_prompt_enter_skips_without_error(machine, capsys):
    vs = [_get("skill", "my-skill")]
    ask, asked = _asks(["c", "p", ""])
    assert own.ask_choices(vs, ask) == []
    assert asked[2].endswith("; Enter: skip): ")
    assert "use lowercase" not in capsys.readouterr().out


def test_profile_prompt_shows_previous_profile(machine):
    vs = [_get("skill", "my-skill"), _get("plugin", "mystery@somewhere")]
    ask, asked = _asks(["c", "p", "mine", "p", ""])
    pairs = own.ask_choices(vs, ask)
    assert [c.profile for _, c in pairs] == ["mine", "mine"]
    assert asked[4].endswith(") [mine]: ") and "Enter: skip" not in asked[4]


def test_own_reason_lists_only_the_options_of_the_item(machine):
    assert _get("skill", "my-skill").reason == "Not managed by loadout. Choose: global, project, leave or remove."
    (machine / ".claude/.mcp.json").write_text(json.dumps({"mcpServers": {"my-db": {"command": "db"}}}))
    mcp = _get("mcp", "my-db")
    assert mcp.reason == "Not managed by loadout. Choose: leave or remove."
    assert own.own_reason(_get("skill", "gpt-taste").item) == "Not managed by loadout. Choose: global, leave or remove."


def test_hook_without_matcher_reads_no_matcher_in_results(machine):
    v = _get("hook", "Stop:")
    assert own.display_name(v.item) == "Stop (no matcher)" and v.item.name == "Stop:"
    rec = own.record_global(v, backup.Backup())
    assert rec.lines[0].startswith("hook Stop (no matcher): recorded in ")
    assert "Stop::" not in "\n".join(rec.lines)
    assert own.display_name(_get("hook", "PreToolUse:Edit").item) == "PreToolUse:Edit"


def test_leave_result_line_explains_how_to_undo(machine):
    lines, _ = adopt.apply_own([(_get("skill", "my-skill"), own.Choice("leave"))], backup.Backup())
    assert lines == ["skill my-skill: left on this machine (not asked again; change it with "
                     "`loadout configure set own NAME …`, list with `loadout configure own --all`)"]


def test_set_own_project_prints_one_hint_and_restart_note(machine, capsys):
    assert configure.set_own("my-skill", "project:mine") == 0
    out = capsys.readouterr().out
    assert out.count("loadout profile mine") == 1
    assert "apply it in a repo: cd <repo> && loadout profile mine" in out
    assert out.count(adopt.RESTART_NOTE) == 1
    assert adopt.RESTART_NOTE == "Restart Claude Code (or run /reload-plugins) to load the changes."


def test_set_own_leave_needs_no_restart(machine, capsys):
    assert configure.set_own("my-skill", "leave") == 0
    assert "Restart Claude Code" not in capsys.readouterr().out


def test_project_skill_machine_line(machine):
    lines, _ = adopt.apply_own([(_get("skill", "my-skill"), own.Choice("project", "mine"))], backup.Backup())
    assert ("skill my-skill: removed from ~/.claude/skills (kept in profile mine; original in the backup)"
            in lines)
    assert not (machine / ".claude/skills/my-skill").exists()


def test_adopt_run_prints_restart_note_after_a_change(machine, capsys):
    assert adopt.run(True, None, set(), False, ask=lambda q: "", with_versions=False, interactive=False,
                     own_spec="my-skill=global") == 0
    assert adopt.RESTART_NOTE in capsys.readouterr().out
    assert adopt.run(True, None, set(), False, ask=lambda q: "", with_versions=False, interactive=False,
                     own_spec="mystery@somewhere=leave") == 0
    assert adopt.RESTART_NOTE not in capsys.readouterr().out


def test_check_own_tools_text(machine):
    r = next(r for r in check.run_checks() if r.name == "own tools")
    assert not r.ok and r.fix == "decide with `loadout adopt --apply` or `loadout configure own`"


def test_check_own_tools_json_error_names_the_file(machine):
    (paths.personal_root()).mkdir(parents=True, exist_ok=True)
    bad = paths.personal_root() / "settings.json"
    bad.write_text("{nope")
    r = next(r for r in check.run_checks() if r.name == "own tools")
    assert not r.ok and r.fix == f"fix the JSON syntax in {bad}"


def test_own_lines_empty_state(fake_home, fake_runner):
    assert configure.own_lines(False) == ["Nothing to decide: loadout or your personal layer manages every tool."]


def test_own_lines_empty_state_mentions_left_tools(machine):
    for v in own.unmanaged(_verdicts()):
        own.remember_leave(v.item)
    lines = configure.own_lines(False)
    assert lines[0].startswith("Nothing to decide:")
    assert lines[1] == "Tools you chose to leave on this machine: `loadout configure own --all`"
    assert len(configure.own_lines(True)) > 2


def test_help_texts(capsys):
    out = " ".join(_help(["configure", "--help"], capsys).split())
    assert "list your own tools (own)" in out and "(names: configure own)" in out
    out = " ".join(_help(["adopt", "--help"], capsys).split())
    assert "item names to skip in this run (nothing is remembered)" in out
    assert "my-db=project:mydb" in out and "Event:matcher" in out and "#n" in out


def test_parse_spec_comma_in_name_explains(machine):
    with pytest.raises(ValueError, match=r"names containing ',' .*cannot be given here, use `loadout adopt --apply`"):
        own.parse_spec("hook:PreToolUse:Bash,Edit=global")


def _set_hook(command):
    data = json.loads((paths.claude_home() / "settings.json").read_text())
    data["hooks"]["Notification"] = [{"hooks": [{"type": "command", "command": command}]}]
    (paths.claude_home() / "settings.json").write_text(json.dumps(data))


def test_no_outside_home_note_for_system_programs(machine):
    _set_hook("/usr/bin/true")
    rec = own.record_global(_get("hook", "Notification:"), backup.Backup())
    assert rec.ok and not any("outside your home" in line for line in rec.lines)


def test_outside_home_note_for_other_files(machine, tmp_path):
    other = tmp_path / "elsewhere.sh"
    other.write_text("#!/bin/sh\n")
    other.chmod(0o755)
    _set_hook(str(other))
    rec = own.record_global(_get("hook", "Notification:"), backup.Backup())
    assert any("outside your home" in line for line in rec.lines)
