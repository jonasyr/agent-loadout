"""Findings of the final review of repo-agents PR 4."""
import json

import pytest

from loadout import __main__ as cli, backup, bootstrap, out, paths, restore_cmd, wsl

NOW = 2_000_000_000.0


def make(desc, ago, tmp_path):
    f = tmp_path / f"{desc}.txt"
    f.write_text(desc)
    bk = backup.Backup(description=desc)
    bk._created_at = NOW - ago
    bk.record_created(f, f"{desc} (created)")
    return f, bk


def test_last_asks_in_a_terminal(fake_home, fake_runner, tmp_path):
    f, _ = make("a", 60, tmp_path)
    asked = []
    assert restore_cmd.run(None, False, True, None, False, lambda q: asked.append(q) or "n", True, now=NOW) == 0
    assert asked == [restore_cmd.CONFIRM] and f.exists()


def test_show_prints_what_a_backup_puts_back_and_changes_nothing(fake_home, fake_runner, tmp_path, capsys):
    f, bk = make("a", 60, tmp_path)
    assert restore_cmd.run(str(bk.root), False, False, None, False, lambda q: pytest.fail("asked"), True,
                           now=NOW, show=True) == 0
    assert "take away" in capsys.readouterr().out and f.exists()


def test_the_cli_has_show(fake_home, monkeypatch):
    got = {}
    monkeypatch.setattr(restore_cmd, "run", lambda *a, **k: got.update(k) or 0)
    assert cli.main(["restore", "--show", "x"]) == 0 and got["show"] is True


def test_a_failed_vscode_switch_is_a_warning(fake_home, fake_runner, monkeypatch, tmp_path):
    home = tmp_path / "winhome"
    monkeypatch.setattr(wsl, "detect", lambda *a, **k: 2)
    monkeypatch.setattr(wsl, "codex_side", lambda **k: wsl.CodexSide("wsl", ["r"], windows_home=home))
    seen = []
    monkeypatch.setattr(out, "status", lambda name, msg, level="ok": seen.append((name, level)))
    bootstrap.codex_gate("wsl", ask=lambda q: "", interactive=False, bk=backup.Backup(description="t"), vscode=True)
    assert seen == [("VS Code", "warn")]


def test_manifest_text_cannot_drive_the_terminal(fake_home, fake_runner, tmp_path, capsys):
    bk = backup.Backup(description="evil\x1b[2J")
    bk._created_at = NOW - 60
    bk.record_created(tmp_path / "x\x1b]0;owned\x07", "label\x1b[2J")
    assert restore_cmd.run(None, False, False, None, False, lambda q: "", True, now=NOW) == 0  # the list, then cancel
    restore_cmd.run(str(bk.root), False, False, None, False, lambda q: "", True, now=NOW, show=True)
    printed = capsys.readouterr().out
    assert "\x1b" not in printed and "\x07" not in printed


def test_a_superscript_digit_is_asked_again(fake_home, fake_runner, tmp_path):
    f, _ = make("a", 60, tmp_path)
    asked = []
    answers = iter(["²", ""])
    assert restore_cmd.run(None, False, False, None, False, lambda q: asked.append(q) or next(answers), True, now=NOW) == 0
    assert len(asked) == 2 and f.exists()


def test_an_infinite_or_odd_manifest_is_listed_without_a_crash(fake_home, fake_runner, tmp_path):
    root = paths.backups_root() / "loadout-odd"
    root.mkdir(parents=True)
    (root / "manifest.json").write_text('{"description": "odd", "created_at": Infinity, "repo": "a\\u0000b", "steps": []}')
    infos = backup.backups()
    assert [b.description for b in infos] == ["odd"]
    assert isinstance(backup.age(infos[0].created, NOW), str)
    assert backup.backups(tmp_path / "repo") == []


@pytest.mark.parametrize("flags", [dict(list_only=True), dict(last=True)])
def test_a_path_with_list_or_last_restores_nothing(fake_home, fake_runner, tmp_path, capsys, flags):
    f, bk = make("a", 60, tmp_path)
    kw = {"list_only": False, "last": False, **flags}
    rc = restore_cmd.run(str(bk.root), kw["list_only"], kw["last"], None, False, lambda q: pytest.fail("asked"), True, now=NOW)
    assert rc == 2 and f.exists() and "nothing restored" in capsys.readouterr().out


def test_the_cli_list_with_a_path_restores_nothing(fake_home, fake_runner, tmp_path, monkeypatch):
    f, bk = make("a", 60, tmp_path)
    assert cli.main(["restore", "--list", str(bk.root)]) == 2 and f.exists()


def test_previews_and_rows_mask_a_token_in_a_path(fake_home, fake_runner, tmp_path, capsys):
    token = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
    repo = tmp_path / f"repo-{token}"
    bk = backup.Backup(description="x", repo=repo)
    bk._created_at = NOW - 60
    bk.record_created(repo / "f.txt", "f")
    assert all(token not in line for line in backup.contents(backup.backups()[0]))
    restore_cmd.run(None, False, False, None, False, lambda q: "", True, now=NOW)
    restore_cmd.run(str(bk.root), False, False, None, False, lambda q: "", True, now=NOW, show=True)
    restore_cmd.run(None, True, False, None, False, lambda q: "", False, now=NOW)
    assert token not in capsys.readouterr().out
