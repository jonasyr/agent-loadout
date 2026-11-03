"""Bootstrap offers a snapshot of the setup before its first write (first-install snapshot, Task 2)."""
import hashlib
import tarfile

import pytest

from loadout import apply, bootstrap, paths, snapshot

QUESTION = "Save a snapshot of your current setup first"


def seed(home):
    (home / ".claude").mkdir()
    (home / ".claude" / "settings.json").write_text('{"mine": 1}')
    (home / ".bashrc").write_text("export MINE=1\n")


def run(ask, interactive=True, yes=False, **kw):
    return bootstrap.bootstrap(False, yes, False, False, ask=ask, interactive=interactive, agents="claude", **kw)


def asked(log, answer=""):
    def ask(q):
        log.append(q)
        return answer
    return ask


def question_in(log):
    return [q for q in log if QUESTION in q]


def archives():
    return list(paths.backups_root().glob("first-install-*.tar.gz"))


def test_first_install_asks_and_snapshots(fake_home, fake_runner, capsys):
    seed(fake_home)
    log = []
    run(asked(log))
    question = question_in(log)
    assert question and question[0].rstrip().endswith("[Y/n]") and ", into ~" in question[0]
    assert len(archives()) == 1
    out = capsys.readouterr().out
    assert f"snapshot: {archives()[0]}" in out
    assert out.count("loadout restore --first-install") >= 2  # at the step and in the summary


def test_answer_no_takes_none(fake_home, fake_runner):
    seed(fake_home)
    run(asked([], "n"))
    assert archives() == []


def test_rerun_never_asks(fake_home, fake_runner):
    seed(fake_home)
    run(asked([]))
    log = []
    run(asked(log))
    assert not question_in(log)
    assert len(archives()) == 1


def test_no_snapshot_flag_skips(fake_home, fake_runner):
    seed(fake_home)
    log = []
    run(asked(log), snapshot=False)
    assert not question_in(log) and archives() == []


def test_snapshot_flag_takes_one_on_a_rerun_without_asking(fake_home, fake_runner):
    seed(fake_home)
    run(asked([]))
    log = []
    run(asked(log), snapshot=True)
    assert not question_in(log)
    assert len(archives()) == 2


@pytest.mark.parametrize("kw", [{"interactive": False}, {"yes": True}])
def test_yes_and_no_terminal_take_the_snapshot(fake_home, fake_runner, kw):
    seed(fake_home)
    log = []
    run(asked(log), **kw)
    assert not question_in(log)
    assert len(archives()) == 1


def test_codex_off_snapshot_never_reads_codex_home(fake_home, fake_runner):
    seed(fake_home)
    (fake_home / ".codex").mkdir()
    (fake_home / ".codex" / "config.toml").write_text("x = 1\n")
    run(asked([]))
    with tarfile.open(archives()[0]) as tar:
        assert not [n for n in tar.getnames() if n.startswith(".codex")]


def test_snapshot_runs_before_any_agent_file_changes(fake_home, fake_runner, monkeypatch):
    seed(fake_home)
    files = [fake_home / ".claude" / "settings.json", fake_home / ".bashrc"]

    def digest():
        return [hashlib.sha256(f.read_bytes()).hexdigest() for f in files]

    before = digest()
    seen = {}
    real_create, real_link = snapshot.create, apply.link_step

    def create(roots, agents):
        seen["at_create"] = digest()
        seen["claude_dir"] = sorted(p.name for p in (fake_home / ".claude").iterdir())
        return real_create(roots, agents)

    def link_step(*a, **k):
        seen["archive_at_first_write"] = bool(archives())
        return real_link(*a, **k)

    monkeypatch.setattr(snapshot, "create", create)
    monkeypatch.setattr(apply, "link_step", link_step)
    run(asked([]))
    assert seen["at_create"] == before and seen["claude_dir"] == ["settings.json"]
    assert seen["archive_at_first_write"] is True


def test_failed_snapshot_stops_before_changes(fake_home, fake_runner, monkeypatch, capsys):
    seed(fake_home)

    def boom(roots, agents):
        raise OSError("disk full")

    monkeypatch.setattr(snapshot, "create", boom)
    assert run(asked([])) == 1  # the follow-up question defaults to no
    assert "disk full" in capsys.readouterr().out
    assert sorted(p.name for p in (fake_home / ".claude").iterdir()) == ["settings.json"]
    assert (fake_home / ".bashrc").read_text() == "export MINE=1\n"


def test_failed_snapshot_can_continue_with_a_yes(fake_home, fake_runner, monkeypatch):
    seed(fake_home)

    def boom(roots, agents):
        raise OSError("disk full")

    monkeypatch.setattr(snapshot, "create", boom)
    run(lambda q: "y" if "Go on without" in q else "")  # take the snapshot (fails), then continue anyway
    assert len(list((fake_home / ".claude").iterdir())) > 1


def test_nothing_to_snapshot_asks_nothing(fake_home, fake_runner):
    log = []
    run(asked(log))
    assert not question_in(log) and archives() == []
