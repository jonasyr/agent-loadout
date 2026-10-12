"""The kit's and the personal layer's rules as one managed block in ~/.codex/AGENTS.md."""
from loadout import backup, codex, paths


def _personal_rules(fake_home, text="# About me\n\n- Answers: concise.\n"):
    rules = paths.personal_root() / "rules"
    rules.mkdir(parents=True)
    (rules / "me.md").write_text(text, encoding="utf-8")


def test_block_holds_kit_and_personal_rules(fake_home):
    _personal_rules(fake_home)
    block = codex.render_instructions()
    assert block.startswith(codex.START) and block.rstrip().endswith(codex.END)
    for f in sorted((paths.kit_root() / "rules").glob("*.md")):
        assert f.read_text(encoding="utf-8").strip() in block
    assert "- Answers: concise." in block
    assert block.index("docs-policy") < block.index("About me"), "kit rules first, then personal"


def test_creates_the_file_when_missing(fake_home):
    _personal_rules(fake_home)
    line = codex.apply_instructions(backup.Backup(description="t"))
    path = paths.codex_home() / "AGENTS.md"
    assert path.read_text(encoding="utf-8") == codex.render_instructions() and "written" in line


def test_appends_to_existing_text_and_backs_it_up_once(fake_home):
    _personal_rules(fake_home)
    path = paths.codex_home() / "AGENTS.md"
    path.parent.mkdir(parents=True)
    path.write_text("# My Codex notes\n\nUse tabs.\n", encoding="utf-8")
    bk = backup.Backup(description="t")
    codex.apply_instructions(bk)
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# My Codex notes\n\nUse tabs.\n") and codex.START in text
    assert not bk.empty
    bk2 = backup.Backup(description="t2")
    assert codex.apply_instructions(bk2) == "instructions up to date" and bk2.empty


def test_replaces_only_the_block(fake_home):
    _personal_rules(fake_home)
    path = paths.codex_home() / "AGENTS.md"
    path.parent.mkdir(parents=True)
    path.write_text(f"before\n\n{codex.START}\nold\n{codex.END}\n\nafter\n", encoding="utf-8")
    codex.apply_instructions(backup.Backup(description="t"))
    text = path.read_text(encoding="utf-8")
    assert text.startswith("before\n\n") and text.endswith("\n\nafter\n") and "\nold\n" not in text


def test_unbalanced_markers_leave_the_file_alone(fake_home):
    _personal_rules(fake_home)
    path = paths.codex_home() / "AGENTS.md"
    path.parent.mkdir(parents=True)
    broken = f"{codex.START}\nhalf a block\n"
    path.write_text(broken, encoding="utf-8")
    line = codex.apply_instructions(backup.Backup(description="t"))
    assert path.read_text(encoding="utf-8") == broken and line.startswith("skipped")


def test_splice_cases():
    block = f"{codex.START}\nnew\n{codex.END}\n"
    assert codex.splice("", block) == block
    assert codex.splice("mine\n", block) == "mine\n\n" + block
    assert codex.splice(f"{codex.END}\n{codex.START}\n", block) is None
    assert codex.splice(f"{codex.START}\n{codex.END}\n{codex.START}\n{codex.END}\n", block) is None
