import re

from loadout import paths

SKILLS = paths.kit_root() / "plugins/loadout/skills"


def test_skills_have_frontmatter_and_short_descriptions():
    for name in ("onboard", "docs-sync", "docs-audit", "configure"):
        text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
        m = re.match(r"---\nname: (.+)\ndescription: (.+)\n---\n", text)
        assert m, name
        assert m.group(1) == name
        assert len(m.group(2)) <= 400, f"{name} description too long (loaded every session)"
