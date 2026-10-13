from loadout import paths


def test_codex_reviewer_agent_carries_the_rubric_and_its_licence():
    text = (paths.kit_root() / ".claude/agents/codex-reviewer.md").read_text(encoding="utf-8")
    assert text.startswith("---\nname: codex-reviewer\n")
    assert "openai/codex" in text and "Apache License 2.0" in text
    assert "[P0]" in text and "overall_correctness" in text and "Code Review Rules" in text
    assert "codex-reviewer" in (paths.kit_root() / "CONTRIBUTING.md").read_text(encoding="utf-8")
