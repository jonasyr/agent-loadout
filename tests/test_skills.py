import re

from loadout import paths

SKILLS = paths.kit_root() / "plugins/loadout/skills"
FRONTMATTER = re.compile(r"---\r?\nname: (.+?)\r?\ndescription: (.+?)\r?\n((?:[a-z-]+: .+\r?\n)*)---\r?\n")


def _frontmatter(name):
    text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
    m = FRONTMATTER.match(text)
    assert m, name
    extra = dict(line.split(": ", 1) for line in m.group(3).splitlines())
    return m.group(1), m.group(2), extra, text


def test_skills_have_frontmatter_and_short_descriptions():
    for name in ("onboard", "docs-sync", "docs-audit", "configure"):
        got, description, extra, _ = _frontmatter(name)
        assert got == name
        assert len(description) <= 400, f"{name} description too long (loaded every session)"
        assert set(extra) <= {"disable-model-invocation"}, name


def test_heavy_skills_are_user_invoked_only():
    for name in ("onboard", "docs-audit"):
        assert _frontmatter(name)[2].get("disable-model-invocation") == "true", name
    for name in ("docs-sync", "configure"):
        assert "disable-model-invocation" not in _frontmatter(name)[2], name


def test_onboard_new_project_does_not_hand_off_to_brainstorming():
    text = _frontmatter("onboard")[3]
    new_project = text.split("## 2a. New project", 1)[1].split("## 2b.", 1)[0]
    assert "Invoke `superpowers:brainstorming`" not in new_project
    for topic in ("purpose", "users", "stack", "constraints"):
        assert topic in new_project.lower(), topic
    assert "one at a time" in new_project
    assert "docs/adr/0001" in new_project and "AGENTS.md" in new_project and "docs/README.md" in new_project
    assert "superpowers:brainstorming" in new_project.split("Stop")[-1]  # suggested at the end, for the first feature
