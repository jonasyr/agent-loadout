"""rtk's config.toml: where it lives, and loadout's one line that silences rtk's false "No hook installed" warning
where loadout's plugin provides the hook (ADR 0043). Never the real rtk config; rtk never runs."""
import sys

from loadout import paths


def test_rtk_config_path_per_os(fake_home, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    assert paths.rtk_config() == fake_home / ".config/rtk/config.toml"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(fake_home / "xdg"))
    assert paths.rtk_config() == fake_home / "xdg/rtk/config.toml"
    monkeypatch.setenv("XDG_CONFIG_HOME", "relative")  # not absolute: ignored, as rtk's dirs crate does
    assert paths.rtk_config() == fake_home / ".config/rtk/config.toml"
    monkeypatch.setattr(sys, "platform", "darwin")
    assert paths.rtk_config() == fake_home / "Library/Application Support/rtk/config.toml"
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(fake_home / "AD"))
    assert paths.rtk_config() == fake_home / "AD/rtk/config.toml"
    monkeypatch.delenv("APPDATA")
    assert paths.rtk_config() == fake_home / "AppData/Roaming/rtk/config.toml"


import json  # noqa: E402

from loadout import apply as apply_mod, backup, duplicates, rtk_config, targets  # noqa: E402

LINE = "suppress_hook_warning = true"


def _wanted(monkeypatch, fake_runner, on=True):
    monkeypatch.setattr(targets, "OVERRIDE", {"claude": on, "codex": False})
    monkeypatch.setattr(duplicates, "plugin_enabled", lambda: on)
    monkeypatch.setattr(duplicates, "plugin_guarded_hooks", lambda p: [("PreToolUse", "rtk hook claude")] if on else [])
    fake_runner.missing = set() if on else {"rtk"}


def _run(dry=False):
    bk = backup.Backup(description="t")
    return bk, rtk_config.apply(bk, dry_run=dry)


def _cfg(fake_home):
    return fake_home / ".config/rtk/config.toml"


def _put(fake_home, text):
    p = _cfg(fake_home)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(text.encode())
    return p


def _rec():
    return json.loads(rtk_config.record_path().read_text())


def test_creates_file_when_missing(fake_home, fake_runner, monkeypatch):
    _wanted(monkeypatch, fake_runner)
    bk, out = _run()
    assert _cfg(fake_home).read_text() == "[hooks]\nsuppress_hook_warning = true\n"
    assert any("created" in s["undo"] for s in bk.steps)
    assert _rec()["created"] is True and _rec()["line"] == LINE
    assert len(out) == 1 and "silenced" in out[0]


def test_inserts_into_user_hooks_table_keeping_text(fake_home, fake_runner, monkeypatch):
    _wanted(monkeypatch, fake_runner)
    old = '# mine\n[hooks]\nexclude_commands = ["curl"] # keep\n\n[display]\ncolors = true\n'
    p = _put(fake_home, old)
    _run()
    assert p.read_text() == '# mine\n[hooks]\nexclude_commands = ["curl"] # keep\n' + LINE + '\n\n[display]\ncolors = true\n'
    assert _rec()["header"] is False and _rec()["created"] is False


def test_appends_table_when_no_hooks(fake_home, fake_runner, monkeypatch):
    _wanted(monkeypatch, fake_runner)
    p = _put(fake_home, "[display]\ncolors = true")
    _run()
    assert p.read_text() == "[display]\ncolors = true\n\n[hooks]\n" + LINE + "\n"
    assert _rec()["header"] is True


def test_crlf_and_missing_final_newline(fake_home, fake_runner, monkeypatch):
    _wanted(monkeypatch, fake_runner)
    p = _put(fake_home, "[display]\r\ncolors = true")
    _run()
    assert p.read_bytes() == b"[display]\r\ncolors = true\r\n\r\n[hooks]\r\n" + LINE.encode() + b"\r\n"
    p.write_bytes(b"[hooks]\r\nx = 1\r\n[d]\r\n")
    rtk_config.record_path().unlink()
    _run()
    assert p.read_bytes() == b"[hooks]\r\nx = 1\r\n" + LINE.encode() + b"\r\n[d]\r\n"


def test_user_true_is_left_unrecorded(fake_home, fake_runner, monkeypatch):
    _wanted(monkeypatch, fake_runner)
    old = "[hooks]\nsuppress_hook_warning = true  # mine\n"
    p = _put(fake_home, old)
    bk, out = _run()
    assert out == [] and p.read_text() == old and not rtk_config.record_path().exists() and bk.empty


def test_user_false_left_and_said_once(fake_home, fake_runner, monkeypatch):
    _wanted(monkeypatch, fake_runner)
    old = "[hooks]\nsuppress_hook_warning = false\n"
    p = _put(fake_home, old)
    _, first = _run()
    _, second = _run()
    assert len(first) == 1 and "left as is" in first[0] and apply_mod.refused(first) == []
    assert second == [] and p.read_text() == old


def test_inline_or_dotted_hooks_left_and_said_once(fake_home, fake_runner, monkeypatch):
    _wanted(monkeypatch, fake_runner)
    for old in ("hooks = { exclude_commands = [] }\n", "hooks.exclude_commands = []\n"):
        rtk_config.record_path().unlink(missing_ok=True)
        p = _put(fake_home, old)
        _, first = _run()
        _, second = _run()
        assert len(first) == 1 and "by hand" in first[0] and len(apply_mod.refused(first)) == 1
        assert second == [] and p.read_text() == old


