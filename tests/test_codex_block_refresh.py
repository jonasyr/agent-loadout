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
