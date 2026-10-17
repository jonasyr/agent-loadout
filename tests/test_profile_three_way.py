"""loadout profile in a shared repo: updates, a teammate's changes, the record (spec Part 2)."""
import json
import os
from pathlib import Path

import pytest

from loadout import backup, jsonio, profiles, project, targets

TOKEN = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
YES = staticmethod(lambda plan: True)


@pytest.fixture
def repo(fake_home, fake_runner, tmp_path):
    p = tmp_path / "repo"
    (p / ".git").mkdir(parents=True)
    targets.set_agents({"claude": True, "codex": False})
    return p


def use(monkeypatch, settings=None, mcp=None, by_name=None):
    def load(n):
        s = (by_name or {}).get(n, settings)
        return profiles.Profile(name=n, description="d", settings=s or {}, mcp=mcp or {})
    monkeypatch.setattr(profiles, "load_profile", load)


def run(repo, name="web", **kw):
    return project.add_profile(repo, name, install=False, approve=lambda plan: True, **kw)


def settings(repo):
    return json.loads((repo / ".claude" / "settings.json").read_text())


def record(repo, name="web"):
    return json.loads((repo / ".loadout.json").read_text()).get("profiles", {}).get(name, {})


def edit(repo, change):
    path = repo / ".claude" / "settings.json"
    data = json.loads(path.read_text())
    change(data)
    path.write_text(json.dumps(data, indent=2) + "\n")


def test_the_first_run_records_what_it_added(repo, monkeypatch):
    use(monkeypatch, {"env": {"A": "1"}, "permissions": {"allow": ["Bash(npm test)"]}})
    assert run(repo) == 0
    assert record(repo) == {".claude/settings.json": {"env/A": "1", "permissions/allow": ["Bash(npm test)"]}}


def test_a_profile_update_applies_by_itself(repo, monkeypatch, capsys):
    use(monkeypatch, {"env": {"A": "1"}})
    run(repo)
    use(monkeypatch, {"env": {"A": "2"}})
    run(repo)
    assert settings(repo)["env"]["A"] == "2" and "update env/A" in capsys.readouterr().out


def test_a_teammate_change_is_kept_without_a_yes(repo, monkeypatch, capsys):
    use(monkeypatch, {"env": {"A": "1"}})
    run(repo)
    edit(repo, lambda d: d["env"].update(A="9"))
    use(monkeypatch, {"env": {"A": "2"}})
    run(repo)
    assert settings(repo)["env"]["A"] == "9" and "--take-profile" in capsys.readouterr().out


def test_decide_yes_takes_the_profile_values(repo, monkeypatch):
    use(monkeypatch, {"env": {"A": "1"}})
    run(repo)
    edit(repo, lambda d: d["env"].update(A="9"))
    use(monkeypatch, {"env": {"A": "2"}})
    asked = []
    run(repo, decide=lambda lines: asked.append(lines) or True)
    assert settings(repo)["env"]["A"] == "2"
    assert asked[0][0] == "This repo differs from profile web in 1 entry:" and '"9"' in asked[0][1]


def test_a_declined_offer_is_not_asked_again(repo, monkeypatch):
    use(monkeypatch, {"env": {"A": "1"}})
    run(repo)
    edit(repo, lambda d: d["env"].update(A="9"))
    use(monkeypatch, {"env": {"A": "2"}})
    asked = []
    run(repo, decide=lambda lines: asked.append(1) and False)
    run(repo, decide=lambda lines: asked.append(1) and False)
    assert asked == [1] and settings(repo)["env"]["A"] == "9"


def test_a_removed_list_entry_stays_removed(repo, monkeypatch, capsys):
    use(monkeypatch, {"permissions": {"allow": ["Bash(npm test)", "Bash(ls)"]}})
    run(repo)
    edit(repo, lambda d: d["permissions"]["allow"].remove("Bash(npm test)"))
    run(repo, decide=lambda lines: True)
    assert settings(repo)["permissions"]["allow"] == ["Bash(ls)"] and "kept removed" in capsys.readouterr().out


def test_without_a_record_only_missing_entries_are_added(repo, monkeypatch, capsys):
    (repo / ".claude").mkdir()
    (repo / ".claude" / "settings.json").write_text(json.dumps({"env": {"A": "5"}}, indent=2) + "\n")
    use(monkeypatch, {"env": {"A": "2", "B": "1"}})
    run(repo)
    assert settings(repo)["env"] == {"A": "5", "B": "1"}
    assert record(repo) == {".claude/settings.json": {"env/B": "1"}}
    assert "left as is" in capsys.readouterr().out


