from loadout import paths


def test_codex_reviewer_agent_carries_the_rubric_and_its_licence():
    text = (paths.kit_root() / "plugins/codex-reviewer/agents/codex-reviewer.md").read_text(encoding="utf-8")
    assert text.startswith("---\nname: codex-reviewer\n")
    assert "openai/codex" in text and "Apache License 2.0" in text
    assert "[P0]" in text and "overall_correctness" in text and "Code Review Rules" in text
    assert "codex-reviewer" in (paths.kit_root() / "CONTRIBUTING.md").read_text(encoding="utf-8")


def test_codex_reviewer_ships_the_apache_license_text():
    plugin = paths.kit_root() / "plugins/codex-reviewer"
    text = (plugin / "LICENSE-APACHE-2.0").read_text(encoding="utf-8")
    assert "Apache License" in text and "Version 2.0, January 2004" in text and "END OF TERMS AND CONDITIONS" in text
    assert "LICENSE-APACHE-2.0" in (plugin / "NOTICE").read_text(encoding="utf-8")
