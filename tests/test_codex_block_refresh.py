"""A hand edit of a rule or me.md reaches Codex's block at the next session start."""
import json

from loadout import codex, maintenance, paths


def _codex_on():
    paths.personal_root().mkdir(parents=True, exist_ok=True)
    (paths.personal_root() / "targets.json").write_text(json.dumps({"claude": True, "codex": True}))


def _agents():
    return paths.codex_home() / "AGENTS.md"


def _seed(text_before="my own notes\n", text_after="\nmore of mine\n"):
    _agents().parent.mkdir(parents=True, exist_ok=True)
    _agents().write_text(text_before + codex.START + "\nold block\n" + codex.END + text_after, encoding="utf-8")


def test_a_stale_block_is_rewritten_and_your_text_kept(fake_home, monkeypatch):
    _codex_on()
    _seed()
    monkeypatch.setattr(codex, "render_instructions", lambda: f"{codex.START}\nnew rules\n{codex.END}\n")
    maintenance.session_start(0)
    text = _agents().read_text(encoding="utf-8")
    assert "new rules" in text and "old block" not in text
    assert text.startswith("my own notes\n") and text.endswith("\nmore of mine\n")


def test_nothing_happens_with_codex_off_without_a_block_or_with_broken_markers(fake_home, monkeypatch):
    monkeypatch.setattr(codex, "render_instructions", lambda: f"{codex.START}\nnew\n{codex.END}\n")
    _seed()
    assert codex.refresh_instructions() is None  # Codex off (no targets.json)
    _codex_on()
    _agents().write_text("only mine\n", encoding="utf-8")
    assert codex.refresh_instructions() is None and _agents().read_text() == "only mine\n"
    _agents().write_text(codex.START + "\nx\n" + codex.START + "\n", encoding="utf-8")
    before = _agents().read_text()
    assert codex.refresh_instructions() is None and _agents().read_text() == before
    _agents().unlink()
    assert codex.refresh_instructions() is None and not _agents().exists()


def test_a_real_rule_edit_reaches_the_block(fake_home):
    _codex_on()
    rules = paths.personal_root() / "rules"
    rules.mkdir(parents=True)
    (rules / "me.md").write_text("I like tabs.\n", encoding="utf-8")
    _seed()
    codex.refresh_instructions()
    assert "I like tabs." in _agents().read_text(encoding="utf-8")
    (rules / "me.md").write_text("I like spaces.\n", encoding="utf-8")  # a hand edit
    maintenance.session_start(0)
    text = _agents().read_text(encoding="utf-8")
    assert "I like spaces." in text and "I like tabs." not in text


def test_windows_line_endings_stay_byte_for_byte(fake_home, monkeypatch):
    _codex_on()
    monkeypatch.setattr(codex, "render_instructions", lambda: f"{codex.START}\nnew rules\n{codex.END}\n")
    _agents().parent.mkdir(parents=True, exist_ok=True)
    mine_before, mine_after = b"my own notes\r\nline two\r\n", b"\r\nmore of mine\r\n"
    _agents().write_bytes(mine_before + codex.START.encode() + b"\r\nold\r\n" + codex.END.encode() + mine_after)
    codex.refresh_instructions()
    data = _agents().read_bytes()
    assert data.startswith(mine_before) and data.endswith(mine_after)
    assert b"new rules" in data and b"\n" not in data.replace(b"\r\n", b"")


def test_apply_instructions_keeps_windows_line_endings_too(fake_home, monkeypatch):
    from loadout import backup
    monkeypatch.setattr(codex, "render_instructions", lambda: f"{codex.START}\nnew rules\n{codex.END}\n")
    _agents().parent.mkdir(parents=True, exist_ok=True)
    _agents().write_bytes(b"mine\r\nmore\r\n")  # no block yet: it is appended
    codex.apply_instructions(backup.Backup(description="t"))
    data = _agents().read_bytes()
    assert data.startswith(b"mine\r\nmore\r\n") and b"\n" not in data.replace(b"\r\n", b"")


def test_the_refresh_is_skipped_while_another_run_sets_up_codex(fake_home, monkeypatch):
    _codex_on()
    _seed()
    monkeypatch.setattr(codex, "render_instructions", lambda: f"{codex.START}\nnew rules\n{codex.END}\n")
    lock = paths.state_dir() / codex.LOCK
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("")
    assert codex.refresh_instructions() is None and "old block" in _agents().read_text()


def test_a_damaged_targets_file_never_breaks_the_session_start(fake_home):
    paths.personal_root().mkdir(parents=True)
    (paths.personal_root() / "targets.json").write_text("{broken")
    maintenance.session_start(0)  # no exception