def test_an_entry_the_profile_dropped_is_removed(repo, monkeypatch):
    use(monkeypatch, {"env": {"A": "1"}, "x": 1})
    run(repo)
    use(monkeypatch, {"x": 1})
    run(repo)
    assert settings(repo) == {"x": 1} and record(repo) == {".claude/settings.json": {"x": 1}}


def test_a_dropped_settings_section_is_cleaned_up(repo, monkeypatch):
    use(monkeypatch, {"env": {"A": "1"}})
    run(repo)
    use(monkeypatch, {})
    run(repo)
    assert settings(repo) == {} and record(repo) == {}


def test_indent_four_and_crlf_are_kept(repo, monkeypatch):
    path = repo / ".claude" / "settings.json"
    path.parent.mkdir()
    path.write_bytes((json.dumps({"mine": 1}, indent=4).replace("\n", "\r\n") + "\r\n").encode())
    use(monkeypatch, {"env": {"A": "1"}})
    run(repo)
    use(monkeypatch, {"env": {"A": "2"}})
    run(repo)
    assert jsonio.json_style(path.read_bytes().decode()) == jsonio.JsonStyle(4, "\r\n", True)


def test_a_no_op_rerun_touches_nothing(repo, monkeypatch, capsys):
    use(monkeypatch, {"env": {"A": "1"}, "permissions": {"allow": ["x"]}})
    run(repo)
    files = [repo / ".claude" / "settings.json", repo / ".loadout.json"]
    for f in files:
        os.utime(f, (1_000_000, 1_000_000))
    capsys.readouterr()
    assert run(repo) == 0
    assert [f.stat().st_mtime for f in files] == [1_000_000, 1_000_000]
    assert "(no file changes)" in capsys.readouterr().out


def test_two_profiles_in_one_plan_share_a_list_entry(repo, monkeypatch):
    use(monkeypatch, by_name={"a": {"disabledMcpjsonServers": ["x"]}, "b": {"disabledMcpjsonServers": ["x", "y"]}})
    project.init(repo, ["a", "b"], yes=True, install=False, dry_run=False, ask=lambda q: "", interactive=False)
    assert settings(repo)["disabledMcpjsonServers"] == ["x", "y"]
    assert record(repo, "a") == {".claude/settings.json": {"disabledMcpjsonServers": ["x"]}}
    assert record(repo, "b") == {".claude/settings.json": {"disabledMcpjsonServers": ["x", "y"]}}
    use(monkeypatch, by_name={"a": {"other": 1}, "b": {"disabledMcpjsonServers": ["x", "y"]}})
    run(repo, "a")
    assert settings(repo)["disabledMcpjsonServers"] == ["x", "y"]


def test_a_secret_is_never_in_the_record_or_the_output(repo, monkeypatch, capsys):
    use(monkeypatch, mcp={"mcpServers": {"gh": {"command": "gh-mcp", "env": {"GITHUB_TOKEN": TOKEN}}}})
    run(repo)
    assert TOKEN not in (repo / ".loadout.json").read_text()
    assert TOKEN not in capsys.readouterr().out


def test_a_wrong_shaped_record_stops_before_any_change(repo, monkeypatch, capsys):
    (repo / ".loadout.json").write_text('{\n  "agents": [\n    "claude"\n  ],\n  "profiles": []\n}\n')
    use(monkeypatch, {"env": {"A": "1"}})
    assert run(repo) == 1
    assert not (repo / ".claude").exists() and "profiles must map" in capsys.readouterr().out


def test_a_record_it_cannot_write_leaves_loadout_json_and_writes_the_rest(repo, monkeypatch, capsys):
    (repo / ".loadout.json").write_text('{"agents": ["claude"]}')
    use(monkeypatch, {"env": {"A": "1"}})
    run(repo)
    assert (repo / ".loadout.json").read_text() == '{"agents": ["claude"]}'
    assert settings(repo)["env"]["A"] == "1" and "record of profile web is not written" in capsys.readouterr().out


def test_restore_undoes_an_update_and_its_record(repo, monkeypatch, capsys):
    use(monkeypatch, {"env": {"A": "1"}})
    run(repo)
    before = {p: p.read_bytes() for p in (repo / ".claude" / "settings.json", repo / ".loadout.json")}
    use(monkeypatch, {"env": {"A": "2"}})
    capsys.readouterr()
    run(repo)
    line = next(l for l in capsys.readouterr().out.splitlines() if "undo: loadout restore " in l)
    _, ok, _ = backup.restore(Path(line.split("undo: loadout restore ", 1)[1].strip()))
    assert ok and {p: p.read_bytes() for p in before} == before
