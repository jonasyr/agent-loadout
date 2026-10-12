"""The README's hero, link row and install routes, and the wordmark it shows."""
import re
import subprocess
import sys

import pytest

from loadout import paths

ROOT = paths.kit_root()
ASSETS = ROOT / "docs" / "assets"
WORDMARKS = [ASSETS / "wordmark.light.svg", ASSETS / "wordmark.dark.svg"]


def test_wordmarks_are_outlines():
    for svg in WORDMARKS:
        text = svg.read_text(encoding="utf-8")
        assert "<title>loadout</title>" in text and 'role="img"' in text and "viewBox=" in text
        for needle in ("<text", "font-family", "@import", "url(", "href="):
            assert needle not in text, f"{svg.name}: {needle} (letters must be outlines, nothing loaded)"


def test_wordmark_variants_use_the_agreed_colours():
    light, dark = (s.read_text(encoding="utf-8") for s in WORDMARKS)
    assert all(c in light for c in ('fill="#7c3aed"', 'stroke="#ffffff"', 'fill="#0f172a"'))
    assert all(c in dark for c in ('fill="#a78bfa"', 'stroke="#0f1117"', 'fill="#e6e6eb"'))


@pytest.mark.skipif(sys.platform != "linux", reason="uses fc-match from fontconfig")
def test_font_lookup_refuses_other_fonts(tmp_path):
    """fc-match falls back to any font; the script must not draw the wordmark in it."""
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "fc-match").write_text("#!/bin/sh\nprintf /usr/share/fonts/TTF/DejaVuSans-Bold.ttf\n", encoding="utf-8")
    (fake / "fc-match").chmod(0o755)
    # font_path sits above the fontTools imports, so it runs without fontTools (tests have only pytest)
    code = (
        "src = open('docs/assets/wordmark.py').read().split('from fontTools')[0];"
        "ns = {'__name__': 'wordmark'}; exec(src, ns); ns['font_path'](['wordmark.py'])"
    )
    p = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True,
                       env={"PATH": f"{fake}:/usr/bin:/bin"}, timeout=30)
    assert p.returncode != 0 and "JetBrains Mono" in p.stderr


README = ROOT / "README.md"
CURL = "curl -fsSL https://raw.githubusercontent.com/jonasyr/agent-loadout/main/bootstrap.sh | bash -s -- --install"
CLONE = "git clone https://github.com/jonasyr/agent-loadout"


def _readme():
    return README.read_text(encoding="utf-8").replace("\r", "")


def _hero(text):
    m = re.search(r'\A<div align="center">\n(.*?)\n</div>\n', text, re.S)
    assert m, 'README must open with <div align="center"> … </div>'
    return m.group(1)


def _slugs(text):
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    return {re.sub(r"[^\w\- ]", "", h.strip().lower()).replace(" ", "-") for h in re.findall(r"^#{1,6}\s+(.*)$", text, re.M)}


def test_hero_shows_the_wordmark_in_both_variants():
    hero = _hero(_readme())
    assert '<source media="(prefers-color-scheme: dark)" srcset="docs/assets/wordmark.dark.svg">' in hero
    # sized by width, so GitHub's max-width: 100% can scale it down on a phone (a fixed height would clip it)
    assert re.search(r'<img alt="loadout" src="docs/assets/wordmark\.light\.svg" width="\d+">', hero)
    assert "Claude Code, fully set up in one command." in hero


def test_hero_markdown_is_separated_by_blank_lines():
    """GitHub parses Markdown inside an HTML block only after a blank line."""
    hero = _hero(_readme())
    assert hero.startswith("\n") and hero.endswith("\n"), "blank lines after <div> and before </div>"
    blocks = hero.strip("\n").split("\n\n")
    assert blocks[0].startswith("<picture>") and blocks[0].endswith("</picture>")
    for block in blocks[1:]:
        assert not block.startswith(" "), f"indented hero block renders as code: {block[:40]!r}"


def test_link_row_points_to_headings():
    text = _readme()
    row = next(line for line in _hero(text).splitlines() if line.startswith("**[Quick start]"))
    targets = re.findall(r"\]\(#([^)]+)\)", row)
    assert [t for t in targets] and len(targets) == 5
    missing = [t for t in targets if t not in _slugs(text)]
    assert not missing, f"link row targets without a heading: {missing}"


def test_quick_start_shows_both_install_routes_in_order():
    text = _readme()
    quick = text[text.index("## Quick start"):text.index("## What you get")]
    assert CURL in quick and CLONE in quick
    assert quick.index(CURL) < quick.index(CLONE), "the one-liner comes first"
    details = "".join(re.findall(r"<details>.*?</details>", quick, re.S))
    assert CURL not in details and CLONE not in details, "neither install route may be hidden in <details>"


def test_commands_have_no_prompt_characters():
    blocks = re.findall(r"```(?:bash|powershell)\n(.*?)```", _readme(), re.S)
    assert blocks
    for block in blocks:
        for line in block.splitlines():
            assert not line.startswith(("$ ", "> ", "PS> ")), f"copy button would copy the prompt: {line}"
