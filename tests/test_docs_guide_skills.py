"""The doc skills read the kit's rules and writing guide from the clone, for Claude Code and Codex alike."""
from loadout import paths

SKILLS = paths.kit_root() / "plugins/loadout/skills"
GUIDE = "docs/explanation/documentation-strategy.md"


def test_kit_path_prints_the_kit_root(fake_home, capsys):
    from loadout.__main__ import main
    assert main(["kit-path"]) == 0
    assert capsys.readouterr().out.strip() == paths.kit_root().as_posix()  # forward slashes: Git Bash and PowerShell


def test_doc_skills_never_depend_on_claude_code_rule_links():
    for name in ("docs-sync", "docs-audit", "onboard"):
        text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
        assert "~/.claude/rules" not in text, name  # missing on a Codex-only machine
        assert "loadout kit-path" in text and "rules/docs-policy.md" in text, name


def test_doc_skills_read_the_writing_guide_sections_they_need():
    for name in ("docs-sync", "docs-audit", "onboard"):
        text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
        assert GUIDE in text, name
        assert "Diátaxis" in text and "ADRs" in text, name


def test_the_sections_the_skills_name_exist_in_the_guide():
    guide = (paths.kit_root() / GUIDE).read_text(encoding="utf-8")
    for heading in ("## The model: one home per fact", "## Diátaxis: four kinds of docs",
                    "## ADRs: decisions with their reasons"):
        assert heading in guide, heading


def test_agents_md_has_code_review_rules():
    text = (paths.kit_root() / "AGENTS.md").read_text(encoding="utf-8")
    rules = text.split("## Code Review Rules", 1)[1]
    for topic in ("User files", "Secrets", "External commands", "Tests"):
        assert f"### {topic}" in rules, topic


def test_kit_path_uses_forward_slashes_for_a_windows_path(fake_home, capsys, monkeypatch):
    from pathlib import PureWindowsPath
    from loadout.__main__ import main
    monkeypatch.setattr(paths, "kit_root", lambda: PureWindowsPath(r"C:\Users\me\agent-loadout"))
    main(["kit-path"])
    assert capsys.readouterr().out.strip() == "C:/Users/me/agent-loadout"
