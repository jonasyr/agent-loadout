"""The CLI front of configure new skill: exit codes, backup line, commit offer only for the personal layer."""
from loadout import configure, paths, targets
from loadout.__main__ import main


def _on(monkeypatch):
    monkeypatch.setattr(targets, "claude_enabled", lambda: True)
    monkeypatch.setattr(targets, "codex_enabled", lambda: True)


def test_new_skill_prints_the_backup_and_offers_the_commit(fake_home, fake_runner, monkeypatch, capsys):
    _on(monkeypatch)
    offered = []
    monkeypatch.setattr(configure, "offer_commit", lambda ask: offered.append(1))
    assert main(["configure", "new", "skill", "notes", "--description", "Use when taking notes."]) == 0
    out = capsys.readouterr().out
    assert "created" in out and "loadout restore" in out and offered == [1]
    assert (paths.personal_root() / "skills" / "notes" / "SKILL.md").is_file()


def test_bad_name_exits_2_and_a_refusal_exits_1(fake_home, fake_runner, monkeypatch, capsys):
    _on(monkeypatch)
    monkeypatch.setattr(configure, "offer_commit", lambda ask: None)
    assert main(["configure", "new", "skill", "Bad"]) == 2
    assert main(["configure", "new", "skill", "notes"]) == 0
    assert main(["configure", "new", "skill", "notes"]) == 1
    assert "already exists" in capsys.readouterr().err


def test_repo_target_offers_no_commit(fake_home, fake_runner, monkeypatch, tmp_path):
    _on(monkeypatch)
    offered = []
    monkeypatch.setattr(configure, "offer_commit", lambda ask: offered.append(1))
    repo = tmp_path / "r"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.chdir(repo)
    assert main(["configure", "new", "skill", "notes", "--to", "repo"]) == 0
    assert offered == []


def test_repo_skill_codex_cannot_see_exits_1(fake_home, fake_runner, monkeypatch, tmp_path):
    """Windows without symlink rights: the skill is written, but Codex does not get it; say so with exit 1."""
    import os
    _on(monkeypatch)
    monkeypatch.setattr(configure, "offer_commit", lambda ask: None)
    repo = tmp_path / "r"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.chdir(repo)

    def no_symlinks(*a, **k):
        raise OSError(1, "A required privilege is not held by the client")
    monkeypatch.setattr(os, "symlink", no_symlinks)
    assert main(["configure", "new", "skill", "notes", "--to", "repo"]) == 1
    assert (repo / ".claude" / "skills" / "notes" / "SKILL.md").is_file()


def test_a_token_given_as_name_or_target_is_never_printed(fake_home, fake_runner, monkeypatch, capsys):
    _on(monkeypatch)
    token = "ghp_" + "Z" * 36
    assert main(["configure", "new", "skill", token]) == 1  # refused as a secret before the format check
    assert main(["configure", "new", "skill", "notes", "--to", token]) == 1  # refused as a secret
    assert main(["configure", "new", "skill", "notes", "--to", f"project:{token}"]) == 1
    assert main(["configure", "new", "skill", "notes", "--to", "elsewhere"]) == 2  # plain bad input stays 2
    captured = capsys.readouterr()
    assert token not in captured.err and token not in captured.out


def test_a_stray_positional_value_is_refused_and_writes_nothing(fake_home, fake_runner, monkeypatch):
    """`new skill notes "Use when ..."` forgot --description: say so instead of dropping the text."""
    _on(monkeypatch)
    assert main(["configure", "new", "skill", "notes", "Use when taking notes"]) == 1
    assert not (paths.personal_root() / "skills" / "notes").exists()


def test_set_skill_is_refused_and_writes_no_setting(fake_home, fake_runner, monkeypatch):
    """`skill` is a kind for `new` only: `set skill x on` must not fall through to `set pref`."""
    _on(monkeypatch)
    assert main(["configure", "set", "skill", "notes", "on"]) == 1
    assert not (paths.personal_root() / "settings.json").exists()


def test_new_needs_skill_and_a_name(fake_home, fake_runner, monkeypatch):
    _on(monkeypatch)
    assert main(["configure", "new", "skill"]) == 1
    assert main(["configure", "new", "plugin", "x"]) == 1
