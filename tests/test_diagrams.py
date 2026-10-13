"""The docs' diagrams: Mermaid sources in docs/diagrams/, rendered SVGs that match them, and the embeds in the docs."""
import json
import os
import re

import pytest

from diagrams_support import DIAGRAMS, HASH_COMMENT, VARIANTS, image_ref, source_hash, sources
from loadout import paths

ROOT = paths.kit_root()

FIX = "run docs/diagrams/render.sh {name} and commit the source with both SVGs"
CLASS_USE = re.compile(r"^\s*class\s+\S+\s+([\w-]+)\s*;?\s*$|:::([\w-]+)", re.M)
CLASS_DEF = re.compile(r"^\s*classDef\s+([\w,-]+)\s", re.M)
MERMAID_FENCE = re.compile(r"^\s*(```+|~~~+)\s*mermaid", re.M)
PICTURE = re.compile(r"<picture>(.*?)</picture>", re.S)
SOURCE = re.compile(r'<source media="\(prefers-color-scheme: dark\)" srcset="([^"]+)">')
IMG = re.compile(r'<img alt="([^"]*)" src="([^"]+)">')
SOURCE_LINK = re.compile(r"</picture>\n\n<sub>\[Source\]\(([^)]+)\)</sub>")


def _body(text):
    """A source without its --- frontmatter."""
    return re.sub(r"\A---\n.*?\n---\n", "", text.replace("\r", ""), flags=re.S)


def _is_flowchart(name):
    body = _body((DIAGRAMS / f"{name}.mmd").read_text(encoding="utf-8"))
    first = next(line.strip() for line in body.splitlines() if line.strip() and not line.strip().startswith("%%"))
    return first.startswith(("flowchart", "graph"))


def _used(text):
    return {a or b for a, b in CLASS_USE.findall(text)}


def _defined(text):
    return {name for names in CLASS_DEF.findall(text) for name in names.split(",")}


def test_class_scan_sees_every_syntax():
    src = "flowchart LR\n  a:::kit --> b\n  class b personal;\n  class c,d my-group\n"
    assert _used(src) == {"kit", "personal", "my-group"}
    assert _defined("  classDef kit,my-group fill:#fff\n  classDef state fill:#000\n") == {"kit", "my-group", "state"}


def test_mermaid_fences_of_both_kinds_are_found():
    assert MERMAID_FENCE.search("text\n```mermaid\nflowchart\n```\n")
    assert MERMAID_FENCE.search("text\n~~~ mermaid\nflowchart\n~~~\n")
    assert not MERMAID_FENCE.search("```python\nprint()\n```\n")


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
    defined = {v: _defined((DIAGRAMS / f"palette.{v}.mmd").read_text(encoding="utf-8")) for v in VARIANTS}
    assert defined["light"] == defined["dark"], f"palettes differ: {defined['light'] ^ defined['dark']}"
    used = set()
    for name in sources():
        used |= _used((DIAGRAMS / f"{name}.mmd").read_text(encoding="utf-8"))
    assert used <= defined["light"], f"classes used but not in the palettes: {sorted(used - defined['light'])}"


def test_themes_render_svg_text_with_system_fonts():
    for variant in VARIANTS:
        theme = json.loads((DIAGRAMS / f"theme.{variant}.json").read_text(encoding="utf-8"))
        assert theme["theme"] == "base"
        assert theme["htmlLabels"] is False and theme["flowchart"]["htmlLabels"] is False
        assert theme["themeVariables"]["fontFamily"].startswith("ui-sans-serif, system-ui")


def _diagram_pictures(text):
    """<picture> blocks that show a diagram (the README's wordmark is a <picture> too)."""
    return [block for block in PICTURE.findall(text) if "diagrams/" in block]


def _docs():
    """README.md and docs/, without the agents' working documents."""
    files = [ROOT / "README.md", *ROOT.glob("docs/**/*.md")]
    return [f for f in files if "docs/superpowers/" not in f.relative_to(ROOT).as_posix()]


def test_no_mermaid_code_blocks_left():
    left = [str(f.relative_to(ROOT)) for f in _docs() if MERMAID_FENCE.search(f.read_text(encoding="utf-8"))]
    assert not left, f"render diagrams to SVG (docs/diagrams/) instead of Mermaid code blocks: {left}"


def test_embeds_show_both_variants_with_alt_text():
    bad = []
    for md in _docs():
        for block in _diagram_pictures(md.read_text(encoding="utf-8")):
            where = md.relative_to(ROOT)
            src, img = SOURCE.search(block), IMG.search(block)
            if not (src and img):
                bad.append(f"{where}: <picture> needs a dark <source> and <img alt src> as in CONTRIBUTING.md")
                continue
            dark, (alt, light) = src.group(1), img.groups()
            if not (dark.endswith(".dark.svg") and light.endswith(".light.svg")
                    and dark[: -len(".dark.svg")] == light[: -len(".light.svg")]):
                bad.append(f"{where}: {dark} and {light} are not one diagram's two variants")
            for ref in (dark, light):
                if not (md.parent / ref).exists():
                    bad.append(f"{where}: {ref} does not exist")
            if len(alt.strip()) < 40 or alt.strip().lower().startswith("diagram"):
                bad.append(f"{where}: alt text must say what the diagram shows ({alt!r})")
    assert not bad, "\n".join(bad)


def test_each_embed_links_its_source():
    bad = []
    for md in _docs():
        text = md.read_text(encoding="utf-8").replace("\r", "")
        pictures = len(_diagram_pictures(text))
        links = SOURCE_LINK.findall(text)
        if len(links) != pictures:
            bad.append(f"{md.relative_to(ROOT)}: each </picture> needs a blank line, then <sub>[Source](….mmd)</sub>")
        bad += [f"{md.relative_to(ROOT)}: {ref} does not exist" for ref in links if not (md.parent / ref).exists()]
    assert not bad, "\n".join(bad)


def test_every_diagram_is_embedded():
    embedded = set()
    for md in _docs():
        for light in IMG.findall(md.read_text(encoding="utf-8")):
            embedded.add((md.parent / light[1]).resolve())
    missing = [n for n in sources() if (DIAGRAMS / f"{n}.light.svg").resolve() not in embedded]
    assert not missing, f"diagrams no page shows (embed or delete them): {missing}"


@pytest.mark.skipif(os.name == "nt", reason="git checks symlinks out as files on Windows runners")
def test_diagram_skill_reaches_both_agents():
    skill = ROOT / ".claude" / "skills" / "diagrams" / "SKILL.md"
    front = re.match(r"---\n(.*?)\n---\n", skill.read_text(encoding="utf-8"), re.S)
    assert front, "SKILL.md needs YAML frontmatter"
    assert re.search(r"^name: diagrams$", front.group(1), re.M)
    assert re.search(r"^description: \S", front.group(1), re.M)
    link = ROOT / ".agents" / "skills" / "diagrams"
    assert link.is_symlink() and os.readlink(link) == "../../.claude/skills/diagrams"
