"""The docs' diagrams: Mermaid sources in docs/diagrams/, rendered SVGs that match them, and the embeds in the docs."""
import json
import re

from diagrams_support import DIAGRAMS, HASH_COMMENT, VARIANTS, image_ref, source_hash, sources

FIX = "run docs/diagrams/render.sh {name} and commit the source with both SVGs"
CLASS_USE = re.compile(r"^\s*class\s+\S+\s+(\w+)\s*$", re.M)
CLASS_DEF = re.compile(r"^\s*classDef\s+(\w+)\s", re.M)


def _body(text):
    """A source without its --- frontmatter."""
    return re.sub(r"\A---\n.*?\n---\n", "", text.replace("\r", ""), flags=re.S)


def _is_flowchart(name):
    body = _body((DIAGRAMS / f"{name}.mmd").read_text(encoding="utf-8"))
    first = next(line.strip() for line in body.splitlines() if line.strip() and not line.strip().startswith("%%"))
    return first.startswith(("flowchart", "graph"))


def test_there_are_diagrams():
    assert sources(), "docs/diagrams/ holds no diagram sources"


def test_every_svg_matches_its_source():
    image = image_ref(DIAGRAMS / "render.sh")
    problems = []
    for name in sources():
        for variant in VARIANTS:
            svg = DIAGRAMS / f"{name}.{variant}.svg"
            if not svg.exists():
                problems.append(f"{svg.name} is missing: " + FIX.format(name=name))
                continue
            found = HASH_COMMENT.findall(svg.read_text(encoding="utf-8"))
            if found != [source_hash(DIAGRAMS, name, variant, image)]:
                problems.append(f"{svg.name} is out of date: " + FIX.format(name=name))
    assert not problems, "\n".join(problems)


def test_no_svg_without_a_source():
    names = set(sources())
    orphans = []
    for svg in DIAGRAMS.glob("*.svg"):
        stem, _, variant = svg.name[: -len(".svg")].rpartition(".")
        if stem not in names or variant not in VARIANTS:
            orphans.append(svg.name)
    assert not orphans, f"SVGs without a <name>.mmd source (delete them or add the source): {orphans}"


def test_svgs_have_no_html_labels_or_external_resources():
    bad = []
    for svg in DIAGRAMS.glob("*.svg"):
        text = svg.read_text(encoding="utf-8")
        for needle in ("<foreignObject", "@import", "url(http"):
            if needle in text:
                bad.append(f"{svg.name}: {needle}")
    assert not bad, "image viewers drop HTML labels and cannot load external resources:\n" + "\n".join(bad)


def test_flowcharts_take_their_colours_from_the_palette():
    bad = []
    for name in filter(_is_flowchart, sources()):
        body = _body((DIAGRAMS / f"{name}.mmd").read_text(encoding="utf-8"))
        if not re.search(r"^\s*%% palette\s*$", body, re.M):
            bad.append(f"{name}: no '%% palette' line")
        for pattern in (r"^\s*classDef\b", r"^\s*style\b", r"^\s*linkStyle\b", r"#[0-9a-fA-F]{3,8}\b"):
            if re.search(pattern, body, re.M):
                bad.append(f"{name}: {pattern} (colours belong in palette.<variant>.mmd)")
    assert not bad, "\n".join(bad)


def test_palettes_define_every_class_used():
    defined = {v: set(CLASS_DEF.findall((DIAGRAMS / f"palette.{v}.mmd").read_text(encoding="utf-8"))) for v in VARIANTS}
    assert defined["light"] == defined["dark"], f"palettes differ: {defined['light'] ^ defined['dark']}"
    used = set()
    for name in sources():
        used |= set(CLASS_USE.findall((DIAGRAMS / f"{name}.mmd").read_text(encoding="utf-8")))
    assert used <= defined["light"], f"classes used but not in the palettes: {sorted(used - defined['light'])}"


def test_themes_render_svg_text_with_system_fonts():
    for variant in VARIANTS:
        theme = json.loads((DIAGRAMS / f"theme.{variant}.json").read_text(encoding="utf-8"))
        assert theme["theme"] == "base"
        assert theme["htmlLabels"] is False and theme["flowchart"]["htmlLabels"] is False
        assert theme["themeVariables"]["fontFamily"].startswith("ui-sans-serif, system-ui")