def test_unparseable_left(fake_home, fake_runner, monkeypatch):
    _wanted(monkeypatch, fake_runner)
    p = _put(fake_home, "[hooks\nbroken")
    _, out = _run()
    assert out == ["skipped rtk config.toml: it does not parse now; left as is"] and apply_mod.refused(out)
    assert p.read_text() == "[hooks\nbroken"


def test_dry_run_writes_nothing(fake_home, fake_runner, monkeypatch):
    _wanted(monkeypatch, fake_runner)
    bk, out = _run(dry=True)
    assert "to silence" in out[0] and not _cfg(fake_home).exists() and not rtk_config.record_path().exists() and bk.empty


def test_idempotent(fake_home, fake_runner, monkeypatch):
    _wanted(monkeypatch, fake_runner)
    _run()
    text = _cfg(fake_home).read_text()
    _, out = _run()
    assert out == [] and _cfg(fake_home).read_text() == text


def test_removed_when_not_wanted(fake_home, fake_runner, monkeypatch):
    _wanted(monkeypatch, fake_runner)
    # a user's table, loadout's line only
    old = "[hooks]\nx = 1\n\n[d]\ny = 2\n"
    p = _put(fake_home, old)
    _run()
    _wanted(monkeypatch, fake_runner, on=False)
    _, out = _run()
    assert p.read_text() == old and "removed" in out[0] and not rtk_config.record_path().exists()
    # loadout's header goes with its line
    _wanted(monkeypatch, fake_runner)
    p.write_text("[d]\ny = 2\n")
    _run()
    _wanted(monkeypatch, fake_runner, on=False)
    _run()
    assert p.read_text() == "[d]\ny = 2\n"
    # a file loadout created goes
    _wanted(monkeypatch, fake_runner)
    p.unlink()
    _run()
    assert p.exists()
    _wanted(monkeypatch, fake_runner, on=False)
    _run()
    assert not p.exists()


def test_removal_keeps_user_lines_in_shared_hooks_table(fake_home, fake_runner, monkeypatch):
    _wanted(monkeypatch, fake_runner)
    p = _put(fake_home, "[hooks]\nexclude_commands = [\"a\"]\n")
    _run()
    p.write_text(p.read_text() + "other = 1\n")
    _wanted(monkeypatch, fake_runner, on=False)
    _run()
    assert p.read_text() == "[hooks]\nexclude_commands = [\"a\"]\nother = 1\n"


def test_edited_line_is_released_not_removed(fake_home, fake_runner, monkeypatch):
    _wanted(monkeypatch, fake_runner)
    p = _put(fake_home, "[hooks]\nx = 1\n")
    _run()
    edited = p.read_text().replace(LINE, LINE + "  # mine")
    p.write_text(edited)
    _wanted(monkeypatch, fake_runner, on=False)
    bk, out = _run()
    assert out == [] and p.read_text() == edited and not rtk_config.record_path().exists()


def test_restore_of_created_file_then_apply_again(fake_home, fake_runner, monkeypatch):
    _wanted(monkeypatch, fake_runner)
    bk, _ = _run()
    backup.restore(bk.root)
    assert not _cfg(fake_home).exists()
    _, out = _run()
    assert _cfg(fake_home).read_text() == "[hooks]\nsuppress_hook_warning = true\n" and "silenced" in out[0]


def test_backup_saves_record_and_config_before_write(fake_home, fake_runner, monkeypatch):
    _wanted(monkeypatch, fake_runner)
    _put(fake_home, "[hooks]\nx = 1\n")
    _run()
    bk, _ = _run()  # nothing to do
    assert bk.empty
    _wanted(monkeypatch, fake_runner, on=False)
    bk, _ = _run()
    saved = [list(s["undo"].get("restore-file", ["", ""]))[1] for s in bk.steps]
    assert str(rtk_config.record_path()) in saved and str(_cfg(fake_home)) in saved


def test_not_wanted_and_never_written_is_silent(fake_home, fake_runner, monkeypatch):
    _wanted(monkeypatch, fake_runner, on=False)
    bk, out = _run()
    assert out == [] and not _cfg(fake_home).exists() and bk.empty


def test_trailing_whitespace_of_last_hooks_line_kept(fake_home, fake_runner, monkeypatch):
    _wanted(monkeypatch, fake_runner)
    for old in ("[hooks]\nexclude_commands = []   \n\n[display]\n", "[hooks]\nx = 1 # c\t\n[d]\n",
                "[hooks]\nx = 1  ", "[display]\na = 1\n", "[display]\na = 1"):
        rtk_config.record_path().unlink(missing_ok=True)
        p = _put(fake_home, old)
        _wanted(monkeypatch, fake_runner)
        _run()
        new = p.read_bytes().decode()
        assert LINE in new and tomllib_ok(new)
        if old.startswith("[hooks]\nexclude"):
            assert new == "[hooks]\nexclude_commands = []   \n" + LINE + "\n\n[display]\n"
        if old.startswith("[hooks]\nx = 1 #"):
            assert new == "[hooks]\nx = 1 # c\t\n" + LINE + "\n[d]\n"
        _, again = _run()
        assert again == [] and _rec()["line"] == LINE
        _wanted(monkeypatch, fake_runner, on=False)
        _run()
        assert p.read_bytes().decode() == old


def tomllib_ok(text):
    import tomllib
    tomllib.loads(text)
    return True


def test_record_written_after_config(fake_home, fake_runner, monkeypatch):
    _wanted(monkeypatch, fake_runner)

    def boom(*a, **k):
        raise OSError("disk")
    monkeypatch.setattr(rtk_config, "write_atomic", boom)
    try:
        _run()
    except OSError:
        pass
    assert not rtk_config.record_path().exists()
