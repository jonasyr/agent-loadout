"""loadout restore --first-install: preview, ask, put the snapshot back."""
from loadout import restore_cmd, snapshot

AGENTS = {"claude": True, "codex": False}


def make(home):
    (home / ".claude").mkdir()
    (home / ".claude" / "settings.json").write_text("old")
    archive = snapshot.create(snapshot.roots(AGENTS), AGENTS)
    (home / ".claude" / "settings.json").write_text("new")
    (home / ".claude" / "added.json").write_text("added")
    return archive


def test_restore_first_install_previews_and_asks(fake_home, capsys):
    make(fake_home)
    log = []
    code = restore_cmd.run_first_install(False, lambda q: log.append(q) or "y", True)
    out = capsys.readouterr().out
    assert code == 0
    assert (fake_home / ".claude" / "settings.json").read_text() == "old"
    assert not (fake_home / ".claude" / "added.json").exists()
    assert ".claude/settings.json" in out and ".claude/added.json" in out
    assert log[0].startswith("Put your setup from ") and log[0].endswith(" back? [y/N] ")


def test_restore_first_install_no_answer_changes_nothing(fake_home, capsys):
    make(fake_home)
    assert restore_cmd.run_first_install(False, lambda q: "", True) == 0
    assert (fake_home / ".claude" / "settings.json").read_text() == "new"
    assert "nothing restored" in capsys.readouterr().out


def test_restore_first_install_yes_asks_nothing(fake_home):
    make(fake_home)

    def never(q):
        raise AssertionError(q)

    assert restore_cmd.run_first_install(True, never, False) == 0
    assert (fake_home / ".claude" / "settings.json").read_text() == "old"


def test_restore_first_install_no_terminal_without_yes_refuses(fake_home, capsys):
    make(fake_home)
    assert restore_cmd.run_first_install(False, lambda q: "y", False) == 1
    assert (fake_home / ".claude" / "settings.json").read_text() == "new"
    assert "--yes" in capsys.readouterr().out


def test_restore_first_install_without_a_snapshot_exits_1(fake_home, capsys):
    assert restore_cmd.run_first_install(True, lambda q: "y", False) == 1
    assert "no snapshot" in capsys.readouterr().out.lower()


def test_preview_lists_at_most_20_names(fake_home, capsys):
    (fake_home / ".claude").mkdir()
    for i in range(30):
        (fake_home / ".claude" / f"f{i:02}.json").write_text("x")
    snapshot.create(snapshot.roots(AGENTS), AGENTS)
    restore_cmd.run_first_install(False, lambda q: "", True)
    out = capsys.readouterr().out
    assert "30 files" in out and "f19.json" in out and "f25.json" not in out and "and 10 more" in out


def test_the_flag_reaches_restore_from_the_cli(fake_home, monkeypatch):
    from loadout import __main__ as main
    seen = {}
    monkeypatch.setattr(restore_cmd, "run_first_install", lambda yes, ask, interactive: seen.update(yes=yes) or 0)
    assert main.main(["restore", "--first-install", "--yes"]) == 0
    assert seen == {"yes": True}


def test_bootstrap_snapshot_flags_reach_python(fake_home, monkeypatch):
    from loadout import __main__ as main, bootstrap
    seen = []
    monkeypatch.setattr(bootstrap, "bootstrap", lambda *a, **k: seen.append(k.get("snapshot")) or 0)
    main.main(["bootstrap", "--no-snapshot"])
    main.main(["bootstrap", "--snapshot"])
    main.main(["bootstrap"])
    assert seen == [False, True, None]
