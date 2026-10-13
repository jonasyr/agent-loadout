"""Names from files become paths or arguments only when they are plain."""
import pytest

from loadout import codex_project, link, paths, profiles, project
from loadout.jsonio import save_json


@pytest.mark.parametrize("name", ["../x", "a/b", "-x", "X Y", ""])
def test_profile_names_must_be_plain(fake_home, name):
    with pytest.raises(ValueError, match="profile name"):
        profiles.load_profile(name)


def test_kit_profiles_still_load(fake_home):
    for name in ("android", "db", "sonar", "thesis", "web"):
        profiles.load_profile(name)


def test_skills_json_keys_must_be_plain(fake_home, tmp_path):
    target = tmp_path / "s"
    target.mkdir()
    save_json(paths.personal_root() / "skills.json", {"../agents": str(target), "-x": str(target), "ok": str(target)})
    names = [dest.name for dest, _ in link.LINKS() if dest.parent == paths.claude_home() / "skills"]
    assert names == ["ok"]


def test_plugin_ids_must_look_like_name_at_market(fake_home, fake_runner, tmp_path, capsys, monkeypatch):
    from loadout import targets
    monkeypatch.setattr(targets, "claude_enabled", lambda: True)
    prof = profiles.Profile(name="t", description="", install=["-rf@x", "ok@m"])
    project._install(prof, tmp_path, dry_run=False)
    assert ["claude", "plugin", "install", "ok@m", "--scope", "project"] in fake_runner.calls
    assert not any("-rf@x" in c for call in fake_runner.calls for c in call)
    assert "not a name@marketplace id, skipped" in capsys.readouterr().out
    assert codex_project._wanted(prof)[1] == ["ok@m"]


def test_profile_commands_are_printed_redacted(fake_home, fake_runner, tmp_path, capsys):
    from loadout import runner
    token = "ghp_" + "a" * 36
    fake_runner.responses[("tool",)] = runner.Result(1, "", f"bad token {token}")
    prof = profiles.Profile(name="t", description="", commands=[["tool", f"--token={token}"]])
    project._install(prof, tmp_path, dry_run=False)
    assert token not in capsys.readouterr().out
